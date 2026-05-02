#include <Arduino.h>

#include "config.h"
#include "sensors_bme280.h"
#include "sensors_ds18b20.h"

static unsigned long lastHeartbeatMs = 0;
static unsigned long lastSensorReadMs = 0;

static inline unsigned long uptimeS() {
    return (unsigned long)(millis() / 1000UL);
}

static void logHeartbeat() {
    Serial.printf("[INFO] [%lus] Booted fw v%s\n", uptimeS(), FW_VERSION);
}

static void readAndPrintSensors() {
    const Bme280Reading b = SensorsBme280::read();
    const Ds18b20Reading d = SensorsDs18b20::read();

    if (!b.ok) {
        Serial.printf("[WARN] [%lus] BME280 read failed (sensor not ready or NaN)\n",
                      uptimeS());
    } else {
        Serial.printf("[INFO] [%lus] BME280 : T=%.2f C  H=%.2f %%  P=%.2f hPa\n",
                      uptimeS(), b.temperature_c, b.humidity_pct, b.pressure_hpa);
    }

    if (!d.ok) {
        Serial.printf("[WARN] [%lus] DS18B20 read failed (disconnected or NaN)\n",
                      uptimeS());
    } else {
        Serial.printf("[INFO] [%lus] DS18B20: T=%.2f C\n",
                      uptimeS(), d.temperature_c);
    }
}

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(200); // brief settle so the first message isn't lost on USB CDC enumeration
    Serial.println();
    Serial.println(F("==============================================="));
    Serial.println(F(" Re-Tech Fusion Node — boot"));
    Serial.println(F("==============================================="));
#ifdef USE_DUMMY_SENSORS
    Serial.println(F("[INFO] Build flag USE_DUMMY_SENSORS=1 — sensors stubbed"));
#endif

    SensorsBme280::begin();   // failures are logged inside; we keep running
    SensorsDs18b20::begin();
}

void loop() {
    const unsigned long now = millis();

    if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
        lastHeartbeatMs = now;
        logHeartbeat();
    }

    if (now - lastSensorReadMs >= SENSOR_READ_INTERVAL_MS) {
        lastSensorReadMs = now;
        readAndPrintSensors();
    }
}
