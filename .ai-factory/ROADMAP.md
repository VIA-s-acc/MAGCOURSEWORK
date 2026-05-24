# Project Roadmap

> Магистерская курсовая ВМК МГУ: оптимизация обновления электрофоретического дисплея — каскадная теория (PDE → ODE → дискретный PMP → Парето) с одной структурной теоремой, реализацией в Python notebook и экспериментальной валидацией на стенде ESP32 + Waveshare 2.13" V4 (SSD1680) + INA219. Дедлайн — сентябрь-октябрь 2026.

## Milestones

- [ ] **M1. Foundation** — `.ai-factory/` + LaTeX-каркас по ГОСТ 7.32 (titlepage, разделы, ссылки, библиография через biblatex-gost); расширение прошивки ESP32 опкодом записи произвольного LUT через USB; прочитаны Васильев (гл. 1–5, 8 — методы оптимизации и теория экстремума), Понтрягин (гл. 1–3 — классический PMP), Phogat 2017 целиком (дискретный PMP). [Артефакт: `tex/thesis.tex` каркас, `firmware/epd_bridge.ino` обновлён, краткие заметки по прочитанному в `docs/notes/`.]

- [ ] **M2. Literature review locked** — все Wiley/Elsevier статьи из «Pending downloads» получены и прочитаны; gap analysis vs Kang 2025 написан явно; INSIGHT collection дополнена до ≥15 пунктов; библиография в bibtex с ≥25 проверенными ссылками. [Артефакт: `tex/introduction.tex`, `tex/review.tex`, `docs/refs/bibliography.bib`.]

- [ ] **M3. Physical model chapter** — PDE Nernst-Planck выписан с граничными условиями как управление; mean-field редукция к single-pixel ODE доказана; параметры η, R, q, m откалиброваны по серии измерений на стенде; работающий ODE-симулятор для одного пикселя в Python. [Артефакт: `tex/model.tex`, `notebook/01_calibration.ipynb`, `data/calibration/*.csv`.]

- [ ] **M4. Main theorem proven** — формулировка задачи как дискретной задачи оптимального управления с hard-constraint `Σ V·TP = 0`; основная структурная теорема («оптимум в классе charge-balanced waveforms — bang-bang с ≤K_eff активных фаз») сформулирована и доказана через дискретный PMP; полное доказательство с леммами; опционально — вторая теорема (нижняя оценка `E ≥ f(G, τ)`). [Артефакт: `tex/theorem.tex` с полным доказательством.]

- [ ] **M5. Pareto algorithm + simulator** — реализован алгоритм построения Парето-границы (ε-constraint + дискретный PMP по срезам); обучена surrogate-модель (NN/spline) для быстрой оптимизации; полный пайплайн `target → optimal waveform` в Python notebook; воспроизводимый Парето-фронт для тест-набора из ≥10 изображений; сравнение с NSGA-II как baseline-алгоритмом. [Артефакт: `tex/algorithm.tex`, `tex/simulation.tex`, `notebook/02_optimize.ipynb`, `notebook/03_pareto.ipynb`.]

- [ ] **M6. Experimental validation** — фотостанд готов (картонный кожух, LED-кольцо, USB-камера/iPhone, фиксированное расстояние); полный набор B0..B4 (Waveshare full / Waveshare fast / custom static / content-adaptive / temp+content-adaptive) измерен на ≥10 сценариях × ≥50 повторов; ImageJ-pipeline для извлечения SSIM/residual из фото; графики симулированного и измеренного Парето на одной координате; анализ расхождений. [Артефакт: `tex/experiment.tex`, `notebook/04_bench.ipynb`, `data/bench/*.csv`, `figures/pareto_sim_vs_stand.pdf`.]

- [ ] **M7. Thesis finalized** — введение и заключение дописаны под получившиеся результаты; библиография собрана через biblatex-gost; приложения (выдержки прошивки, структура notebook, полные таблицы LUT); проверены и закрыты все TODO; полная вычитка на отсутствие AI-маркеров и соответствие ГОСТ-стилю; единый `dist/thesis.pdf` собирается одной командой. [Артефакт: `dist/thesis.pdf`, ≈40 стр., все ссылки кликабельны и проверены.]

- [ ] **M8. Defense materials** — 15-слайдовая презентация (Beamer или PowerPoint) с ключевыми диаграммами из работы; speaker notes на 15-минутный доклад; список ожидаемых вопросов с ответами; опционально — 6-страничный препринт в SID-style формате для публикации. [Артефакт: `dist/presentation.pdf`, `dist/preprint.pdf` (опц.).]

## Completed

| Milestone | Date |
|-----------|------|

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
