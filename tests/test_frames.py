"""Тесты для python/frames.py — упаковка кадров + генераторы сценариев."""

from __future__ import annotations

import numpy as np
import pytest

from python.frames import (
    FRAME_BYTES,
    PANEL_H,
    PANEL_W,
    SCENARIOS,
    pack_frame,
    scn_bb,
    scn_vstripes,
    scn_ww,
)


def test_frame_bytes_constant():
    assert FRAME_BYTES == 4000
    assert PANEL_W == 122 and PANEL_H == 250


def test_pack_all_white_is_0xff():
    data = pack_frame(scn_ww())
    assert len(data) == FRAME_BYTES
    assert set(data) == {0xFF}  # все биты 1 = белый (включая паддинг)


def test_pack_all_black_padding_white():
    data = pack_frame(scn_bb())
    assert len(data) == FRAME_BYTES
    # первые 122 бита строки = 0 (чёрный), последние 6 бит = 1 (паддинг)
    # 122 = 15*8 + 2 → байт 15 = 2 чёрных пикселя + 6 паддинг = 0b00111111 = 0x3F
    row = data[:16]
    assert row[:15] == bytes(15)
    assert row[15] == 0x3F


def test_pack_vstripes_alternates():
    data = pack_frame(scn_vstripes(period=1))
    # period=1 → чередование пикселей 0101... но pixel 0 (x=0): (0//1)%2=0 → чёрный
    # первый байт = 01010101 = 0x55
    assert data[0] == 0x55


def test_pack_rejects_wrong_shape():
    with pytest.raises(ValueError, match="img shape"):
        pack_frame(np.zeros((100, 100)))


def test_all_scenarios_valid_shape_and_range():
    assert len(SCENARIOS) == 10
    for name, gen in SCENARIOS.items():
        img = gen()
        assert img.shape == (PANEL_H, PANEL_W), name
        assert 0.0 <= img.min() <= img.max() <= 1.0, name
        # упаковка не падает
        assert len(pack_frame(img)) == FRAME_BYTES, name


def test_scenarios_are_distinct():
    means = {name: float(gen().mean()) for name, gen in SCENARIOS.items()}
    # ww (≈1) и bb (≈0) — крайние
    assert means["01_ww"] == pytest.approx(1.0)
    assert means["02_bb"] == pytest.approx(0.0)
