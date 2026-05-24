"""Тесты для python/metrics.py — SSIM, residual, lifetime proxy."""

import numpy as np
import pytest

from python.metrics import (
    ghost_ssim,
    lifetime_proxy_energy_density,
    residual,
    ssim_score,
    to_float01,
    worst_case_residual,
)


# ---- to_float01 -----------------------------------------------------------

def test_to_float01_uint8():
    img = np.array([[0, 128, 255]], dtype=np.uint8)
    f = to_float01(img)
    assert f.dtype == np.float64
    np.testing.assert_allclose(f, [[0.0, 128 / 255, 1.0]])


def test_to_float01_bool():
    img = np.array([[True, False]], dtype=np.bool_)
    f = to_float01(img)
    np.testing.assert_array_equal(f, [[1.0, 0.0]])


def test_to_float01_already_normalized():
    img = np.array([[0.0, 0.5, 1.0]])
    f = to_float01(img)
    np.testing.assert_allclose(f, img)


# ---- residual -------------------------------------------------------------

def test_residual_identical_zero():
    img = np.ones((32, 32), dtype=np.uint8) * 128
    assert residual(img, img) == 0.0


def test_residual_black_vs_white():
    black = np.zeros((10, 10), dtype=np.uint8)
    white = np.ones((10, 10), dtype=np.uint8) * 255
    assert residual(black, white) == pytest.approx(1.0)
    assert residual(white, black) == pytest.approx(1.0)


def test_residual_half_difference():
    a = np.zeros((10, 10), dtype=np.uint8)
    b = np.ones((10, 10), dtype=np.uint8) * 128  # 0.5019 после деления на 255
    assert residual(a, b) == pytest.approx(128 / 255, rel=1e-6)


def test_residual_shape_mismatch_raises():
    with pytest.raises(ValueError, match="shape mismatch"):
        residual(np.zeros((10, 10)), np.zeros((10, 20)))


# ---- SSIM -----------------------------------------------------------------

def test_ssim_identical_is_one():
    rng = np.random.default_rng(0)
    img = (rng.random((64, 64)) * 255).astype(np.uint8)
    assert ssim_score(img, img) == pytest.approx(1.0, abs=1e-6)


def test_ssim_inverted_is_low():
    img = np.zeros((64, 64), dtype=np.uint8)
    inv = np.ones((64, 64), dtype=np.uint8) * 255
    score = ssim_score(img, inv)
    # SSIM на полностью противоположных постоянных изображениях должно быть низким
    assert score < 0.1


def test_ghost_ssim_complement():
    img = np.ones((32, 32), dtype=np.uint8) * 100
    assert ghost_ssim(img, img) == pytest.approx(0.0, abs=1e-6)


# ---- worst-case residual --------------------------------------------------

def test_worst_case_residual_picks_max():
    target = np.zeros((10, 10), dtype=np.uint8)
    histories = [
        np.zeros((10, 10), dtype=np.uint8),         # res = 0
        np.full((10, 10), 64,  dtype=np.uint8),     # res ≈ 0.25
        np.full((10, 10), 255, dtype=np.uint8),     # res = 1.0
    ]
    worst = worst_case_residual(histories, target)
    assert worst == pytest.approx(1.0)


def test_worst_case_empty_raises():
    with pytest.raises(ValueError, match="non-empty"):
        worst_case_residual([], np.zeros((10, 10)))


# ---- lifetime proxy -------------------------------------------------------

def test_lifetime_proxy_zero_for_vcom():
    """Все напряжения = 0 → нагрузка = 0."""
    v = np.zeros(12)
    t = np.ones(12) * 0.01
    assert lifetime_proxy_energy_density(v, t) == 0.0


def test_lifetime_proxy_v_squared():
    """Σ V²·TP: 1 фаза 15В × 0.1 сек = 22.5 В²·с."""
    v = np.array([15.0])
    t = np.array([0.1])
    assert lifetime_proxy_energy_density(v, t) == pytest.approx(22.5)


def test_lifetime_proxy_sign_insensitive():
    """V² одинаково для +V и -V (charge balance — это hard constraint, не lifetime)."""
    v_pos = np.array([15.0, 15.0])
    v_neg = np.array([-15.0, -15.0])
    t = np.array([0.1, 0.1])
    assert lifetime_proxy_energy_density(v_pos, t) == lifetime_proxy_energy_density(v_neg, t)


def test_lifetime_proxy_shape_mismatch():
    with pytest.raises(ValueError, match="shape mismatch"):
        lifetime_proxy_energy_density(np.zeros(3), np.zeros(4))
