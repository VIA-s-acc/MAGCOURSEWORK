"""Обработка фотографий EPD-панели для измерения ghosting (гл. 7).

Pipeline извлечения метрик качества из снимка стенда:

  фото (RGB) → grayscale → коррекция ROI (перспектива/кроп) →
  нормировка яркости по белому калибровочному квадрату →
  reflectance-карта [0,1] → сравнение с целевым кадром (SSIM, residual).

Метрики SSIM/residual вычисляются модулем :mod:`python.metrics`; здесь
реализована только специфичная для фотостанда часть: геометрическая и
яркостная нормализация снимка.

Используется в:
- python/bench_protocol.py (один прогон baseline на стенде)
- scripts/run_bench_campaign.py (полная кампания B0..B4)
- gl. 7 курсовой (§ 7.3 «Фотостанд для измерения ghost»)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from PIL import Image
from skimage.transform import ProjectiveTransform, warp

from python.metrics import residual, ssim_score

logger = logging.getLogger(__name__)

# Нативное разрешение Waveshare 2.13" V4.
PANEL_W = 250
PANEL_H = 122


@dataclass(frozen=True)
class Capture:
    """Нормированный снимок EPD-панели.

    Атрибуты:
        reflectance: 2D-массив [0,1] размера (PANEL_H, PANEL_W),
            где 0 — самый тёмный, 1 — самый светлый пиксель (после
            яркостной нормировки по белому квадрату).
        white_level: измеренная яркость белого калибровочного квадрата
            (до нормировки, в долях [0,1]) — для контроля стабильности
            освещения между кадрами.
    """

    reflectance: np.ndarray
    white_level: float


def load_grayscale(path: str) -> np.ndarray:
    """Загрузить изображение и привести к grayscale float [0,1].

    Использует luma-преобразование ITU-R BT.601 (стандарт PIL "L").
    """
    img = Image.open(path).convert("L")
    arr = np.asarray(img, dtype=np.float64) / 255.0
    logger.debug("load_grayscale: %s -> shape=%s, mean=%.3f", path, arr.shape, arr.mean())
    return arr


def extract_roi(
    gray: np.ndarray,
    corners: list[tuple[float, float]],
    out_w: int = PANEL_W,
    out_h: int = PANEL_H,
) -> np.ndarray:
    """Геометрически выпрямить область EPD по 4 угловым точкам.

    Параметры:
        gray: grayscale-изображение [0,1].
        corners: 4 точки (x, y) углов панели на снимке в порядке
            [верх-лево, верх-право, низ-право, низ-лево].
        out_w, out_h: размер выходной прямоугольной reflectance-карты.

    Возвращает: выпрямленный массив (out_h, out_w) в [0,1].

    Проективное преобразование переводит произвольный четырёхугольник
    (панель, снятая под небольшим углом) в строгий прямоугольник, устраняя
    перспективные искажения.
    """
    if len(corners) != 4:
        raise ValueError(f"corners must have exactly 4 points, got {len(corners)}")

    src = np.array([
        [0, 0],
        [out_w, 0],
        [out_w, out_h],
        [0, out_h],
    ], dtype=np.float64)
    dst = np.array(corners, dtype=np.float64)

    tform = ProjectiveTransform()
    if not tform.estimate(src, dst):
        raise RuntimeError("ProjectiveTransform.estimate failed (вырожденные углы?)")

    warped = warp(gray, tform, output_shape=(out_h, out_w), order=1, mode="edge")
    logger.debug("extract_roi: -> shape=%s, mean=%.3f", warped.shape, warped.mean())
    return warped


def crop_roi(gray: np.ndarray, bbox: tuple[int, int, int, int],
             out_w: int = PANEL_W, out_h: int = PANEL_H) -> np.ndarray:
    """Упрощённый ROI без перспективы: прямоугольный кроп + resize.

    bbox = (x0, y0, x1, y1) в пикселях исходного снимка.
    Применим, когда камера строго перпендикулярна панели.
    """
    x0, y0, x1, y1 = bbox
    if not (0 <= x0 < x1 <= gray.shape[1] and 0 <= y0 < y1 <= gray.shape[0]):
        raise ValueError(f"bbox {bbox} вне границ изображения {gray.shape}")
    sub = gray[y0:y1, x0:x1]
    img = Image.fromarray((np.clip(sub, 0, 1) * 255).astype(np.uint8)).resize(
        (out_w, out_h), Image.BILINEAR
    )
    return np.asarray(img, dtype=np.float64) / 255.0


def measure_white_level(gray: np.ndarray, patch_bbox: tuple[int, int, int, int]) -> float:
    """Средняя яркость белого калибровочного квадрата (в [0,1])."""
    x0, y0, x1, y1 = patch_bbox
    patch = gray[y0:y1, x0:x1]
    if patch.size == 0:
        raise ValueError(f"patch_bbox {patch_bbox} даёт пустую область")
    return float(patch.mean())


def build_capture(
    gray: np.ndarray,
    panel_corners: list[tuple[float, float]] | None = None,
    panel_bbox: tuple[int, int, int, int] | None = None,
    white_patch_bbox: tuple[int, int, int, int] | None = None,
) -> Capture:
    """Собрать нормированный Capture из grayscale-снимка.

    Геометрия: либо `panel_corners` (перспектива), либо `panel_bbox` (кроп).
    Яркостная нормировка: если задан `white_patch_bbox`, reflectance делится
    на яркость белого квадрата (компенсация колебаний освещения между
    кадрами); иначе нормировка не выполняется.
    """
    if (panel_corners is None) == (panel_bbox is None):
        raise ValueError("Задайте ровно одно из panel_corners / panel_bbox")

    if panel_corners is not None:
        roi = extract_roi(gray, panel_corners)
    else:
        roi = crop_roi(gray, panel_bbox)  # type: ignore[arg-type]

    white_level = 1.0
    if white_patch_bbox is not None:
        white_level = measure_white_level(gray, white_patch_bbox)
        if white_level <= 1e-6:
            raise ValueError("Белый квадрат измерен как чёрный — проверьте bbox/освещение")
        roi = np.clip(roi / white_level, 0.0, 1.0)
        logger.debug("build_capture: white_level=%.3f, нормировано", white_level)

    return Capture(reflectance=roi, white_level=white_level)


def compare_to_target(capture: Capture, target: np.ndarray) -> dict[str, float]:
    """Сравнить снятый кадр с целевым изображением.

    Параметры:
        capture: нормированный Capture (reflectance [0,1], PANEL_H×PANEL_W).
        target: целевое изображение [0,1]; при ином размере масштабируется
            к (PANEL_H, PANEL_W).

    Возвращает: {"ssim": ..., "residual": ..., "ghost_ssim": 1-ssim}.
    """
    tgt = target
    if tgt.shape != capture.reflectance.shape:
        img = Image.fromarray((np.clip(tgt, 0, 1) * 255).astype(np.uint8)).resize(
            (PANEL_W, PANEL_H), Image.BILINEAR
        )
        tgt = np.asarray(img, dtype=np.float64) / 255.0

    s = ssim_score(capture.reflectance, tgt)
    r = residual(capture.reflectance, tgt)
    logger.info("compare_to_target: SSIM=%.4f, residual=%.4f", s, r)
    return {"ssim": s, "residual": r, "ghost_ssim": 1.0 - s}
