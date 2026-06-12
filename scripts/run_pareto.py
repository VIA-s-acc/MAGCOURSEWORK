"""Полный Парето-фронт по тест-набору + сравнение с NSGA-II.

Обходит 10 сценариев перехода (z_init → z_target), для каждого строит
Парето-фронт ε-constraint методом и (опц.) NSGA-II baseline, сравнивает их по
hypervolume. Сохраняет PDF-рисунки и LaTeX-таблицу summary.

Это «предсказанный» пайплайн на ODE-суррогате — для структурного сравнения с
NSGA-II в одной модели; измеренные результаты см. scripts/make_figures.py.
Реализует § 6.4 курсовой.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from tqdm.auto import tqdm

from python.baselines import NSGA2
from python.optimizer import Waveform
from python.pareto import ParetoPoint, build_pareto_frontier, hypervolume
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


# Симулированный B0 = представительная заводская full-refresh waveform
# Waveshare: 4 фазы по 8 кадров (~640 мс при f=50Гц) с амплитудой ±15 В.
# Это близко к реальному поведению Waveshare 2.13"V4 full update (~600 мс).
B0_WAVEFORM = Waveform(
    voltages=(+15.0, -15.0, +15.0, -15.0),
    durations=(8, 8, 8, 8),
    f_frame=50.0,
)


def evaluate_b0(surr: SurrogateModel, sc: Scenario) -> tuple[float, float, float]:
    """Оценить (E, G, τ) симулированного B0 для конкретного сценария."""
    return surr.predict(B0_WAVEFORM, sc.z_init, sc.z_target)


def run_one_scenario(
    sc: Scenario, surr: SurrogateModel,
    eps_G_grid: tuple[float, ...], eps_tau_grid: tuple[float, ...],
    voltages: tuple[float, ...], durations: tuple[int, ...], k_eff_max: int,
) -> tuple[list[ParetoPoint], list[ParetoPoint]]:
    """Вернуть (наш фронт, NSGA-II фронт). NSGA-II с seed=42 для воспроизводимости."""
    logger.info("scenario: %s", sc.name)
    ours = build_pareto_frontier(
        z_init=sc.z_init, z_target=sc.z_target,
        eps_G_grid=eps_G_grid, eps_tau_grid=eps_tau_grid,
        model=surr,
        voltages=voltages, durations=durations,
        k_eff_max=k_eff_max,
    )
    ga = NSGA2(
        pop_size=100, n_gen=50,
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
    for i, (name, (ours, _, _)) in enumerate(results.items()):
        arr = _pts_to_arr(ours)
        if arr.size == 0:
            continue
        ax.scatter(arr[:, axes[0]], arr[:, axes[1]], s=10, c=[cmap(i % 10)], label=name, alpha=0.8)
    # B0 — симулированная заводская точка для среднего сценария (BB→WW)
    b0_E, b0_G, b0_tau = results["BB→WW"][2]  # 3-й элемент — B0 для сценария
    b_arr = [b0_E, b0_G, b0_tau]
    ax.scatter([b_arr[axes[0]]], [b_arr[axes[1]]], s=80, marker="x", c="red",
               label="B0 (sim. заводской)", zorder=10)
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
    for i, (name, (ours, _, _)) in enumerate(results.items()):
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


def plot_ours_vs_nsga2_3d(name: str, ours: list[ParetoPoint], nsga: list[ParetoPoint], out_path: Path) -> None:
    """3D-сравнение с подписями координат для наших точек и ближайших NSGA."""
    fig = plt.figure(figsize=(15.0 / 2.54, 12.0 / 2.54))
    ax = fig.add_subplot(111, projection="3d")
    arr_o = _pts_to_arr(ours)
    arr_n = _pts_to_arr(nsga)

    # Уникальные точки нашего фронта (после дедупликации совпадающих)
    if arr_o.size > 0:
        unique_o = np.unique(np.round(arr_o, 5), axis=0)
    else:
        unique_o = np.empty((0, 3))

    if arr_n.size > 0:
        ax.scatter(arr_n[:, 0], arr_n[:, 1], arr_n[:, 2], s=22, marker="s",
                   c="orange", alpha=0.45, edgecolors="darkorange", linewidths=0.4,
                   label="NSGA-II")
    if arr_o.size > 0:
        ax.scatter(unique_o[:, 0], unique_o[:, 1], unique_o[:, 2], s=130, marker="o",
                   facecolors="blue", edgecolors="black", linewidths=1.4,
                   label=f"ε-constraint + PMP ({len(unique_o)} уник.)", alpha=1.0)

    # Подписи координат для всех наших точек + связь линией к точке
    def _fmt(v: np.ndarray) -> str:
        return f"({v[0]:.4f}, {v[1]:.3f}, {v[2]:.2f})"

    z_range = max(1e-3, arr_n[:, 2].max() if arr_n.size > 0 else 1.0)
    offset_z = 0.08 * z_range
    offset_x = 0.001
    for i, p in enumerate(unique_o):
        # Текст подписи рядом с точкой (смещение вверх по z)
        text_pos = (p[0] + offset_x, p[1] + 0.02, p[2] + offset_z)
        ax.plot([p[0], text_pos[0]], [p[1], text_pos[1]], [p[2], text_pos[2]],
                color="black", linewidth=0.5, alpha=0.7)
        ax.text(text_pos[0], text_pos[1], text_pos[2], f"P{i+1}: {_fmt(p)}",
                fontsize=6, color="navy", fontweight="bold")

    # Подписи для NSGA-II — ближайших к нашим PMP-точкам
    if arr_n.size > 0 and unique_o.size > 0:
        labeled_nsga: set[int] = set()
        for p in unique_o:
            dists = np.linalg.norm(arr_n - p, axis=1)
            nearest = int(np.argmin(dists))
            if nearest in labeled_nsga:
                continue
            labeled_nsga.add(nearest)
            q = arr_n[nearest]
            text_pos = (q[0] + offset_x, q[1] - 0.03, q[2] - offset_z)
            ax.plot([q[0], text_pos[0]], [q[1], text_pos[1]], [q[2], text_pos[2]],
                    color="darkorange", linewidth=0.5, alpha=0.7)
            ax.text(text_pos[0], text_pos[1], text_pos[2], f"N: {_fmt(q)}",
                    fontsize=6, color="saddlebrown", style="italic")

    ax.set_xlabel("E, мДж", fontsize=9, labelpad=8)
    ax.set_ylabel("G, рефл.", fontsize=9, labelpad=8)
    ax.set_zlabel("τ, с", fontsize=9, labelpad=8)
    ax.set_title(
        f"3D-сравнение фронтов: {name}\n"
        f"P — наши точки (синие), N — ближайшие NSGA-II (оранж.); "
        "формат подписи (E мДж, G, τ с)",
        fontsize=8, pad=8,
    )
    ax.tick_params(labelsize=7, pad=2)
    ax.legend(fontsize=7, loc="upper left", bbox_to_anchor=(0.0, 1.0))
    ax.view_init(elev=20, azim=-65)
    fig.subplots_adjust(left=0.05, right=0.95, bottom=0.05, top=0.90)
    fig.savefig(out_path, format="pdf", bbox_inches=None, pad_inches=0.15)
    plt.close(fig)
    logger.info("saved: %s", out_path)


def plot_ours_vs_nsga2(name: str, ours: list[ParetoPoint], nsga: list[ParetoPoint], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13.0 / 2.54, 8.5 / 2.54))
    arr_o = _pts_to_arr(ours)
    arr_n = _pts_to_arr(nsga)

    # Уникальные точки нашего фронта (после дедупликации)
    if arr_o.size > 0:
        unique_o = np.unique(np.round(arr_o, 5), axis=0)
    else:
        unique_o = np.empty((0, 3))

    if arr_n.size > 0:
        ax.scatter(arr_n[:, 0], arr_n[:, 1], s=30, marker="s", c="orange",
                   label="NSGA-II", alpha=0.5, edgecolors="darkorange", linewidths=0.5, zorder=1)
    if unique_o.size > 0:
        ax.scatter(unique_o[:, 0], unique_o[:, 1], s=110, marker="o", facecolors="blue",
                   edgecolors="black", linewidths=1.2,
                   label=f"ε-constraint + PMP ({len(unique_o)} уник.)", alpha=1.0, zorder=5)

    # Annotation для всех наших + ближайшие NSGA
    def _fmt(v: np.ndarray) -> str:
        return f"E={v[0]:.4f}, G={v[1]:.3f}, τ={v[2]:.2f}"

    # Расширяем верхнюю границу оси Y, чтобы подписи не лезли на легенду
    y_max_pts = max(arr_n[:, 1].max() if arr_n.size > 0 else 0.0,
                    unique_o[:, 1].max() if unique_o.size > 0 else 0.0)
    ax.set_ylim(top=y_max_pts * 1.4 + 0.05)

    labeled_nsga: set[int] = set()
    # Подписи стек-горизонтально (друг под другом сверху над точкой)
    for i, p in enumerate(unique_o):
        y_text_p = 0.15 + 0.04 * i  # стек подписей наших точек
        ax.annotate(f"P{i+1}: {_fmt(p)}",
                    xy=(p[0], p[1]),
                    xytext=(p[0], y_text_p),
                    fontsize=6, color="navy", fontweight="bold",
                    ha="left",
                    arrowprops=dict(arrowstyle="->", color="black", lw=0.5))
        if arr_n.size > 0:
            dists = np.linalg.norm(arr_n[:, :2] - p[:2], axis=1)
            nearest = int(np.argmin(dists))
            if nearest in labeled_nsga:
                continue
            labeled_nsga.add(nearest)
            q = arr_n[nearest]
            y_text_q = 0.30 + 0.04 * i  # стек подписей NSGA выше
            ax.annotate(f"N: {_fmt(q)}",
                        xy=(q[0], q[1]),
                        xytext=(q[0], y_text_q),
                        fontsize=6, color="saddlebrown", style="italic",
                        ha="left",
                        arrowprops=dict(arrowstyle="->", color="darkorange", lw=0.5))

    ax.set_xlabel("E, мДж", fontsize=8)
    ax.set_ylabel("G, рефл.", fontsize=8)
    ax.set_title(f"Сравнение фронтов для сценария {name} (проекция E,G)\n"
                 "P — наши; N — ближайшие NSGA-II", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.savefig(out_path, format="pdf", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    logger.info("saved: %s", out_path)


def plot_energy_distribution(results: dict, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12.0 / 2.54, 6.0 / 2.54))
    names = list(results.keys())
    energies = [[p.energy for p in results[n][0]] for n in names]
    ax.boxplot(energies, tick_labels=names, showfliers=False)
    # B0 reference — среднее значение по 10 сценариям
    b0_E_mean = float(np.mean([results[n][2][0] for n in names]))
    ax.axhline(b0_E_mean, color="red", linestyle="--", linewidth=0.8,
               label=f'B0 (sim, среднее): {b0_E_mean:.4f} мДж')
    ax.set_ylabel("E, мДж на обновление панели", fontsize=8)
    ax.set_title("Распределение энергии по точкам Парето-фронта (10 сценариев)", fontsize=8)
    ax.tick_params(labelsize=6)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3, axis="y")
    fig.savefig(out_path, format="pdf", bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    logger.info("saved: %s", out_path)


def export_summary_table(results: dict, out_path: Path) -> None:
    """LaTeX-таблица с метриками HV, IGD, %улучшения E vs sim B0."""
    rows = []
    for name, (ours, nsga, (b0_E, b0_G, b0_tau)) in results.items():
        if not ours:
            rows.append((name, "—", f"{b0_E:.4f}", "—", "—", "—"))
            continue
        best_E = min(p.energy for p in ours)
        ref = (max(0.05, best_E * 5), 0.1, 1.0)
        hv_ours = hypervolume(ours, ref)
        hv_nsga = hypervolume(nsga, ref) if nsga else 0.0
        improvement = 100.0 * (b0_E - best_E) / b0_E if b0_E > 0 else 0.0
        rows.append((
            name,
            f"{best_E:.4f}",
            f"{b0_E:.4f}",
            f"{improvement:+.1f}\\%",
            f"{hv_ours:.4f}",
            f"{hv_nsga:.4f}",
        ))

    lines = [
        "\\begin{tabular}{lrrrrr}",
        "\\hline",
        "Сценарий & $E^*$, мДж & $E_{B_0}$, мДж & $\\Delta E$ & HV (наш) & HV (NSGA-II) \\\\",
        "\\hline",
    ]
    for r in rows:
        lines.append(" & ".join(r) + " \\\\")
    lines.append("\\hline")
    lines.append("\\end{tabular}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("saved: %s", out_path)


def _worker_run_scenario(
    sc: Scenario, cal: dict,
    eps_G_grid: tuple, eps_tau_grid: tuple,
    voltages: tuple, durations: tuple, k_eff_max: int,
) -> tuple[list[ParetoPoint], list[ParetoPoint], tuple[float, float, float]]:
    """Worker: реконструирует surrogate в дочернем процессе и решает один сценарий."""
    # Тишина в worker'е: только WARNING/ERROR — INFO глушим явно по логгерам,
    # т.к. basicConfig может быть no-op, если кто-то уже сконфигурировал root.
    for name in ("python.surrogate", "python.optimizer", "python.pareto",
                 "python.baselines", "scripts.run_pareto", "scripts.run_optimize"):
        logging.getLogger(name).setLevel(logging.WARNING)
    sim, c_eff_nF = build_sim_from_calibration(cal)
    surr = build_surrogate(sim, c_eff_nF)
    ours, nsga = run_one_scenario(sc, surr, eps_G_grid, eps_tau_grid, voltages, durations, k_eff_max)
    b0_eval = evaluate_b0(surr, sc)
    return ours, nsga, b0_eval


def main(verbose: bool = False) -> dict:
    """Запустить полный pareto-pipeline.

    verbose=False (default): тихий режим, только tqdm и финальный JSON.
        Подходит для notebook'ов и финальной сборки.
    verbose=True: подробные INFO логи (для отладки из CLI).
    """
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    # При verbose=False явно глушим info-логи нашего кода даже если root шумит.
    if not verbose:
        for name in ("python.surrogate", "python.optimizer", "python.pareto",
                     "python.baselines", "scripts.run_pareto", "scripts.run_optimize"):
            logging.getLogger(name).setLevel(logging.WARNING)
    repo = Path(__file__).resolve().parents[1]
    cal = load_calibration(repo / "data" / "calibration" / "fitted_params.json")
    sim, c_eff_nF = build_sim_from_calibration(cal)
    surr = build_surrogate(sim, c_eff_nF)

    eps_G_grid = (0.005, 0.01, 0.02, 0.04)
    eps_tau_grid = tuple(round(0.1 * i, 2) for i in range(1, 8))  # 0.1..0.7 шаг 0.1
    voltages = (-15.0, -5.0, 0.0, 5.0, 15.0)
    durations = (1, 2, 4, 8, 12, 16)
    k_eff_max = 4

    # Параллельный прогон по сценариям через ProcessPoolExecutor.
    results: dict = {}
    n_workers = min(len(SCENARIOS), 10)
    logger.info("parallel run: %d workers", n_workers)
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(
                _worker_run_scenario,
                sc, cal, eps_G_grid, eps_tau_grid, voltages, durations, k_eff_max,
            ): sc
            for sc in SCENARIOS
        }
        with tqdm(total=len(SCENARIOS), desc="Сценарии", unit="сц.") as pbar:
            for fut in as_completed(futures):
                sc = futures[fut]
                ours, nsga, b0_eval = fut.result()
                results[sc.name] = (ours, nsga, b0_eval)
                best_E = min((p.energy for p in ours), default=float("inf"))
                pbar.set_postfix_str(f"{sc.name}: E*={best_E:.4f}")
                pbar.update(1)
    results = {sc.name: results[sc.name] for sc in SCENARIOS}

    out_dir = repo / "tex" / "figures" / "plots"
    plot_pareto_projection(results, (0, 1), ("E, мДж на обновление панели", "G, рефл."),
                           out_dir / "pareto_2d_E_G.pdf",
                           "Парето-фронт (проекция E,G) на 10 сценариях")
    plot_pareto_projection(results, (0, 2), ("E, мДж на обновление панели", "τ, с"),
                           out_dir / "pareto_2d_E_tau.pdf",
                           "Парето-фронт (проекция E,τ) на 10 сценариях")
    plot_pareto_projection(results, (1, 2), ("G, рефл.", "τ, с"),
                           out_dir / "pareto_2d_G_tau.pdf",
                           "Парето-фронт (проекция G,τ) на 10 сценариях")
    plot_pareto_3d(results, out_dir / "pareto_3d.pdf")
    plot_ours_vs_nsga2("BB→WW", results["BB→WW"][0], results["BB→WW"][1],
                        out_dir / "pareto_vs_nsga2.pdf")
    plot_ours_vs_nsga2_3d("BB→WW", results["BB→WW"][0], results["BB→WW"][1],
                          out_dir / "pareto_vs_nsga2_3d.pdf")
    plot_energy_distribution(results, out_dir / "energy_distribution.pdf")

    export_summary_table(results, repo / "tex" / "tables" / "pareto_summary.tex")

    summary = {
        "n_scenarios": len(results),
        "scenarios_feasible": sum(1 for v in results.values() if v[0]),
        "best_E_per_scenario_mJ": {n: (min(p.energy for p in v[0]) if v[0] else None) for n, v in results.items()},
        "b0_E_per_scenario_mJ": {n: v[2][0] for n, v in results.items()},
    }
    return summary


if __name__ == "__main__":
    import sys
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    s = main(verbose=verbose)
    print(json.dumps(s, indent=2, ensure_ascii=False))
