#!/usr/bin/env python3
"""Долговечность/ghosting: циклический тест чёрный↔белый для разных waveform.

DC-несбалансированная waveform (напр. final_hv: клир 6 ≠ драйв 22) копит
остаточный заряд → image retention / выцветание за многие обновления.
Сбалансированная (клир = драйв, ΣV·T≈0) — нет. Тест:

  clear→white → [нарисовать чёрный → нарисовать белый] × K циклов кандидатной
  waveform → нарисовать 03_halves → фото.
Метрики:
  ghost_white = темнота «белого» после цикла чёрный→белый (0=чисто);
  contrast    = контраст halves после K циклов (деградация качества).

Сравниваем: B1(заводский, сбаланс), final_hv(наш, НЕсбаланс), noosc(наш, сбаланс),
drive_lng(наш, сбаланс). Это даёт ось ε-баланса Парето (энергия↔долговечность).

Запуск:
    python scripts/measure_ghost_designs.py --port /dev/cu.SLAB_USBtoUART \
        --cycles 8 --camera-url http://192.168.1.101:8080/shot.jpg
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
from python.frames import SCENARIOS, pack_frame
from python.photo_pipeline import build_capture

from scripts.bench_one import capture_photo
from scripts.probe_phases import n_frames, set_phases
from scripts.test_known_lut import apply_voltage_cfg, load_v3

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]

# (имя, specs|None, balanced?). None specs = заводский B1.
DESIGNS = [
    ("B1_fast",   None, True),
    ("noosc",     [(15, 0, 0), (0, 0, 0), (15, 0, 0), (1, 0, 0)], True),   # сбаланс (15=15)
    ("drive_lng", [(25, 0, 0), (0, 0, 0), (25, 0, 0), (1, 0, 0)], True),   # сбаланс (25=25)
    ("final_hv",  [(6, 0, 0),  (0, 0, 0), (22, 0, 0), (1, 0, 0)], False),  # НЕсбаланс
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--camera-url", default=None)
    ap.add_argument("--camera", type=int, default=None)
    ap.add_argument("--cycles", type=int, default=8)
    ap.add_argument("--settle", type=float, default=1.0)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = json.loads((REPO / "data" / "bench" / "roi_config.json").read_text())
    black = pack_frame(SCENARIOS["02_bb"]())
    white = pack_frame(SCENARIOS["01_ww"]())
    halves_img = SCENARIOS["03_halves"]()
    halves = pack_frame(halves_img)
    full = load_v3()
    do_photo = args.camera is not None or args.camera_url

    out_dir = REPO / "data" / "bench" / "ghost"
    photo_dir = out_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)

    def snap(tag: str):
        ph = capture_photo(args.camera, args.camera_url)
        ph.save(photo_dir / f"{tag}.jpg", quality=88)
        g = np.asarray(ph.convert("L"), float) / 255
        return build_capture(g, panel_bbox=tuple(cfg["panel_bbox"]),
                             white_patch_bbox=tuple(cfg["white_patch_bbox"]),
                             rotate_deg=int(cfg["rotate_deg"])).reflectance

    def draw(bridge, specs, frame):
        if specs is None:                       # B1 заводский
            bridge.init_partial_fast(); bridge.bench_factory(frame, mode_byte=REFRESH_FAST_C7)
        else:
            lut159 = set_phases(full, specs); lut153 = bytes(lut159[:153])
            bridge.init(); apply_voltage_cfg(bridge, lut159)
            bridge.bench_run(lut153, frame, n_repeats=1)

    rows = []
    with open_bridge(port=args.port) as bridge:
        for name, specs, balanced in DESIGNS:
            nf = n_frames(specs) if specs else None
            logger.info("=== %s (balanced=%s, N=%s): %d циклов ===", name, balanced, nf, args.cycles)
            # чистый старт
            bridge.init(); bridge.send_frame(white); bridge.refresh(); time.sleep(args.settle)
            # K циклов чёрный↔белый кандидатной waveform
            for c in range(args.cycles):
                draw(bridge, specs, black); time.sleep(args.settle)
                draw(bridge, specs, white); time.sleep(args.settle)
            ghost_white = None
            if do_photo:
                r = snap(f"{name}_aftercycle_white")
                ghost_white = float(1.0 - r.mean())   # темнота «белого» = ghost
            # контраст halves после циклирования
            draw(bridge, specs, halves); time.sleep(args.settle)
            contrast = None
            if do_photo:
                r = snap(f"{name}_aftercycle_halves")
                t = halves_img
                if t.shape != r.shape:
                    t = np.asarray(Image.fromarray((t*255).astype("uint8")).resize(
                        (r.shape[1], r.shape[0]), Image.NEAREST), float) / 255
                w, b = t > 0.5, t < 0.5
                contrast = float(r[w].mean() - r[b].mean())
            rows.append({"name": name, "balanced": balanced, "n_frames": nf,
                         "ghost_white": ghost_white, "contrast_after": contrast})
            logger.info("  -> ghost_white=%s, contrast_after=%s",
                        f"{ghost_white:.4f}" if ghost_white is not None else "--",
                        f"{contrast:.4f}" if contrast is not None else "--")
        bridge.sleep()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ghost_designs.json").write_text(
        json.dumps({"cycles": args.cycles, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8")

    print(f"\n=== GHOST/ДОЛГОВЕЧНОСТЬ ({args.cycles} циклов чёрный↔белый) ===")
    print(f"{'name':>11} {'balanced':>9} {'ghost_white':>12} {'contrast_after':>15}")
    for r in rows:
        gw = "  --  " if r["ghost_white"] is None else f"{r['ghost_white']:.4f}"
        ca = "  --  " if r["contrast_after"] is None else f"{r['contrast_after']:.4f}"
        print(f"{r['name']:>11} {str(r['balanced']):>9} {gw:>12} {ca:>15}")
    print("\n  ghost_white: 0=идеально чисто; выше=остаточное изображение (DC-накопление).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
