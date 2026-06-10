"""Метрики качества отрисовки EPD по нормированному снимку (гл. 7).

Региональная метрика контраста (среднее «белых» минус «чёрных» по маске цели)
вырождается на мелком контенте из-за субпиксельного рассогласования камеры и
цели. Здесь собран набор alignment-устойчивых метрик; лучшая выбирается
эмпирически (scripts/eval_metrics.py) по монотонности на свипе известного
качества и применимости к мелкому контенту.

Все функции принимают reflectance [0,1] (PANEL_H×PANEL_W); часть~--- ещё и target.
"""
from __future__ import annotations

import numpy as np


def region_contrast(refl: np.ndarray, target: np.ndarray) -> float:
    """Среднее по «белым» минус среднее по «чёрным» пикселям цели (исходная)."""
    w, b = target > 0.5, target < 0.5
    if not (w.any() and b.any()):
        return float("nan")
    return float(refl[w].mean() - refl[b].mean())


def dynamic_range(refl: np.ndarray, lo: float = 5, hi: float = 95) -> float:
    """Перцентильный размах яркости P_hi − P_lo (без привязки к маске)."""
    return float(np.percentile(refl, hi) - np.percentile(refl, lo))


def std_spread(refl: np.ndarray) -> float:
    """СКО яркости — мера разброса (контраста) без выравнивания."""
    return float(refl.std())


def otsu_gap(refl: np.ndarray, bins: int = 64) -> float:
    """Разность средних двух классов при оптимальном (Otsu) пороге.

    Бимодальность гистограммы яркости: насколько разделены «тёмная» и «светлая»
    популяции пикселей. Не зависит от пространственного выравнивания.
    """
    hist, edges = np.histogram(refl, bins=bins, range=(0, 1))
    hist = hist.astype(float)
    centers = (edges[:-1] + edges[1:]) / 2
    total = hist.sum()
    if total == 0:
        return 0.0
    w0 = np.cumsum(hist)
    w1 = total - w0
    mu0 = np.cumsum(hist * centers)
    mu_tot = mu0[-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        m0 = mu0 / w0
        m1 = (mu_tot - mu0) / w1
        var_between = w0 * w1 * (m0 - m1) ** 2
    k = int(np.nanargmax(var_between))
    if w0[k] == 0 or w1[k] == 0:
        return 0.0
    return float(abs(m1[k] - m0[k]))


def gradient_energy(refl: np.ndarray) -> float:
    """Средняя величина градиента — резкость/энергия краёв (мелкий контент)."""
    gy, gx = np.gradient(refl)
    return float(np.sqrt(gx ** 2 + gy ** 2).mean())


def _resize(a: np.ndarray, shape) -> np.ndarray:
    from PIL import Image
    if a.shape == shape:
        return a
    return np.asarray(Image.fromarray((np.clip(a, 0, 1) * 255).astype("uint8")).resize(
        (shape[1], shape[0]), Image.NEAREST), float) / 255


def block_contrast(refl: np.ndarray, target: np.ndarray, block: int = 8) -> float:
    """Region-contrast на огрублённой сетке блоков (устойчив к субпиксельному сдвигу)."""
    t = _resize(target, refl.shape)
    H, W = refl.shape
    hb, wb = H // block, W // block
    rb = refl[:hb * block, :wb * block].reshape(hb, block, wb, block).mean((1, 3))
    tb = t[:hb * block, :wb * block].reshape(hb, block, wb, block).mean((1, 3))
    w, b = tb > 0.5, tb < 0.5
    if not (w.any() and b.any()):
        return float("nan")
    return float(rb[w].mean() - rb[b].mean())


def ncc_aligned(refl: np.ndarray, target: np.ndarray, max_shift: int = 4) -> float:
    """Макс. нормированная кросс-корреляция с целью по сдвигам ±max_shift.

    Снимает субпиксельное/целочисленное рассогласование: ищет лучший сдвиг и
    возвращает корреляцию структуры (1 = идеальное совпадение рисунка).
    """
    t = _resize(target, refl.shape)
    r = refl - refl.mean()
    best = -1.0
    H, W = refl.shape
    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            ts = np.roll(np.roll(t, dy, 0), dx, 1)
            tc = ts - ts.mean()
            denom = np.sqrt((r ** 2).sum() * (tc ** 2).sum())
            if denom > 0:
                best = max(best, float((r * tc).sum() / denom))
    return best


ALL_METRICS = {
    "region": lambda r, t: region_contrast(r, t),
    "dyn_range": lambda r, t: dynamic_range(r),
    "std": lambda r, t: std_spread(r),
    "otsu_gap": lambda r, t: otsu_gap(r),
    "grad": lambda r, t: gradient_energy(r),
    "block8": lambda r, t: block_contrast(r, t, 8),
    "ncc": lambda r, t: ncc_aligned(r, t),
}
