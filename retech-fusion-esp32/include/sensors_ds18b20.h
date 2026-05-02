#pragma once

#include <Arduino.h>

struct Ds18b20Reading {
    float temperature_c; // NAN on failure
    bool  ok;            // false if sensor not initialised, disconnected, or NaN
};

namespace SensorsDs18b20 {

// Initialise OneWire on DS18B20_PIN and the DallasTemperature driver.
// Returns true on success. Safe to retry: subsequent calls re-attempt init
// if the previous attempt found no devices.
bool begin();

// Returns true once begin() has succeeded at least once.
bool isReady();

// Reads the first DS18B20 on the bus.
// On any failure (no device, NaN, DEVICE_DISCONNECTED_C), Reading.ok == false
// and temperature_c is NAN. Never returns -127 / -999 sentinels.
Ds18b20Reading read();

} // namespace SensorsDs18b20
