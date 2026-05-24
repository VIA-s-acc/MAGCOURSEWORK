"""Тесты для python/bridge.py — opcode formation через mock serial."""

from __future__ import annotations

import io
import struct

import pytest

from python.bridge import (
    EPD_FRAME_SIZE,
    EPD_LUT_SIZE,
    OP_BENCH_RUN,
    OP_INA_READ,
    OP_INIT,
    OP_INIT_PARTIAL,
    OP_INIT_PARTIAL_FAST,
    OP_LUT,
    OP_PING,
    OP_REFRESH,
    OP_REFRESH_CUSTOM_LUT,
    OP_REFRESH_PARTIAL,
    OP_SLEEP,
    OP_WRITE_LUT_DYNAMIC,
    OP_WRITE_REGISTER,
    STATUS_BAD_OPCODE,
    STATUS_OK,
    BridgeError,
    EpdBridge,
)


class MockSerial:
    """Минимальный serial-like для тестов: 2 буфера (TX наблюдаемый, RX scripted)."""

    def __init__(self, rx_data: bytes = b""):
        self.tx = bytearray()        # что bridge нам послал
        self.rx_buffer = bytearray(rx_data)
        self._open = True

    def write(self, data: bytes) -> int:
        self.tx.extend(data)
        return len(data)

    def read(self, n: int) -> bytes:
        chunk = bytes(self.rx_buffer[:n])
        del self.rx_buffer[:n]
        return chunk

    def close(self) -> None:
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open


def _status_ok_bytes() -> bytes:
    return struct.pack(">H", STATUS_OK)


def _make_bridge(rx_data: bytes) -> tuple[EpdBridge, MockSerial]:
    mock = MockSerial(rx_data)
    bridge = EpdBridge(ser=mock)
    return bridge, mock


# ---- Конструкторы / контекст ---------------------------------------------

def test_constructor_requires_port_or_ser():
    with pytest.raises(ValueError, match="port or ser"):
        EpdBridge()


def test_close_does_not_close_injected_serial():
    mock = MockSerial(b"")
    bridge = EpdBridge(ser=mock)
    bridge.close()
    # mock — внешний, bridge не должен его закрывать
    assert mock.is_open


def test_context_manager():
    bridge, _ = _make_bridge(b"")
    with bridge as br:
        assert br is bridge


# ---- Status handling ------------------------------------------------------

def test_status_ok_passes_through():
    bridge, _ = _make_bridge(_status_ok_bytes())
    bridge.init()  # не должно бросить


def test_status_error_raises_bridge_error():
    rx = struct.pack(">H", STATUS_BAD_OPCODE)
    bridge, _ = _make_bridge(rx)
    with pytest.raises(BridgeError) as exc_info:
        bridge.init()
    assert exc_info.value.status == STATUS_BAD_OPCODE
    assert "BAD_OPCODE" in str(exc_info.value)


def test_truncated_status_raises():
    bridge, _ = _make_bridge(b"\x00")  # 1 байт вместо 2
    with pytest.raises(BridgeError) as exc:
        bridge.init()
    assert "TIMEOUT_RX" in str(exc.value)


# ---- Простые опкоды (один байт TX, status RX) -----------------------------

@pytest.mark.parametrize("method,opcode", [
    ("init",                 OP_INIT),
    ("init_partial",         OP_INIT_PARTIAL),
    ("init_partial_fast",    OP_INIT_PARTIAL_FAST),
    ("refresh",              OP_REFRESH),
    ("refresh_partial",      OP_REFRESH_PARTIAL),
    ("refresh_custom_lut",   OP_REFRESH_CUSTOM_LUT),
    ("sleep",                OP_SLEEP),
])
def test_simple_opcodes_send_single_byte(method, opcode):
    bridge, mock = _make_bridge(_status_ok_bytes())
    getattr(bridge, method)()
    assert bytes(mock.tx) == bytes([opcode])


# ---- PING ----------------------------------------------------------------

def test_ping_returns_version():
    rx = _status_ok_bytes() + struct.pack(">H", 0x0102)
    bridge, mock = _make_bridge(rx)
    version = bridge.ping()
    assert version == 0x0102
    assert bytes(mock.tx) == bytes([OP_PING])


# ---- FRAME / LUT (с payload) ---------------------------------------------

def test_send_frame_sends_opcode_plus_4000_bytes():
    bridge, mock = _make_bridge(_status_ok_bytes())
    payload = b"\xAA" * EPD_FRAME_SIZE
    bridge.send_frame(payload)
    assert len(mock.tx) == 1 + EPD_FRAME_SIZE
    assert mock.tx[0] == 0x02
    assert bytes(mock.tx[1:]) == payload


def test_send_frame_bad_length_raises():
    bridge, _ = _make_bridge(b"")
    with pytest.raises(ValueError, match="4000 bytes"):
        bridge.send_frame(b"\x00" * 100)


def test_write_lut_sends_153_bytes():
    bridge, mock = _make_bridge(_status_ok_bytes())
    payload = b"\xBB" * EPD_LUT_SIZE
    bridge.write_lut(payload)
    assert len(mock.tx) == 1 + EPD_LUT_SIZE
    assert mock.tx[0] == OP_LUT


def test_write_lut_dynamic_sends_153_bytes_with_correct_opcode():
    bridge, mock = _make_bridge(_status_ok_bytes())
    payload = b"\xCC" * EPD_LUT_SIZE
    bridge.write_lut_dynamic(payload)
    assert mock.tx[0] == OP_WRITE_LUT_DYNAMIC
    assert bytes(mock.tx[1:]) == payload


def test_write_lut_bad_length_raises():
    bridge, _ = _make_bridge(b"")
    with pytest.raises(ValueError, match="153 bytes"):
        bridge.write_lut(b"\x00" * 152)


# ---- WRITE_REGISTER -------------------------------------------------------

def test_write_register_basic():
    bridge, mock = _make_bridge(_status_ok_bytes())
    bridge.write_register(0x1A, bytes([0x64, 0x00]))
    # [OP, addr, len, data...]
    assert bytes(mock.tx) == bytes([OP_WRITE_REGISTER, 0x1A, 2, 0x64, 0x00])


def test_write_register_zero_data_ok():
    bridge, mock = _make_bridge(_status_ok_bytes())
    bridge.write_register(0x12, b"")  # SWRESET — без данных
    assert bytes(mock.tx) == bytes([OP_WRITE_REGISTER, 0x12, 0])


def test_write_register_bad_addr():
    bridge, _ = _make_bridge(b"")
    with pytest.raises(ValueError, match="addr"):
        bridge.write_register(0x100, b"")


def test_write_register_data_too_long():
    bridge, _ = _make_bridge(b"")
    with pytest.raises(ValueError, match="≤16"):
        bridge.write_register(0x32, b"\x00" * 17)


# ---- INA_READ ------------------------------------------------------------

def test_ina_read_parses_response():
    bus_raw = (3300 // 4) << 3
    rx = _status_ok_bytes() + struct.pack(">hHhH", 100, bus_raw, 500, 25)
    bridge, mock = _make_bridge(rx)
    r = bridge.ina_read()
    assert mock.tx == bytes([OP_INA_READ])
    assert r["bus_v"] == pytest.approx(3.3)
    assert r["current_a"] == pytest.approx(0.050)


# ---- BENCH_RUN ----------------------------------------------------------

def test_bench_run_sends_correct_payload_and_parses_response():
    lut = b"\x11" * EPD_LUT_SIZE
    image = b"\x22" * EPD_FRAME_SIZE
    n_repeats = 3

    # ответ: status + n_samples=2 + 2×8 байт samples
    samples_raw = struct.pack(">IhH", 1000, 50, 10) + struct.pack(">IhH", 2000, 60, 12)
    rx = _status_ok_bytes() + struct.pack(">H", 2) + samples_raw

    bridge, mock = _make_bridge(rx)
    trace = bridge.bench_run(lut, image, n_repeats)

    # Проверка TX: [OP][LUT 153][image 4000][N 1]
    expected_tx_len = 1 + EPD_LUT_SIZE + EPD_FRAME_SIZE + 1
    assert len(mock.tx) == expected_tx_len
    assert mock.tx[0] == OP_BENCH_RUN
    assert bytes(mock.tx[1 : 1 + EPD_LUT_SIZE]) == lut
    assert bytes(mock.tx[1 + EPD_LUT_SIZE : 1 + EPD_LUT_SIZE + EPD_FRAME_SIZE]) == image
    assert mock.tx[-1] == n_repeats

    # Проверка trace
    assert len(trace) == 2
    assert trace.t_us[0] == 1000
    assert trace.t_us[1] == 2000


def test_bench_run_bad_n_repeats():
    bridge, _ = _make_bridge(b"")
    with pytest.raises(ValueError, match="1..255"):
        bridge.bench_run(b"\x00" * EPD_LUT_SIZE, b"\x00" * EPD_FRAME_SIZE, 0)
    with pytest.raises(ValueError, match="1..255"):
        bridge.bench_run(b"\x00" * EPD_LUT_SIZE, b"\x00" * EPD_FRAME_SIZE, 256)
