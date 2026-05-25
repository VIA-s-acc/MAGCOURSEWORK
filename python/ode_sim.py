"""ODE-симулятор одного пикселя EPD на базе lumped Stokes-модели.

Реализует уравнения § 3.3-3.4 курсовой:

  Overdamped (по умолчанию):
    dx/dt = mu_star · U(t) / L

  Full (с инерцией, опц.):
    m · d²x/dt² = q·U(t)/L − 6πηR · dx/dt
    => dv/dt = (1/tau_star) · (mu_star · U(t)/L · L − v) — после нормировки

Параметры модели — эффективные комбинации (§ 3.4.5):
  mu_star (м/(В·с))   — электрофоретическая подвижность = q/(6πηRL)
  tau_star (с)         — стоксова постоянная времени = m/(6πηR)
  rho_min, rho_max     — границы reflectance
  L (м)                — расстояние между электродами (д_caps)

Используется в:
- notebook/01_calibration.ipynb (фит mu_star, tau_star по данным стенда)
- notebook/02_optimize.ipynb (оптимизация waveform)
- gl. 6 курсовой (симуляция Парето-фронта)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from scipy.integrate import solve_ivp

logger = logging.getLogger(__name__)


@dataclass
class PixelOdeSim:
    """Симулятор одного EPD-пикселя на ODE-уровне.

    Атрибуты:
        mu_star: эффективная электрофоретическая подвижность [м/(В·с)].
            v_terminal = mu_star · U / L.
        tau_star: время релаксации Стокса [с].
            Для overdamped режима роль не играет; для full — задаёт время выхода
            на terminal velocity.
        rho_min: reflectance при позиции x = 0 (все белые внизу).
        rho_max: reflectance при позиции x = L (все белые вверху).
        L: расстояние между электродами [м].
        mode: "overdamped" (1st order) или "full" (2nd order).
    """

    mu_star: float = 1.0e-9            # типовое для EPD: 10^-9 м/(В·с)
    tau_star: float = 30e-3            # 30 мс
    rho_min: float = 0.07
    rho_max: float = 0.40
    L: float = 40e-6                   # 40 мкм межэлектродный зазор
    mode: str = "overdamped"           # или "full"

    def __post_init__(self) -> None:
        if self.mode not in ("overdamped", "full"):
            raise ValueError(f"mode must be 'overdamped' or 'full', got {self.mode!r}")
        if self.tau_star <= 0:
            raise ValueError(f"tau_star must be positive, got {self.tau_star}")
        if self.L <= 0:
            raise ValueError(f"L must be positive, got {self.L}")
        if not (0 <= self.rho_min <= self.rho_max <= 1):
            raise ValueError(
                f"reflectance bounds invalid: 0 ≤ rho_min={self.rho_min} ≤ rho_max={self.rho_max} ≤ 1"
            )
        logger.debug(
            "PixelOdeSim init: mu_star=%.3e, tau_star=%.3e s, L=%.3e m, mode=%s",
            self.mu_star, self.tau_star, self.L, self.mode,
        )

    # ---- Базовые соотношения ---------------------------------------------

    def terminal_velocity(self, U: float) -> float:
        """v_∞ = mu_star · U / L  (формула 3.7 курсовой)."""
        return self.mu_star * U / self.L

    def reflectance(self, x: float | np.ndarray) -> float | np.ndarray:
        """Преобразование позиции в reflectance (формула 3.13 курсовой).

        Линейная карта: x=0 → rho_min, x=L → rho_max. За границами клипуется.
        """
        x_clipped = np.clip(x, 0.0, self.L)
        return self.rho_min + (self.rho_max - self.rho_min) * (x_clipped / self.L)

    # ---- ODE правые части ------------------------------------------------

    def _rhs_overdamped(self, t: float, y: np.ndarray, u_func: Callable[[float], float]) -> np.ndarray:
        """y = [x]. dx/dt = mu_star · U(t) / L."""
        U = u_func(t)
        return np.array([self.mu_star * U / self.L])

    def _rhs_full(self, t: float, y: np.ndarray, u_func: Callable[[float], float]) -> np.ndarray:
        """y = [x, v]. dx/dt = v; dv/dt = (terminal_v - v) / tau_star."""
        U = u_func(t)
        v_terminal = self.mu_star * U / self.L
        x, v = y[0], y[1]
        dxdt = v
        dvdt = (v_terminal - v) / self.tau_star
        return np.array([dxdt, dvdt])

    # ---- Public simulate -------------------------------------------------

    def simulate(
        self,
        t_span: tuple[float, float],
        u_func: Callable[[float], float],
        x0: float = 0.0,
        v0: float = 0.0,
        rtol: float = 1e-6,
        atol: float = 1e-9,
        max_step: float | None = None,
    ) -> dict[str, np.ndarray]:
        """Запустить интегрирование ODE.

        Параметры:
            t_span: (t_start, t_end) в секундах.
            u_func: callable t -> U (В), управляющее напряжение.
            x0: начальная позиция [м].
            v0: начальная скорость [м/с] (только для mode='full').
            rtol, atol: точности solve_ivp.
            max_step: максимальный шаг (помогает захватить быстрые переходы U).

        Возвращает:
            dict с полями t (1D np.ndarray, сек), x (1D, м), v (1D, м/с — для full,
            пусто для overdamped), rho (1D, reflectance).
        """
        if self.mode == "overdamped":
            y0 = np.array([x0])
            rhs = lambda t, y: self._rhs_overdamped(t, y, u_func)  # noqa: E731
        else:  # full
            y0 = np.array([x0, v0])
            rhs = lambda t, y: self._rhs_full(t, y, u_func)  # noqa: E731

        kwargs: dict = {
            "fun": rhs,
            "t_span": t_span,
            "y0": y0,
            "method": "LSODA",  # adaptive, хорошо для stiff/non-stiff mix
            "rtol": rtol,
            "atol": atol,
            "dense_output": False,
        }
        if max_step is not None:
            kwargs["max_step"] = max_step

        logger.debug(
            "simulate: t=[%.3e, %.3e], y0=%s, mode=%s",
            t_span[0], t_span[1], y0.tolist(), self.mode,
        )
        sol = solve_ivp(**kwargs)
        if not sol.success:
            raise RuntimeError(f"solve_ivp failed: {sol.message}")

        t = sol.t
        x = sol.y[0]
        v = sol.y[1] if self.mode == "full" else np.array([])
        rho = self.reflectance(x)

        logger.debug("simulate: %d steps, x_final=%.3e m, rho_final=%.4f", len(t), x[-1], rho[-1])
        return {"t": t, "x": x, "v": v, "rho": rho}

    # ---- LUT replay ------------------------------------------------------

    def replay_lut(
        self,
        u_seq: list[tuple[float, float]],
        x0: float = 0.0,
        v0: float = 0.0,
        n_eval_per_phase: int = 20,
    ) -> dict[str, np.ndarray]:
        """Прогнать последовательность (V, T) фаз через симулятор.

        Параметры:
            u_seq: список (V_phase, T_phase_s) — напряжение [В] и длительность [с] каждой фазы.
            x0, v0: начальные условия.
            n_eval_per_phase: число точек оценки на фазу для итогового вектора.

        Возвращает:
            dict с полями t, x, v, rho (вся waveform склеена).
        """
        if not u_seq:
            raise ValueError("u_seq must be non-empty")

        all_t: list[np.ndarray] = []
        all_x: list[np.ndarray] = []
        all_v: list[np.ndarray] = []

        t_offset = 0.0
        x_curr = x0
        v_curr = v0

        for phase_idx, (V, T) in enumerate(u_seq):
            if T <= 0:
                continue  # пропускаем нулевые фазы (TP=0)
            u_const = lambda t, V=V: V  # noqa: E731  — capture V by value
            sol = self.simulate(
                t_span=(0.0, T),
                u_func=u_const,
                x0=x_curr,
                v0=v_curr,
                max_step=T / max(n_eval_per_phase, 1),
            )
            phase_t = sol["t"] + t_offset
            all_t.append(phase_t)
            all_x.append(sol["x"])
            if self.mode == "full":
                all_v.append(sol["v"])
            x_curr = sol["x"][-1]
            v_curr = sol["v"][-1] if self.mode == "full" and len(sol["v"]) > 0 else 0.0
            t_offset += T

        t = np.concatenate(all_t)
        x = np.concatenate(all_x)
        v = np.concatenate(all_v) if self.mode == "full" else np.array([])
        rho = self.reflectance(x)

        logger.debug(
            "replay_lut: %d phases, total duration=%.3e s, %d points, x_final=%.3e",
            len(u_seq), t_offset, len(t), x[-1],
        )
        return {"t": t, "x": x, "v": v, "rho": rho}

    # ---- Convenience -----------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"PixelOdeSim(mu_star={self.mu_star:.3e}, tau_star={self.tau_star*1e3:.1f} ms, "
            f"L={self.L*1e6:.0f} мкм, mode={self.mode!r})"
        )
