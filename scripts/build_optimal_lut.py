#!/usr/bin/env python3
"""Построение оптимальной waveform-LUT из модели M5 (главы 4-6 → глава 7).

Воспроизводимо связывает теорию с железом: калибрует surrogate по
data/calibration/fitted_params.json, решает ε-задачу теоремы 4.1
(min E при G≤ε_G, τ≤ε_τ, ε-зарядовый баланс) для полного Ч/Б-перехода,
переводит найденную bang-bang waveform в 153-байтную LUT SSD1680 и
сохраняет её в data/bench/optimal_lut.json (waveform + hex + метрики).

Эта LUT используется в scripts/run_bench_campaign.py как «наш метод»
(baseline B2..B4). Скрипт детерминирован и не требует железа.

Запуск:
    python scripts/build_optimal_lut.py
    python scripts/build_optimal_lut.py --eps-g 0.02 --eps-tau 0.5
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

# Bootstrap корня репозитория для запуска `python scripts/build_optimal_lut.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.lut import Lut
from python.ode_sim import PixelOdeSim
from python.optimizer import DEFAULT_DURATIONS, DEFAULT_VOLTAGES, solve_pmp_slice
from python.surrogate import SurrogateModel

logger = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parents[1]


def build_surrogate(params: dict) -> SurrogateModel:
    """Откалибровать surrogate по fitted_params.json (ODE-augmentation)."""
    mp = params["model_params"]
    sim = PixelOdeSim(
        mu_star=mp["mu_star_m_per_Vs"],
        tau_star=mp["tau_stokes_ms"] / 1000.0,
        L=mp["L_caps_um"] * 1e-6,
        rho_min=mp["rho_min"],
        rho_max=mp["rho_max"],
    )
    voltages = tuple(sorted(DEFAULT_VOLTAGES))          # (-15, 0, 5, 15)
    durations = tuple(DEFAULT_DURATIONS)                # 1..16
    z_levels = tuple(np.linspace(mp["rho_min"], mp["rho_max"], 5).tolist())
    sur = SurrogateModel(
        voltages=voltages, durations_frames=durations, z_levels=z_levels,
        f_frame=50.0, z_clip=(mp["rho_min"], mp["rho_max"]),
    )
    sur.fit_from_ode_sim(sim, c_eff_nF=mp["c_effective_pF"] / 1000.0)
    return sur


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--eps-g", type=float, default=0.02, help="порог ghosting G (рефл. ед.)")
    ap.add_argument("--eps-tau", type=float, default=0.5, help="порог латентности τ [с]")
    ap.add_argument("--out", default="data/bench/optimal_lut.json")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    params = json.loads((REPO / "data" / "calibration" / "fitted_params.json").read_text())
    rho_min, rho_max = params["model_params"]["rho_min"], params["model_params"]["rho_max"]

    sur = build_surrogate(params)

    # Полный переход «белый → чёрный» — самый энергоёмкий случай (worst-case
    # для оптимизации обновления): z_init = rho_max, z_target = rho_min.
    logger.info("Решаю ε-задачу: z %.3f -> %.3f, ε_G=%.3f, ε_τ=%.3f с",
                rho_max, rho_min, args.eps_g, args.eps_tau)
    best = solve_pmp_slice(
        z_init=rho_max, z_target=rho_min,
        eps_G=args.eps_g, eps_tau=args.eps_tau, model=sur,
    )
    if best is None:
        logger.error("Допустимой waveform не найдено — ослабьте ε_G/ε_τ")
        return 1

    wf = best.waveform
    logger.info("Оптимум: V=%s, T=%s, K_eff=%d | E=%.4f мДж, G=%.4f, τ=%.3f с",
                wf.voltages, wf.durations, wf.k_eff, best.energy, best.ghost, best.latency)

    lut = Lut.from_waveform(wf.voltages, wf.durations)
    errors = lut.validate(charge_tolerance=0.05)
    if errors:
        logger.warning("LUT validate замечания: %s", errors)
    encoded = lut.encode()
    cb = lut.charge_balance()

    out = {
        "source": "build_optimal_lut.py (M5 surrogate + PMP slice)",
        "transition": {"z_init": rho_max, "z_target": rho_min},
        "eps_g": args.eps_g, "eps_tau": args.eps_tau,
        "waveform": {
            "voltages": list(wf.voltages),
            "durations": list(wf.durations),
            "f_frame": wf.f_frame,
            "k_eff": wf.k_eff,
        },
        "predicted": {"energy_mj": best.energy, "ghost": best.ghost, "latency_s": best.latency},
        "charge_balance_vs": cb,
        "lut_hex": encoded.hex(),
        "validate_errors": errors,
    }
    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Сохранено: %s (charge=%.3e В·с)", out_path, cb)

    print("\n=== ОПТИМАЛЬНАЯ LUT ===")
    print(f"  V = {wf.voltages}")
    print(f"  T = {wf.durations} кадров")
    print(f"  K_eff = {wf.k_eff}")
    print(f"  E(pred) = {best.energy:.4f} мДж,  G = {best.ghost:.4f},  τ = {best.latency:.3f} с")
    print(f"  заряд = {cb:.3e} В·с (|·| ≤ 0.05 → сбалансирована)")
    print(f"  сохранено: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
