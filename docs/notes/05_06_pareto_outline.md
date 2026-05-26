# Outline: главы 5 (Алгоритм Парето-границы) + 6 (Симуляция)

**Дата:** 2026-05-26
**Plan:** `.ai-factory/plans/m5-pareto-algorithm.md`
**Цель документа:** зафиксировать ключевые проектные решения до начала кода и LaTeX-draft.

---

## 1. Формулировка задачи MOO (для § 5.1)

Используем обозначения главы 4 (Definitions 4.1-4.4).

**Дано:** `u = (V[k], T[k])_{k=0}^{K-1}` — waveform длины K, где `V[k] ∈ U_disc = {VSH1, VSH2, VSL, VCOM, 0}` и `T[k] ∈ T_disc ⊂ ℕ` (целые кадры, T ∈ {1, ..., T_max}).

**Цель состояния:** перевести пиксель из `z(0) = z_init` в `z(T) ≈ z_target`, где z — состояние ODE из § 3.

**Три критерия (минимизируются одновременно):**

```
E(u) = Σ_{k=0}^{K-1} ½ · C_eff · ΔV[k]² · f_frame · T[k]     [мДж]   (Lin 2024)
G(u) = ||z(T; u) − z_target||₁                                 [рефл. единицы]
τ(u) = Σ_{k=0}^{K-1} T[k] / f_frame                            [с]
```

**Ограничения (жёсткие):**
- ε-зарядовый баланс: `|Σ_k V[k] · T[k]| ≤ ε` (ε ≈ 0.05 В·с по § 4.3)
- структура bang-bang: `|{k : V[k] ≠ 0}| ≤ K_eff = 4` (по Theorem 4.1)
- допустимое управление: `V[k] ∈ U_disc`, `T[k] ∈ {1, ..., T_max}`

**Множество Парето-оптимальных решений:**
```
P* = { u ∈ U_feasible : ∄ u' ∈ U_feasible с (E(u'), G(u'), τ(u')) ≺ (E(u), G(u), τ(u)) }
```
где `≺` — покомпонентное доминирование с хотя бы одним строгим неравенством.

---

## 2. ε-constraint метод (для § 5.2, **`\label{sec:eps-constraint}` ставится здесь**)

**Идея:** двумерная сетка по `(ε_G, ε_τ)`, на каждом узле — задача `min_u E(u)` при ограничениях `G(u) ≤ ε_G`, `τ(u) ≤ ε_τ` + жёсткие из § 5.1.

**Псевдокод:**

```
INPUT:
  ε_G ∈ {ε_G^(1) < ... < ε_G^(N_G)}   — сетка ghost
  ε_τ ∈ {ε_τ^(1) < ... < ε_τ^(N_τ)}   — сетка latency
  z_init, z_target — пара состояний
  model — surrogate из § 6.1

OUTPUT:
  pareto_points — список точек (E, G, τ, u)

FOR (ε_G, ε_τ) IN grid:
  best_E := +∞;  best_u := None
  FOR K_eff IN {1, 2, 3, 4}:           # перебор активных фаз (Theorem 4.1)
    FOR (V_seq, T_seq) IN bang_bang_candidates(K_eff, U_disc, T_disc):
      IF NOT charge_balanced(V_seq, T_seq, ε): CONTINUE
      (E, G, τ) := model.predict(V_seq, T_seq, z_init, z_target)
      IF G ≤ ε_G AND τ ≤ ε_τ AND E < best_E:
        best_E := E;  best_u := (V_seq, T_seq)
  IF best_u IS NOT None:
    pareto_points.append((best_E, *, *, best_u))

RETURN filter_dominated(pareto_points)
```

**Размер пространства кандидатов:**
- |U_disc| = 5, K_eff ≤ 4 → ≤ 5⁴ = 625 V-последовательностей
- T_disc: возьмём T_max = 16 кадров (~ 320 мс при f_frame = 50 Гц), K_eff ≤ 4 → ≤ 16⁴ ≈ 65 тыс T-последовательностей
- ИТОГО ≤ 4·10⁷ кандидатов на одну (ε_G, ε_τ)-точку. С фильтром charge balance отсеивается ~80% → ~8·10⁶. На сетке 8×8 = 64 точки → ~5·10⁸ surrogate-вызовов.
- **Сразу ясно:** surrogate должен быть быстрым (<10 мкс/вызов) → spline, не ODE-интегрирование.
- **Оптимизация:** кэширование (V_seq → E_per_unit_T) сокращает в ~|T_disc|^K_eff раз.

---

## 3. Выбор surrogate-модели (для § 6.1)

**Решение: `scipy.interpolate.RegularGridInterpolator` (линейная интерполяция).**

**Обоснование:**

| Критерий | Spline (RegularGridInterpolator) | MLP (sklearn) |
|---|---|---|
| Размер калибровочного датасета | ~30-50 точек (V × T sweep из M3 BENCH_RUN) — структурированная сетка | требует ≥500 точек для обобщения |
| Скорость predict() | ~5 мкс | ~50-200 мкс |
| Воспроизводимость | детерминированная | зависит от random_state, init |
| Интерпретируемость | прямая (нет «чёрного ящика») | низкая |
| Подходит для thesis-defense | ★ да: «классический метод из Васильев гл. 10» | требует обсуждения архитектуры/обучения |
| Совместимость с ε-релаксацией (линейность ΔV → энергии) | ★ согласована с Lin 2024 | overkill |

**Архитектура surrogate (linearity exploit):**
- Декомпозиция отклика waveform на сумму вкладов одиночных фаз:
  ```
  E(waveform) = Σ_k e(V[k], T[k])           # spline e: (V, T) → ΔE
  Δz(waveform) = Σ_k δz(V[k], T[k], z_at_k) # spline δz: (V, T, z_in) → Δz
  τ(waveform) = Σ_k T[k] / f_frame          # тривиально
  ```
- `e(V, T)` — 2D spline (5 значений V × 16 значений T = 80 узлов)
- `δz(V, T, z_in)` — 3D spline (5 × 16 × 8 узлов = 640) — z_in дискретизуется на 8 уровней grayscale
- **Калибровка:** датасет из M3 + augmentation через `python/ode_sim.py` (быстро — 1000 ODE-симуляций ~ 10 сек).

**Cross-validation:** k-fold (k=5) по узлам сетки, метрика MAE на hold-out. Цель: MAE_E < 5%, MAE_Δz < 0.1 уровня grayscale.

---

## 4. Состав тест-набора (для § 6.3, 10 сценариев)

| # | Тип | Описание | from → to |
|---|---|---|---|
| 1 | Диагност. | Полная инверсия | WW (all-white) → BB (all-black) |
| 2 | Диагност. | Обратная инверсия | BB → WW |
| 3 | Диагност. | Промежуточный grayscale | GS0 → GS3 (mid-tone) |
| 4 | Диагност. | Чекерборд (high-freq) | uniform-gray → checkerboard 8×8 |
| 5 | Реалист. | Текст (русск.) | пустой → «тест M5» (PT Mono 24pt) |
| 6 | Реалист. | Простая геометрия | пустой → квадрат + круг |
| 7 | Реалист. | Bar chart | пустой → 5 столбцов разной высоты |
| 8 | Реалист. | Line art | пустой → схема стрелки/коробки |
| 9 | Реалист. | Низкоразрешённая фотография | пустой → cameraman 64×64 (бин.) |
| 10 | Реалист. | Градиент | пустой → горизонтальный 4-уровневый градиент |

Разрешение: **250×122 пикселя** (Waveshare 2.13"V4 native). Биты на пиксель: 1 (B/W) для сценариев 1-9; 2 (4-grayscale) для сценария 10.

**Файлы:** `tests/fixtures/scenarios/sc{01..10}_{name}.png` (pair фреймов в одном файле side-by-side, или два файла).

---

## 5. Сравнение с NSGA-II (для § 5.5 + § 6.4)

**Решение: собственная минимальная реализация в `python/baselines.py` (~200 строк, Deb 2002 Algorithm 1).**

**Обоснование:**
- `pymoo` — 30+ МБ зависимостей, неуместно для курсовой
- Собственная реализация: 200 строк, полный контроль, прямая ссылка на Deb 2002
- Соответствует стилю работы: «каждый метод, который мы используем, мы реализуем и понимаем»

**Архитектура:**
```
class NSGA2:
  def __init__(pop_size, n_gen, crossover_rate, mutation_rate)
  def initialize_population(scenario, K_max) → list[Waveform]  # случайные допустимые waveforms
  def crossover(parent_a, parent_b) → Waveform                  # single-point по фазам
  def mutate(individual) → Waveform                              # перебор V или Δ T
  def fast_non_dominated_sort(population) → list[list[int]]      # фронты F1, F2, ...
  def crowding_distance(front) → np.ndarray                      # стандарт
  def run(scenario, surrogate) → list[Waveform]                  # возвращает финальный фронт
```

Параметры: pop_size = 100, n_gen = 50, crossover_rate = 0.9, mutation_rate = 0.1 (Deb 2002 defaults).

**Метрики сравнения:**

1. **Hypervolume (HV):** объём области в (E, G, τ)-пространстве, доминируемой фронтом до reference point R = (E_max, G_max, τ_max) × 1.1.
2. **Inverted Generational Distance (IGD):** для каждой точки `p` объединённого фронта `P_combined = P_ours ∪ P_nsga2` → расстояние до ближайшей точки в `P_method`, среднее по `p ∈ P_combined`.

**Ожидаемый результат (теоретически):**
- Hypervolume(ours) ≥ Hypervolume(NSGA-II) (PMP-теорема гарантирует структурную оптимальность)
- IGD(ours) ≤ IGD(NSGA-II) (ближе к идеальному фронту)
- Время: NSGA-II — ~5000 surrogate-вызовов; наш — ~10⁷ (но кэшированных) ≈ соизмеримо

**Если ours ≺ NSGA-II не получается** (маловероятно, но возможно при ошибках калибровки) — фиксируем как открытый вопрос в § 5.5 и обсуждаем причины.

---

## 6. Forward-reference `\label{sec:eps-constraint}` (для § 4.6)

В тексте главы 4, § 4.6 (Следствие 3 и 4) есть две ссылки `\ref{sec:eps-constraint}` — пока резолвятся в «??».

**Где ставить label:** в `tex/chapters/05_algorithm.tex`, в начале **§ 5.2** «ε-constraint метод», сразу после `\section{...}`:
```latex
\section{Метод ε-ограничений}\label{sec:eps-constraint}
```

После `make build` (после задачи E1) ссылки `\ref{sec:eps-constraint}` в гл. 4 автоматически разрешаются в «5.2».

Verify в G1: `grep "??" dist/thesis.log | wc -l` должен быть 0 (или пусто).

---

## 7. Перечень рисунков

### Глава 5 (минимум 2 рисунка)

| ID | Файл | Тип | Описание |
|---|---|---|---|
| 5.1 | `tex/figures/diagrams/algorithm_flowchart.tex` | TikZ | Блок-схема: вход (z_init, z_target) → ε-сетка → PMP-перебор по K_eff → фильтр charge-balance → выбор min E → Парето-фронт |
| 5.2 | `tex/figures/plots/pareto_schematic.pdf` | matplotlib | Концептуальная схема Парето-фронта в 2D (E, G) с feasibility region и доминируемой областью |

### Глава 6 (минимум 4 рисунка)

| ID | Файл | Источник | Описание |
|---|---|---|---|
| 6.1 | `tex/figures/plots/optimal_waveform_example.pdf` | `notebooks/02_optimize.ipynb` | Найденный waveform для сценария GS0→GS3 vs заводской LUT B0, ось V/время |
| 6.2 | `tex/figures/plots/pareto_2d_E_G.pdf` | `notebooks/03_pareto.ipynb` | 2D проекция фронта (E, G), 10 сценариев цветом + точки B0/B1 |
| 6.3 | `tex/figures/plots/pareto_2d_E_tau.pdf` | `notebooks/03_pareto.ipynb` | 2D проекция (E, τ) |
| 6.4 | `tex/figures/plots/pareto_2d_G_tau.pdf` | `notebooks/03_pareto.ipynb` | 2D проекция (G, τ) |
| 6.5 | `tex/figures/plots/pareto_vs_nsga2.pdf` | `notebooks/03_pareto.ipynb` | Наш фронт vs NSGA-II на одном сценарии (например, BB→WW), цветные точки |
| 6.6 | `tex/figures/plots/sensitivity_heatmap.pdf` (опц.) | `notebooks/03_pareto.ipynb` | Heatmap чувствительности (E, G) к ±20% возмущению C_eff и τ_Stokes |

**ИТОГО:** 2 рисунка для гл. 5 + 4-5 рисунков для гл. 6 = **6-7 рисунков** новых в M5 (без учёта таблиц).

### Таблицы

| ID | Файл | Описание |
|---|---|---|
| 5.1 | inline | Сложность алгоритма vs NSGA-II: O(N_ε²·K·|U|) vs O(pop_size·n_gen·K·|U|) + место в памяти |
| 6.1 | `tex/tables/pareto_summary.tex` (генерируется из 03_pareto) | % улучшения по (E, G, τ) относительно B0 на 10 сценариях |

---

## 8. Резюме проектных решений (для одобрения)

1. **Surrogate:** RegularGridInterpolator (spline линейная) с декомпозицией на одно-фазные вклады. **Не MLP.**
2. **NSGA-II:** собственная минимальная реализация в `python/baselines.py`. **Не pymoo.**
3. **Тест-набор:** 10 сценариев: 4 диагност. (BB↔WW, GS0→GS3, чекерборд) + 6 реалистичных (текст, геометрия, bar chart, line art, фото-thumbnail, градиент) при 250×122.
4. **Метрики сравнения:** Hypervolume + IGD.
5. **ε-сетка:** 8×8 по `(ε_G, ε_τ)` = 64 точки на сценарий. Хват: `T_max = 16` кадров, `K_eff ≤ 4`.
6. **Forward-ref:** `\label{sec:eps-constraint}` ставится в § 5.2.
7. **Минимум figures:** 6-7 PDF + 2 таблицы.
8. **Sensitivity (§ 6.5):** опциональная, при недостатке времени — режется до одного абзаца.

---

## Открытые вопросы для пользователя

Только если у читателя есть возражения по любой из 8 позиций — указать какие. Иначе → переходим к фазе B.
