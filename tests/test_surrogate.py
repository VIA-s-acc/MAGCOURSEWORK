"""Тесты для python/surrogate.py — SurrogateModel + fit + predict."""

from __future__ import annotations

import numpy as np
import pytest

from python.ode_sim import PixelOdeSim
from python.optimizer import Waveform
from python.surrogate import SurrogateModel


# ---- Конструктор и валидация --------------------------------------------


def test_surrogate_validates_voltages_grid():
    with pytest.raises(ValueError, match="voltages grid"):
        SurrogateModel(voltages=(0.0,), durations_frames=(1, 2), z_levels=(0.0, 1.0))


def test_surrogate_validates_sort_order():
    with pytest.raises(ValueError, match="voltages must be sorted"):
        SurrogateModel(voltages=(15.0, -15.0), durations_frames=(1, 2), z_levels=(0.0, 1.0))
    with pytest.raises(ValueError, match="durations_frames must be sorted"):
        SurrogateModel(voltages=(-15.0, 15.0), durations_frames=(4, 1), z_levels=(0.0, 1.0))
    with pytest.raises(ValueError, match="z_levels must be sorted"):
        SurrogateModel(voltages=(-15.0, 15.0), durations_frames=(1, 4), z_levels=(0.5, 0.1))


def test_surrogate_predict_before_fit_raises():
    surr = SurrogateModel(voltages=(-15.0, 15.0), durations_frames=(1, 4), z_levels=(0.1, 0.4))
    wf = Waveform(voltages=(15.0,), durations=(1,))
    with pytest.raises(RuntimeError, match="not fitted"):
        surr.predict(wf, 0.1, 0.4)


# ---- Fit from ODE-симулятора -------------------------------------------


def _fitted_surrogate() -> tuple[SurrogateModel, PixelOdeSim]:
    sim = PixelOdeSim(mu_star=1.5e-9, tau_star=30e-3, rho_min=0.07, rho_max=0.40, L=40e-6)
    surr = SurrogateModel(
        voltages=(-15.0, -5.0, 0.0, 5.0, 15.0),
        durations_frames=(1, 2, 4, 8, 16),
        z_levels=(0.07, 0.15, 0.25, 0.40),
        z_clip=(0.07, 0.40),
    )
    surr.fit_from_ode_sim(sim, c_eff_nF=11.7, vcom=0.0)
    return surr, sim


def test_surrogate_fit_populates_grids():
    surr, _ = _fitted_surrogate()
    assert surr.e_grid.shape == (5, 5)
    assert surr.dz_grid.shape == (5, 5, 4)
    # Энергия положительна для любого V≠0, нулевая для V=0.
    assert (surr.e_grid >= -1e-12).all()
    # V=0 столбец должен быть нулевой.
    v0_idx = surr.voltages.index(0.0)
    assert np.allclose(surr.e_grid[v0_idx, :], 0.0)


def test_surrogate_predict_matches_grid_node():
    """В узле сетки surrogate должен воспроизводить grid значение точно."""
    surr, _ = _fitted_surrogate()
    # узел: V=15, T=4, z_in=0.07
    wf = Waveform(voltages=(15.0,), durations=(4,), f_frame=50.0)
    E, G, tau = surr.predict(wf, z_init=0.07, z_target=0.07)
    # ожидание: E = surr.e_grid[V=15, T=4]; z_final = 0.07 + surr.dz_grid[V=15, T=4, z=0.07]
    i_V = surr.voltages.index(15.0)
    j_T = surr.durations_frames.index(4)
    k_Z = surr.z_levels.index(0.07)
    expected_E = surr.e_grid[i_V, j_T]
    expected_dz = surr.dz_grid[i_V, j_T, k_Z]
    assert E == pytest.approx(expected_E, rel=1e-9)
    assert G == pytest.approx(abs(expected_dz), abs=1e-9)  # z_target=z_init → G=|dz|
    assert tau == pytest.approx(4 / 50.0)


def test_surrogate_predict_is_deterministic():
    """predict() в одинаковых условиях даёт одинаковый результат."""
    surr, _ = _fitted_surrogate()
    wf = Waveform(voltages=(15.0, -15.0, 5.0), durations=(2, 2, 3))
    r1 = surr.predict(wf, 0.07, 0.40)
    r2 = surr.predict(wf, 0.07, 0.40)
    assert r1 == r2


def test_surrogate_predict_decomposes_into_phases():
    """E(waveform) = Σ_k e_grid[V_k, T_k] (аддитивность по фазам)."""
    surr, _ = _fitted_surrogate()
    wf = Waveform(voltages=(15.0, -15.0), durations=(4, 4), f_frame=50.0)
    E, _, _ = surr.predict(wf, z_init=0.07, z_target=0.07)
    i_V_pos = surr.voltages.index(15.0)
    i_V_neg = surr.voltages.index(-15.0)
    j_T = surr.durations_frames.index(4)
    expected_E = surr.e_grid[i_V_pos, j_T] + surr.e_grid[i_V_neg, j_T]
    assert E == pytest.approx(expected_E, rel=1e-9)


def test_surrogate_dz_at_boundary_clipped():
    """При z_init за пределами z_clip surrogate должен клипнуть к границе."""
    surr, _ = _fitted_surrogate()
    wf = Waveform(voltages=(15.0,), durations=(1,))
    # z_init = 0.50 — выше rho_max=0.40, должен клипнуться без ошибки.
    E1, G1, _ = surr.predict(wf, z_init=0.50, z_target=0.50)
    E2, G2, _ = surr.predict(wf, z_init=0.40, z_target=0.40)
    # E одинакова (не зависит от z), G тоже совпадает (clip уравнял z_in для δz).
    assert E1 == pytest.approx(E2)
    assert G1 == pytest.approx(G2)
