"""Baseline-алгоритмы для сравнения с нашим PMP-оптимизатором.

Содержит минимальную собственную реализацию NSGA-II (Deb 2002,
Algorithm 1), ~250 строк. Используется в § 5.5 и § 6.4 курсовой как
эволюционный baseline для построения Парето-фронта.

Алгоритмические детали (по Deb 2002):
- Fast Non-Dominated Sorting: O(M·N²) для M критериев, N особей.
- Crowding Distance: для каждой особи в фронте — мера «свободного места»
  вокруг неё в objective space.
- Binary Tournament Selection: турнир из 2-х особей, побеждает та, что
  в лучшем фронте; при равенстве — с большей crowding distance.
- Single-Point Crossover: точка случайно по фазам, обмен хвостами.
- Uniform Mutation: с вероятностью mutation_rate — случайная замена V или T.

Реализация **не использует numpy для эволюционных операций** (списки питона
быстрее на N≤200), только для оценки fitness через model.predict().

Используется в:
- notebooks/03_pareto.ipynb (сравнение нашего ε-constraint фронта с NSGA-II)
- gl. 5 курсовой (§ 5.5 «Сравнительный анализ с NSGA-II»)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field

import numpy as np

from python.optimizer import (
    DEFAULT_CHARGE_EPS,
    DEFAULT_DURATIONS,
    DEFAULT_F_FRAME,
    DEFAULT_K_EFF_MAX,
    DEFAULT_VOLTAGES,
    Waveform,
    WaveformModel,
)
from python.pareto import ParetoPoint

logger = logging.getLogger(__name__)


@dataclass
class Individual:
    """Особь в популяции NSGA-II: waveform + кэш fitness."""

    waveform: Waveform
    energy: float = float("inf")
    ghost: float = float("inf")
    latency: float = float("inf")
    rank: int = -1
    crowding: float = 0.0

    @property
    def objectives(self) -> np.ndarray:
        return np.array([self.energy, self.ghost, self.latency])


@dataclass
class NSGA2:
    """Минимальная NSGA-II по Deb et al. (2002), Algorithm 1.

    Атрибуты:
        pop_size: размер популяции (Deb default = 100).
        n_gen: число поколений (Deb default = 50).
        crossover_rate: вероятность single-point crossover (0.9).
        mutation_rate: вероятность мутации каждой фазы (0.1).
        voltages: дискретный алфавит напряжений.
        durations: дискретный алфавит длительностей (целые кадры).
        k_eff_max: верхняя граница на число фаз (по теореме 4.1 = 4).
        charge_eps: ε-зарядовый баланс (мягко: штраф в fitness).
        seed: random seed для воспроизводимости.
    """

    pop_size: int = 100
    n_gen: int = 50
    crossover_rate: float = 0.9
    mutation_rate: float = 0.1
    voltages: tuple[float, ...] = DEFAULT_VOLTAGES
    durations: tuple[int, ...] = DEFAULT_DURATIONS
    k_eff_max: int = DEFAULT_K_EFF_MAX
    charge_eps: float = DEFAULT_CHARGE_EPS
    f_frame: float = DEFAULT_F_FRAME
    seed: int = 42
    _rng: random.Random = field(default_factory=lambda: random.Random(42))

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    # ---- Инициализация --------------------------------------------------

    def _random_waveform(self) -> Waveform:
        k = self._rng.randint(1, self.k_eff_max)
        voltages = tuple(self._rng.choice(self.voltages) for _ in range(k))
        durations = tuple(self._rng.choice(self.durations) for _ in range(k))
        return Waveform(voltages=voltages, durations=durations, f_frame=self.f_frame)

    def _initialize_population(self) -> list[Individual]:
        return [Individual(waveform=self._random_waveform()) for _ in range(self.pop_size)]

    # ---- Fitness --------------------------------------------------------

    def _evaluate(self, ind: Individual, model: WaveformModel, z_init: float, z_target: float) -> None:
        E, G, tau = model.predict(ind.waveform, z_init, z_target)
        # Soft penalty за нарушение charge balance (вместо hard reject — стандарт для GA).
        imbalance = abs(ind.waveform.charge_integral)
        penalty = max(0.0, imbalance - self.charge_eps) * 100.0  # коэф. подобран эмпирически
        ind.energy = E + penalty
        ind.ghost = G + penalty
        ind.latency = tau

    # ---- Non-dominated sorting (Deb 2002 Algorithm 1) ------------------

    def _fast_non_dominated_sort(self, pop: list[Individual]) -> list[list[int]]:
        n = len(pop)
        S: list[list[int]] = [[] for _ in range(n)]
        domcount = [0] * n
        fronts: list[list[int]] = [[]]
        for p in range(n):
            for q in range(n):
                if p == q:
                    continue
                op = pop[p].objectives
                oq = pop[q].objectives
                if np.all(op <= oq) and np.any(op < oq):
                    S[p].append(q)
                elif np.all(oq <= op) and np.any(oq < op):
                    domcount[p] += 1
            if domcount[p] == 0:
                pop[p].rank = 0
                fronts[0].append(p)
        i = 0
        while fronts[i]:
            next_front: list[int] = []
            for p in fronts[i]:
                for q in S[p]:
                    domcount[q] -= 1
                    if domcount[q] == 0:
                        pop[q].rank = i + 1
                        next_front.append(q)
            i += 1
            fronts.append(next_front)
        return [f for f in fronts if f]

    # ---- Crowding distance ----------------------------------------------

    def _crowding_distance(self, front: list[int], pop: list[Individual]) -> None:
        if len(front) <= 2:
            for idx in front:
                pop[idx].crowding = float("inf")
            return
        for idx in front:
            pop[idx].crowding = 0.0
        for m in range(3):  # 3 objectives: E, G, τ
            front_sorted = sorted(front, key=lambda i: pop[i].objectives[m])
            pop[front_sorted[0]].crowding = float("inf")
            pop[front_sorted[-1]].crowding = float("inf")
            f_min = pop[front_sorted[0]].objectives[m]
            f_max = pop[front_sorted[-1]].objectives[m]
            if f_max - f_min < 1e-12:
                continue
            for k in range(1, len(front_sorted) - 1):
                prev_v = pop[front_sorted[k - 1]].objectives[m]
                next_v = pop[front_sorted[k + 1]].objectives[m]
                pop[front_sorted[k]].crowding += (next_v - prev_v) / (f_max - f_min)

    # ---- Selection / variation -----------------------------------------

    def _tournament_select(self, pop: list[Individual]) -> Individual:
        a, b = self._rng.sample(range(len(pop)), 2)
        ia, ib = pop[a], pop[b]
        if ia.rank < ib.rank:
            return ia
        if ib.rank < ia.rank:
            return ib
        return ia if ia.crowding > ib.crowding else ib

    def _crossover(self, p1: Waveform, p2: Waveform) -> Waveform:
        if self._rng.random() > self.crossover_rate or len(p1.voltages) < 2 or len(p2.voltages) < 2:
            return p1
        cut1 = self._rng.randint(1, len(p1.voltages) - 1)
        cut2 = self._rng.randint(1, len(p2.voltages) - 1)
        new_V = p1.voltages[:cut1] + p2.voltages[cut2:]
        new_T = p1.durations[:cut1] + p2.durations[cut2:]
        if len(new_V) > self.k_eff_max:
            new_V = new_V[: self.k_eff_max]
            new_T = new_T[: self.k_eff_max]
        if len(new_V) == 0:  # edge case
            return p1
        return Waveform(voltages=new_V, durations=new_T, f_frame=self.f_frame)

    def _mutate(self, wf: Waveform) -> Waveform:
        V_list = list(wf.voltages)
        T_list = list(wf.durations)
        for i in range(len(V_list)):
            if self._rng.random() < self.mutation_rate:
                V_list[i] = self._rng.choice(self.voltages)
            if self._rng.random() < self.mutation_rate:
                T_list[i] = self._rng.choice(self.durations)
        return Waveform(voltages=tuple(V_list), durations=tuple(T_list), f_frame=self.f_frame)

    # ---- Run -----------------------------------------------------------

    def run(self, model: WaveformModel, z_init: float, z_target: float) -> list[ParetoPoint]:
        """Запустить NSGA-II, вернуть финальный недоминируемый фронт.

        Возвращает список ParetoPoint (waveform_result=None — это baseline).
        """
        logger.info(
            "NSGA-II run: pop=%d, gen=%d, z=%.3f→%.3f, seed=%d",
            self.pop_size, self.n_gen, z_init, z_target, self.seed,
        )

        pop = self._initialize_population()
        for ind in pop:
            self._evaluate(ind, model, z_init, z_target)

        for gen in range(self.n_gen):
            fronts = self._fast_non_dominated_sort(pop)
            for f in fronts:
                self._crowding_distance(f, pop)

            # Создаём потомков
            offspring: list[Individual] = []
            while len(offspring) < self.pop_size:
                p1 = self._tournament_select(pop).waveform
                p2 = self._tournament_select(pop).waveform
                child_wf = self._mutate(self._crossover(p1, p2))
                child = Individual(waveform=child_wf)
                self._evaluate(child, model, z_init, z_target)
                offspring.append(child)

            # Объединение и selection топ-N по rank+crowding
            combined = pop + offspring
            combined_fronts = self._fast_non_dominated_sort(combined)
            new_pop: list[Individual] = []
            for f in combined_fronts:
                self._crowding_distance(f, combined)
                if len(new_pop) + len(f) <= self.pop_size:
                    new_pop.extend(combined[i] for i in f)
                else:
                    remaining = self.pop_size - len(new_pop)
                    sorted_f = sorted(f, key=lambda i: -combined[i].crowding)
                    new_pop.extend(combined[i] for i in sorted_f[:remaining])
                    break
            pop = new_pop

            if (gen + 1) % 10 == 0:
                best_E = min(ind.energy for ind in pop)
                logger.debug("gen=%d: best_E=%.4f мДж", gen + 1, best_E)

        # Финальный фронт: только rank=0
        final_fronts = self._fast_non_dominated_sort(pop)
        first_front = [pop[i] for i in final_fronts[0]]
        result = [
            ParetoPoint(energy=ind.energy, ghost=ind.ghost, latency=ind.latency, waveform_result=None)
            for ind in first_front
        ]
        logger.info("NSGA-II done: %d points in final front", len(result))
        return result
