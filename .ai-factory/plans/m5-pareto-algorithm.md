# M5. Pareto algorithm + simulator — план пятого milestone

**Создан:** 2026-05-26
**Ветка:** main (без feature branch)
**Mode:** Full
**Plan slug:** `m5-pareto-algorithm`
**Дедлайн фазы:** ~3-4 недели (фазы W8-W11 из ROADMAP)

## Settings

- **Testing:** да. Python-модули `optimizer.py`, `pareto.py`, `surrogate.py` покрываются pytest по образцу `python/ode_sim.py` (M3 → 21 тест).
- **Logging:** verbose (DEBUG для траектории оптимизации, INFO для прогресса по ε-сетке).
- **Docs:** skip (как в M2-M4: глава курсовой — самодостаточный документ; SKILL.md в `.ai-factory/skill-context/` не зависит от M5).
- **Approach:** outline (2 главы) → review → Python-инфраструктура (с тестами) → 2 notebook → 2 главы LaTeX → review → close.
- **Commit strategy:** 4 commit-чекпоинта.
- **Forward references:** Метка `\label{sec:eps-constraint}` ставится **в первой же задаче chapter 5** (§ 5.2), что автоматически закрывает «??» из § 4.6.

## Roadmap Linkage

- **Milestone:** `M5. Pareto algorithm + simulator` (из ROADMAP.md)
- **Rationale:** прямая реализация — две главы курсовой (5 «Алгоритм Парето-границы»
  + 6 «Симуляция и численные эксперименты», ~10 стр PDF) и два рабочих Python notebook
  (`02_optimize.ipynb` единичная задача + `03_pareto.ipynb` полный Парето-фронт по
  тест-набору). Это «переход от теории к вычислениям» — первый working pipeline
  `target → optimal waveform`, который дальше валидируется на стенде в M6.

## Research Context

Из `RESEARCH.md` Active Summary и Chapter Plan:
- M5 — уровень M2 в каскаде PDE → ODE → M1 (доказано в гл. 4) → **M2 (Парето)**.
- Алгоритм: ε-constraint метод (Васильев гл. 8) + дискретный PMP из теоремы 4.1 по
  каждому ε-срезу. Для каждой пары `(ε_G, ε_τ)` фиксируем ограничения и решаем
  задачу `min E(u)` через bang-bang структуру из теоремы 4.1
  (K_eff ≤ 4 фазы → конечный перебор кандидатов).
- Симулятор S3 (гибрид): ODE-модель из § 3 (через `python/ode_sim.py` — готов в M3)
  как «истина» + data-driven surrogate (spline или малый MLP) для быстрой оценки
  отклика на новый waveform без интегрирования ODE.
- Baseline для сравнения: NSGA-II (Deb 2002, `docs/refs/deb2002_nsga2.pdf` уже
  получен). Реализация — через библиотеку `pymoo` либо собственная (см. risks).
- Тест-набор: ≥10 сценариев (BB↔WW, чекерборд, текст, 5-6 реалистичных изображений).
- Численная связь с теоремой 4.2: проверить нижнюю границу `E ≥ K_lower·G ≈ 1.8 мДж/G`
  на построенном Парето-фронте; рассчитать «энергетический gap до оптимума».

## Tasks

### Phase 0: Закрытие M4 (housekeeping, 1 задача)

- [ ] **Z1** — Закрыть M4: завершить D1 (review pause неявно одобрен пользователем переходом к M5), выполнить E1 (`make build` + ROADMAP: M4 → [x] + строка `M4. Main theorem proven | 2026-05-26` в Completed table). Опц. INSIGHT в RESEARCH.md «процесс доказательства гл. 4: ε-релаксация разблокировала Theorem 4.2». Один commit: `chore(M4): close milestone`.

### Phase A: Outline двух глав (2 задачи)

- [ ] **A1** ← Z1 — Outline в `docs/notes/05_06_pareto_outline.md` для глав 5 и 6 (~300-400 строк). Включает: (а) точную формулировку задачи MOO в обозначениях гл. 4, (б) псевдокод ε-constraint + PMP, (в) проектные решения по surrogate (spline vs MLP — выбрать одно с обоснованием), (г) структуру тест-набора (10 сценариев списком), (д) дизайн сравнения с NSGA-II (общая координатная плоскость, метрики hypervolume + IGD), (е) расположение `\label{sec:eps-constraint}` (§ 5.2), (ж) перечень рисунков (≥2 для гл. 5, ≥4 для гл. 6 — из Chapter Plan: блок-схема алгоритма, Парето-схема, фронт 2D × 3 проекции, 3D-облако, ghost evolution, energy distribution).
- [ ] **A2** ← A1 — **⏸ PAUSE** для review outline пользователем. Критическая остановка: фиксируем выбор surrogate (spline/MLP), состав тест-набора, способ сравнения с NSGA-II до начала кода.

### Phase B: Python-инфраструктура оптимизации (3 задачи)

- [ ] **B1** ← A2 — `python/optimizer.py` (~200 строк): функция `solve_pmp_slice(target_z, eps_G, eps_tau, model_params) → WaveformResult`. Реализует дискретный PMP из § 4.4: перебор bang-bang кандидатов с ≤K_eff=4 активными фазами, фильтр по ε-зарядовому балансу (|Σ V·T| ≤ ε), минимизация E. Возвращает оптимальный waveform + достижимые (E, G, τ). Verbose logging: DEBUG для каждого кандидата, INFO для финального выбора. Тесты в `tests/test_optimizer.py`: (а) единичная PMP-задача с известным аналитическим ответом, (б) проверка charge-balance в выходе, (в) проверка K_eff ≤ 4. **Target: ≥5 тестов, all green.**
- [ ] **B2** ← B1 — `python/surrogate.py` (~150 строк): класс `SurrogateModel` с методами `fit(calibration_data)` и `predict(waveform) → (E, G, τ)`. Согласно выбору в A1: либо `scipy.interpolate.RegularGridInterpolator` (spline), либо `sklearn.neural_network.MLPRegressor` (NN, малый — 2 слоя × 16 нейронов). Калибровка — на данных из BENCH_RUN, собранных в M3. Тесты в `tests/test_surrogate.py`: (а) обучение на синтетических данных + проверка точности на hold-out, (б) reproducibility (фикс random_state). **Target: ≥3 теста.**
- [ ] **B3** ← B2 — `python/pareto.py` (~150 строк): функции `build_pareto_frontier(targets, eps_grid, surrogate) → list[ParetoPoint]` (внешний цикл ε-constraint) и `hypervolume(points, ref_point) → float` для сравнения с NSGA-II. Использует `optimizer.solve_pmp_slice` внутри. Параллелизация по ε-сетке через `concurrent.futures.ProcessPoolExecutor` (опц.). Тесты: (а) Парето на тривиальном случае с известным фронтом, (б) недоминируемость каждой точки, (в) монотонность hypervolume при расширении сетки. **Target: ≥4 теста.**

### Phase C: Notebook оптимизации (1 задача)

- [ ] **C1** ← B3 — `notebooks/02_optimize.ipynb`: end-to-end пример «единичный target → оптимальный waveform». Загружает калибровочные данные, обучает surrogate, решает одну PMP-задачу для конкретного перехода (например, GS0→GS3), визуализирует найденный waveform vs заводской LUT (B0). Сохраняет рисунок `tex/figures/plots/optimal_waveform_example.pdf` (~12×4 см) для гл. 6. Markdown-ячейки на русском с пояснениями на 2-3 абзаца. Структура: 6-8 ячеек кода + текст.

### Phase D: Notebook Парето-фронта (1 задача)

- [ ] **D1** ← C1 — `notebooks/03_pareto.ipynb`: построение Парето-фронта на тест-наборе из ≥10 сценариев. Сетка по ε (например, 8×8 = 64 точки). Сравнение с NSGA-II (через `pymoo` либо own — см. risks). Метрики: hypervolume, IGD. Графики (сохраняются как PDF в `tex/figures/plots/`): (а) `pareto_2d_E_G.pdf`, (б) `pareto_2d_E_tau.pdf`, (в) `pareto_2d_G_tau.pdf`, (г) `pareto_3d.pdf`, (д) `pareto_vs_nsga2.pdf`, (е) `energy_distribution.pdf`. Таблица «% улучшения по каждой оси относительно B0» — экспорт в `tex/tables/pareto_summary.tex` через pandas.to_latex(). **Target: фронт строго доминирует заводской LUT B0 (success signal из RESEARCH.md).**

### Phase E: Глава 5 LaTeX (1 задача)

- [ ] **E1** ← D1 — Заполнить `tex/chapters/05_algorithm.tex` (удалить «Заглушку», добавить ~5 стр согласно TODO-структуре). 5 секций:
  - § 5.1 Многокритериальная постановка (`\label{sec:moo-formulation}`)
  - § 5.2 ε-constraint метод (`\label{sec:eps-constraint}` — **разрешает forward-ref из § 4.6**)
  - § 5.3 Свойства Парето-фронта (монотонность по числу фаз, нижняя оценка через Theorem 4.2)
  - § 5.4 Псевдокод (algorithmic env) + оценки сложности O(N_ε² · K · |U|)
  - § 5.5 Сравнение с NSGA-II (Deb 2002) — таблица complexity и краткая дискуссия преимуществ структурной теоремы (см. INSIGHT I-16)
  - Минимум 2 рисунка: блок-схема алгоритма (TikZ) + образец Парето-фронта (из 03_pareto.ipynb).

### Phase F: Глава 6 LaTeX (1 задача)

- [ ] **F1** ← E1 — Заполнить `tex/chapters/06_simulation.tex` (~5 стр согласно TODO-структуре). 5 секций:
  - § 6.1 Архитектура симулятора S3 (ODE из § 3 + surrogate из B2)
  - § 6.2 Калибровочный pipeline (отсылка на M3 + дополнения)
  - § 6.3 Тест-набор (перечисление 10 сценариев, мотивация выбора)
  - § 6.4 Парето-фронт симулированный (4-6 рисунков из 03_pareto.ipynb + таблица)
  - § 6.5 Анализ чувствительности (как меняется фронт при возмущении калибровочных параметров ±20%) + численная проверка нижней границы Theorem 4.2.

### Phase G: Review (1 задача)

- [ ] **G1** ← F1 — **⏸ PAUSE** для review двух глав целиком + проверки рисунков и таблиц (вёрстка не плывёт, подписи по ГОСТ). Verify: `\ref{sec:eps-constraint}` в § 4.6 теперь резолвится (нет «??» в PDF).

### Phase H: Финализация (1 задача)

- [ ] **H1** ← G1 — Final `make build`, проверка `dist/thesis.pdf` (~58 стр суммарно: было 53 после M4 + ~10 за гл. 5 и 6 − небольшая экономия от слияния заглушек), ROADMAP: M5 → [x] + строка `M5. Pareto algorithm + simulator | <дата>` в Completed table. Обновить RESEARCH.md: 1-2 INSIGHT-карточки про численные находки (например, насколько Парето-фронт оптимизатора превзошёл заводской LUT; насколько близок к нижней границе Theorem 4.2).

## Commit Plan

4 commit-чекпоинта.

| # | После задач | Сообщение | Проверка |
|---|---|---|---|
| 1 | Z1 | `chore(M4): close milestone` | ROADMAP: M4 → [x] |
| 2 | A1, A2 | `docs(notes): outline chapters 5-6 (Pareto algorithm + simulator)` | outline одобрен пользователем |
| 3 | B1, B2, B3, C1, D1 | `feat(python): Pareto optimizer + surrogate + notebooks 02/03` | все тесты зелёные, notebooks выполняются end-to-end |
| 4 | E1, F1, G1, H1 | `feat(thesis): chapters 5-6 — Pareto algorithm and simulator + close M5` | `dist/thesis.pdf` ~58 стр, нет «??», ROADMAP закрыт |

## Risks & Mitigations

| Риск | Митигация |
|---|---|
| Surrogate-модель плохо обобщается на новые waveform (overfitting на калибровочный набор) | (а) cross-validation на этапе B2; (б) augmentation калибровочного набора синтетическими ODE-симуляциями (быстро через `python/ode_sim.py`); (в) fallback на чистый ODE-расчёт в гл. 6 без surrogate. |
| NSGA-II через `pymoo` тянет тяжёлый dependency | Альтернатива — собственная минимальная реализация NSGA-II (200 строк, классика — Deb 2002 алгоритм 1) в `python/baselines.py`. Решение фиксируется в A1. |
| Парето-фронт оптимизатора **не** доминирует заводской LUT (success signal не достигнут) | Анализ почему: (а) ошибки калибровки; (б) waveform-таблица SSD1680 имеет неучтённые ограничения (например, на repeat-count); (в) функционал J нуждается в перенормировке. Минимум добиться доминирования по 1-2 осям из 3 для содержательного результата. |
| Notebook 03_pareto.ipynb выполняется слишком долго (>10 мин) | (а) уменьшить сетку ε до 5×5; (б) кэширование результатов через `joblib.Memory`; (в) параллелизация через `ProcessPoolExecutor`. |
| Гл. 5 и 6 вместе раздуваются за 10 страниц (общий объём курсовой превышает 40 стр без учёта M6/M7) | Жёстко резать: § 5.5 NSGA-II сокращать до одной таблицы; § 6.5 sensitivity — до одного абзаца. Tight scope. |
| Forward-ref `\label{sec:eps-constraint}` ставится не там, где ожидалось чтение § 4.6 | Поставить **точно перед** алгоритмом ε-constraint в § 5.2 (как было обещано в гл. 4). Verify в G1. |

## Done criteria

M5 закрыт когда:
- `python/optimizer.py`, `python/surrogate.py`, `python/pareto.py` написаны, все тесты зелёные (≥12 новых тестов суммарно, общее покрытие пакета не падает ниже 85%).
- `notebooks/02_optimize.ipynb` и `notebooks/03_pareto.ipynb` выполняются end-to-end без ошибок (`jupyter nbconvert --execute`).
- `tex/chapters/05_algorithm.tex` и `tex/chapters/06_simulation.tex` написаны (~5+5 стр).
- `\label{sec:eps-constraint}` ставится в § 5.2; в PDF нет «??».
- ≥6 PDF-рисунков сохранены в `tex/figures/plots/`.
- Парето-фронт симуляции **доминирует** заводской LUT B0 хотя бы по 2 из 3 осей (E, G, τ) на ≥80% сценариев тест-набора.
- `make build` → `dist/thesis.pdf` ~58 стр, ROADMAP: M5 → [x], в Completed table.

## Next step after M5

`/aif-plan M6` (экспериментальная валидация на стенде) — глава 7 с протоколом
измерения, фотостанд для ghost, прогон baseline B0..B4 × 10 сценариев × 50 повторов,
сопоставление симулированного и измеренного Парето на одной координатной плоскости.
Это критический шаг — превращение симуляции в верифицированный результат.
