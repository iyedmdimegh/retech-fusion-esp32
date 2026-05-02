#include <Arduino.h>

#include "config.h"
#include "sensors_bme280.h"
#include "sensors_ds18b20.h"
#include "schema.h"
#include "network.h"

static unsigned long lastHeartbeatMs  = 0;
static unsigned long lastSensorReadMs = 0;
static unsigned long lastPublishMs    = 0;

// Latest sensor snapshot — refreshed at SENSOR_READ_INTERVAL_MS, consumed at
// PUBLISH_INTERVAL_MS. Marked .ok=false until the first successful read.
static Bme280Reading  s_bme{NAN, NAN, NAN, false};
static Ds18b20Reading s_ds {NAN, false};

static inline unsigned long uptimeS() {
    return (unsigned long)(millis() / 1000UL);
}

static void logHeartbeat() {
    Serial.printf("[INFO] [%lus] Booted fw v%s\n", uptimeS(), FW_VERSION);
}

static void readAndPrintSensors() {
    s_bme = SensorsBme280::read();
    s_ds  = SensorsDs18b20::read();

    if (!s_bme.ok) {
        Serial.printf("[WARN] [%lus] BME280 read failed (sensor not ready or NaN)\n",
                      uptimeS());
    } else {
        Serial.printf("[INFO] [%lus] BME280 : T=%.2f C  H=%.2f %%  P=%.2f hPa\n",
                      uptimeS(), s_bme.temperature_c, s_bme.humidity_pct, s_bme.pressure_hpa);
    }

    if (!s_ds.ok) {
        Serial.printf("[WARN] [%lus] DS18B20 read failed (disconnected or NaN)\n",
                      uptimeS());
    } else {
        Serial.printf("[INFO] [%lus] DS18B20: T=%.2f C\n",
                      uptimeS(), s_ds.temperature_c);
    }
}

static void buildAndPrintPayload() {
    char buf[Schema::PAYLOAD_BUFFER_SIZE];
    const size_t n = Schema::buildPayload(buf, sizeof(buf),
                                          s_bme, s_ds,
                                          Network::rssiDbm(),
                                          uptimeS());
    if (n == 0) {
        Serial.printf("[ERROR] [%lus] schema buildPayload returned 0\n", uptimeS());
        return;
    }
    Serial.printf("[JSON] [%lus] %s\n", uptimeS(), buf);
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
    Network::begin();
}

void loop() {
    Network::loop();

    const unsigned long now = millis();

    if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
        lastHeartbeatMs = now;
        logHeartbeat();
    }

    if (now - lastSensorReadMs >= SENSOR_READ_INTERVAL_MS) {
        lastSensorReadMs = now;
        readAndPrintSensors();
    }

    if (now - lastPublishMs >= PUBLISH_INTERVAL_MS) {
        lastPublishMs = now;
        buildAndPrintPayload();
    }
}
