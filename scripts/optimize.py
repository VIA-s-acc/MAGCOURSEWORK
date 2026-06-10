#!/usr/bin/env python3
"""Запуск оптимизатора (теорема 4.1) над калиброванной моделью → наш оптимум.

Выдаёт:
  - рекомендованные waveform для целевого контраста при разных режимах ε-баланса;
  - Парето-фронт E↔контраст (наш метод) для сравнения с заводским и равномерным.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.panel_model import PanelModel, Waveform, optimize

REPO = Path(__file__).resolve().parents[1]

# Заводские точки (стенд, 03_halves): для сравнения.
FACTORY = {"B0_full": (10.4, 2.27, 0.367), "B1_fast": (8.34, 1.747, 0.372)}


def show(model: PanelModel, w: Waveform, tag: str) -> dict:
    e, t, c, q = model.energy(w), model.latency(w), model.contrast(w), model.net_charge(w)
    print(f"{tag:>22}: Tc={w.tc:>2} Tosc={w.tosc:>2} Td={w.td:>2} N={w.n_frames:>3} | "
          f"E={e:5.2f}мДж τ={t:5.3f}с C={c:.3f} Q={q:+.0f}В·кадр")
    return {"tag": tag, "tc": w.tc, "tosc": w.tosc, "td": w.td, "n": w.n_frames,
            "E_mj": e, "tau_s": t, "contrast": c, "charge": q}


def main() -> int:
    m = PanelModel.load()
    print(f"Модель: Cmax={m.Cmax:.3f}, Th={m.Th:.2f}, f={m.f_frame:.1f}Гц")
    print(f"Заводский B1: E=8.34мДж τ=1.747с C=0.372\n")

    c_star = 0.34   # цель ≈ 95% Cmax (≈91% заводского)
    print(f"=== Наш оптимум при C* = {c_star} ===")
    rows = []
    # Режим 1: ε-relaxed (макс. экономия, долговечность через периодич. сброс)
    w = optimize(m, c_star, eps_charge=1e9, tc_min=4)
    if w: rows.append(show(m, w, "наш (ε-relaxed, Tc≥4)"))
    # Режим 2: умеренный баланс ε=120 В·кадр (|Td−Tc|≤8)
    w = optimize(m, c_star, eps_charge=120, tc_min=4)
    if w: rows.append(show(m, w, "наш (ε=120, баланс)"))
    # Режим 3: строгий DC-баланс ε=0 (Td=Tc, безопасно бессрочно)
    w = optimize(m, c_star, eps_charge=0, tc_min=0)
    if w: rows.append(show(m, w, "наш (ε=0, сбаланс.)"))

    print("\n=== Сравнение с заводским B1 (C≈0.372, E=8.34, τ=1.747) ===")
    for r in rows:
        dE = 100 * (r["E_mj"] - 8.34) / 8.34
        dt = 100 * (r["tau_s"] - 1.747) / 1.747
        print(f"  {r['tag']:>22}: ΔE={dE:+5.1f}%  Δτ={dt:+5.1f}%  при C={r['contrast']:.3f}")

    # Парето-фронт нашего метода (ε-relaxed): C* от 0.20 до 0.357
    print("\n=== Парето-фронт (наш, ε-relaxed) ===")
    print(f"  {'C*':>5} {'Tc':>3} {'Td':>3} {'E_mj':>6} {'tau_s':>6}")
    pareto = []
    cstar = 0.20
    while cstar <= 0.356:
        w = optimize(m, cstar, eps_charge=1e9, tc_min=4)
        if w:
            pareto.append({"c": cstar, "tc": w.tc, "td": w.td,
                           "E_mj": m.energy(w), "tau_s": m.latency(w)})
            print(f"  {cstar:>5.2f} {w.tc:>3} {w.td:>3} {m.energy(w):>6.2f} {m.latency(w):>6.3f}")
        cstar += 0.02

    import json
    out = REPO / "data" / "bench" / "optimizer_result.json"
    out.write_text(json.dumps({"c_star": c_star, "optima": rows, "pareto": pareto},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nСохранено: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
