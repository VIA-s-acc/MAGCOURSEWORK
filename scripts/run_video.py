#!/usr/bin/env python3
"""Видео-последовательность под разными политиками обновления (гл. 7, направление 2).

Требует FW>=1.05 (PART_BASE, BENCH_PARTIAL, WRITE_OLD).

Проигрывает N кадров синтетической анимации и для каждой политики измеряет
по кадрам энергию (INA), контраст (otsu_gap) и накопление ghosting:
  full        — каждый кадр заводским полным (B0, 0xF7): дорого, без накопления;
  fac_partial — заводский partial (V3 partial-LUT), последовательно;
  our_partial — наш укороченный partial (TP×scale);
  adaptive    — наш partial, при накоплении ghost>порога → наш экономный полный
                сброс (Tc=4,Td=22), затем снова partial.

Ghosting по кадру: «загрязнение фона» = насколько потемнели пиксели, ставшие
фоном (были тёмными в пред. кадре, стали белыми в текущем) относительно чистого фона.

Запуск:
    python scripts/run_video.py --port /dev/cu.SLAB_USBtoUART \
        --camera-url http://192.168.1.101:8080/shot.jpg --frames 20
"""
from __future__ import annotations

import argparse, json, logging, sys, time
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.bridge import REFRESH_FULL_F7, open_bridge
from python.frames import pack_frame
from python.photo_pipeline import build_capture
from python.quality import otsu_gap
from python.video_scenes import SCENES
from scripts.bench_one import capture_photo
from scripts.test_known_lut import apply_voltage_cfg, load_v3
from scripts.probe_phases import set_phases
from scripts.measure_partial import scale_partial_tp, load_partial

REPO = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)
OUR_FULL = [(4, 0, 0), (0, 0, 0), (22, 0, 0), (1, 0, 0)]   # наш экономный полный сброс


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--camera-url", default=None); ap.add_argument("--camera", type=int, default=None)
    ap.add_argument("--scene", default="julia"); ap.add_argument("--frames", type=int, default=20)
    ap.add_argument("--policies", nargs="+", default=["full", "fac_partial", "our_partial", "adaptive"])
    ap.add_argument("--our-scale", type=float, default=0.5)
    ap.add_argument("--ghost-thresh", type=float, default=0.06)
    ap.add_argument("--settle", type=float, default=0.8)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = json.loads((REPO/"data"/"bench"/"roi_config.json").read_text())
    frames = SCENES[args.scene](args.frames)
    packed = [pack_frame(f) for f in frames]
    partial159 = load_partial()          # V3 partial-LUT (для partial-политик)
    fac_lut, fac_cfg = scale_partial_tp(partial159, 1.0)        # заводский partial
    our_lut, our_cfg = scale_partial_tp(partial159, args.our_scale)  # наш укороченный partial
    our_full159 = set_phases(load_v3(), OUR_FULL); our_full_lut = bytes(our_full159[:153])  # наш полный сброс
    do_photo = args.camera is not None or args.camera_url
    out = REPO/"data"/"bench"/"video"; (out/"photos").mkdir(parents=True, exist_ok=True)

    def refl():
        ph = capture_photo(args.camera, args.camera_url)
        g = np.asarray(ph.convert("L"), float)/255
        return build_capture(g, panel_bbox=tuple(cfg["panel_bbox"]),
                             white_patch_bbox=tuple(cfg["white_patch_bbox"]),
                             rotate_deg=int(cfg["rotate_deg"])).reflectance, ph

    def metrics(r, k):
        t = np.asarray(Image.fromarray((frames[k]*255).astype("uint8")).resize(
            (r.shape[1], r.shape[0]), Image.NEAREST), float)/255
        tp = np.asarray(Image.fromarray((frames[k-1]*255).astype("uint8")).resize(
            (r.shape[1], r.shape[0]), Image.NEAREST), float)/255 if k > 0 else t
        clean = (tp > .5) & (t > .5); erased = (tp < .5) & (t > .5)
        ghost = float(r[clean].mean() - r[erased].mean()) if erased.any() else 0.0
        bg = float(r[t > .5].mean())            # яркость фона (падает при накоплении ghost)
        return otsu_gap(r), ghost, bg

    results = {}
    with open_bridge(port=args.port) as br:
        if br.ping() < 0x0105:
            raise SystemExit("Нужна FW>=1.05, перепрошей.")
        for pol in args.policies:
            logger.info("===== ПОЛИТИКА %s =====", pol)
            # старт: чистая база = кадр 0 полным заводским
            br.init(); br.part_base(packed[0]); time.sleep(args.settle)
            rows = []; n_resets = 0
            bg_ref = None        # яркость фона сразу после последнего полного сброса
            for k in range(1, args.frames):
                did_reset = False
                # drift фона относительно последнего чистого сброса = накопленный ghost
                drift = (bg_ref - rows[-1]["bg"]) if (bg_ref is not None and rows and rows[-1]["bg"]) else 0.0
                if pol == "full":
                    br.init(); tr = br.bench_factory(packed[k], mode_byte=REFRESH_FULL_F7)
                elif pol in ("fac_partial", "our_partial"):
                    lut, c6 = (fac_lut, fac_cfg) if pol == "fac_partial" else (our_lut, our_cfg)
                    br.write_old(packed[k-1])
                    tr = br.bench_partial(lut, c6, packed[k], mode_byte=0x0F)
                else:  # adaptive: накопился ghost (фон потемнел) → наш экономный полный сброс
                    if drift > args.ghost_thresh:
                        br.init(); apply_voltage_cfg(br, our_full159)
                        tr = br.bench_run(our_full_lut, packed[k], n_repeats=1)
                        br.write_old(packed[k]); n_resets += 1; did_reset = True
                    else:
                        br.write_old(packed[k-1])
                        tr = br.bench_partial(our_lut, our_cfg, packed[k], mode_byte=0x0F)
                E = tr.energy_mj()
                o = g = bg = None
                if do_photo:
                    r, ph = refl(); o, g, bg = metrics(r, k)
                    if k % 5 == 0:
                        ph.save(out/"photos"/f"{pol}_f{k:02d}.jpg", quality=88)
                    if bg_ref is None or did_reset:
                        bg_ref = bg   # обновляем baseline фона при старте/сбросе
                rows.append({"k": k, "E_mj": E, "tau_s": tr.duration_ms/1000.0,
                             "otsu": o, "ghost": g, "bg": bg, "drift": drift, "reset": did_reset})
                time.sleep(args.settle)
            tot = sum(r["E_mj"] for r in rows)
            results[pol] = {"rows": rows, "total_E_mj": tot, "n_resets": n_resets}
            logger.info("  Σ энергии=%.1f мДж, сбросов=%d", tot, n_resets)
        br.sleep()

    (out/f"video_{args.scene}.json").write_text(json.dumps({"scene": args.scene,
        "frames": args.frames, "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n=== ВИДЕО {args.scene}, {args.frames} кадров ===")
    print(f"{'политика':>12} {'ΣE,мДж':>8} {'E/кадр':>7} {'otsu_ср':>8} {'ghost_max':>9} {'сбросов':>7}")
    for pol, d in results.items():
        os_ = [r['otsu'] for r in d['rows'] if r['otsu'] is not None]
        gs = [r['ghost'] for r in d['rows'] if r['ghost'] is not None]
        om = np.mean(os_) if os_ else float('nan'); gm = max(gs) if gs else float('nan')
        print(f"{pol:>12} {d['total_E_mj']:>8.1f} {d['total_E_mj']/(args.frames-1):>7.2f} "
              f"{om:>8.3f} {gm:>9.3f} {d['n_resets']:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
