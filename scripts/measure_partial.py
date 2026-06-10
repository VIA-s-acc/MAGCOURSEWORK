#!/usr/bin/env python3
"""Измерение частичного (безмерцательного) обновления EPD (направление 2).

Требует прошивку FW>=1.03 (опкоды PART_BASE 0x10, BENCH_PARTIAL 0x11).

Протокол: init → part_base(A) → bench_partial(LUT, cfg, B) — partial-refresh
переводит только изменившиеся пиксели из A в B без глобальной вспышки, с
INA-трассой (энергия/латентность). Затем фото кадра B (контраст + ghost).

Базовая waveform partial — из драйвера Waveshare V3 (data/bench/v3_lut.json,
ключ "partial"); далее перебираются масштабы её длительностей для поиска
оптимума частичного обновления.

Запуск:
    python scripts/measure_partial.py --port /dev/cu.SLAB_USBtoUART \
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

from python.bridge import open_bridge
from python.frames import pack_frame
from python.photo_pipeline import build_capture
from python.scenarios_real import clock

from scripts.bench_one import capture_photo

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]


def load_partial():
    d = json.loads((REPO / "data" / "bench" / "v3_lut.json").read_text())["partial"]
    return d  # 159 байт


def scale_partial_tp(full159: list[int], k: float) -> tuple[bytes, bytes]:
    out = list(full159)
    for n in range(12):                       # 12 фаз LUT, блок 7 байт с offset 60
        base = 60 + n * 7
        for off in (0, 1, 3, 4):              # TP_A, TP_B, TP_C, TP_D
            v = out[base + off]
            if v:
                out[base + off] = max(1, min(255, round(v * k)))
    return bytes(out[:153]), bytes(out[153:159])


def _nframes(lut153: bytes) -> int:
    return sum(lut153[60 + n * 7] + lut153[60 + n * 7 + 3] for n in range(12))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--camera-url", default=None)
    ap.add_argument("--camera", type=int, default=None)
    ap.add_argument("--mode", default="0x0F", help="0x22-байт partial: 0x0F/0x0C/0xCF")
    ap.add_argument("--scales", default="1.0,0.7,0.5,0.35", help="масштабы TP partial-LUT")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--settle", type=float, default=1.2)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = json.loads((REPO / "data" / "bench" / "roi_config.json").read_text())
    full = load_partial()
    mode = int(args.mode, 16)
    A = clock("12:00"); B = clock("12:01")
    fA, fB = pack_frame(A), pack_frame(B)
    do_photo = args.camera is not None or args.camera_url
    out_dir = REPO / "data" / "bench" / "partial"; (out_dir / "photos").mkdir(parents=True, exist_ok=True)

    def measure(tag, r):
        ph = capture_photo(args.camera, args.camera_url)
        ph.save(out_dir / "photos" / f"{tag}.jpg", quality=90)
        g = np.asarray(ph.convert("L"), float) / 255
        refl = build_capture(g, panel_bbox=tuple(cfg["panel_bbox"]),
                             white_patch_bbox=tuple(cfg["white_patch_bbox"]),
                             rotate_deg=int(cfg["rotate_deg"])).reflectance
        tB = np.asarray(Image.fromarray((B*255).astype("uint8")).resize(
            (refl.shape[1], refl.shape[0]), Image.NEAREST), float) / 255
        tA = np.asarray(Image.fromarray((A*255).astype("uint8")).resize(
            (refl.shape[1], refl.shape[0]), Image.NEAREST), float) / 255
        contrast = float(refl[tB > 0.5].mean() - refl[tB < 0.5].mean())
        m_ghost = (tA < 0.5) & (tB > 0.5)
        m_clean = (tA > 0.5) & (tB > 0.5)
        ghost = float(refl[m_clean].mean() - refl[m_ghost].mean()) if m_ghost.any() else 0.0
        return contrast, ghost

    rows = []
    with open_bridge(port=args.port) as bridge:
        ver = bridge.ping()
        if ver < 0x0104:
            raise SystemExit(f"Нужна прошивка FW>=1.04, на плате v{ver>>8}.{ver&0xFF:02d}. Перепрошей.")
        for k in [float(s) for s in args.scales.split(",")]:
            lut153, cfg6 = scale_partial_tp(full, k)
            nf = _nframes(lut153)
            logger.info("=== partial TP×%.2f (mode=%#x) ===", k, mode)
            Es, Ts = [], []
            for _ in range(args.repeats):
                bridge.init(); bridge.part_base(fA); time.sleep(args.settle)
                tr = bridge.bench_partial(lut153, cfg6, fB, mode_byte=mode)
                Es.append(tr.energy_mj()); Ts.append(tr.duration_ms/1000.0)
                time.sleep(args.settle)
            con = gh = None
            if do_photo:
                con, gh = measure(f"partial_x{int(k*100):03d}", None)
            rows.append({"scale": k, "n_frames_est": nf, "energy_mj": statistics.mean(Es),
                         "latency_s": statistics.mean(Ts), "contrast": con, "ghost": gh})
            logger.info("  E=%.3f мДж τ=%.3f с contrast=%s ghost=%s",
                        statistics.mean(Es), statistics.mean(Ts),
                        f"{con:.4f}" if con is not None else "--",
                        f"{gh:.4f}" if gh is not None else "--")
        bridge.sleep()

    (out_dir / "partial.json").write_text(json.dumps({"mode": args.mode, "rows": rows},
                                          indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== ЧАСТИЧНОЕ ОБНОВЛЕНИЕ (часы 12:00→12:01) ===")
    print(f"{'TP×':>5} {'E_mj':>7} {'tau_s':>7} {'contrast':>9} {'ghost':>8}")
    for r in rows:
        con = "  --  " if r["contrast"] is None else f"{r['contrast']:.4f}"
        gh = "  --  " if r["ghost"] is None else f"{r['ghost']:.4f}"
        print(f"{r['scale']:>5.2f} {r['energy_mj']:>7.3f} {r['latency_s']:>7.3f} {con:>9} {gh:>8}")
    print("\n  Сравни E с полным обновлением (наш оптимум ~4.2 мДж): partial должен быть НАМНОГО ниже.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
