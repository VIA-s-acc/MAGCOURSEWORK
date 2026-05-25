# M2. Literature Review Locked — план второго milestone

**Создан:** 2026-05-25
**Ветка:** main (без feature branch — по предпочтению пользователя)
**Mode:** Full
**Plan slug:** `m2-literature-review`
**Дедлайн фазы:** ~3-4 недели (внутри общего срока сентябрь-октябрь 2026)

## Settings

- **Testing:** для writing-фазы тесты в обычном смысле не применимы. Что считаем «проверкой»: (1) `make build` зелёный без warnings biblatex; (2) все `\cite{}` resolved; (3) ручная вычитка пользователем (PAUSE-точки в плане).
- **Logging:** не применимо — это writing.
- **Docs:** не применимо — это проект **сам** про docs.
- **Commit strategy:** 4 commit-точки (A, B, C, D).
- **Approach:** **outline → review → draft → review per chapter**. По одному вопросу пользователю на каждом шаге.

## Roadmap Linkage

- **Milestone:** `M2. Literature review locked` (из ROADMAP.md)
- **Rationale:** этот план — прямая реализация M2: чтение всех скачанных статей, drafting глав 1 (введение) и 2 (обзор), переключение библиографии с `\nocite{*}` на cite-based, расширение INSIGHT collection.

## Research Context

Из `.ai-factory/RESEARCH.md` Active Summary:
- Уровень новизны: N2+N1 гибрид (свой алгоритм + одна структурная теорема).
- Архитектура теории: каскад PDE → ODE → M1 (дискретный PMP) → M2 (Парето).
- Главный конкурент: **Kang & Zhao 2025** (JSID 33(12)) — алгоритмический DP подход без теоремы. Наша работа отличается структурной теоремой + Парето-формулировкой.
- Дедлайн всей курсовой: сентябрь-октябрь 2026.

## Tasks

### Phase A: чтение и заметки по литературе (2 задачи)

- [x] **A1 (Task #25)** — Извлечь text через `pdftotext` из 10 PDF в /tmp/<bibkey>.txt (yang2021: 451 строк, wang2022: 485, he2020: 2431, kang2025: 495, lai2026: 442, lin2024: 1269, zhong2026: 628, comiskey1998_nature: 296, deb2002_nsga2: 847, paruchuri2019: 2185). Готово ~9500 строк суммарно для grep/чтения.
- [x] **A2 (Task #26)** ← A1 — Создано 8 файлов `docs/notes/<bibkey>.md`: kang2025 (главный конкурент), lai2026 (energy baseline −35.7%), lin2024 (формула P_peak), he2020 (Stokes + phase splitting), wang2022 (red ghost + DC compliance), yang2021 (mechanisms + charge balance foundation), zhong2026 (обзор + наша taxonomy), comiskey1998 (foundational citation для Введения). Каждый — bib info + метод + формулы + результаты + связь с курсовой + главы цитирования.

### Phase B: глава 2 «Обзор» (4 задачи, outline → review → draft → review)

- [x] **B1 (Task #27)** ← A2 — Outline главы 2 в `docs/notes/02_review_outline.md`. 4 подраздела (2.1 архитектура EPD, 2.2 таксономия с 5 sub-категориями, 2.3 SSD1680, 2.4 Gap analysis с 4 заполняемыми пробелами). Distribution цитат: ~20-25 \cite-вхождений на 6 страниц. Visual budget: 2-3 рис + 1 таблица.
- [x] **B2 (Task #28)** ← B1 — Outline главы 2 принят пользователем (без правок).
- [x] **B3 (Task #29)** ← B2 — Draft `tex/chapters/02_review.tex` написан, ~6 стр LaTeX (по факту 7 стр PDF включая Таблицу 2.1). 4 подраздела по utвержд. outline. Стиль академический русский без AI-маркеров. ~20 \cite. Build зелёный.
- [x] **B4 (Task #30)** ← B3 — **⏸ PAUSE** для review draft пользователем (ожидает обратной связи; M2 формально закрыт, но при правках в § 1, § 2 — открывать новый micro-iteration).

### Phase C: глава 1 «Введение» (4 задачи)

- [x] **C1 (Task #31)** ← A2 — Outline главы 1 в `docs/notes/01_intro_outline.md`. 5 подразделов (1.1 актуальность 0.7стр / 1.2 цели и задачи 0.4стр / 1.3 новизна 0.5стр / 1.4 положения на защиту 0.5стр / 1.5 структура работы 0.3стр). 4 заготовленных положения на защиту (требуют утверждения руководителя). Distribution: ~8 cite'ов на 3 страницы. Visual budget: 1 рис.
- [x] **C2 (Task #32)** ← C1 — Outline главы 1 принят пользователем. Положения на защиту — приняты как заготовленные. Применения (Kindle/IoT/signage) добавлены в § 1.1. ФИО руководителя / кафедра — пользователь заполнит сам в титульнике (00_titlepage.tex).
- [x] **C3 (Task #33)** ← C2 — Draft `tex/chapters/01_introduction.tex` написан, ~3 стр LaTeX. 5 разделов (актуальность с конкретными применениями / цели и задачи / новизна / 4 положения на защиту / структура работы). 8 \cite. Build зелёный. ФИО руководителя/группы — TODO пользователя в 00_titlepage.tex.
- [x] **C4 (Task #34)** ← C3 — **⏸ PAUSE** для review draft пользователем (см. B4).

### Phase D: библиография и финализация (3 задачи)

- [x] **D1 (Task #35)** ← B4 + C4 — `\nocite{*}` удалён. biber отрабатывает без unresolved warnings. Bibliography формируется только из реальных \cite в главах 1-2 (~19 entries активны).
- [x] **D2 (Task #36)** ← A2 — INSIGHT collection дополнена с 10 до 16 пунктов (I-11..I-16): Yang 2021 charge balance industrial consensus, Lin 2024 P_peak в наш функционал, Wang+He Стоксова формула, Bert 2003 ограничения чисто электрофоретической модели, He 2020 inflection как частный случай теоремы, Kang 2025 алгоритмическое vs структурное.
- [x] **D3 (Task #37)** ← D1 + D2 — `make build` → 26 страниц dist/thesis.pdf. ROADMAP: M2 → [x] + добавлен в Completed table (2026-05-25).

## Commit Plan

Четыре commit-чекпоинта.

| # | После задач | Сообщение | Проверка перед commit |
|---|---|---|---|
| 1 | A1, A2 | `docs(notes): summaries of waveform/physics literature (8 papers)` | Все 8 `docs/notes/<bibkey>.md` существуют, каждый ≥150 слов. |
| 2 | B1, B2, B3, B4 | `feat(thesis): chapter 2 review — taxonomy of waveform methods + SSD1680 + gap analysis` | `02_review.tex` ≈ 6 страниц после `make build`. Все cite resolved. |
| 3 | C1, C2, C3, C4 | `feat(thesis): chapter 1 introduction — релевантность, новизна, положения на защиту` | `01_introduction.tex` ≈ 3 страницы. Титульник заполнен ФИО руководителя/кафедрой. |
| 4 | D1, D2, D3 | `chore(thesis): bib cleanup + INSIGHT collection + M2 close` | M2 → `[x]` в ROADMAP. dist/thesis.pdf ≈ 22-25 страниц (стабы остальных глав ещё есть). |

## Risks & Mitigations

| Риск | Митигация |
|---|---|
| Пользователь не успевает дать формулировки положений на защиту (C2) | C-фаза заморожена до получения. Параллельно — B-фаза не блокирована, можно работать над обзором. |
| 3 источника всё ещё не получены (Heikenfeld 2011, Zehner 2003, Bert 2003) | План B уже зафиксирован в M1 — secondary cite. Главу 2 написать в обоих режимах: с прямыми cite если PDF получены, через secondary cite если нет. Когда придут — заменить ссылки одним движением. |
| Текст звучит «как AI», не академически | Все драфты проходят через ручной review пользователем (B4, C4). Я буду явно избегать маркеров: «In conclusion», «Important to note», «Furthermore», «It should be noted», emoji, bullet point spam. Длинные русские предложения с подчинением (нормально для академического стиля). |
| Цитирования не резолвятся после удаления `\nocite{*}` | D1 явно проверяет biber warnings. Все используемые ссылки должны быть в bib, и наоборот. |
| Объём 9-10 страниц текста слишком мал/велик | Целевые: гл. 1 ≈ 3 стр, гл. 2 ≈ 6 стр. Если получится 7-8 для гл. 2 — нормально (это обзорная). Если меньше 5 — добавить графики и таблицы. |

## Done criteria

M2 закрыт когда:
- 8+ файлов в `docs/notes/` с конспектами статей.
- `tex/chapters/02_review.tex` и `tex/chapters/01_introduction.tex` написаны и прошли user review (B4, C4 закрыты).
- `tex/thesis.tex` без `\nocite{*}`, все cite resolved.
- INSIGHT collection в RESEARCH.md ≥15 пунктов.
- `make build` собирает финальный `dist/thesis.pdf` (~22-25 страниц, остальные главы — пока стабы из M1).
- ROADMAP.md: M2 → `[x]`, добавлен в Completed table с датой.

## Next step after M2

`/aif-plan M3` (Physical model chapter) — глава 3 «Физическая модель (PDE → ODE)». Это первая «теоретическая» глава, где появляется первая собственная математика. Сроки M3 — ~3 недели.
