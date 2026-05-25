# Outline главы 2 «Обзор предметной области»

Целевой объём — **~6 страниц** (по Chapter Plan в RESEARCH.md).
Visual budget — 2-3 рисунка + 1 таблица.

---

## 2.1 Архитектура электрофоретического дисплея (~1 стр.)

**Цель:** дать читателю общее представление об устройстве EPD, чтобы
последующие разделы про waveform-методы имели физический контекст.

**Содержание:**
- Микрокапсулы с заряженными частицами в non-polar solvent
  (`\cite{comiskey1998_nature}` — основоположная Nature статья 1998).
- Bistability: частицы сохраняют положение неделями без энергии
  (`\cite{yang2021_mechanisms}` — современный обзор механизмов).
- Active matrix (AM-EPD) — TFT-матрица как backplane для individual
  pixel control.
- Контраст и реакция: EPD выигрывает по reflectance и outdoor
  visibility, но проигрывает по refresh rate относительно LCD/OLED
  (`\cite{yang2021_mechanisms}` Table 1).

**Рисунок 2.1** (`diagrams/02_am_epd_arch.tex`):
схема AM-EPD — TFT-матрица + микрокапсула с двумя типами частиц +
управляющие электроды (сверху common, снизу — pixel-individual).

**Ключевые тезисы (1-2 предложения каждый):**
- T1: EPD основан на электрофоретическом движении заряженных частиц.
- T2: Bistability — фундаментальное физическое свойство, обеспечивающее
  ультранизкое потребление в режиме статического изображения.
- T3: Limitation — медленный refresh (сотни миллисекунд) делает
  waveform engineering критическим для пользовательского опыта.

---

## 2.2 Таксономия waveform-методов (~2 стр.)

**Цель:** показать развитие подходов к design'у waveform — от
исторических до современных, выделить ключевые семейства методов.

**Структурная база:** таксономия из `zhong2026_review.pdf` (обзор-2026),
дополненная нашими insights из работ 2020-2026.

### Подразделы

**2.2.1. Исторический фундамент.** Drive waveforms for AM-EPD —
основополагающая работа Zehner et al. 2003 (`\cite{zehner2003_drive_waveforms}`,
secondary cite через `\cite{kang2025_dp_waveform}` если PDF не получен).
Базовая 3-стадийная структура: erasing + activation + driving.

**2.2.2. Ghost reduction.** Wang et al. 2022 (`\cite{wang2022_red_ghost}`) —
sub-divided erasing для red ghost в 3-color EPD; формула Стокса для
скорости частицы; **−80% red ghost** через physical-aware modification.

**2.2.3. Response speed.** He et al. 2020 (`\cite{he2020_particle_activation}`) —
phase splitting активационной фазы; brightness curve inflection point
как индикатор optimal duration; **−300 мс** в total waveform.

**2.2.4. Energy efficiency.** Два current state-of-the-art подхода:
- Lin et al. 2024 (`\cite{lin2024_low_power}`) — formula
  `P_peak = (1/2)·C·ΔV²·f·V_source`, redesign waveform с 0V-вставками,
  **−37.24% energy fluctuation**.
- Lai et al. 2026 (`\cite{lai2026_e3dw_energy}`) — E3DW: temperature
  compensation + low-frequency square wave (1-5 Hz), **−35.7% энергии**.

**2.2.5. Optimization-based.** Kang & Zhao 2025
(`\cite{kang2025_dp_waveform}`) — DP-based search с scalar cost
function; ближайший аналитический предшественник нашей работы.

**Таблица 2.1:** Сравнение waveform-методов (Метод / Что
оптимизирует / Алгоритм / Результат). 6-7 строк.

| Работа | Оптимизирует | Алгоритм | Лучший результат |
|---|---|---|---|
| Zhener 2003 | базовая структура | manual | reference |
| He 2020 | response speed | inflection heuristic | −300 ms |
| Wang 2022 | ghost (red) | sub-stage erasing | −80% ghost |
| Lin 2024 | energy | 0V vstavki | −37% energy fluct. |
| Lai 2026 | energy | E3DW system | −35.7% energy |
| Kang 2025 | quality+speed | DP scalar | (numerical) |
| **Наша** | **(E, G, τ) Pareto** | **PMP + ε-constraint** | **strict dominance** |

**Рисунок 2.2** (`diagrams/02_waveform_taxonomy.tex`):
дерево waveform-методов — корень «EPD waveform design», ветви
«ghost reduction / response speed / energy / optimization» с
работами-листьями.

---

## 2.3 Контроллер SSD1680 — архитектура управления (~1.5 стр.)

**Цель:** перейти от обобщённой теории waveform к **конкретному**
контроллеру нашего стенда. Это переходное место от «академического обзора»
к «практической задаче», над которой работает данная курсовая.

**Подразделы:**

**2.3.1. Структура waveform setting** (Section 6.7 datasheet
`\cite{ssd1680_datasheet}`). 159 байт: 153 байта LUT + EOPT + VGH +
VSH1 + VSH2 + VSL + VCOM. LUT: 5 sub-LUT × 12 фаз × 4 sub-frame ×
{VSH1, VSH2, VSL, VCOM, 0}. **Это даёт нам конечномерную дискретную
задачу оптимального управления.**

**2.3.2. OTP-таблица и temperature-mapped LUT** (Section 6.9
datasheet). Контроллер хранит до 36 temperature ranges (TR0..TR35),
для каждого — свой waveform setting. Поиск через `0x18` (temperature
sensor) + searching mechanism.

**2.3.3. Регистр 0x22 Display Update Control 2 и «ключевой фикс».**
Семантика 8 значений (0xC7 / 0xCF / 0xF7 / 0xFF). Объяснение почему
`0xC7` — единственный валидный вариант для custom user LUT (не
перезаписывает её через OTP-search). Это — обнаружение, без которого
наш эксперимент не воспроизводим.

**Рисунок 2.3** (`diagrams/02_ssd1680_lut_struct.tex`, опц.):
структурная карта 159-байтного waveform setting с маркировкой полей.

**Ключевые тезисы:**
- T1: SSD1680 предоставляет полный программный доступ к waveform
  через регистр 0x32 (153-байт LUT).
- T2: По умолчанию контроллер использует заводский LUT из OTP — для
  custom-оптимизации это нужно явно обходить через `0x22=0xC7`.
- T3: Архитектура контроллера естественно отображается в наш
  дискретный класс задач оптимального управления (12 фаз × 4
  sub-frame × конечное множество voltage levels).

---

## 2.4 Gap analysis — место нашей работы (~1.5 стр.)

**Цель:** обосновать **новизну** нашей работы относительно литературы.

**Структура:**

**2.4.1. Что обзорная статья Zhong 2026 классифицирует и что НЕ
охватывает.** Zhong даёт обзор по 3 семействам (image preprocessing /
multi-stage waveforms / optimization-based), но в **optimization-based**
все работы — single-objective (один скалярный критерий с фиксированными
весами или с одной соответствующей метрикой).

**2.4.2. Что делает Kang 2025 и в чём её ограничения.**
- DP-based поиск optimal path в state-action graph.
- Cost function: `α·T + β·flicker + γ·quality`, α=0.6, β=γ=0.2.
- Нет структурного результата (форма оптимума).
- Нет явного charge balance constraint (формализация физического
  требования из Yang 2021 / Wang 2022).
- Нет multi-objective формулировки — одна точка в пространстве
  (E, G, τ), не Парето-фронт.

**2.4.3. Пробелы, заполняемые нашей работой.**
- ✓ **Пробел 1:** Структурный результат (Теорема 4.1 курсовой) — форма
  оптимума в классе charge-balanced waveforms (bang-bang с K_eff
  ограниченным).
- ✓ **Пробел 2:** Multi-objective формулировка с явным построением
  Парето-фронта (ε-constraint + PMP по срезам).
- ✓ **Пробел 3:** Каскадная теория PDE → ODE → discrete (M1) → Парето
  (M2), каждая ступень обоснована физически и математически.
- ✓ **Пробел 4:** Validation на реальном стенде с измерением реальной
  энергии через INA219 (а не симулированной).

**2.4.4. Краткая постановка задачи (1 абзац).** Это finale обзорной
главы — формулировка проблемы, которая в полной форме развёрнута в § 3-5.

---

## Распределение цитат

В обзорной главе должны появиться **все** ключевые источники:

| `\cite` ключ | Где используется | Сколько раз |
|---|---|---|
| `comiskey1998_nature` | § 2.1 (рождение технологии) | 1 |
| `yang2021_mechanisms` | § 2.1 (механизмы), § 2.4.2 (charge balance) | 2-3 |
| `zhong2026_review` | § 2.2 (таксономия), § 2.4.1 (gap) | 3-4 |
| `wang2022_red_ghost` | § 2.2.2, § 2.4.2 (charge balance) | 2 |
| `he2020_particle_activation` | § 2.2.3, § 2.4 | 2 |
| `lin2024_low_power` | § 2.2.4 (energy) | 1 |
| `lai2026_e3dw_energy` | § 2.2.4 (energy) | 1 |
| `kang2025_dp_waveform` | § 2.2.5 + § 2.4.2 (main competitor) | 2-3 |
| `ssd1680_datasheet` | § 2.3 (полностью) | 3-4 |
| `waveshareteam_epaper` | § 2.3 (reference code) | 1 |
| `zehner2003_drive_waveforms` | § 2.2.1 (secondary cite через kang2025) | 1 |
| `heikenfeld2011_review` | опц. § 2.1 если PDF получен | 0-1 |
| `bert2003_physics` | опц. § 2.1 если PDF получен | 0-1 |

Итого `\cite{}`-вхождений: **≈20-25** на 6 страниц обзора.

---

## Чего НЕ должно быть в главе 2

- **Доказательств** — это § 4.
- **Алгоритма** — это § 5.
- **Результатов** — это § 6, 7.
- **Длинных дифференциальных уравнений** — только пара формул-маркеров
  (Стокс, P_peak), детали — в § 3.
- **AI-стиля:** «In conclusion», «It is important to note», bullet point
  spam, emoji, длинные водные фразы.

---

## Готовность к B3 (drafting)

Outline считается готовым, когда пользователь:
- ✅ Согласен со структурой 2.1–2.4.
- ✅ Согласен с распределением цитат.
- ✅ Согласен с тем, что Heikenfeld 2011 и Bert 2003 заменяются через
  secondary cite (если их PDF не получены к B3).
- ✅ Утвердил «гэп» в § 2.4 как новизну работы (структурная теорема +
  Парето).
- ⚠ Опционально: правки в формулировках ключевых тезисов / таблице 2.1.

После согласия — переход к **B3** (draft в LaTeX).
