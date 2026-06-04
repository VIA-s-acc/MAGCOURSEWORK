"""Тесты для python/bench_protocol.py (с mock-мостом, без железа)."""

from __future__ import annotations

import numpy as np
import pytest

import numpy as np

from python.bench_protocol import BASELINES, BenchResult, run_baseline
from python.frames import scn_checker
from python.ina219 import Trace
from python.lut import LUT_BYTES


def _fake_trace(energy_scale: float = 1.0) -> Trace:
    """Синтетическая трасса: 100 сэмплов, ~постоянный ток ~1 мА, ~3 мВт."""
    t_us = np.arange(100) * 1000.0  # 0..99 мс
    i_a = np.full(100, 1e-3 * energy_scale)
    p_w = np.full(100, 3e-3 * energy_scale)
    return Trace(t_us=t_us, i_a=i_a, p_w=p_w)


class MockBridge:
    """Минимальный мок EpdBridge: пишет лог вызовов, возвращает фейк-трассу."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def init(self) -> None:
        self.calls.append("init")

    def init_partial_fast(self) -> None:
        self.calls.append("init_partial_fast")

    def write_register(self, addr: int, data: bytes) -> None:
        self.calls.append(f"write_register({addr:#x})")

    def bench_factory(self, image: bytes, mode_byte: int) -> Trace:
        self.calls.append(f"bench_factory(mode={mode_byte:#x})")
        return _fake_trace()

    def bench_run(self, lut: bytes, image: bytes, n_repeats: int = 1) -> Trace:
        self.calls.append(f"bench_run(n={n_repeats})")
        return _fake_trace()


@pytest.fixture
def img() -> np.ndarray:
    return scn_checker()


def test_b0_uses_factory_full(img):
    br = MockBridge()
    res = run_baseline(br, "04_checker", img, "B0")
    assert br.calls == ["init", "bench_factory(mode=0xf7)"]
    assert isinstance(res, BenchResult)
    assert res.baseline == "B0" and res.scenario == "04_checker"
    assert res.energy_mj > 0 and res.latency_s > 0 and res.n_samples == 100


def test_b1_uses_fast_init_and_c7(img):
    br = MockBridge()
    run_baseline(br, "s", img, "B1")
    assert br.calls == ["init_partial_fast", "bench_factory(mode=0xc7)"]


def test_b2_requires_lut(img):
    br = MockBridge()
    with pytest.raises(ValueError, match="требует custom_lut"):
        run_baseline(br, "s", img, "B2")


def test_b2_runs_bench_run_with_lut(img):
    br = MockBridge()
    run_baseline(br, "s", img, "B2", custom_lut=bytes(LUT_BYTES))
    assert br.calls == ["init", "bench_run(n=1)"]


def test_b4_writes_temp_register(img):
    br = MockBridge()
    run_baseline(br, "s", img, "B4", custom_lut=bytes(LUT_BYTES), temp_override=0x0064)
    assert "write_register(0x1a)" in br.calls
    assert br.calls[-1] == "bench_run(n=1)"


def test_unknown_baseline_raises(img):
    br = MockBridge()
    with pytest.raises(ValueError, match="unknown baseline"):
        run_baseline(br, "s", img, "B9")


def test_all_baselines_named():
    assert BASELINES == ("B0", "B1", "B2", "B3", "B4")
