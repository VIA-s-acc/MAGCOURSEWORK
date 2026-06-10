// ============================================================================
//  epd_bridge.ino  —  ESP32 USB-Serial ↔ SPI мост для Waveshare 2.13" V4
//                     (контроллер SSD1680, 250×122 видимая / 250×128 буфер).
//
//  Транспорт: USB-Serial @ 921600 бод (fallback 115200), бинарный протокол.
//  SPI:       10 МГц, MODE0, MSB first.
//  I²C:       400 кГц для INA219 (адрес 0x40, шунт 0.1 Ом).
//
//  Каждый опкод возвращает 2-байтный статус: 0x0000 = OK, иначе код ошибки
//  (см. таблицу в firmware/README.md и константы STATUS_* ниже).
//
//  Опкоды:
//    0x01 INIT                      — init для full update
//    0x02 FRAME                     — записать 4000-байт frame buffer в RAM 0x24
//    0x03 REFRESH                   — full refresh (0x22=0xF7 — заводская)
//    0x04 SLEEP                     — deep sleep
//    0x05 LUT                       — записать 153-байт LUT в регистр 0x32
//    0x06 PING                      — ответ {0x00, 0x00} + FW_VERSION
//    0x07 INA_READ                  — вернуть U(шунт), U(шина), I, P
//    0x08 REFRESH_PARTIAL           — partial refresh (0x22=0xCF)
//    0x09 INIT_PARTIAL              — init для partial update
//    0x0A INIT_PARTIAL_FAST         — fast init (подмена температуры через 0x1A)
//    0x0B REFRESH_CUSTOM_LUT        — refresh с уже записанной LUT через 0xC7
//                                    (КЛЮЧЕВОЙ ФИКС: НЕ перезагружает LUT из OTP)
//
//  (Опкоды 0x0C-0x0F: WRITE_LUT_DYNAMIC, WRITE_REGISTER, BENCH_RUN,
//   BENCH_FACTORY — см. ниже.)
//    0x0F BENCH_FACTORY             — INA-трасса заводского refresh (B0/B1):
//                                    [image 4000][0x22-byte] → trace
//
//  Сборка: Arduino IDE → Board: ESP32 Dev Module, Flash 80MHz, partition default
//  Прошивка: usbserial, port = /dev/cu.SLAB_USBtoUART (macOS, драйвер CP2102)
// ============================================================================

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>

// ---- GPIO mapping (по схеме подключения в брифе) --------------------------
constexpr uint8_t PIN_RST    = 16;   // EPD reset
constexpr uint8_t PIN_DC     = 17;   // EPD data/command
constexpr uint8_t PIN_CS     = 5;    // EPD chip select
constexpr uint8_t PIN_BUSY   = 4;    // EPD busy (0=idle, 1=busy)
constexpr uint8_t PIN_MOSI   = 23;   // SPI MOSI → DIN
constexpr uint8_t PIN_CLK    = 18;   // SPI SCK  → CLK
constexpr uint8_t PIN_SDA    = 21;   // I²C SDA (INA219)
constexpr uint8_t PIN_SCL    = 22;   // I²C SCL (INA219)

// ---- EPD геометрия --------------------------------------------------------
constexpr uint16_t EPD_WIDTH      = 122;     // видимая ширина (px)
constexpr uint16_t EPD_HEIGHT     = 250;     // видимая высота (px)
constexpr uint16_t EPD_BUF_WIDTH  = 128;     // буфер выровнен на 8 (128 = 16 байт)
constexpr uint16_t EPD_FRAME_SIZE = (EPD_BUF_WIDTH / 8) * EPD_HEIGHT;  // = 4000 байт
constexpr uint16_t EPD_LUT_SIZE   = 153;     // регистр 0x32 SSD1680

// ---- INA219 (CJMCU-219, шунт 0.1 Ом) --------------------------------------
constexpr uint8_t  INA219_ADDR        = 0x40;
constexpr uint8_t  INA219_REG_CONFIG  = 0x00;
constexpr uint8_t  INA219_REG_SHUNT   = 0x01;
constexpr uint8_t  INA219_REG_BUS     = 0x02;
constexpr uint8_t  INA219_REG_POWER   = 0x03;
constexpr uint8_t  INA219_REG_CURRENT = 0x04;
constexpr uint8_t  INA219_REG_CALIB   = 0x05;
constexpr float    INA219_SHUNT_OHMS  = 0.1f;
// Калибровка для шунта 0.1 Ом, max ток ~3.2А (с запасом):
//   Current_LSB = max_I / 2^15 ≈ 100 мкА
//   Cal = trunc(0.04096 / (Current_LSB · R_shunt)) = trunc(0.04096 / (1e-4 · 0.1)) = 4096
constexpr uint16_t INA219_CAL_VALUE   = 4096;
constexpr float    INA219_I_LSB_A     = 0.0001f;   // 100 мкА
constexpr float    INA219_P_LSB_W     = INA219_I_LSB_A * 20.0f;  // 2 мВт (POWER_LSB = 20×Current_LSB)

// Возвращает: U_shunt[мВ], U_bus[В], I[мА], P[мВт] — упаковано в 8-байт ответ.
// ВАЖНО: объявляется ЗДЕСЬ (до любой функции), потому что Arduino IDE
// автогенерирует прототипы в начале файла и иначе не находит тип InaReadout.
struct InaReadout {
    int16_t  shunt_raw;     // LSB = 10 мкВ (signed)
    uint16_t bus_raw;       // bits [15..3] = V_bus / 4 мВ (LSB 4mV)
    int16_t  current_raw;   // LSB = INA219_I_LSB_A (signed)
    uint16_t power_raw;     // LSB = INA219_P_LSB_W
};

// ---- Опкоды протокола -----------------------------------------------------
constexpr uint8_t OP_INIT                = 0x01;
constexpr uint8_t OP_FRAME               = 0x02;
constexpr uint8_t OP_REFRESH             = 0x03;
constexpr uint8_t OP_SLEEP               = 0x04;
constexpr uint8_t OP_LUT                 = 0x05;
constexpr uint8_t OP_PING                = 0x06;
constexpr uint8_t OP_INA_READ            = 0x07;
constexpr uint8_t OP_REFRESH_PARTIAL     = 0x08;
constexpr uint8_t OP_INIT_PARTIAL        = 0x09;
constexpr uint8_t OP_INIT_PARTIAL_FAST   = 0x0A;
constexpr uint8_t OP_REFRESH_CUSTOM_LUT  = 0x0B;
// --- B2: расширенные опкоды для калибровки и benchmark ---
constexpr uint8_t OP_WRITE_LUT_DYNAMIC   = 0x0C;   // принять LUT + сразу refresh с 0xC7
constexpr uint8_t OP_WRITE_REGISTER      = 0x0D;   // произвольная запись регистра SSD1680
constexpr uint8_t OP_BENCH_RUN           = 0x0E;   // benchmark: LUT + image + N повторов + INA-трасса
constexpr uint8_t OP_BENCH_FACTORY       = 0x0F;   // benchmark заводского refresh (B0/B1): image + 0x22-byte + INA-трасса
constexpr uint8_t OP_PART_BASE           = 0x10;   // partial: записать базовый кадр в RAM 0x24+0x26 + full refresh
constexpr uint8_t OP_BENCH_PARTIAL       = 0x11;   // partial: LUT+cfg+image, безмерцательный refresh + INA-трасса
constexpr uint8_t OP_WRITE_OLD           = 0x12;   // partial: записать «предыдущий» кадр в RAM 0x26 (без refresh)

// ---- Статусы --------------------------------------------------------------
constexpr uint16_t STATUS_OK             = 0x0000;
constexpr uint16_t STATUS_BAD_OPCODE     = 0xFF01;
constexpr uint16_t STATUS_TIMEOUT_RX     = 0xFF02;
constexpr uint16_t STATUS_TIMEOUT_BUSY   = 0xFF03;
constexpr uint16_t STATUS_INA_NACK       = 0xFF04;

// ---- Тайминги -------------------------------------------------------------
constexpr uint32_t SERIAL_BAUD           = 921600UL;
constexpr uint32_t SPI_FREQ              = 10000000UL;   // 10 МГц
constexpr uint32_t BUSY_TIMEOUT_MS       = 10000UL;      // 10 c — full refresh может быть долгим
constexpr uint32_t RX_TIMEOUT_MS         = 5000UL;       // 5 с — с запасом для 4154 байт BENCH_RUN payload
constexpr uint32_t I2C_FREQ              = 400000UL;     // 400 кГц fast mode
constexpr size_t   SERIAL_RX_BUFFER      = 8192;         // 8 KB — вмещает BENCH_RUN payload (4154 B) с запасом

// ---- Версия прошивки ------------------------------------------------------
constexpr uint16_t FW_VERSION            = 0x0105;       // major=1, minor=05 (+ WRITE_OLD для секв. partial)

// ---- Verbose logging (DEBUG) ----------------------------------------------
// Включать DEBUG только при отладке — Serial.print замусоривает binary-протокол!
// Лучше использовать вторичный UART (Serial2) для логов.
// #define EPD_BRIDGE_DEBUG 1

#ifdef EPD_BRIDGE_DEBUG
#define DBG(...) do { Serial2.printf(__VA_ARGS__); } while(0)
#else
#define DBG(...) do { } while(0)
#endif

// ===========================================================================
//                            SPI helpers
// ===========================================================================

static SPISettings spi_settings(SPI_FREQ, MSBFIRST, SPI_MODE0);

inline void epd_cs_low()  { digitalWrite(PIN_CS, LOW); }
inline void epd_cs_high() { digitalWrite(PIN_CS, HIGH); }
inline void epd_dc_low()  { digitalWrite(PIN_DC, LOW); }    // command
inline void epd_dc_high() { digitalWrite(PIN_DC, HIGH); }   // data

void epd_send_command(uint8_t cmd) {
    SPI.beginTransaction(spi_settings);
    epd_dc_low();
    epd_cs_low();
    SPI.transfer(cmd);
    epd_cs_high();
    SPI.endTransaction();
}

void epd_send_data(uint8_t data) {
    SPI.beginTransaction(spi_settings);
    epd_dc_high();
    epd_cs_low();
    SPI.transfer(data);
    epd_cs_high();
    SPI.endTransaction();
}

void epd_send_data_buffer(const uint8_t* buf, size_t len) {
    SPI.beginTransaction(spi_settings);
    epd_dc_high();
    epd_cs_low();
    SPI.writeBytes(buf, len);
    epd_cs_high();
    SPI.endTransaction();
}

bool epd_wait_busy(uint32_t timeout_ms = BUSY_TIMEOUT_MS) {
    uint32_t t0 = millis();
    while (digitalRead(PIN_BUSY) == HIGH) {
        if (millis() - t0 > timeout_ms) {
            DBG("BUSY timeout after %u ms\n", (unsigned)(millis() - t0));
            return false;
        }
        delay(1);
    }
    return true;
}

void epd_reset() {
    digitalWrite(PIN_RST, HIGH);
    delay(20);
    digitalWrite(PIN_RST, LOW);
    delay(2);
    digitalWrite(PIN_RST, HIGH);
    delay(20);
    epd_wait_busy();
}

// ===========================================================================
//                            EPD init / refresh
// ===========================================================================

// Базовая инициализация для full update (по reference epd2in13_V4.py).
bool epd_init() {
    DBG("epd_init\n");
    epd_reset();
    epd_send_command(0x12);                                  // SWRESET
    if (!epd_wait_busy()) return false;

    epd_send_command(0x01);                                  // Driver output control
    epd_send_data(0xF9);  // 0x00F9 = 249 (height-1 lo)
    epd_send_data(0x00);  //              hi
    epd_send_data(0x00);  // gate scanning order

    epd_send_command(0x11);                                  // data entry mode
    epd_send_data(0x03);                                     // X+, Y+

    // SetWindow(0,0, w-1, h-1)
    epd_send_command(0x44);                                  // RAM-X start/end
    epd_send_data(0x00);
    epd_send_data((EPD_WIDTH - 1) / 8);
    epd_send_command(0x45);                                  // RAM-Y start/end
    epd_send_data(0x00);
    epd_send_data(0x00);
    epd_send_data((EPD_HEIGHT - 1) & 0xFF);
    epd_send_data(((EPD_HEIGHT - 1) >> 8) & 0xFF);

    // SetCursor(0,0)
    epd_send_command(0x4E);
    epd_send_data(0x00);
    epd_send_command(0x4F);
    epd_send_data(0x00);
    epd_send_data(0x00);

    epd_send_command(0x3C);                                  // Border waveform
    epd_send_data(0x05);

    epd_send_command(0x21);                                  // Display Update Control 1
    epd_send_data(0x00);
    epd_send_data(0x80);

    epd_send_command(0x18);                                  // Temperature sensor selection
    epd_send_data(0x80);                                     // 0x80 = internal sensor

    return epd_wait_busy();
}

// Init для partial update (без temperature load — используем уже записанный LUT).
bool epd_init_partial() {
    DBG("epd_init_partial\n");
    if (!epd_init()) return false;

    // Дополнительная настройка для partial: VCOM (если требуется кастомная).
    // По умолчанию остаёмся на factory VCOM (значение в OTP).
    return true;
}

// Fast init — Waveshare-овский трюк с подменой температуры через 0x1A.
bool epd_init_partial_fast() {
    DBG("epd_init_partial_fast\n");
    epd_reset();
    epd_send_command(0x12);                                  // SWRESET
    if (!epd_wait_busy()) return false;

    epd_send_command(0x18);                                  // Temperature sensor select
    epd_send_data(0x80);

    epd_send_command(0x11);                                  // data entry
    epd_send_data(0x03);

    // SetWindow, SetCursor (как в epd_init)
    epd_send_command(0x44); epd_send_data(0x00); epd_send_data((EPD_WIDTH - 1) / 8);
    epd_send_command(0x45);
    epd_send_data(0x00); epd_send_data(0x00);
    epd_send_data((EPD_HEIGHT - 1) & 0xFF); epd_send_data(((EPD_HEIGHT - 1) >> 8) & 0xFF);
    epd_send_command(0x4E); epd_send_data(0x00);
    epd_send_command(0x4F); epd_send_data(0x00); epd_send_data(0x00);

    epd_send_command(0x22);                                  // Load temperature value + Load LUT (Mode 1)
    epd_send_data(0xB1);
    epd_send_command(0x20);                                  // Master Activation
    if (!epd_wait_busy()) return false;

    epd_send_command(0x1A);                                  // Write to temperature register
    epd_send_data(0x64);                                     // 0x0064 / 16 = +6.25 °C (фейк для холодного LUT)
    epd_send_data(0x00);

    epd_send_command(0x22);                                  // Load LUT Mode 1 (по подменённой T)
    epd_send_data(0x91);
    epd_send_command(0x20);
    return epd_wait_busy();
}

// Запись 4000-байтного frame buffer в RAM 0x24 (b/w).
bool epd_write_frame(const uint8_t* buf, size_t len) {
    if (len != EPD_FRAME_SIZE) {
        DBG("epd_write_frame: bad len %u (expected %u)\n", (unsigned)len, EPD_FRAME_SIZE);
        return false;
    }
    epd_send_command(0x24);                                  // Write RAM (B/W)
    epd_send_data_buffer(buf, len);
    return true;
}

// Запись 4000-байтного buffer в RAM 0x26 (old/red) — базовый кадр для partial.
bool epd_write_frame_old(const uint8_t* buf, size_t len) {
    if (len != EPD_FRAME_SIZE) return false;
    epd_send_command(0x26);                                  // Write RAM (OLD)
    epd_send_data_buffer(buf, len);
    return true;
}

// Запись 153-байтной LUT в регистр 0x32.
bool epd_write_lut(const uint8_t* lut, size_t len) {
    if (len != EPD_LUT_SIZE) {
        DBG("epd_write_lut: bad len %u (expected %u)\n", (unsigned)len, EPD_LUT_SIZE);
        return false;
    }
    epd_send_command(0x32);
    epd_send_data_buffer(lut, len);
    return true;
}

// Full refresh с заводской LUT по температуре (0x22 = 0xF7).
bool epd_refresh_full() {
    DBG("epd_refresh_full (0x22=0xF7)\n");
    epd_send_command(0x22);
    epd_send_data(0xF7);                                     // Load temp + DISPLAY Mode 1 + Disable
    epd_send_command(0x20);                                  // Master Activation
    return epd_wait_busy();
}

// Partial refresh (0x22 = 0xCF) — DISPLAY Mode 2, BEZ загрузки temperature.
bool epd_refresh_partial() {
    DBG("epd_refresh_partial (0x22=0xCF)\n");
    epd_send_command(0x22);
    epd_send_data(0xCF);
    epd_send_command(0x20);
    return epd_wait_busy();
}

// КЛЮЧЕВОЙ ФИКС: refresh с кастомной LUT, БЕЗ перезагрузки из OTP по температуре.
// 0x22 = 0xC7 → последовательность "Enable Analog + DISPLAY Mode 1 + Disable Analog + Disable OSC"
// БЕЗ "Load temperature value" → используется LUT, записанная пользователем через 0x32.
// Без этого фикса 0xFF/0xF7 запускают Waveform Setting Searching Mechanism (Section 6.9 datasheet)
// и перезаписывают пользовательский LUT заводской.
bool epd_refresh_custom_lut() {
    DBG("epd_refresh_custom_lut (0x22=0xC7) — using user-written LUT from 0x32\n");
    epd_send_command(0x22);
    epd_send_data(0xC7);
    epd_send_command(0x20);
    return epd_wait_busy();
}

// Deep sleep.
void epd_sleep() {
    DBG("epd_sleep\n");
    epd_send_command(0x10);
    epd_send_data(0x01);
}

// ===========================================================================
//                            INA219 (I²C)
// ===========================================================================

bool ina219_write_reg(uint8_t reg, uint16_t value) {
    Wire.beginTransmission(INA219_ADDR);
    Wire.write(reg);
    Wire.write((value >> 8) & 0xFF);
    Wire.write(value & 0xFF);
    return (Wire.endTransmission() == 0);
}

bool ina219_read_reg(uint8_t reg, uint16_t* out) {
    Wire.beginTransmission(INA219_ADDR);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom((uint8_t)INA219_ADDR, (uint8_t)2) != 2) return false;
    uint8_t hi = Wire.read();
    uint8_t lo = Wire.read();
    *out = ((uint16_t)hi << 8) | lo;
    return true;
}

bool ina219_init() {
    // Config: BRNG=0 (16V), PG=01 (±80mV), BADC=ADC=12bit, single-shot continuous (0x07 mode)
    // 0x199F: 0001 1001 1001 1111 → 16V, /1 gain, 12bit 8 sample averaging
    if (!ina219_write_reg(INA219_REG_CONFIG, 0x199F)) return false;
    if (!ina219_write_reg(INA219_REG_CALIB, INA219_CAL_VALUE)) return false;
    DBG("INA219 init OK\n");
    return true;
}

// struct InaReadout определён выше (после INA219 constants).
bool ina219_read_all(InaReadout* r) {
    uint16_t v;
    if (!ina219_read_reg(INA219_REG_SHUNT,   &v)) return false; r->shunt_raw   = (int16_t)v;
    if (!ina219_read_reg(INA219_REG_BUS,     &v)) return false; r->bus_raw     = v;
    if (!ina219_read_reg(INA219_REG_CURRENT, &v)) return false; r->current_raw = (int16_t)v;
    if (!ina219_read_reg(INA219_REG_POWER,   &v)) return false; r->power_raw   = v;
    return true;
}

// ===========================================================================
//                            Serial transport helpers
// ===========================================================================

void send_status(uint16_t status) {
    Serial.write((uint8_t)((status >> 8) & 0xFF));
    Serial.write((uint8_t)(status & 0xFF));
    Serial.flush();
}

// Blocking read of n bytes. Используем встроенный Serial.readBytes(), который
// надёжнее ручного цикла на больших объёмах и автоматически блокируется до
// получения всех байт или истечения Serial.setTimeout() (выставлен в setup()).
// Возвращает false, если не удалось получить все n байт за timeout.
bool read_bytes(uint8_t* buf, size_t n) {
    size_t got = Serial.readBytes(buf, n);
    return got == n;
}

// Static frame buffer — 4000 байт, alloc один раз в .bss.
static uint8_t frame_buf[EPD_FRAME_SIZE];
static uint8_t lut_buf[EPD_LUT_SIZE];

// ---- BENCH_RUN: RAM-буфер для INA219 трассы --------------------------------
// Каждый sample = {t_us:u32, I_raw:i16, P_raw:u16} = 8 байт.
// Лимит 5000 samples = 40 KB. При sampling ~300 Гц (8-sample averaging
// в INA219 config 0x199F) хватит на ~16 секунд непрерывного измерения.
constexpr uint16_t BENCH_MAX_SAMPLES = 5000;
struct BenchSample {
    uint32_t t_us;       // относительно старта refresh
    int16_t  i_raw;      // INA219 CURRENT register
    uint16_t p_raw;      // INA219 POWER register
} __attribute__((packed));
static BenchSample bench_buf[BENCH_MAX_SAMPLES];

// ===========================================================================
//                            Opcode dispatcher
// ===========================================================================

void dispatch(uint8_t opcode) {
    switch (opcode) {
        case OP_INIT: {
            send_status(epd_init() ? STATUS_OK : STATUS_TIMEOUT_BUSY);
            break;
        }
        case OP_FRAME: {
            if (!read_bytes(frame_buf, EPD_FRAME_SIZE)) {
                send_status(STATUS_TIMEOUT_RX); break;
            }
            send_status(epd_write_frame(frame_buf, EPD_FRAME_SIZE) ? STATUS_OK : STATUS_BAD_OPCODE);
            break;
        }
        case OP_REFRESH: {
            send_status(epd_refresh_full() ? STATUS_OK : STATUS_TIMEOUT_BUSY);
            break;
        }
        case OP_SLEEP: {
            epd_sleep();
            send_status(STATUS_OK);
            break;
        }
        case OP_LUT: {
            if (!read_bytes(lut_buf, EPD_LUT_SIZE)) {
                send_status(STATUS_TIMEOUT_RX); break;
            }
            send_status(epd_write_lut(lut_buf, EPD_LUT_SIZE) ? STATUS_OK : STATUS_BAD_OPCODE);
            break;
        }
        case OP_PING: {
            // Ответ: 2 байта статус + 2 байта версия FW
            send_status(STATUS_OK);
            Serial.write((uint8_t)((FW_VERSION >> 8) & 0xFF));
            Serial.write((uint8_t)(FW_VERSION & 0xFF));
            Serial.flush();
            break;
        }
        case OP_INA_READ: {
            InaReadout r;
            if (!ina219_read_all(&r)) {
                send_status(STATUS_INA_NACK); break;
            }
            send_status(STATUS_OK);
            // 8 байт raw: shunt(2) + bus(2) + current(2) + power(2), big-endian
            uint8_t out[8] = {
                (uint8_t)((r.shunt_raw   >> 8) & 0xFF), (uint8_t)(r.shunt_raw   & 0xFF),
                (uint8_t)((r.bus_raw     >> 8) & 0xFF), (uint8_t)(r.bus_raw     & 0xFF),
                (uint8_t)((r.current_raw >> 8) & 0xFF), (uint8_t)(r.current_raw & 0xFF),
                (uint8_t)((r.power_raw   >> 8) & 0xFF), (uint8_t)(r.power_raw   & 0xFF),
            };
            Serial.write(out, 8);
            Serial.flush();
            break;
        }
        case OP_REFRESH_PARTIAL: {
            send_status(epd_refresh_partial() ? STATUS_OK : STATUS_TIMEOUT_BUSY);
            break;
        }
        case OP_INIT_PARTIAL: {
            send_status(epd_init_partial() ? STATUS_OK : STATUS_TIMEOUT_BUSY);
            break;
        }
        case OP_INIT_PARTIAL_FAST: {
            send_status(epd_init_partial_fast() ? STATUS_OK : STATUS_TIMEOUT_BUSY);
            break;
        }
        case OP_REFRESH_CUSTOM_LUT: {
            send_status(epd_refresh_custom_lut() ? STATUS_OK : STATUS_TIMEOUT_BUSY);
            break;
        }
        // --- B2: расширенные опкоды ---
        case OP_WRITE_LUT_DYNAMIC: {
            // Принять 153 байта LUT, записать в 0x32, сразу refresh с 0xC7.
            if (!read_bytes(lut_buf, EPD_LUT_SIZE)) {
                send_status(STATUS_TIMEOUT_RX); break;
            }
            if (!epd_write_lut(lut_buf, EPD_LUT_SIZE)) {
                send_status(STATUS_BAD_OPCODE); break;
            }
            send_status(epd_refresh_custom_lut() ? STATUS_OK : STATUS_TIMEOUT_BUSY);
            break;
        }

        case OP_WRITE_REGISTER: {
            // Принять {addr:u8, len:u8, data[len]}, записать в произвольный регистр SSD1680.
            // Используется для тонкой калибровки (например 0x1A — temperature override,
            // 0x2C — VCOM, 0x03 — VGH, 0x04 — VSH1/VSH2/VSL).
            uint8_t header[2];
            if (!read_bytes(header, 2)) { send_status(STATUS_TIMEOUT_RX); break; }
            uint8_t addr = header[0];
            uint8_t len  = header[1];
            if (len > 16) {           // sanity: типовые регистры ≤ 10 байт
                send_status(STATUS_BAD_OPCODE); break;
            }
            uint8_t data[16];
            if (len > 0 && !read_bytes(data, len)) {
                send_status(STATUS_TIMEOUT_RX); break;
            }
            epd_send_command(addr);
            for (uint8_t i = 0; i < len; i++) epd_send_data(data[i]);
            send_status(STATUS_OK);
            break;
        }

        case OP_BENCH_RUN: {
            // Принять {LUT:153, image:4000, n_repeats:u8}, выполнить N циклов
            // "write_lut → write_frame → refresh_custom_lut" с записью INA219 трассы
            // во время refresh (BUSY=1). Вернуть status + n_samples + trace.
            //
            // Запрос:  [0x0E][LUT 153][image 4000][N 1]   = 4154 байт после opcode
            // Ответ:   [status 2][n_samples 2][trace n_samples*8]
            if (!read_bytes(lut_buf, EPD_LUT_SIZE))            { send_status(STATUS_TIMEOUT_RX); break; }
            if (!read_bytes(frame_buf, EPD_FRAME_SIZE))        { send_status(STATUS_TIMEOUT_RX); break; }
            uint8_t n_rep_byte;
            if (!read_bytes(&n_rep_byte, 1))                   { send_status(STATUS_TIMEOUT_RX); break; }
            uint8_t n_repeats = n_rep_byte;
            if (n_repeats == 0) n_repeats = 1;

            // Записываем LUT один раз перед циклом — он стабилен между обновлениями
            // (0x22=0xC7 не перезагружает её).
            if (!epd_write_lut(lut_buf, EPD_LUT_SIZE))         { send_status(STATUS_BAD_OPCODE); break; }

            uint16_t total_samples = 0;
            uint32_t bench_t0 = micros();

            for (uint8_t rep = 0; rep < n_repeats; rep++) {
                // Запись frame (один и тот же image на все повторы).
                if (!epd_write_frame(frame_buf, EPD_FRAME_SIZE)) {
                    send_status(STATUS_BAD_OPCODE); return;
                }

                // Старт refresh (0x22=0xC7 + 0x20). BUSY поднимется.
                epd_send_command(0x22); epd_send_data(0xC7);
                epd_send_command(0x20);

                // Семплируем INA219 пока BUSY=1.
                uint32_t t0 = micros();
                uint32_t deadline = millis() + BUSY_TIMEOUT_MS;
                while (digitalRead(PIN_BUSY) == HIGH) {
                    if (millis() > deadline) {
                        send_status(STATUS_TIMEOUT_BUSY); return;
                    }
                    if (total_samples >= BENCH_MAX_SAMPLES) break;   // буфер кончился
                    InaReadout r;
                    if (ina219_read_all(&r)) {
                        bench_buf[total_samples].t_us  = micros() - bench_t0;
                        bench_buf[total_samples].i_raw = r.current_raw;
                        bench_buf[total_samples].p_raw = r.power_raw;
                        total_samples++;
                    }
                    // INA219 в config 0x199F даёт ~300 Гц (8-sample avg).
                    // delayMicroseconds(0) — отдадим scheduler'у только если нужно.
                }
                (void)t0;
            }

            // Ответ
            send_status(STATUS_OK);
            Serial.write((uint8_t)((total_samples >> 8) & 0xFF));
            Serial.write((uint8_t)(total_samples & 0xFF));
            Serial.write((const uint8_t*)bench_buf, (size_t)total_samples * sizeof(BenchSample));
            Serial.flush();
            break;
        }

        case OP_BENCH_FACTORY: {
            // Бенчмарк ЗАВОДСКОГО refresh (baseline B0/B1) с INA-трассой.
            // В отличие от BENCH_RUN, НЕ пишет custom LUT — использует
            // заводскую (OTP) waveform, выбранную по 0x22-байту:
            //   mode 0xF7 → full factory (B0, загрузка темп. + DISPLAY Mode 1)
            //   mode 0xC7 → DISPLAY Mode 1 без перезагрузки (B1, после init_fast)
            // INIT (обычный 0x01 для B0 либо fast 0x0A для B1) выполняется
            // ОТДЕЛЬНЫМ опкодом ДО вызова BENCH_FACTORY.
            //
            // Запрос:  [0x0F][image 4000][mode 1]   = 4001 байт после opcode
            // Ответ:   [status 2][n_samples 2][trace n_samples*8]
            if (!read_bytes(frame_buf, EPD_FRAME_SIZE))        { send_status(STATUS_TIMEOUT_RX); break; }
            uint8_t mode_byte;
            if (!read_bytes(&mode_byte, 1))                    { send_status(STATUS_TIMEOUT_RX); break; }

            if (!epd_write_frame(frame_buf, EPD_FRAME_SIZE))   { send_status(STATUS_BAD_OPCODE); break; }

            uint16_t total_samples = 0;
            uint32_t bench_t0 = micros();

            // Старт заводского refresh (0x22 = mode_byte + 0x20). BUSY поднимется.
            epd_send_command(0x22); epd_send_data(mode_byte);
            epd_send_command(0x20);

            uint32_t deadline = millis() + BUSY_TIMEOUT_MS;
            while (digitalRead(PIN_BUSY) == HIGH) {
                if (millis() > deadline) { send_status(STATUS_TIMEOUT_BUSY); return; }
                if (total_samples >= BENCH_MAX_SAMPLES) break;
                InaReadout r;
                if (ina219_read_all(&r)) {
                    bench_buf[total_samples].t_us  = micros() - bench_t0;
                    bench_buf[total_samples].i_raw = r.current_raw;
                    bench_buf[total_samples].p_raw = r.power_raw;
                    total_samples++;
                }
            }

            send_status(STATUS_OK);
            Serial.write((uint8_t)((total_samples >> 8) & 0xFF));
            Serial.write((uint8_t)(total_samples & 0xFF));
            Serial.write((const uint8_t*)bench_buf, (size_t)total_samples * sizeof(BenchSample));
            Serial.flush();
            break;
        }

        case OP_PART_BASE: {
            // Базовый кадр для partial: записать image в RAM 0x24 И 0x26 + полный
            // refresh (0xC7). Устанавливает «предыдущее» состояние, относительно
            // которого partial-обновление двигает лишь изменившиеся пиксели.
            // INIT (0x01) должен быть выполнен ДО. Запрос: [0x10][image 4000].
            if (!read_bytes(frame_buf, EPD_FRAME_SIZE))        { send_status(STATUS_TIMEOUT_RX); break; }
            if (!epd_write_frame(frame_buf, EPD_FRAME_SIZE))   { send_status(STATUS_BAD_OPCODE); break; }
            if (!epd_write_frame_old(frame_buf, EPD_FRAME_SIZE)){ send_status(STATUS_BAD_OPCODE); break; }
            // 0xF7 — заводский полный refresh (грузит OTP-LUT + температуру):
            // гарантированно чистит панель независимо от содержимого регистра 0x32.
            epd_send_command(0x22); epd_send_data(0xF7);
            epd_send_command(0x20);
            if (!epd_wait_busy())                              { send_status(STATUS_TIMEOUT_BUSY); break; }
            send_status(STATUS_OK);
            break;
        }

        case OP_BENCH_PARTIAL: {
            // Бенчмарк ЧАСТИЧНОГО (безмерцательного) обновления с INA-трассой.
            // Последовательность по драйверу Waveshare V3 displayPartial, БЕЗ
            // SWRESET (чтобы сохранить базовый кадр в RAM 0x26 от OP_PART_BASE).
            // Запрос: [0x11][lut 153][cfg 6][mode 1][image 4000].
            //   cfg = [0x3F, 0x03(gate), 0x04a, 0x04b, 0x04c, 0x2C(VCOM)]
            //   mode = байт 0x22 для partial (V3: 0x0F качество / 0x0C быстро / 0xCF)
            // Ответ: [status 2][n_samples 2][trace n_samples*8]
            uint8_t cfg[6]; uint8_t mode_byte;
            if (!read_bytes(lut_buf, EPD_LUT_SIZE))            { send_status(STATUS_TIMEOUT_RX); break; }
            if (!read_bytes(cfg, 6))                           { send_status(STATUS_TIMEOUT_RX); break; }
            if (!read_bytes(&mode_byte, 1))                    { send_status(STATUS_TIMEOUT_RX); break; }
            if (!read_bytes(frame_buf, EPD_FRAME_SIZE))        { send_status(STATUS_TIMEOUT_RX); break; }

            // SetLut: 153-байт LUT + хвост напряжений.
            epd_write_lut(lut_buf, EPD_LUT_SIZE);
            epd_send_command(0x3F); epd_send_data(cfg[0]);
            epd_send_command(0x03); epd_send_data(cfg[1]);
            epd_send_command(0x04); epd_send_data(cfg[2]); epd_send_data(cfg[3]); epd_send_data(cfg[4]);
            epd_send_command(0x2C); epd_send_data(cfg[5]);

            // Конфигурация partial (V3): 0x37 + 10 байт, граница 0x3C=0x80, prep 0x22=0xC0.
            epd_send_command(0x37);
            epd_send_data(0x00); epd_send_data(0x00); epd_send_data(0x00); epd_send_data(0x00);
            epd_send_data(0x00); epd_send_data(0x40); epd_send_data(0x00); epd_send_data(0x00);
            epd_send_data(0x00); epd_send_data(0x00);
            epd_send_command(0x3C); epd_send_data(0x80);
            epd_send_command(0x22); epd_send_data(0xC0);
            epd_send_command(0x20);
            if (!epd_wait_busy())                              { send_status(STATUS_TIMEOUT_BUSY); break; }

            // Новый кадр в RAM 0x24 (0x26 хранит базовый от PART_BASE).
            if (!epd_write_frame(frame_buf, EPD_FRAME_SIZE))   { send_status(STATUS_BAD_OPCODE); break; }

            // Старт partial-обновления (0x22=mode + 0x20) с INA-семплированием.
            uint16_t total_samples = 0;
            uint32_t bench_t0 = micros();
            epd_send_command(0x22); epd_send_data(mode_byte);
            epd_send_command(0x20);
            uint32_t deadline = millis() + BUSY_TIMEOUT_MS;
            while (digitalRead(PIN_BUSY) == HIGH) {
                if (millis() > deadline) { send_status(STATUS_TIMEOUT_BUSY); return; }
                if (total_samples >= BENCH_MAX_SAMPLES) break;
                InaReadout r;
                if (ina219_read_all(&r)) {
                    bench_buf[total_samples].t_us  = micros() - bench_t0;
                    bench_buf[total_samples].i_raw = r.current_raw;
                    bench_buf[total_samples].p_raw = r.power_raw;
                    total_samples++;
                }
            }
            send_status(STATUS_OK);
            Serial.write((uint8_t)((total_samples >> 8) & 0xFF));
            Serial.write((uint8_t)(total_samples & 0xFF));
            Serial.write((const uint8_t*)bench_buf, (size_t)total_samples * sizeof(BenchSample));
            Serial.flush();
            break;
        }

        case OP_WRITE_OLD: {
            // Записать «предыдущий» кадр в RAM 0x26 (без refresh) — для корректного
            // последовательного partial: контроллер диффит 0x24(новый) vs 0x26(старый).
            // Запрос: [0x12][image 4000].
            if (!read_bytes(frame_buf, EPD_FRAME_SIZE))        { send_status(STATUS_TIMEOUT_RX); break; }
            if (!epd_write_frame_old(frame_buf, EPD_FRAME_SIZE)){ send_status(STATUS_BAD_OPCODE); break; }
            send_status(STATUS_OK);
            break;
        }

        default: {
            send_status(STATUS_BAD_OPCODE);
            break;
        }
    }
}

// ===========================================================================
//                            Arduino entry points
// ===========================================================================

void setup() {
    // КРИТИЧНО: увеличиваем RX-буфер ДО Serial.begin() — иначе ESP32 теряет байты
    // при больших передачах (FRAME=4000B, BENCH_RUN=4154B) на 921600 бод.
    // Дефолтный буфер 256 байт → loss на больших frame'ах → TIMEOUT_RX на хост-стороне.
    Serial.setRxBufferSize(SERIAL_RX_BUFFER);
    Serial.begin(SERIAL_BAUD);
    Serial.setTimeout(RX_TIMEOUT_MS);  // используется в read_bytes() через Serial.readBytes()

    // Запасной канал логов: Serial2 (UART2 = GPIO16/17 — НО они заняты под RST/DC!)
    // Поэтому DBG() в production должен оставаться выключенным.

    pinMode(PIN_RST,  OUTPUT);
    pinMode(PIN_DC,   OUTPUT);
    pinMode(PIN_CS,   OUTPUT);
    pinMode(PIN_BUSY, INPUT);
    digitalWrite(PIN_CS, HIGH);

    SPI.begin(PIN_CLK, /*MISO*/-1, PIN_MOSI, PIN_CS);
    Wire.begin(PIN_SDA, PIN_SCL, I2C_FREQ);

    if (!ina219_init()) {
        DBG("INA219 init failed\n");
    }

    DBG("epd_bridge ready, fw=0x%04X, baud=%u\n", FW_VERSION, (unsigned)SERIAL_BAUD);
}

void loop() {
    if (Serial.available()) {
        uint8_t op = (uint8_t)Serial.read();
        dispatch(op);
    }
}
