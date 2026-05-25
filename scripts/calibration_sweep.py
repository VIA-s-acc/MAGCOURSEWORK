#!/usr/bin/env python3
"""Калибровочный sweep для оценки параметров Stokes-модели по INA219-трассам.

Запускает на стенде ESP32+SSD1680+INA219 серию single-phase waveform'ов с
разными комбинациями (V_source, TP), снимает INA-трассы и сохраняет в CSV.
Результаты обрабатываются в notebook/01_calibration.ipynb (задача C3 M3).

Протокол:
  Для каждой комбинации (V_source ∈ {VSH1, VSH2}, TP ∈ TP_LIST):
    1. Подготовить single-phase LUT (фаза 0 = (V, TP, 4 sub-frame'а), остальные = VCOM/0).
    2. Залить frame_buffer указанным шаблоном (по умолчанию — белый = 0xFF).
    3. BENCH_RUN(LUT, frame, n_repeats) — даст трассу (t_us, i_mA, p_mW).
    4. Записать в CSV строки `session_id, run_idx, V_name, TP, repeat, t_us, i_mA, p_mW`.
    5. SLEEP опкодом 0x04, пауза 0.5 с перед следующим измерением (чтобы панель
       не перегревалась).

Использование:
    python scripts/calibration_sweep.py \\
        --port /dev/cu.SLAB_USBtoUART \\
        --output data/calibration/sweep_$(date +%Y%m%d_%H%M).csv \\
        --tp-list 5,10,20,50 \\
        --n-repeats 10 \\
        --frame-pattern white
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from python.bridge import open_bridge
from python.ina219 import Trace
from python.lut import N_SUB_FRAMES, Lut, Source

logger = logging.getLogger(__name__)

# VSH1 — типично +15В; VSH2 — типично +5В (промежуточный grey level).
# Отрицательный уровень (VSL) симметричен → не обязательно мерить отдельно.
DEFAULT_V_SOURCES: list[tuple[str, int]] = [
    ("VSH1", Source.VSH1.value),
    ("VSH2", Source.VSH2.value),
]
DEFAULT_TP_LIST: list[int] = [5, 10, 20, 50]


def make_single_phase_lut(v_source: int, tp: int) -> bytes:
    """Сделать LUT с одной активной фазой 0 на всех 5 sub-LUT × 4 sub-frame."""
    lut = Lut.zeros()
    for m in range(5):
        for sub in range(N_SUB_FRAMES):
            lut.vs[m, 0, sub] = v_source
    lut.tp[0, :] = tp
    return lut.encode()


def make_test_frame(pattern: str) -> bytes:
    """Сгенерировать 4000-байтный frame buffer."""
    if pattern == "white":
        return b"\xFF" * 4000
    if pattern == "black":
        return b"\x00" * 4000
    if pattern == "checkerboard":
        return b"\x55\xAA" * 2000
    raise ValueError(f"Unknown pattern: {pattern!r}")


def trace_to_rows(
    trace: Trace,
    *,
    session_id: str,
    run_idx: int,
    v_name: str,
    v_code: int,
    tp: int,
    n_repeats: int,
) -> list[dict]:
    """Развернуть Trace в список CSV-строк."""
    rows: list[dict] = []
    for i in range(len(trace)):
        rows.append({
            "session_id": session_id,
            "run_idx": run_idx,
            "V_name": v_name,
            "V_code": v_code,
            "TP": tp,
            "n_repeats": n_repeats,
            "sample_idx": i,
            "t_us": int(trace.t_us[i]),
            "i_mA": float(trace.i_a[i] * 1e3),
            "p_mW": float(trace.p_w[i] * 1e3),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Калибровочный sweep EPD-стенда")
    parser.add_argument("--port", default="/dev/cu.SLAB_USBtoUART")
    parser.add_argument("--output", required=True,
                        help="Путь к выходному CSV (директория будет создана)")
    parser.add_argument("--tp-list", default=",".join(str(x) for x in DEFAULT_TP_LIST))
    parser.add_argument("--n-repeats", type=int, default=10)
    parser.add_argument("--frame-pattern", default="white",
                        choices=["white", "black", "checkerboard"])
    parser.add_argument("--settle-s", type=float, default=0.5)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = output_path.with_suffix(".meta.json")

    tp_list = [int(x.strip()) for x in args.tp_list.split(",")]
    sources = DEFAULT_V_SOURCES
    total_runs = len(sources) * len(tp_list)
    session_id = datetime.now().strftime("%Y%m%dT%H%M%S")

    logger.info(
        "Sweep config: %d runs (sources=%s × TPs=%s × n_repeats=%d), pattern=%s",
        total_runs, [s[0] for s in sources], tp_list, args.n_repeats, args.frame_pattern,
    )

    meta = {
        "session_id": session_id,
        "started_at": datetime.now().isoformat(),
        "port": args.port,
        "sources": [{"name": n, "code": c} for n, c in sources],
        "tp_list": tp_list,
        "n_repeats": args.n_repeats,
        "frame_pattern": args.frame_pattern,
        "total_runs": total_runs,
    }
    frame = make_test_frame(args.frame_pattern)

    fieldnames = [
        "session_id", "run_idx", "V_name", "V_code", "TP",
        "n_repeats", "sample_idx", "t_us", "i_mA", "p_mW",
    ]

    with open_bridge(args.port) as br, output_path.open("w", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()

        logger.info("INIT panel")
        br.init()
        time.sleep(0.2)

        run_idx = 0
        sweep_start = time.monotonic()
        for v_name, v_code in sources:
            for tp in tp_list:
                run_idx += 1
                lut_bytes = make_single_phase_lut(v_code, tp)
                logger.info(
                    "[%d/%d] V=%s (code=%d), TP=%d frames, n_repeats=%d",
                    run_idx, total_runs, v_name, v_code, tp, args.n_repeats,
                )
                run_start = time.monotonic()
                try:
                    trace = br.bench_run(lut_bytes, frame, n_repeats=args.n_repeats)
                except Exception as e:
                    logger.error("bench_run failed at run %d: %s", run_idx, e)
                    raise

                rows = trace_to_rows(
                    trace,
                    session_id=session_id, run_idx=run_idx,
                    v_name=v_name, v_code=v_code, tp=tp, n_repeats=args.n_repeats,
                )
                writer.writerows(rows)
                run_dur = time.monotonic() - run_start
                logger.info(
                    "  -> %d samples, peak_I=%+.2f mA, E=%.3f mJ, took %.1f s",
                    len(trace), trace.peak_current_ma(), trace.energy_mj(), run_dur,
                )
                time.sleep(args.settle_s)

        logger.info("SLEEP panel")
        br.sleep()

        meta["completed_at"] = datetime.now().isoformat()
        meta["total_duration_s"] = round(time.monotonic() - sweep_start, 2)
        meta["completed_runs"] = run_idx

    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    logger.info("Sweep done. CSV: %s  Meta: %s  Total time: %.1f s",
                output_path, meta_path, meta["total_duration_s"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
