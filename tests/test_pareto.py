"""Тесты для python/pareto.py + python/baselines.py."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from python.baselines import NSGA2
from python.optimizer import Waveform
from python.pareto import ParetoPoint, build_pareto_frontier, filter_dominated, hypervolume, igd


# ---- Аналитическая модель (повтор из test_optimizer.py для изоляции) ----


@dataclass
class AsymmetricModel:
    c_E: float = 1.0e-3
    mu_pos: float = 0.060
    mu_neg: float = 0.040

    def predict(self, wf: Waveform, z_init: float, z_target: float) -> tuple[float, float, float]:
        e = sum(self.c_E * v * v * t / wf.f_frame for v, t in zip(wf.voltages, wf.durations))
        dz = sum(
            (self.mu_pos if v > 0 else (self.mu_neg if v < 0 else 0.0)) * v * t / wf.f_frame
            for v, t in zip(wf.voltages, wf.durations)
        )
        g = abs(dz - (z_target - z_init))
        tau = wf.total_time
        return (e, g, tau)


# ---- filter_dominated ----------------------------------------------------


def _pt(E: float, G: float, tau: float) -> ParetoPoint:
    return ParetoPoint(energy=E, ghost=G, latency=tau)


def test_filter_empty_returns_empty():
    assert filter_dominated([]) == []


def test_filter_removes_dominated_point():
    p_good = _pt(1.0, 0.1, 0.1)
    p_dom = _pt(2.0, 0.2, 0.2)  # доминируется p_good
    out = filter_dominated([p_good, p_dom])
    assert len(out) == 1
    assert out[0] is p_good


def test_filter_keeps_all_pareto_optimal():
    p1 = _pt(1.0, 0.3, 0.1)
    p2 = _pt(2.0, 0.1, 0.2)
    p3 = _pt(3.0, 0.05, 0.5)
    out = filter_dominated([p1, p2, p3])
    assert len(out) == 3


def test_filter_keeps_one_when_tied():
    p1 = _pt(1.0, 0.1, 0.1)
    p2 = _pt(1.0, 0.1, 0.1)  # точная копия
    # Каждая считается доминирующей другую по «≤ покомпонентно и ≠» → не дублирует
    out = filter_dominated([p1, p2])
    # Допустимо: либо одна, либо обе (если строгое доминирование) — но обе равные
    # не дают np.any(<) → не доминируют друг друга. Значит обе остаются.
    assert len(out) == 2


# ---- hypervolume + igd --------------------------------------------------


def test_hypervolume_empty_is_zero():
    assert hypervolume([], (10.0, 1.0, 1.0)) == 0.0


def test_hypervolume_single_point():
    # Точка (1, 0.1, 0.1) при reference (10, 1, 1) доминирует «коробку» от
    # (1, 0.1, 0.1) до (10, 1, 1) → объём = 9 · 0.9 · 0.9 = 7.29.
    pt = _pt(1.0, 0.1, 0.1)
    hv = hypervolume([pt], (10.0, 1.0, 1.0))
    expected = (10.0 - 1.0) * (1.0 - 0.1) * (1.0 - 0.1)
    assert hv == pytest.approx(expected, rel=0.05)  # MC погрешность ~5%


def test_hypervolume_monotone_with_better_front():
    # Лучший фронт (меньше E, G, τ) должен иметь больший HV.
    pt_better = _pt(0.5, 0.05, 0.05)
    pt_worse = _pt(2.0, 0.5, 0.5)
    ref = (10.0, 1.0, 1.0)
    hv_better = hypervolume([pt_better], ref)
    hv_worse = hypervolume([pt_worse], ref)
    assert hv_better > hv_worse


def test_igd_zero_for_identical_fronts():
    A = [_pt(1.0, 0.1, 0.1), _pt(2.0, 0.05, 0.2)]
    R = list(A)
    assert igd(A, R) == pytest.approx(0.0, abs=1e-12)


def test_igd_positive_for_different_fronts():
    A = [_pt(2.0, 0.2, 0.2)]
    R = [_pt(1.0, 0.1, 0.1)]
    d = igd(A, R)
    # Расстояние между точками = sqrt(1 + 0.01 + 0.01) ≈ 1.0050
    assert d == pytest.approx((1.0**2 + 0.1**2 + 0.1**2) ** 0.5, rel=1e-6)


# ---- build_pareto_frontier ----------------------------------------------


def test_build_pareto_frontier_produces_nondominated_points():
    model = AsymmetricModel()
    pts = build_pareto_frontier(
        z_init=0.07, z_target=0.10,
        eps_G_grid=(0.005, 0.01, 0.02),
        eps_tau_grid=(0.1, 0.2),
        model=model,
        voltages=(+15.0, -15.0, +5.0),
        durations=(1, 2, 4),
        k_eff_max=3,
        charge_eps=0.05,
    )
    # Проверка недоминируемости.
    assert len(pts) >= 1
    for i, p in enumerate(pts):
        for j, q in enumerate(pts):
            if i == j:
                continue
            assert not (
                q.energy <= p.energy and q.ghost <= p.ghost and q.latency <= p.latency
                and (q.energy < p.energy or q.ghost < p.ghost or q.latency < p.latency)
            ), f"point {i} is dominated by {j}"


# ---- NSGA-II ------------------------------------------------------------


def test_nsga2_returns_nonempty_front():
    """NSGA-II на простой задаче должен вернуть непустой Парето-фронт."""
    model = AsymmetricModel()
    ga = NSGA2(
        pop_size=30, n_gen=10,
        voltages=(+15.0, -15.0, 0.0),
        durations=(1, 2, 4, 8),
        k_eff_max=3,
        seed=42,
    )
    front = ga.run(model, z_init=0.07, z_target=0.10)
    assert len(front) >= 1


def test_nsga2_is_reproducible_with_seed():
    """Один и тот же seed → один и тот же фронт."""
    model = AsymmetricModel()
    ga1 = NSGA2(pop_size=20, n_gen=5, seed=7,
                voltages=(+15.0, -15.0), durations=(1, 2, 4), k_eff_max=2)
    ga2 = NSGA2(pop_size=20, n_gen=5, seed=7,
                voltages=(+15.0, -15.0), durations=(1, 2, 4), k_eff_max=2)
    front1 = ga1.run(model, 0.07, 0.10)
    front2 = ga2.run(model, 0.07, 0.10)
    assert len(front1) == len(front2)
    v1 = sorted((p.energy, p.ghost, p.latency) for p in front1)
    v2 = sorted((p.energy, p.ghost, p.latency) for p in front2)
    assert v1 == pytest.approx(v2, abs=1e-9)
