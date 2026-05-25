"""INA219 трасс-парсер и расчёт энергии.

Прошивка ESP32 (опкод 0x0E ``BENCH_RUN``) возвращает поток samples в формате
``{t_us:u32, i_raw:i16, p_raw:u16}`` = 8 байт каждый, big-endian.

Этот модуль:
- парсит сырой байтовый поток в numpy arrays;
- конвертирует raw → SI (mA, mW) по калибровке INA219 (Current_LSB=100мкА,
  Power_LSB=2мВт — настроено в firmware ``ina219_init()``);
- интегрирует мощность по времени методом трапеций → энергия за обновление [мДж].
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

# Согласовано с firmware (constexpr INA219_I_LSB_A, INA219_P_LSB_W).
CURRENT_LSB_A = 0.0001   # 100 мкА
POWER_LSB_W   = 0.002    # 2 мВт
BUS_LSB_V     = 0.004    # 4 мВ (bus voltage, raw сдвинут на 3 бита)
SHUNT_LSB_V   = 1e-5     # 10 мкВ (signed)

SAMPLE_SIZE = 8


@dataclass
class Trace:
    """Распарсенная трасса измерений во время одного refresh-цикла."""

    t_us:    np.ndarray  # время в мкс относительно старта BENCH_RUN
    i_a:     np.ndarray  # ток в амперах
    p_w:     np.ndarray  # мощность в ваттах

    def __len__(self) -> int:
        return len(self.t_us)

    @property
    def duration_ms(self) -> float:
        if len(self) == 0:
            return 0.0
        return float(self.t_us[-1] - self.t_us[0]) / 1000.0

    def energy_j(self) -> float:
        """Энергия в джоулях через метод трапеций ∫ P dt."""
        if len(self) < 2:
            return 0.0
        t_s = self.t_us * 1e-6
        return float(np.trapezoid(self.p_w, t_s))

    def energy_mj(self) -> float:
        return self.energy_j() * 1e3

    def peak_current_ma(self) -> float:
        return float(np.max(self.i_a) * 1e3) if len(self) else 0.0

    def avg_current_ma(self) -> float:
        return float(np.mean(self.i_a) * 1e3) if len(self) else 0.0

    def __repr__(self) -> str:
        return (
            f"Trace(samples={len(self)}, duration={self.duration_ms:.1f} ms, "
            f"E={self.energy_mj():.3f} mJ, I_peak={self.peak_current_ma():.2f} mA)"
        )


def parse_bench_response(raw: bytes) -> Trace:
    """Распарсить ответ опкода 0x0E ``BENCH_RUN`` (без первых 2 байт status).

    Ожидаемый формат:
        [n_samples:u16_be][sample₀:8B][sample₁:8B]...
    где:
    - ``n_samples`` — **big-endian** (firmware пишет явными shift'ами);
    - sample = ``{t_us:u32_le, i_raw:i16_le, p_raw:u16_le}`` —
      **little-endian** (firmware делает raw memcpy через
      ``Serial.write((uint8_t*)bench_buf, ...)``, что копирует
      packed struct в native порядке ESP32 = little-endian).

    Параметр ``raw`` — байты НАЧИНАЯ С n_samples (status уже отрезан caller'ом).
    """
    if len(raw) < 2:
        raise ValueError(f"raw too short ({len(raw)} bytes) — expected ≥2 для n_samples")
    n_samples = struct.unpack(">H", raw[:2])[0]
    expected = 2 + n_samples * SAMPLE_SIZE
    if len(raw) < expected:
        raise ValueError(
            f"raw truncated: got {len(raw)} bytes, expected {expected} "
            f"для n_samples={n_samples}"
        )

    payload = raw[2 : 2 + n_samples * SAMPLE_SIZE]
    # Один блочный unpack — быстрее чем циклом. Little-endian — см. docstring.
    fmt = "<" + "IhH" * n_samples
    flat = struct.unpack(fmt, payload)

    t_us  = np.array(flat[0::3], dtype=np.uint32)
    i_raw = np.array(flat[1::3], dtype=np.int16)
    p_raw = np.array(flat[2::3], dtype=np.uint16)

    i_a = i_raw.astype(np.float64) * CURRENT_LSB_A
    p_w = p_raw.astype(np.float64) * POWER_LSB_W

    logger.debug(
        "parse_bench_response: %d samples, duration ~%.1f ms",
        n_samples, (t_us[-1] - t_us[0]) / 1000.0 if n_samples > 1 else 0.0,
    )
    return Trace(t_us=t_us, i_a=i_a, p_w=p_w)


def parse_ina_read_response(raw: bytes) -> dict[str, float]:
    """Распарсить ответ опкода 0x07 ``INA_READ`` (без первых 2 байт status).

    Формат: shunt(2) + bus(2) + current(2) + power(2), big-endian.

    Bus voltage: верхние 13 бит / 8 → V; младшие биты содержат флаги.
    """
    if len(raw) != 8:
        raise ValueError(f"INA_READ response must be 8 bytes, got {len(raw)}")
    shunt_raw, bus_raw, current_raw, power_raw = struct.unpack(">hHhH", raw)

    bus_v_word = (bus_raw >> 3) * BUS_LSB_V  # bits 15..3 = bus voltage

    result = {
        "shunt_v":   shunt_raw * SHUNT_LSB_V,
        "bus_v":     bus_v_word,
        "current_a": current_raw * CURRENT_LSB_A,
        "power_w":   power_raw * POWER_LSB_W,
    }
    logger.debug("parse_ina_read: %s", {k: f"{v:.6f}" for k, v in result.items()})
    return result
