#include "mqtt.h"

#include <WiFi.h>
#include <PubSubClient.h>
#include <string.h>

#include "config.h"
#include "secrets.h"
#include "network.h"

// =============================================================================
// MQTT client wrapper around PubSubClient.
//
// Note on QoS: PubSubClient only supports MQTT QoS 0 (fire-and-forget).
// At-least-once semantics are achieved at the application layer by the M7 ring
// buffer + the bool return of publish() — failed publishes are re-queued.
// =============================================================================

namespace {

WiFiClient    g_wifi;
PubSubClient  g_mqtt(g_wifi);

MqttClient::State g_state = MqttClient::State::Disconnected;
unsigned long g_next_attempt_ms    = 0;
unsigned long g_current_backoff_ms = RECONNECT_BACKOFF_MIN_MS;

void log(const char* level, const char* fmt, ...) {
    char msg[160];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof(msg), fmt, ap);
    va_end(ap);
    Serial.printf("[%s] [%lus] %s\n", level,
                  (unsigned long)(millis() / 1000UL), msg);
}

const char* connStateText(int s) {
    switch (s) {
        case -4: return "MQTT_CONNECTION_TIMEOUT";
        case -3: return "MQTT_CONNECTION_LOST";
        case -2: return "MQTT_CONNECT_FAILED (TCP)";
        case -1: return "MQTT_DISCONNECTED";
        case  0: return "MQTT_CONNECTED";
        case  1: return "MQTT_CONNECT_BAD_PROTOCOL";
        case  2: return "MQTT_CONNECT_BAD_CLIENT_ID";
        case  3: return "MQTT_CONNECT_UNAVAILABLE";
        case  4: return "MQTT_CONNECT_BAD_CREDENTIALS";
        case  5: return "MQTT_CONNECT_UNAUTHORIZED";
        default: return "MQTT_UNKNOWN";
    }
}

void scheduleReconnect() {
    g_next_attempt_ms = millis() + g_current_backoff_ms;
    log("WARN", "MQTT reconnect scheduled in %lu ms (backoff)",
        g_current_backoff_ms);
    g_current_backoff_ms = min<unsigned long>(g_current_backoff_ms * 2UL,
                                              RECONNECT_BACKOFF_MAX_MS);
}

bool tryConnect() {
    log("INFO", "MQTT connecting to %s:%u as \"%s\" ...",
        MQTT_BROKER_HOST, (unsigned)MQTT_BROKER_PORT, DEVICE_ID);

    const char* user = (MQTT_USERNAME[0] != '\0') ? MQTT_USERNAME : nullptr;
    const char* pass = (MQTT_PASSWORD[0] != '\0') ? MQTT_PASSWORD : nullptr;

    const bool ok = (user == nullptr)
        ? g_mqtt.connect(DEVICE_ID)
        : g_mqtt.connect(DEVICE_ID, user, pass);

    if (!ok) {
        log("WARN", "MQTT connect failed: %s (state=%d)",
            connStateText(g_mqtt.state()), g_mqtt.state());
    }
    return ok;
}

} // namespace

namespace MqttClient {

void begin() {
    g_mqtt.setServer(MQTT_BROKER_HOST, MQTT_BROKER_PORT);
    g_mqtt.setBufferSize(MQTT_TX_BUFFER_SIZE);
    g_mqtt.setKeepAlive(MQTT_KEEPALIVE_S);
    g_mqtt.setSocketTimeout(MQTT_SOCKET_TIMEOUT_S);
    g_state = State::Disconnected;
    g_next_attempt_ms = millis();
    g_current_backoff_ms = RECONNECT_BACKOFF_MIN_MS;
}

void loop() {
    // Wi-Fi must be up first; without it there's nothing useful to do.
    if (!Network::isConnected()) {
        if (g_state != State::Disconnected) {
            log("WARN", "Wi-Fi down — MQTT marking disconnected");
            g_state = State::Disconnected;
            g_next_attempt_ms = millis(); // attempt as soon as Wi-Fi returns
            g_current_backoff_ms = RECONNECT_BACKOFF_MIN_MS;
        }
        return;
    }

    // Already connected: keep the loop alive and detect drops.
    if (g_mqtt.connected()) {
        g_state = State::Connected;
        g_mqtt.loop();
        return;
    }

    // We were connected but PubSubClient says we're not — log the transition.
    if (g_state == State::Connected) {
        log("WARN", "MQTT link dropped: %s", connStateText(g_mqtt.state()));
        g_state = State::Disconnected;
        scheduleReconnect();
        return;
    }

    // Not connected and waiting for the next attempt window.
    if ((long)(millis() - g_next_attempt_ms) < 0) {
        return;
    }

    g_state = State::Connecting;
    if (tryConnect()) {
        g_state = State::Connected;
        g_current_backoff_ms = RECONNECT_BACKOFF_MIN_MS;
        log("INFO", "MQTT connected to %s:%u",
            MQTT_BROKER_HOST, (unsigned)MQTT_BROKER_PORT);
    } else {
        g_state = State::Disconnected;
        scheduleReconnect();
    }
}

State state() { return g_state; }

bool isConnected() { return g_state == State::Connected && g_mqtt.connected(); }

bool publish(const char* payload, size_t len) {
    if (!isConnected()) return false;
    if (payload == nullptr || len == 0) return false;
    return g_mqtt.publish(MQTT_TOPIC_READINGS,
                          reinterpret_cast<const uint8_t*>(payload),
                          (unsigned int)len,
                          MQTT_RETAINED);
}

} // namespace MqttClient
