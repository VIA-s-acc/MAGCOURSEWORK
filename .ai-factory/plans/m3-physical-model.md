# M3. Physical Model Chapter — план третьего milestone

**Создан:** 2026-05-25
**Ветка:** main (без feature branch)
**Mode:** Full
**Plan slug:** `m3-physical-model`
**Дедлайн фазы:** ~2-3 недели

## Settings

- **Testing:** да — pytest на `python/ode_sim.py` (≥85% coverage). Это новый научный модуль с числовой работой, тесты критичны для воспроизводимости.
- **Logging:** verbose (DEBUG-level).
- **Docs:** skip (project = docs).
- **Approach:** outline → review → теория → калибровочный эксперимент → итог.
- **Commit strategy:** 4-5 commit-точек (A, B, C, D, E).

## Roadmap Linkage

- **Milestone:** `M3. Physical model chapter` (из ROADMAP.md)
- **Rationale:** прямая реализация — § 3 курсовой (физическая модель), плюс новый python-модуль `ode_sim.py` (требуется для M5/M6) и первый калибровочный эксперимент на собранном стенде (использует BENCH_RUN из M1).

## Research Context

Из `RESEARCH.md` Active Summary:
- Архитектура теории: каскад PDE → ODE → M1 (дискретный PMP) → M2 (Парето).
- В M3 строим PDE-уровень + редукции.
- Симулятор: S3 гибрид (ODE-физика + surrogate). ODE-часть — в M3 (это `python/ode_sim.py`); surrogate — в M5.
- Из конспектов: Yang 2021 (mechanisms + charge balance), Bert 2003 (DEP-ограничения чисто электрофоретики), Wang 2022 (Стокс), He 2020 (Стокс), Lin 2024 (P_peak формула).
- Калибровка: η, R, q, m по trace'ам BENCH_RUN.

## Tasks

### Phase A: outline главы 3 (2 задачи)

- [x] **A1 (Task #38)** — Outline в `docs/notes/03_model_outline.md` с 5 подразделами (3.1 микрокапсула + DEP-замечание, 3.2 PDE Nernst-Planck + Poisson, 3.3 mean-field редукция с 3 допущениями, 3.4 Стоксова форма с явным выводом v_∞ и τ_Stokes, 3.5 калибровка с Таблицей 3.1). ~10-12 cite. Visual budget: 2-3 рис + 1 табл параметров.
- [x] **A2 (Task #39)** ← A1 — Outline одобрен пользователем. Принято решение: **§ 3.2 расширен до полного вывода Nernst-Planck из первых принципов** (continuity + Stokes drag + Эйнштейн + Poisson) — для усиления математичности работы ВМК. Целевой объём § 3.2 увеличен 1.0 → 1.8 стр; глава 3 целиком ~6.5 стр.

### Phase B: теория + симулятор (3 задачи, B2+B3 параллельно с B1)

- [x] **B1 (Task #40)** ← A2 — Draft § 3.1-3.4 в `tex/chapters/03_model.tex` написан (~9 стр PDF, включая полный вывод NP из первых принципов). § 3.5 — заглушка для D1. PDF 35 стр (+9 vs M2 финал).
- [x] **B2 (Task #41)** ← A2 — `python/ode_sim.py` с классом `PixelOdeSim`. Поддержка overdamped (1st order) и full (2nd order) режимов. Методы: terminal_velocity, reflectance, simulate (LSODA), replay_lut (последовательность фаз). 175 строк.
- [x] **B3 (Task #42)** ← B2 — `tests/test_ode_sim.py` готов: 21 тест (валидация конструктора, reflectance с clipping и vectorize, overdamped + full режимы, terminal velocity по экспоненте, charge-balanced returns origin, replay_lut со skip нулевых фаз). Coverage `python/ode_sim.py` = 98%. Полный suite: 87 passed, total coverage 93%.

### Phase C: калибровочный эксперимент (3 задачи)

- [x] **C1 (Task #43)** ← B2 — `scripts/calibration_sweep.py` готов (240 строк). Sweep по 2 V × 4 TP × 10 repeats = 80 циклов BENCH_RUN. Оффлайн-проверка LUT прошла. CLI с argparse, CSV + meta.json output, configurable pattern.
- [ ] **C2 (Task #44)** ← C1 — **⏸ КРИТИЧЕСКАЯ PAUSE.** Пользователь запускает sweep на подключенном ESP32 (~5-10 мин), присылает CSV.
- [ ] **C3 (Task #45)** ← C2 — `notebook/01_calibration.ipynb` с обработкой CSV, фитингом Стокса, экстракцией параметров, plots в PDF.

### Phase D: § 3.5 + review (2 задачи)

- [ ] **D1 (Task #46)** ← B1 + C3 — Добавить § 3.5 (Калибровка) с Таблицей 3.1 и Рисунком 3.3.
- [ ] **D2 (Task #47)** ← D1 — **⏸ PAUSE** для review draft полной главы 3.

### Phase E: финализация (1 задача)

- [ ] **E1 (Task #48)** ← D2 + B3 — Final build, ROADMAP M3 → [x], апдейт RESEARCH с фактами калибровки.

## Commit Plan

| # | После задач | Сообщение | Проверка |
|---|---|---|---|
| 1 | A1, A2 | `docs(notes): outline for chapter 3 (physical model)` | outline одобрен пользователем |
| 2 | B1, B2, B3 | `feat(model): chapter 3 theory + ODE simulator + tests` | теория собрана, pytest зелёный |
| 3 | C1, C2, C3 | `feat(calibration): sweep script + notebook + fitted Stokes params` | params в JSON, plot в PDF |
| 4 | D1, D2 | `feat(thesis): § 3.5 calibration — fitted params in chapter 3` | глава 3 ~6 стр, все рисунки/таблицы |
| 5 | E1 | `chore(M3): close milestone` | ROADMAP обновлён |

## Risks & Mitigations

| Риск | Митигация |
|---|---|
| Sweep на стенде даёт зашумлённые данные | C3 обрабатывает 10 повторов на точку с усреднением + std. При s/n хуже 5 — увеличить n_repeats. |
| ODE-симулятор не сходится к данным стенда (большие residuals) | Это сигнал что наша модель неполна (DEP вклад, неучтённые нелинейности). § 3.5 явно обсуждает residuals и применимость модели. |
| Калибровочные параметры физически нереалистичны | Сравнение с типовыми из Wang 2022 / He 2020 (η ≈ 0.001-0.01 Pa·s, R ≈ 100-500 нм для пигментов). Большие расхождения → пересмотр модели. |
| Sweep сжигает панель из-за длительной работы | n_repeats=10 в C1 — разумно. INA219 контролирует ток. Между sweep'ами — sleep панели опкодом 0x04. |

## Done criteria

M3 закрыт когда:
- `tex/chapters/03_model.tex` написан полностью (5 разделов, ~6 стр).
- `python/ode_sim.py` + pytest зелёный с coverage ≥85%.
- `notebook/01_calibration.ipynb` запускается на собранных данных, выдаёт parameters JSON + PDF-plots.
- `data/calibration/sweep_*.csv` сохранён локально (не commit'ится из-за .gitignore).
- `data/calibration/fitted_params.json` commit'ится.
- `make build` → dist/thesis.pdf с заполненной главой 3.
- ROADMAP: M3 → [x], добавлен в Completed table.

## Next step after M3

`/aif-plan M4` (Main theorem proven) — глава 4 курсовой. Это центральная теоретическая глава с нашей структурной теоремой и её полным доказательством. Сроки M4 — ~3 недели.
