"""Тесты для python/ina219.py — parser BENCH_RUN + parser INA_READ + энергия."""

import struct

import numpy as np
import pytest

from python.ina219 import (
    CURRENT_LSB_A,
    POWER_LSB_W,
    SAMPLE_SIZE,
    Trace,
    parse_bench_response,
    parse_ina_read_response,
)


def _make_bench_payload(samples: list[tuple[int, int, int]]) -> bytes:
    """Собрать BENCH_RUN payload (без status): n_samples big-endian + samples little-endian.

    Соответствует тому, как firmware реально пишет:
    - n_samples — через явные shift'ы (big-endian);
    - sample bytes — через raw memcpy из packed struct (little-endian, native ESP32).
    """
    n = len(samples)
    payload = struct.pack(">H", n)
    for t_us, i_raw, p_raw in samples:
        payload += struct.pack("<IhH", t_us, i_raw, p_raw)
    return payload


def test_parse_bench_empty():
    raw = struct.pack(">H", 0)
    trace = parse_bench_response(raw)
    assert len(trace) == 0
    assert trace.duration_ms == 0.0
    assert trace.energy_j() == 0.0


def test_parse_bench_single_sample():
    raw = _make_bench_payload([(1000, 500, 25)])  # 50 мА, 50 мВт
    trace = parse_bench_response(raw)
    assert len(trace) == 1
    assert trace.t_us[0] == 1000
    assert trace.i_a[0] == pytest.approx(500 * CURRENT_LSB_A)
    assert trace.p_w[0] == pytest.approx(25 * POWER_LSB_W)


def test_parse_bench_truncated_raises():
    raw = struct.pack(">H", 5) + b"\x00\x00\x00"  # only 3 bytes after n_samples instead of 5×8=40
    with pytest.raises(ValueError, match="truncated"):
        parse_bench_response(raw)


def test_parse_bench_too_short_raises():
    raw = b"\x00"  # < 2 bytes
    with pytest.raises(ValueError, match="too short"):
        parse_bench_response(raw)


def test_energy_trapezoidal_constant_power():
    """Постоянная мощность 100 мВт × 100 мс = 10 мДж."""
    # 10 семплов, каждые 10000 мкс (10 мс), power_raw=50 → 100 мВт
    samples = [(i * 10000, 1000, 50) for i in range(11)]
    raw = _make_bench_payload(samples)
    trace = parse_bench_response(raw)

    # Интегрирование: 100 мс × 0.1 Вт = 0.01 Дж = 10 мДж
    energy_mj = trace.energy_mj()
    assert energy_mj == pytest.approx(10.0, rel=1e-3)


def test_energy_trapezoidal_linear_ramp():
    """Линейный рост мощности от 0 до 100 мВт за 100 мс → 5 мДж (треугольник)."""
    # power_raw от 0 до 50 (= 0..100 мВт)
    samples = [(i * 10000, 0, int(50 * i / 10)) for i in range(11)]
    raw = _make_bench_payload(samples)
    trace = parse_bench_response(raw)
    # Площадь треугольника = (1/2) × 0.1 с × 0.1 Вт = 0.005 Дж = 5 мДж
    assert trace.energy_mj() == pytest.approx(5.0, rel=1e-3)


def test_peak_and_avg_current():
    samples = [(0, 100, 0), (1000, 500, 0), (2000, 200, 0)]
    raw = _make_bench_payload(samples)
    trace = parse_bench_response(raw)
    assert trace.peak_current_ma() == pytest.approx(500 * CURRENT_LSB_A * 1000)
    assert trace.avg_current_ma() == pytest.approx((100 + 500 + 200) / 3 * CURRENT_LSB_A * 1000)


def test_sample_size_invariant():
    """Pythonный struct unpack даёт ровно 8 байт на sample без padding."""
    assert struct.calcsize(">IhH") == SAMPLE_SIZE == 8


def test_parse_ina_read_zero():
    raw = bytes(8)
    r = parse_ina_read_response(raw)
    assert r["shunt_v"] == 0.0
    assert r["bus_v"] == 0.0
    assert r["current_a"] == 0.0
    assert r["power_w"] == 0.0


def test_parse_ina_read_known_values():
    # shunt = 100 (10мкВ × 100 = 1мВ), bus_raw = (3300 << 3) = 26400 (= 3.3В × 1000/4 << 3 = 3.3В),
    # current = 500 (50мА), power = 25 (50мВт)
    bus_raw = (3300 // 4) << 3  # 3.3В / 4мВ = 825, << 3 = 6600
    raw = struct.pack(">hHhH", 100, bus_raw, 500, 25)
    r = parse_ina_read_response(raw)
    assert r["shunt_v"]   == pytest.approx(0.001)
    assert r["bus_v"]     == pytest.approx(3.3)
    assert r["current_a"] == pytest.approx(0.050)
    assert r["power_w"]   == pytest.approx(0.050)


def test_parse_ina_read_bad_length():
    with pytest.raises(ValueError, match="8 bytes"):
        parse_ina_read_response(b"\x00" * 7)


def test_trace_repr_smoke():
    samples = [(0, 100, 50), (10000, 100, 50)]
    raw = _make_bench_payload(samples)
    trace = parse_bench_response(raw)
    rep = repr(trace)
    assert "Trace(" in rep
    assert "samples=2" in rep
