#include "schema.h"

#include <ArduinoJson.h>
#include <time.h>
#include <math.h>

#include "config.h"

namespace {

// Treat any wallclock < 2023-11-14 as "not yet NTP-synced" — at that point
// the on-board RTC is just running off boot epoch and we should fall back to
// the placeholder format.
constexpr time_t MIN_VALID_UNIX_TIME = 1700000000;

void appendReading(JsonArray& arr,
                   const char* type,
                   float value,
                   const char* unit,
                   const char* sensor) {
    JsonObject o = arr.createNestedObject();
    o["type"]   = type;
    o["value"]  = value;
    o["unit"]   = unit;
    o["sensor"] = sensor;
}

} // namespace

namespace Schema {

void formatTimestamp(char* buf, size_t n) {
    if (n == 0) return;

    const time_t now = time(nullptr);
    if (now >= MIN_VALID_UNIX_TIME) {
        struct tm tm_utc;
        gmtime_r(&now, &tm_utc);
        strftime(buf, n, "%Y-%m-%dT%H:%M:%SZ", &tm_utc);
        return;
    }

    // Not yet synced — placeholder driven by uptime so the schema is still
    // well-formed and obviously non-real.
    const unsigned long up_s = (unsigned long)(millis() / 1000UL);
    snprintf(buf, n, "1970-01-01T%02lu:%02lu:%02luZ",
             (up_s / 3600UL) % 24UL,
             (up_s / 60UL)   % 60UL,
              up_s            % 60UL);
}

size_t buildPayload(char* out, size_t out_size,
                    const Bme280Reading& bme,
                    const Ds18b20Reading& ds,
                    int rssi_dbm,
                    unsigned long uptime_s) {
    if (out == nullptr || out_size == 0) return 0;

    StaticJsonDocument<PAYLOAD_BUFFER_SIZE> doc;

    doc["device_id"] = DEVICE_ID;
    doc["site"]      = SITE_ID;

    char ts[24];
    formatTimestamp(ts, sizeof(ts));
    doc["timestamp"] = ts;

    JsonArray readings = doc.createNestedArray("readings");

    bool any_dropped = false;

    if (ds.ok && !isnan(ds.temperature_c)) {
        appendReading(readings, "temperature", ds.temperature_c, "celsius", "ds18b20");
    } else {
        any_dropped = true;
    }

    if (bme.ok && !isnan(bme.temperature_c)) {
        appendReading(readings, "temperature", bme.temperature_c, "celsius", "bme280");
    } else {
        any_dropped = true;
    }

    if (bme.ok && !isnan(bme.humidity_pct)) {
        appendReading(readings, "humidity", bme.humidity_pct, "percent", "bme280");
    } else {
        any_dropped = true;
    }

    if (bme.ok && !isnan(bme.pressure_hpa)) {
        appendReading(readings, "pressure", bme.pressure_hpa, "hPa", "bme280");
    } else {
        any_dropped = true;
    }

    doc["status"]     = any_dropped ? "invalid_reading" : "ok";
    doc["rssi"]       = rssi_dbm;
    doc["uptime_s"]   = uptime_s;
    doc["fw_version"] = FW_VERSION;

    return serializeJson(doc, out, out_size);
}

} // namespace Schema
