#include <Arduino.h>

#include "config.h"
#include "sensors_bme280.h"

static unsigned long lastHeartbeatMs = 0;
static unsigned long lastSensorReadMs = 0;

static inline unsigned long uptimeS() {
    return (unsigned long)(millis() / 1000UL);
}

static void logHeartbeat() {
    Serial.printf("[INFO] [%lus] Booted fw v%s\n", uptimeS(), FW_VERSION);
}

static void readAndPrintBme280() {
    const Bme280Reading r = SensorsBme280::read();
    if (!r.ok) {
        Serial.printf("[WARN] [%lus] BME280 read failed (sensor not ready or NaN)\n",
                      uptimeS());
        return;
    }
    Serial.printf("[INFO] [%lus] BME280: T=%.2f C  H=%.2f %%  P=%.2f hPa\n",
                  uptimeS(), r.temperature_c, r.humidity_pct, r.pressure_hpa);
}

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(200); // brief settle so the first message isn't lost on USB CDC enumeration
    Serial.println();
    Serial.println(F("==============================================="));
    Serial.println(F(" Re-Tech Fusion Node — boot"));
    Serial.println(F("==============================================="));

    SensorsBme280::begin(); // failure is logged inside; we keep running
}

void loop() {
    const unsigned long now = millis();

    if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
        lastHeartbeatMs = now;
        logHeartbeat();
    }

    if (now - lastSensorReadMs >= SENSOR_READ_INTERVAL_MS) {
        lastSensorReadMs = now;
        readAndPrintBme280();
    }
}
