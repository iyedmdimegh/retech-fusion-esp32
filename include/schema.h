#pragma once

#include <Arduino.h>
#include <stddef.h>

#include "sensors_bme280.h"
#include "sensors_ds18b20.h"
#include "sensors_acs712.h"

namespace Schema {

// Largest expected serialized payload, with comfortable headroom.
// Canonical payload (5 readings + drift alert + metadata) measures ~430 bytes.
constexpr size_t PAYLOAD_BUFFER_SIZE = 640;

// Format the current UTC timestamp into 'buf' as ISO-8601 ("...Z").
// If the system clock has not yet been NTP-synced (we don't have Wi-Fi until
// M5), emits a placeholder of the form "1970-01-01TXX:XX:XXZ" derived from
// uptime so the schema stays well-formed.
void formatTimestamp(char* buf, size_t n);

// Build the canonical retech payload as JSON into 'out'.
// Returns the number of bytes written (excluding the trailing NUL), or 0 on
// failure.
size_t buildPayload(char* out, size_t out_size,
                    const Bme280Reading& bme,
                    const Ds18b20Reading& ds,
                    const Acs712Reading& acs,
                    int rssi_dbm,
                    unsigned long uptime_s);

} // namespace Schema
