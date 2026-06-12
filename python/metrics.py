"""Метрики качества обновления EPD: SSIM, residual reflectance, ghost score.

Используются в:
- симуляторе (``notebook/02_optimize.ipynb``) — для оптимизации waveform;
- экспериментах (``notebook/04_bench.ipynb``) — для сравнения с baseline'ами;
- теоретической главе 4 — формальное определение G через L1-норму residual'а.

Канонические определения:
- ``G_residual = (1/N) · Σ |reflect_actual − reflect_target|``  — линейная метрика
   для PMP-теоремы.
- ``G_ssim     = 1 − SSIM(target, rendered)``                   — для презентации.
- ``G_worst    = max_history |reflect_after_history − reflect_target|`` — для
   worst-case анализа (требует множества историй).
"""

from __future__ import annotations

import logging

import numpy as np
from skimage.metrics import structural_similarity as ssim

logger = logging.getLogger(__name__)


def to_float01(img: np.ndarray) -> np.ndarray:
    """Привести изображение к float в диапазоне [0, 1].

    Поддерживает uint8 [0..255], bool, float [0..1].
    """
    if img.dtype == np.bool_:
        return img.astype(np.float64)
    if np.issubdtype(img.dtype, np.integer):
        info = np.iinfo(img.dtype)
        return img.astype(np.float64) / float(info.max)
    # float reflectance ожидается уже в [0,1]; клипуем, а не нормируем по max
    # (нормировка по своему max сделала бы два кадра несравнимыми между собой).
    return np.clip(img.astype(np.float64), 0.0, 1.0)


def residual(img_actual: np.ndarray, img_target: np.ndarray) -> float:
    """Средняя пиксельная L1-разность по изображениям.

    G_residual = (1/N) · Σ |reflect_actual − reflect_target|, где reflectance ∈ [0,1].
    """
    a = to_float01(img_actual)
    t = to_float01(img_target)
    if a.shape != t.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {t.shape}")
    val = float(np.mean(np.abs(a - t)))
    logger.debug("residual: shape=%s, value=%.6f", a.shape, val)
    return val


def ssim_score(img_actual: np.ndarray, img_target: np.ndarray) -> float:
    """SSIM(target, rendered) ∈ [-1, 1], 1 = идентичны."""
    a = to_float01(img_actual)
    t = to_float01(img_target)
    if a.shape != t.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {t.shape}")
    val = float(ssim(t, a, data_range=1.0))
    logger.debug("ssim: shape=%s, value=%.6f", a.shape, val)
    return val


def ghost_ssim(img_actual: np.ndarray, img_target: np.ndarray) -> float:
    """Ghost-метрика для презентации: 1 − SSIM (0 = идеально)."""
    return 1.0 - ssim_score(img_actual, img_target)


def worst_case_residual(
    rendered_per_history: list[np.ndarray],
    target: np.ndarray,
) -> float:
    """Наихудший residual по множеству предисторий (для G_worst).

    rendered_per_history — список снимков "что получилось после каждой
    тестовой предыстории". target — желаемое целевое изображение.
    """
    if not rendered_per_history:
        raise ValueError("rendered_per_history must be non-empty")
    return max(residual(img, target) for img in rendered_per_history)


def lifetime_proxy_energy_density(
    voltages_per_phase: np.ndarray,
    time_phase_per_phase: np.ndarray,
) -> float:
    """Прокси-метрика износа: Σ V² · TP (energy density, см. INSIGHT I-06).

    Параметры:
        voltages_per_phase: массив напряжений (В) по фазам.
        time_phase_per_phase: длительность каждой фазы (сек).

    Возвращает: суммарную "тепловую нагрузку" (В²·с).
    Жёстким ограничением (charge balance) занимается ``lut.py``.
    """
    v = np.asarray(voltages_per_phase, dtype=np.float64)
    t = np.asarray(time_phase_per_phase, dtype=np.float64)
    if v.shape != t.shape:
        raise ValueError(f"shape mismatch: {v.shape} vs {t.shape}")
    val = float(np.sum(v * v * t))
    logger.debug("lifetime_proxy: %d phases, value=%.6f V²·s", len(v), val)
    return val
