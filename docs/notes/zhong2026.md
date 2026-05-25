# Конспект: Zhong et al. (2026) — обзор image preprocessing + driving waveforms

Источник: `docs/refs/zhong2026_review.pdf` (12 стр.).
- **Авторы:** Xiangjie Zhong, Xiaoyan Zhao, Tiesong Zhao.
- **Journal:** Journal of the Society for Information Display, 2026.
- **DOI:** [10.1002/jsid.70044](https://doi.org/10.1002/jsid.70044).
- **Received** 20 June 2025, **Accepted** 4 March 2026.
- **Affiliation:** Fuzhou University.

**Самый свежий обзор waveform-методов и image processing для EPD.
Главный single-source для § 2 (Обзор) нашей курсовой.**

---

## Структура обзора

Главы обзора:
1. Введение в EPD (history, applications).
2. **Image Preprocessing Algorithms:**
   - 2.1 Halftoning (Floyd-Steinberg и аналоги для grayscale представления).
   - 2.2 Image enhancement (brightness, contrast pre-boost).
   - 2.3 Halftoned video compression для EPD video.
3. **Driving Waveform Methods (Sec 3-4):**
   - Four-stage waveforms.
   - Three-stage waveforms.
   - Optimized waveforms based on response delay.
   - Three-color (b/w/r) waveforms.
   - Damping oscillation activation phase.
   - LTDR (Long-Term Display Refresh) для динамических изображений.

## Таксономия методов по Zhong

| Категория | Представители |
|---|---|
| **Image preprocessing** | Halftoning, brightness enhancement, LTDR |
| **Многостадийные waveforms** | Three-stage / Four-stage |
| **Optimization-based** | Response-delay optimization, particle-aware methods |
| **Multi-color** | Three-color (b/w/r) с red-ghost handling |
| **Dynamic content** | LTDR — fast refresh для video |
| **Physical-based** | Damping oscillation, activation phase splitting |

## Ключевые цитированные работы (можно через secondary cite!)

Zhong со-ссылается на (важно для нашей работы — даёт нам цепочку cite, если
оригинальные PDFs не получены):
- Amundson 2016 (Handbook of Visual Display Technology, EPD chapter).
- Kim et al. (color EPD).
- Ito et al. (red-color handling).

## Связь с нашей курсовой

### Главный источник для § 2 (Обзор)

Zhong **уже сделал нашу работу по обзору**: предложил таксономию,
показал hierarchy методов. Мы:
- В § 2.2 структурируем наш обзор **по их таксономии** (Image processing,
  Multi-stage waveforms, Optimization-based, ...).
- Каждую категорию иллюстрируем 1-2 ключевыми работами (Zehner historical
  → Wang 2022 → Kang 2025 → Lai 2026 → Lin 2024 → He 2020).
- Завершаем § 2.4 (Gap analysis): что Zhong **не упомянул** — отсутствие
  unified multi-objective формулировки с теоретическим бекграундом.

### Замена для Heikenfeld 2011

В нашем плане B (без 3 неполученных PDF) Heikenfeld 2011 (canonical 2011
review) заменяется через **Zhong 2026** (modern 2026 review). Zhong
покрывает все темы Heikenfeld + новые работы 2012-2025.

### Также — Zhong as «umbrella citation»

Для утверждений общего характера («ghost is a known issue in EPD»,
«multiple waveform-shaping approaches exist») мы можем цитировать
**только Zhong** как summarising reference, не утопая в детальных primary
citations. Это упрощает текст обзора.

## Главы цитирования

- **§ 1.1 (Актуальность):** Zhong как summary of current state в области.
- **§ 2.1-2.4 (весь обзор):** **главная база** для структуры главы.
- **§ 2.4 (Gap):** Zhong **не покрывает** unified multi-objective формулировку
  — это место для нашей работы.

## bib-key

`zhong2026_review`
