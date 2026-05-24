# Конспект: Paruchuri & Chatterjee (2019, IEEE TAC)
## «Discrete time Pontryagin maximum principle for optimal control problems under state-action-frequency constraints»

Источник: `docs/refs/paruchuri2019_discrete_pmp.pdf` (31 стр.).
- DOI: 10.1109/TAC.2019.2893160.
- Preprint: arXiv:1708.04419v1 (15 Aug 2017).
- Авторы: Pradyumna Paruchuri, Debasish Chatterjee (IIT Bombay).

**Это — несущий технический референс для Теоремы 4.1 нашей курсовой.**
Полный текст доступен (PDF c text layer), конспект — содержательный.

---

## §1. Введение

**Контекст.** Авторы рассматривают задачи дискретного оптимального управления
с тремя типами ограничений:
1. Pointwise state constraints `x_t ∈ S_t`.
2. Pointwise control constraints `u_t ∈ U_t`.
3. **Frequency constraints** на спектр Фурье управления — главная новизна.

Первые два типа покрыты классическим дискретным PMP [Boltyanskii 1978]. Третий
тип constraint вводит связь между управлениями в разные моменты времени
(через DFT) — классический pointwise Hamiltonian maximization теряет силу.

**Применение в нашей курсовой:** мы используем структуру (1) + (2), но не
frequency constraints. Однако техника доказательства, разработанная авторами
для случая (3), легко проецируется на наш более простой случай — потому что
наш дополнительный constraint (charge balance `Σ V·TP = 0`) также вносит
зависимость между управлениями в разные моменты времени — структурно аналогичную
frequency constraint, но более простую (линейное равенство вместо DFT-условия).

---

## §2. Problem Setup

**Динамика (формула 2.1):**
$$x_{t+1} = f_t(x_t, u_t), \quad t = 0, \ldots, T-1, \quad x_t \in \mathbb{R}^d, u_t \in \mathbb{R}^m.$$

Функции `f_t` — непрерывно дифференцируемые по `(x, u)`.

**Целевая задача (формула 2.3):**
$$\min_{u_t \in U_t} \; \sum_{t=0}^{T-1} c_t(x_t, u_t)$$
при ограничениях:
- динамика (2.1);
- state constraints `x_t ∈ S_t` для `t = 0, ..., T`;
- control constraints `u_t ∈ U_t` для `t = 0, ..., T-1`;
- frequency constraints `\widehat{u}^{(k)} \in F^{(k)}` для каждого канала управления `k`.

**Frequency constraints (формулы 2.2, 2.6):**
DFT `\widehat{u}^{(k)} = F u^{(k)}` ограничен поддержкой:
$$\widehat{u}^{(k)} \in F^{(k)} = \{v \in \mathbb{C}^T \mid \text{supp}(v) \subset W^{(k)}\}.$$

Множества `W^{(k)} ⊂ {1, ..., T}` задают допустимые частоты — то есть пользователь
определяет, какие гармоники DFT могут быть ненулевыми. Это позволяет ограничивать
band управления (например, низкочастотные — для actuator с медленной механикой).

**Аналог в нашей курсовой.** У нас вместо frequency constraint —
charge balance `Σ_t V(u_t) · TP_t = 0`. Это эквивалентно линейному равенству
`A·u = 0`, где `A = (V(VSH1), V(VSH2), V(VSL), V(VCOM), 0)`. Такое равенство
точно укладывается в схему «non-pointwise constraint, зависящий от
последовательности `u`», для которой классический PMP неприменим.

---

## §3. Main Result — Theorem 3.1

**Theorem 3.1 (Pontryagin maximum principle under state-action-frequency
constraints).** Пусть `(x_t^*)_{t=0}^T, (u_t^*)_{t=0}^{T-1}` — оптимальная
state-action траектория. Определим Гамильтониан:
$$H_{\nu, \vartheta}(\zeta, s, \xi, \mu) := \langle \zeta, f_s(\xi, \mu) \rangle - \nu \, c_s(\xi, \mu) - \langle \vartheta, \widetilde{F}_s \mu \rangle.$$

Тогда существуют:
- adjoint траектория `\{η_t^f\}_{t=0}^{T-1}`;
- state-related sequence `\{η_t^x\}_{t=0}^T`;
- пара мультипликаторов `(η^C, η^{bu}) \in \mathbb{R} \times \mathbb{R}^\ell`,

удовлетворяющие условиям:

**(PMP-i) Non-negativity:** `η^C ≥ 0`.

**(PMP-ii) Non-triviality:** adjoint trajectory и пара мультипликаторов не
обращаются в ноль одновременно.

**(PMP-iii) State + adjoint dynamics:**
$$x_{t+1}^* = \frac{\partial H^{η^C, η^{bu}}}{\partial \zeta}(\eta_t^f, t, x_t^*, u_t^*), \quad t = 0, ..., T-1;$$
$$η_{t-1}^f = \frac{\partial H^{η^C, η^{bu}}}{\partial \xi}(\eta_t^f, t, x_t^*, u_t^*) - η_t^x, \quad t = 1, ..., T-1.$$

Где `η_t^x` лежит в dual cone «палатки» (tent) `q_t^x(x_t^*)` множества `S_t` в точке `x_t^*`.

**(PMP-iv) Transversality:** условия на `η_0^x, η_T^x` и `η_{T-1}^f`.

**(PMP-v) Hamiltonian maximization (pointwise):**
$$\frac{\partial H^{η^C, η^{bu}}}{\partial \mu}(\eta_t^f, t, x_t^*, u_t^*) \cdot \tilde{u}_t \leq 0 \quad \text{whenever} \quad u_t^* + \tilde{u}_t \in q_t^u(u_t^*).$$

То есть оптимальное `u_t^*` доставляет локальный максимум Гамильтониана на
*касательном конусе* `q_t^u` к допустимому множеству `U_t` в точке `u_t^*`.

**(PMP-vi) Frequency constraints:** `F(u_0^*, ..., u_{T-1}^*) = 0`
(оптимальное управление лежит в допустимой частотной поддержке).

**Доказательство:** через игольчатые вариации (классическая техника
Понтрягина-Болтянского), но с тщательным построением касательных конусов
к комбинированному допустимому множеству (state × action × frequency).
Полное доказательство — в Appendix C.

---

## Remarks (важные)

**Remark 3.1.** Можно нормализовать `η^C ∈ {0, 1}`. Случай `η^C = 1` —
**normal extremal**, `η^C = 0` — **abnormal extremal**. Abnormal соответствует
ситуации, когда constraint qualification нарушается (например, нет
internal point в допустимом множестве).

**Remark 3.2.** Дополнительный член `⟨η^{bu}, \widetilde{F}_t μ⟩` в
Гамильтониане — единственное отличие от классического PMP Болтянского.
Он не влияет на state и adjoint dynamics, только на Hamiltonian
maximization condition.

**Remark 3.3.** Применение в линейном случае (LQR без частотных constraints)
сводится к классическому LQR Беллмана-Калмана.

---

## §4. Linear quadratic problem with frequency constraints (Proposition 4.2)

Авторы детально разбирают LQ case: `f_t(x, u) = Ax + Bu`, `c_t(x, u) = x^T Q x + u^T R u`,
с frequency constraints на `u`. Получают tight conditions для normal/abnormal
extremals в зависимости от controllability и количества доступных гармоник.

**Применение в курсовой:** прямой аналог — после линеаризации нашей системы
по управляющему напряжению (что верно для малых отклонений в Стоксовой модели,
см. § 3.4) мы попадаем в LQ-родственный класс. Это даёт нам ключ к доказательству,
что наш оптимум — *normal extremal* и можно явно характеризовать число активных
фаз waveform.

---

## Что используем напрямую в нашей Теореме 4.1

| Из Paruchuri 2019 | В нашей курсовой |
|---|---|
| Theorem 3.1: формулировка дискретного PMP | § 4.4 — общая формулировка для нашей задачи |
| (PMP-v) Hamiltonian maximization на касательном конусе | § 4.5 — bang-bang из дискретности `U = {VSH1, VSH2, VSL, VCOM, 0}` |
| (PMP-vi) Constraint condition (наш аналог — charge balance) | § 4.3 — переформулировано как линейное равенство `Σ V(u_t)·TP_t = 0` |
| Proposition 4.2: характеризация normal extremals в LQ-case | § 4.6 — следствие: число активных фаз `K_eff` оценивается через размерность пространства сопряжённых переменных |

---

## Ключевые отличия нашей формулировки от Paruchuri

1. **Constraint set:** у нас `Σ V·TP = 0` (одно линейное равенство),
   у них — frequency support condition (равенство нулю DFT-компонент
   вне `W^{(k)}`). Структурно одного типа (linear equality), но наш проще.

2. **Action set:** у нас `U_t = U = {VSH1, VSH2, VSL, VCOM, 0}` —
   **дискретное конечное множество** (не выпуклое!),
   у них `U_t ⊂ \mathbb{R}^m` — произвольное (часто выпуклое).
   Дискретность U — наш вклад: переход от tangent cone в (PMP-v) к
   *direction set* (всего 4 ненулевых перехода между уровнями source).

3. **Cost function:** у нас три цели (E, G, τ) — мы их скаляризуем
   в ε-constraint методе (см. § 5.2), а Paruchuri рассматривает один
   функционал. Наша работа выходит на многокритериальную постановку
   *после* применения их PMP к каждому ε-срезу.

Это и есть **наша новизна** относительно Paruchuri 2019: применение их
теоремы к (а) дискретному action set, (б) charge balance constraint,
(в) многокритериальной структуре через ε-constraint.

---

## Ссылка в курсовой

`\cite{paruchuri2019_discrete_pmp}` — bib key соответствует.
