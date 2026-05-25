"""Тесты для python/ode_sim.py — overdamped + full режимы + replay_lut."""

import numpy as np
import pytest

from python.ode_sim import PixelOdeSim


# ---- Конструктор и валидация --------------------------------------------

def test_default_constructor_ok():
    sim = PixelOdeSim()
    assert sim.mu_star > 0
    assert sim.tau_star > 0
    assert sim.mode == "overdamped"


def test_bad_mode_raises():
    with pytest.raises(ValueError, match="mode must be"):
        PixelOdeSim(mode="quantum")


def test_bad_tau_raises():
    with pytest.raises(ValueError, match="tau_star must be positive"):
        PixelOdeSim(tau_star=-1.0)


def test_bad_L_raises():
    with pytest.raises(ValueError, match="L must be positive"):
        PixelOdeSim(L=0.0)


def test_bad_reflectance_bounds():
    with pytest.raises(ValueError, match="reflectance bounds"):
        PixelOdeSim(rho_min=0.5, rho_max=0.3)
    with pytest.raises(ValueError, match="reflectance bounds"):
        PixelOdeSim(rho_min=-0.1, rho_max=0.5)
    with pytest.raises(ValueError, match="reflectance bounds"):
        PixelOdeSim(rho_min=0.5, rho_max=1.5)


# ---- terminal_velocity и reflectance ------------------------------------

def test_terminal_velocity_proportional_to_U():
    sim = PixelOdeSim(mu_star=1e-9, L=40e-6)
    assert sim.terminal_velocity(0) == 0.0
    v1 = sim.terminal_velocity(1.0)
    v15 = sim.terminal_velocity(15.0)
    assert v15 == pytest.approx(15.0 * v1)
    assert v1 == pytest.approx(1e-9 / 40e-6)


def test_reflectance_endpoints():
    sim = PixelOdeSim(rho_min=0.07, rho_max=0.40, L=40e-6)
    assert sim.reflectance(0.0) == pytest.approx(0.07)
    assert sim.reflectance(sim.L) == pytest.approx(0.40)
    assert sim.reflectance(sim.L / 2) == pytest.approx((0.07 + 0.40) / 2)


def test_reflectance_clipping():
    sim = PixelOdeSim(rho_min=0.07, rho_max=0.40, L=40e-6)
    # за пределами [0, L] — клипуем
    assert sim.reflectance(-1e-3) == pytest.approx(0.07)
    assert sim.reflectance(10 * sim.L) == pytest.approx(0.40)


def test_reflectance_vectorized():
    sim = PixelOdeSim()
    xs = np.linspace(0, sim.L, 5)
    rhos = sim.reflectance(xs)
    assert rhos.shape == xs.shape
    assert rhos[0] == pytest.approx(sim.rho_min)
    assert rhos[-1] == pytest.approx(sim.rho_max)


# ---- Overdamped simulate ------------------------------------------------

def test_overdamped_constant_voltage_linear_motion():
    """При постоянном U положение растёт линейно: x(t) = v_∞·t."""
    sim = PixelOdeSim(mu_star=1e-9, L=40e-6, mode="overdamped")
    U0 = 15.0
    sol = sim.simulate(t_span=(0, 0.1), u_func=lambda t: U0, x0=0.0)
    v_inf = sim.terminal_velocity(U0)
    expected_xf = v_inf * 0.1
    assert sol["x"][-1] == pytest.approx(expected_xf, rel=1e-4)


def test_overdamped_zero_voltage_no_motion():
    sim = PixelOdeSim(mode="overdamped")
    sol = sim.simulate(t_span=(0, 0.1), u_func=lambda t: 0.0, x0=1e-5)
    assert sol["x"][-1] == pytest.approx(1e-5, abs=1e-10)


def test_overdamped_charge_balanced_returns_origin():
    """Симметричный +V/-V с равными длительностями → x(T_end) = x(0)."""
    sim = PixelOdeSim(mode="overdamped")
    T_half = 0.05

    def u_balanced(t):
        return 15.0 if t < T_half else -15.0

    sol = sim.simulate(
        t_span=(0, 2 * T_half),
        u_func=u_balanced,
        x0=1e-5,
        max_step=T_half / 100,
    )
    assert sol["x"][-1] == pytest.approx(1e-5, abs=1e-9)


# ---- Full mode (с инерцией) ---------------------------------------------

def test_full_mode_reaches_terminal_velocity():
    """В full режиме при постоянном U скорость стремится к v_terminal."""
    sim = PixelOdeSim(mu_star=1e-9, tau_star=30e-3, L=40e-6, mode="full")
    U0 = 15.0
    # симулируем 10·tau, должны выйти на v_inf с погрешностью exp(-10) ≈ 0.005%
    sol = sim.simulate(t_span=(0, 10 * sim.tau_star), u_func=lambda t: U0, x0=0.0, v0=0.0)
    v_inf = sim.terminal_velocity(U0)
    assert sol["v"][-1] == pytest.approx(v_inf, rel=1e-3)


def test_full_mode_exponential_approach():
    """v(τ) ≈ v_∞·(1 − e^-1) ≈ 0.632·v_∞ — проверка экспоненты."""
    sim = PixelOdeSim(mu_star=1e-9, tau_star=30e-3, L=40e-6, mode="full")
    U0 = 15.0
    sol = sim.simulate(
        t_span=(0, sim.tau_star),
        u_func=lambda t: U0,
        x0=0.0, v0=0.0,
        max_step=sim.tau_star / 100,
    )
    v_inf = sim.terminal_velocity(U0)
    # При t=tau v должно быть v_inf·(1−1/e)
    assert sol["v"][-1] == pytest.approx(v_inf * (1 - np.exp(-1)), rel=1e-3)


def test_full_mode_v_starts_at_zero():
    sim = PixelOdeSim(mode="full")
    sol = sim.simulate(t_span=(0, 1e-3), u_func=lambda t: 15.0, x0=0.0, v0=0.0)
    # на первом шаге v ещё мала
    assert sol["v"][0] == pytest.approx(0.0, abs=1e-9)


# ---- replay_lut ----------------------------------------------------------

def test_replay_lut_single_phase():
    sim = PixelOdeSim(mu_star=1e-9, L=40e-6, mode="overdamped")
    sol = sim.replay_lut(u_seq=[(15.0, 0.1)])
    v_inf = sim.terminal_velocity(15.0)
    assert sol["t"][-1] == pytest.approx(0.1)
    assert sol["x"][-1] == pytest.approx(v_inf * 0.1, rel=1e-3)


def test_replay_lut_charge_balanced_4_phases():
    """4-фазная charge-balanced LUT возвращает в начальное положение."""
    sim = PixelOdeSim(mode="overdamped")
    # +V, -V, +V, -V с равными TP
    u_seq = [(15.0, 0.025), (-15.0, 0.025), (15.0, 0.025), (-15.0, 0.025)]
    sol = sim.replay_lut(u_seq, x0=1e-5)
    assert sol["t"][-1] == pytest.approx(0.1)
    assert sol["x"][-1] == pytest.approx(1e-5, abs=1e-10)


def test_replay_lut_skips_zero_duration_phases():
    sim = PixelOdeSim()
    u_seq = [(15.0, 0.05), (10.0, 0.0), (-15.0, 0.05)]
    sol = sim.replay_lut(u_seq)
    # T_total = 0.05 + 0 + 0.05 = 0.1
    assert sol["t"][-1] == pytest.approx(0.1)


def test_replay_lut_empty_raises():
    sim = PixelOdeSim()
    with pytest.raises(ValueError, match="non-empty"):
        sim.replay_lut(u_seq=[])


def test_replay_lut_reflectance_changes():
    sim = PixelOdeSim(mu_star=1e-9, L=40e-6, rho_min=0.07, rho_max=0.40, mode="overdamped")
    # Применяем большой положительный V — частицы движутся к x = L
    # mu_star * U / L * T = 1e-9 * 15 / 40e-6 * 0.1 = 3.75e-5 м — больше L=40e-6
    # → доходим до L, rho → rho_max
    sol = sim.replay_lut([(15.0, 0.2)], x0=0.0)
    assert sol["rho"][-1] == pytest.approx(sim.rho_max, abs=0.02)


# ---- Repr smoke ----------------------------------------------------------

def test_repr_smoke():
    sim = PixelOdeSim()
    s = repr(sim)
    assert "PixelOdeSim" in s
    assert "mu_star" in s
    assert "mode" in s
