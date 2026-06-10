#!/usr/bin/env python3
"""Decisive-тест: рендерит ли КАСТОМНЫЙ LUT с полной настройкой напряжений.

Берёт заведомо рабочий LUT SSD1680 2.13" из драйвера Waveshare V3
(data/bench/v3_lut.json: 159 байт = 153 LUT + 0x3F/0x03/0x04/0x2C) и
прогоняет его через наш мост, ПРАВИЛЬНО задавая регистры напряжений
(0x04 VSH/VSL, 0x2C VCOM, 0x03 gate, 0x3F) перед обновлением — то, чего
не делал прежний путь. Если панель отрисует контент → кастомный LUT
работает, и наш генератор просто слал неполную конфигурацию.

Заодно — превью оптимизации: масштабирует длительности фаз (TP) вниз,
сохраняя структуру/напряжения, и меряет E/τ/ghost. Так находим, насколько
можно укоротить рабочую waveform без потери качества (реальный оптимум,
выбранный по железу, на якоре известного-рабочего LUT).

Перепрошивка НЕ нужна (используются опкоды write_register + bench_run).

Запуск:
    python scripts/test_known_lut.py --port /dev/cu.SLAB_USBtoUART \
        --scenario 04_checker --camera-url http://192.168.1.101:8080/shot.jpg
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.bridge import REFRESH_FAST_C7, EpdBridge, open_bridge
from python.frames import SCENARIOS, pack_frame

from scripts.bench_one import capture_photo, compute_ghost

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]

# Смещения TP-байтов внутри 7-байтного блока фазы (TP_A,TP_B,SR,TP_C,TP_D,SR,RP).
_TP_OFFSETS = (0, 1, 3, 4)


def load_v3() -> list[int]:
    data = json.loads((REPO / "data" / "bench" / "v3_lut.json").read_text())
    full = data["full"]
    assert len(full) == 159, len(full)
    return full


def scale_tp(full159: list[int], k: float) -> list[int]:
    """Масштабировать длительности фаз (TP) на k, сохраняя структуру/напряжения."""
    out = list(full159)
    for n in range(12):                       # 12 фаз, блок по 7 байт с offset 60
        base = 60 + n * 7
        for off in _TP_OFFSETS:
            v = out[base + off]
            if v:
                out[base + off] = max(1, min(255, round(v * k)))
    return out


def apply_voltage_cfg(bridge: EpdBridge, full159: list[int]) -> None:
    """Задать регистры напряжений из хвоста LUT (как SetLut драйвера V3)."""
    bridge.write_register(0x3F, bytes([full159[153]]))
    bridge.write_register(0x03, bytes([full159[154]]))                       # gate
    bridge.write_register(0x04, bytes([full159[155], full159[156], full159[157]]))  # VSH1/VSH2/VSL
    bridge.write_register(0x2C, bytes([full159[158]]))                       # VCOM


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--scenario", default="04_checker")
    ap.add_argument("--camera-url", default=None)
    ap.add_argument("--camera", type=int, default=None)
    ap.add_argument("--settle", type=float, default=1.5)
    ap.add_argument("--scales", default="1.0,0.6,0.5,0.45,0.4,0.35",
                    help="список масштабов TP через запятую")
    ap.add_argument("--repeats", type=int, default=1, help="повторов на вариант (для std)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.scenario not in SCENARIOS:
        raise SystemExit(f"Неизвестный сценарий {args.scenario!r}")
    scenario_img = SCENARIOS[args.scenario]()
    frame = pack_frame(scenario_img)
    white = pack_frame(SCENARIOS["01_ww"]())
    do_photo = args.camera is not None or args.camera_url

    full = load_v3()
    # Варианты: масштабы TP из CLI (имя = x<процент>).
    scales = [float(s) for s in args.scales.split(",")]
    variants = [(f"v3_x{int(round(k*100)):03d}", k) for k in scales]

    out_dir = REPO / "data" / "bench" / "known_lut"
    photo_dir = out_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    def ghost(tag: str) -> dict | None:
        if not do_photo:
            return None
        try:
            import numpy as np  # noqa: PLC0415
            from python.photo_pipeline import build_capture  # noqa: PLC0415
            cfg = json.loads((REPO / "data" / "bench" / "roi_config.json").read_text())
            ph = capture_photo(args.camera, args.camera_url)
            ph.save(photo_dir / f"{tag}_{args.scenario}.jpg", quality=88)
            gray = np.asarray(ph.convert("L"), dtype=np.float64) / 255.0
            cap = build_capture(gray, panel_bbox=tuple(cfg["panel_bbox"]),
                                white_patch_bbox=tuple(cfg["white_patch_bbox"]),
                                rotate_deg=int(cfg.get("rotate_deg", 0)))
            res = cap.reflectance
            # Контраст: средняя яркость «белых» пикселей цели минус «чёрных».
            tgt = scenario_img
            if tgt.shape != res.shape:
                from PIL import Image  # noqa: PLC0415
                tgt = np.asarray(Image.fromarray((tgt*255).astype("uint8")).resize(
                    (res.shape[1], res.shape[0]), Image.NEAREST), dtype=np.float64) / 255.0
            wmask, bmask = tgt > 0.5, tgt < 0.5
            contrast = (float(res[wmask].mean()) - float(res[bmask].mean())
                        if wmask.any() and bmask.any() else float("nan"))
            d = compute_ghost(ph, scenario_img)
            d["contrast"] = contrast
            d["black_level"] = float(res[bmask].mean()) if bmask.any() else float("nan")
            return d
        except Exception as exc:  # noqa: BLE001
            logger.warning("фото %s: %s", tag, exc)
            return None

    with open_bridge(port=args.port) as bridge:
        # B1 reference (заводский fast).
        logger.info("=== B1 factory fast (reference) ===")
        bridge.init(); bridge.send_frame(white); bridge.refresh()  # clear→white
        time.sleep(args.settle)
        bridge.init_partial_fast()
        tr = bridge.bench_factory(frame, mode_byte=REFRESH_FAST_C7)
        g = ghost("B1_fast")
        rows.append({"name": "B1_fast", "tp_scale": None, "energy_mj": tr.energy_mj(),
                     "energy_std": 0.0, "latency_s": tr.duration_ms/1000.0,
                     "peak_ma": tr.peak_current_ma(),
                     "residual": g["residual"] if g else None,
                     "contrast": g["contrast"] if g else None})
        time.sleep(args.settle)

        import statistics
        for name, k in variants:
            lut159 = scale_tp(full, k)
            lut153 = bytes(lut159[:153])
            tp_a = [lut159[60 + n*7] for n in range(4)]
            logger.info("=== %s (TP×%.2f, фазы TP_A=%s) × %d ===", name, k, tp_a, args.repeats)
            energies, lats, peaks = [], [], []
            g = None
            for rep in range(args.repeats):
                # Чистый старт из белого заводским полным refresh.
                bridge.init(); bridge.send_frame(white); bridge.refresh()
                time.sleep(args.settle)
                # Init + ПОЛНАЯ настройка напряжений + кастомный LUT через bench_run.
                bridge.init()
                apply_voltage_cfg(bridge, lut159)
                tr = bridge.bench_run(lut153, frame, n_repeats=1)
                energies.append(tr.energy_mj()); lats.append(tr.duration_ms/1000.0)
                peaks.append(tr.peak_current_ma())
                if rep == 0:
                    g = ghost(name)   # фото один раз (картинка одинакова)
                time.sleep(args.settle)
            rows.append({
                "name": name, "tp_scale": k, "tp_a": tp_a, "n": len(energies),
                "energy_mj": statistics.mean(energies),
                "energy_std": statistics.pstdev(energies) if len(energies) > 1 else 0.0,
                "latency_s": statistics.mean(lats), "peak_ma": statistics.mean(peaks),
                "residual": g["residual"] if g else None,
                "contrast": g["contrast"] if g else None})

        bridge.sleep()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"results_{args.scenario}.json").write_text(
        json.dumps({"scenario": args.scenario, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8")

    print(f"\n=== KNOWN-LUT тест (сценарий {args.scenario}) ===")
    print(f"{'name':>10} {'E_mj':>8} {'±std':>6} {'tau_s':>7} {'peak_mA':>8} "
          f"{'contrast':>9} {'resid':>7}")
    for r in rows:
        resid = "  --  " if r["residual"] is None else f"{r['residual']:.4f}"
        con = "   --   " if r.get("contrast") is None else f"{r['contrast']:.4f}"
        std = r.get("energy_std", 0.0) or 0.0
        print(f"{r['name']:>10} {r['energy_mj']:>8.3f} {std:>6.3f} {r['latency_s']:>7.3f} "
              f"{r['peak_ma']:>8.2f} {con:>9} {resid:>7}")
    print("\n  contrast = ср.яркость(белые цели) − ср.яркость(чёрные цели); выше = лучше рендер.")
    print("  Ищем минимальный TP×k, где contrast ещё близок к v3_x100 (полному).")
    print(f"\nJSON: {out_dir}/results_{args.scenario}.json\nФото: {photo_dir}")
    print("Если v3_x100 отрисовал checker (SSIM заметно > B1 или чёткая шахматка на фото) →")
    print("кастомный LUT РАБОТАЕТ. Дальше смотрим, до какого TP×k держится качество.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
