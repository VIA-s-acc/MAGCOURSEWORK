# Project Roadmap

> Магистерская курсовая ВМК МГУ: оптимизация обновления электрофоретического дисплея — каскадная теория (PDE → ODE → дискретный PMP → Парето) с одной структурной теоремой, реализацией в Python notebook и экспериментальной валидацией на стенде ESP32 + Waveshare 2.13" V4 (SSD1680) + INA219. Дедлайн — сентябрь-октябрь 2026.

## Milestones

- [x] **M1. Foundation** — `.ai-factory/` + LaTeX-каркас по ГОСТ 7.32 (titlepage, разделы, ссылки, библиография через biblatex-gost, PT Mono для кириллической моноширинки); прошивка ESP32 epd_bridge.ino с опкодами 0x01-0x0E (включая dynamic LUT и INA219 BENCH_RUN); Python-пакет (bridge/lut/ina219/metrics) с pytest suite (66 tests, coverage 92%); literature notes (Васильев, Понтрягин, Paruchuri-Chatterjee, Моисеев) + notation map + proof sketch главной теоремы. Закрыт 2026-05-25.

- [x] **M2. Literature review locked** — 9 ключевых конспектов в `docs/notes/` (kang2025, lai2026, lin2024, he2020, wang2022, yang2021, zhong2026, comiskey1998, bert2003); главы 1 (введение, ~3 стр) и 2 (обзор, ~6 стр) написаны на русском в академическом стиле без AI-маркеров; gap analysis vs Kang 2025 явный (4 пробела → 4 решения); 19 проверенных bibtex-записей с biblatex-gost; INSIGHT collection до 16 пунктов. `make build` → 26-страничный PDF без unresolved cite. Закрыт 2026-05-25.

- [x] **M3. Physical model chapter** — глава 3 курсовой (~14 стр PDF) с полным выводом Пуассона-Нернста-Планка из первых принципов (continuity + Стокс + Эйнштейн + Пуассон), mean-field редукция PDE→ODE с 3 явными допущениями, аналитическое решение Стокса (v_∞, τ_Stokes), калибровка эффективных параметров по реальному sweep'у на стенде (VSH1: E=1.63 мДж/refresh, VSH2: 1.51 мДж, C_eff≈11.7 нФ). `python/ode_sim.py` (overdamped + full режимы, 175 строк) + 21 pytest. `scripts/calibration_sweep.py` (sweep V × TP × n_repeats) + `scripts/process_calibration.py` (фитинг). 2 PDF-рис калибровки. Закрыт 2026-05-25.

- [x] **M4. Main theorem proven** — глава 4 (~12 стр PDF) с формализацией дискретной задачи оптимального управления (4 Definition: waveform, ε-зарядовый баланс, bang-bang, K_eff), функционалом J = α·E + β·G + γ·τ (через формулу Lin 2024), ε-релаксацией зарядового баланса |Σ V·T| ≤ ε (~0.05 В·с по INA219), дискретным PMP Paruchuri & Chatterjee 2019. **Теорема 4.1** (структура: bang-bang с K_eff ≤ d_state + 2 = 4 фазы) доказана в 3 шагах через PMP + Лемма 4.1. **Теорема 4.2** (нижняя оценка энергии E* ≥ K_lower·G* ≈ 1.8 мДж/единица G) доказана через геометрию + интеграл напряжения + Lin 2024. 5 Corollary (оценка пространства поиска, He 2020 как частный случай d_state=1, превосходство над DP Kang 2025, применимость к Парето, сопоставление с Lin 2024 ≈30% от теоретического оптимума). Закрыт 2026-05-26.

- [x] **M5. Pareto algorithm + simulator** — главы 5 (Алгоритм Парето-границы, ~5 стр) и 6 (Симуляция, ~7 стр) написаны. `python/optimizer.py` (solve_pmp_slice — дискретный PMP), `python/surrogate.py` (RegularGridInterpolator + векторизованный predict_batch), `python/pareto.py` (build_pareto_frontier с pre-eval пулом), `python/baselines.py` (NSGA-II Deb 2002 с numpy-векторизованным non-dominated sort, smart-init по charge balance). 30 новых pytest (suite 117/117). Notebooks `02_optimize.ipynb` (один PMP-пример) и `03_pareto.ipynb` (полный фронт по 10 сценариям + NSGA-II сравнение). 7 PDF-figures + 2 LaTeX-таблицы в `tex/figures/plots/` и `tex/tables/`. **Глубокая ревизия:** симулированный B0 (4-фазный заводской waveform через тот же surrogate) для честного сравнения, ε_τ-сетка расширена до 0.7с для покрытия 4-фазных Парето-оптимумов, NSGA-II с hard-reject infeasible. **Perf:** 76с→2.7с (28× ускорение) через pre-eval пул + numpy broadcast non-dominated sort + ProcessPoolExecutor по сценариям. `\label{sec:eps-constraint}` в § 5.2 разрешил forward-ref из § 4.6. PDF 67 стр, 0 undefined refs. Закрыт 2026-05-26.

- [ ] **M6. Experimental validation** — фотостанд готов (картонный кожух, LED-кольцо, USB-камера/iPhone, фиксированное расстояние); полный набор B0..B4 (Waveshare full / Waveshare fast / custom static / content-adaptive / temp+content-adaptive) измерен на ≥10 сценариях × ≥50 повторов; ImageJ-pipeline для извлечения SSIM/residual из фото; графики симулированного и измеренного Парето на одной координате; анализ расхождений. [Артефакт: `tex/experiment.tex`, `notebook/04_bench.ipynb`, `data/bench/*.csv`, `figures/pareto_sim_vs_stand.pdf`.]

- [ ] **M7. Thesis finalized** — введение и заключение дописаны под получившиеся результаты; библиография собрана через biblatex-gost; приложения (выдержки прошивки, структура notebook, полные таблицы LUT); проверены и закрыты все TODO; полная вычитка на отсутствие AI-маркеров и соответствие ГОСТ-стилю; единый `dist/thesis.pdf` собирается одной командой. [Артефакт: `dist/thesis.pdf`, ≈40 стр., все ссылки кликабельны и проверены.]

- [ ] **M8. Defense materials** — 15-слайдовая презентация (Beamer или PowerPoint) с ключевыми диаграммами из работы; speaker notes на 15-минутный доклад; список ожидаемых вопросов с ответами; опционально — 6-страничный препринт в SID-style формате для публикации. [Артефакт: `dist/presentation.pdf`, `dist/preprint.pdf` (опц.).]

## Completed

| Milestone | Date |
|-----------|------|
| M1. Foundation | 2026-05-25 |
| M2. Literature review locked | 2026-05-25 |
| M3. Physical model chapter | 2026-05-25 |
| M4. Main theorem proven | 2026-05-26 |
| M5. Pareto algorithm + simulator | 2026-05-26 |

## Phase plan (target: ~20 weeks to October 2026)

| Phase | Weeks | Milestones |
|---|---|---|
| Setup | W1 | M1 |
| Theory groundwork | W2-W4 | M2, M3 |
| Main result | W5-W7 | M4 |
| Algorithm & simulation | W8-W11 | M5 |
| Experiment | W12-W15 | M6 |
| Finalize | W16-W18 | M7 |
| Defense prep | W19-W20 | M8 |

Detailed page-by-page Chapter Plan, INSIGHT collection и full Active Summary — в `.ai-factory/RESEARCH.md`.
