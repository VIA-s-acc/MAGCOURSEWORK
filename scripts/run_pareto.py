"""Полный Парето-фронт по тест-набору + сравнение с NSGA-II.

Обходит 10 сценариев перехода (z_init → z_target), для каждого строит
Парето-фронт ε-constraint методом и (опц.) NSGA-II baseline. Считает
hypervolume и IGD. Сохраняет 6 PDF-рисунков и LaTeX-таблицу summary.

Используется из notebooks/03_pareto.ipynb. Реализует § 6.4 курсовой.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from python.baselines import NSGA2
from python.pareto import ParetoPoint, build_pareto_frontier, filter_dominated, hypervolume, igd
from python.surrogate import SurrogateModel
from scripts.run_optimize import build_sim_from_calibration, build_surrogate, load_calibration

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Scenario:
    name: str
    z_init: float
    z_target: float


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("BB→WW", 0.07, 0.40),
    Scenario("WW→BB", 0.40, 0.07),
    Scenario("GS0→GS3", 0.07, 0.30),
    Scenario("GS1→GS2", 0.15, 0.25),
    Scenario("WW→GS2", 0.40, 0.25),
    Scenario("GS3→WW", 0.30, 0.40),
    Scenario("step+", 0.07, 0.10),
    Scenario("step−", 0.10, 0.07),
    Scenario("mid→BB", 0.25, 0.07),
    Scenario("mid→WW", 0.25, 0.40),
)


# Заводская точка B0 (типовая) для контекста на графиках.
B0_REF = {"E": 0.02, "G": 0.05, "tau": 0.6}  # мДж/пиксель, ghost, с


def run_one_scenario(
    sc: Scenario, surr: SurrogateModel,
    eps_G_grid: tuple[float, ...], eps_tau_grid: tuple[float, ...],
    voltages: tuple[float, ...], durations: tuple[int, ...], k_eff_max: int,
) -> tuple[list[ParetoPoint], list[ParetoPoint]]:
    """Вернуть (наш фронт, NSGA-II фронт)."""
    logger.info("scenario: %s", sc.name)
    ours = build_pareto_frontier(
        z_init=sc.z_init, z_target=sc.z_target,
        eps_G_grid=eps_G_grid, eps_tau_grid=eps_tau_grid,
        model=surr,
        voltages=voltages, durations=durations,
        k_eff_max=k_eff_max,
    )
    ga = NSGA2(
        pop_size=50, n_gen=20,
        voltages=voltages, durations=durations, k_eff_max=k_eff_max,
        seed=42,
    )
    nsga = ga.run(surr, sc.z_init, sc.z_target)
    return ours, nsga


def _pts_to_arr(points: list[ParetoPoint]) -> np.ndarray:
    if not points:
        return np.empty((0, 3))
    return np.array([p.vector for p in points])


def plot_pareto_projection(
    results: dict[str, tuple[list[ParetoPoint], list[ParetoPoint]]],
    axes: tuple[int, int], labels: tuple[str, str],
    out_path: Path, title: str,
) -> None:
    """2D проекция фронта по двум осям из (E, G, τ)."""
    fig, ax = plt.subplots(figsize=(12.0 / 2.54, 7.0 / 2.54))
    cmap = plt.get_cmap("tab10")
    for i, (name, (ours, _)) in enumerate(results.items()):
        arr = _pts_to_arr(ours)
        if arr.size == 0:
            continue
        ax.scatter(arr[:, axes[0]], arr[:, axes[1]], s=10, c=[cmap(i % 10)], label=name, alpha=0.8)
    # B0 reference
    b_x = [B0_REF["E"], B0_REF["G"], B0_REF["tau"]][axes[0]]
    b_y = [B0_REF["E"], B0_REF["G"], B0_REF["tau"]][axes[1]]
    ax.scatter([b_x], [b_y], s=80, marker="x", c="red", label="B0 (заводской)", zorder=10)
    ax.set_xlabel(labels[0], fontsize=8)
    ax.set_ylabel(labels[1], fontsize=8)
    ax.set_title(title, fontsize=8)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=6, loc="upper right", ncol=2)
    ax.grid(True, alpha=0.3)
    fig.savefig(out_path, format="pdf", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    logger.info("saved: %s", out_path)


def plot_pareto_3d(results: dict, out_path: Path) -> None:
    fig = plt.figure(figsize=(12.0 / 2.54, 9.0 / 2.54))
    ax = fig.add_subplot(111, projection="3d")
    cmap = plt.get_cmap("tab10")
    for i, (name, (ours, _)) in enumerate(results.items()):
        arr = _pts_to_arr(ours)
        if arr.size == 0:
            continue
        ax.scatter(arr[:, 0], arr[:, 1], arr[:, 2], s=8, c=[cmap(i % 10)], label=name, alpha=0.7)
    ax.set_xlabel("E, мДж", fontsize=7)
    ax.set_ylabel("G, рефл.", fontsize=7)
    ax.set_zlabel("τ, с", fontsize=7)
    ax.set_title("3D Парето-фронт по 10 сценариям", fontsize=8)
    ax.tick_params(labelsize=6)
    ax.legend(fontsize=5, loc="upper left", ncol=2)
    fig.savefig(out_path, format="pdf", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    logger.info("saved: %s", out_path)


def plot_ours_vs_nsga2(name: str, ours: list[ParetoPoint], nsga: list[ParetoPoint], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12.0 / 2.54, 7.0 / 2.54))
    arr_o = _pts_to_arr(ours)
    arr_n = _pts_to_arr(nsga)
    if arr_o.size > 0:
        ax.scatter(arr_o[:, 0], arr_o[:, 1], s=30, marker="o", c="blue", label="ε-constraint + PMP", alpha=0.8)
    if arr_n.size > 0:
        ax.scatter(arr_n[:, 0], arr_n[:, 1], s=30, marker="s", c="orange", label="NSGA-II", alpha=0.6)
    ax.set_xlabel("E, мДж", fontsize=8)
    ax.set_ylabel("G, рефл.", fontsize=8)
    ax.set_title(f"Сравнение фронтов для сценария {name} (проекция E,G)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.savefig(out_path, format="pdf", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    logger.info("saved: %s", out_path)


def plot_energy_distribution(results: dict, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12.0 / 2.54, 6.0 / 2.54))
    names = list(results.keys())
    energies = [[p.energy for p in results[n][0]] for n in names]
    ax.boxplot(energies, labels=names, showfliers=False)
    ax.axhline(B0_REF["E"], color="red", linestyle="--", linewidth=0.8, label=f'B0: {B0_REF["E"]} мДж')
    ax.set_ylabel("E, мДж/пиксель", fontsize=8)
    ax.set_title("Распределение энергии по точкам Парето-фронта (10 сценариев)", fontsize=8)
    ax.tick_params(labelsize=6)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3, axis="y")
    fig.savefig(out_path, format="pdf", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    logger.info("saved: %s", out_path)


def export_summary_table(results: dict, out_path: Path) -> None:
    """LaTeX-таблица с метриками HV, IGD, %улучшения E vs B0."""
    rows = []
    for name, (ours, nsga) in results.items():
        if not ours:
            rows.append((name, "—", "—", "—", "—"))
            continue
        best_E = min(p.energy for p in ours)
        # HV: ref = (max E in scenario × 1.2, 0.1, 1.0)
        ref = (max(0.05, best_E * 5), 0.1, 1.0)
        hv_ours = hypervolume(ours, ref)
        hv_nsga = hypervolume(nsga, ref) if nsga else 0.0
        combined = filter_dominated(ours + nsga)
        igd_ours = igd(ours, combined)
        improvement = 100.0 * (B0_REF["E"] - best_E) / B0_REF["E"]
        rows.append((
            name,
            f"{best_E:.4f}",
            f"{improvement:+.1f}%",
            f"{hv_ours:.4f}",
            f"{hv_nsga:.4f}",
        ))

    lines = [
        "\\begin{tabular}{lrrrr}",
        "\\hline",
        "Сценарий & $E^*$, мДж & $\\Delta E$ vs B0 & HV (наш) & HV (NSGA-II) \\\\",
        "\\hline",
    ]
    for r in rows:
        lines.append(" & ".join(r) + " \\\\")
    lines.append("\\hline")
    lines.append("\\end{tabular}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("saved: %s", out_path)


def main() -> dict:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    repo = Path(__file__).resolve().parents[1]
    cal = load_calibration(repo / "data" / "calibration" / "fitted_params.json")
    sim, c_eff_nF = build_sim_from_calibration(cal)
    surr = build_surrogate(sim, c_eff_nF)

    eps_G_grid = (0.005, 0.01, 0.02, 0.04)
    eps_tau_grid = (0.1, 0.2, 0.3, 0.4)
    voltages = (-15.0, -5.0, 0.0, 5.0, 15.0)
    durations = (1, 2, 4, 8, 12, 16)
    k_eff_max = 4

    results: dict[str, tuple[list[ParetoPoint], list[ParetoPoint]]] = {}
    for sc in SCENARIOS:
        ours, nsga = run_one_scenario(sc, surr, eps_G_grid, eps_tau_grid, voltages, durations, k_eff_max)
        results[sc.name] = (ours, nsga)

    out_dir = repo / "tex" / "figures" / "plots"
    plot_pareto_projection(results, (0, 1), ("E, мДж/пиксель", "G, рефл."), out_dir / "pareto_2d_E_G.pdf",
                           "Парето-фронт (проекция E,G) на 10 сценариях")
    plot_pareto_projection(results, (0, 2), ("E, мДж/пиксель", "τ, с"), out_dir / "pareto_2d_E_tau.pdf",
                           "Парето-фронт (проекция E,τ) на 10 сценариях")
    plot_pareto_projection(results, (1, 2), ("G, рефл.", "τ, с"), out_dir / "pareto_2d_G_tau.pdf",
                           "Парето-фронт (проекция G,τ) на 10 сценариях")
    plot_pareto_3d(results, out_dir / "pareto_3d.pdf")
    # NSGA сравнение на одном «трудном» сценарии — BB→WW
    plot_ours_vs_nsga2("BB→WW", results["BB→WW"][0], results["BB→WW"][1], out_dir / "pareto_vs_nsga2.pdf")
    plot_energy_distribution(results, out_dir / "energy_distribution.pdf")

    export_summary_table(results, repo / "tex" / "tables" / "pareto_summary.tex")

    summary = {
        "n_scenarios": len(results),
        "scenarios_feasible": sum(1 for v in results.values() if v[0]),
        "best_E_per_scenario_mJ": {n: (min(p.energy for p in ours) if ours else None) for n, (ours, _) in results.items()},
    }
    return summary


if __name__ == "__main__":
    s = main()
    print(json.dumps(s, indent=2, ensure_ascii=False))
