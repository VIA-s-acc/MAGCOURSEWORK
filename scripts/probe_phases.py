#!/usr/bin/env python3
"""Эксперимент «нашего метода»: НЕРАВНОМЕРНАЯ раскладка фаз vs равномерный масштаб.

Структура waveform V3 (бистабильная модель): [драйв → осцилляция(RP×) → финальный
драйв → settle]. Осцилляционная фаза 1 (RP=2 → ×3) занимает 74% кадров и энергии,
но нужна лишь для активации/DC-баланса. Равномерный масштаб (test_known_lut) режет
ВСЁ пропорционально. Наш PMP-подход режет ИМЕННО дорогую осцилляцию, сохраняя
финальный драйв → та же контрастность за меньшую энергию.

Каждый вариант сохраняет VS-паттерн и напряжения V3, меняет только TP/RP
активных фаз 0..3. Сравниваем (E, contrast, τ) с равномерной кривой при той же
энергии: если контраст ВЫШЕ при той же E — неравномерная раскладка доминирует.

Запуск:
    python scripts/probe_phases.py --port /dev/cu.SLAB_USBtoUART \
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
from python.frames import SCENARIOS, pack_frame
from python.photo_pipeline import build_capture

from scripts.bench_one import capture_photo
from scripts.test_known_lut import apply_voltage_cfg, load_v3

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]

# Позиции активных фаз в 159-массиве (base=60+n*7): TP_A=+0, TP_C=+3, RP=+6.
_PHASE_BASE = [60 + n * 7 for n in range(4)]


def set_phases(full159: list[int], specs: list[tuple[int, int, int]]) -> list[int]:
    """specs[n] = (tp_a, tp_c, rp) для фазы n=0..3. Прочее обнуляется."""
    out = list(full159)
    for n, (tp_a, tp_c, rp) in enumerate(specs):
        base = _PHASE_BASE[n]
        out[base + 0] = tp_a       # TP_A
        out[base + 1] = 0          # TP_B
        out[base + 3] = tp_c       # TP_C
        out[base + 4] = 0          # TP_D
        out[base + 6] = rp         # RP
    return out


def n_frames(specs: list[tuple[int, int, int]]) -> int:
    return sum((tp_a + tp_c) * (rp + 1) for tp_a, tp_c, rp in specs)


# Дизайны: (имя, [(tp_a,tp_c,rp) фаз 0..3]). V3-структура, варьируем раскладку.
# Фаза0 = драйв(VSL), фаза1 = осцилляция(VSH1+VSL)×(RP+1), фаза2 = финал(VSH1), фаза3 = settle.
DESIGNS: list[tuple[str, list[tuple[int, int, int]]]] = [
    ("full",      [(15, 0, 0), (15, 15, 2), (15, 0, 0), (1, 0, 0)]),  # = V3 (121 кадр)
    ("rp1",       [(15, 0, 0), (15, 15, 1), (15, 0, 0), (1, 0, 0)]),  # осц ×2  (91)
    ("rp0",       [(15, 0, 0), (15, 15, 0), (15, 0, 0), (1, 0, 0)]),  # осц ×1  (61)
    ("rp0_s8",    [(15, 0, 0), (8, 8, 0),   (15, 0, 0), (1, 0, 0)]),  # осц короче (47)
    ("rp0_s4",    [(15, 0, 0), (4, 4, 0),   (15, 0, 0), (1, 0, 0)]),  # осц мин (39)
    ("noosc",     [(15, 0, 0), (0, 0, 0),   (15, 0, 0), (1, 0, 0)]),  # без осц (31)
    ("noosc_s10", [(10, 0, 0), (0, 0, 0),   (10, 0, 0), (1, 0, 0)]),  # без осц, короче (21)
    ("final_hv",  [(6, 0, 0),  (0, 0, 0),   (22, 0, 0), (1, 0, 0)]),  # упор в финал (29)
    ("drive_lng", [(25, 0, 0), (0, 0, 0),   (25, 0, 0), (1, 0, 0)]),  # длинный драйв без осц (51)
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--scenario", default="03_halves")
    ap.add_argument("--camera-url", default=None)
    ap.add_argument("--camera", type=int, default=None)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--settle", type=float, default=1.5)
    ap.add_argument("--designs", default=None,
                    help="JSON-список [[name,[[tp_a,tp_c,rp]×4]], ...] (переопределяет дизайны)")
    args = ap.parse_args()

    global DESIGNS
    if args.designs:
        DESIGNS = [(d[0], [tuple(p) for p in d[1]]) for d in json.loads(args.designs)]

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = json.loads((REPO / "data" / "bench" / "roi_config.json").read_text())
    tgt = SCENARIOS[args.scenario]()
    frame = pack_frame(tgt)
    white = pack_frame(SCENARIOS["01_ww"]())
    full = load_v3()
    do_photo = args.camera is not None or args.camera_url

    out_dir = REPO / "data" / "bench" / "phases"
    photo_dir = out_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)

    def contrast(tag: str) -> float | None:
        if not do_photo:
            return None
        try:
            ph = capture_photo(args.camera, args.camera_url)
            ph.save(photo_dir / f"{tag}_{args.scenario}.jpg", quality=88)
            g = np.asarray(ph.convert("L"), float) / 255
            cap = build_capture(g, panel_bbox=tuple(cfg["panel_bbox"]),
                                white_patch_bbox=tuple(cfg["white_patch_bbox"]),
                                rotate_deg=int(cfg["rotate_deg"]))
            r = cap.reflectance
            t = tgt
            if t.shape != r.shape:
                t = np.asarray(Image.fromarray((t*255).astype("uint8")).resize(
                    (r.shape[1], r.shape[0]), Image.NEAREST), float) / 255
            w, b = t > 0.5, t < 0.5
            return float(r[w].mean() - r[b].mean()) if w.any() and b.any() else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("фото %s: %s", tag, exc)
            return None

    rows: list[dict] = []
    with open_bridge(port=args.port) as bridge:
        for name, specs in DESIGNS:
            lut159 = set_phases(full, specs)
            lut153 = bytes(lut159[:153])
            nf = n_frames(specs)
            logger.info("=== %s: specs=%s (N=%d кадров) ===", name, specs, nf)
            Es = []
            for _ in range(args.repeats):
                bridge.init(); bridge.send_frame(white); bridge.refresh()  # clear→white
                time.sleep(args.settle)
                bridge.init(); apply_voltage_cfg(bridge, lut159)
                tr = bridge.bench_run(lut153, frame, n_repeats=1)
                Es.append(tr.energy_mj()); time.sleep(args.settle)
            con = contrast(name)
            rows.append({"name": name, "specs": specs, "n_frames": nf,
                         "energy_mj": statistics.mean(Es),
                         "energy_std": statistics.pstdev(Es) if len(Es) > 1 else 0.0,
                         "latency_s": tr.duration_ms/1000.0, "contrast": con})
            logger.info("  -> E=%.3f мДж, τ=%.3f с, contrast=%s",
                        statistics.mean(Es), tr.duration_ms/1000.0,
                        f"{con:.4f}" if con is not None else "--")
        bridge.sleep()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"phases_{args.scenario}.json").write_text(
        json.dumps({"scenario": args.scenario, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8")

    print(f"\n=== НЕРАВНОМЕРНАЯ РАСКЛАДКА ({args.scenario}) ===")
    print(f"{'name':>11} {'N':>4} {'E_mj':>7} {'tau_s':>7} {'contrast':>9}")
    for r in rows:
        con = "   --   " if r["contrast"] is None else f"{r['contrast']:.4f}"
        print(f"{r['name']:>11} {r['n_frames']:>4} {r['energy_mj']:>7.3f} "
              f"{r['latency_s']:>7.3f} {con:>9}")
    print("\n  Сравни с равномерной кривой при той же E: выше contrast = наш метод доминирует.")
    print("  Цель — обойти заводской быстрый режим B1 (база в data/bench/final/final.json).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
