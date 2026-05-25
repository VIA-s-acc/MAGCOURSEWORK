#!/usr/bin/env python3
"""Smoke-test полного цикла стенда: PING → INA idle → INIT → FRAME → REFRESH → BENCH_RUN.

Финальная верификация M1: подтверждает что ESP32 + SSD1680 + INA219 + Python
работают end-to-end. Запускать после прошивки и подключения панели.

Использование:
    python scripts/smoke_test.py [--port /dev/cu.SLAB_USBtoUART]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from python.bridge import open_bridge
from python.lut import Lut, N_PHASES, N_SUB_FRAMES, Source


def make_charge_balanced_lut() -> bytes:
    """Простейшая charge-balanced waveform для smoke-теста:

    Phase 0: все 4 sub-frames на VSH1 (поднимаем частицы к + полюсу), TP=20
    Phase 1: все 4 sub-frames на VSL  (тянем к -),                     TP=20
    Phase 2: все 4 sub-frames на VSH1,                                  TP=20
    Phase 3: все 4 sub-frames на VSL,                                   TP=20
    Остальные фазы — пустые.

    Заполняем LUT0..LUT4 одинаково (мы не знаем какой sub-LUT активен в
    DISPLAY Mode 1 по умолчанию). Это гарантирует, что независимо от
    выбора sub-LUT через регистр 0x37, выполнится наша waveform.

    Charge balance: (+VSH1 × 20 + -VSL × 20) × 2 повтора × 4 sub-frame = 0
    (при V(VSH1) = +15 В, V(VSL) = -15 В номинально).
    """
    lut = Lut.zeros()
    for m in range(5):  # все sub-LUT
        for sub in range(N_SUB_FRAMES):
            lut.vs[m, 0, sub] = Source.VSH1.value
            lut.vs[m, 1, sub] = Source.VSL.value
            lut.vs[m, 2, sub] = Source.VSH1.value
            lut.vs[m, 3, sub] = Source.VSL.value
    for phase in range(4):
        lut.tp[phase, :] = 20

    # Проверка балансировки (на случай если параметры изменили):
    errors = lut.validate(charge_tolerance=1e-9)
    if errors:
        print("⚠ warnings от Lut.validate():")
        for e in errors:
            print(f"   - {e}")
    return lut.encode()


def print_ina(label: str, readout: dict) -> None:
    print(
        f"  {label:30s}  U={readout['bus_v']:.3f} V  "
        f"I={readout['current_a']*1000:+.3f} mA  "
        f"P={readout['power_w']*1000:+.3f} mW"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test EPD стенда")
    parser.add_argument("--port", default="/dev/cu.SLAB_USBtoUART",
                        help="Путь к ESP32 (по умолчанию /dev/cu.SLAB_USBtoUART)")
    parser.add_argument("--n-repeats", type=int, default=1,
                        help="Повторов в BENCH_RUN (1..255)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="DEBUG-уровень логирования")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print(f"\n=== SMOKE TEST: {args.port} ===\n")

    with open_bridge(args.port) as br:
        # 1. Idle baseline
        print("[1/5] Idle baseline (панель в исходном состоянии):")
        print_ina("idle", br.ina_read())

        # 2. INIT — поднимает контроллер из reset
        print("\n[2/5] INIT (полная инициализация для full update):")
        t0 = time.monotonic()
        br.init()
        dt = (time.monotonic() - t0) * 1000
        print(f"  init() done in {dt:.0f} ms")
        print_ina("after init", br.ina_read())

        # 3. FRAME — заливаем буфер белым (0xFF = white pixel в SSD1680 RAM 0x24)
        print("\n[3/5] FRAME (4000 байт = весь экран в white):")
        t0 = time.monotonic()
        br.send_frame(b"\xFF" * 4000)
        dt = (time.monotonic() - t0) * 1000
        print(f"  send_frame() done in {dt:.0f} ms")

        # 4. Обычный REFRESH (заводская LUT по температуре) — baseline B0
        print("\n[4/5] REFRESH (заводская LUT, 0x22=0xF7) — baseline B0:")
        before = br.ina_read()
        print_ina("before refresh", before)
        t0 = time.monotonic()
        br.refresh()
        dt = (time.monotonic() - t0) * 1000
        after = br.ina_read()
        print_ina("after refresh", after)
        print(f"  refresh() blocked for {dt:.0f} ms")
        # Грубая оценка энергии: средний ток × bus × время
        avg_i = (before['current_a'] + after['current_a']) / 2
        approx_e_mj = abs(avg_i) * before['bus_v'] * (dt / 1000) * 1000
        print(f"  rough energy estimate ≈ {approx_e_mj:.2f} mJ "
              f"(2-точки усреднения, неточно)")

        # 5. BENCH_RUN с custom charge-balanced LUT — настоящий замер с trace
        print("\n[5/5] BENCH_RUN (custom charge-balanced LUT, INA-трасса):")
        custom_lut = make_charge_balanced_lut()
        # Заливаем чёрным (0x00 = black pixel) чтобы заставить waveform поработать
        # на B↔W переходе с предыдущего обновления (которое сделало белый экран).
        black_frame = b"\x00" * 4000
        print(f"  отправляю LUT (153 B) + frame (4000 B) + N={args.n_repeats}...")
        t0 = time.monotonic()
        trace = br.bench_run(custom_lut, black_frame, n_repeats=args.n_repeats)
        dt = (time.monotonic() - t0) * 1000
        print(f"  bench_run() total = {dt:.0f} ms (включая передачу 4154 B по 921600)")
        print(f"  trace: {trace}")
        if len(trace) > 0:
            print(f"     samples = {len(trace)}")
            print(f"     duration = {trace.duration_ms:.1f} ms")
            print(f"     peak I = {trace.peak_current_ma():+.2f} mA")
            print(f"     avg I = {trace.avg_current_ma():+.2f} mA")
            print(f"     energy = {trace.energy_mj():.3f} mJ")
        else:
            print("  ⚠ no samples (refresh завершился быстрее одного цикла INA?)")

        # Финал — sleep панели, чтобы не жгла ток
        print("\n[*] SLEEP (deep sleep):")
        br.sleep()
        time.sleep(0.1)
        print_ina("after sleep", br.ina_read())

    print("\n=== SMOKE TEST DONE ===\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
