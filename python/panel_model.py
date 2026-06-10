"""Калиброванная по стенду ПАНЕЛЬНАЯ модель EPD-обновления + оптимизатор.

Заменяет прежний per-pixel суррогат (ошибочный масштаб энергии) панельной
моделью, откалиброванной по INA219 + фото (см. scripts/fit_model.py,
data/bench/calibrated_model.json):

  waveform w = (Tc, Tosc, Td) [кадры]: клир(реверс) + осцилляция + финальный драйв,
  N(w) = Tc + Tosc + Td + 1 (settle),
  E(w)   = E0 + kE·(V/Vref)²·N                        [мДж]
  τ(w)   = t0 + kτ·N                                  [с]
  C(w)   = Cmax·(1 − exp(−u/Th)),  u = Td + a·Tosc − b·Tc   [контраст]
  Q(w)   = V·(Td − Tc)   — чистый заряд set-LUT (DC-баланс; |Q|≤ε для долговечности)

Оптимизатор решает дискретную задачу теоремы 4.1 в редуцированном (bang-bang)
пространстве: min E(w) при C(w) ≥ C*, τ(w) ≤ τ_max, |Q(w)| ≤ ε, Tc ≥ Tc_min.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

_MODEL_PATH = Path(__file__).resolve().parents[1] / "data" / "bench" / "calibrated_model.json"


@dataclass(frozen=True)
class Waveform:
    """Bang-bang waveform: клир (реверс), осцилляция, финальный драйв [кадры]."""
    tc: int          # клир (фаза 0, реверсная полярность)
    tosc: int        # осцилляция (фаза 1, ±, активация) — суммарно кадров
    td: int          # финальный драйв (фаза 2, set-полярность)
    settle: int = 1  # пауза (фаза 3)

    @property
    def n_frames(self) -> int:
        return self.tc + self.tosc + self.td + self.settle


@dataclass(frozen=True)
class PanelModel:
    """Калиброванная модель E/τ/contrast/charge панели Waveshare 2.13 V4 (SSD1680)."""
    E0: float; kE: float; V_ref: float
    t0: float; kt: float; f_frame: float
    Cmax: float; Th: float; a_osc: float; b_clear: float

    @classmethod
    def load(cls, path: Path = _MODEL_PATH) -> "PanelModel":
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            E0=d["energy"]["E0_mj"], kE=d["energy"]["kE_mj_per_frame"], V_ref=d["V_ref"],
            t0=d["latency"]["t0_s"], kt=d["latency"]["kt_s_per_frame"],
            f_frame=d["latency"]["f_frame_hz"],
            Cmax=d["contrast"]["Cmax"], Th=d["contrast"]["Th"],
            a_osc=d["contrast"]["a_osc"], b_clear=d["contrast"]["b_clear"],
        )

    def energy(self, w: Waveform, v: float | None = None) -> float:
        v = self.V_ref if v is None else v
        return self.E0 + self.kE * (v / self.V_ref) ** 2 * w.n_frames

    def latency(self, w: Waveform) -> float:
        return self.t0 + self.kt * w.n_frames

    def _u(self, w: Waveform) -> float:
        return max(0.0, w.td + self.a_osc * w.tosc - self.b_clear * w.tc)

    def contrast(self, w: Waveform) -> float:
        return self.Cmax * (1.0 - math.exp(-self._u(w) / self.Th))

    def net_charge(self, w: Waveform, v: float | None = None) -> float:
        """Чистый заряд set-LUT (∝ долговечность). 0 = идеальный DC-баланс."""
        v = self.V_ref if v is None else v
        return v * (w.td - w.tc)

    def u_for_contrast(self, c_target: float) -> float:
        c = min(c_target, 0.999 * self.Cmax)
        return -self.Th * math.log(1.0 - c / self.Cmax)


def optimize(
    model: PanelModel,
    c_target: float,
    tau_max: float = 10.0,
    eps_charge: float = 1e9,
    tc_min: int = 0,
    use_osc: bool = False,
    td_max: int = 80,
) -> Waveform | None:
    """Дискретная оптимизация теоремы 4.1: min E при C≥C*, τ≤τ_max, |Q|≤ε, Tc≥Tc_min.

    Осцилляция доминируется (a_osc<1, та же цена) → по умолчанию Tosc=0.
    Перебор bang-bang (Tc, Td) — пространство мало благодаря структурной теореме.
    """
    eps_frames = eps_charge / model.V_ref  # |Td−Tc| ≤ eps_frames
    best: Waveform | None = None
    best_e = math.inf
    osc_range = range(0, 1) if not use_osc else range(0, 40, 2)
    for tosc in osc_range:
        for tc in range(tc_min, td_max + 1):
            for td in range(1, td_max + 1):
                if abs(td - tc) > eps_frames:
                    continue
                w = Waveform(tc=tc, tosc=tosc, td=td)
                if model.contrast(w) < c_target:
                    continue
                if model.latency(w) > tau_max:
                    continue
                e = model.energy(w)
                if e < best_e:
                    best_e, best = e, w
    return best
