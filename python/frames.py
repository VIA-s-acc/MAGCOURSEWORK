"""Генерация тестовых кадров EPD и упаковка в формат RAM SSD1680.

Панель Waveshare 2.13" V4 — 122×250 пикселей (портрет). Чёрно-белый буфер
RAM (команда 0x24): по 16 байт на строку (122 пикселя + 6 бит паддинга),
250 строк = 4000 байт. Бит = 1 → белый, бит = 0 → чёрный (MSB — левый
пиксель строки).

Здесь:
- ``pack_frame`` — (H, W) булев/[0,1] массив → 4000-байтный кадр SSD1680;
- генераторы 10 диагностических и реалистичных сценариев для гл. 7.

Целевые изображения сценариев также сохраняются как PNG (для сравнения
с фотографиями стенда через :mod:`python.photo_pipeline`).
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

PANEL_W = 122   # ширина (пиксели в строке)
PANEL_H = 250   # высота (число строк)
ROW_BYTES = (PANEL_W + 7) // 8   # = 16 (122 → 16 байт, 6 бит паддинга)
FRAME_BYTES = ROW_BYTES * PANEL_H  # = 4000


def pack_frame(img: np.ndarray) -> bytes:
    """Упаковать (PANEL_H, PANEL_W) изображение в 4000-байтный кадр SSD1680.

    Вход: массив [0,1] или булев, где 1 (или True) — белый пиксель.
    Бит RAM = 1 → белый, 0 → чёрный; MSB байта — левый пиксель.
    Паддинг (биты 122..127 каждой строки) заполняется единицами (белый).
    """
    if img.shape != (PANEL_H, PANEL_W):
        raise ValueError(f"img shape must be ({PANEL_H}, {PANEL_W}), got {img.shape}")
    white = (np.asarray(img) >= 0.5)  # True = белый
    # Дополним строки до ROW_BYTES*8 = 128 бит, паддинг = белый (1).
    padded = np.ones((PANEL_H, ROW_BYTES * 8), dtype=bool)
    padded[:, :PANEL_W] = white
    packed = np.packbits(padded, axis=1)  # (H, ROW_BYTES), MSB-first
    data = packed.astype(np.uint8).tobytes()
    assert len(data) == FRAME_BYTES, len(data)
    return data


# ---- Генераторы сценариев (возвращают (H, W) float [0,1], 1=белый) -------


def _blank(value: float) -> np.ndarray:
    return np.full((PANEL_H, PANEL_W), value, dtype=np.float64)


def scn_ww() -> np.ndarray:
    """Полностью белый."""
    return _blank(1.0)


def scn_bb() -> np.ndarray:
    """Полностью чёрный."""
    return _blank(0.0)


def scn_checker(cell: int = 8) -> np.ndarray:
    """Шахматка с клеткой cell×cell пикселей."""
    yy, xx = np.indices((PANEL_H, PANEL_W))
    return (((xx // cell) + (yy // cell)) % 2).astype(np.float64)


def scn_vstripes(period: int = 2) -> np.ndarray:
    """Вертикальные полосы (высокочастотный тест адресации)."""
    xx = np.indices((PANEL_H, PANEL_W))[1]
    return ((xx // period) % 2).astype(np.float64)


def scn_gradient(levels: int = 4) -> np.ndarray:
    """Горизонтальный ступенчатый градиент из levels уровней серого."""
    xx = np.indices((PANEL_H, PANEL_W))[1]
    q = (xx * levels // PANEL_W).clip(0, levels - 1)
    return (q / (levels - 1)).astype(np.float64)


def scn_halves() -> np.ndarray:
    """Верхняя половина белая, нижняя чёрная (крупный переход)."""
    img = _blank(1.0)
    img[PANEL_H // 2:, :] = 0.0
    return img


def scn_frame_box() -> np.ndarray:
    """Чёрная рамка по периметру на белом фоне (геометрия)."""
    img = _blank(1.0)
    t = 6
    img[:t, :] = 0.0; img[-t:, :] = 0.0; img[:, :t] = 0.0; img[:, -t:] = 0.0
    return img


def scn_bars() -> np.ndarray:
    """Столбчатая диаграмма: 5 чёрных столбцов разной высоты на белом."""
    img = _blank(1.0)
    heights = [0.3, 0.6, 0.45, 0.85, 0.55]
    n = len(heights)
    bw = PANEL_W // (2 * n + 1)
    for i, h in enumerate(heights):
        x0 = bw * (2 * i + 1)
        top = int(PANEL_H * (1 - h))
        img[top:PANEL_H - 6, x0:x0 + bw] = 0.0
    return img


def scn_diag() -> np.ndarray:
    """Диагональная линия (line art) на белом фоне."""
    img = _blank(1.0)
    for y in range(PANEL_H):
        x = int(y * (PANEL_W - 1) / (PANEL_H - 1))
        img[y, max(0, x - 1):min(PANEL_W, x + 2)] = 0.0
    return img


def scn_dot_grid(step: int = 24) -> np.ndarray:
    """Регулярная решётка точек (псевдо-текст/иконки) на белом."""
    img = _blank(1.0)
    for y in range(step // 2, PANEL_H, step):
        for x in range(step // 2, PANEL_W, step):
            img[y - 3:y + 4, x - 3:x + 4] = 0.0
    return img


# Упорядоченный тест-набор из 10 сценариев (имя → генератор).
SCENARIOS: dict[str, "callable"] = {
    "01_ww": scn_ww,
    "02_bb": scn_bb,
    "03_halves": scn_halves,
    "04_checker": scn_checker,
    "05_vstripes": scn_vstripes,
    "06_gradient": scn_gradient,
    "07_frame_box": scn_frame_box,
    "08_bars": scn_bars,
    "09_diag": scn_diag,
    "10_dot_grid": scn_dot_grid,
}
