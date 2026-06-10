"""Реалистичные сценарии контента для теста ghosting (гл. 7).

Имитируют типовые применения EPD: электронные часы, онлайн-табло счёта,
страница читалки. Для каждого задаётся ПАРА кадров (A→B) с изменением
содержимого~--- это позволяет измерить остаточное изображение (ghosting)
при переключении, а не только контраст одиночного кадра.

Кадр~--- (PANEL_H, PANEL_W) float [0,1], 1=белый фон, 0=чёрный текст.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from python.frames import PANEL_H, PANEL_W

_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
_MONO = "/System/Library/Fonts/Monaco.ttf"


def _canvas() -> Image.Image:
    return Image.new("L", (PANEL_W, PANEL_H), 255)


def _to_arr(im: Image.Image) -> np.ndarray:
    return np.asarray(im, dtype=np.float64) / 255.0


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _center_text(d: ImageDraw.ImageDraw, xy, text, font, anchor="mm"):
    d.text(xy, text, fill=0, font=font, anchor=anchor)


def clock(hhmm: str = "12:00") -> np.ndarray:
    """Электронные часы: HH сверху, MM снизу (крупные цифры, портрет)."""
    im = _canvas(); d = ImageDraw.Draw(im)
    hh, mm = hhmm.split(":")
    f = _font(_BOLD, 88)
    _center_text(d, (PANEL_W // 2, 70), hh, f)
    _center_text(d, (PANEL_W // 2, 175), mm, f)
    d.line([(20, 122), (PANEL_W - 20, 122)], fill=0, width=2)
    return _to_arr(im)


def scoreboard(score: str = "2-0") -> np.ndarray:
    """Онлайн-табло счёта: команды + крупный счёт."""
    im = _canvas(); d = ImageDraw.Draw(im)
    home, away = score.split("-")
    fs = _font(_BOLD, 96)
    ft = _font(_BOLD, 22)
    _center_text(d, (PANEL_W // 2, 35), "HOME", ft)
    _center_text(d, (PANEL_W // 2, 95), home, fs)
    _center_text(d, (PANEL_W // 2, 160), "GUEST", ft)
    _center_text(d, (PANEL_W // 2, 220), away, fs)
    return _to_arr(im)


def reader(page: int = 1) -> np.ndarray:
    """Страница читалки: строки текста (две разные страницы)."""
    im = _canvas(); d = ImageDraw.Draw(im)
    f = _font(_MONO, 12)
    pages = {
        1: ["Глава 1.", "", "Электрофорез", "управляет", "частицами в", "капсуле под",
            "действием", "поля. Белые", "и чёрные", "пигменты", "движутся к", "электродам,",
            "формируя", "изображение", "на экране."],
        2: ["Глава 2.", "", "Обновление", "дисплея", "требует", "энергии на", "перенос",
            "заряда. Цель", "работы --", "снизить её", "при том же", "качестве",
            "картинки на", "электронной", "бумаге."],
    }
    y = 8
    for line in pages.get(page, pages[1]):
        d.text((8, y), line, fill=0, font=f)
        y += 16
    return _to_arr(im)


# Пары переключения (A, B) для теста ghosting: меняется часть содержимого.
SWITCH_PAIRS = {
    "clock":      (lambda: clock("12:00"), lambda: clock("12:01")),
    "scoreboard": (lambda: scoreboard("2-0"), lambda: scoreboard("2-1")),
    "reader":     (lambda: reader(1), lambda: reader(2)),
}
