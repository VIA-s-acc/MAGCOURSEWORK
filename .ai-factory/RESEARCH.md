# Research

Updated: 2026-05-24 21:18
Status: active

## Active Summary (input for /aif-plan)
<!-- aif:active-summary:start -->
**Topic:** Магистерская курсовая ВМК МГУ — «Оптимизация обновления электрофоретического (E-Ink) дисплея: мат. модель, алгоритм управления и экспериментальная валидация».

**Goal:** Разработать формальную мат. модель обновления EPD и оптимизирующий waveform-алгоритм, обеспечивающий компромисс «энергия ↔ ghosting ↔ скорость обновления ↔ ресурс панели», превосходящий заводской LUT. Подтвердить симуляцией (Python notebook) и физическим экспериментом на стенде ESP32 + Waveshare 2.13" V4 (SSD1680) + INA219.

**Constraints:**
- Объём ~40 стр., LaTeX, ГОСТ-форматирование.
- Библиография — только верифицированные источники (DOI / физический файл в `docs/refs/`). Никаких фантомных ссылок.
- Стиль — human-like (без «I am Claude…», без типовых ИИ-фраз: «Important to note», «In conclusion», «In summary»).
- Целевой уровень новизны: **N2+N1 гибрид** (свой алгоритм + одна структурная теорема о форме оптимума в классе charge-balanced LUT).
- Стенд уже собран и прошит (epd_bridge.ino, опкоды 0x01–0x0B).
- Язык артефактов: русский.

**Decisions:**
1. AI-Factory скиллы установлены, режим работы — `/aif-explore` → `/aif-roadmap` → `/aif-plan`.
2. Уровень новизны: **N2+N1 гибрид** (см. выше).
3. Сетевой доступ разрешён (WebFetch + WebSearch).
4. Платные источники (Wiley JSID) скачиваются пользователем вручную в `docs/refs/` (список ниже в разделе «Pending downloads»).
5. SSD1680 datasheet и INA219 datasheet — скачаны и распарсены в `docs/refs/`.
6. **Архитектура теории: каскад PDE → ODE → M1 (дискретный PMP с теоремой) → M2 (Парето).** Каждый уровень имеет содержательную редукцию к следующему. Теорема — на уровне M1 («оптимум в классе charge-balanced waveforms — bang-bang с ≤K_eff активных фаз»). Алгоритм — на уровне M2 (ε-constraint + PMP по срезам). Стенд — валидация Парето-границы против заводского LUT, Kang 2025, Lin 2024.
7. **Симулятор: S3 гибрид.** ODE-модель частицы (на основе Wang 2022 Стокса) — для теоремы и калибровки физических констант. Data-driven surrogate (нейросеть/spline по отклику на калибровочный набор LUT) — для быстрой оптимизации. Реальный стенд — для финальной валидации.
8. **Метрики:**
   - Energy: `E = ∫ U·I dt` через INA219 (метод трапеций, 1.9..12 кГц).
   - Latency: `τ = t(BUSY↓0) − t(0x20)` с timestamping на ESP32.
   - Ghost (формальное определение для теоремы): `G = (1/N) Σ |reflect_actual − reflect_target|` — линейный residual.
   - Ghost (отчётная для презентации): `1 − SSIM(target, rendered)`.
   - Lifetime proxy (мягкая цель): `L = Σ V² · TP` (тепловая нагрузка / energy density).
   - Charge balance (жёсткое ограничение в постановке): `Σ V · TP = 0`.
9. **Ghost на стенде измеряется через iPhone/USB-камеру** + ImageJ (или scikit-image) для пикселометрии. Потребуется простейший «фотостандарт»: чёрный картонный кожух с фиксированным расстоянием и постоянной засветкой (LED-кольцо или окно с известной яркостью).

**Open questions — ВСЕ ЗАКРЫТЫ (см. Decisions):**
- ✅ Q1: каскад PDE→ODE→M1→M2.
- ✅ Q2: симулятор S3 (ODE + surrogate).
- ✅ Q3: G2-residual в теореме + SSIM для презентации; L3 (V²·TP) soft + L4 (DC-balance) hard.
- ✅ Q4: lifetime → proxy L3 (закрыто в рамках Q3).
- ✅ Q5: дедлайн **сентябрь-октябрь 2026 (≈18–22 недели от 2026-05-24)**. Режим работы: chapter-by-chapter с обсуждением каждой главы. Больше воздуха → берём полный PDE-раздел, две теоремы, расширенный эксперимент, и опц. preprint в виде SID-style 6-страничного paper.

**Success signals:** На реальном стенде (а) средняя энергия обновления ниже заводской на ≥15%, ИЛИ (б) латентность ≤80% заводской при сохранении SSIM≥0.95 за окно из 50 обновлений, ИЛИ (в) граница Парето строго доминирует заводскую при сопоставимом качестве. И теоретическая часть: одна структурная теорема о форме оптимума в классе charge-balanced waveforms (доказательство — через дискретный PMP Болтянского/Paruchuri & Chatterjee 2019).

**Next step:** Финализировать Chapter Plan + INSIGHT collection ниже → переход к `/aif-roadmap` (детальный план по неделям).
<!-- aif:active-summary:end -->

---

## Hardware findings (verified from datasheet)

### SSD1680 — что важно для теоретической главы

Источник: Solomon Systech, *SSD1680 Product Preview*, Rev 0.14, P 1/46, Jun 2019. Локально: `docs/refs/SSD1680.pdf`. Сторонний mirror: `https://github.com/CursedHardware/epd-driver-ic/blob/master/SSD1680.pdf` (репозиторий-зеркало datasheet'ов EPD контроллеров).

**Размерность управления (Section 6.7, Figure 6-6, Table «Waveform Setting mapping»):**
- Waveform Setting — **159 байт**. Из них:
  - byte 0–152 — собственно LUT (загружается командой 0x32, **153 байта**);
  - byte 153 — EOPT (option for LUT end, регистр 0x3F);
  - byte 154 — VGH (gate voltage, регистр 0x03);
  - bytes 155–157 — VSH1, VSH2, VSL (source voltages, регистр 0x04);
  - byte 158 — VCOM (регистр 0x2C).
- LUT поддерживает **до 5 sub-LUT (LUT0..LUT4)** × **12 фаз (phase 0..11)** × 4 sub-frame (A, B, C, D).
- Параметры на фазу: `VS[nX-LUTm]` (выбор источника), `TP[nX]` (time phase), `SR[nXY]` (slew rate), `RP[n]` (repeat), `FR[n]` (frame rate), `XON[nXY]` (gate gating).
- ИТОГ: дискретное управление с конечным алфавитом источников {VSH1, VSH2, VSL, VCOM, GND} × конечным временным разрешением. **Это даёт ровно ту дискретную задачу оптимального управления, к которой применим дискретный PMP / DP.**

### Регистр 0x22 (Display Update Control 2) — подтверждение «ключевого фикса»

Datasheet, Command Table, страница 25 (ориентировочно строка 1365 текста), `A[7:0] = FFh (POR)`:

| Hex | Sequence |
|---|---|
| 0x80 | Enable clock signal |
| 0x01 | Disable clock signal |
| 0xC0 | Enable clock + Enable Analog |
| 0x03 | Disable Analog + Disable clock |
| 0x91 | Enable clock + Load LUT with **DISPLAY Mode 1** + Disable clock |
| 0x99 | Enable clock + Load LUT with **DISPLAY Mode 2** + Disable clock |
| 0xB1 | Enable clock + **Load temperature value** + Load LUT with DISPLAY Mode 1 |
| 0xB9 | Enable clock + **Load temperature value** + Load LUT with DISPLAY Mode 2 |
| **0xC7** | Enable clock + Enable Analog + **DISPLAY with DISPLAY Mode 1** + Disable Analog + Disable OSC |
| **0xCF** | Enable clock + Enable Analog + **DISPLAY with DISPLAY Mode 2** + Disable Analog + Disable OSC |
| **0xF7** | Enable clock + Enable Analog + **Load temperature value + DISPLAY with DISPLAY Mode 1** + Disable Analog + Disable OSC |
| **0xFF** | Enable clock + Enable Analog + **Load temperature value + DISPLAY with DISPLAY Mode 2** + Disable Analog + Disable OSC |

**Объяснение пользовательского фикса:**
- 0xC7 / 0xCF — НЕ перезагружают LUT (используют уже записанный пользователем в регистр 0x32).
- 0xF7 / 0xFF — содержат подпоследовательность «Load temperature value», что запускает **Waveform Setting Searching Mechanism (Section 6.9)**: контроллер ищет матчинг по температурному диапазону в OTP-таблице (TR0..TR35), и заводская WS, найденная по температуре, перезаписывает пользовательский LUT в регистре. Отсюда — все три алгоритма дают ~600 мс заводского LUT.
- Partial использует 0xCF (DISPLAY Mode 2) — потому что Mode 2 в SSD1680 → partial-update LUT (см. также регистр 0x37, поле B[7:0]..F[3:0] «Display Mode for WS[0..35]»: 0 = Mode 1, 1 = Mode 2).

### Temperature mechanism (Section 6.8)

- Внутренний температурный сенсор: ±2°C в диапазоне -25..+50°C.
- Внешний сенсор по I²C (TSDA/TSCL).
- Формат — 12-bit binary signed (бит D11 — знак, значение в DegC = X/16).
- OTP может хранить до 36 temperature ranges (TR0..TR35), каждый со своим WS.

### Регистр 0x3C (Border Waveform Control)

- `A[7:0] = C0h [POR]`, по умолчанию VBD = HiZ.
- A[7:6]: 00 = GS Transition (по LUT), 01 = Fix Level, 10 = VCOM, 11 = HiZ.
- A[5:4]: Fix Level — VSS / VSH1 / VSL / VSH2.

### Опасные значения с точки зрения «срока службы»

Из таблицы VSH/VSL/VCOM (datasheet, страницы 22-24, строки 1049-1086 текста):
- VSH1, VSH2: типовой диапазон 2.4..17 В (значения 0x8E..0x4B).
- VSL: -5..-17 В (значения 0x0A..0x22).
- VCOM: 0..-15 В (значения 0x3C..0x32).

**Гипотеза для метрики «срок службы»:** условный износ за обновление пропорционален `Σ_i Σ_φ |V_i(φ)| · TP[φ]` или `Σ |V|² · TP` (рассеяние мощности в среде). Точная связь — открытый вопрос, требует литературы (Yang 2021, Bert 2003).

---

### INA219 — измерительная подсистема

Источник: Texas Instruments, INA219 datasheet (`docs/refs/INA219.pdf`, 10 страниц).
- Дифференциальное измерение напряжения на шунте, разрешение АЦП 12 бит (вес LSB шунт-напряжения = 10 мкВ).
- I²C/SMBus интерфейс, программируемая частота преобразования.
- Шунт 0.1 Ом → ток I = U_shunt / 0.1 = 10·U_shunt; разрешение по току ~100 мкА.
- Питание: 3–5.5 В, ток потребления самой ИС ≤1 мА.
- При шунте 0.1 Ом и максимуме шунт-напряжения 320 мВ → максимально измеряемый ток ~3.2 А (с большим запасом для нашей панели — типичный пик ~30..50 мА).

**Замечание по методологии измерения энергии за обновление:**
- Период преобразования INA219 в режиме full 12-bit ~532 мкс (≈1.9 кГц семплирования) с фильтрацией; в минимальном режиме 84 мкс (≈12 кГц).
- Для обновления длительностью 100..600 мс получим 200..6000 семплов — достаточно для интегрирования `E = ∫ U(t)·I(t) dt` через метод трапеций.
- Однако: тонкие импульсные шумы коротких фаз LUT (TP ~ единицы кадров при FR~50Гц → ~20 мс на фазу) могут «прыгать» — потребуется аккуратное усреднение/burst-чтение.

---

## Verified references (Round 1)

### Foundational physics & reviews

1. **Comiskey B., Albert J.D., Yoshizawa H., Jacobson J.** (1998). *An electrophoretic ink for all-printed reflective electronic displays.* Nature, **394**(6690), 253–255.
   - DOI: [10.1038/28349](https://doi.org/10.1038/28349)
   - VERIFIED: да, полный текст в `docs/refs/comiskey1998_nature.pdf` (3 стр.).
   - Применение: глава «введение», ссылка на канонический генезис EPD.

2. **Heikenfeld J., Drzaic P., Yeo J.-S., Koch T.** (2011). *Review paper: A critical review of the present and future prospects for electronic paper.* Journal of the Society for Information Display, **19**(2), 129–156.
   - DOI: [10.1889/JSID19.2.129](https://doi.org/10.1889/JSID19.2.129)
   - VERIFIED: да, через wiley landing page + sci-hub mirror в поиске.
   - Применение: глава «обзор технологий», физика, ограничения скорости/контраста.
   - **Pending download (Wiley paywall)** — нужен PDF в `docs/refs/`.

3. **Yang B.-R., Hu W.-J., Zeng Z., Wu Z.-Y., Gu Y.-F., Xu J.-Z., Cao J.-X., Zhang Y.-D., Chen P.** (2021). *Understanding the mechanisms of electronic ink operation.* Journal of the Society for Information Display.
   - DOI: [10.1002/jsid.960](https://doi.org/10.1002/jsid.960)
   - VERIFIED: да, полный текст в `docs/refs/yang2021_mechanisms.pdf` (9 стр.).
   - Применение: микрофизическая модель — гл. «модель частиц».

### Waveform design & ghosting

4. **Zehner R., Amundson K., Knaian A., Zion B., Johnson M., Zhou G.** (2003). *Drive Waveforms for Active Matrix Electrophoretic Displays.* SID Symposium Digest of Technical Papers, **34**(1), 842–845.
   - DOI: [10.1889/1.1832402](https://doi.org/10.1889/1.1832402)
   - VERIFIED: да, через wiley landing page.
   - Применение: канон конструкции waveform для AM-EPD.
   - **Pending download (Wiley paywall).**

5. **Bert T., De Smet H.** (2003). *The microscopic physics of electronic paper revealed.* Displays, **24**(3), 103–110.
   - DOI: [10.1016/S0141-9382(03)00060-1](https://doi.org/10.1016/S0141-9382(03)00060-1)
   - VERIFIED: title и venue подтверждены поиском; точный DOI зафиксирую при скачивании PDF.
   - Применение: физика микрокапсул, обоснование Стоксовой модели.
   - **Pending download (Elsevier paywall).**

6. **Wang L., Zeng W., Liang Z., Zhou G.** (2022). *Red Ghost Image Elimination Method Based on Driving Waveform Design in Three-Color Electrophoretic Displays.* Micromachines, **13**(2), 275.
   - DOI: [10.3390/mi13020275](https://doi.org/10.3390/mi13020275)
   - VERIFIED: да, прочитан полный текст через PMC8875704.
   - Метод: двухстадийное стирание + Стоксова формула скорости частиц `v = Uq/(6πdηR)·(1 − exp(−6πηR/m·t))`. Метрики: 80.43% reduction ghost, 79.63% flicker reduction, 20.8% luminance improvement.
   - Применение: гл. «обзор методов»; точка отсчёта для метрик ghost reduction.

7. **Kang D., Zhao X., Wei X., Wu H., Zhang H., Zhao T.** (2025). *Effective E-Paper Driving Waveform Design Based on Dynamic Programming.* Journal of the Society for Information Display, **33**(12), 1114–1122.
   - DOI: [10.1002/jsid.2113](https://doi.org/10.1002/jsid.2113)
   - VERIFIED: да, полный текст в `docs/refs/kang2025_dp_waveform.pdf` (9 стр.).
   - Заявленный метод: physical simulation + DP для поиска оптимального пути waveform.
   - **КРИТИЧНО:** прямой конкурент нашего N1+N2 подхода. Обязательно изучить полный текст до того, как фиксировать постановку.

8. **Lai J., Xiangba Q., Fu Y., Cao M., He N., Xu Y.** (2026). *Energy-Efficient Driving Waveform Design for E-Paper Display.* Journal of the Society for Information Display.
   - DOI: [10.1002/jsid.70042](https://doi.org/10.1002/jsid.70042)
   - VERIFIED: да, полный текст в `docs/refs/lai2026_e3dw_energy.pdf` (8 стр.).
   - Заявленный метод (E3DW): temperature compensation + dynamic voltage adjustment + square-wave driving → 35.7% энергии минус.
   - **КРИТИЧНО как baseline для энергетического сравнения.**

9. **Zhong X., Zhao X., Zhao T.** (2026). *Review on Image Preprocessing and Driving Waveform Design for Electrophoretic Displays.* Journal of the Society for Information Display.
   - DOI: [10.1002/jsid.70044](https://doi.org/10.1002/jsid.70044)
   - Received 20 June 2025, accepted 4 March 2026. Fujian Key Laboratory for Intelligent Processing and Wireless Transmission of Media Information, Fuzhou University.
   - VERIFIED: да, полный текст в `docs/refs/zhong2026_review.pdf` (12 стр.).
   - Применение: единственный современный обзор waveform-методов — основа для главы «состояние области».

10. **Lin et al.** (2024). *Low-Power Driving Waveform Design for Improving the Display Effect of Electrophoretic Electronic Paper.* Micromachines, **15**(9), 1076.
    - DOI: [10.3390/mi15091076](https://doi.org/10.3390/mi15091076)
    - VERIFIED: да, прочитан полный текст через PMC11433740.
    - Формула пиковой мощности: `P_peak = ½·C·ΔV²·f·V_source`. Метрики: −37.24% energy fluctuation, −5.19 Вт средней мощности на 10.3" 1680×2240 BOE; 90 мс B↔W.
    - Применение: непосредственный донор формулы энергии для нашей модели.

11. **He W., Yi Z., Shen S., Huang Z., Liu L., Zhang T., Li W., Wang L., Shui L., Zhang C., Zhou G.** (2020). *Driving Waveform Design of Electrophoretic Display Based on Optimized Particle Activation for a Rapid Response Speed.* Micromachines, **11**(5), 498.
    - DOI: [10.3390/mi11050498](https://doi.org/10.3390/mi11050498)
    - VERIFIED: да, полный текст в `docs/refs/he2020_particle_activation.pdf` (15 стр.). Атрибуция в первом раунде разведки была некорректной («Tong 2020») — поправлено.
    - Метод: разделение активационной фазы на «improving particle activity» (60 ms) и «uniform reference grayscale» (120 ms) → сокращение waveform на 300 ms. Метрики: ghost −57%, flicker −26.7%, контраст +2.7 nits.
    - Применение: third baseline для главы 7.

### Multi-objective optimization & control theory

12. **Deb K., Pratap A., Agarwal S., Meyarivan T.** (2002). *A fast and elitist multi-objective genetic algorithm: NSGA-II.* IEEE Transactions on Evolutionary Computation, **6**(2), 182–197.
    - DOI: [10.1109/4235.996017](https://doi.org/10.1109/4235.996017)
    - VERIFIED: да, полный текст в `docs/refs/deb2002_nsga2.pdf` (16 стр., open access mirror на sci2s.ugr.es).
    - Применение: бенчмарк для поиска Парето-фронта в нашей MOO формулировке.

13. **Понтрягин Л.С., Болтянский В.Г., Гамкрелидзе Р.В., Мищенко Е.Ф.** (1961, переиздания). *Математическая теория оптимальных процессов.* М.: Наука.
    - VERIFIED: классика, не нуждается в верификации, но точное издание/год для библиографии — указать при сборке (есть PDF на mathnet.ru / nauka).
    - Применение: фундамент дискретного PMP в наших структурных результатах.

14. **Васильев Ф.П.** (2002, 4-е изд.). *Методы оптимизации.* М.: Факториал Пресс. (Также: Васильев Ф.П., Потапов М.М., Будак Б.А., Артемьева Л.А., 2024, изд. Юрайт — комплект для бакалавриата/магистратуры.)
    - VERIFIED: книга подтверждена через urait.ru, studizba.com (есть PDF).
    - **Особое значение: написана на основе курсов лекций ВМК МГУ.** Идеально для ссылки в магистерской работе ВМК.
    - Применение: основная цитата для разделов «методы условной/безусловной оптимизации».

### Discrete-time PMP literature (для теоремы N1)

15. **Boltyanskii V.G.** (early 1960s). Original work on discrete-time maximum principle.
    - Точная ссылка будет уточнена; в современной литературе ссылаются на это как «дискретный аналог Понтрягина, доказан Болтянским». Кандидаты-первоисточники нужно проверить.

16. **Paruchuri P., Chatterjee D.** (2019). *Discrete time Pontryagin maximum principle for optimal control problems under state-action-frequency constraints.* IEEE Transactions on Automatic Control, **64**.
    - DOI: [10.1109/TAC.2019.2893160](https://doi.org/10.1109/TAC.2019.2893160). Preprint: [arXiv:1708.04419](https://arxiv.org/abs/1708.04419) (2017).
    - VERIFIED: да, полный текст в `docs/refs/paruchuri2019_discrete_pmp.pdf` (31 стр., arXiv v1).
    - **Уточнение атрибуции:** в первом раунде разведки источник ошибочно атрибутирован как «Phogat-Banavar-Chatterjee» — это была другая группа работ по дискретному PMP (`arXiv:1612.08022`, на матричных группах Ли). Здесь правильно — Paruchuri & Chatterjee.
    - Применение: современная формулировка дискретного PMP с constraints на состояние И на множество допустимых управлений — наш случай (управление дискретно по уровню напряжения). Основа доказательства Теоремы 4.1.

---

## ⚡ Полезные находки из reference-кода Waveshare (epd2in13_V4.py)

Источник: `docs/refs/waveshare_code/epd2in13_V4.py` (350 строк, скачан из waveshareteam/e-Paper, RaspberryPi_JetsonNano/python/lib/waveshare_epd/).

**`init()` (стандартный full-update инициализатор):**
- 0x12 SWRESET → 0x01 Driver output (0xF9,0x00,0x00) → 0x11 Data entry (0x03) → SetWindow/SetCursor → **0x3C Border (0x05)** → **0x21 Display Update Control 1 (0x00, 0x80)** → **0x18 Temperature sensor (0x80 = internal)** → ReadBusy.
- В стандартном init НЕТ 0x32 (Write LUT) — поэтому при последующем `TurnOnDisplay()` контроллер сам берёт заводский LUT из OTP по реальной температуре.

**`init_fast()` (Waveshare-овский "fast"):**
- SWRESET → 0x18 (sensor selection) → data entry → SetWindow/Cursor → **0x22=0xB1, 0x20** (Load temp + Load LUT Mode 1 + Activate) → **0x1A=0x64,0x00** (Write to temperature register: 0x0064/16 ≈ +6.25 °C) → **0x22=0x91, 0x20** (Load LUT Mode 1 + Activate с фейковой температурой).
- **Ключ:** "fast" режим Waveshare работает через **подмену температурного значения** через регистр 0x1A — заставляя контроллер выбрать из OTP другую (более короткую) waveform для холодной температуры. Это не магия — это эксплуатация архитектуры OTP-search.

**`TurnOnDisplay()` (full):** `0x22=0xF7 → 0x20`. Это вариант с «Load temperature value + DISPLAY Mode 1 + Disable» — он переписывает любой пользовательский LUT заводским.

**`TurnOnDisplay_Fast()` (для use в нашей работе):** `0x22=0xC7 → 0x20`. Это «DISPLAY Mode 1 + Disable» БЕЗ перезагрузки LUT — то, что нужно для нашего кастомного waveform.

### Что это даёт нам как baseline-таксономию для главы экспериментов:

| Сценарий | init | Write LUT (0x32)? | Update (0x22) | Что фактически проигрывается |
|---|---|---|---|---|
| **B0** — Waveshare full | `init()` | нет | `0xF7` | заводская OTP-LUT для реальной T |
| **B1** — Waveshare fast | `init_fast()` | нет | `0xC7` | заводская OTP-LUT для фейковой T = +6.25°C |
| **B2** — Custom static | `init()` | **наша LUT** | `0xC7` | наш заранее посчитанный waveform |
| **B3** — Custom + content-adaptive | `init()` | **LUT(diff)** | `0xC7` | waveform, выбранная по битовому diff текущего и нового кадра |
| **B4** — Content-adaptive + temp-aware | `init()` + `0x1A` | **LUT(diff, T)** | `0xC7` | то же + явная подмена температуры под наш waveform-домен |

B0 и B1 — известные baseline'ы (Waveshare). **B2–B4 — наш экспериментальный конус.** Теоретическая глава доказывает структуру оптимума для класса B2 (статический оптимальный waveform) и расширяет на B3/B4 через decomposition.

## Downloads status

Все файлы в `/Users/georgii/GITHUB/MAGCOURSEWORK/docs/refs/`. Naming: `<firstauthor><year>_<short_topic>.{pdf,djvu}` (lowercase, snake_case).

### ✅ Получено и переименовано (17 файлов)

| Файл | Источник | Стр. |
|---|---|---|
| `ssd1680_datasheet.pdf` + `.txt` | Solomon Systech SSD1680, Rev 0.14 (Jun 2019) | 46 |
| `ina219_datasheet.pdf` + `.txt` | Texas Instruments INA219 datasheet | 10 |
| `vasiliev2002_methods.pdf` | Васильев Ф.П. (2002). Методы оптимизации. М.: Факториал Пресс. | 415 |
| `pontryagin_optimal_processes.pdf` | Понтрягин Л.С., Болтянский В.Г., Гамкрелидзе Р.В., Мищенко Е.Ф. Мат. теория оптимальных процессов. | 393 |
| `moiseev1971_numerical_optimal_systems.djvu` | Моисеев Н.Н. (1971). Численные методы в теории оптимальных систем. М.: Наука. | — |
| `paruchuri2019_discrete_pmp.pdf` | Phogat K., Banavar R., Chatterjee D. (2017). arXiv:1708.04419. | 31 |
| `comiskey1998_nature.pdf` | Comiskey et al. (1998). Nature 394:253–255. DOI 10.1038/28349. | 3 |
| `he2020_particle_activation.pdf` | He W., Yi Z., Shen S. et al. (2020). Micromachines 11(5):498. DOI 10.3390/mi11050498. | 15 |
| `kang2025_dp_waveform.pdf` | Kang D., Zhao X., Wei X., Wu H., Zhang H., Zhao T. (2025). JSID 33(12):1114–1122. DOI 10.1002/jsid.2113. | 9 |
| `lai2026_e3dw_energy.pdf` | Lai J., Xiangba Q., Fu Y., Cao M., He N., Xu Y. (2026). JSID. DOI 10.1002/jsid.70042. | 8 |
| `lin2024_low_power.pdf` | Lin S. et al. (2024). Micromachines 15(9):1076. DOI 10.3390/mi15091076. | 14 |
| `wang2022_red_ghost.pdf` | Wang L., Zeng W., Liang Z., Zhou G. (2022). Micromachines 13(2):275. DOI 10.3390/mi13020275. | 11 |
| `yang2021_mechanisms.pdf` | Yang B.-R., Hu W.-J., Zeng Z. et al. (2021). JSID. DOI 10.1002/jsid.960. | 9 |
| `zhong2026_review.pdf` | Zhong X., Zhao X., Zhao T. (2026). Review on Image Preprocessing and Driving Waveform Design for EPDs. JSID. DOI 10.1002/jsid.70044. (Received 2025, accepted Mar 2026.) | 12 |
| `waveshare_code/epd2in13_V4.py` | Reference driver waveshareteam/e-Paper | 350 строк |
| `deb2002_nsga2.pdf` | Deb K., Pratap A., Agarwal S., Meyarivan T. (2002). NSGA-II. IEEE TEC 6(2):182–197. DOI 10.1109/4235.996017. | 16 |

### ⏳ Ждём одобрения запроса (paywall, скачиваешь руками)

| Имя файла | Источник | DOI | Зачем |
|---|---|---|---|
| `heikenfeld2011_review.pdf` | JSID 19(2):129–156 | [10.1889/JSID19.2.129](https://doi.org/10.1889/JSID19.2.129) | Канонический обзор-2011 |
| `zehner2003_drive_waveforms.pdf` | SID Digest 34:842–845 | [10.1889/1.1832402](https://doi.org/10.1889/1.1832402) | Канон по waveform AM-EPD |
| `bert2003_physics.pdf` | Displays 24(3):103–110 | [10.1016/S0141-9382(03)00060-1](https://doi.org/10.1016/S0141-9382(03)00060-1) | Микрофизика частиц |

### Опционально (если найдётся — отлично, не критично)

- Сухарев А.Г., Тимохов А.В., Фёдоров В.В. (2005, ФИЗМАТЛИТ; 2011 2-е изд.). Курс методов оптимизации. — `sukharev2005_course.pdf`
- E-Paper Displays (Wiley, 2022), главы 1–3 (книга под ред. Heikenfeld et al.).
- Amundson K., Sjodin T. (2006). *Achieving graytone images in microencapsulated EPD.* SID Digest 37, 1918–1921, DOI 10.1889/1.2433429.

### Уточнения после полной верификации скачанных файлов

- **He et al. 2020** (не «Tong 2020» как было в первом раунде разведки). Первый автор — Wenyao He, соавторы Zichuan Yi, Shitao Shen, Zhenyu Huang, Linwei Liu, Taiyuan Zhang, Wei Li, Li Wang, Lingling Shui, Chongfu Zhang, Guofu Zhou. Источник: Micromachines 11(5):498, опубликовано 14 May 2020.
- **Zhong et al. 2026** (в первом раунде писали «2024»). Полная атрибуция: Xiangjie Zhong, Xiaoyan Zhao, Tiesong Zhao (Fuzhou University). Received 20 June 2025, accepted 4 March 2026, JSID, DOI 10.1002/jsid.70044.
- **Lai et al. 2026** — первый автор Jinhui Lai, 6 авторов; JSID, DOI 10.1002/jsid.70042. Received 15 July 2025, accepted 27 January 2026.
- **Kang & Zhao 2025** — полный список из 6 авторов: Danling Kang, Xiaoyan Zhao, Xiaojie Wei, Hongxin Wu, Honghui Zhang, Tiesong Zhao.
- **Yang 2021** — полный список 9 авторов; первый автор Bo-Ru Yang. Тема: bistable displays, microcapsules, mechanisms.
- **Wang 2022** — 4 автора (Li Wang, Wenjun Zeng, Zhuopei Liang, Guofu Zhou).
- **Lin 2024** — 12 авторов; первый автор Shanling Lin. Тема: low-power waveform, refresh power, flicker, ghosting.

## Pending research (моих)

- Найти и проверить ru-источники по теории сигналов, оптимальному управлению для ГОСТ-библиографии.
- Поиск ru-обзоров по электронной бумаге (КомпьютерПресс уже найден, но это популярная статья — не годится; нужны статьи из eLibrary/CyberLeninka).
- Поиск ссылок на дискретный PMP по статье Boltyanskii (оригинал).
- Поиск моделей износа EPD (cycles-to-failure, DC imbalance literature).
- Изучить (когда будут PDF) Kang 2025 и Lai 2026 — нужно понять чем мы будем отличаться.

## Chapter Plan (черновик ~40 страниц, ГОСТ)

### Visual budget (минимум на главу)

ГОСТ Р 7.32-2017: каждая иллюстрация подписывается «Рисунок N — Название» (выровнено по центру под рисунком), таблица — «Таблица N — Название» (выровнено по левому краю над таблицей), сквозная нумерация по главе (например, «Рисунок 3.5» — 5-я иллюстрация в гл. 3).

| Глава | Рис. (мин.) | Табл. (мин.) | Что конкретно |
|---|---|---|---|
| 1. Введение | 1 | 0 | Схема 4-целевой оптимизации (E ↔ G ↔ τ ↔ L). |
| 2. Обзор | 2-3 | 1 | (а) AM-EPD архитектура, (б) waveform-таксономия, (в) опц. фото панели Waveshare; табл. — сравнение методов из лит. |
| 3. Модель | 2-3 | 1 | (а) микрокапсула (диаграмма), (б) PDE→ODE редукция (схема), (в) опц. калибровочные кривые; табл. — параметры η, R, q, m, ε и их источники. |
| 4. Теорема | 1-2 | 1 | (а) пример bang-bang waveform до/после оптимизации; табл. — обозначения и соответствия (Phogat↔Понтрягин↔наша). |
| 5. Алгоритм | 2 | 1 | (а) блок-схема ε-constraint + PMP, (б) Парето-фронт схема; табл. — сравнение со NSGA-II, complexity. |
| 6. Симуляция | 4-6 | 1-2 | (а) Парето-фронт, (б) примеры waveforms (наша vs Waveshare vs Kang), (в) ghost evolution для разных историй, (г) energy distribution, (д) опц. heatmaps по тест-набору; табл. — числа по 10 сценариям. |
| 7. Эксперимент | 6-8 | 3-4 | (а-б) фото стенда (общий + крупно INA219), (в) фото фотостанда, (г-д) INA219 трассы для 3-4 baseline, (е) сравнение симул↔стенд (Парето), (ж-з) фото экранов с примерами ghost для B0/B1/B2; табл. — статистика по 5 baseline × 10 сценариев. |
| 8. Заключение | 0-1 | 0 | опц. итоговая Парето-карта. |
| Приложения | 0-2 | 0-2 | опц. иллюстрации регистровой карты SSD1680, полные waveform таблицы. |
| **ИТОГО** | **~20-25** | **~10-12** | |

**Поток создания:**
- TikZ-диаграммы (концептуальные схемы) — пишутся прямо в `.tex` файлах в `tex/figures/diagrams/`.
- matplotlib plots (графики из симуляций) — генерируются в notebooks, сохраняются как PDF через `plt.savefig(..., format='pdf')` в `tex/figures/plots/`.
- Фотографии стенда — пользователь снимает по запросу, кладёт в `docs/inbox/`, я обрабатываю (crop/resize) и переношу в `tex/figures/raw_photos/`.
- Все figures используются в LaTeX через `\includegraphics{figures/<subdir>/<name>}` с подписью `\caption{Рисунок ... — ...}`.

### Структура и распределение страниц

| # | Глава | Стр. | Содержание | Срок |
|---|---|---|---|---|
| 0 | **Титул, оглавление, аннотация ru/en** | 3 | По ГОСТ 7.32. | неделя 5 |
| 1 | **Введение** | 3 | Актуальность (массовое EPD-применение, энергоэффективность), цель, задачи, новизна (N1+N2), положения на защиту, апробация. | неделя 1 |
| 2 | **Обзор предметной области** | 6 | 2.1 Архитектура EPD (микрокапсулы, AM-driver). 2.2 Waveform-методы: Zehner 2003 → He 2020 → Wang 2022 → Kang 2025 → Lai 2026 → Lin 2024 (таксономия). 2.3 Контроллер SSD1680: регистры, OTP, partial vs full. 2.4 Пробелы в литературе → наша задача. | неделя 1 |
| 3 | **Физическая модель (PDE → ODE)** | 6 | 3.1 Уравнения Nernst-Planck для микрокапсулы. 3.2 Mean-field редукция к ODE одного пикселя. 3.3 Стоксова форма; параметры η, q, R. 3.4 Граничное условие как управление u(t). 3.5 Калибровка по данным стенда. | неделя 2 |
| 4 | **Дискретная задача оптимального управления (M1)** | 7 | 4.1 Дискретизация по фазам LUT: u[k] ∈ {VSH1,VSH2,VSL,VCOM,0}. 4.2 Функционал J = Σ α·E[k] + β·G(z[k]) + γ·TP[k]. 4.3 Hard-constraint: Σ V[k]·TP[k] = 0 (charge balance). 4.4 Дискретный PMP (по Болтянскому/Paruchuri & Chatterjee 2019). **4.5 ТЕОРЕМА: оптимум в классе charge-balanced waveforms — bang-bang с ≤K_eff активных фаз; доказательство.** 4.6 Следствия и интерпретация. | неделя 2-3 |
| 5 | **Алгоритм построения Парето-границы (M2)** | 5 | 5.1 ε-constraint метод. 5.2 По каждому ε-срезу — PMP-задача из гл.4. 5.3 Свойства фронта: монотонность, недоминируемость. 5.4 Псевдокод и сложность. 5.5 Сравнительный анализ с NSGA-II как baseline. | неделя 3 |
| 6 | **Симуляция (Python notebook)** | 5 | 6.1 Архитектура (ODE-сим + surrogate). 6.2 Калибровочный pipeline. 6.3 Тест-набор (5-10 «диагностических» переходов: BB→WW, чекерборд, текст, изображения). 6.4 Результаты — Парето-фронт. 6.5 Сравнение с заводским LUT, Kang 2025 (если воспроизводимо), Lin 2024. | неделя 3-4 |
| 7 | **Экспериментальная валидация** | 5 | 7.1 Стенд: ESP32+SSD1680+INA219+камера. 7.2 Прошивка-расширение (новые опкоды для динамических LUT). 7.3 Протокол измерения (10 сценариев × 50 повторов). 7.4 Сравнение симулированного и измеренного Парето. 7.5 Анализ расхождений и пределов применимости. | неделя 4 |
| 8 | **Заключение** | 2 | Главные результаты, ограничения, направления развития. | неделя 5 |
|  | **Список литературы (ГОСТ Р 7.0.5-2008)** | 3 | ~30 ссылок: иностранные DOI + русские книги ВМК. | по ходу |
|  | **Приложения** | 3 | A. Код прошивки (выдержки). B. Notebook (структура). C. Полные waveform-LUT (наш и заводской). | неделя 5 |
| | **ИТОГО** | **~48** | (с запасом, плотно — 40) | |

### Распределение по фазам (до сентября-октября 2026, ≈20 недель)

| Фаза | Недели | Главы | Ключевой результат | Sidecar |
|---|---|---|---|---|
| **0. Setup** | W1 (текущая) | — | Прочитан Васильев гл.1-5 (методы оптимизации, основные обозначения), Понтрягин гл.1-3 (PMP канон), Paruchuri & Chatterjee 2019 целиком (дискретный PMP). LaTeX-каркас по ГОСТ. | Расширить прошивку ESP32 — опкод динамической записи LUT через USB (если ещё нет). |
| **1. Обзор + физика** | W2-W4 | 1 + 2 + 3 | `tex/intro.tex`, `tex/review.tex`, `tex/model.tex`. Все Wiley статьи прочитаны и просуммированы. PDE-модель Nernst-Planck выписана, mean-field редукция к ODE доказана. | Калибровочные измерения на стенде (I·V·t × все 4 типа переходов × 50 повторов). |
| **2. Теорема** | W5-W7 | 4 | `tex/theorem.tex`. **Главная структурная теорема** доказана (bang-bang ≤K_eff фаз). Опционально — вторая теорема (нижняя оценка `E ≥ f(G, τ)` через charge balance). | Прототип ODE-симулятора в Python (без оптимизации скорости). |
| **3. Алгоритм + симулятор** | W8-W11 | 5 + 6 | `tex/algorithm.tex`, `tex/simulation.tex`, `notebook/optimize.ipynb` рабочий. Парето-фронт построен в симуляции. | Surrogate-модель (NN или spline) обучен на калибровочных данных. |
| **4. Эксперимент** | W12-W15 | 7 | `tex/experiment.tex`. Все 5 baseline (B0..B4) измерены. Сравнение симулированного и измеренного Парето. Фотостанд готов. | Анализ расхождений симуляция↔стенд. Корректировка surrogate. |
| **5. Доводка** | W16-W18 | 0 + 8 + библиография + приложения | `dist/thesis.pdf` готов. Полная вычитка. Все ссылки проверены. ГОСТ-формат проверен. | Готовится 15-слайдовая презентация. |
| **6. Защита** | W19-W20 | — | Презентация. Опционально — 6-страничный SID-style препринт. | |

**Темп:** ≈1 глава за 2-3 недели. Достаточно воздуха для пересдач/переписываний. Если что-то пойдёт быстрее — берём вторую теорему и расширенный эксперимент.

### Риски и митигации

| Риск | Вероятность | Митигация |
|---|---|---|
| Теорема не доказывается в полном объёме | средняя | Зарезервирован «слабый вариант»: доказать для подкласса waveforms (например, симметричных). Это всё ещё содержательный результат. |
| Калибровка ODE-симулятора не сходится с реальным стенда | средняя | Использовать surrogate как backup. В теореме оставить «модельные» утверждения, явно отделив от физических. |
| Wiley статьи не получены вовремя | низкая | Уже есть аннотации и заявленные результаты — можно сослаться, проверив издательскую landing page. Полные тексты нужны для главы 2 (обзор) — можно отложить до недели 1. |
| Кастомный LUT не «проигрывается» из-за temperature override | низкая | Уже решено: используем `0x22=0xC7` и НЕ вызываем `0x1A` без необходимости. |
| Камерные измерения ghost зашумлены | средняя | Усреднять по 10+ кадрам, использовать только b/w канал, фиксировать ROI. |
| Дедлайн смещается из-за PDE-главы | средняя | PDE-уровень — компактный, по сути обзорный (теорема — на ODE/discrete уровне). |

---

## INSIGHT collection

Содержательные инсайты, которые войдут в текст как ключевые «находки/наблюдения». Каждый INSIGHT — это утверждение со ссылкой на источник, которое формирует нарратив работы.

### I-01. Архитектура waveform SSD1680 — это уже дискретная конечномерная задача
LUT'а — 5 sub-LUT × 12 фаз × 4 sub-frame × алфавит источников {VSH1, VSH2, VSL, VCOM, 0}. **Без всякой натяжки** это попадает в класс задач дискретного оптимального управления (Paruchuri-Chatterjee 2019 (arXiv 2017), arXiv:1708.04419). Это даёт нам право использовать дискретный PMP Болтянского для нашей теоремы.
→ **Применение:** § 4.1, § 4.4.

### I-02. «Ключевой фикс» 0x22=0xC7 — это не bug, это features архитектуры
Биты 0x22 определяют последовательность операций. 0xF7/0xFF включают «Load temperature value», что запускает Waveform Setting Searching Mechanism (Section 6.9 datasheet), перезаписывающий пользовательский LUT заводским из OTP-таблицы по температуре. 0xC7/0xCF — пропускают этот шаг. Эту находку можно использовать как иллюстрацию «подводных камней реальных контроллеров» во введении и в гл. 7.
→ **Применение:** § 2.3, § 7.2, опционально — отдельный «engineering remark».

### I-03. Waveshare-овский «fast init» — это не оптимизация waveform, а подмена температуры
В `init_fast()` они через регистр 0x1A фактически записывают `T = +6.25°C`, и контроллер по таблице OTP выбирает более короткую (потому что предполагает медленную физику холодной среды) waveform. Это даёт нам сравнительный baseline B1 (Waveshare fast) — не оптимальный, но широко используемый.
→ **Применение:** § 2.3, § 7.4.

### I-04. Энергетическая модель Lin 2024 встраивается в нашу постановку напрямую
`P_peak = ½·C·ΔV²·f·V_source` — это конкретное выражение, связывающее waveform (через ΔV между фазами) и потребляемую мощность. Подставляется в функционал `E = Σ P[k]·TP[k]` без модификаций.
→ **Применение:** § 3.4, § 4.2.

### I-05. Стоксова формула Wang 2022 даёт физическую модель для ODE-симулятора
`v = Uq/(6πdηR) · (1 − e^{-6πηR·t/m})` описывает скорость частицы в микрокапсуле. После калибровки одного-двух параметров (η·R — вязкость·радиус) она предсказывает отклик пикселя на single-phase waveform. Это основа симулятора S3.
→ **Применение:** § 3.3, § 6.1.

### I-06. Charge balance — единственное жёсткое физическое ограничение
`Σ_phase V[k]·TP[k] = 0` — без этого панель накапливает DC, что приводит к stuck pixels и износу. Все авторы (Zehner 2003, Wang 2022, Lin 2024) это явно учитывают. У нас — hard-constraint в постановке задачи M1.
→ **Применение:** § 4.3, § 5.2.

### I-07. Существующий конкурент — Kang & Zhao 2025 (JSID 33/12) — алгоритмический, не структурный
Они применяют DP к задаче «найти оптимальный путь waveform», получая численное решение. Наша работа отличается: (а) формулировка как многокритериальной задачи с PMP-теоремой о структуре оптимума, (б) явный hard-constraint charge balance в постановке, (в) сравнение Парето-границ, а не отдельных точек. Это надо явно прописать в § 2.4 (gap analysis) и § 5.4 (комплексное сравнение).
→ **Применение:** § 2.4, § 5.4.

### I-08. Российская мат.школа даёт нам легитимный фундамент для ГОСТ-курсовой ВМК
Понтрягин-Болтянский-Гамкрелидзе-Мищенко (1961) — фундамент PMP. Васильев (2002, ВМК) — методы оптимизации, включая методы решения экстремальных задач в функциональных пространствах. Сухарев-Тимохов-Фёдоров (2005, ВМК) — общий курс. Это «свой» канон для ВМК МГУ.
→ **Применение:** библиография; раздел «методология» (если нужен по ГОСТ).

### I-09. Multi-baseline таксономия (B0..B4) — структурирует экспериментальную главу
B0 (Waveshare full), B1 (Waveshare fast), B2 (custom static), B3 (content-adaptive), B4 (temp+content). Эти пять точек дают понятный нарратив: «вот что есть, вот что мы добавляем, вот что выигрываем».
→ **Применение:** § 7 целиком.

### I-10. Дедлайн жёсткий — 5 недель — диктует компактность теоретической главы
PDE-уровень — обзорный, без новых результатов. Теорема — одна, на discrete уровне. Алгоритм — конструктивный. Эксперимент — по 50 повторов на сценарий, чтобы статистика была. Если что-то выпадает по срокам — первой жертвуем «комплексное» сравнение с воспроизведённым Kang 2025 (оставим как future work).
→ **Применение:** общая дисциплина scope.

---

## Sessions
<!-- aif:sessions:start -->
### 2026-05-24 22:00 — Round 2: согласование всех ключевых развилок

**What changed:**
- Закрыты Q1–Q5: каскад PDE→ODE→M1→M2, симулятор S3, метрики G2+SSIM/L3+L4, ghost-измерение через iPhone+ImageJ, дедлайн **июнь 2026** (~5 недель), режим работы — chapter-by-chapter с обсуждением.
- Скачана статья Paruchuri-Chatterjee 2019 (arXiv 2017) (arXiv:1708.04419), `docs/refs/paruchuri2019_discrete_pmp.pdf`, 31 стр. — основной технический референс для теоремы.
- Извлечён waveshare-овский reference-код (epd2in13_V4.py): полный init для full и fast, расшифровка их «магии» (фейковая температура через 0x1A).
- Сформирована baseline-таксономия B0..B4 (Waveshare full, fast, custom static, content-adaptive, temp+content-adaptive).
- Sukharev fragment (17 стр) удалён — это была preview-демо, не книга.
- Зафиксирован Chapter Plan на ~48 страниц (40 целевых) с распределением по 5 неделям.
- Зафиксирован INSIGHT collection (10 ключевых наблюдений).
- Pending downloads (нужны от пользователя руками) — обновлённый список, 6 Wiley + 2 Elsevier/Nature + 4 русских учебника.

**Key notes:**
- Конкурент Kang 2025 — алгоритмический подход; наша работа отличается структурной теоремой и Парето-формулировкой.
- Энергомодель Lin 2024 (P_peak формула) встраивается напрямую в наш функционал.
- Сжатый дедлайн 5 недель — диктует компактность PDE-главы (обзорная, теорема — на discrete уровне).

**Links (paths):**
- `docs/refs/SSD1680.pdf`, `docs/refs/SSD1680.txt`
- `docs/refs/INA219.pdf`, `docs/refs/INA219.txt`
- `docs/refs/paruchuri2019_discrete_pmp.pdf`
- `docs/refs/waveshare_code/epd2in13_V4.py`
- `.ai-factory/config.yaml`
- TaskList #1..#8.

### 2026-05-24 21:18 — Round 1: проблемное пространство, разведка железа и литературы

**What changed:**
- Создана структура `.ai-factory/` с `config.yaml` (язык ru, paths по умолчанию).
- Согласован уровень новизны N2+N1 (свой алгоритм + структурная теорема).
- Скачаны и распарсены: `docs/refs/SSD1680.pdf` (46 стр.), `docs/refs/SSD1680.txt`, `docs/refs/INA219.pdf` (10 стр.), `docs/refs/INA219.txt`.
- Извлечены критические регистры SSD1680 (0x22, 0x32, 0x3C, 0x37, 0x2C, Section 6.7-6.9).
- **Подтверждён «ключевой фикс» пользователя:** 0xC7/0xCF — играют записанный пользователем LUT; 0xF7/0xFF — содержат «Load temperature value», что запускает поиск в OTP-таблице и перезаписывает наш LUT заводским WS.
- Собран первый раунд верифицированной литературы (16 позиций), из них 8 требуют ручного скачивания пользователем.

**Key notes:**
- Дискретность waveform-LUT (5 sub-LUT × 12 фаз × выбор источника {VSH1, VSH2, VSL, VCOM, GND}) — это конечномерная задача дискретного оптимального управления. Подойдёт PMP/DP.
- В литературе уже существует Kang 2025 (DP-based waveform) — нужно явно отличить нашу постановку.
- Lin 2024 даёт явную формулу `P_peak = ½·C·ΔV²·f·V_source` — основа энергомодели.
- Wang 2022 даёт Стоксову формулу скорости частицы — основа симулятора.

**Links (paths):**
- `docs/refs/SSD1680.pdf`, `docs/refs/SSD1680.txt`
- `docs/refs/INA219.pdf`, `docs/refs/INA219.txt`
- `.ai-factory/config.yaml`
- TaskList #1–#8 (см. TaskList tool).
<!-- aif:sessions:end -->
