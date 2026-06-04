"""Тесты для python/photo_pipeline.py."""

from __future__ import annotations

import numpy as np
import pytest

from python.photo_pipeline import (
    PANEL_H,
    PANEL_W,
    build_capture,
    compare_to_target,
    crop_roi,
    extract_roi,
    measure_white_level,
)


# ---- crop_roi -----------------------------------------------------------


def test_crop_roi_resizes_to_panel():
    gray = np.linspace(0, 1, 200 * 100).reshape(100, 200)
    roi = crop_roi(gray, bbox=(10, 10, 190, 90))
    assert roi.shape == (PANEL_H, PANEL_W)
    assert 0.0 <= roi.min() <= roi.max() <= 1.0


def test_crop_roi_rejects_out_of_bounds():
    gray = np.zeros((100, 200))
    with pytest.raises(ValueError, match="вне границ"):
        crop_roi(gray, bbox=(0, 0, 300, 90))


# ---- extract_roi (perspective) ------------------------------------------


def test_extract_roi_identity_rectangle():
    """Для углов, совпадающих с прямоугольником PANEL_W×PANEL_H,
    выпрямление должно вернуть исходное изображение почти без изменений."""
    rng = np.random.default_rng(0)
    gray = rng.random((PANEL_H, PANEL_W))
    corners = [(0, 0), (PANEL_W, 0), (PANEL_W, PANEL_H), (0, PANEL_H)]
    roi = extract_roi(gray, corners)
    assert roi.shape == (PANEL_H, PANEL_W)
    # центральная область должна совпадать (края могут чуть отличаться из-за warp)
    assert np.allclose(roi[5:-5, 5:-5], gray[5:-5, 5:-5], atol=0.05)


def test_extract_roi_requires_four_corners():
    gray = np.zeros((50, 50))
    with pytest.raises(ValueError, match="exactly 4"):
        extract_roi(gray, [(0, 0), (1, 0), (1, 1)])


# ---- white level + normalization ----------------------------------------


def test_measure_white_level():
    gray = np.full((100, 100), 0.5)
    gray[0:10, 0:10] = 0.8  # белый квадрат
    assert measure_white_level(gray, (0, 0, 10, 10)) == pytest.approx(0.8)


def test_build_capture_normalizes_by_white_patch():
    # Панель серая (0.4), белый квадрат 0.8 → нормировка даёт reflectance 0.5
    gray = np.full((PANEL_H + 20, PANEL_W + 40), 0.4)
    gray[0:10, 0:10] = 0.8
    cap = build_capture(
        gray,
        panel_bbox=(20, 15, 20 + PANEL_W, 15 + PANEL_H),
        white_patch_bbox=(0, 0, 10, 10),
    )
    assert cap.white_level == pytest.approx(0.8)
    assert cap.reflectance.mean() == pytest.approx(0.5, abs=0.02)


def test_build_capture_requires_exactly_one_geometry():
    gray = np.zeros((PANEL_H, PANEL_W))
    with pytest.raises(ValueError, match="ровно одно"):
        build_capture(gray)  # ни corners, ни bbox
    with pytest.raises(ValueError, match="ровно одно"):
        build_capture(gray, panel_bbox=(0, 0, 10, 10),
                      panel_corners=[(0, 0), (1, 0), (1, 1), (0, 1)])


# ---- compare_to_target --------------------------------------------------


def test_compare_identical_gives_ssim_one():
    from python.photo_pipeline import Capture
    img = np.random.default_rng(1).random((PANEL_H, PANEL_W))
    cap = Capture(reflectance=img, white_level=1.0)
    res = compare_to_target(cap, img)
    assert res["ssim"] == pytest.approx(1.0, abs=1e-9)
    assert res["residual"] == pytest.approx(0.0, abs=1e-9)
    assert res["ghost_ssim"] == pytest.approx(0.0, abs=1e-9)


def test_compare_resizes_target():
    from python.photo_pipeline import Capture
    cap = Capture(reflectance=np.full((PANEL_H, PANEL_W), 0.3), white_level=1.0)
    target_big = np.full((PANEL_H * 2, PANEL_W * 2), 0.3)  # иной размер
    res = compare_to_target(cap, target_big)
    assert res["residual"] == pytest.approx(0.0, abs=0.01)
