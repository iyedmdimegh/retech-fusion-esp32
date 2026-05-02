#pragma once

#include <Arduino.h>

struct Acs712Reading {
    float current_a;   // signed; positive = IP+ to IP- direction. NAN on failure.
    bool  ok;
};

namespace SensorsAcs712 {

// Initialise the ADC pin and run a one-shot zero-offset calibration. The
// load MUST be off (motor not turning) at the moment begin() is called.
bool begin();

bool isReady();

// Take a noise-averaged reading and convert to amps using the configured
// sensitivity, divider ratio, and calibrated zero offset.
Acs712Reading read();

// Re-sample the zero-offset NOW. Call this whenever you can guarantee the
// load is off — e.g. before you start the motor or via the 'c' Serial
// command. Without periodic recalibration, temperature drift on the IC
// will introduce a slow bias.
void calibrateZero();

// The current zero offset (in mV at the ACS712 OUT pin), exposed for logs.
float zeroOffsetMv();

} // namespace SensorsAcs712
