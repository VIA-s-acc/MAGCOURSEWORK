#!/usr/bin/env python3
"""Графики видео-эксперимента и partial-Парето для главы 7 (§7.8)."""
from __future__ import annotations
import json, sys
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "tex" / "figures" / "plots"
plt.rcParams.update({"font.size": 11, "figure.dpi": 130, "font.family": "DejaVu Sans"})

vid = json.loads((REPO/"data"/"bench"/"video"/"video_julia.json").read_text())["results"]
part = json.loads((REPO/"data"/"bench"/"partial"/"partial.json").read_text())["rows"]

LAB = {"full": "полное (B0)", "fac_partial": "заводский partial",
       "our_partial": "наш partial", "adaptive": "адаптивная"}
COL = {"full": "#d62728", "fac_partial": "#ff7f0e", "our_partial": "#2ca02c", "adaptive": "#1f77b4"}

# --- Рис A: кумулятивная энергия по кадрам ---
fig, ax = plt.subplots(figsize=(5.6, 3.6))
for pol, d in vid.items():
    ks = [r["k"] for r in d["rows"]]; cum = np.cumsum([r["E_mj"] for r in d["rows"]])
    ax.plot(ks, cum, "-o", ms=3, color=COL[pol], label=f"{LAB[pol]} (Σ={d['total_E_mj']:.0f} мДж)")
ax.set_xlabel("Кадр видео"); ax.set_ylabel("Накопленная энергия, мДж")
ax.legend(fontsize=8); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(OUT/"video_energy.png"); plt.close(fig)

# --- Рис B: качество (otsu) по кадрам ---
fig, ax = plt.subplots(figsize=(5.6, 3.4))
for pol, d in vid.items():
    ks = [r["k"] for r in d["rows"] if r["otsu"] is not None]
    ot = [r["otsu"] for r in d["rows"] if r["otsu"] is not None]
    ax.plot(ks, ot, "-o", ms=3, color=COL[pol], label=LAB[pol])
ax.set_xlabel("Кадр видео"); ax.set_ylabel("Контраст (otsu_gap)")
ax.legend(fontsize=8); ax.grid(alpha=.3)
fig.tight_layout(); fig.savefig(OUT/"video_quality.png"); plt.close(fig)

# --- Рис C: Парето partial — энергия и FPS от длительности ---
sc = np.array([r["scale"] for r in part]); E = np.array([r["energy_mj"] for r in part])
tau = np.array([r["latency_s"] for r in part]); fps = 1.0 / tau
fig, ax1 = plt.subplots(figsize=(5.6, 3.4))
ax1.plot(E, fps, "o-", color="#2ca02c")
for x, y, s in zip(E, fps, sc):
    ax1.annotate(f"×{s:.2f}", (x, y), fontsize=7, xytext=(3, 3), textcoords="offset points")
ax1.set_xlabel("Энергия на кадр, мДж"); ax1.set_ylabel("FPS (1/τ)")
ax1.axhline(1/0.27, ls=":", color="gray", lw=1)
ax1.text(E.max()*0.5, 1/0.27+0.05, "потолок панели", fontsize=7, color="gray")
ax1.grid(alpha=.3)
fig.tight_layout(); fig.savefig(OUT/"partial_pareto.png"); plt.close(fig)

print("Видео-графики:", [p.name for p in [OUT/'video_energy.png', OUT/'video_quality.png', OUT/'partial_pareto.png']])
