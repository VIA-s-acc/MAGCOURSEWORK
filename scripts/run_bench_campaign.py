#!/usr/bin/env python3
"""Полная измерительная кампания для главы 7 (B0..B4 × сценарии × повторы).

Для каждой комбинации (baseline, сценарий) выполняет N повторов измерения
энергии/латентности через INA-трассу и снимает одно фото панели (для
ghosting). Результаты пишутся инкрементально в JSONL (устойчивость к
обрыву), по завершении агрегируются в CSV-сводку и JSON со статистикой
(среднее, медиана, std по каждому baseline×сценарий).

Baseline (см. RESEARCH.md и python/bench_protocol.py):
  B0  Waveshare full   — заводская полная waveform (0xF7)
  B1  Waveshare fast   — заводская быстрая waveform (0xC7)
  B2  Наш оптимум      — LUT из M5 (data/bench/optimal_lut.json), PMP-оптимум
  B3  Content-adaptive — требует пер-контентной оптимизации (см. --include-b3b4)
  B4  Temp+content     — B3 + подмена температуры (0x1A)

По умолчанию измеряются B0,B1,B2 — три ДОСТОВЕРНО различимых режима в
одно-кадровом протоколе. B3/B4 (адаптация по diff кадров и температуре)
осмысленны только для частичных обновлений и включаются явным флагом.

Примеры:
    # быстрая проверка: 1 сценарий, 3 повтора, без фото
    python scripts/run_bench_campaign.py --port /dev/cu.SLAB_USBtoUART \
        --scenarios 01_ww 02_bb 03_halves --repeats 3

    # полная кампания с фото через IP Webcam
    python scripts/run_bench_campaign.py --port /dev/cu.SLAB_USBtoUART \
        --repeats 10 --camera-url http://192.168.1.101:8080/shot.jpg
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path

# Bootstrap: позволяет запуск как `python scripts/run_bench_campaign.py`
# (добавляет корень репозитория в sys.path для импорта python.* и scripts.*).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tqdm import tqdm

from python.bench_protocol import CUSTOM_BASELINES, run_baseline
from python.bridge import open_bridge
from python.frames import SCENARIOS

# Переиспользуем готовые помощники одиночного прогона.
from scripts.bench_one import capture_photo, compute_ghost, default_balanced_lut

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]

DEFAULT_BASELINES = ("B0", "B1", "B2")
B4_TEMP_OVERRIDE = 0x4A  # ≈ +25°C в формате регистра 0x1A (как Waveshare fast-демо)


def load_optimal_lut() -> bytes:
    """LUT «нашего метода» (B2..B4) из data/bench/optimal_lut.json.

    Если файла нет — fallback на зарядо-сбалансированную заглушку с
    предупреждением (но для главы 7 нужен именно оптимум из M5).
    """
    path = REPO / "data" / "bench" / "optimal_lut.json"
    if not path.exists():
        logger.warning("optimal_lut.json не найден — запустите scripts/build_optimal_lut.py. "
                       "Использую default_balanced_lut() (НЕ оптимум M5).")
        return default_balanced_lut()
    data = json.loads(path.read_text(encoding="utf-8"))
    lut = bytes.fromhex(data["lut_hex"])
    logger.info("Оптимальная LUT M5: V=%s T=%s (E_pred=%.4f мДж)",
                data["waveform"]["voltages"], data["waveform"]["durations"],
                data["predicted"]["energy_mj"])
    return lut


def aggregate(rows: list[dict]) -> list[dict]:
    """Свернуть повторы в статистику по (baseline, scenario)."""
    keys: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        keys.setdefault((r["baseline"], r["scenario"]), []).append(r)

    summary = []
    for (bl, sc), group in sorted(keys.items()):
        e = [g["energy_mj"] for g in group]
        t = [g["latency_s"] for g in group]
        p = [g["peak_ma"] for g in group]
        ghosts = [g["ssim"] for g in group if g.get("ssim") is not None]
        row = {
            "baseline": bl, "scenario": sc, "n": len(group),
            "E_mean_mj": statistics.mean(e), "E_median_mj": statistics.median(e),
            "E_std_mj": statistics.pstdev(e) if len(e) > 1 else 0.0,
            "tau_mean_s": statistics.mean(t), "tau_max_s": max(t),
            "peak_mean_ma": statistics.mean(p),
            "ssim_mean": statistics.mean(ghosts) if ghosts else None,
        }
        summary.append(row)
    return summary


def write_csv(summary: list[dict], path: Path) -> None:
    cols = ["baseline", "scenario", "n", "E_mean_mj", "E_median_mj", "E_std_mj",
            "tau_mean_s", "tau_max_s", "peak_mean_ma", "ssim_mean"]
    lines = [",".join(cols)]
    for r in summary:
        vals = []
        for c in cols:
            v = r[c]
            vals.append("" if v is None else (f"{v:.5f}" if isinstance(v, float) else str(v)))
        lines.append(",".join(vals))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True, help="serial-порт ESP32")
    ap.add_argument("--baselines", nargs="+", default=None,
                    help=f"список baseline (по умолчанию {DEFAULT_BASELINES})")
    ap.add_argument("--include-b3b4", action="store_true",
                    help="добавить B3/B4 (содержательны лишь для частичных обновлений)")
    ap.add_argument("--scenarios", nargs="+", default=None,
                    help="список сценариев (по умолчанию все 10)")
    ap.add_argument("--repeats", type=int, default=10, help="повторов на комбинацию")
    ap.add_argument("--camera", type=int, default=None, help="индекс вебкамеры")
    ap.add_argument("--camera-url", default=None, help="URL кадра IP Webcam")
    ap.add_argument("--settle", type=float, default=1.5,
                    help="пауза между прогонами [с] (стабилизация панели)")
    ap.add_argument("--out", default="data/bench/campaign", help="каталог результатов")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.baselines:
        baselines = tuple(args.baselines)
    elif args.include_b3b4:
        baselines = ("B0", "B1", "B2", "B3", "B4")
    else:
        baselines = DEFAULT_BASELINES

    scenarios = args.scenarios or list(SCENARIOS)
    for sc in scenarios:
        if sc not in SCENARIOS:
            raise SystemExit(f"Неизвестный сценарий {sc!r}. Доступны: {list(SCENARIOS)}")

    custom_lut = load_optimal_lut() if any(b in CUSTOM_BASELINES for b in baselines) else None

    out_dir = REPO / args.out
    photo_dir = out_dir / "photos"
    out_dir.mkdir(parents=True, exist_ok=True)
    photo_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "runs.jsonl"
    jsonl_f = jsonl_path.open("w", encoding="utf-8")

    do_photo = args.camera is not None or args.camera_url
    total = len(baselines) * len(scenarios) * args.repeats
    logger.info("Кампания: baseline=%s × сценариев=%d × повторов=%d = %d прогонов; фото=%s",
                baselines, len(scenarios), args.repeats, total, bool(do_photo))

    rows: list[dict] = []
    with open_bridge(port=args.port) as bridge:
        with tqdm(total=total, desc="кампания", unit="run") as pbar:
            for bl in baselines:
                for sc in scenarios:
                    scenario_img = SCENARIOS[sc]()
                    lut = custom_lut if bl in CUSTOM_BASELINES else None
                    temp = B4_TEMP_OVERRIDE if bl == "B4" else None
                    ghost = None
                    for rep in range(args.repeats):
                        res = run_baseline(bridge, sc, scenario_img, bl,
                                           custom_lut=lut, temp_override=temp)
                        row = {
                            "baseline": bl, "scenario": sc, "repeat": rep,
                            "energy_mj": res.energy_mj, "latency_s": res.latency_s,
                            "peak_ma": res.peak_ma, "n_samples": res.n_samples,
                        }
                        # Фото снимаем один раз на комбинацию (после 1-го повтора:
                        # панель уже показывает целевой кадр).
                        if do_photo and rep == 0:
                            try:
                                photo = capture_photo(args.camera, args.camera_url)
                                photo.save(photo_dir / f"{bl}_{sc}.jpg", quality=88)
                                ghost = compute_ghost(photo, scenario_img)
                            except Exception as exc:  # noqa: BLE001
                                logger.warning("фото %s/%s не снято: %s", bl, sc, exc)
                        # SSIM/residual — только в строке с фактическим фото (rep==0),
                        # иначе один замер дублировался бы во все повторы и учитывался
                        # бы N раз при агрегации.
                        if ghost is not None and rep == 0:
                            row.update(ssim=ghost["ssim"], residual=ghost["residual"])
                        rows.append(row)
                        jsonl_f.write(json.dumps(row, ensure_ascii=False) + "\n")
                        jsonl_f.flush()
                        pbar.update(1)
                        pbar.set_postfix(bl=bl, sc=sc, E=f"{res.energy_mj:.1f}")
                        time.sleep(args.settle)
        bridge.sleep()
    jsonl_f.close()

    summary = aggregate(rows)
    write_csv(summary, out_dir / "summary.csv")
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== СВОДКА КАМПАНИИ ===")
    print(f"{'baseline':>8} {'scenario':>12} {'n':>3} {'E_mean':>9} {'tau':>7} {'SSIM':>7}")
    for r in summary:
        ssim = "  --  " if r["ssim_mean"] is None else f"{r['ssim_mean']:.4f}"
        print(f"{r['baseline']:>8} {r['scenario']:>12} {r['n']:>3} "
              f"{r['E_mean_mj']:>9.3f} {r['tau_mean_s']:>7.3f} {ssim:>7}")
    print(f"\nJSONL:   {jsonl_path}")
    print(f"Сводка:  {out_dir/'summary.csv'}")
    print(f"Фото:    {photo_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
