# M1. Foundation — план первого milestone

**Создан:** 2026-05-24
**Ветка:** main (без feature branch — пользователь предпочёл)
**Mode:** Full
**Plan slug:** `m1-foundation`

## Settings

- **Testing:** да — pytest на ключевые функции (`python/lut.py`, `python/ina219.py`, `python/metrics.py`, `python/bridge.py` через mock serial). Coverage цель ≥70% для python/ модулей.
- **Logging:** verbose — DEBUG-level в каждом python-модуле через `logging`; в прошивке — `Serial.printf` под `#ifdef DEBUG`.
- **Docs:** skipped — проект сам про документ (тезис в LaTeX); никаких отдельных docs-чекпоинтов не нужно. `/aif-implement` будет показывать `WARN [docs]`, что ок.
- **Commit strategy:** четыре commit-точки (A, B, C, D), см. Commit Plan ниже.

## Roadmap Linkage

- **Milestone:** `M1. Foundation` (из `.ai-factory/ROADMAP.md`)
- **Rationale:** этот план — прямая реализация M1: LaTeX-каркас по ГОСТ, расширенная прошивка ESP32 (опкоды 0x01-0x0E), Python скелет (bridge/LUT/INA219/metrics) с тестами, и первичные конспекты по классике оптимизации.

## Research Context

Из `.ai-factory/RESEARCH.md` (Active Summary):

> **Topic:** Магистерская курсовая ВМК МГУ — «Оптимизация обновления электрофоретического (E-Ink) дисплея: мат. модель, алгоритм управления и экспериментальная валидация».
>
> **Goal:** Разработать формальную мат. модель обновления EPD и оптимизирующий waveform-алгоритм, обеспечивающий компромисс «энергия ↔ ghosting ↔ скорость обновления ↔ ресурс панели», превосходящий заводской LUT. Подтвердить симуляцией (Python notebook) и физическим экспериментом на стенде ESP32 + Waveshare 2.13" V4 (SSD1680) + INA219.
>
> **Key decisions:** N2+N1 гибрид (свой алгоритм + структурная теорема), каскад PDE→ODE→M1(дискретный PMP)→M2(Парето), симулятор S3 (ODE+surrogate), метрики G2-residual + L3+L4, дедлайн сентябрь-октябрь 2026.

Полный контекст и Chapter Plan — в `.ai-factory/RESEARCH.md`.

## Tasks

### Phase A: LaTeX каркас по ГОСТ (4 задачи)

- [x] **A1 (Task #9)** — Создать структуру: `tex/{chapters,figures,bib}/`, `firmware/`, `python/`, `notebook/`, `tests/`, `dist/`, `scripts/`, `docs/notes/`. Прописать `.gitignore` для всех типичных временных файлов LaTeX, Python, Jupyter, dist/.
- [x] **A2 (Task #10)** ← A1 — `tex/thesis.tex`: документкласс с ГОСТ-полями, fontspec (XeLaTeX, Times New Roman), polyglossia (ru+en), biblatex с `style=gost-numeric`, hyperref, командой `\titulpage` по ГОСТ ВМК МГУ; `\include` всех chapter-стабов из A3.
- [x] **A3 (Task #11)** ← A2 — `tex/chapters/00..09_*.tex` (10 файлов), Makefile с целями `build`/`clean`/`watch`. `make build` собирает `dist/thesis.pdf` через `xelatex+biber+xelatex+xelatex`. Каждый chapter-стаб содержит `\chapter{}` и 1-2 параграфа TODO-placeholder из Chapter Plan.
- [x] **A4 (Task #12)** ← A1 — `tex/bib/bibliography.bib` с 16+ верифицированными ссылками из `RESEARCH.md` в bibtex-формате (ГОСТ Р 7.0.5-2008). Авторы — кириллица для русских книг. Итого 19 записей: 11 статей + 1 arXiv + 3 русских учебника + 3 datasheet/manual + 1 online code repo.

### Phase B: ESP32 firmware (3 задачи)

- [x] **B1 (Task #13)** — `firmware/epd_bridge.ino`: каркас Arduino (Serial 921600, SPI 10MHz, I²C 400kHz), диспетчер опкодов 0x01-0x0B по оригинальному описанию из исходного брифа. Ключевой фикс: 0x22=0xC7 для full, 0xCF для partial.
- [x] **B2 (Task #14)** ← B1 — добавить опкоды 0x0C `WRITE_LUT_DYNAMIC` (153 байта + refresh), 0x0D `WRITE_REGISTER` (произвольный регистр), 0x0E `BENCH_RUN` (LUT + image + N повторов + INA219 трасса).
- [x] **B3 (Task #15)** ← B2 — `firmware/README.md`: таблица опкодов с byte-layout, схема подключения (3 группы), инструкция по прошивке, заметка про «ключевой фикс», ссылка на референс waveshareteam/e-Paper.

### Phase C: Python пайплайн каркас (4 задачи)

- **C1 (Task #16)** — `pyproject.toml` с deps (numpy/scipy/matplotlib/pyserial/scikit-image/jupyterlab/pytest/pytest-cov/pandas/tqdm), `scripts/setup_env.sh` для одношагового setup через `uv sync` (или venv+pip как fallback).
- **C2 (Task #17)** ← C1 — `python/bridge.py`: класс `EpdBridge` с методами под каждый опкод, mock-friendly (принимает serial.Serial-like). Verbose logging.
- **C3 (Task #18)** ← C1 — `python/lut.py` (encode/decode 153 байт по Section 6.7 SSD1680, charge_balance validate), `python/ina219.py` (parser BENCH_RUN трасс + trapezoidal energy), `python/metrics.py` (SSIM, residual через scikit-image). Pure functions, тестируемые.
- **C4 (Task #19)** ← C2+C3 — `tests/test_*.py`: round-trip LUT, синтетический parser energy, SSIM identity, mock-bridge opcode tests. `pytest -v` зелёное, coverage ≥70%.

### Phase E: визуальный аппарат (1 задача, можно делать с A1)

- [x] **E1 (Task #24)** ← A1 — `tex/figures/` с подпапками (`diagrams/`, `plots/`, `raw_photos/`, `screenshots/`), `tex/figures/README.md` с figure budget по главам (taблица из RESEARCH.md → Chapter Plan → Visual budget). Это контрольный документ для отслеживания статуса визуалов (planned/raw_ready/final/in_thesis). Naming convention: `<chapter>_<short_name>.pdf` (например `03_capsule_diagram.pdf`, `07_stand_overview.jpg`).

### Phase D: чтение и заметки по теории (4 задачи, независимые между собой)

- **D1 (Task #20)** — извлечь главы Васильева 1-5,8 и Понтрягина 1-3 через `pdftotext`; структурированные конспекты в `docs/notes/vasiliev.md`, `docs/notes/pontryagin.md` (определения + теоремы + страницы).
- **D2 (Task #21)** — конспект Phogat 2017 целиком (31 стр.) и Моисеева главы 1-3; `docs/notes/phogat.md`, `docs/notes/moiseev.md`.
- **D3 (Task #22)** — `docs/notes/notation_map.md`: таблица соответствий обозначений (Phogat ↔ Понтрягин ↔ Васильев ↔ наша курсовая).
- **D4 (Task #23)** — `docs/notes/proof_sketches.md`: эскиз доказательства главной теоремы (bang-bang ≤K_eff в charge-balanced классе) на основе D1-D3. Если эскиз «не складывается» — флаг и корректировка формулировки до начала M4.

## Commit Plan

Четыре commit-чекпоинта, каждый — атомарный shippable артефакт.

| # | После задач | Сообщение | Что проверить перед commit |
|---|---|---|---|
| 1 | A1, A2, A3, A4, E1 | `chore(latex): bootstrap thesis skeleton + figure budget (ГОСТ 7.32)` | `make build` собирает пустой `dist/thesis.pdf` без ошибок; библиография рендерится; `tex/figures/README.md` со всеми главами. |
| 2 | B1, B2, B3 | `feat(firmware): epd_bridge with opcodes 0x01-0x0E (dynamic LUT, register write, bench)` | Прошивка компилируется (Arduino-cli/PlatformIO); ESP32 шьётся; `0x06 PING` отвечает. |
| 3 | C1, C2, C3, C4 | `feat(python): bridge/lut/ina219/metrics + pytest suite` | `pytest -v` зелёное; `pytest-cov` ≥70% для `python/`. |
| 4 | D1, D2, D3, D4 | `docs(notes): structured literature notes + theorem proof sketch` | Все 5 файлов в `docs/notes/` существуют; D4 содержит explicit decision «доказательство складывается / требует переформулировки». |

## Risks & Mitigations

| Риск | Митигация |
|---|---|
| `biblatex-gost` не установлен в MacTeX по умолчанию | A2 task проверяет `tlmgr install biblatex-gost`; альтернатива — `gost71l.bst` через bibtex. |
| Прошивка не компилируется без Arduino-cli/IDE на хосте | B-фаза задач — формальная (мы пишем .ino, проверка компиляции — отдельный шаг пользователя). При желании добавить `scripts/flash.sh` через arduino-cli. |
| `pdftotext` плохо работает с djvu (Моисеев) | Для djvu использовать `djvutxt` (входит в `djvulibre`, `brew install djvulibre`). Или сначала `ddjvu -format=pdf` → потом `pdftotext`. |
| Эскиз доказательства в D4 «не складывается» | Это сигнал переформулировать теорему до начала M4; в плане проще исправить рано, чем поздно. |
| Объём `vasiliev2002_methods.pdf.pdf` (80 MB, 415 стр.) | Извлекаем только нужные главы (1-5,8) — это ~150 страниц; в зависимости от качества — может потребоваться OCR (`ocrmypdf`). |

## Done criteria

M1 закрыт когда:
- `make build` собирает `dist/thesis.pdf` (≈10 страниц со стабами+рендерёной библиографией).
- `pytest -v` зелёное, coverage отчёт показывает ≥70%.
- ESP32 в стенде отвечает на PING и WRITE_LUT_DYNAMIC; есть screenshot/фото работающего обновления с custom LUT.
- Все 5 файлов в `docs/notes/` написаны и просмотрены пользователем.
- ROADMAP.md обновлён: `M1` → `[x]`, добавлена строка в таблицу `Completed`.

## Next step after M1

`/aif-plan M2-M3` или сразу `/aif-implement` для M1.
