"""Запуск одиночной задачи оптимизации waveform для notebook 02.

Загружает калиброванный PixelOdeSim из data/calibration/fitted_params.json,
обучает SurrogateModel, решает PMP-задачу для GS0→GS3 (z=0.07 → z=0.40),
сохраняет визуализацию найденного waveform в tex/figures/plots/.

Используется из notebooks/02_optimize.ipynb.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from python.ode_sim import PixelOdeSim
from python.optimizer import Waveform, solve_pmp_slice
from python.surrogate import SurrogateModel

logger = logging.getLogger(__name__)


def load_calibration(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_sim_from_calibration(cal: dict) -> tuple[PixelOdeSim, float]:
    """PixelOdeSim из fitted_params.json + c_eff в нФ."""
    p = cal["model_params"]
    sim = PixelOdeSim(
        mu_star=p["mu_star_m_per_Vs"],
        tau_star=p["tau_stokes_ms"] * 1e-3,
        rho_min=p["rho_min"],
        rho_max=p["rho_max"],
        L=p["L_caps_um"] * 1e-6,
    )
    c_eff_nF = p["c_effective_pF"] / 1000.0
    return sim, c_eff_nF


def build_surrogate(sim: PixelOdeSim, c_eff_nF: float) -> SurrogateModel:
    surr = SurrogateModel(
        voltages=(-15.0, -5.0, 0.0, 5.0, 15.0),
        durations_frames=(1, 2, 4, 8, 12, 16),
        z_levels=(0.07, 0.15, 0.25, 0.40),
        z_clip=(0.07, 0.40),
    )
    surr.fit_from_ode_sim(sim, c_eff_nF=c_eff_nF, vcom=0.0)
    return surr


def solve_example_task(surr: SurrogateModel) -> Waveform | None:
    """GS0 → GS3 (z=0.07 → z=0.40), ε_G=0.04, ε_τ=0.4 с."""
    res = solve_pmp_slice(
        z_init=0.07, z_target=0.40,
        eps_G=0.04, eps_tau=0.4,
        model=surr,
        voltages=(-15.0, -5.0, 0.0, 5.0, 15.0),
        durations=(1, 2, 4, 8, 12, 16),
        k_eff_max=4,
        charge_eps=0.05,
    )
    if res is None:
        return None
    logger.info("solved: E=%.3f мДж, G=%.4f, τ=%.3f с", res.energy, res.ghost, res.latency)
    return res.waveform


def plot_waveform_vs_baseline(wf_ours: Waveform, out_path: Path) -> None:
    """Сравнение нашего waveform с типичным B0 (Waveshare заводской full ≈ 600 мс)."""
    fig, ax = plt.subplots(figsize=(12.0 / 2.54, 4.0 / 2.54))  # 12×4 см

    # Наш waveform.
    t_curr = 0.0
    times_ours = [0.0]
    voltages_ours = [0.0]
    for V, T in zip(wf_ours.voltages, wf_ours.durations):
        T_sec = T / wf_ours.f_frame
        times_ours.append(t_curr)
        voltages_ours.append(V)
        t_curr += T_sec
        times_ours.append(t_curr)
        voltages_ours.append(V)
    times_ours.append(t_curr)
    voltages_ours.append(0.0)

    # Типичный B0: упрощённая модель Waveshare full update — 4 фазы по 150 мс,
    # последовательность (+15, -15, +15, -15). Энергия ~ 7 мДж.
    times_b0 = [0.0]
    voltages_b0 = [0.0]
    b0_seq = [(+15.0, 0.15), (-15.0, 0.15), (+15.0, 0.15), (-15.0, 0.15)]
    t_curr_b0 = 0.0
    for V, T in b0_seq:
        times_b0.append(t_curr_b0)
        voltages_b0.append(V)
        t_curr_b0 += T
        times_b0.append(t_curr_b0)
        voltages_b0.append(V)
    times_b0.append(t_curr_b0)
    voltages_b0.append(0.0)

    ax.plot(times_b0, voltages_b0, "k--", linewidth=1.0, label="B0 (Waveshare full)")
    ax.plot(times_ours, voltages_ours, "b-", linewidth=1.5, label="Оптимальный (PMP)")
    ax.set_xlabel("Время, с", fontsize=8)
    ax.set_ylabel("Напряжение источника, В", fontsize=8)
    ax.set_title("Найденный waveform vs заводская LUT (переход GS0→GS3)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="gray", linewidth=0.5)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="pdf", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    logger.info("saved: %s", out_path)


def main() -> dict:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    repo = Path(__file__).resolve().parents[1]
    cal = load_calibration(repo / "data" / "calibration" / "fitted_params.json")
    sim, c_eff_nF = build_sim_from_calibration(cal)
    surr = build_surrogate(sim, c_eff_nF)
    wf = solve_example_task(surr)
    if wf is None:
        logger.warning("no feasible waveform for GS0→GS3")
        return {"ok": False}
    E, G, tau = surr.predict(wf, 0.07, 0.40)
    plot_waveform_vs_baseline(wf, repo / "tex" / "figures" / "plots" / "optimal_waveform_example.pdf")
    return {
        "ok": True,
        "voltages": list(wf.voltages),
        "durations_frames": list(wf.durations),
        "energy_mJ": E,
        "ghost_residual": G,
        "latency_s": tau,
        "k_eff": wf.k_eff,
        "charge_imbalance_Vs": wf.charge_integral,
    }


if __name__ == "__main__":
    out = main()
    print(json.dumps(out, indent=2, ensure_ascii=False))
