#pragma once

#include <Arduino.h>
#include <stddef.h>
#include <stdint.h>

namespace MqttClient {

enum class State : uint8_t {
    Disconnected,
    Connecting,
    Connected
};

void  begin();
void  loop();
State state();
bool  isConnected();

// Publish a JSON payload to the configured topic. Returns true on broker
// acceptance. Caller is responsible for not calling when isConnected()==false
// (or for tolerating the false return when offline). The M7 ring buffer will
// wrap this call to add at-least-once delivery semantics.
bool publish(const char* payload, size_t len);

} // namespace MqttClient
