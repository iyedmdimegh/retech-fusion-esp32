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
    return {DUMMY_TEMP_C, DUMMY_HUMID_PCT, DUMMY_PRES_HPA, true};
}

} // namespace SensorsBme280

#else // ====================== Real I2C / Adafruit_BME280 path ================

#include <Wire.h>
#include <Adafruit_BME280.h>
#include <Adafruit_Sensor.h>

namespace {

Adafruit_BME280 bme;
bool g_ready = false;
unsigned int g_fail_count = 0;

constexpr float PA_PER_HPA = 100.0f;

void reportBusElectricals() {
    // Briefly take the I2C pins back as plain GPIO inputs WITHOUT enabling the
    // internal pull-ups, so we can see what voltage the external pull-ups
    // (or competing pull-downs like an onboard LED) actually settle at.
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

        // Run the full diagnostic on the very first failure, and again every
        // 10 retries so the user can always see it without scrolling.
        const bool do_diag = (g_fail_count == 0) || (g_fail_count % 10 == 0);
        if (do_diag) {
            reportBusElectricals();
            // Restore I2C mode after the electrical sniff.
            Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
            Wire.setClock(100000);
            scanI2cAndReport();
            // Try the alternative GY-BME280 address (SDO tied HIGH).
            if (bme.begin(0x77, &Wire)) {
                Serial.println(F("[INFO]   BME280 actually answered at 0x77 — "
                                 "update BME280_I2C_ADDR in config.h to 0x77"));
            }
        }
        g_fail_count++;
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

#endif // USE_DUMMY_SENSORS
