#include "sensors_ds18b20.h"

#include <math.h>

#include "config.h"

// =============================================================================
// Dummy-mode stub (compile-time selected via -D USE_DUMMY_SENSORS=1).
// =============================================================================
#ifdef USE_DUMMY_SENSORS

namespace {
bool g_ready = false;
constexpr float DUMMY_TEMP_C = 23.5f;
}

namespace SensorsDs18b20 {

bool begin() {
    if (!g_ready) {
        Serial.printf("[INFO] [%lus] DS18B20 dummy mode — returning constants\n",
                      (unsigned long)(millis() / 1000UL));
        g_ready = true;
    }
    return true;
}

bool isReady() { return g_ready; }

Ds18b20Reading read() {
    if (!g_ready) begin();
    return {DUMMY_TEMP_C, true};
}

} // namespace SensorsDs18b20

#else // ====================== Real OneWire / DallasTemperature path ===========

#include <OneWire.h>
#include <DallasTemperature.h>

namespace {

OneWire           g_oneWire(DS18B20_PIN);
DallasTemperature g_dallas(&g_oneWire);
bool              g_ready = false;
unsigned int      g_fail_count = 0;

} // namespace

namespace SensorsDs18b20 {

bool begin() {
    if (g_ready) {
        return true;
    }

    g_dallas.begin();
    g_dallas.setResolution(DS18B20_RESOLUTION_BITS);

    const uint8_t count = g_dallas.getDeviceCount();
    if (count == 0) {
        if ((g_fail_count++ % 10) == 0) {
            Serial.printf("[ERROR] [%lus] DS18B20 not found on GPIO %d "
                          "(check 4.7k pull-up to 3.3V and data wire)\n",
                          (unsigned long)(millis() / 1000UL), DS18B20_PIN);
        }
        g_ready = false;
        return false;
    }

    Serial.printf("[INFO] [%lus] DS18B20 initialised on GPIO %d (%u device%s)\n",
                  (unsigned long)(millis() / 1000UL),
                  DS18B20_PIN, count, count == 1 ? "" : "s");
    g_ready = true;
    return true;
}

bool isReady() { return g_ready; }

Ds18b20Reading read() {
    Ds18b20Reading r{NAN, false};

    if (!g_ready) {
        if (!begin()) {
            return r;
        }
    }

    g_dallas.requestTemperatures();
    const float t = g_dallas.getTempCByIndex(0);

    if (isnan(t) || t == DEVICE_DISCONNECTED_C) {
        // Mark not-ready so begin() will be re-tried on the next read.
        g_ready = false;
        return r;
    }

    r.temperature_c = t;
    r.ok = true;
    return r;
}

} // namespace SensorsDs18b20

#endif // USE_DUMMY_SENSORS
