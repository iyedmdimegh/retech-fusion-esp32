#pragma once

#include <Arduino.h>
#include <stdint.h>

namespace Network {

enum class State : uint8_t {
    Disconnected,
    Connecting,
    Connected
};

// Initialise Wi-Fi in STA mode and kick off the first connection attempt.
// Non-blocking: actual connection happens in loop().
void begin();

// Drive the connection state machine and reconnect logic.
// Must be called every iteration of the main loop.
void loop();

State state();
bool  isConnected();

// RSSI in dBm. Returns 0 when not connected (matches schema's pre-Wi-Fi value).
int rssiDbm();

// Local IP as a printable string ("0.0.0.0" if not connected).
const char* localIpStr();

} // namespace Network
