#!/usr/bin/env python3
"""Графики результатов для главы 7 (из реальных замеров стенда, метрика otsu_gap)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.panel_model import PanelModel, Waveform

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "tex" / "figures" / "plots"
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.size": 11, "figure.dpi": 130, "font.family": "DejaVu Sans"})

m = PanelModel.load()
mp = json.loads((REPO / "data" / "bench" / "calibrated_model.json").read_text())
pts = mp["data_points"]
final = json.loads((REPO / "data" / "bench" / "final" / "final.json").read_text())["rows"]
uni = json.loads((REPO / "data" / "bench" / "uniform_otsu.json").read_text())  # [[E,otsu],...]


def fget(kind):
    return next(r for r in final if r["kind"] == kind)


B0, B1 = fget("B0"), fget("B1")
our = [r for r in final if r["kind"] == "OUR"]  # равный, баланс, relaxed (в порядке DESIGNS)
C_B1 = B1["otsu"]

# --- Рис 1: калибровка E(N) и τ(N) ---
N = np.array([p["N"] for p in pts]); E = np.array([p["E_mj"] for p in pts]); T = np.array([p["tau_s"] for p in pts])
fig, ax = plt.subplots(1, 2, figsize=(8.2, 3.2))
xs = np.linspace(N.min(), N.max(), 50)
ax[0].scatter(N, E, s=22, color="#1f77b4", zorder=3, label="замеры INA219")
ax[0].plot(xs, m.E0 + m.kE*xs, "r-", lw=1.5, label=f"E={m.E0:.2f}+{m.kE:.3f}·N\n$R^2$={mp['energy']['r2']:.3f}")
ax[0].set_xlabel("Число кадров N"); ax[0].set_ylabel("Энергия E, мДж"); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3)
ax[1].scatter(N, T, s=22, color="#1f77b4", zorder=3, label="замеры")
ax[1].plot(xs, m.t0 + m.kt*xs, "r-", lw=1.5, label=f"τ={m.t0:.3f}+{m.kt:.4f}·N\n$R^2$={mp['latency']['r2']:.3f}")
ax[1].set_xlabel("Число кадров N"); ax[1].set_ylabel("Латентность τ, с"); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3)
fig.tight_layout(); fig.savefig(OUT/"calib_E_tau.png"); plt.close(fig)

# --- Рис 2: contrast(Td) otsu + насыщение модели ---
td_pts = sorted((p["Td"], p["contrast"]) for p in pts if p["Tc"] == 4 and p["Tosc"] == 0)
fig, ax = plt.subplots(figsize=(5.2, 3.4))
tdx = np.array([t for t, _ in td_pts]); tdy = np.array([c for _, c in td_pts])
ax.scatter(tdx, tdy, s=28, color="#2ca02c", zorder=3, label="замеры (клир=4)")
xx = np.linspace(1, 32, 100)
cc = [m.contrast(Waveform(tc=4, tosc=0, td=int(round(x)))) for x in xx]
ax.plot(xx, cc, "r-", lw=1.5, label=f"модель $R^2$={mp['contrast']['r2']:.3f}")
ax.axhline(C_B1, ls="--", color="gray", lw=1, label=f"заводский B1 ({C_B1:.3f})")
ax.set_xlabel("Кадры финального драйва $T_d$"); ax.set_ylabel("Контраст (otsu_gap)")
ax.legend(fontsize=8); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(OUT/"contrast_td.png"); plt.close(fig)

# --- Рис 3: Парето otsu: наш метод vs равномерный vs заводский + ε-точки ---
ours_curve = sorted([(p["E_mj"], p["contrast"]) for p in pts if p["Tc"] == 4 and p["Tosc"] == 0])
fig, ax = plt.subplots(figsize=(6.0, 4.2))
u = np.array(uni); o = np.array(ours_curve)
ax.plot(u[:,0], u[:,1], "s-", color="#ff7f0e", ms=5, label="равномерный масштаб (V3)")
ax.plot(o[:,0], o[:,1], "o-", color="#2ca02c", ms=5, label="наш метод (концентр. драйва)")
ax.scatter([B1["E_mj"]], [B1["otsu"]], s=120, marker="*", color="red", zorder=6, label="заводский B1 (быстрый)")
ax.scatter([B0["E_mj"]], [B0["otsu"]], s=80, marker="P", color="darkred", zorder=6, label="заводский B0 (полный)")
labels = ["наш: равный контраст", "наш: ε=0 (баланс)", "наш: ε-relaxed"]
for r, lab, mk in zip(our, labels, ["D", "v", "^"]):
    ax.scatter([r["E_mj"]], [r["otsu"]], s=90, marker=mk, color="#1f77b4", zorder=7,
               edgecolor="k", linewidth=0.5, label=lab)
ax.annotate("контраст полного\nзаводского при −63% E",
            xy=(our[0]["E_mj"], our[0]["otsu"]), xytext=(5.6, 0.27),
            fontsize=8, arrowprops=dict(arrowstyle="->", color="green"))
ax.set_xlabel("Энергия E, мДж"); ax.set_ylabel("Контраст (otsu_gap), сценарий halves")
ax.legend(fontsize=7.5, loc="lower right"); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(OUT/"pareto_energy_contrast.png"); plt.close(fig)

# --- Рис 4: разбивка энергии по фазам заводской waveform ---
fig, ax = plt.subplots(figsize=(5.0, 3.0))
phases = ["клир\n(15)", "осцилляция\n(90)", "финал.\nдрайв (15)", "settle\n(1)"]
frames = [15, 90, 15, 1]; colors = ["#1f77b4", "#d62728", "#2ca02c", "#7f7f7f"]
ax.bar(phases, frames, color=colors)
for i, f in enumerate(frames):
    ax.text(i, f+2, f"{100*f/121:.0f}%", ha="center", fontsize=9)
ax.set_ylabel("Кадров (∝ энергии)"); ax.set_title("Заводская waveform V3 (121 кадр)", fontsize=10)
fig.tight_layout(); fig.savefig(OUT/"phase_breakdown.png"); plt.close(fig)

print("Графики обновлены (otsu_gap):", [p.name for p in sorted(OUT.glob('*.png'))])
