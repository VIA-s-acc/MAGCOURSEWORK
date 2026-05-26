"""Алгоритм построения Парето-границы через ε-constraint метод.

Реализует внешний цикл из § 5.2 курсовой:

    FOR (ε_G, ε_τ) IN grid:
        result = solve_pmp_slice(z_init, z_target, ε_G, ε_τ, surrogate)
        if result is not None:
            collect

    filter_dominated(collected)

Также предоставляет метрики сравнения с NSGA-II (§ 5.5):
- hypervolume (HV) в (E, G, τ)-пространстве;
- inverted generational distance (IGD).

Используется в:
- notebooks/03_pareto.ipynb (полный фронт по 10 сценариям + сравнение с NSGA-II)
- gl. 6 курсовой (§ 6.4 «Парето-фронт симулированный»)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from python.optimizer import (
    DEFAULT_CHARGE_EPS,
    DEFAULT_DURATIONS,
    DEFAULT_F_FRAME,
    DEFAULT_K_EFF_MAX,
    DEFAULT_VOLTAGES,
    WaveformModel,
    WaveformResult,
    solve_pmp_slice,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParetoPoint:
    """Одна точка Парето-фронта."""

    energy: float    # E [мДж]
    ghost: float     # G [рефл. единицы]
    latency: float   # τ [с]
    waveform_result: WaveformResult | None = None  # None — если из baseline

    @property
    def vector(self) -> np.ndarray:
        return np.array([self.energy, self.ghost, self.latency])


def build_pareto_frontier(
    z_init: float,
    z_target: float,
    eps_G_grid: tuple[float, ...],
    eps_tau_grid: tuple[float, ...],
    model: WaveformModel,
    voltages: tuple[float, ...] = DEFAULT_VOLTAGES,
    durations: tuple[int, ...] = DEFAULT_DURATIONS,
    k_eff_max: int = DEFAULT_K_EFF_MAX,
    charge_eps: float = DEFAULT_CHARGE_EPS,
    f_frame: float = DEFAULT_F_FRAME,
) -> list[ParetoPoint]:
    """Построить Парето-фронт для одной задачи перехода (z_init → z_target).

    Перебор по 2D сетке (ε_G, ε_τ) → для каждого узла — solve_pmp_slice →
    собираем все непустые результаты → фильтрация недоминируемых.
    """
    logger.info(
        "build_pareto_frontier: z_init=%.3f, z_target=%.3f, grid %d×%d",
        z_init, z_target, len(eps_G_grid), len(eps_tau_grid),
    )

    candidates: list[ParetoPoint] = []
    for eps_G in eps_G_grid:
        for eps_tau in eps_tau_grid:
            res = solve_pmp_slice(
                z_init=z_init, z_target=z_target,
                eps_G=eps_G, eps_tau=eps_tau,
                model=model,
                voltages=voltages, durations=durations,
                k_eff_max=k_eff_max, charge_eps=charge_eps, f_frame=f_frame,
            )
            if res is not None:
                candidates.append(ParetoPoint(
                    energy=res.energy, ghost=res.ghost, latency=res.latency,
                    waveform_result=res,
                ))

    frontier = filter_dominated(candidates)
    logger.info("frontier: %d candidates → %d non-dominated", len(candidates), len(frontier))
    return frontier


def filter_dominated(points: list[ParetoPoint]) -> list[ParetoPoint]:
    """Оставить только недоминируемые точки (Парето-фронт).

    p1 доминирует p2 ⟺ p1 ≤ p2 покомпонентно и p1 ≠ p2.
    """
    if not points:
        return []
    pts = np.array([p.vector for p in points])
    n = len(pts)
    is_dom = np.zeros(n, dtype=bool)
    for i in range(n):
        for j in range(n):
            if i == j or is_dom[j]:
                continue
            if np.all(pts[j] <= pts[i]) and np.any(pts[j] < pts[i]):
                is_dom[i] = True
                break
    return [points[i] for i in range(n) if not is_dom[i]]


# ---- Метрики сравнения фронтов ------------------------------------------


def hypervolume(points: list[ParetoPoint], reference: tuple[float, float, float]) -> float:
    """3D hypervolume — объём области, доминируемой фронтом до reference point.

    Простая реализация через Monte-Carlo выборку (быстра и корректна для
    небольших фронтов — до ~50 точек, что наш случай). Для thesis-точности
    можно заменить на точный WFG (Auger 2009), но MC даёт стабильную оценку
    с погрешностью ~1% при n_samples=50000.
    """
    if not points:
        return 0.0
    pts = np.array([p.vector for p in points])
    ref = np.asarray(reference, dtype=float)
    if (pts > ref).any():
        # Точки выше reference не дают вклад; обрезаем.
        pts = np.minimum(pts, ref)
    # MC: 50000 точек в коробке [0, ref]; считаем долю доминируемых.
    rng = np.random.default_rng(seed=42)
    n_samples = 50000
    samples = rng.uniform(low=0.0, high=ref, size=(n_samples, 3))
    # точка sample доминируется фронтом, если ∃ p ∈ frontier: p ≤ sample
    dominated = np.zeros(n_samples, dtype=bool)
    for p in pts:
        dominated |= np.all(p <= samples, axis=1)
    box_volume = float(np.prod(ref))
    hv = box_volume * dominated.mean()
    logger.debug("hypervolume: %d points, ref=%s, HV=%.4f", len(points), tuple(ref), hv)
    return hv


def igd(approx: list[ParetoPoint], reference_front: list[ParetoPoint]) -> float:
    """Inverted Generational Distance.

    IGD = (1/|R|) · Σ_{r ∈ R} min_{a ∈ A} ||r − a||_2,
    где R — reference (combined ours ∪ NSGA-II), A — оцениваемый фронт.
    Меньше — лучше (фронт A ближе к R).
    """
    if not approx or not reference_front:
        return float("inf")
    A = np.array([p.vector for p in approx])
    R = np.array([p.vector for p in reference_front])
    # для каждой r ∈ R — минимум по a ∈ A.
    dists = np.array([np.min(np.linalg.norm(A - r, axis=1)) for r in R])
    return float(dists.mean())
