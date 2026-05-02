#include "sensors_bme280.h"

#include <Wire.h>
#include <Adafruit_BME280.h>
#include <Adafruit_Sensor.h>
#include <math.h>

#include "config.h"

namespace {

Adafruit_BME280 bme;
bool g_ready = false;
bool g_scanned_on_failure = false;

constexpr float PA_PER_HPA = 100.0f;

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

void configureSampling() {
    // Weather-station preset: low power, ~1 Hz friendly, 1x oversampling.
    bme.setSampling(Adafruit_BME280::MODE_NORMAL,
                    Adafruit_BME280::SAMPLING_X1,   // temperature
                    Adafruit_BME280::SAMPLING_X1,   // pressure
                    Adafruit_BME280::SAMPLING_X1,   // humidity
                    Adafruit_BME280::FILTER_OFF,
                    Adafruit_BME280::STANDBY_MS_1000);
}

} // namespace

namespace SensorsBme280 {

bool begin() {
    if (g_ready) {
        return true;
    }

    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
    Wire.setClock(100000); // 100 kHz: most tolerant of cheap GY-BME280 wiring

    if (!bme.begin(BME280_I2C_ADDR, &Wire)) {
        Serial.printf("[ERROR] [%lus] BME280 not found at 0x%02X (check wiring & 3.3V)\n",
                      (unsigned long)(millis() / 1000UL), BME280_I2C_ADDR);
        if (!g_scanned_on_failure) {
            g_scanned_on_failure = true;
            scanI2cAndReport();
            // Also try the alternative GY-BME280 address (SDO tied HIGH)
            if (bme.begin(0x77, &Wire)) {
                Serial.println(F("[INFO]   BME280 actually answered at 0x77 — "
                                 "update BME280_I2C_ADDR in config.h"));
            }
        }
        g_ready = false;
        return false;
    }

    configureSampling();
    g_ready = true;
    Serial.printf("[INFO] [%lus] BME280 initialised at 0x%02X\n",
                  (unsigned long)(millis() / 1000UL), BME280_I2C_ADDR);
    return true;
}

bool isReady() {
    return g_ready;
}

Bme280Reading read() {
    Bme280Reading r{NAN, NAN, NAN, false};

    if (!g_ready) {
        // Try to recover silently — the main loop will log if it stays down.
        if (!begin()) {
            return r;
        }
    }

    const float t = bme.readTemperature();
    const float h = bme.readHumidity();
    const float p_pa = bme.readPressure();

    if (isnan(t) || isnan(h) || isnan(p_pa)) {
        return r;
    }

    r.temperature_c = t;
    r.humidity_pct  = h;
    r.pressure_hpa  = p_pa / PA_PER_HPA;
    r.ok = true;
    return r;
}

} // namespace SensorsBme280
