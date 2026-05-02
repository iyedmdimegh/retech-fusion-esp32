#pragma once

#include <Arduino.h>

struct Bme280Reading {
    float temperature_c; // NAN on failure
    float humidity_pct;  // NAN on failure
    float pressure_hpa;  // NAN on failure
    bool  ok;            // false if sensor not initialised or read failed
};

namespace SensorsBme280 {

// Initialise I2C (custom SDA/SCL pins from config.h) and the BME280.
// Returns true on success. Safe to retry: subsequent calls will re-attempt init
// if the previous attempt failed.
bool begin();

// Returns true once begin() has succeeded at least once.
bool isReady();

// Read temperature (C), humidity (%), pressure (hPa).
// On any failure (sensor not ready, NaN from driver), Reading.ok == false and
// the float fields are set to NAN. Never returns -999 or other sentinels.
Bme280Reading read();

} // namespace SensorsBme280
