#include "sensors_bme280.h"

#include <math.h>

#include "config.h"

// =============================================================================
// Dummy-mode stub (compile-time selected via -D USE_DUMMY_SENSORS=1).
// Returns constant readings matching the schema example so the rest of the
// architecture can be developed and demoed without working hardware.
// =============================================================================
#ifdef USE_DUMMY_SENSORS

namespace {
bool g_ready = false;
constexpr float DUMMY_TEMP_C    = 23.7f;
constexpr float DUMMY_HUMID_PCT = 45.2f;
constexpr float DUMMY_PRES_HPA  = 1013.25f;
}

namespace SensorsBme280 {

bool begin() {
    if (!g_ready) {
        Serial.printf("[INFO] [%lus] BME280 dummy mode — returning constants\n",
                      (unsigned long)(millis() / 1000UL));
        g_ready = true;
    }
    return true;
}

bool isReady() { return g_ready; }

Bme280Reading read() {
    if (!g_ready) begin();
    return {DUMMY_TEMP_C, DUMMY_HUMID_PCT, DUMMY_PRES_HPA, true, true};
}

const char* sensorName() { return g_ready ? "bme280" : "none"; }

} // namespace SensorsBme280

#else // ============= Real I2C path: BME280 with BMP280 fallback ==============

#include <Wire.h>
#include <Adafruit_BME280.h>
#include <Adafruit_BMP280.h>
#include <Adafruit_Sensor.h>

namespace {

enum class ChipType : uint8_t { None, Bme280, Bmp280 };

Adafruit_BME280 g_bme;
Adafruit_BMP280 g_bmp;
ChipType        g_chip = ChipType::None;
bool            g_ready = false;
unsigned int    g_fail_count = 0;

constexpr float PA_PER_HPA = 100.0f;

void reportBusElectricals() {
    pinMode(I2C_SDA_PIN, INPUT);
    pinMode(I2C_SCL_PIN, INPUT);
    delayMicroseconds(50);
    const int sda_idle = digitalRead(I2C_SDA_PIN);
    const int scl_idle = digitalRead(I2C_SCL_PIN);
    Serial.printf("[INFO]   bus idle (no internal pullup): SDA=%s  SCL=%s\n",
                  sda_idle ? "HIGH" : "LOW",
                  scl_idle ? "HIGH" : "LOW");
    if (!sda_idle || !scl_idle) {
        Serial.println(F("[INFO]   -> a LOW idle line means no external pull-up "
                         "is reaching it (bad wire, no power, or a competing "
                         "pull-down such as an onboard LED on this pin)"));
    }
}

void scanI2cAndReport() {
    Serial.printf("[INFO] [%lus] I2C scan on SDA=%d SCL=%d ...\n",
                  (unsigned long)(millis() / 1000UL),
                  I2C_SDA_PIN, I2C_SCL_PIN);
    int found = 0;
    for (uint8_t addr = 0x03; addr < 0x78; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf("[INFO]   device responding at 0x%02X\n", addr);
            found++;
        }
    }
    if (found == 0) {
        Serial.println(F("[INFO]   no devices on bus (wiring/power/pin issue)"));
    }
}

void reportChipId(uint8_t addr) {
    Wire.beginTransmission(addr);
    Wire.write(0xD0);
    if (Wire.endTransmission(false) != 0) {
        Serial.printf("[INFO]   chip-id readback failed at 0x%02X\n", addr);
        return;
    }
    Wire.requestFrom(addr, (uint8_t)1);
    if (!Wire.available()) {
        Serial.printf("[INFO]   chip-id readback: no data at 0x%02X\n", addr);
        return;
    }
    const uint8_t id = Wire.read();
    const char* name = "unknown";
    switch (id) {
        case 0x60: name = "BME280 (genuine — temp/humidity/pressure)"; break;
        case 0x58: name = "BMP280 (NO humidity — temp/pressure only)"; break;
        case 0x57: case 0x56: name = "BMP280 early sample"; break;
    }
    Serial.printf("[INFO]   chip ID at 0x%02X reg 0xD0 = 0x%02X (%s)\n",
                  addr, id, name);
}

void configureBme280() {
    g_bme.setSampling(Adafruit_BME280::MODE_NORMAL,
                      Adafruit_BME280::SAMPLING_X1,
                      Adafruit_BME280::SAMPLING_X1,
                      Adafruit_BME280::SAMPLING_X1,
                      Adafruit_BME280::FILTER_OFF,
                      Adafruit_BME280::STANDBY_MS_1000);
}

void configureBmp280() {
    g_bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                      Adafruit_BMP280::SAMPLING_X1,   // temperature
                      Adafruit_BMP280::SAMPLING_X1,   // pressure
                      Adafruit_BMP280::FILTER_OFF,
                      Adafruit_BMP280::STANDBY_MS_1000);
}

bool tryBme280() {
    if (!g_bme.begin(BME280_I2C_ADDR, &Wire)) return false;
    configureBme280();
    g_chip = ChipType::Bme280;
    Serial.printf("[INFO] [%lus] BME280 initialised at 0x%02X\n",
                  (unsigned long)(millis() / 1000UL), BME280_I2C_ADDR);
    return true;
}

bool tryBmp280() {
    if (!g_bmp.begin(BME280_I2C_ADDR, BMP280_CHIPID)) return false;
    configureBmp280();
    g_chip = ChipType::Bmp280;
    Serial.printf("[INFO] [%lus] BMP280 initialised at 0x%02X "
                  "(no humidity available)\n",
                  (unsigned long)(millis() / 1000UL), BME280_I2C_ADDR);
    return true;
}

} // namespace

namespace SensorsBme280 {

bool begin() {
    if (g_ready) return true;

    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
    Wire.setClock(100000);

    if (tryBme280() || tryBmp280()) {
        g_ready = true;
        return true;
    }

    Serial.printf("[ERROR] [%lus] BME280/BMP280 not found at 0x%02X (check wiring & 3.3V)\n",
                  (unsigned long)(millis() / 1000UL), BME280_I2C_ADDR);

    const bool do_diag = (g_fail_count == 0) || (g_fail_count % 10 == 0);
    if (do_diag) {
        reportBusElectricals();
        Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
        Wire.setClock(100000);
        scanI2cAndReport();
        reportChipId(BME280_I2C_ADDR);
        reportChipId(0x77);
    }
    g_fail_count++;
    g_ready = false;
    return false;
}

bool isReady() { return g_ready; }

Bme280Reading read() {
    Bme280Reading r{NAN, NAN, NAN, false, false};

    if (!g_ready) {
        if (!begin()) return r;
    }

    if (g_chip == ChipType::Bme280) {
        const float t    = g_bme.readTemperature();
        const float h    = g_bme.readHumidity();
        const float p_pa = g_bme.readPressure();
        if (isnan(t) || isnan(h) || isnan(p_pa)) return r;
        r.temperature_c = t;
        r.humidity_pct  = h;
        r.pressure_hpa  = p_pa / PA_PER_HPA;
        r.has_humidity  = true;
        r.ok            = true;
        return r;
    }

    if (g_chip == ChipType::Bmp280) {
        const float t    = g_bmp.readTemperature();
        const float p_pa = g_bmp.readPressure();
        if (isnan(t) || isnan(p_pa)) return r;
        r.temperature_c = t;
        r.humidity_pct  = NAN;          // BMP280 has no humidity sensor
        r.pressure_hpa  = p_pa / PA_PER_HPA;
        r.has_humidity  = false;
        r.ok            = true;
        return r;
    }

    return r;
}

const char* sensorName() {
    switch (g_chip) {
        case ChipType::Bme280: return "bme280";
        case ChipType::Bmp280: return "bmp280";
        default:               return "none";
    }
}

} // namespace SensorsBme280

#endif // USE_DUMMY_SENSORS
