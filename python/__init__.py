"""Python-пакет для магистерской курсовой ВМК МГУ.

Модули:
- ``bridge``  — клиент для ESP32-моста (опкоды 0x01-0x0E через pyserial).
- ``lut``     — encode/decode 153-байтовой LUT SSD1680 (Section 6.7 datasheet).
- ``ina219``  — парсер трасс из BENCH_RUN и интегрирование энергии.
- ``metrics`` — метрики качества (SSIM, residual reflectance, ghost score).
"""

__version__ = "0.1.0"
