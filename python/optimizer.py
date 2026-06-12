"""Оптимизатор waveform по дискретному PMP из теоремы 4.1.

Реализует solve_pmp_slice — решение задачи:

    min_u  E(u)
    s.t.   G(u; z_init, z_target) ≤ ε_G
           τ(u) ≤ ε_τ
           |Σ_k V[k] · T[k]| ≤ ε      (ε-зарядовый баланс, § 4.3)
           K_eff(u) ≤ K_eff_max       (структура bang-bang, теорема 4.1)
           V[k] ∈ U_disc, T[k] ∈ T_disc

Структура bang-bang из теоремы 4.1 (Paruchuri-Chatterjee 2019, дискретный PMP)
позволяет перебирать лишь конечное множество кандидатов: |U_disc|^K_eff
последовательностей напряжений × |T_disc|^K_eff длительностей.

Используется в:
- python/pareto.py (build_pareto_frontier — внешний ε-constraint цикл)
- notebooks/02_optimize.ipynb (одиночная задача)
- gl. 5 курсовой (§ 5.2 «Метод ε-ограничений»)
"""

from __future__ import annotations

import itertools
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

# Дефолтные источники напряжения SSD1680 (см. python/lut.py Source enum и § 3.5.5
# курсовой — VSH1, VSH2 калибруются по реальному стенду; здесь — типовые номиналы).
DEFAULT_VOLTAGES: tuple[float, ...] = (+15.0, +5.0, -15.0, 0.0)  # VSH1, VSH2, VSL, VCOM
DEFAULT_DURATIONS: tuple[int, ...] = tuple(range(1, 17))  # 1..16 кадров (≈ 20..320 мс @ 50 Гц)
DEFAULT_K_EFF_MAX: int = 4  # d_state + 2 по теореме 4.1
DEFAULT_CHARGE_EPS: float = 0.05  # В·с (§ 4.3)
DEFAULT_F_FRAME: float = 50.0  # Гц — частота кадров SSD1680


@dataclass(frozen=True)
class Waveform:
    """Bang-bang waveform: последовательность активных фаз (V, T).

    Атрибуты:
        voltages: напряжения каждой фазы [В]. Длина = K_eff.
        durations: длительности каждой фазы в кадрах. Длина = K_eff.
        f_frame: частота кадров [Гц] для пересчёта в секунды.
    """

    voltages: tuple[float, ...]
    durations: tuple[int, ...]
    f_frame: float = DEFAULT_F_FRAME

    def __post_init__(self) -> None:
        if len(self.voltages) != len(self.durations):
            raise ValueError(
                f"len(voltages)={len(self.voltages)} != len(durations)={len(self.durations)}"
            )
        if self.f_frame <= 0:
            raise ValueError(f"f_frame must be positive, got {self.f_frame}")

    @property
    def k_eff(self) -> int:
        """Число активных фаз (V ≠ 0)."""
        return sum(1 for v in self.voltages if v != 0.0)

    @property
    def charge_integral(self) -> float:
        """Σ_k V[k] · T[k] / f_frame [В·с] — интеграл напряжения по времени."""
        return sum(v * t / self.f_frame for v, t in zip(self.voltages, self.durations))

    @property
    def total_time(self) -> float:
        """Полная длительность [с] = Σ_k T[k] / f_frame."""
        return sum(self.durations) / self.f_frame


@dataclass(frozen=True)
class WaveformResult:
    """Результат оптимизации одной ε-точки.

    Атрибуты:
        waveform: найденный оптимальный waveform.
        energy: E(waveform) [мДж].
        ghost: G(waveform; z_init, z_target) [рефл. единицы, ||·||_1].
        latency: τ(waveform) [с].
    """

    waveform: Waveform
    energy: float
    ghost: float
    latency: float


class WaveformModel(Protocol):
    """Контракт surrogate-модели (см. python/surrogate.py)."""

    def predict(self, waveform: Waveform, z_init: float, z_target: float) -> tuple[float, float, float]:
        """Вернуть (E [мДж], G [||·||_1], τ [с]) для данного waveform."""
        ...


def _iter_bang_bang_candidates(
    voltages: tuple[float, ...],
    durations: tuple[int, ...],
    k_eff_max: int,
    f_frame: float,
) -> "Iterator[Waveform]":
    """Генератор всех bang-bang waveforms длины 1..k_eff_max.

    Принципиально: не повторяем подряд одинаковое напряжение (это эквивалентно
    одной фазе с суммарным T) — снижает кратность счёта.
    """
    for k in range(1, k_eff_max + 1):
        for v_seq in itertools.product(voltages, repeat=k):
            # Skip "constant V over all phases" duplicate enumerations
            if k >= 2 and any(v_seq[i] == v_seq[i + 1] for i in range(k - 1)):
                continue
            for t_seq in itertools.product(durations, repeat=k):
                yield Waveform(voltages=v_seq, durations=t_seq, f_frame=f_frame)


def solve_pmp_slice(
    z_init: float,
    z_target: float,
    eps_G: float,
    eps_tau: float,
    model: WaveformModel,
    voltages: tuple[float, ...] = DEFAULT_VOLTAGES,
    durations: tuple[int, ...] = DEFAULT_DURATIONS,
    k_eff_max: int = DEFAULT_K_EFF_MAX,
    charge_eps: float = DEFAULT_CHARGE_EPS,
    f_frame: float = DEFAULT_F_FRAME,
) -> WaveformResult | None:
    """Решить одну ε-задачу из теоремы 4.1: min E s.t. G≤ε_G, τ≤ε_τ + жёсткие.

    Перебор bang-bang кандидатов с ранним отсечением по заряду (|Σ V·T|>ε) и
    латентности (τ>ε_τ) до вызова model.predict(); возвращает None, если ни один
    кандидат не прошёл ограничения.
    """
    best: WaveformResult | None = None
    for wf in _iter_bang_bang_candidates(voltages, durations, k_eff_max, f_frame):
        if abs(wf.charge_integral) > charge_eps:
            continue
        if wf.total_time > eps_tau:
            continue
        E, G, tau = model.predict(wf, z_init, z_target)
        if G > eps_G:
            continue
        if best is not None and E >= best.energy:
            continue
        best = WaveformResult(waveform=wf, energy=E, ghost=G, latency=tau)

    logger.debug(
        "solve_pmp_slice(z=%.3f→%.3f, ε_G=%.4f, ε_τ=%.3fs): %s",
        z_init, z_target, eps_G, eps_tau,
        "none" if best is None else f"E={best.energy:.4f}мДж K_eff={best.waveform.k_eff}",
    )
    return best
