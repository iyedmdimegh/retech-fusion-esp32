#include <Arduino.h>
#include "config.h"

static unsigned long lastHeartbeatMs = 0;

static void logBoot() {
    Serial.printf("[INFO] [%lus] Booted fw v%s\n",
                  (unsigned long)(millis() / 1000UL), FW_VERSION);
}

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(200); // brief settle so the first message isn't lost on USB CDC enumeration
    Serial.println();
    Serial.println(F("==============================================="));
    Serial.println(F(" Re-Tech Fusion Node — boot"));
    Serial.println(F("==============================================="));
}

void loop() {
    const unsigned long now = millis();
    if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
        lastHeartbeatMs = now;
        logBoot();
    }
}
