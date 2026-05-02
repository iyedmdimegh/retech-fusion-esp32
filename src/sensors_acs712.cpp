#include "sensors_acs712.h"

#include <math.h>

#include "config.h"

// =============================================================================
// Dummy-mode stub (compile-time selected via -D USE_DUMMY_SENSORS=1).
// Returns a constant idle current so the schema demo stays self-contained.
// =============================================================================
#ifdef USE_DUMMY_SENSORS

namespace {
bool g_ready = false;
constexpr float DUMMY_CURRENT_A = 0.42f;
}

namespace SensorsAcs712 {

bool begin() {
    if (!g_ready) {
        Serial.printf("[INFO] [%lus] ACS712 dummy mode — returning %.2f A\n",
                      (unsigned long)(millis() / 1000UL), DUMMY_CURRENT_A);
        g_ready = true;
    }
    return true;
}

bool isReady() { return g_ready; }

Acs712Reading read() {
    if (!g_ready) begin();
    return {DUMMY_CURRENT_A, true};
}

void  calibrateZero() {}                   // no-op in dummy mode
float zeroOffsetMv() { return ACS712_NOMINAL_ZERO_MV; }

} // namespace SensorsAcs712

#else // ============================ Real ADC path ============================

namespace {

bool  g_ready          = false;
float g_zero_offset_mv = ACS712_NOMINAL_ZERO_MV;

float averageMillivolts(uint16_t samples) {
    uint32_t sum = 0;
    for (uint16_t i = 0; i < samples; ++i) {
        sum += analogReadMilliVolts(ACS712_PIN);
    }
    return (float)sum / (float)samples;
}

} // namespace

namespace SensorsAcs712 {

bool begin() {
    if (g_ready) return true;

    // 11 dB attenuation gives the ESP32 ADC its full ~0–3.3 V input range.
    analogSetPinAttenuation(ACS712_PIN, ADC_11db);
    analogReadResolution(12);

    calibrateZero();
    g_ready = true;

    Serial.printf("[INFO] [%lus] ACS712 initialised on GPIO %d "
                  "(zero=%.1f mV, sens=%.1f mV/A, divider=%.4f)\n",
                  (unsigned long)(millis() / 1000UL),
                  ACS712_PIN,
                  g_zero_offset_mv,
                  ACS712_SENSITIVITY_MV_PER_A,
                  ACS712_DIVIDER_RATIO);
    return true;
}

bool isReady() { return g_ready; }

void calibrateZero() {
    const float adc_mv    = averageMillivolts(ACS712_CALIBRATION_SAMPLES);
    const float sensor_mv = adc_mv / ACS712_DIVIDER_RATIO;
    g_zero_offset_mv = sensor_mv;
    Serial.printf("[INFO] [%lus] ACS712 zero recalibrated: ADC=%.1f mV "
                  "→ sensor=%.1f mV (expected ~%.0f mV)\n",
                  (unsigned long)(millis() / 1000UL),
                  adc_mv, sensor_mv, ACS712_NOMINAL_ZERO_MV);
}

float zeroOffsetMv() { return g_zero_offset_mv; }

Acs712Reading read() {
    Acs712Reading r{NAN, false};
    if (!g_ready) {
        if (!begin()) return r;
    }

    const float adc_mv    = averageMillivolts(ACS712_SAMPLES_PER_READ);
    const float sensor_mv = adc_mv / ACS712_DIVIDER_RATIO;
    const float current_a = (sensor_mv - g_zero_offset_mv)
                          / ACS712_SENSITIVITY_MV_PER_A;

    r.current_a = current_a;
    r.ok = true;
    return r;
}

} // namespace SensorsAcs712

#endif // USE_DUMMY_SENSORS
