#pragma once

#include <Arduino.h>

struct Bme280Reading {
    float temperature_c; // NAN on failure
    float humidity_pct;  // NAN on failure OR when has_humidity == false (BMP280)
    float pressure_hpa;  // NAN on failure
    bool  ok;            // false if sensor not initialised or read failed
    bool  has_humidity;  // true on genuine BME280, false on BMP280 (no hum sensor)
};

namespace SensorsBme280 {

// Initialise I2C (custom SDA/SCL pins from config.h) and probe for either a
// genuine BME280 or a BMP280 fallback. Returns true on success. Safe to
// retry: subsequent calls will re-attempt init if the previous attempt failed.
bool begin();

// Returns true once begin() has succeeded at least once.
bool isReady();

// Read temperature (C), humidity (%), pressure (hPa).
// On any failure (sensor not ready, NaN from driver), Reading.ok == false and
// the float fields are set to NAN. Never returns -999 or other sentinels.
// On BMP280 the humidity field is always NAN with has_humidity == false.
Bme280Reading read();

// Returns "bme280" or "bmp280" depending on which chip was detected, or
// "none" before begin() succeeds. Used in the JSON payload's "sensor" field.
const char* sensorName();

} // namespace SensorsBme280
