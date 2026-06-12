#!/usr/bin/env python3
"""Аппаратный свип bang-bang waveform: измерить E/τ/peak/ghost на железе.

Мотивация (см. главу 7): суррогатная per-pixel модель E=½CV²fT плохо
предсказывает АБСОЛЮТНУЮ энергию полной панели и период кадра при кастомной
LUT. Поэтому оптимум выбираем не по модели, а по измерению: PMP даёт
СТРУКТУРУ (bang-bang, K_eff≤4, |ΣV·T|≈0), внутри которой мы перебираем
небольшой набор кандидатов и меряем реальные E/τ/peak/ghost.

Каждый кандидат — заряд-сбалансированная waveform (ΣV·T=0). Прогон через
BENCH_RUN (0x22=0xC7, наша LUT в 0x32). Для сравнения первым меряется
заводский быстрый режим B1.

Результаты → data/bench/probe/timing.{json,csv} + фото.

Запуск:
    python scripts/probe_timing.py --port /dev/cu.SLAB_USBtoUART \
        --scenario 02_bb --camera-url http://192.168.1.101:8080/shot.jpg
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
from python.lut import Lut

from scripts.bench_one import capture_photo, compute_ghost

_WHITE_FRAME = pack_frame(SCENARIOS["01_ww"]())


def clear_to_white(bridge: EpdBridge) -> None:
    """Очистить панель в чистый белый заводским полным refresh (0xF7).

    Гарантирует одинаковое стартовое состояние перед каждым кандидатом →
    все измерения = честный переход белый→цель (а не цель→цель с накоплением
    ghosting). Энергия очистки в измерение кандидата НЕ входит.
    """
    bridge.init()
    bridge.send_frame(_WHITE_FRAME)
    bridge.refresh()  # 0x22=0xF7 + Master Activation + wait BUSY

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]

# Кандидаты: (имя, voltages [В], durations [кадры]).
# ВАЖНО: для РЕНДЕРИНГА пикселя нужен ЧИСТЫЙ заряд ∫V·dt ≠ 0 (смещение
# частицы ∝ импульсу поля). Заряд-сбалансированные waveform (ΣV·T=0) дают
# нулевое чистое смещение → пиксель не двигается. Поэтому свип здесь —
# по net-charged waveform: определяем (а) полярность, чернящую панель,
# (б) минимальный импульс для полного перехода белый→чёрный (02_bb).
# DC-баланс восстанавливается на уровне ЦИКЛА W↔B↔W (обратный переход несёт
# противоположный заряд), а не внутри одного обновления.
# Доступные рельсы источников: {VCOM 0, VSH1 +15, VSL −15, VSH2 +5} — отрицательного
# «слабого» рельса (−5 В) нет, поэтому амплитуду драйва варьируем длительностью.
CANDIDATES: list[tuple[str, tuple[float, ...], tuple[int, ...]]] = [
    ("neg_10",   (-15.0,),         (10,)),   # чистый −150 В·кадр
    ("neg_6",    (-15.0,),         (6,)),
    ("neg_3",    (-15.0,),         (3,)),    # слабый импульс (короткий драйв)
    ("pos_10",   (15.0,),          (10,)),   # чистый +150 — проверка полярности
    ("pos_6",    (15.0,),          (6,)),
    ("bias_neg", (-15.0, 5.0),     (8, 4)),  # net −100, с коротким обратным «хвостом»
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--scenario", default="02_bb", help="сценарий (по умолч. 02_bb — белый→чёрный)")
    ap.add_argument("--camera-url", default=None)
    ap.add_argument("--camera", type=int, default=None)
    ap.add_argument("--settle", type=float, default=1.5)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.scenario not in SCENARIOS:
        raise SystemExit(f"Неизвестный сценарий {args.scenario!r}")
    scenario_img = SCENARIOS[args.scenario]()
    frame = pack_frame(scenario_img)
    do_photo = args.camera is not None or args.camera_url

    out_dir = REPO / "data" / "bench" / "probe"
    photo_dir = out_dir / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []

    def measure_ghost(tag: str) -> dict | None:
        if not do_photo:
            return None
        try:
            photo = capture_photo(args.camera, args.camera_url)
            photo.save(photo_dir / f"{tag}_{args.scenario}.jpg", quality=88)
            return compute_ghost(photo, scenario_img)
        except Exception as exc:  # noqa: BLE001
            logger.warning("фото %s не снято: %s", tag, exc)
            return None

    with open_bridge(port=args.port) as bridge:
        # Референс: заводский быстрый (B1). Старт из чистого белого.
        logger.info("=== B1 (factory fast) === (очистка в белый)")
        clear_to_white(bridge)
        time.sleep(args.settle)
        bridge.init_partial_fast()
        tr = bridge.bench_factory(frame, mode_byte=REFRESH_FAST_C7)
        g = measure_ghost("B1_fast")
        rows.append({
            "name": "B1_fast", "voltages": None, "durations": None, "n_frames": None,
            "energy_mj": tr.energy_mj(), "latency_s": tr.duration_ms / 1000.0,
            "peak_ma": tr.peak_current_ma(), "n_samples": len(tr),
            "ssim": g["ssim"] if g else None, "residual": g["residual"] if g else None,
        })
        time.sleep(args.settle)

        # Кандидаты-bang-bang через BENCH_RUN.
        for name, volts, durs in CANDIDATES:
            lut = Lut.from_waveform(volts, durs)
            cb = lut.charge_balance()
            logger.info("=== %s: V=%s T=%s (Σframes=%d, charge=%.2e) === (очистка в белый)",
                        name, volts, durs, sum(durs), cb)
            clear_to_white(bridge)
            time.sleep(args.settle)
            bridge.init()
            tr = bridge.bench_run(lut.encode(), frame, n_repeats=1)
            g = measure_ghost(name)
            rows.append({
                "name": name, "voltages": list(volts), "durations": list(durs),
                "n_frames": sum(durs), "charge_vs": cb,
                "energy_mj": tr.energy_mj(), "latency_s": tr.duration_ms / 1000.0,
                "peak_ma": tr.peak_current_ma(), "n_samples": len(tr),
                "ssim": g["ssim"] if g else None, "residual": g["residual"] if g else None,
            })
            time.sleep(args.settle)

        bridge.sleep()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "timing.json").write_text(
        json.dumps({"scenario": args.scenario, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    cols = ["name", "n_frames", "energy_mj", "latency_s", "peak_ma", "ssim", "residual"]
    lines = [",".join(cols)]
    for r in rows:
        lines.append(",".join(
            "" if r.get(c) is None else (f"{r[c]:.4f}" if isinstance(r[c], float) else str(r[c]))
            for c in cols))
    (out_dir / "timing.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n=== СВИП waveform (сценарий {args.scenario}) ===")
    print(f"{'name':>10} {'frames':>6} {'E_mj':>8} {'tau_s':>7} {'peak_mA':>8} "
          f"{'SSIM':>7} {'resid':>7}")
    for r in rows:
        ssim = "  --  " if r["ssim"] is None else f"{r['ssim']:.4f}"
        resid = "  --  " if r["residual"] is None else f"{r['residual']:.4f}"
        nf = "  -" if r["n_frames"] is None else str(r["n_frames"])
        print(f"{r['name']:>10} {nf:>6} {r['energy_mj']:>8.3f} {r['latency_s']:>7.3f} "
              f"{r['peak_ma']:>8.2f} {ssim:>7} {resid:>7}")
    print("\n  Прим.: для сплошных сценариев (bb/ww) SSIM вырожден → смотри residual.")
    print(f"\nJSON: {out_dir/'timing.json'}\nCSV:  {out_dir/'timing.csv'}\nФото: {photo_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
