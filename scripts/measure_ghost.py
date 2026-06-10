#!/usr/bin/env python3
"""Измерение ghosting (остаточного изображения) — ось G Парето-фронта.

Ghosting — многокадровый эффект: остаток предыдущего кадра после нового
обновления. Одно-кадровые тесты (с очисткой в белый) его НЕ ловят.

Протокол A→B (на каждый кандидат waveform):
  1. clear→white (заводский полный refresh, один раз);
  2. отрисовать A = ЧЁРНЫЙ (02_bb) кандидатной waveform;
  3. БЕЗ очистки отрисовать B = БЕЛЫЙ (01_ww) той же waveform;
  4. фото: ghost = насколько «белый» B остался тёмным (1 − reflectance).
     0 → идеально стёрло; больше → waveform не справляется со стиранием.

Короткая/дешёвая waveform хуже стирает → выше ghost. Здесь и живёт
компромисс E–G–τ (Теорема 4.1: min E при G ≤ G_max, τ ≤ τ_max).

Запуск:
    python scripts/measure_ghost.py --port /dev/cu.SLAB_USBtoUART \
        --scales 1.0,0.5,0.4,0.33,0.25,0.2,0.15 \
        --camera-url http://192.168.1.101:8080/shot.jpg
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
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
from scripts.test_known_lut import apply_voltage_cfg, load_v3, scale_tp

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]


def white_ghost(photo: Image.Image, cfg: dict) -> float:
    """Ghost = средняя «темнота» панели на кадре, который должен быть белым."""
    gray = np.asarray(photo.convert("L"), dtype=np.float64) / 255.0
    cap = build_capture(gray, panel_bbox=tuple(cfg["panel_bbox"]),
                        white_patch_bbox=tuple(cfg["white_patch_bbox"]),
                        rotate_deg=int(cfg.get("rotate_deg", 0)))
    return float(1.0 - cap.reflectance.mean())   # 0=идеально белый, выше=ghost


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--camera-url", default=None)
    ap.add_argument("--camera", type=int, default=None)
    ap.add_argument("--scales", default="1.0,0.5,0.4,0.33,0.25,0.2,0.15")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--settle", type=float, default=1.5)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = json.loads((REPO / "data" / "bench" / "roi_config.json").read_text())
    full = load_v3()
    black = pack_frame(SCENARIOS["02_bb"]())
    white = pack_frame(SCENARIOS["01_ww"]())
    do_photo = args.camera is not None or args.camera_url

    out_dir = REPO / "data" / "bench" / "ghost"
    photo_dir = out_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    scales = [float(s) for s in args.scales.split(",")]
    rows: list[dict] = []

    with open_bridge(port=args.port) as bridge:
        # B1 reference: A→B заводским быстрым.
        logger.info("=== B1 factory fast: A(чёрный)→B(белый) ===")
        ghs, erase_e = [], []
        for _ in range(args.repeats):
            bridge.init_partial_fast(); bridge.bench_factory(black, mode_byte=REFRESH_FAST_C7)
            time.sleep(args.settle)
            bridge.init_partial_fast(); tr = bridge.bench_factory(white, mode_byte=REFRESH_FAST_C7)
            erase_e.append(tr.energy_mj()); time.sleep(args.settle)
        if do_photo:
            ph = capture_photo(args.camera, args.camera_url)
            ph.save(photo_dir / "B1_fast_ghost.jpg", quality=88)
            ghs.append(white_ghost(ph, cfg))
        rows.append({"name": "B1_fast", "tp_scale": None, "erase_e_mj": statistics.mean(erase_e),
                     "ghost": statistics.mean(ghs) if ghs else None})
        time.sleep(args.settle)

        for k in scales:
            lut159 = scale_tp(full, k); lut153 = bytes(lut159[:153])
            name = f"v3_x{int(round(k*100)):03d}"
            logger.info("=== %s (TP×%.2f): A(чёрный)→B(белый) ===", name, k)
            ghs, erase_e = [], []
            for _ in range(args.repeats):
                bridge.init(); apply_voltage_cfg(bridge, lut159)
                bridge.bench_run(lut153, black, n_repeats=1)
                time.sleep(args.settle)
                bridge.init(); apply_voltage_cfg(bridge, lut159)
                tr = bridge.bench_run(lut153, white, n_repeats=1)
                erase_e.append(tr.energy_mj()); time.sleep(args.settle)
            if do_photo:
                ph = capture_photo(args.camera, args.camera_url)
                ph.save(photo_dir / f"{name}_ghost.jpg", quality=88)
                ghs.append(white_ghost(ph, cfg))
            rows.append({"name": name, "tp_scale": k, "erase_e_mj": statistics.mean(erase_e),
                         "ghost": statistics.mean(ghs) if ghs else None})

        bridge.sleep()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ghost.json").write_text(
        json.dumps({"rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== GHOST A→B (после стирания чёрного в белый) ===")
    print(f"{'name':>10} {'erase_E':>8} {'ghost':>8}  (ghost: 0=идеально стёрло, выше=хуже)")
    for r in rows:
        gh = "   --   " if r["ghost"] is None else f"{r['ghost']:.4f}"
        print(f"{r['name']:>10} {r['erase_e_mj']:>8.3f} {gh:>8}")
    print(f"\nJSON: {out_dir}/ghost.json\nФото: {photo_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
