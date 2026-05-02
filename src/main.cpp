#include <Arduino.h>

#include "config.h"
#include "sensors_bme280.h"
#include "sensors_ds18b20.h"
#include "schema.h"
#include "network.h"
#include "mqtt.h"
#include "buffer.h"

// How many buffered messages to drain per pass through loop(). Keeps the
// main loop responsive while still flushing fast enough to clear a 100-deep
// backlog in well under one publish interval.
static constexpr size_t MAX_DRAIN_PER_PASS = 8;

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

// Build a payload from the latest sensor snapshot and enqueue it. The drainer
// (drainBufferIfPossible) does the actual MQTT publish — that way the offline
// and online paths share the same code, and ordering is preserved across
// reconnects.
static void buildAndQueuePayload() {
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

    const size_t before = MsgBuffer::size();
    if (!MsgBuffer::push(buf, n)) {
        Serial.printf("[ERROR] [%lus] payload (%u B) did not fit in ring buffer\n",
                      uptimeS(), (unsigned)n);
        return;
    }

    if (MsgBuffer::isFull()) {
        Serial.printf("[WARN] [%lus] ring buffer at capacity (%u/%u, dropped %u total)\n",
                      uptimeS(),
                      (unsigned)MsgBuffer::size(),
                      (unsigned)MsgBuffer::capacity(),
                      (unsigned)MsgBuffer::dropped());
    } else if (!MqttClient::isConnected()) {
        Serial.printf("[INFO] [%lus] queued offline (queue=%u/%u)\n",
                      uptimeS(),
                      (unsigned)MsgBuffer::size(),
                      (unsigned)MsgBuffer::capacity());
    }
    (void)before;
}

static void drainBufferIfPossible() {
    if (!MqttClient::isConnected()) return;
    if (MsgBuffer::isEmpty())        return;

    size_t drained = 0;
    while (drained < MAX_DRAIN_PER_PASS && !MsgBuffer::isEmpty()) {
        const char* p = nullptr;
        size_t      l = 0;
        if (!MsgBuffer::peekOldest(&p, &l)) break;

        if (!MqttClient::publish(p, l)) {
            // Likely a TCP / broker hiccup. Stop the drain pass and let the
            // MQTT state machine reconnect — we'll retry on the next loop.
            Serial.printf("[WARN] [%lus] drain publish failed — pausing (queue=%u)\n",
                          uptimeS(), (unsigned)MsgBuffer::size());
            break;
        }

        MsgBuffer::popOldest();
        drained++;
        Serial.printf("[INFO] [%lus] published %u B (queue=%u/%u)\n",
                      uptimeS(), (unsigned)l,
                      (unsigned)MsgBuffer::size(),
                      (unsigned)MsgBuffer::capacity());
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
    MsgBuffer::begin();
    Network::begin();
    MqttClient::begin();
}

void loop() {
    Network::loop();
    MqttClient::loop();

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
        buildAndQueuePayload();
    }

    // Drain after queuing so a fresh sample can also go out this loop pass
    // when MQTT is up and the queue was already empty.
    drainBufferIfPossible();
}
