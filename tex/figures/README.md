# tex/figures/ — визуальный аппарат курсовой

Структура и контроль состояния всех figures/tables.

## Подпапки

| Папка | Назначение | Источник |
|---|---|---|
| `diagrams/` | Концептуальные диаграммы (схемы редукции, state machines, taxonomy) | TikZ-исходник `.tex` внутри документа или отдельный `.tikz` файл, либо PDF-экспорт draw.io/Inkscape |
| `plots/` | Графики из numerical экспериментов (Парето-фронт, INA219 трассы, distributions) | matplotlib → `plt.savefig('tex/figures/plots/<name>.pdf', bbox_inches='tight')` |
| `raw_photos/` | Фотографии физического стенда и фотостанда | iPhone/USB-камера. Перед commit-ом — crop через Preview/scikit-image, ресайз до ≤2000 px по длинной стороне |
| `screenshots/` | Скриншоты с экрана EPD (ghost-примеры, B0..B4 сравнения) | Камера или RAW-капчер с панели |

## Naming convention

`<chapter>_<short_name>.<ext>` (lowercase, snake_case).

Пример:
- `01_opt_axes_diagram.pdf` — Рисунок 1.1 (схема 4-целевой оптимизации)
- `03_capsule_micro.pdf` — Рисунок 3.1 (микрокапсула)
- `07_stand_overview.jpg` — Рисунок 7.1 (общий вид стенда)
- `07_ina219_closeup.jpg` — Рисунок 7.2 (крупно INA219)
- `06_pareto_sim_vs_stand.pdf` — Рисунок 6.4 (Парето-фронт)

## Figure budget (синхронизировано с RESEARCH.md → Chapter Plan → Visual budget)

Статусы: `planned` → `raw_ready` → `final` → `in_thesis`.

### Глава 1 — Введение (минимум 1 рис.)

| ID | Файл | Описание | Статус |
|---|---|---|---|
| 1.1 | `diagrams/01_opt_axes.tex` (TikZ) | Схема 4-целевой оптимизации (E ↔ G ↔ τ ↔ L) с конфликтами по парам | planned |

### Глава 2 — Обзор (2-3 рис., 1 табл.)

| ID | Файл | Описание | Статус |
|---|---|---|---|
| 2.1 | `diagrams/02_am_epd_arch.tex` | Архитектура AM-EPD (TFT матрица + микрокапсулы) | planned |
| 2.2 | `diagrams/02_waveform_taxonomy.tex` | Таксономия waveform-методов (Zehner 2003 → Kang 2025) | planned |
| 2.3 | `raw_photos/02_waveshare_panel.jpg` (опц.) | Фото панели Waveshare 2.13" V4 | planned |
| Т2.1 | inline в `02_review.tex` | Сравнительная таблица методов из литературы (10 строк) | planned |

### Глава 3 — Модель (2-3 рис., 1 табл.)

| ID | Файл | Описание | Статус |
|---|---|---|---|
| 3.1 | `diagrams/03_microcapsule.pdf` | Микрокапсула с заряженными частицами + поле | planned |
| 3.2 | `diagrams/03_pde_to_ode_reduction.tex` | Схема редукции PDE → ODE → discrete | planned |
| 3.3 | `plots/03_calibration_curves.pdf` (опц.) | Калибровочные кривые reflectance(U,t) | planned |
| Т3.1 | inline | Параметры модели (η, R, q, m, ε) и их источники | planned |

### Глава 4 — Теорема (1-2 рис., 1 табл.)

| ID | Файл | Описание | Статус |
|---|---|---|---|
| 4.1 | `plots/04_bang_bang_example.pdf` | Пример bang-bang waveform до/после оптимизации | planned |
| Т4.1 | inline | Таблица обозначений (Phogat ↔ Понтрягин ↔ наша) | planned |

### Глава 5 — Алгоритм (2 рис., 1 табл.)

| ID | Файл | Описание | Статус |
|---|---|---|---|
| 5.1 | `diagrams/05_eps_constraint_flow.tex` | Блок-схема ε-constraint + PMP | planned |
| 5.2 | `diagrams/05_pareto_construction.tex` | Схема построения Парето-фронта по срезам | planned |
| Т5.1 | inline | Сравнение со NSGA-II (complexity, time, quality) | planned |

### Глава 6 — Симуляция (4-6 рис., 1-2 табл.)

| ID | Файл | Описание | Статус |
|---|---|---|---|
| 6.1 | `plots/06_pareto_3d.pdf` | 3D-облако Парето-фронта (E, G, τ) | planned |
| 6.2 | `plots/06_pareto_2d_projections.pdf` | 2D-проекции попарно | planned |
| 6.3 | `plots/06_waveform_examples.pdf` | Примеры waveforms (наш, Waveshare, Kang) | planned |
| 6.4 | `plots/06_ghost_evolution.pdf` | Ghost evolution для разных историй | planned |
| 6.5 | `plots/06_energy_dist.pdf` | Energy distribution по тест-набору | planned |
| Т6.1 | inline | Числа по 10 сценариям (E_avg, G_med, τ_max ± std) | planned |

### Глава 7 — Эксперимент (6-8 рис., 3-4 табл.)

| ID | Файл | Описание | Статус |
|---|---|---|---|
| 7.1 | `raw_photos/07_stand_overview.jpg` | Общий вид стенда | planned (нужно фото) |
| 7.2 | `raw_photos/07_ina219_closeup.jpg` | Крупно INA219 + шунт | planned (нужно фото) |
| 7.3 | `raw_photos/07_photostand.jpg` | Фотостанд (кожух, камера, освещение) | planned (нужно фото) |
| 7.4 | `plots/07_ina219_traces.pdf` | INA219 трассы для 3-4 baseline | planned |
| 7.5 | `plots/07_sim_vs_real_pareto.pdf` | Симулированный vs реальный Парето | planned |
| 7.6 | `screenshots/07_ghost_b0.jpg` | Пример ghost для B0 (Waveshare full) | planned (нужно фото) |
| 7.7 | `screenshots/07_ghost_b1.jpg` | Пример ghost для B1 (Waveshare fast) | planned (нужно фото) |
| 7.8 | `screenshots/07_ghost_b2.jpg` | Пример ghost для B2 (наш custom) | planned (нужно фото) |
| Т7.1 | inline | Статистика по 5 baseline × 10 сценариев | planned |
| Т7.2 | inline | Сравнение симуляция↔стенд по energy | planned |
| Т7.3 | inline | Сравнение по latency | planned |

### Глава 8 — Заключение (0-1 рис.)

| ID | Файл | Описание | Статус |
|---|---|---|---|
| 8.1 (опц.) | `plots/08_final_pareto.pdf` | Итоговая Парето-карта (с baseline'ами) | planned |

### Приложения

| ID | Файл | Описание | Статус |
|---|---|---|---|
| A.1 (опц.) | `diagrams/A1_ssd1680_regmap.tex` | Регистровая карта SSD1680 | planned |

## Как добавить figure

### TikZ-диаграмма (внутри `.tex`)

```latex
\begin{figure}[H]
    \centering
    \begin{tikzpicture}[scale=1.2]
        % ... drawing ...
    \end{tikzpicture}
    \caption{Описание рисунка}
    \label{fig:01_opt_axes}
\end{figure}
```

### matplotlib-график (из notebook)

```python
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(6, 4))
# ... plot ...
plt.tight_layout()
plt.savefig('../tex/figures/plots/06_pareto_3d.pdf', bbox_inches='tight', dpi=300)
```

Затем в LaTeX:
```latex
\begin{figure}[H]
    \centering
    \includegraphics[width=0.85\textwidth]{plots/06_pareto_3d.pdf}
    \caption{Парето-фронт по трём целям}
    \label{fig:06_pareto_3d}
\end{figure}
```

### Фотография (от пользователя)

1. Пользователь снимает на iPhone/камеру, кладёт в `docs/inbox/<short_name>.jpg`.
2. Обработка через `python/preprocess_photo.py` (TODO: создать в M6): crop, resize, exposure.
3. Финальный файл переносится в `tex/figures/raw_photos/<chapter>_<name>.jpg`.

## Контроль статуса

Обновляй колонку «Статус» по мере наполнения:
- `planned` — ID зарезервирован, файла ещё нет.
- `raw_ready` — есть raw-материал (фото, raw .pdf из notebook), но не обработан.
- `final` — финальный файл готов, лежит на месте.
- `in_thesis` — `\includegraphics` или TikZ-код уже в соответствующем `.tex` главы.

Цель к M7: все ID в статусе `in_thesis`.
