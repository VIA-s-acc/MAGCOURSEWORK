#!/usr/bin/env python3
"""Итоговое консистентное сравнение (новый ROI, метрика otsu_gap), сценарий halves.

Меряет заводские B0/B1 и наши waveform одним прогоном с единым ROI и метрикой
качества otsu_gap → таблица и графики главы 7. Энергия/латентность по INA219.
"""
from __future__ import annotations

import argparse, json, logging, statistics, sys, time
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.bridge import REFRESH_FULL_F7, REFRESH_FAST_C7, open_bridge
from python.frames import SCENARIOS, pack_frame
from python.photo_pipeline import build_capture
from python.quality import otsu_gap
from scripts.bench_one import capture_photo
from scripts.test_known_lut import apply_voltage_cfg, load_v3
from scripts.probe_phases import set_phases

REPO = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)

# (имя, вид, параметр). вид: B0/B1 заводские; OUR=(Tc,Td) наш.
DESIGNS = [
    ("B0_факт_полный", "B0", None),
    ("B1_факт_быстрый", "B1", None),
    ("наш_равный",      "OUR", (4, 22)),
    ("наш_ε0_баланс",   "OUR", (15, 15)),
    ("наш_ε-relaxed",   "OUR", (4, 10)),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--camera-url", default=None)
    ap.add_argument("--camera", type=int, default=None)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--settle", type=float, default=1.3)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = json.loads((REPO/"data"/"bench"/"roi_config.json").read_text())
    full = load_v3()
    img = SCENARIOS["03_halves"](); frame = pack_frame(img); white = pack_frame(SCENARIOS["01_ww"]())
    out = REPO/"data"/"bench"/"final"; (out/"photos").mkdir(parents=True, exist_ok=True)

    def otsu(tag):
        ph = capture_photo(args.camera, args.camera_url); ph.save(out/"photos"/f"{tag}.jpg", quality=90)
        g = np.asarray(ph.convert("L"), float)/255
        r = build_capture(g, panel_bbox=tuple(cfg["panel_bbox"]), white_patch_bbox=tuple(cfg["white_patch_bbox"]),
                          rotate_deg=int(cfg["rotate_deg"])).reflectance
        return otsu_gap(r)

    rows = []
    with open_bridge(port=args.port) as br:
        for name, kind, par in DESIGNS:
            logger.info("=== %s ===", name)
            Es, Ts = [], []
            for _ in range(args.repeats):
                br.init(); br.send_frame(white); br.refresh(); time.sleep(args.settle)  # чистый старт
                if kind == "B0":
                    br.init(); tr = br.bench_factory(frame, mode_byte=REFRESH_FULL_F7)
                elif kind == "B1":
                    br.init_partial_fast(); tr = br.bench_factory(frame, mode_byte=REFRESH_FAST_C7)
                else:
                    tc, td = par
                    lut159 = set_phases(full, [(tc,0,0),(0,0,0),(td,0,0),(1,0,0)])
                    br.init(); apply_voltage_cfg(br, lut159)
                    tr = br.bench_run(bytes(lut159[:153]), frame, n_repeats=1)
                Es.append(tr.energy_mj()); Ts.append(tr.duration_ms/1000.0); time.sleep(args.settle)
            c = otsu(name) if (args.camera is not None or args.camera_url) else None
            rows.append({"name": name, "kind": kind, "param": par,
                         "E_mj": statistics.mean(Es), "E_std": statistics.pstdev(Es),
                         "tau_s": statistics.mean(Ts), "otsu": c})
            logger.info("  E=%.3f±%.3f мДж τ=%.3f с otsu=%s", statistics.mean(Es),
                        statistics.pstdev(Es), statistics.mean(Ts), f"{c:.4f}" if c else "--")
        br.sleep()

    (out/"final.json").write_text(json.dumps({"rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    b1 = next(r for r in rows if r["kind"] == "B1")
    print("\n=== ИТОГ (halves, otsu_gap, новый ROI) ===")
    print(f"{'waveform':>16} {'E_mj':>7} {'tau_s':>7} {'otsu':>7} {'ΔE%':>7} {'Δτ%':>7}")
    for r in rows:
        dE = 100*(r["E_mj"]-b1["E_mj"])/b1["E_mj"]; dT = 100*(r["tau_s"]-b1["tau_s"])/b1["tau_s"]
        o = "  --  " if r["otsu"] is None else f"{r['otsu']:.4f}"
        print(f"{r['name']:>16} {r['E_mj']:>7.3f} {r['tau_s']:>7.3f} {o:>7} {dE:>+7.1f} {dT:>+7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
