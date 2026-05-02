#include "network.h"

#include <WiFi.h>
#include <time.h>

#include "config.h"
#include "secrets.h"

namespace {

Network::State g_state = Network::State::Disconnected;

unsigned long g_attempt_started_ms = 0;
unsigned long g_next_attempt_ms    = 0;
unsigned long g_last_poll_ms       = 0;
unsigned long g_current_backoff_ms = RECONNECT_BACKOFF_MIN_MS;

bool g_ntp_started = false;

void logTagged(const char* level, const char* fmt, ...) {
    char msg[160];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof(msg), fmt, ap);
    va_end(ap);
    Serial.printf("[%s] [%lus] %s\n", level,
                  (unsigned long)(millis() / 1000UL), msg);
}

void scheduleReconnect() {
    g_next_attempt_ms = millis() + g_current_backoff_ms;
    logTagged("WARN", "Wi-Fi reconnect scheduled in %lu ms (backoff)", g_current_backoff_ms);
    // Double the backoff for the *next* failure, capped.
    g_current_backoff_ms = min<unsigned long>(g_current_backoff_ms * 2UL,
                                              RECONNECT_BACKOFF_MAX_MS);
}

void startConnectAttempt() {
    logTagged("INFO", "Wi-Fi connecting to SSID \"%s\" ...", WIFI_SSID);
    WiFi.disconnect(true, true);  // clear any stale config
    delay(10);
    WiFi.mode(WIFI_STA);
    WiFi.setHostname(WIFI_HOSTNAME);
    WiFi.setAutoReconnect(false); // we drive reconnect ourselves
    WiFi.persistent(false);       // don't write creds to flash on every begin
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    g_state = Network::State::Connecting;
    g_attempt_started_ms = millis();
}

void onConnected() {
    g_state = Network::State::Connected;
    g_current_backoff_ms = RECONNECT_BACKOFF_MIN_MS;  // reset for next time
    logTagged("INFO", "Wi-Fi connected — IP=%s  RSSI=%d dBm",
              WiFi.localIP().toString().c_str(),
              WiFi.RSSI());

    if (!g_ntp_started) {
        configTime(NTP_TZ_OFFSET_S, 0, NTP_SERVER_PRIMARY, NTP_SERVER_SECONDARY);
        logTagged("INFO", "NTP sync started (%s, %s)",
                  NTP_SERVER_PRIMARY, NTP_SERVER_SECONDARY);
        g_ntp_started = true;
    }
}

void onDisconnected(const char* reason) {
    if (g_state == Network::State::Connected) {
        logTagged("WARN", "Wi-Fi link dropped (%s)", reason);
    } else {
        logTagged("WARN", "Wi-Fi connect failed (%s)", reason);
    }
    g_state = Network::State::Disconnected;
    scheduleReconnect();
}

} // namespace

namespace Network {

void begin() {
    WiFi.mode(WIFI_STA);
    g_current_backoff_ms = RECONNECT_BACKOFF_MIN_MS;
    g_next_attempt_ms = millis();   // attempt immediately
}

void loop() {
    const unsigned long now = millis();
    if (now - g_last_poll_ms < WIFI_POLL_INTERVAL_MS) {
        return;
    }
    g_last_poll_ms = now;

    switch (g_state) {
        case State::Disconnected:
            if ((long)(now - g_next_attempt_ms) >= 0) {
                startConnectAttempt();
            }
            break;

        case State::Connecting:
            if (WiFi.status() == WL_CONNECTED) {
                onConnected();
            } else if (now - g_attempt_started_ms >= WIFI_CONNECT_TIMEOUT_MS) {
                onDisconnected("attempt timed out");
            }
            break;

        case State::Connected:
            if (WiFi.status() != WL_CONNECTED) {
                onDisconnected("link lost");
            }
            break;
    }
}

State state() { return g_state; }

bool isConnected() { return g_state == State::Connected; }

int rssiDbm() {
    return isConnected() ? (int)WiFi.RSSI() : 0;
}

const char* localIpStr() {
    static char buf[20];
    if (!isConnected()) {
        return "0.0.0.0";
    }
    snprintf(buf, sizeof(buf), "%s", WiFi.localIP().toString().c_str());
    return buf;
}

} // namespace Network
