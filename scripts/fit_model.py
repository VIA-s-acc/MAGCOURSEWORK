#!/usr/bin/env python3
"""Калибровка ПАНЕЛЬНОЙ модели по реальным замерам стенда (заменяет суррогат).

Старый суррогат считал энергию по-пиксельно (½CV², C≈12нФ → 0.01 мДж) —
ошибка ~1000×. Реальная энергия — панельного уровня. Здесь фитируем по
данным INA219 + фото:

  E(N)        = E0 + kE·(V/Vref)²·N        [мДж]   — линейна по числу кадров
  τ(N)        = t0 + kτ·N                   [с]
  contrast(w) = Cmax·(1 − exp(−u/Th)),  u = Td + a·Tosc − b·Tc   [эфф. set-драйв]

где waveform w = (Tc клир, Tosc осцилляция, Td финальный драйв), V=±15 В,
N = Tc + Tosc + Td + 1 (settle). Данные — из scripts/probe_phases.py и
scripts/test_known_lut.py (03_halves, новый ROI).

Сохраняет data/bench/calibrated_model.json (используется python/panel_model.py).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
REPO = Path(__file__).resolve().parents[1]

# Замороженный калибровочный датасет: реальные замеры стенда (V=±15, 03_halves),
# сведённые вручную из прогонов probe_phases.py / test_known_lut.py / measure_*.py.
# Сырьё рядом: data/bench/{phases,known_lut,final}/*.json (INA219-трассы + фото).
# Поля: (Tc, Tosc_total, Td, N, E_mj, tau_s, contrast); N = Tc+Tosc+Td+1(settle);
# Tosc_total — сумма кадров фазы осцилляции за все повторы.
# contrast — метрика otsu_gap (разрыв классов яркости по Оцу, alignment-free;
# выбрана эмпирически в scripts/eval_metrics.py).
DATA = [
    # name        Tc  Tosc  Td   N    E       tau     otsu_gap
    ("full",      15,  90,  15, 121, 12.327, 2.685, 0.3919),
    ("rp1",       15,  60,  15,  91,  9.688, 2.086, 0.3924),
    ("rp0",       15,  30,  15,  61,  7.153, 1.487, 0.3845),
    ("rp0_s8",    15,  16,  15,  47,  6.053, 1.208, 0.3783),
    ("rp0_s4",    15,   8,  15,  39,  5.420, 1.048, 0.3635),
    ("noosc",     15,   0,  15,  31,  4.712, 0.889, 0.3304),
    ("noosc_s10", 10,   0,  10,  21,  3.703, 0.689, 0.3061),
    ("final_hv",   6,   0,  22,  29,  4.429, 0.849, 0.3890),
    ("drive_lng", 25,   0,  25,  51,  6.802, 1.288, 0.3679),
    # Прямая кривая contrast(Td) при малом клире Tc=4 (пин насыщения):
    ("td04",       4,   0,   4,   9,  2.453, 0.450, 0.1710),
    ("td06",       4,   0,   6,  11,  2.607, 0.490, 0.2693),
    ("td08",       4,   0,   8,  13,  2.830, 0.530, 0.3159),
    ("td10",       4,   0,  10,  15,  3.010, 0.569, 0.3382),
    ("td14",       4,   0,  14,  19,  3.412, 0.649, 0.3893),
    ("td18",       4,   0,  18,  23,  3.811, 0.729, 0.3769),
    ("td22",       4,   0,  22,  27,  4.224, 0.809, 0.4104),
    ("td30",       4,   0,  30,  35,  4.996, 0.969, 0.3956),
]


def main() -> int:
    names = [d[0] for d in DATA]
    Tc = np.array([d[1] for d in DATA], float)
    Tosc = np.array([d[2] for d in DATA], float)
    Td = np.array([d[3] for d in DATA], float)
    N = np.array([d[4] for d in DATA], float)
    E = np.array([d[5] for d in DATA], float)
    tau = np.array([d[6] for d in DATA], float)
    con = np.array([d[7] for d in DATA], float)

    def r2(y, yhat):
        return 1 - np.sum((y - yhat) ** 2) / np.sum((y - np.mean(y)) ** 2)

    # --- E(N) и τ(N): линейные (V=±15 для всех) ---
    (kE, E0) = np.polyfit(N, E, 1)
    (kt, t0) = np.polyfit(N, tau, 1)
    print(f"E(N)   = {E0:.3f} + {kE:.4f}·N   мДж   (R²={r2(E, kE*N+E0):.4f})")
    print(f"τ(N)   = {t0:.4f} + {kt:.5f}·N   с    (R²={r2(tau, kt*N+t0):.4f})")
    print(f"f_frame = {1/kt:.1f} Гц")

    # --- contrast(Tc,Tosc,Td): насыщение по эфф. set-драйву u = Td + a·Tosc − b·Tc ---
    def model(X, Cmax, Th, a, b):
        tc, tosc, td = X
        u = np.clip(td + a * tosc - b * tc, 0, None)
        return Cmax * (1 - np.exp(-u / Th))

    p0 = [0.40, 12.0, 0.3, 0.3]
    popt, _ = curve_fit(model, (Tc, Tosc, Td), con, p0=p0,
                        bounds=([0.3, 1, 0, 0], [0.6, 100, 2, 2]), maxfev=20000)
    Cmax, Th, a, b = popt
    pred = model((Tc, Tosc, Td), *popt)
    print(f"\ncontrast = {Cmax:.4f}·(1−exp(−u/{Th:.2f})),  u = Td + {a:.3f}·Tosc − {b:.3f}·Tc")
    print(f"   R²={r2(con, pred):.4f},  max|resid|={np.max(np.abs(con-pred)):.4f}")
    print(f"\n{'name':>11} {'con_meas':>9} {'con_pred':>9} {'resid':>7}")
    for i, nm in enumerate(names):
        print(f"{nm:>11} {con[i]:>9.4f} {pred[i]:>9.4f} {con[i]-pred[i]:>+7.4f}")

    model_json = {
        "source": "fit_model.py (стенд: probe_phases + test_known_lut, 03_halves, ROI 2026-06-05)",
        "V_ref": 15.0,
        "energy": {"E0_mj": float(E0), "kE_mj_per_frame": float(kE),
                   "r2": float(r2(E, kE*N+E0))},
        "latency": {"t0_s": float(t0), "kt_s_per_frame": float(kt),
                    "f_frame_hz": float(1/kt), "r2": float(r2(tau, kt*N+t0))},
        "contrast": {"metric": "otsu_gap", "Cmax": float(Cmax), "Th": float(Th),
                     "a_osc": float(a), "b_clear": float(b), "r2": float(r2(con, pred))},
        "data_points": [
            {"name": d[0], "Tc": d[1], "Tosc": d[2], "Td": d[3], "N": d[4],
             "E_mj": d[5], "tau_s": d[6], "contrast": d[7]} for d in DATA
        ],
    }
    out = REPO / "data" / "bench" / "calibrated_model.json"
    out.write_text(json.dumps(model_json, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nСохранено: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
