# M6. Experimental validation — план шестого milestone

**Создан:** 2026-05-26
**Ветка:** main (без feature branch)
**Mode:** Full
**Plan slug:** `m6-experimental-validation`
**Дедлайн фазы:** ~4 недели (W12-W15 из ROADMAP)
**Режим работы:** **поэтапный** — пользователь делает физические шаги (сборка стенда, фотографии, прогон измерений), AI отвечает за код, обработку, главу.

## Settings

- **Testing:** да (Python-модули обработки фото покрываются pytest).
- **Logging:** verbose.
- **Docs:** skip.
- **Commit strategy:** 5 commit-чекпоинтов (по концу каждой фазы).

## Roadmap Linkage

- **Milestone:** `M6. Experimental validation` (из ROADMAP.md)
- **Rationale:** реализация центральной экспериментальной главы (гл. 7,
  ~5-7 стр PDF) с прогоном 5 baseline × 10 сценариев × 50 повторов на
  реальном стенде, сравнением симулированного (M5) и измеренного
  Парето-фронта. Это **превращение симуляции в верифицированный результат**.

## Research Context (из RESEARCH.md)

- Стенд: ESP32 DevKit V1 (WROOM-32) + Waveshare 2.13"V4 (SSD1680) + INA219 (CJMCU, 0.1 Ω шунт).
- Прошивка `firmware/epd_bridge/epd_bridge.ino` готова, опкоды 0x01-0x0E включая `BENCH_RUN` (0x0E) для INA-трасс.
- Baseline-таксономия B0..B4 (RESEARCH.md):
  - **B0** Waveshare full (init + 0xF7) — заводская OTP-LUT
  - **B1** Waveshare fast (init_fast + 0xC7) — заводская при фейковой T=+6.25°C
  - **B2** Custom static — наш заранее посчитанный waveform через 0xC7
  - **B3** Content-adaptive — waveform по битовому diff фреймов
  - **B4** Temp+content-adaptive — то же + явная подмена температуры
- Метрики на стенде:
  - **E** = ∫U·I dt через INA219 (метод трапеций, 1.9..12 кГц, готово в M3)
  - **τ** = t(BUSY↓0) − t(0x20), timestamping на ESP32 (готово)
  - **G (формальная)** = (1/N)·Σ|reflect_actual − reflect_target|, через фото
  - **G (отчётная)** = 1 − SSIM(target, rendered), через фото
- Фотостанд — пользователь собирает физически (картонный кожух, LED-кольцо или постоянная засветка, USB-камера/iPhone, фиксированное расстояние).

## Tasks

### Phase A: Физический стенд (пользователь делает, AI ждёт фотки)

- [ ] **A1** — **[ПОЛЬЗОВАТЕЛЬ]** Собрать фотостанд: картонный кожух (закрыть EPD от внешнего света), источник постоянной засветки (LED-кольцо или окно с известной яркостью), USB-камера или iPhone закреплённые на фиксированном расстоянии (~15-20 см) перпендикулярно экрану. Зафиксировать ROI = область EPD (250×122 пикселя × масштабный коэффициент).
- [ ] **A2** — **[ПОЛЬЗОВАТЕЛЬ]** Сделать 3 фотографии стенда для гл. 7: (а) общий вид (стенд+EPD+ESP32+INA219+камера); (б) крупно EPD под кожухом; (в) пример снятого кадра (например, BB→WW при разной освещённости). Скинуть в `docs/inbox/`, я обработаю (crop/resize) и перенесу в `tex/figures/raw_photos/`.

### Phase B: Python-pipeline обработки фото (AI пишет)

- [ ] **B1** ← A2 — `python/photo_pipeline.py`: функции `load_capture(path) → np.ndarray` (RGB→grayscale, нормирование яркости), `extract_roi(image, ref_corners) → ndarray[H,W]` (perspective correction по 4 угловым маркерам или просто crop), `compute_ssim(actual, target) → float` (через `skimage.metrics.structural_similarity`), `compute_residual(actual, target) → float` (||·||₁ по нормированным reflectance). Тесты в `tests/test_photo_pipeline.py`: (а) round-trip SSIM=1 для идентичных, (б) residual < 0.05 для шумной копии. **Target: ≥4 теста.**
- [ ] **B2** ← B1 — `python/bench_protocol.py`: высокоуровневый pipeline `run_bench_scenario(bridge, scenario, baseline, n_repeats) → BenchResult` (один запуск). Использует `python/bridge.py` для опкодов, `python/ina219.py` для парсинга трасс, `python/photo_pipeline.py` для фото. Возвращает структуру с (E_mean, E_std, G_mean, tau_mean, raw_traces). Тесты: dry-run с mock bridge.

### Phase C: Тест-набор и измерительная кампания (пользователь прогоняет, AI помогает)

- [ ] **C1** ← B2 — Тест-набор: 10 пар изображений (frame_init, frame_target) в `tests/fixtures/scenarios/` PNG 250×122 1-bit (BB/WW + 8 реалистичных). Скрипт `scripts/prepare_scenarios.py` генерирует их детерминированно из текстов/геометрии (так чтобы любой мог воспроизвести).
- [ ] **C2** ← C1 — **[ПОЛЬЗОВАТЕЛЬ + AI]** Прогон полной измерительной кампании. AI: `scripts/run_bench_campaign.py` — обходит `5 baseline × 10 сценариев × 50 повторов = 2500 запусков`, для каждого: загрузить frame_init, заrefresh'ить, загрузить frame_target, refresh с выбранной waveform, прочитать INA-трассу, попросить пользователя сфотографировать, продолжить. **Кампания займёт ~2 часа.** Пользователь нажимает enter после каждой фотографии (или: фотограф автоматизирован через cv2.VideoCapture, если USB-камера подключена). Все данные сохраняются в `data/bench/<timestamp>/`.
- [ ] **C3** ← C2 — Постобработка: `scripts/process_bench_data.py` агрегирует все измерения, экспортирует `data/bench/<ts>/summary.json` со статистикой (mean/median/std по каждому baseline×сценарию).

### Phase D: Анализ симуляция vs стенд (AI делает)

- [ ] **D1** ← C3 — `scripts/compare_sim_vs_stand.py`: загружает Парето-фронт из M5 (через перезапуск `scripts/run_pareto.py` или из кэша JSON) и измеренные точки из кампании. Строит наложенные графики: (а) `pareto_sim_vs_stand.pdf` — 3 проекции 2D, (б) `bench_per_scenario.pdf` — bar chart по сценариям для каждого baseline. Считает coefficient of determination R² между предсказанным и измеренным E.
- [ ] **D2** ← D1 — Анализ расхождений: для каждой baseline-сценарии посчитать абсолютное и относительное отклонение (E_sim − E_stand)/E_stand. Найти выбросы (>2σ). Записать в `data/bench/<ts>/discrepancies.json` для гл. 7.

### Phase E: Глава 7 LaTeX + finalize (AI пишет)

- [ ] **E1** ← D2 — Заполнить `tex/chapters/07_experiment.tex` (~5-7 стр, удалить «Заглушку»). 5 секций: 7.1 аппаратный стенд (фото + схема подключения), 7.2 прошивка ESP32 (опкоды + измерительный pipeline), 7.3 фотостанд (фото + pipeline SSIM), 7.4 протокол + таблица результатов, 7.5 sim vs stand сравнение + анализ.
- [ ] **E2** ← E1 — **⏸ PAUSE** для review главы 7 пользователем.
- [ ] **E3** ← E2 — `make build` + ROADMAP M6 → [x] + Completed table + INSIGHT в RESEARCH.md о найденных расхождениях sim↔stand.

## Commit Plan

5 commit-чекпоинтов.

| # | После задач | Сообщение | Проверка |
|---|---|---|---|
| 1 | A1, A2 | `assets(thesis): фото стенда для главы 7` | 3 фото в `tex/figures/raw_photos/` |
| 2 | B1, B2 | `feat(python): photo pipeline + bench protocol` | тесты зелёные |
| 3 | C1, C2, C3 | `data(bench): полная измерительная кампания` | summary.json есть |
| 4 | D1, D2 | `feat(analysis): sim-vs-stand Парето + discrepancies` | 2 новых PDF |
| 5 | E1, E2, E3 | `feat(thesis): chapter 7 — experimental validation + close M6` | PDF ~72-75 стр, ROADMAP закрыт |

## Risks & Mitigations

| Риск | Митигация |
|---|---|
| Camera/iPhone фото даёт нестабильную яркость → SSIM шумит | Использовать ROI с белым калибровочным quadratom рядом с EPD, нормировать каждое фото по нему. |
| Кампания на 2500 запусков займёт >6 часов | Автоматизировать фотографирование через cv2.VideoCapture (если USB-камера). Уменьшить n_repeats до 30 при необходимости. |
| Custom waveform B2/B3/B4 не «проигрывается» (заводский LUT перезаписывается) | Уже решено: 0x22=0xC7 + 0x0B опкод, не вызывать 0x1A для B2-B3. Verify в первом тестовом запуске. |
| Симулированный фронт не совпадает с измеренным (R²<0.5) | Это интересный результат — обсудить пределы surrogate-модели; **не подгонять под сим**. Уровень B0 (заводской) должен по крайней мере совпадать в E. |
| Пользователь не сможет физически собрать стенд (нет картона / освещения) | Альтернатива: использовать iPhone в тёмной комнате с постоянной подсветкой LED-телефона. ROI по 4 углам через ArUco-маркеры. |
| Истирание панели за 2500 циклов | Waveshare 2.13"V4 спецификация: >1M обновлений. 2500 = 0.25% ресурса. Безопасно. |

## Done criteria

M6 закрыт когда:
- Все 5 baseline (B0..B4) измерены на 10 сценариях × минимум 30 повторов.
- `data/bench/<ts>/summary.json` содержит статистику.
- `pareto_sim_vs_stand.pdf` показывает наложение двух фронтов с осмысленной координатой (либо нормированной, либо в реальных единицах с явным calibration factor).
- `tex/chapters/07_experiment.tex` написан (~5-7 стр) с минимум 4 рисунками (фото стенда + sim-vs-stand + per-scenario bar) и 1 таблицей результатов.
- `dist/thesis.pdf` собирается, 0 undefined refs, ROADMAP: M6 → [x].

## Next step after M6

`/aif-plan M7` (Thesis finalized) — финальная сборка: введение/заключение под полученные результаты, библиография проверена, приложения, полная вычитка под GOST + AI-маркеры.

## ПОЭТАПНЫЙ ПОРЯДОК (для пользователя)

```
СЕЙЧАС → A1 (собери стенд) + A2 (3 фото в docs/inbox/)
        ↓
        ↓ AI делает B1, B2, C1
        ↓
        → C2 (вместе): запускаем кампанию, ты фотаешь после каждого refresh
        ↓
        ↓ AI делает C3, D1, D2, E1
        ↓
        → E2 (ты): прочитай главу 7
        ↓
        ↓ AI делает E3 (close)
```

**Первый шаг — твой:** собери фотостанд + сделай 3 фото.
