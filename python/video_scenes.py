"""Синтетические видео-сцены для теста многокадрового обновления (гл. 7).

Генерирует последовательность 1-битных кадров (PANEL_H×PANEL_W, 1=белый):
анимация множества Жюлиа (параметр c движется по окружности). Используется для
сравнения политик обновления (полное / заводский partial / наш partial /
адаптивная) по накоплению ghosting, контрасту и суммарной энергии.
"""
from __future__ import annotations

import numpy as np

from python.frames import PANEL_H, PANEL_W


def julia_frames(n: int = 30, thr: float = 0.5) -> list[np.ndarray]:
    """n кадров анимации Жюлиа, бинаризованных (1=белый фон, 0=чёрный узор)."""
    ys, xs = np.mgrid[0:PANEL_H, 0:PANEL_W]
    # координаты комплексной плоскости (портрет → вытянуто по мнимой оси)
    cx = (xs - PANEL_W / 2) / (PANEL_W / 2) * 1.6
    cy = (ys - PANEL_H / 2) / (PANEL_H / 2) * 1.6
    frames = []
    for k in range(n):
        ang = 2 * np.pi * k / n
        c = 0.7885 * np.exp(1j * (ang * 0.5 + 2.0))   # c по дуге → плавная анимация
        z = cx + 1j * cy
        esc = np.zeros((PANEL_H, PANEL_W), dtype=np.float64)
        zz = z.copy()
        for i in range(24):
            zz = zz * zz + c
            np.clip(zz.real, -1e6, 1e6, out=zz.real)
            np.clip(zz.imag, -1e6, 1e6, out=zz.imag)
            escaped = (np.abs(zz) > 2) & (esc == 0)
            esc[escaped] = i
        esc[esc == 0] = 24
        norm = esc / 24.0
        # белый фон, чёрный узор: «улетающая» область (фон) → белый, множество → чёрный
        img = (norm <= thr).astype(np.float64)   # 1=белый фон, 0=чёрный фрактал
        frames.append(img)
    return frames


def moving_bar_frames(n: int = 30) -> list[np.ndarray]:
    """Простая сцена: чёрная полоса, движущаяся сверху вниз (контролируемое изменение)."""
    frames = []
    bar_h = 40
    for k in range(n):
        img = np.ones((PANEL_H, PANEL_W))
        y0 = int((PANEL_H - bar_h) * k / max(1, n - 1))
        img[y0:y0 + bar_h, :] = 0.0
        frames.append(img)
    return frames


def clock_frames(n: int = 12) -> list[np.ndarray]:
    """Тикающие часы 12:00, 12:01, ... (накопление ghosting при частых обновлениях)."""
    from python.scenarios_real import clock
    return [clock(f"12:{k % 60:02d}") for k in range(n)]


def pong_frames(n: int = 30) -> list[np.ndarray]:
    """Авто-пинг-понг (air-hockey): мяч прыгает, две ракетки сверху/снизу следят за ним.

    Демонстрирует интерактивный сценарий: каждый кадр меняется лишь мяч и ракетки →
    идеально для безмерцательного partial. Частота кадров = FPS panel в этом режиме.
    """
    frames = []
    bx, by = PANEL_W // 2, PANEL_H // 2
    vx, vy = 5, 9
    pw = 34   # ширина ракетки
    bs = 8    # размер мяча
    for _ in range(n):
        img = np.ones((PANEL_H, PANEL_W))
        bx += vx; by += vy
        if bx < bs or bx > PANEL_W - bs: vx = -vx; bx += 2 * vx
        if by < 16 or by > PANEL_H - 16: vy = -vy; by += 2 * vy
        # ракетки следят за мячом по x
        for py in (6, PANEL_H - 12):
            px = int(np.clip(bx - pw // 2, 0, PANEL_W - pw))
            img[py:py + 6, px:px + pw] = 0.0
        img[max(0, by - bs):by + bs, max(0, bx - bs):bx + bs] = 0.0  # мяч
        frames.append(img)
    return frames


SCENES = {
    "julia": julia_frames,
    "bar": moving_bar_frames,
    "clock": clock_frames,
    "pong": pong_frames,
}
