# firmware/ — прошивка ESP32 для стенда

Минимальная Arduino-прошивка для ESP32 DevKit V1, выступающего USB-мостом
между хост-компьютером и панелью Waveshare 2.13" V4 на контроллере SSD1680.
Замер тока/напряжения — через INA219.

## Аппаратная схема

Три группы соединений (по исходному брифу проекта):

```
                    ┌─────────── ESP32 DevKit V1 ───────────┐
                    │                                        │
   ESP32            │                          Waveshare HAT  │  INA219
   ─────────────────┤                                        │
                    │                                        │
   Группа 1 — ESP32 → HAT (управление дисплеем, 7 проводов): │
     GND     ───────┤ GND                ──→  GND            │
     GPIO23  ───────┤ ─→ DIN (MOSI)      ──→  DIN            │
     GPIO18  ───────┤ ─→ CLK (SCK)       ──→  CLK            │
     GPIO5   ───────┤ ─→ CS              ──→  CS             │
     GPIO17  ───────┤ ─→ DC              ──→  DC             │
     GPIO16  ───────┤ ─→ RST             ──→  RST            │
     GPIO4   ───────┤ ─→ BUSY            ←──  BUSY           │
                    │                                        │
   Группа 2 — ESP32 → INA219 (питание датчика и I²C, 4 провода): │
     3V3     ───────┤ ─→ VCC                              ─→  VCC
     GND     ───────┤ ─→ GND                              ─→  GND
     GPIO21  ───────┤ ─→ SDA                              ─→  SDA
     GPIO22  ───────┤ ─→ SCL                              ─→  SCL
                    │                                        │
   Группа 3 — шунт-линия (2 провода — питание панели через шунт): │
     3V3 ──────────→ INA219 Vin+ ───[шунт 0.1 Ом]──→ Vin- ──→ HAT VCC
                    │                                        │
                    │  ⚠ Только 3.3В, никогда 5В!            │
                    │  ⚠ HAT VCC подключается ТОЛЬКО к Vin-, │
                    │    не напрямую к 3V3.                  │
                    └────────────────────────────────────────┘
```

USB-Serial: **921600 бод** (fallback 115200). Драйвер: **CP2102** (на macOS уже
встроен; порт `/dev/cu.SLAB_USBtoUART`).

## Установка и прошивка

### Через Arduino IDE

1. **File → Preferences → Additional Boards Manager URLs:**
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. **Tools → Board → Boards Manager:** установить **esp32** by Espressif Systems.
3. **Board:** ESP32 Dev Module.
4. **Flash Size:** 4MB; **Partition Scheme:** Default 4MB; **Upload Speed:** 921600;
   **Port:** `/dev/cu.SLAB_USBtoUART`.
5. Открыть `firmware/epd_bridge.ino`, нажать **Upload**.

### Через arduino-cli

```bash
arduino-cli core install esp32:esp32
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/
arduino-cli upload --port /dev/cu.SLAB_USBtoUART --fqbn esp32:esp32:esp32 firmware/
```

### Через PlatformIO (рекомендуется для автоматизации)

`platformio.ini`:
```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
upload_port = /dev/cu.SLAB_USBtoUART
upload_speed = 921600
monitor_speed = 921600
build_flags = -DARDUINO_USB_MODE=1
```

## Протокол: бинарные опкоды через USB-Serial

Каждый запрос начинается с 1 байта опкода. Параметры запроса и ответа —
бинарные, big-endian (sane default для сетевых протоколов).

Каждый опкод возвращает **первыми двумя байтами status code**:
- `0x0000` — OK
- `0xFF01` — `BAD_OPCODE` (неизвестный опкод или несоответствие данных)
- `0xFF02` — `TIMEOUT_RX` (не получены ожидаемые байты данных за 2 секунды)
- `0xFF03` — `TIMEOUT_BUSY` (BUSY от EPD не упал за 10 секунд)
- `0xFF04` — `INA_NACK` (INA219 не ответил по I²C)

### Базовые опкоды (M1.B1)

| Код | Имя | Запрос | Ответ |
|---|---|---|---|
| `0x01` | `INIT` | — | status (2) |
| `0x02` | `FRAME` | 4000 байт frame buffer | status (2) |
| `0x03` | `REFRESH` | — | status (2). Использует `0x22=0xF7` (заводская LUT по T). |
| `0x04` | `SLEEP` | — | status (2). Deep sleep. |
| `0x05` | `LUT` | 153 байта LUT в регистр 0x32 | status (2) |
| `0x06` | `PING` | — | status (2) + версия FW (2): big-endian `0x0101` для v1.01 |
| `0x07` | `INA_READ` | — | status (2) + raw регистры INA219 (8 байт): shunt(2) bus(2) current(2) power(2), big-endian |
| `0x08` | `REFRESH_PARTIAL` | — | status (2). `0x22=0xCF`. |
| `0x09` | `INIT_PARTIAL` | — | status (2). Init без temperature override. |
| `0x0A` | `INIT_PARTIAL_FAST` | — | status (2). Waveshare-овский «fast» init с подменой T через `0x1A`. |
| `0x0B` | `REFRESH_CUSTOM_LUT` | — | status (2). **`0x22=0xC7`** — НЕ перезагружает LUT из OTP по температуре. См. «Ключевой фикс» ниже. |

### Расширенные опкоды (M1.B2)

| Код | Имя | Запрос | Ответ |
|---|---|---|---|
| `0x0C` | `WRITE_LUT_DYNAMIC` | 153 байта LUT | status (2). Записывает LUT в 0x32 + сразу выполняет refresh с `0xC7`. Атомарно для тестового сценария «применить и измерить». |
| `0x0D` | `WRITE_REGISTER` | addr (1) + len (1) + data (len, ≤16) | status (2). Произвольная запись в регистр SSD1680. Полезно для калибровки `0x1A` (T override), `0x2C` (VCOM), `0x03` (VGH), `0x04` (VSH1/VSH2/VSL). |
| `0x0E` | `BENCH_RUN` | LUT (153) + image (4000) + N (1) | status (2) + n_samples (2) + trace (n_samples × 8: t_us (u32) + i_raw (i16) + p_raw (u16)). Выполняет N циклов «write_frame + refresh с custom LUT» с непрерывным семплированием INA219 во время BUSY. |

## ⚠ КЛЮЧЕВОЙ ФИКС: семантика регистра 0x22

Из datasheet SSD1680 Rev 0.14, Command Table (стр. 25), регистр `0x22`
(`Display Update Control 2`) задаёт последовательность операций при
активации Master Activation (`0x20`). Параметр — 1 байт `A[7:0]`. POR = `0xFF`.

| Hex | Действие |
|---|---|
| `0xC7` | Enable Analog + **DISPLAY Mode 1** + Disable Analog + Disable OSC. **НЕ перезагружает LUT.** |
| `0xCF` | то же, Mode 2 (partial). |
| `0xF7` | **Load temperature value** + DISPLAY Mode 1 + ... — **запускает Waveform Setting Searching Mechanism** (Section 6.9), который перезаписывает пользовательский LUT заводским WS из OTP по сенсированной температуре. |
| `0xFF` | то же, Mode 2 + Load T. |

**Практически:** если хочешь использовать свою LUT через регистр 0x32 — после
записи LUT шли `0x22=0xC7` (опкод `0x0B` `REFRESH_CUSTOM_LUT` или `0x0C`
`WRITE_LUT_DYNAMIC`). Если шлёшь `0xF7`/`0xFF` — контроллер перезапишет твою
LUT заводской, и все «оптимизированные» waveforms превратятся в заводские
~600 мс.

См. также reference-код Waveshare для сравнения:
[`epd2in13_V4.py`](../docs/refs/waveshare_code/epd2in13_V4.py) — функция
`TurnOnDisplay()` (`0xF7`) vs `TurnOnDisplay_Fast()` (`0xC7`).

## Замер энергии через INA219

Конфигурация (выполняется автоматически в `ina219_init()`):

```
CONFIG (0x00) = 0x199F:
  BRNG  = 0      (16V диапазон)
  PG    = 01     (±80 mV gain, max ток через 0.1 Ом = 800 mA)
  BADC  = 1100   (12-bit, 8-sample averaging → ~300 Гц sample rate)
  SADC  = 1100   (то же для shunt)
  MODE  = 111    (continuous shunt + bus)

CALIBRATION (0x05) = 4096
  → Current_LSB = 100 мкА
  → Power_LSB   = 2 мВт
```

При типичном токе панели 30..50 мА (~3-5 мВт) разрешение по току 100 мкА
даёт ~3-5% относительной точности на пике, что достаточно для целевых
измерений энергии за обновление.

**Опкод `0x0E` `BENCH_RUN`** автоматически выполняет цикл refresh с
семплированием — это основной режим для главы 7 «Экспериментальная валидация».
Хост-side парсер трассы — `python/ina219.py` (создаётся в задаче C3 плана M1).

## Структура кода

- `epd_bridge.ino` (~600 строк) — single-file Arduino sketch:
  - GPIO/SPI/I²C setup
  - SSD1680 driver (init, frame write, refresh full/partial/custom)
  - INA219 driver (init, read_all)
  - Serial transport (read_bytes с timeout)
  - Opcode dispatcher (0x01..0x0E)
  - BENCH_RUN с RAM-буфером 5000 samples × 8 байт = 40 KB.

Зависимости — только встроенные Arduino-ESP32 библиотеки (`SPI`, `Wire`).

## Известные ограничения

- **Логи через `Serial2`/`DBG`** — отключены по умолчанию (`#define EPD_BRIDGE_DEBUG`
  закомментирован), потому что Serial2 на ESP32 DevKit V1 использует пины GPIO16/17,
  которые у нас заняты под RST/DC дисплея. При включении логов нужно либо
  перенаправить Serial2 на другие GPIO (см. `Serial2.begin(115200, SERIAL_8N1, RX, TX)`),
  либо использовать сам `Serial` (но это сломает бинарный протокол!).
- **INA219 sample rate ~300 Гц** при 8-sample averaging. Если нужно быстрее
  для тонких импульсов в фазах waveform — переключить config в 0x0193
  (single sample 12-bit, ~1.9 кГц), но возрастёт шум.
- **BENCH_RUN buffer 5000 samples** — хватает на ~16 секунд непрерывного измерения.
  Для длинных серий — split на несколько `BENCH_RUN` с N=1 каждый.
