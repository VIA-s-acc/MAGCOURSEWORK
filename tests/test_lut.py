"""Тесты для python/lut.py — encode/decode round-trip, charge_balance, validate."""

import numpy as np
import pytest

from python.lut import LUT_BYTES, N_PHASES, N_SUB_FRAMES, N_SUB_LUTS, Lut, Source


def test_zeros_encodes_to_153_bytes():
    """Пустая LUT кодируется в 153 нулевых байта."""
    data = Lut.zeros().encode()
    assert len(data) == LUT_BYTES
    assert data == bytes(LUT_BYTES)


def test_decode_zeros_returns_zero_lut():
    """Decode 153 нулевых байт возвращает пустую LUT без активных фаз."""
    lut = Lut.decode(bytes(LUT_BYTES))
    assert np.all(lut.vs == 0)
    assert np.all(lut.tp == 0)
    assert np.all(lut.sr == 0)
    assert np.all(lut.rp == 0)
    assert np.all(lut.fr == 0)
    assert np.all(lut.xon == 0)


def test_decode_bad_length_raises():
    with pytest.raises(ValueError, match="153 bytes"):
        Lut.decode(bytes(152))
    with pytest.raises(ValueError, match="153 bytes"):
        Lut.decode(bytes(154))


def test_encode_decode_roundtrip_random():
    """Случайная LUT после encode→decode возвращает себя побитово."""
    rng = np.random.default_rng(42)
    orig = Lut.zeros()
    orig.vs  = rng.integers(0, 4,  size=orig.vs.shape, dtype=np.uint8)
    orig.tp  = rng.integers(0, 256, size=orig.tp.shape, dtype=np.uint8)
    orig.sr  = rng.integers(0, 256, size=orig.sr.shape, dtype=np.uint8)
    orig.rp  = rng.integers(0, 256, size=orig.rp.shape, dtype=np.uint8)
    orig.fr  = rng.integers(0, 16, size=orig.fr.shape, dtype=np.uint8)
    orig.xon = rng.integers(0, 2,  size=orig.xon.shape, dtype=np.uint8)

    encoded = orig.encode()
    assert len(encoded) == LUT_BYTES

    decoded = Lut.decode(encoded)
    np.testing.assert_array_equal(decoded.vs,  orig.vs,  err_msg="vs mismatch")
    np.testing.assert_array_equal(decoded.tp,  orig.tp,  err_msg="tp mismatch")
    np.testing.assert_array_equal(decoded.sr,  orig.sr,  err_msg="sr mismatch")
    np.testing.assert_array_equal(decoded.rp,  orig.rp,  err_msg="rp mismatch")
    np.testing.assert_array_equal(decoded.fr,  orig.fr,  err_msg="fr mismatch")
    np.testing.assert_array_equal(decoded.xon, orig.xon, err_msg="xon mismatch")


def test_charge_balance_zero_for_pure_vcom():
    """Если все VS=VCOM, заряд = 0 независимо от TP."""
    lut = Lut.zeros()
    # vs остаётся VCOM, tp заполняем случайно
    rng = np.random.default_rng(0)
    lut.tp = rng.integers(1, 100, size=lut.tp.shape, dtype=np.uint8)
    assert lut.charge_balance(lut_index=0) == 0.0


def test_charge_balance_symmetric_balanced():
    """Симметричный waveform VSH1 + VSL равных длительностей → charge balance = 0."""
    lut = Lut.zeros()
    # phase 0: VSH1 на всех 4 sub-frames, TP=10
    lut.vs[0, 0, :] = Source.VSH1.value
    lut.tp[0, :]    = 10
    # phase 1: VSL на всех 4 sub-frames, TP=10
    lut.vs[0, 1, :] = Source.VSL.value
    lut.tp[1, :]    = 10

    # +15·10·4 + (-15)·10·4 = 0 (при V_VSH1=+15, V_VSL=-15)
    assert lut.charge_balance(lut_index=0) == pytest.approx(0.0, abs=1e-12)


def test_charge_balance_imbalanced_detected():
    """Asymmetric waveform → ненулевой charge."""
    lut = Lut.zeros()
    lut.vs[0, 0, :] = Source.VSH1.value
    lut.tp[0, :]    = 20  # 2× больше времени на + полюс
    lut.vs[0, 1, :] = Source.VSL.value
    lut.tp[1, :]    = 10

    cb = lut.charge_balance(lut_index=0)
    assert cb > 0  # net positive charge


def test_validate_balanced_passes():
    lut = Lut.zeros()
    lut.vs[0, 0, :] = Source.VSH1.value
    lut.tp[0, :]    = 10
    lut.vs[0, 1, :] = Source.VSL.value
    lut.tp[1, :]    = 10
    errors = lut.validate(charge_tolerance=1e-9)
    assert errors == []


def test_validate_imbalanced_flagged():
    lut = Lut.zeros()
    lut.vs[0, 0, :] = Source.VSH1.value
    lut.tp[0, :]    = 20
    lut.vs[0, 1, :] = Source.VSL.value
    lut.tp[1, :]    = 10
    errors = lut.validate(charge_tolerance=1e-9)
    assert any("charge imbalance" in e for e in errors)


def test_from_waveform_maps_voltages_and_durations():
    """from_waveform кодирует фазы bang-bang в sub-frame A всех sub-LUT."""
    # V=(5,-15,5,-15), T=(16,3,2,3) — оптимум M5 (зарядо-сбалансирован).
    lut = Lut.from_waveform((5.0, -15.0, 5.0, -15.0), (16, 3, 2, 3))
    # фаза 0: +5 → VSH2, фаза 1: -15 → VSL и т.д., во всех 5 sub-LUT
    for m in range(N_SUB_LUTS):
        assert lut.vs[m, 0, 0] == Source.VSH2
        assert lut.vs[m, 1, 0] == Source.VSL
        assert lut.vs[m, 2, 0] == Source.VSH2
        assert lut.vs[m, 3, 0] == Source.VSL
    assert list(lut.tp[:4, 0]) == [16, 3, 2, 3]
    # sub-frames B/C/D пустые (TP=0)
    assert np.all(lut.tp[:, 1:] == 0)
    # round-trip через encode/decode сохраняет
    assert Lut.decode(lut.encode()).vs[0, 1, 0] == Source.VSL


def test_from_waveform_charge_balanced_optimum():
    """Оптимум M5 проходит ε-проверку заряда (Σ V·T = 0)."""
    lut = Lut.from_waveform((5.0, -15.0, 5.0, -15.0), (16, 3, 2, 3))
    assert abs(lut.charge_balance()) < 1e-9
    assert lut.validate(charge_tolerance=0.05) == []


def test_from_waveform_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="!="):
        Lut.from_waveform((5.0, -15.0), (16,))


def test_source_enum_2bit_values():
    """Source values укладываются в 2 бита (для VS поля LUT)."""
    for src in Source:
        assert 0 <= src.value < 4


def test_lut_repr_smoke():
    lut = Lut.zeros()
    lut.tp[3, 0] = 50
    rep = repr(lut)
    assert "Lut(" in rep
    assert "active_phases=1" in rep


def test_format_field_sizes():
    """Проверка инвариантов размеров полей (соответствие datasheet Section 6.7)."""
    assert N_SUB_LUTS == 5
    assert N_PHASES == 12
    assert N_SUB_FRAMES == 4
    # Сумма байт: 60 (VS) + 84 (TP/SR/RP) + 6 (FR) + 3 (XON) = 153
    assert 60 + N_PHASES * 7 + 6 + 3 == LUT_BYTES
