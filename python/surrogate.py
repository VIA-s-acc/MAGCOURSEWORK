"""Surrogate-модель отклика пикселя EPD на bang-bang waveform.

Реализует декомпозицию на одно-фазные вклады (см. outline § 3):

    E(waveform)  = Σ_k  e(V[k], T[k])
    Δz(waveform) = Σ_k  δz(V[k], T[k], z_at_start_of_phase_k)
    τ(waveform)  = Σ_k  T[k] / f_frame

где e() и δz() — линейные интерполяторы на регулярной сетке
(scipy.interpolate.RegularGridInterpolator). Состояние z трекается
последовательно через фазы, что воспроизводит динамику ODE из § 3.

Калибровка: либо из реальных измерений BENCH_RUN (M3), либо синтетически —
прогоном PixelOdeSim на сетке (V, T, z_in). Последнее — augmentation,
позволяющее обучить surrogate без огромного датасета со стенда.

Используется в:
- python/optimizer.py (быстрая оценка кандидатов в solve_pmp_slice)
- python/pareto.py (внешний цикл ε-constraint)
- notebooks/02_optimize.ipynb, notebooks/03_pareto.ipynb
- gl. 6 курсовой (§ 6.1 «Архитектура симулятора S3»)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from scipy.interpolate import RegularGridInterpolator

from python.optimizer import Waveform

if TYPE_CHECKING:
    from python.ode_sim import PixelOdeSim

logger = logging.getLogger(__name__)


@dataclass
class SurrogateModel:
    """Spline surrogate с раскладкой waveform-отклика на одно-фазные вклады.

    Атрибуты:
        voltages: упорядоченная сетка по V (узлы интерполяции).
        durations_frames: упорядоченная сетка по T (целые кадры).
        z_levels: упорядоченная сетка по z_in для δz-интерполятора.
        f_frame: частота кадров [Гц].
        e_grid: (|V|, |T|) — энергия фазы [мДж].
        dz_grid: (|V|, |T|, |z|) — Δz после фазы при стартовом z_in [рефл. единицы].
        z_clip: ограничение reflectance [rho_min, rho_max] для clip входа в δz.
    """

    voltages: tuple[float, ...]
    durations_frames: tuple[int, ...]
    z_levels: tuple[float, ...]
    f_frame: float = 50.0
    e_grid: np.ndarray = field(default_factory=lambda: np.empty(0))
    dz_grid: np.ndarray = field(default_factory=lambda: np.empty(0))
    z_clip: tuple[float, float] = (0.07, 0.40)
    _e_interp: object = None
    _dz_interp: object = None

    def __post_init__(self) -> None:
        if len(self.voltages) < 2:
            raise ValueError("voltages grid must have ≥ 2 nodes")
        if len(self.durations_frames) < 2:
            raise ValueError("durations grid must have ≥ 2 nodes")
        if len(self.z_levels) < 2:
            raise ValueError("z_levels grid must have ≥ 2 nodes")
        if self.f_frame <= 0:
            raise ValueError(f"f_frame must be positive, got {self.f_frame}")
        if list(self.voltages) != sorted(self.voltages):
            raise ValueError("voltages must be sorted ascending")
        if list(self.durations_frames) != sorted(self.durations_frames):
            raise ValueError("durations_frames must be sorted ascending")
        if list(self.z_levels) != sorted(self.z_levels):
            raise ValueError("z_levels must be sorted ascending")

    # ---- Калибровка ------------------------------------------------------

    def fit_from_ode_sim(self, sim: PixelOdeSim, c_eff_nF: float = 11.7, vcom: float = 0.0) -> None:
        """Заполнить e_grid и dz_grid прогоном ODE-симулятора на полной сетке.

        Параметры:
            sim: уже сконструированный PixelOdeSim (с откалиброванными
                mu_star, tau_star из M3).
            c_eff_nF: эффективная ёмкость пикселя [нФ] — для оценки энергии
                по формуле Lin 2024: E = ½·C·ΔV²·f·T.
            vcom: опорное напряжение для ΔV (обычно 0 = земля).
        """
        nV = len(self.voltages)
        nT = len(self.durations_frames)
        nZ = len(self.z_levels)

        self.e_grid = np.zeros((nV, nT))
        self.dz_grid = np.zeros((nV, nT, nZ))

        c_eff_F = c_eff_nF * 1e-9  # нФ → Ф

        logger.info("fit_from_ode_sim: grid %dV × %dT × %dZ = %d points", nV, nT, nZ, nV * nT * nZ)

        for i, V in enumerate(self.voltages):
            for j, T_frames in enumerate(self.durations_frames):
                T_sec = T_frames / self.f_frame
                # Энергия фазы (формула 4.13 курсовой): E = ½ C V² f T, где
                # V = (V_source - vcom) — амплитуда напряжения фазы от опорного
                # уровня vcom=0, f — частота кадров, T — длительность. E в мДж.
                # Размерность Ф·В²·Гц·с = Дж; функционал аддитивен по фазам.
                delta_V = V - vcom
                self.e_grid[i, j] = 0.5 * c_eff_F * delta_V * delta_V * self.f_frame * T_sec * 1e3

                for k, z_in in enumerate(self.z_levels):
                    # Преобразовать z_in (reflectance) в позицию x_in.
                    rho_min, rho_max = self.z_clip
                    x_in = sim.L * (z_in - rho_min) / (rho_max - rho_min)
                    x_in = float(np.clip(x_in, 0.0, sim.L))

                    sol = sim.simulate(
                        t_span=(0.0, T_sec),
                        u_func=lambda t, V=V: V,  # noqa: E731
                        x0=x_in,
                    )
                    z_out = float(sol["rho"][-1])
                    self.dz_grid[i, j, k] = z_out - z_in

        self._build_interpolators()
        logger.info("fit complete: e_grid mean=%.4f мДж, dz_grid mean=%.4f", self.e_grid.mean(), self.dz_grid.mean())

    def _build_interpolators(self) -> None:
        """Построить RegularGridInterpolator поверх e_grid и dz_grid."""
        if self.e_grid.size == 0 or self.dz_grid.size == 0:
            raise RuntimeError("grids are empty — call fit_from_ode_sim() first")
        self._e_interp = RegularGridInterpolator(
            (np.asarray(self.voltages), np.asarray(self.durations_frames, dtype=float)),
            self.e_grid,
            method="linear",
            bounds_error=False,
            fill_value=None,
        )
        self._dz_interp = RegularGridInterpolator(
            (np.asarray(self.voltages), np.asarray(self.durations_frames, dtype=float), np.asarray(self.z_levels)),
            self.dz_grid,
            method="linear",
            bounds_error=False,
            fill_value=None,
        )

    # ---- Predict ---------------------------------------------------------

    def predict(self, waveform: Waveform, z_init: float, z_target: float) -> tuple[float, float, float]:
        """Вернуть (E [мДж], G [||·||_1], τ [с]) для данного waveform."""
        if self._e_interp is None or self._dz_interp is None:
            raise RuntimeError("surrogate is not fitted; call fit_from_ode_sim() first")
        z_curr = z_init
        e_total = 0.0
        rho_min, rho_max = self.z_clip
        for V, T in zip(waveform.voltages, waveform.durations):
            e_phase = float(self._e_interp([[V, float(T)]])[0])
            z_clipped = float(np.clip(z_curr, rho_min, rho_max))
            dz_phase = float(self._dz_interp([[V, float(T), z_clipped]])[0])
            e_total += e_phase
            z_curr += dz_phase
        g = abs(z_curr - z_target)
        tau = waveform.total_time
        return (e_total, g, tau)

    def predict_batch(self, waveforms: list[Waveform], z_init: float, z_target: float) -> np.ndarray:
        """Векторизованный predict для пакета waveform'ов.

        Возвращает np.ndarray shape (N, 3) с колонками (E, G, τ).
        Существенно быстрее цикла из predict() — один вызов interp на пакет
        вместо отдельного на каждую фазу каждого waveform.
        """
        if self._e_interp is None or self._dz_interp is None:
            raise RuntimeError("surrogate is not fitted; call fit_from_ode_sim() first")
        N = len(waveforms)
        if N == 0:
            return np.empty((0, 3))

        # Длины могут различаться → padding по максимуму, маска активных фаз
        K_max = max(len(wf.voltages) for wf in waveforms)
        V_pad = np.zeros((N, K_max))
        T_pad = np.zeros((N, K_max))
        mask = np.zeros((N, K_max), dtype=bool)
        tau = np.zeros(N)
        for i, wf in enumerate(waveforms):
            k = len(wf.voltages)
            V_pad[i, :k] = wf.voltages
            T_pad[i, :k] = wf.durations
            mask[i, :k] = True
            tau[i] = wf.total_time

        rho_min, rho_max = self.z_clip
        # E аддитивна, не зависит от z → batch по (V, T) сразу для всех (i, k)
        pts_e = np.stack([V_pad.ravel(), T_pad.ravel()], axis=1)  # (N*K, 2)
        e_flat = self._e_interp(pts_e)  # type: ignore[operator]
        e_grid_per_phase = e_flat.reshape(N, K_max) * mask
        E = e_grid_per_phase.sum(axis=1)

        # Δz зависит от z_curr → по фазам последовательно, но батч по waveform
        z_curr = np.full(N, z_init)
        for k in range(K_max):
            active = mask[:, k]
            if not active.any():
                break
            z_clip = np.clip(z_curr, rho_min, rho_max)
            pts_dz = np.stack([V_pad[:, k], T_pad[:, k], z_clip], axis=1)
            dz = self._dz_interp(pts_dz)  # type: ignore[operator]
            z_curr = z_curr + np.where(active, dz, 0.0)

        G = np.abs(z_curr - z_target)
        return np.stack([E, G, tau], axis=1)

    # ---- Round-trip validation ------------------------------------------

    def evaluate_mae(self, sim: PixelOdeSim, test_waveforms: list[Waveform]) -> dict[str, float]:
        """MAE смещения reflectance между surrogate и прямым прогоном ode_sim.

        Энергия в обеих ветках — одна и та же аналитика, поэтому валидируется
        только смещение (δz), где surrogate использует интерполяцию таблицы, а
        ode_sim интегрирует ОДУ.
        """
        if not test_waveforms:
            raise ValueError("test_waveforms must be non-empty")

        z_err: list[float] = []
        rho_min = self.z_clip[0]
        for wf in test_waveforms:
            sol = sim.replay_lut(
                u_seq=[(V, T / wf.f_frame) for V, T in zip(wf.voltages, wf.durations)],
                x0=0.0,
            )
            z_true = float(sol["rho"][-1])
            z_surr = rho_min + sum(
                float(self._dz_interp([[V, float(T), rho_min]])[0])
                for V, T in zip(wf.voltages, wf.durations)
            )
            z_err.append(abs(z_surr - z_true))

        return {"mae_dz": float(np.mean(z_err))}
