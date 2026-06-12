#!/usr/bin/env python3
"""Эмпирический выбор метрики качества: монотонность на свипе известного качества.

Считает все метрики (python.quality.ALL_METRICS) на свипе TP halves (крупный) и
checker (мелкий), где истинный порядок качества задаётся числом кадров. Лучшая
метрика — максимально монотонная (|Спирмен|→1) на ОБОИХ наборах, особенно на
мелком checker, где региональная метрика вырождается.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.frames import SCENARIOS
from python.photo_pipeline import build_capture
from python.quality import ALL_METRICS

REPO = Path(__file__).resolve().parents[1]
PH = REPO / "data" / "bench" / "known_lut" / "photos"
# ROI, активный при съёмке этих фото (move#1):
ROI = dict(panel_bbox=(772, 376, 1256, 606), white_patch_bbox=(965, 713, 1180, 923), rotate_deg=270)


def spearman(x, y):
    rx = np.argsort(np.argsort(x)); ry = np.argsort(np.argsort(y))
    rx = rx - rx.mean(); ry = ry - ry.mean()
    d = np.sqrt((rx**2).sum() * (ry**2).sum())
    return float((rx*ry).sum()/d) if d else 0.0


def refl_of(path, roi):
    g = np.asarray(Image.open(path).convert("L"), float) / 255
    return build_capture(g, panel_bbox=roi["panel_bbox"], white_patch_bbox=roi["white_patch_bbox"],
                         rotate_deg=roi["rotate_deg"]).reflectance


def eval_set(name, scenario, scales, roi):
    tgt = SCENARIOS[scenario]()
    avail = []
    for s in scales:
        p = PH / f"v3_x{s:03d}_{scenario}.jpg"
        if p.exists():
            avail.append((s, refl_of(p, roi)))
    if len(avail) < 3:
        print(f"[{name}] мало фото ({len(avail)})"); return {}
    ss = np.array([s for s, _ in avail], float)  # число кадров ∝ scale
    print(f"\n=== {name} ({scenario}), {len(avail)} точек, scales={list(ss.astype(int))} ===")
    res = {}
    for mname, fn in ALL_METRICS.items():
        vals = np.array([fn(r, tgt) for _, r in avail])
        rho = spearman(ss, vals)
        res[mname] = rho
        print(f"  {mname:>10}: ρ(scale)={rho:+.3f}   значения={np.round(vals,3).tolist()}")
    return res


def main():
    rh = eval_set("HALVES (крупный)", "03_halves",
                  [100, 60, 50, 45, 40, 35, 33, 30, 25, 20, 15], ROI)
    rc = eval_set("CHECKER (мелкий)", "04_checker",
                  [100, 50, 40, 33, 25, 20], ROI)
    if rh and rc:
        print("\n=== ИТОГ: |ρ| на обоих наборах (выше = лучше) ===")
        print(f"  {'метрика':>10} {'halves':>8} {'checker':>8} {'min':>8}")
        for m in ALL_METRICS:
            a, b = abs(rh.get(m, 0)), abs(rc.get(m, 0))
            print(f"  {m:>10} {a:>8.3f} {b:>8.3f} {min(a,b):>8.3f}")
        best = max(ALL_METRICS, key=lambda m: min(abs(rh.get(m,0)), abs(rc.get(m,0))))
        print(f"\n  ЛУЧШАЯ (по min|ρ|): {best}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
