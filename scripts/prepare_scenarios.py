#!/usr/bin/env python3
"""Сгенерировать 10 тестовых кадров для экспериментальной кампании (гл. 7).

Кадры сохраняются как PNG 122×250 в tests/fixtures/scenarios/ (целевые
изображения для сравнения с фото стенда) и используются bench_protocol.py
как target-кадры для отрисовки на панели.

Запуск:
    python scripts/prepare_scenarios.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from python.frames import PANEL_H, PANEL_W, SCENARIOS

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    out_dir = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, gen in SCENARIOS.items():
        img = gen()
        if img.shape != (PANEL_H, PANEL_W):
            raise RuntimeError(f"{name}: bad shape {img.shape}")
        arr = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        path = out_dir / f"{name}.png"
        Image.fromarray(arr, mode="L").save(path)
        logger.info("saved %s (mean=%.2f)", path.name, img.mean())

    print(f"\n{len(SCENARIOS)} сценариев сохранено в {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
