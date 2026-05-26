"""LUT (Look-Up Table) для SSD1680 — encode/decode/validate.

Формат waveform SSD1680 описан в datasheet Rev 0.14, Section 6.7
(Figure 6-6 «Waveform Setting mapping»). Регистр 0x32 принимает 153 байта,
кодирующие:

- ``VS[nX-LUTm]``  — выбор источника напряжения для каждой фазы n=0..11,
                     каждого sub-frame X=A,B,C,D, каждого sub-LUT m=0..4.
                     2 бита на значение → 60 байт.
- ``TP[nX]``       — длительность time-phase для каждой фазы и sub-frame
                     (1 байт каждое) → 48 байт.
- ``SR[nXY]``      — slew rate между sub-frames A-B и C-D
                     (1 байт каждое) → 24 байта.
- ``RP[n]``        — repeat count для каждой фазы (1 байт) → 12 байт.
- ``FR[n]``        — frame rate для каждой фазы (4 бита, 2 фазы / байт) → 6 байт.
- ``XON[nXY]``     — gate gating on/off для sub-frame pair (1 бит, 8 в байте) → 3 байта.

Итого 60 + 48 + 24 + 12 + 6 + 3 = 153 байта.

Источник напряжения — 2 бита:
    00 → VCOM,  01 → VSH1,  10 → VSL,  11 → VSH2.

Физическое ограничение **ε-зарядового баланса** (релаксация из § 4.3 курсовой):
    |Σ_k V[k] · TP[k]| ≤ ε,   где ε ≈ 0.05 В·с
обоснование ε по разрешающей способности INA219 и индустриальной погрешности
(см. RESEARCH.md → INSIGHT I-06 и tex/chapters/04_theorem.tex § 4.3).
Строгая версия Σ V·TP = 0 даёт вырождение в линейной overdamped-модели
(нулевое перемещение пикселя), поэтому везде используем ε-вариант.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np

logger = logging.getLogger(__name__)

# Размеры формата.
LUT_BYTES = 153
N_PHASES = 12
N_SUB_LUTS = 5
N_SUB_FRAMES = 4  # A, B, C, D


class Source(IntEnum):
    """2-битный код источника напряжения (datasheet Section 6.6/6.7)."""

    VCOM = 0b00  # 0x00 в waveform setting
    VSH1 = 0b01  # обычно +15 В
    VSL  = 0b10  # обычно −15 В
    VSH2 = 0b11  # обычно +5..+8 В (промежуточный grey level)


@dataclass
class Lut:
    """In-memory представление 153-байтной LUT SSD1680.

    Все поля — numpy arrays нужной формы. Значения по-умолчанию = нули
    (что соответствует пустой/однополярной waveform; для практики надо
    заполнять осознанно).
    """

    # vs[m, n, X] = код Source для LUTm, phase n, sub-frame X (A=0, B=1, C=2, D=3)
    vs: np.ndarray = field(default_factory=lambda: np.zeros((N_SUB_LUTS, N_PHASES, N_SUB_FRAMES), dtype=np.uint8))
    # tp[n, X] = длительность time-phase для phase n, sub-frame X (0..255)
    tp: np.ndarray = field(default_factory=lambda: np.zeros((N_PHASES, N_SUB_FRAMES), dtype=np.uint8))
    # sr[n, pair] = slew rate для phase n, pair (AB=0, CD=1)
    sr: np.ndarray = field(default_factory=lambda: np.zeros((N_PHASES, 2), dtype=np.uint8))
    # rp[n] = repeat count для phase n
    rp: np.ndarray = field(default_factory=lambda: np.zeros(N_PHASES, dtype=np.uint8))
    # fr[n] = frame rate (4-битный) для phase n
    fr: np.ndarray = field(default_factory=lambda: np.zeros(N_PHASES, dtype=np.uint8))
    # xon[n, pair] = gate gating bit для phase n, pair (AB=0, CD=1)
    xon: np.ndarray = field(default_factory=lambda: np.zeros((N_PHASES, 2), dtype=np.uint8))

    # ---- Encoding ---------------------------------------------------------

    def encode(self) -> bytes:
        """Сериализовать LUT в 153 байта формата SSD1680."""
        buf = bytearray(LUT_BYTES)

        # bytes 0..59: VS[m][n][X], 2 бита на значение, 4 значения в байте.
        # Порядок в datasheet (Figure 6-6): для каждого m → для каждой phase n
        # → 4 sub-frames A,B,C,D в одном байте: D7-D6 = A, D5-D4 = B, D3-D2 = C, D1-D0 = D.
        idx = 0
        for m in range(N_SUB_LUTS):
            for n in range(N_PHASES):
                a, b, c, d = (self.vs[m, n, X] & 0b11 for X in range(4))
                buf[idx] = (a << 6) | (b << 4) | (c << 2) | d
                idx += 1
        assert idx == 60

        # bytes 60..143: для каждой phase n — 7 байт:
        # TP[nA], TP[nB], SR[nAB], TP[nC], TP[nD], SR[nCD], RP[n]
        for n in range(N_PHASES):
            base = 60 + n * 7
            buf[base + 0] = self.tp[n, 0]
            buf[base + 1] = self.tp[n, 1]
            buf[base + 2] = self.sr[n, 0]
            buf[base + 3] = self.tp[n, 2]
            buf[base + 4] = self.tp[n, 3]
            buf[base + 5] = self.sr[n, 1]
            buf[base + 6] = self.rp[n]
        assert 60 + N_PHASES * 7 == 144

        # bytes 144..149: FR[0..11], 4 бита на значение, 2 на байт.
        # FR[0] в верхней nibble byte 144, FR[1] в нижней; FR[2]/[3] в byte 145 и т.д.
        for n in range(N_PHASES):
            byte_idx = 144 + n // 2
            if n % 2 == 0:
                buf[byte_idx] = (buf[byte_idx] & 0x0F) | ((self.fr[n] & 0x0F) << 4)
            else:
                buf[byte_idx] = (buf[byte_idx] & 0xF0) | (self.fr[n] & 0x0F)

        # bytes 150..152: XON[n,pair], 1 бит на значение, 8 в байте.
        # Порядок (Figure 6-6, byte 150): XON[0AB], XON[0CD], XON[1AB], XON[1CD], ...
        bits = []
        for n in range(N_PHASES):
            bits.append(self.xon[n, 0] & 1)
            bits.append(self.xon[n, 1] & 1)
        assert len(bits) == 24
        for byte_offset in range(3):
            b = 0
            for bit_in_byte in range(8):
                bit_val = bits[byte_offset * 8 + bit_in_byte]
                b |= bit_val << (7 - bit_in_byte)
            buf[150 + byte_offset] = b

        result = bytes(buf)
        logger.debug("Lut.encode: 153 bytes produced (%d non-zero)", sum(1 for x in result if x))
        return result

    # ---- Decoding ---------------------------------------------------------

    @classmethod
    def decode(cls, data: bytes) -> Lut:
        """Восстановить Lut из 153 байт формата SSD1680."""
        if len(data) != LUT_BYTES:
            raise ValueError(f"LUT must be exactly {LUT_BYTES} bytes, got {len(data)}")

        lut = cls()

        # VS (bytes 0..59)
        idx = 0
        for m in range(N_SUB_LUTS):
            for n in range(N_PHASES):
                b = data[idx]
                lut.vs[m, n, 0] = (b >> 6) & 0b11
                lut.vs[m, n, 1] = (b >> 4) & 0b11
                lut.vs[m, n, 2] = (b >> 2) & 0b11
                lut.vs[m, n, 3] = b & 0b11
                idx += 1

        # TP / SR / RP (bytes 60..143)
        for n in range(N_PHASES):
            base = 60 + n * 7
            lut.tp[n, 0] = data[base + 0]
            lut.tp[n, 1] = data[base + 1]
            lut.sr[n, 0] = data[base + 2]
            lut.tp[n, 2] = data[base + 3]
            lut.tp[n, 3] = data[base + 4]
            lut.sr[n, 1] = data[base + 5]
            lut.rp[n]    = data[base + 6]

        # FR (bytes 144..149)
        for n in range(N_PHASES):
            byte_idx = 144 + n // 2
            if n % 2 == 0:
                lut.fr[n] = (data[byte_idx] >> 4) & 0x0F
            else:
                lut.fr[n] = data[byte_idx] & 0x0F

        # XON (bytes 150..152)
        for n in range(N_PHASES):
            bit_index = n * 2  # AB
            byte_idx = 150 + bit_index // 8
            bit_in_byte = 7 - (bit_index % 8)
            lut.xon[n, 0] = (data[byte_idx] >> bit_in_byte) & 1

            bit_index = n * 2 + 1  # CD
            byte_idx = 150 + bit_index // 8
            bit_in_byte = 7 - (bit_index % 8)
            lut.xon[n, 1] = (data[byte_idx] >> bit_in_byte) & 1

        logger.debug("Lut.decode: 153 bytes parsed successfully")
        return lut

    # ---- Validation -------------------------------------------------------

    def charge_balance(
        self,
        lut_index: int = 0,
        voltage_map: dict[int, float] | None = None,
        frame_period_us: float = 1.0,
    ) -> float:
        """Вычислить накопленный заряд для выбранного sub-LUT.

        Σ_n Σ_X V(VS[m,n,X]) · TP[n,X] · (RP[n] + 1) · frame_period.

        Параметры:
            lut_index: индекс sub-LUT (0..4).
            voltage_map: словарь {Source.value: вольты}. По умолчанию —
                номинальные {VCOM: 0, VSH1: +15, VSL: -15, VSH2: +5}.
            frame_period_us: длительность одного frame в микросекундах
                (для модели можно оставить 1.0 — тогда метрика в условных
                единицах «вольт × frame»).

        Возвращает: суммарный заряд в условных единицах «вольт × сек»
        (или «вольт × frame» если frame_period_us=1.0).
        Близость к 0 → DC-balanced waveform.
        """
        if voltage_map is None:
            voltage_map = {
                Source.VCOM.value: 0.0,
                Source.VSH1.value: 15.0,
                Source.VSL.value: -15.0,
                Source.VSH2.value: 5.0,
            }
        if not (0 <= lut_index < N_SUB_LUTS):
            raise ValueError(f"lut_index must be in 0..{N_SUB_LUTS-1}")

        total = 0.0
        for n in range(N_PHASES):
            rp_mult = int(self.rp[n]) + 1
            for X in range(N_SUB_FRAMES):
                v = voltage_map[int(self.vs[lut_index, n, X])]
                t = int(self.tp[n, X]) * frame_period_us * 1e-6
                total += v * t * rp_mult
        logger.debug(
            "charge_balance[lut=%d]: total = %.6e V·s (≈0 means balanced)",
            lut_index, total,
        )
        return total

    def validate(self, charge_tolerance: float = 0.05) -> list[str]:
        """Проверить consistency LUT. Возвращает список ошибок (пустой = OK).

        Параметры:
            charge_tolerance: допустимая по модулю погрешность заряда (В·с).
                По умолчанию 0.05 В·с — соответствует ε-релаксации из § 4.3
                курсовой (обоснование по разрешению INA219). Используйте
                меньшее значение для строгой проверки идеального DC-баланса.
        """
        errors: list[str] = []

        # Диапазоны полей
        if np.any(self.vs >= 4):
            errors.append("vs содержит значения ≥ 4 (выходит за 2 бита)")
        if np.any(self.fr >= 16):
            errors.append("fr содержит значения ≥ 16 (выходит за 4 бита)")
        if np.any(self.xon > 1):
            errors.append("xon содержит значения > 1 (выходит за 1 бит)")

        # Charge balance для каждого активного sub-LUT
        for m in range(N_SUB_LUTS):
            # Считаем sub-LUT «активным», если он содержит хотя бы один не-VCOM source
            if np.any(self.vs[m] != Source.VCOM.value):
                cb = self.charge_balance(m)
                if abs(cb) > charge_tolerance:
                    errors.append(
                        f"sub-LUT {m}: charge imbalance = {cb:.3e} "
                        f"(допуск {charge_tolerance:.1e})"
                    )

        return errors

    # ---- Constructors -----------------------------------------------------

    @classmethod
    def zeros(cls) -> Lut:
        """Полностью нулевая LUT (все фазы — VCOM, TP=0, без активности)."""
        return cls()

    def __repr__(self) -> str:
        active_phases = int(np.sum(np.any(self.tp > 0, axis=1)))
        return (
            f"Lut(active_phases={active_phases}/{N_PHASES}, "
            f"max_tp={int(self.tp.max())}, max_rp={int(self.rp.max())})"
        )
