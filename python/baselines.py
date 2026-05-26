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
from tqdm.auto import tqdm

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
    show_progress: bool = False  # tqdm-бар по поколениям (включать в notebook'ах)
    _rng: random.Random = field(default_factory=lambda: random.Random(42))

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    # ---- Инициализация --------------------------------------------------

    def _random_waveform(self) -> Waveform:
        """Случайный waveform с попыткой выполнить charge balance.

        Стратегия: для k>=2 генерируем k-1 свободных фаз случайно,
        затем подбираем последнюю (V_k, T_k) так, чтобы |sum V*T| было
        минимальным. Это не гарантирует строгое равенство, но повышает
        долю feasible индивидов в начальной популяции с ~0.3% до ~46%,
        что даёт NSGA-II реальный шанс работать (а не вырождаться в
        random-search).
        """
        k = self._rng.randint(1, self.k_eff_max)
        if k == 1:
            return Waveform(
                voltages=(self._rng.choice(self.voltages),),
                durations=(self._rng.choice(self.durations),),
                f_frame=self.f_frame,
            )
        # Свободные фазы 1..k-1
        v_list = [self._rng.choice(self.voltages) for _ in range(k - 1)]
        t_list = [self._rng.choice(self.durations) for _ in range(k - 1)]
        partial = sum(v * t for v, t in zip(v_list, t_list))
        # Подбираем (V_k, T_k), минимизирующие |partial + V_k·T_k|
        best_v, best_t, best_imb = self.voltages[0], self.durations[0], float("inf")
        for v in self.voltages:
            if v == 0:
                continue
            t_ideal = -partial / v
            for t in self.durations:
                imb = abs(partial + v * t)
                if imb < best_imb and abs(t - t_ideal) < 8:  # cap search
                    best_v, best_t, best_imb = v, t, imb
        v_list.append(best_v)
        t_list.append(best_t)
        return Waveform(voltages=tuple(v_list), durations=tuple(t_list), f_frame=self.f_frame)

    def _initialize_population(self) -> list[Individual]:
        return [Individual(waveform=self._random_waveform()) for _ in range(self.pop_size)]

    # ---- Fitness --------------------------------------------------------

    def _evaluate(self, ind: Individual, model: WaveformModel, z_init: float, z_target: float) -> None:
        E, G, tau = model.predict(ind.waveform, z_init, z_target)
        imbalance = abs(ind.waveform.charge_integral)
        if imbalance > self.charge_eps:
            ind.energy = 1e9
            ind.ghost = 1e9
            ind.latency = 1e9
        else:
            ind.energy = E
            ind.ghost = G
            ind.latency = tau

    def _evaluate_batch(self, inds: list[Individual], model: WaveformModel, z_init: float, z_target: float) -> None:
        """Векторизованная оценка популяции — если модель поддерживает batch."""
        if not hasattr(model, "predict_batch"):
            for ind in inds:
                self._evaluate(ind, model, z_init, z_target)
            return
        wfs = [ind.waveform for ind in inds]
        results = model.predict_batch(wfs, z_init, z_target)
        for ind, (E, G, tau) in zip(inds, results):
            imb = abs(ind.waveform.charge_integral)
            if imb > self.charge_eps:
                ind.energy = 1e9
                ind.ghost = 1e9
                ind.latency = 1e9
            else:
                ind.energy = float(E)
                ind.ghost = float(G)
                ind.latency = float(tau)

    # ---- Non-dominated sorting (Deb 2002 Algorithm 1) ------------------

    def _fast_non_dominated_sort(self, pop: list[Individual]) -> list[list[int]]:
        """NumPy-векторизованный non-dominated sort (Deb 2002).

        Строим матрицу доминирования (N×N) одним broadcast'ом — на 2 порядка
        быстрее двойного Python-цикла при N=100, M=3.
        """
        n = len(pop)
        objs = np.stack([ind.objectives for ind in pop])  # (N, M)
        # dominates[i, j] = (i доминирует j) ⟺ obj_i ≤ obj_j ∀ и obj_i < obj_j хотя бы для одной
        le = (objs[:, None, :] <= objs[None, :, :]).all(axis=2)
        lt = (objs[:, None, :] <  objs[None, :, :]).any(axis=2)
        dominates = le & lt  # (N, N) bool
        # Убираем диагональ (i==i)
        np.fill_diagonal(dominates, False)
        # domcount[i] = сколько индивидов доминируют над i
        domcount = dominates.sum(axis=0).astype(int).tolist()
        # S[i] = список j, над которыми i доминирует
        S = [np.where(dominates[i])[0].tolist() for i in range(n)]

        fronts: list[list[int]] = [[]]
        for p in range(n):
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
        self._evaluate_batch(pop, model, z_init, z_target)

        gen_iter = (
            tqdm(range(self.n_gen), desc="NSGA-II поколения", unit="ген.", leave=False)
            if self.show_progress else range(self.n_gen)
        )
        for gen in gen_iter:
            fronts = self._fast_non_dominated_sort(pop)
            for f in fronts:
                self._crowding_distance(f, pop)

            # Создаём потомков — batch evaluation
            offspring: list[Individual] = []
            while len(offspring) < self.pop_size:
                p1 = self._tournament_select(pop).waveform
                p2 = self._tournament_select(pop).waveform
                child_wf = self._mutate(self._crossover(p1, p2))
                offspring.append(Individual(waveform=child_wf))
            self._evaluate_batch(offspring, model, z_init, z_target)

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

        # Финальный фронт: только rank=0, отфильтровать infeasible (помеченные 1e9)
        final_fronts = self._fast_non_dominated_sort(pop)
        first_front = [pop[i] for i in final_fronts[0]]
        result = [
            ParetoPoint(energy=ind.energy, ghost=ind.ghost, latency=ind.latency, waveform_result=None)
            for ind in first_front
            if ind.energy < 1e8  # отбрасываем infeasible
        ]
        logger.info("NSGA-II done: %d points in final front", len(result))
        return result
