"""EpdBridge — Python-клиент для ESP32-моста (firmware/epd_bridge.ino).

Диспетчер опкодов 0x01–0x0E поверх USB-Serial.

Протокол: бинарные опкоды, big-endian, каждый возвращает 2-байтный status
(0x0000 = OK). См. ``firmware/README.md`` для полной таблицы.

Использование:
    from python.bridge import EpdBridge
    with EpdBridge(port="/dev/cu.SLAB_USBtoUART") as br:
        br.ping()
        br.init()
        br.write_lut_dynamic(my_lut.encode())

Для unit-тестов конструктор принимает любой serial.Serial-like объект
через параметр ``ser``.
"""

from __future__ import annotations

import logging
import struct
import time
from contextlib import contextmanager
from typing import Iterator, Protocol

from .ina219 import Trace, parse_bench_response, parse_ina_read_response

logger = logging.getLogger(__name__)

# ---- Опкоды (синхронизировано с firmware/epd_bridge.ino) -----------------

OP_INIT                = 0x01
OP_FRAME               = 0x02
OP_REFRESH             = 0x03
OP_SLEEP               = 0x04
OP_LUT                 = 0x05
OP_PING                = 0x06
OP_INA_READ            = 0x07
OP_REFRESH_PARTIAL     = 0x08
OP_INIT_PARTIAL        = 0x09
OP_INIT_PARTIAL_FAST   = 0x0A
OP_REFRESH_CUSTOM_LUT  = 0x0B
OP_WRITE_LUT_DYNAMIC   = 0x0C
OP_WRITE_REGISTER      = 0x0D
OP_BENCH_RUN           = 0x0E
OP_BENCH_FACTORY       = 0x0F

# 0x22-байты заводского refresh для BENCH_FACTORY.
REFRESH_FULL_F7 = 0xF7   # B0: полный заводский refresh (load temp + Mode 1)
REFRESH_FAST_C7 = 0xC7   # B1: Mode 1 без перезагрузки LUT (после init_partial_fast)

# ---- Статусы --------------------------------------------------------------

STATUS_OK            = 0x0000
STATUS_BAD_OPCODE    = 0xFF01
STATUS_TIMEOUT_RX    = 0xFF02
STATUS_TIMEOUT_BUSY  = 0xFF03
STATUS_INA_NACK     = 0xFF04

_STATUS_NAMES = {
    STATUS_OK:           "OK",
    STATUS_BAD_OPCODE:   "BAD_OPCODE",
    STATUS_TIMEOUT_RX:   "TIMEOUT_RX",
    STATUS_TIMEOUT_BUSY: "TIMEOUT_BUSY",
    STATUS_INA_NACK:     "INA_NACK",
}

# ---- Константы геометрии ---------------------------------------------------

EPD_FRAME_SIZE = 4000   # 128 × 250 / 8
EPD_LUT_SIZE   = 153

DEFAULT_BAUDRATE = 921600
DEFAULT_TIMEOUT  = 12.0   # ≥ BUSY_TIMEOUT_MS прошивки (10 с) + запас


class BridgeError(RuntimeError):
    """Ошибка протокола моста (timeout, bad opcode, INA NACK и т.д.)."""

    def __init__(self, status: int, context: str = ""):
        name = _STATUS_NAMES.get(status, f"UNKNOWN_0x{status:04X}")
        msg = f"BridgeError({name})"
        if context:
            msg += f" в {context}"
        super().__init__(msg)
        self.status = status


class _SerialLike(Protocol):
    """Минимальный интерфейс, нужный bridge'у от serial-объекта."""

    def write(self, data: bytes) -> int: ...
    def read(self, n: int) -> bytes: ...
    def close(self) -> None: ...
    @property
    def is_open(self) -> bool: ...


class EpdBridge:
    """Клиент бинарного протокола над USB-Serial.

    Параметры:
        port: путь к serial-устройству (например ``/dev/cu.SLAB_USBtoUART``).
            Игнорируется, если передан готовый ``ser``.
        baudrate: скорость (по умолчанию 921600).
        timeout: чтение timeout в секундах (по умолчанию 12 — больше чем
            BUSY_TIMEOUT_MS прошивки).
        ser: уже открытый serial-объект (для тестов с mock).
    """

    def __init__(
        self,
        port: str | None = None,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        ser: _SerialLike | None = None,
    ):
        if ser is not None:
            self._ser = ser
            self._owns_serial = False
            logger.debug("EpdBridge: using injected serial (mock)")
        else:
            if port is None:
                raise ValueError("Either port or ser must be provided")
            # Импорт pyserial — отложенный, чтобы тесты с mock не требовали pyserial.
            import serial  # type: ignore[import-not-found]
            self._ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
            self._owns_serial = True
            logger.debug("EpdBridge: opened %s @ %d baud", port, baudrate)

    def close(self) -> None:
        if self._owns_serial and self._ser.is_open:
            self._ser.close()
            logger.debug("EpdBridge: serial closed")

    def __enter__(self) -> EpdBridge:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- Низкоуровневые helpers ------------------------------------------

    def _send(self, data: bytes) -> None:
        n = self._ser.write(data)
        logger.debug("send: %d bytes (%s)", n, data[:8].hex() + ("..." if len(data) > 8 else ""))

    def _recv(self, n: int) -> bytes:
        data = self._ser.read(n)
        if len(data) != n:
            raise BridgeError(STATUS_TIMEOUT_RX, f"recv: expected {n} bytes, got {len(data)}")
        logger.debug("recv: %d bytes (%s)", n, data[:8].hex() + ("..." if len(data) > 8 else ""))
        return data

    def _read_status(self) -> int:
        raw = self._recv(2)
        status = (raw[0] << 8) | raw[1]
        return status

    def _check_status(self, opcode: int) -> None:
        status = self._read_status()
        if status != STATUS_OK:
            raise BridgeError(status, f"opcode 0x{opcode:02X}")

    # ---- Опкоды ----------------------------------------------------------

    def ping(self) -> int:
        """Опкод 0x06: проверка моста. Возвращает FW_VERSION (uint16)."""
        self._send(bytes([OP_PING]))
        self._check_status(OP_PING)
        ver_raw = self._recv(2)
        version = (ver_raw[0] << 8) | ver_raw[1]
        logger.info("ping: FW v%d.%02d", version >> 8, version & 0xFF)
        return version

    def init(self) -> None:
        """Опкод 0x01: init для full update."""
        self._send(bytes([OP_INIT]))
        self._check_status(OP_INIT)

    def init_partial(self) -> None:
        """Опкод 0x09: init для partial update (без OTP temperature override)."""
        self._send(bytes([OP_INIT_PARTIAL]))
        self._check_status(OP_INIT_PARTIAL)

    def init_partial_fast(self) -> None:
        """Опкод 0x0A: Waveshare-овский fast init (подмена T → +6.25°C через 0x1A)."""
        self._send(bytes([OP_INIT_PARTIAL_FAST]))
        self._check_status(OP_INIT_PARTIAL_FAST)

    def send_frame(self, frame: bytes) -> None:
        """Опкод 0x02: записать 4000-байт frame в RAM 0x24."""
        if len(frame) != EPD_FRAME_SIZE:
            raise ValueError(f"frame must be {EPD_FRAME_SIZE} bytes, got {len(frame)}")
        self._send(bytes([OP_FRAME]) + frame)
        self._check_status(OP_FRAME)

    def refresh(self) -> None:
        """Опкод 0x03: full refresh (0x22=0xF7 — заводская LUT по T)."""
        self._send(bytes([OP_REFRESH]))
        self._check_status(OP_REFRESH)

    def refresh_partial(self) -> None:
        """Опкод 0x08: partial refresh (0x22=0xCF)."""
        self._send(bytes([OP_REFRESH_PARTIAL]))
        self._check_status(OP_REFRESH_PARTIAL)

    def refresh_custom_lut(self) -> None:
        """Опкод 0x0B: refresh с уже записанной LUT (0x22=0xC7) — ключевой фикс."""
        self._send(bytes([OP_REFRESH_CUSTOM_LUT]))
        self._check_status(OP_REFRESH_CUSTOM_LUT)

    def write_lut(self, lut_bytes: bytes) -> None:
        """Опкод 0x05: записать 153-байт LUT в регистр 0x32 (без refresh)."""
        if len(lut_bytes) != EPD_LUT_SIZE:
            raise ValueError(f"LUT must be {EPD_LUT_SIZE} bytes, got {len(lut_bytes)}")
        self._send(bytes([OP_LUT]) + lut_bytes)
        self._check_status(OP_LUT)

    def write_lut_dynamic(self, lut_bytes: bytes) -> None:
        """Опкод 0x0C: атомарно LUT (153 байт) → 0x32 + refresh с 0xC7."""
        if len(lut_bytes) != EPD_LUT_SIZE:
            raise ValueError(f"LUT must be {EPD_LUT_SIZE} bytes, got {len(lut_bytes)}")
        self._send(bytes([OP_WRITE_LUT_DYNAMIC]) + lut_bytes)
        self._check_status(OP_WRITE_LUT_DYNAMIC)

    def write_register(self, addr: int, data: bytes) -> None:
        """Опкод 0x0D: записать произвольный регистр SSD1680 (0..16 байт data)."""
        if not (0 <= addr <= 0xFF):
            raise ValueError(f"addr out of range: 0x{addr:X}")
        if len(data) > 16:
            raise ValueError(f"data must be ≤16 bytes, got {len(data)}")
        payload = bytes([OP_WRITE_REGISTER, addr, len(data)]) + data
        self._send(payload)
        self._check_status(OP_WRITE_REGISTER)

    def bench_run(
        self,
        lut_bytes: bytes,
        image: bytes,
        n_repeats: int = 1,
    ) -> Trace:
        """Опкод 0x0E: цикл N повторов с INA-семплированием. Возвращает ``Trace``."""
        if len(lut_bytes) != EPD_LUT_SIZE:
            raise ValueError(f"LUT must be {EPD_LUT_SIZE} bytes")
        if len(image) != EPD_FRAME_SIZE:
            raise ValueError(f"image must be {EPD_FRAME_SIZE} bytes")
        if not (1 <= n_repeats <= 255):
            raise ValueError(f"n_repeats must be in 1..255, got {n_repeats}")

        payload = bytes([OP_BENCH_RUN]) + lut_bytes + image + bytes([n_repeats])
        self._send(payload)
        self._check_status(OP_BENCH_RUN)

        # n_samples (2 байта big-endian) + samples
        n_raw = self._recv(2)
        n_samples = (n_raw[0] << 8) | n_raw[1]
        body = self._recv(n_samples * 8)
        # parse_bench_response ожидает n_samples + payload — пересоберём
        return parse_bench_response(n_raw + body)

    def bench_factory(self, image: bytes, mode_byte: int = REFRESH_FULL_F7) -> Trace:
        """Опкод 0x0F: INA-трасса ЗАВОДСКОГО refresh (baseline B0/B1).

        В отличие от ``bench_run``, custom LUT не пишется — используется
        заводская OTP-waveform. INIT (обычный для B0 или fast для B1) должен
        быть выполнен ДО вызова: для B0 — ``init()`` + ``mode_byte=0xF7``;
        для B1 — ``init_partial_fast()`` + ``mode_byte=0xC7``.
        """
        if len(image) != EPD_FRAME_SIZE:
            raise ValueError(f"image must be {EPD_FRAME_SIZE} bytes")
        if mode_byte not in (REFRESH_FULL_F7, REFRESH_FAST_C7):
            raise ValueError(f"mode_byte must be 0xF7 or 0xC7, got {mode_byte:#x}")

        payload = bytes([OP_BENCH_FACTORY]) + image + bytes([mode_byte])
        self._send(payload)
        self._check_status(OP_BENCH_FACTORY)

        n_raw = self._recv(2)
        n_samples = (n_raw[0] << 8) | n_raw[1]
        body = self._recv(n_samples * 8)
        return parse_bench_response(n_raw + body)

    def ina_read(self) -> dict[str, float]:
        """Опкод 0x07: одно мгновенное чтение INA219.

        Возвращает {shunt_v, bus_v, current_a, power_w}.
        """
        self._send(bytes([OP_INA_READ]))
        self._check_status(OP_INA_READ)
        raw = self._recv(8)
        return parse_ina_read_response(raw)

    def sleep(self) -> None:
        """Опкод 0x04: deep sleep панели (минимальный ток)."""
        self._send(bytes([OP_SLEEP]))
        self._check_status(OP_SLEEP)


@contextmanager
def open_bridge(
    port: str,
    baudrate: int = DEFAULT_BAUDRATE,
    settle_time_s: float = 2.0,
) -> Iterator[EpdBridge]:
    """Контекст-менеджер: открыть мост, подождать settle, проверить ping, закрыть."""
    bridge = EpdBridge(port=port, baudrate=baudrate)
    try:
        # ESP32 после открытия USB-Serial делает auto-reset → надо подождать.
        logger.info("Waiting %.1f s для ESP32 settle после reset...", settle_time_s)
        time.sleep(settle_time_s)
        version = bridge.ping()
        logger.info("Bridge ready, FW v%d.%02d", version >> 8, version & 0xFF)
        yield bridge
    finally:
        bridge.close()


# ---- CLI sanity check (опционально, при `python -m python.bridge <port>`) -

def _main() -> None:
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if len(sys.argv) != 2:
        print("Usage: python -m python.bridge /dev/cu.SLAB_USBtoUART")
        sys.exit(1)

    with open_bridge(sys.argv[1]) as br:
        readout = br.ina_read()
        print(f"INA219: {readout['bus_v']:.3f} V, {readout['current_a']*1000:.2f} mA, "
              f"{readout['power_w']*1000:.2f} mW")


if __name__ == "__main__":
    _main()
