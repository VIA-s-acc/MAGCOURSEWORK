#!/usr/bin/env python3
"""Ghosting на реалистичных сценариях при ПЕРЕКЛЮЧЕНИИ контента (гл. 7).

Для каждого сценария (часы, табло, читалка) и каждой waveform:
  1. clear→white;
  2. отрисовать кадр A;
  3. БЕЗ очистки отрисовать кадр B (смена содержимого);
  4. фото кадра B.
Метрики по фото (ROI-нормировка):
  contrast_B  = яркость(фон B) − яркость(текст B)         — качество нового кадра;
  ghost       = яркость(чистый фон) − яркость(бывший текст A, ставший фоном B)
                — остаточное изображение (0 = нет ghosting).

Сравниваются заводская быстрая (B1) и наш оптимум (Tc=4, Td=22, равный контраст).

Запуск:
    python scripts/measure_scenarios.py --port /dev/cu.SLAB_USBtoUART \
        --camera-url http://192.168.1.101:8080/shot.jpg
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.bridge import REFRESH_FAST_C7, open_bridge
from python.frames import pack_frame
from python.photo_pipeline import build_capture
from python.scenarios_real import SWITCH_PAIRS

from scripts.bench_one import capture_photo
from scripts.test_known_lut import apply_voltage_cfg, load_v3
from scripts.probe_phases import set_phases

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]

OUR_OPT = [(4, 0, 0), (0, 0, 0), (22, 0, 0), (1, 0, 0)]  # Tc=4, Td=22 — равный контраст


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--camera-url", default=None)
    ap.add_argument("--camera", type=int, default=None)
    ap.add_argument("--settle", type=float, default=1.2)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = json.loads((REPO / "data" / "bench" / "roi_config.json").read_text())
    full = load_v3()
    white = pack_frame(np.ones((250, 122)))
    out_dir = REPO / "data" / "bench" / "scenarios"
    photo_dir = out_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)

    def refl(tag: str) -> np.ndarray:
        ph = capture_photo(args.camera, args.camera_url)
        ph.save(photo_dir / f"{tag}.jpg", quality=90)
        g = np.asarray(ph.convert("L"), float) / 255
        return build_capture(g, panel_bbox=tuple(cfg["panel_bbox"]),
                             white_patch_bbox=tuple(cfg["white_patch_bbox"]),
                             rotate_deg=int(cfg["rotate_deg"])).reflectance

    def draw(bridge, wave, frame):
        if wave == "B1":
            bridge.init_partial_fast(); bridge.bench_factory(frame, mode_byte=REFRESH_FAST_C7)
        else:
            lut159 = set_phases(full, OUR_OPT); lut153 = bytes(lut159[:153])
            bridge.init(); apply_voltage_cfg(bridge, lut159)
            bridge.bench_run(lut153, frame, n_repeats=1)

    def to_panel(arr: np.ndarray, shape) -> np.ndarray:
        if arr.shape == shape:
            return arr
        return np.asarray(Image.fromarray((arr*255).astype("uint8")).resize(
            (shape[1], shape[0]), Image.NEAREST), float) / 255

    rows = []
    with open_bridge(port=args.port) as bridge:
        for name, (genA, genB) in SWITCH_PAIRS.items():
            A, B = genA(), genB()
            fA, fB = pack_frame(A), pack_frame(B)
            for wave in ("B1", "OUR"):
                logger.info("=== %s / %s: A→B ===", name, wave)
                bridge.init(); bridge.send_frame(white); bridge.refresh(); time.sleep(args.settle)
                draw(bridge, wave, fA); time.sleep(args.settle)
                draw(bridge, wave, fB); time.sleep(args.settle)
                r = refl(f"{name}_{wave}_B")
                tA, tB = to_panel(A, r.shape), to_panel(B, r.shape)
                m_clean = (tA > 0.5) & (tB > 0.5)         # фон в A и B
                m_ghost = (tA < 0.5) & (tB > 0.5)         # текст A → фон B
                m_textB = tB < 0.5                         # текст нового кадра
                contrast = float(r[tB > 0.5].mean() - r[m_textB].mean())
                ghost = float(r[m_clean].mean() - r[m_ghost].mean()) if m_ghost.any() else 0.0
                rows.append({"scenario": name, "wave": wave,
                             "contrast": contrast, "ghost": ghost})
                logger.info("  contrast=%.4f ghost=%.4f", contrast, ghost)
        bridge.sleep()

    (out_dir / "scenarios.json").write_text(
        json.dumps({"rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== GHOSTING ПЕРЕКЛЮЧЕНИЯ КОНТЕНТА ===")
    print(f"{'сценарий':>12} {'waveform':>9} {'contrast':>9} {'ghost':>8}")
    for r in rows:
        print(f"{r['scenario']:>12} {r['wave']:>9} {r['contrast']:>9.4f} {r['ghost']:>8.4f}")
    print("\n  ghost: 0 = нет остаточного изображения; выше = заметнее след старого кадра.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
