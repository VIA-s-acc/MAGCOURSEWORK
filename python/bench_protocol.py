"""Протокол измерения одного baseline на стенде (гл. 7).

Определяет таксономию baseline B0..B4 (RESEARCH.md) и единый интерфейс
прогона: для заданного сценария (целевого кадра) и baseline выполняется
последовательность init→refresh с записью INA-трассы, из которой
извлекаются энергия E [мДж] и латентность τ [с]. Метрика гостинга G
измеряется отдельно по фотографии (:mod:`python.photo_pipeline`) и
присоединяется к результату на этапе постобработки.

Baseline (см. RESEARCH.md, B0..B4):
  B0  Waveshare full   — init() + заводский refresh 0xF7 (BENCH_FACTORY)
  B1  Waveshare fast   — init_partial_fast() + 0xC7 (BENCH_FACTORY)
  B2  Custom static    — init() + наш LUT + 0xC7 (BENCH_RUN)
  B3  Content-adaptive — как B2, но LUT выбирается по diff кадров (передаётся)
  B4  Temp+content     — как B3 + подмена температуры (0x1A) перед прогоном

Используется в:
- scripts/run_bench_campaign.py (полная кампания B0..B4 × сценарии × повторы)
- gl. 7 курсовой (§ 7.4 «Протокол измерения»)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from python.bridge import REFRESH_FAST_C7, REFRESH_FULL_F7, EpdBridge
from python.frames import pack_frame
from python.ina219 import Trace
from python.lut import LUT_BYTES

logger = logging.getLogger(__name__)

BASELINES = ("B0", "B1", "B2", "B3", "B4")
FACTORY_BASELINES = ("B0", "B1")
CUSTOM_BASELINES = ("B2", "B3", "B4")


@dataclass(frozen=True)
class BenchResult:
    """Результат одного прогона baseline на одном сценарии.

    Атрибуты:
        baseline: имя baseline (B0..B4).
        scenario: имя сценария (например "04_checker").
        energy_mj: энергия обновления [мДж] (интеграл U·I по трассе INA219).
        latency_s: латентность [с] (длительность активной фазы BUSY=1).
        peak_ma: пиковый ток [мА].
        n_samples: число точек INA-трассы.
    """

    baseline: str
    scenario: str
    energy_mj: float
    latency_s: float
    peak_ma: float
    n_samples: int

    @classmethod
    def from_trace(cls, baseline: str, scenario: str, tr: Trace) -> "BenchResult":
        return cls(
            baseline=baseline,
            scenario=scenario,
            energy_mj=tr.energy_mj(),
            latency_s=tr.duration_ms / 1000.0,
            peak_ma=tr.peak_current_ma(),
            n_samples=len(tr),
        )


def run_baseline(
    bridge: EpdBridge,
    scenario_name: str,
    scenario_img: np.ndarray,
    baseline: str,
    custom_lut: bytes | None = None,
    temp_override: int | None = None,
) -> BenchResult:
    """Прогнать один baseline на одном сценарии, вернуть BenchResult.

    Параметры:
        bridge: открытый EpdBridge.
        scenario_name: имя сценария (для метки результата).
        scenario_img: целевой кадр (PANEL_H, PANEL_W) [0,1].
        baseline: один из B0..B4.
        custom_lut: 153-байтная LUT для B2..B4 (обязательна для них).
        temp_override: для B4 — значение регистра 0x1A (подмена температуры).
    """
    if baseline not in BASELINES:
        raise ValueError(f"unknown baseline {baseline!r}, expected one of {BASELINES}")
    frame = pack_frame(scenario_img)

    if baseline in CUSTOM_BASELINES and (custom_lut is None or len(custom_lut) != LUT_BYTES):
        raise ValueError(f"{baseline} требует custom_lut длиной {LUT_BYTES} байт")

    logger.info("run_baseline: %s / %s", baseline, scenario_name)

    if baseline == "B0":
        bridge.init()
        tr = bridge.bench_factory(frame, mode_byte=REFRESH_FULL_F7)
    elif baseline == "B1":
        bridge.init_partial_fast()
        tr = bridge.bench_factory(frame, mode_byte=REFRESH_FAST_C7)
    else:  # B2, B3, B4 — custom LUT через BENCH_RUN (0x22=0xC7 внутри)
        bridge.init()
        if baseline == "B4" and temp_override is not None:
            # Регистр 0x1A — запись температурного значения (как Waveshare fast).
            bridge.write_register(0x1A, bytes([(temp_override >> 8) & 0xFF, temp_override & 0xFF]))
        tr = bridge.bench_run(custom_lut, frame, n_repeats=1)  # type: ignore[arg-type]

    res = BenchResult.from_trace(baseline, scenario_name, tr)
    logger.info("  -> E=%.3f мДж, τ=%.3f с, peak=%.2f мА, n=%d",
                res.energy_mj, res.latency_s, res.peak_ma, res.n_samples)
    return res
