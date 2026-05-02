# Re·Tech Fusion — Industrial IoT Node

> Re·Tech Fusion Hackathon — INSAT, University of Carthage

Multi-sensor IoT node that collects environmental data, validates readings, and streams them as JSON over MQTT with offline buffering.

---

## Current Prototype (Proof of Concept)

This repo is the **hackathon PoC** running on an ESP32 DevKit with breakout sensors. It validates the full firmware pipeline before migrating to the production PCB.

### Sensors

| Sensor | Reads | Interface |
|--------|-------|-----------|
| **BME280** (auto-fallback to BMP280) | Temperature · Humidity · Pressure | I2C `0x76` |
| **DS18B20** | Temperature | OneWire GPIO 4 |

Both temperature sources enable cross-sensor drift detection (±2 °C threshold).

### How It Works

1. Reads sensors every **1 s**, validates against physical ranges.
2. Builds a JSON payload every **10 s** with NTP-synced UTC timestamp.
3. Queues into a **100-message ring buffer** (survives Wi-Fi/MQTT outages).
4. Drains buffer to MQTT broker, auto-reconnects with exponential backoff.

### Payload Example

Topic: `retech/devices/esp32_node_01/readings`

```json
{
  "device_id": "esp32_node_01",
  "site": "insat_lab_zone_a",
  "timestamp": "2026-05-02T13:45:00Z",
  "readings": [
    { "type": "temperature", "value": 23.5, "unit": "celsius", "sensor": "ds18b20" },
    { "type": "temperature", "value": 23.7, "unit": "celsius", "sensor": "bme280" },
    { "type": "humidity",    "value": 45.2, "unit": "percent", "sensor": "bme280" },
    { "type": "pressure",    "value": 1013.25, "unit": "hPa",  "sensor": "bme280" }
  ],
  "status": "ok",
  "rssi": -55,
  "uptime_s": 3600,
  "fw_version": "1.0.0"
}
```

---

## Target Product — Custom Industrial PCB

The production board is built around the **ESP32-S3/C6** with industrial-grade power, isolation, and multi-protocol connectivity. Sensors and interfaces will be refined in upcoming phases.

![PCB 3D render](docs/images/pcb_3d_render.png)

![PCB layout](docs/images/pcb_layout.png)

| Area | Capabilities |
|------|-------------|
| **Sensors** | Environmental, inertial (vibrations), acoustic (leak detection), 4–20 mA loop |
| **Comms** | Wi-Fi · BLE · RS485 · CAN (TJA1040) · RS232 · LoRaWAN (RAK4270) · NB-IoT/GSM (SIM7022/SIM800C) |
| **Power** | 5–30V DC input, 3.3V regulation, OVP, reverse polarity protection, deep sleep, BMS-ready |
| **Isolation** | Galvanic barriers on RS485 and field inputs (24V) |

---

## Quick Start

```bash
git clone https://github.com/iyedmdimegh/retech-fusion-esp32.git
cd retech-fusion-esp32
cp include/secrets.h.example include/secrets.h   # fill in Wi-Fi & MQTT creds
pio run -t upload
pio device monitor
```

Start broker: `mosquitto -c tools/mosquitto.conf -v`  
Verify: `mosquitto_sub -h localhost -t "retech/devices/esp32_node_01/readings"`

> **No hardware?** Uncomment `-D USE_DUMMY_SENSORS=1` in `platformio.ini` to run with stubbed sensor values.

---

## Project Structure

```
include/          Config, sensor/network/MQTT headers, secrets template
src/              Firmware — main loop, sensor drivers, MQTT, ring buffer, JSON schema
tools/            Mosquitto broker config
docs/images/      PCB renders
```

---

*Built for the Re·Tech Fusion Hackathon — INSAT, University of Carthage*
