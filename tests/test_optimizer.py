"""Тесты для python/optimizer.py — solve_pmp_slice + Waveform/WaveformResult."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from python.optimizer import (
    DEFAULT_CHARGE_EPS,
    DEFAULT_F_FRAME,
    Waveform,
    WaveformResult,
    solve_pmp_slice,
)


# ---- Аналитическая модель (для контролируемых тестов) -------------------


@dataclass
class AsymmetricAnalyticalModel:
    """Модель для тестов: асимметричная подвижность (рев. вс. форв. пульсов).

    Физически: TiO2/CB-частицы имеют разную скорость в положительном и
    отрицательном поле (Yang 2021). Это разрушает дегенерацию линейной модели
    при ε-зарядовом балансе: даже при Σ V·T = 0 имеем ненулевой Δz, что
    физически правильно (см. M4 § 4.3 — обоснование ε-релаксации).

    E  = c_E · Σ_k V[k]² · T[k]/f_frame                       [мДж]
    Δz = Σ_k μ(V[k]) · V[k] · T[k]/f_frame,
         где μ(V) = μ_pos при V>0, μ_neg при V<0, 0 при V=0   [рефл. единицы]
    G  = |Δz − (z_target − z_init)|                            [||·||_1]
    τ  = Σ_k T[k]/f_frame                                       [с]
    """

    c_E: float = 1.0e-3     # коэффициент энергии (мДж на В²·с)
    mu_pos: float = 0.060   # подвижность форв. пульса (рефл. единицы на В·с)
    mu_neg: float = 0.040   # подвижность реверс. пульса (асимметрия 50%)

    def predict(self, wf: Waveform, z_init: float, z_target: float) -> tuple[float, float, float]:
        e = sum(self.c_E * v * v * t / wf.f_frame for v, t in zip(wf.voltages, wf.durations))
        dz = 0.0
        for v, t in zip(wf.voltages, wf.durations):
            if v > 0:
                dz += self.mu_pos * v * t / wf.f_frame
            elif v < 0:
                dz += self.mu_neg * v * t / wf.f_frame
        g = abs(dz - (z_target - z_init))
        tau = wf.total_time
        return (e, g, tau)


# Backward alias — старое имя ничего не значит, но используем в тестах
LinearAnalyticalModel = AsymmetricAnalyticalModel


# ---- Waveform: конструктор и инварианты ---------------------------------


def test_waveform_length_mismatch_raises():
    with pytest.raises(ValueError, match="len\\(voltages\\)"):
        Waveform(voltages=(15.0, -15.0), durations=(4,))


def test_waveform_bad_frame_rate_raises():
    with pytest.raises(ValueError, match="f_frame must be positive"):
        Waveform(voltages=(15.0,), durations=(4,), f_frame=0.0)


def test_waveform_k_eff_counts_only_nonzero():
    wf = Waveform(voltages=(+15.0, 0.0, -15.0, 0.0), durations=(2, 1, 2, 1))
    assert wf.k_eff == 2


def test_waveform_charge_integral_balanced():
    wf = Waveform(voltages=(+15.0, -15.0), durations=(4, 4), f_frame=50.0)
    assert wf.charge_integral == pytest.approx(0.0, abs=1e-12)


def test_waveform_total_time():
    wf = Waveform(voltages=(+15.0, -15.0), durations=(4, 4), f_frame=50.0)
    assert wf.total_time == pytest.approx(8 / 50.0)


# ---- solve_pmp_slice: feasibility + структура ---------------------------


def test_optimizer_returns_none_when_eps_tau_too_tight():
    model = LinearAnalyticalModel()
    # τ ограничено 1 кадром при f=50 → 0.02 с. С durations начиная с 1
    # τ_min = 0.02 с; задаём 0.005 → нет ни одного допустимого кандидата.
    result = solve_pmp_slice(
        z_init=0.0, z_target=0.5,
        eps_G=1.0, eps_tau=0.005,
        model=model,
        voltages=(+15.0, -15.0),
        durations=(1, 2),
    )
    assert result is None


def test_optimizer_returns_charge_balanced_waveform():
    """Выход должен удовлетворять |Σ V·T| ≤ charge_eps.

    Цель Δz = 0.04 достижима в асимметричной модели через 2-фазный baseline
    (+15, T=4)+(−15, T=4): Δz = 0.02·15·4/50 = 0.024 для μ_diff=0.02; 4-фазный
    (+15,4)+(−15,2)+(+15,4)+(−15,2) с балансом гораздо лучше.
    """
    model = LinearAnalyticalModel()
    result = solve_pmp_slice(
        z_init=0.0, z_target=0.04,
        eps_G=0.02, eps_tau=0.5,
        model=model,
        voltages=(+15.0, -15.0, +5.0),
        durations=(1, 2, 4, 8),
        charge_eps=DEFAULT_CHARGE_EPS,
    )
    assert result is not None
    assert abs(result.waveform.charge_integral) <= DEFAULT_CHARGE_EPS


def test_optimizer_respects_k_eff_bound():
    """K_eff(найденного waveform) ≤ k_eff_max."""
    model = LinearAnalyticalModel()
    K_MAX = 3
    result = solve_pmp_slice(
        z_init=0.0, z_target=0.03,
        eps_G=0.02, eps_tau=1.0,
        model=model,
        voltages=(+15.0, -15.0),
        durations=(1, 2, 3, 4),
        k_eff_max=K_MAX,
    )
    assert result is not None
    assert len(result.waveform.voltages) <= K_MAX


def test_optimizer_minimizes_energy_among_feasible():
    """При нескольких допустимых кандидатах выбран минимум E."""
    model = LinearAnalyticalModel()
    voltages = (+15.0, +5.0, -15.0, -5.0)
    durations = (1, 2, 3, 4, 6, 8)
    result = solve_pmp_slice(
        z_init=0.0, z_target=0.03,
        eps_G=0.02, eps_tau=0.5,
        model=model,
        voltages=voltages,
        durations=durations,
        k_eff_max=3,
        charge_eps=0.05,
    )
    assert result is not None
    # Сверка с brute-force перебором — оптимизатор должен совпасть глобально.
    from python.optimizer import _iter_bang_bang_candidates
    best_E_brute = float("inf")
    for wf in _iter_bang_bang_candidates(voltages, durations, 3, DEFAULT_F_FRAME):
        if abs(wf.charge_integral) > 0.05:
            continue
        if wf.total_time > 0.5:
            continue
        E, G, tau = model.predict(wf, 0.0, 0.03)
        if G > 0.02:
            continue
        if E < best_E_brute:
            best_E_brute = E
    assert result.energy == pytest.approx(best_E_brute, rel=1e-9)


def test_optimizer_respects_eps_G_constraint():
    """ε_G — жёсткое: результат должен иметь G ≤ ε_G."""
    model = LinearAnalyticalModel()
    EPS_G = 0.015
    result = solve_pmp_slice(
        z_init=0.0, z_target=0.03,
        eps_G=EPS_G, eps_tau=1.0,
        model=model,
        voltages=(+15.0, -15.0, +5.0),
        durations=(1, 2, 4, 8),
        k_eff_max=4,
    )
    if result is not None:
        assert result.ghost <= EPS_G + 1e-12
