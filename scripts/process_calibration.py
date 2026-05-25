#!/usr/bin/env python3
"""Обработка калибровочного sweep'а — фитинг параметров и генерация артефактов.

Вход:  data/calibration/sweep_<ts>.csv (+ meta.json) из scripts/calibration_sweep.py
Выход:
  - data/calibration/fitted_params.json — извлечённые параметры модели Стокса.
  - tex/figures/plots/03_calibration_traces.pdf — overlay I(t) для всех runs.
  - tex/figures/plots/03_calibration_summary.pdf — summary energy / peak / avg по (V, TP).

Запуск:
  python scripts/process_calibration.py data/calibration/sweep_20260525_1923.csv

Модуль написан так, чтобы его можно было также импортировать из notebook
(notebook/01_calibration.ipynb просто вызывает run_calibration(csv_path)).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

logger = logging.getLogger(__name__)


# ---- Конфигурация по умолчанию -----------------------------------------

# Типовые напряжения SSD1680 (datasheet section 6.6, default values).
# Реальные значения зависят от waveform setting в OTP / регистре 0x04;
# мы здесь принимаем номинальные для пересчёта в физические единицы.
NOMINAL_VOLTAGES = {
    "VSH1": 15.0,    # +15 В (typical for full update)
    "VSH2": 5.0,     # +5 В (intermediate grey level)
    "VSL":  -15.0,   # -15 В (negative full)
    "VCOM": 0.0,
}

# Параметры калибровочной модели (фит):
#   I(t) ≈ I_baseline + Σ_k I_peak · exp(-(t - t_k)/τ),  где t_k — моменты
#   срабатывания фаз waveform. Для одно-фазной single-shot waveform упрощается
#   до экспоненциального decay → можно фитить τ_Stokes и I_peak.
#
# В нашем sweep'е waveform = N_repeats повторов одной фазы → видим серию пиков.
# Извлекаем «characteristic peak current» как 95-й перцентиль распределения
# тока (не max, чтобы убрать outliers).


@dataclass
class RunStats:
    """Статистика одного run'а (одна пара (V, TP))."""
    v_name: str
    v_code: int
    v_nominal_volts: float
    tp_frames: int
    n_repeats: int
    n_samples: int
    duration_ms: float
    energy_total_mj: float
    energy_per_repeat_mj: float
    peak_i_ma: float           # 95-percentile
    avg_i_ma: float
    avg_power_mw: float


def compute_run_stats(df: pd.DataFrame, meta: dict) -> list[RunStats]:
    """Посчитать статистики для каждого (V, TP) комбо."""
    stats: list[RunStats] = []
    nominal_v_map = {s["name"]: NOMINAL_VOLTAGES[s["name"]] for s in meta["sources"]}
    n_repeats = meta["n_repeats"]

    for (v_name, tp), sub in df.groupby(["V_name", "TP"]):
        sub = sub.sort_values("t_us")
        t_s = sub["t_us"].to_numpy() * 1e-6
        i_a = sub["i_mA"].to_numpy() * 1e-3
        p_w = sub["p_mW"].to_numpy() * 1e-3

        energy_total_j = float(np.trapezoid(p_w, t_s))
        peak_i = float(np.percentile(sub["i_mA"], 95))
        avg_i = float(sub["i_mA"].mean())
        avg_p = float(sub["p_mW"].mean())

        stat = RunStats(
            v_name=v_name,
            v_code=int(sub["V_code"].iloc[0]),
            v_nominal_volts=nominal_v_map[v_name],
            tp_frames=int(tp),
            n_repeats=n_repeats,
            n_samples=len(sub),
            duration_ms=float(t_s.max() * 1e3),
            energy_total_mj=energy_total_j * 1e3,
            energy_per_repeat_mj=energy_total_j * 1e3 / n_repeats,
            peak_i_ma=peak_i,
            avg_i_ma=avg_i,
            avg_power_mw=avg_p,
        )
        stats.append(stat)
        logger.info(
            "Run %s/TP=%2d:  E=%6.2f mJ tot (%5.2f per repeat),  P=%4.2f mW avg,  I_peak=%5.2f mA",
            v_name, tp, stat.energy_total_mj, stat.energy_per_repeat_mj,
            stat.avg_power_mw, stat.peak_i_ma,
        )
    return stats


def fit_effective_params(stats: list[RunStats]) -> dict:
    """Извлечь эффективные параметры модели из stats.

    Поскольку наш текущий sweep даёт не одну экспоненту, а серию повторов в окне,
    извлекаем integral-level характеристики:
        - mu_star_estimate: эффективная подвижность (м/(В·с)) — из соотношения
          энергии к работе перемещения частиц,
        - tau_estimate: ОЦЕНКА времени релаксации (можно получить только из
          ratio peak/avg current или из частоты переключений),
        - rho_min, rho_max: значения по datasheet/литературе (не извлекаются
          из этого sweep'а — нужны фотометрические измерения).
    """
    # Среднее по двум источникам (VSH1, VSH2)
    by_v = {}
    for s in stats:
        by_v.setdefault(s.v_name, []).append(s)

    fit = {}
    for v_name, runs in by_v.items():
        avg_energy_per_repeat = np.mean([r.energy_per_repeat_mj for r in runs])
        avg_peak = np.mean([r.peak_i_ma for r in runs])
        avg_avg = np.mean([r.avg_i_ma for r in runs])
        avg_power = np.mean([r.avg_power_mw for r in runs])

        fit[v_name] = {
            "v_nominal_volts": NOMINAL_VOLTAGES[v_name],
            "avg_energy_per_repeat_mj": float(avg_energy_per_repeat),
            "avg_peak_current_ma": float(avg_peak),
            "avg_mean_current_ma": float(avg_avg),
            "avg_power_mw": float(avg_power),
            "peak_to_mean_ratio": float(avg_peak / max(avg_avg, 1e-9)),
        }

    # Эффективные параметры модели Стокса.
    # Поскольку прямой single-shot экспоненциальный фит невозможен из текущих
    # данных, берём литературные типовые из Wang 2022 / He 2020 и используем
    # наши измерения для калибровки одного скейлинг-коэффициента.
    tau_stokes_literature_ms = 60.0   # He 2020: измерено 60 ms на ED060SC7
    mu_star_literature = 1e-9          # типовое для коммерческих EPD

    # Эффективная мощность × длительность фазы должна дать движение частиц.
    # Из формулы Lin 2024: P_peak = (1/2)·C·ΔV²·f·V_source
    # → C_eff = 2·P_peak / (ΔV²·f·V_source)
    # Берём VSH1 как опорный case:
    p_peak_vsh1_w = fit["VSH1"]["avg_peak_current_ma"] * 1e-3 * 3.3
    # frame rate SSD1680 ≈ 50 Hz; ΔV между фазами = 2·V_source при swithing
    delta_v = 2 * NOMINAL_VOLTAGES["VSH1"]
    f_switching = 50.0
    c_effective = 2 * p_peak_vsh1_w / (delta_v**2 * f_switching * NOMINAL_VOLTAGES["VSH1"])

    fit["model_params"] = {
        "mu_star_m_per_Vs": mu_star_literature,
        "tau_stokes_ms": tau_stokes_literature_ms,
        "rho_min": 0.07,
        "rho_max": 0.40,
        "L_caps_um": 40.0,
        "c_effective_pF": float(c_effective * 1e12),
        "source": "mu_star, tau_stokes, rho_min/max — из литературы (Wang 2022, He 2020); c_effective — фит по данным стенда",
    }

    return fit


def plot_traces(df: pd.DataFrame, meta: dict, output_pdf: Path) -> None:
    """Overlay I(t) для всех runs (фигура 3.3 в § 3.5)."""
    fig, axes = plt.subplots(2, 4, figsize=(14, 6), sharey=True)
    sources = [s["name"] for s in meta["sources"]]
    tp_list = meta["tp_list"]

    for row, v_name in enumerate(sources):
        for col, tp in enumerate(tp_list):
            ax = axes[row, col]
            sub = df[(df["V_name"] == v_name) & (df["TP"] == tp)]
            t_ms = sub["t_us"].to_numpy() / 1000.0
            i_ma = sub["i_mA"].to_numpy()
            ax.plot(t_ms, i_ma, lw=0.5, alpha=0.8)
            ax.set_title(f"V={v_name}, TP={tp}")
            ax.set_xlabel("t (мс)")
            if col == 0:
                ax.set_ylabel("I (мА)")
            ax.grid(True, alpha=0.3)

    fig.suptitle(
        "INA219-трассы калибровочного sweep'а (n_repeats=10, frame=white)",
        fontsize=12, y=1.00,
    )
    plt.tight_layout()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_pdf, bbox_inches="tight")
    plt.close()
    logger.info("Trace plot saved: %s", output_pdf)


def plot_summary(stats: list[RunStats], output_pdf: Path) -> None:
    """Bar chart: energy_per_repeat, peak_I, avg_I по (V, TP) — фигура 3.3b."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))

    df_stats = pd.DataFrame([asdict(s) for s in stats])

    for ax, metric, title, ylabel in [
        (axes[0], "energy_per_repeat_mj", "Энергия / refresh", "E, мДж"),
        (axes[1], "peak_i_ma", "Пиковый ток (95-й перцентиль)", "I_peak, мА"),
        (axes[2], "avg_power_mw", "Средняя мощность", "P_avg, мВт"),
    ]:
        for v_name, group in df_stats.groupby("v_name"):
            ax.plot(group["tp_frames"], group[metric], "o-", label=v_name, lw=2, ms=8)
        ax.set_xlabel("TP (фазы waveform)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_pdf, bbox_inches="tight")
    plt.close()
    logger.info("Summary plot saved: %s", output_pdf)


def run_calibration(csv_path: Path) -> dict:
    """Главная функция — обработать CSV и сгенерировать все артефакты."""
    csv_path = Path(csv_path)
    meta_path = csv_path.with_suffix(".meta.json")
    if not meta_path.exists():
        raise FileNotFoundError(f"Meta-файл не найден: {meta_path}")

    logger.info("Loading: %s (%d KB)", csv_path, csv_path.stat().st_size // 1024)
    df = pd.read_csv(csv_path)
    meta = json.loads(meta_path.read_text())
    logger.info("Rows: %d, runs: %d", len(df), meta["completed_runs"])

    stats = compute_run_stats(df, meta)
    fit = fit_effective_params(stats)

    # Сохранить fitted_params.json
    params_path = csv_path.parent / "fitted_params.json"
    fit_out = {
        "calibration_source": str(csv_path.name),
        "calibration_session_id": meta["session_id"],
        "n_runs": len(stats),
        "per_voltage": {k: v for k, v in fit.items() if k != "model_params"},
        "model_params": fit["model_params"],
        "raw_run_stats": [asdict(s) for s in stats],
    }
    params_path.write_text(json.dumps(fit_out, indent=2, ensure_ascii=False))
    logger.info("Params saved: %s", params_path)

    # Сохранить PDF-figures
    figures_dir = Path("tex/figures/plots")
    plot_traces(df, meta, figures_dir / "03_calibration_traces.pdf")
    plot_summary(stats, figures_dir / "03_calibration_summary.pdf")

    return fit_out


def main() -> int:
    parser = argparse.ArgumentParser(description="Обработка калибровочного sweep'а")
    parser.add_argument("csv", help="Путь к CSV из calibration_sweep.py")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    fit = run_calibration(args.csv)
    print()
    print("===== ИТОГОВЫЕ ПАРАМЕТРЫ =====")
    print(json.dumps(fit["model_params"], indent=2, ensure_ascii=False))
    print()
    print("По каждому напряжению:")
    for v_name, stats in fit["per_voltage"].items():
        print(f"  {v_name}: E={stats['avg_energy_per_repeat_mj']:.3f} мДж/refresh, "
              f"P={stats['avg_power_mw']:.3f} мВт, "
              f"I_peak={stats['avg_peak_current_ma']:.2f} мА")
    return 0


if __name__ == "__main__":
    sys.exit(main())
