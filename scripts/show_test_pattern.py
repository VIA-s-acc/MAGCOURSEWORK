#!/usr/bin/env python3
"""Показать тестовый паттерн на EPD для фотографирования стенда.

Использование:
    python scripts/show_test_pattern.py --pattern bb         # всё чёрное
    python scripts/show_test_pattern.py --pattern ww         # всё белое
    python scripts/show_test_pattern.py --pattern checker    # шахматка
    python scripts/show_test_pattern.py --pattern transition # BB → WW (с паузой)

Скрипт делает full-refresh заводским LUT (0x22=0xF7), что занимает ~600 мс.
После refresh ждёт enter — за это время ты делаешь фото.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from python.bridge import open_bridge

# Waveshare 2.13" V4: 250×122 пикселя, упаковано по 8 бит/байт по горизонтали
# Размер frame buffer = 250 * 16 = 4000 байт (16 = ceil(122/8) * 1)
# Фактически: 250 столбцов × 16 байт = 4000 байт. Каждый бит = пиксель.
FRAME_BYTES = 4000


def make_pattern_ww() -> bytes:
    """Всё белое (0xFF — пиксели выключены = белый на EPD)."""
    return bytes([0xFF] * FRAME_BYTES)


def make_pattern_bb() -> bytes:
    """Всё чёрное (0x00 — пиксели включены = чёрный)."""
    return bytes([0x00] * FRAME_BYTES)


def make_pattern_checker() -> bytes:
    """Чёрно-белая шахматка (полосы по байту = ~8 пикселей)."""
    return bytes([0xAA if i % 2 == 0 else 0x55 for i in range(FRAME_BYTES)])


PATTERNS = {
    "bb": make_pattern_bb,
    "ww": make_pattern_ww,
    "checker": make_pattern_checker,
}


def show(bridge, pattern_name: str) -> None:
    """Один цикл: INIT → FRAME → REFRESH → ждать enter."""
    print(f"\n→ Загружаю паттерн '{pattern_name}'...")
    bridge.init()
    time.sleep(0.05)
    bridge.send_frame(PATTERNS[pattern_name]())
    time.sleep(0.05)
    print("  refresh (~600 мс)...")
    t0 = time.perf_counter()
    bridge.refresh()
    elapsed = time.perf_counter() - t0
    print(f"  готово за {elapsed*1000:.0f} мс\n")
    print("СФОТКАЙ панель сейчас. Когда готов — нажми Enter.")
    input()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default=None, help="serial-порт ESP32 (auto-detect если не задан)")
    ap.add_argument("--pattern", choices=["bb", "ww", "checker", "transition"], default="ww",
                    help="что показать")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    open_kwargs = {"port": args.port} if args.port else {}
    with open_bridge(**open_kwargs) as bridge:
        if args.pattern == "transition":
            # Полный цикл: BB → пауза → WW (для съёмки переходного процесса)
            show(bridge, "bb")
            show(bridge, "ww")
            show(bridge, "checker")
            print("✓ Цикл BB → WW → checker завершён.")
        else:
            show(bridge, args.pattern)
            print(f"✓ Паттерн '{args.pattern}' показан.")
        bridge.sleep()
    print("Sleep panel — отключаюсь.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
