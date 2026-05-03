# Re·Tech Fusion ESP32 Node — Technical Reference

This document is the deep technical reference for the firmware in this repo.
For the high-level pitch and quick start, see [README.md](../README.md).

> Re·Tech Fusion Hackathon — INSAT, University of Carthage. Part 1 of 3
> (firmware → ingestion pipeline → edge ML).

---

## Table of contents

1. [System overview](#1-system-overview)
2. [Hardware bill of materials](#2-hardware-bill-of-materials)
3. [Wiring](#3-wiring)
4. [Software setup](#4-software-setup)
5. [Build modes](#5-build-modes)
6. [Mosquitto broker setup](#6-mosquitto-broker-setup)
7. [JSON schema](#7-json-schema)
8. [Architecture](#8-architecture)
9. [Module map](#9-module-map)
10. [Resilience design](#10-resilience-design)
11. [Validation rules](#11-validation-rules)
12. [Serial command reference](#12-serial-command-reference)
13. [Sensor deep-dive](#13-sensor-deep-dive)
14. [Tested scenarios](#14-tested-scenarios)
15. [Known limitations](#15-known-limitations)
16. [Consuming the data from another app](#16-consuming-the-data-from-another-app)

---

## 1. System overview

The ESP32 reads three sensors, builds a JSON payload every 10 seconds, and
publishes it to an MQTT broker on the same LAN. The pipeline is fully
non-blocking and survives Wi-Fi or broker outages via a 100-deep RAM ring
buffer with at-least-once retry semantics.

```
DS18B20 ──┐
BMP/BME280┼──► sensor cache ──► schema (JSON) ──► ring buffer ──► MQTT ──► broker
ACS712 ───┘                                            ▲
                                                       │ retry on
                                                       │ reconnect
                                       network (Wi-Fi + NTP, exp. backoff)
```

**Key characteristics**

- 10 s publish cadence, QoS 0 over MQTT (PubSubClient limitation), with
  app-layer at-least-once via the ring buffer + publish-success retry.
- Wi-Fi & MQTT each have their own state machine and exponential backoff
  (1 → 2 → 4 → 8 → 16 → 32 → 60 s).
- Validation drops invalid readings and flips top-level `status` to
  `"invalid_reading"` — never emits `null` or `-999`.
- Cross-sensor capability detection: chips from the BMP/BME280 family are
  auto-detected at runtime; missing capabilities (e.g. humidity on a
  BMP280) are silently absent from the payload, not flagged as faults.

---

## 2. Hardware bill of materials

| Item | Qty | Notes |
|---|---|---|
| ESP32 dev board (`esp32dev`, WROOM-32 module) | 1 | USB programming, 3V3 + 5V/VIN rails |
| GY-BME280 / GY-BMP280 breakout (3.3 V) | 1 | I²C @ 0x76 |
| DS18B20 (TO-92) | 1 | 1-Wire |
| 4.7 kΩ resistor | 1 | DS18B20 data-line pull-up |
| ACS712 current sensor breakout (5A / 20A / 30A) | 1 | analog Hall-effect |
| 10 kΩ resistor | 1 | ACS712 OUT divider, top |
| 20 kΩ resistor (or 2× 10 kΩ in series) | 1 | ACS712 OUT divider, bottom |
| 1N4007 (or Schottky) diode | 1 | flyback across motor |
| Breadboard + jumper wires | — | |
| Optional: 5 V wall adapter or 4×AA pack | — | If the motor draws > 200 mA, USB VIN is unreliable. |

> ⚠ The BME280/BMP280 module is **3.3 V only**. Connecting VCC to 5 V will
> destroy the chip silently. Use the **3V3** pin on the ESP32.

---

## 3. Wiring

### Pinout table

| Function | ESP32 pin | Notes |
|---|---|---|
| BMP/BME280 VCC | `3V3` | not 5 V |
| BMP/BME280 GND | `GND` | |
| BMP/BME280 SDA | `GPIO 22` | (current bench wiring; canonical default is 21) |
| BMP/BME280 SCL | `GPIO 21` | (current bench wiring; canonical default is 22) |
| DS18B20 VDD | `3V3` | pin 3 |
| DS18B20 DQ | `GPIO 4` | pin 2, with 4.7 kΩ pull-up to 3V3 |
| DS18B20 GND | `GND` | pin 1 |
| ACS712 VCC | `5V` / `VIN` | datasheet requires 4.5–5.5 V |
| ACS712 GND | `GND` | common ground with ESP32 |
| ACS712 OUT | divider top | divider tap → `GPIO 33` |
| ACS712 IP+ | motor supply + | series with the load |
| ACS712 IP− | motor + terminal | |
| Motor − terminal | motor supply GND | also tied to ESP32 GND |

All pin assignments live in [`include/config.h`](../include/config.h).

### ASCII overview

```
         ESP32                            BMP/BME280
         ┌──────────────┐                ┌──────────────┐
         │          3V3 ├────────┬───────┤ VCC          │
         │          GND ├────────┼─┬─────┤ GND          │
         │       GPIO22 ├────────┼─┼─────┤ SDA          │
         │       GPIO21 ├────────┼─┼─────┤ SCL          │
         │              │        │ │     └──────────────┘
         │              │        │ │     DS18B20  (flat side facing you)
         │              │        │ ├───────────[ VDD pin 3 ]
         │              │        │ │  ┌─────────[ GND pin 1 ]
         │       GPIO 4 ├────────┼─┼──┤   ┌─────[ DQ  pin 2 ]
         │              │        │ │  │  ┌┴┐
         │              │        │ │  │  │ │ 4.7 kΩ pull-up
         │              │        │ │  │  └┬┘
         │              │        │ │  │   └─── DQ pulled HIGH to 3V3
         │              │        │ │  │
         │           5V ├────┐   │ │  │
         │              │    │   │ │  │     ACS712 module
         │              │    └───┼─┼──┼─────► VCC
         │              │        │ │  │      GND ◄────┘
         │              │        │ │  │      OUT ──┐
         │       GPIO33 ├────────┼─┼──┼───────┬────┘
         │              │        │ │  │      │
         │              │        │ │  │   [ 10 kΩ ]
         │              │        │ │  │      │
         │              │        │ │  │      ├──── ESP32 ADC
         │              │        │ │  │   [ 20 kΩ ]
         │              │        │ │  │      │
         └──────────────┘        └─┴──┴──────┴──── GND
```

> Per-sensor wiring details and the flyback-diode requirement are in
> [§13 Sensor deep-dive](#13-sensor-deep-dive).

---

## 4. Software setup

### Toolchain

- VS Code + PlatformIO IDE extension (PlatformIO Core ≥ 6).
- Open the repo folder; PlatformIO indexes and pulls libraries on first build.

### Pinned libraries ([`platformio.ini`](../platformio.ini))

| Library | Version |
|---|---|
| `paulstoffregen/OneWire` | `^2.3.8` |
| `milesburton/DallasTemperature` | `^3.11.0` |
| `adafruit/Adafruit BME280 Library` | `^2.2.4` |
| `adafruit/Adafruit BMP280 Library` | `^2.6.8` |
| `adafruit/Adafruit Unified Sensor` | `^1.1.14` |
| `adafruit/Adafruit BusIO` | `^1.16.1` |
| `bblanchon/ArduinoJson` | `^6.21.5` |
| `knolleary/PubSubClient` | `^2.8` |

### Secrets

Wi-Fi and broker credentials live in
[`include/secrets.h`](../include/secrets.h.example), which is gitignored.
Copy the template and edit:

```powershell
Copy-Item include/secrets.h.example include/secrets.h
```

```cpp
#define WIFI_SSID         "your-ssid"
#define WIFI_PASSWORD     "your-password"
#define MQTT_BROKER_HOST  "192.168.137.1"   // laptop IP on the ESP32's network
#define MQTT_BROKER_PORT  1883
#define MQTT_USERNAME     ""                // empty == anonymous
#define MQTT_PASSWORD     ""
```

### Build & flash

```powershell
pio run -t upload
pio device monitor -b 115200
```

Or use the PlatformIO sidebar in VS Code.

---

## 5. Build modes

The single configuration knob is `USE_DUMMY_SENSORS` in
[`platformio.ini`](../platformio.ini):

| Mode | Behaviour |
|---|---|
| `-D USE_DUMMY_SENSORS=1` (uncommented) | Sensor drivers return constants matching the schema example (no I²C / OneWire / ADC traffic). The full pipeline still runs end-to-end, ideal for laptop-only development. |
| Flag commented out (default) | Real driver paths compile in: I²C auto-detect for BME280/BMP280, OneWire for DS18B20, ADC1 for ACS712. |

The header API never changes — the build flag only swaps the `.cpp`
implementation under the same `begin / read / isReady` interface.

---

## 6. Mosquitto broker setup

### Windows install (one-time, admin PowerShell)

```powershell
winget install --id EclipseFoundation.Mosquitto -e --accept-source-agreements --accept-package-agreements
New-NetFirewallRule -DisplayName "Mosquitto MQTT 1883" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow
```

The installer also registers a Windows service that auto-starts on boot.
That service uses Mosquitto's locked-down default config (localhost-only,
auth required) and will hold port 1883, blocking your manual launch. Stop it
when you want to run the dev config:

```powershell
Stop-Service mosquitto
# Optional, to prevent it auto-starting in the future:
Set-Service mosquitto -StartupType Disabled
```

### Run with the dev config

[`tools/mosquitto.conf`](../tools/mosquitto.conf):

```
listener 1883 0.0.0.0
allow_anonymous true
```

In a regular PowerShell window in the project root:

```powershell
& 'C:\Program Files\mosquitto\mosquitto.exe' -c .\tools\mosquitto.conf -v
```

### Subscribe (verify reception)

```powershell
& 'C:\Program Files\mosquitto\mosquitto_sub.exe' -h 192.168.137.1 -t 'retech/devices/+/readings' -v
```

Replace the IP with whichever interface the ESP32 is on. For Windows Mobile
Hotspot, the host IP is typically `192.168.137.1`.

### Linux install

```bash
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
# Edit /etc/mosquitto/mosquitto.conf to add:
#   listener 1883 0.0.0.0
#   allow_anonymous true
sudo systemctl restart mosquitto
sudo ufw allow 1883/tcp
```

> ⚠ The dev config is **insecure by design** (anonymous + plaintext on
> `0.0.0.0`). Only use it on a private hackathon LAN / hotspot.

---

## 7. JSON schema

**Topic**: `retech/devices/{device_id}/readings`
(default `retech/devices/esp32_node_01/readings`)

**Retained**: false. **Cadence**: every 10 s.

### Canonical payload

```json
{
  "device_id": "esp32_node_01",
  "site": "insat_lab_zone_a",
  "timestamp": "2026-05-02T14:30:00Z",
  "readings": [
    {"type": "temperature", "value": 23.5,    "unit": "celsius", "sensor": "ds18b20"},
    {"type": "temperature", "value": 23.7,    "unit": "celsius", "sensor": "bme280"},
    {"type": "humidity",    "value": 45.2,    "unit": "percent", "sensor": "bme280"},
    {"type": "pressure",    "value": 1013.25, "unit": "hPa",     "sensor": "bme280"},
    {"type": "current",     "value": 0.42,    "unit": "ampere",  "sensor": "acs712"}
  ],
  "status": "ok",
  "rssi": -67,
  "uptime_s": 3600,
  "fw_version": "1.0.0"
}
```

### Field reference

| Field | Type | Notes |
|---|---|---|
| `device_id` | string | from `DEVICE_ID` in [`config.h`](../include/config.h) |
| `site` | string | from `SITE_ID` |
| `timestamp` | string (ISO-8601 UTC, `Z` suffix) | NTP-synced once Wi-Fi is up; placeholder `1970-01-01T...Z` until then |
| `readings[]` | array of objects | up to 5 entries (4 on BMP280: humidity is absent) |
| `readings[].type` | enum string | `temperature` / `humidity` / `pressure` / `current` |
| `readings[].value` | float | physical value in `unit` |
| `readings[].unit` | string | `celsius` / `percent` / `hPa` / `ampere` |
| `readings[].sensor` | string | `ds18b20` / `bme280` / `bmp280` / `acs712` |
| `status` | string | `"ok"` or `"invalid_reading"` |
| `rssi` | int | dBm, 0 when not connected |
| `uptime_s` | int | seconds since boot |
| `fw_version` | string | from `FW_VERSION` |

### Drop / fault rules

A reading is **dropped from the array** (never emitted as `null` or `-999`)
when:

- the sensor's `ok` flag is false,
- the value is `NaN`, **OR**
- the value is outside its validation range (see [§11](#11-validation-rules)).

When *anything* is dropped, top-level `status` becomes `"invalid_reading"`.

**Capability vs fault:** when the detected chip *does not provide* a
quantity (e.g. BMP280 has no humidity sensor), the corresponding reading is
silently absent — this is **not** a fault and `status` stays `"ok"`.

---

## 8. Architecture

```
                  ┌────────────────┐
                  │   main.cpp     │
                  │ 1 s: read+log  │
                  │ 10 s: publish  │
                  └───────┬────────┘
                          │
   ┌──────────────────────┼──────────────────────┐
   ▼                      ▼                      ▼
sensors_ds18b20    sensors_bme280         sensors_acs712
(OneWire)         (I²C, BME/BMP fallback) (ADC1 + averaging)
   │                      │                      │
   └──────────────────────┼──────────────────────┘
                          ▼
                  ┌──────────────────┐
                  │  schema (JSON)   │   build canonical payload
                  └────────┬─────────┘
                           ▼
                  ┌──────────────────┐
                  │   buffer (RAM)   │   100-deep ring, FIFO overflow
                  └────────┬─────────┘
                           ▼
                  ┌──────────────────┐      ┌──────────────────┐
                  │      mqtt        │◄─────┤     network      │
                  │  PubSubClient    │      │  Wi-Fi STA + NTP │
                  │  exp backoff     │      │  exp backoff     │
                  └────────┬─────────┘      └──────────────────┘
                           ▼
                       broker (LAN)
```

**Loop** (every iteration, no `delay()`):

1. `pumpSerial()` — process Serial commands.
2. `Network::loop()` — Wi-Fi state machine.
3. `MqttClient::loop()` — MQTT keep-alive + reconnect.
4. Time-based work:
   - 1 s: log heartbeat.
   - 1 s: read sensors → cache; apply fault injection if active.
   - 10 s: build payload → enqueue.
5. `drainBufferIfPossible()` — flush oldest-first when MQTT is up
   (≤ 8 messages per loop pass to keep responsive).

---

## 9. Module map

| File | Responsibility |
|---|---|
| [`include/config.h`](../include/config.h) | All pins, intervals, thresholds, ranges, ACS712 calibration constants |
| [`include/secrets.h`](../include/secrets.h.example) | Wi-Fi + broker credentials (gitignored) |
| [`sensors_bme280.{h,cpp}`](../src/sensors_bme280.cpp) | I²C driver with **BME280 / BMP280 auto-detect**, has-humidity flag, dynamic sensor name |
| [`sensors_ds18b20.{h,cpp}`](../src/sensors_ds18b20.cpp) | OneWire / Dallas wrapper, defensive against `DEVICE_DISCONNECTED_C` |
| [`sensors_acs712.{h,cpp}`](../src/sensors_acs712.cpp) | ADC1 sampler, voltage-divider math, zero-offset calibration |
| [`schema.{h,cpp}`](../src/schema.cpp) | ArduinoJson v6 payload builder, range validators, drop logic |
| [`network.{h,cpp}`](../src/network.cpp) | Wi-Fi STA, NTP sync, exponential backoff |
| [`mqtt.{h,cpp}`](../src/mqtt.cpp) | PubSubClient wrapper, exponential backoff |
| [`buffer.{h,cpp}`](../src/buffer.cpp) | Static 100-deep ring buffer (~51 KB SRAM) |
| [`main.cpp`](../src/main.cpp) | Orchestration, sensor cache, fault-injection serial CLI |

---

## 10. Resilience design

- **Wi-Fi**: state machine `Disconnected → Connecting → Connected`; per-attempt
  timeout 15 s; exponential backoff capped at 60 s.
- **MQTT**: same state machine and backoff; lazy-reconnects only when Wi-Fi
  is up; failed connects log the PubSubClient state code (`-2 TCP fail`,
  `4 bad credentials`, etc.) for fast triage.
- **Buffer-first publish**: every payload is enqueued first; a separate
  drainer publishes oldest → newest whenever MQTT is up. FIFO overflow
  drops the oldest entry and increments a counter for telemetry.
- **At-least-once at app layer**: a failed publish leaves the entry at the
  head of the queue and retries on the next pass. Combined with QoS 0
  PubSubClient, this gives at-least-once delivery without protocol-level
  acknowledgement.
- **Loop**: 100 % non-blocking — `millis()` timers everywhere, no
  scheduling `delay()` calls.

---

## 11. Validation rules

Defined in [`config.h`](../include/config.h):

| Quantity | Min | Max |
|---|---|---|
| temperature (°C) | -40 | 85 |
| humidity (%) | 0 | 100 |
| pressure (hPa) | 300 | 1100 |
| current (A) | -30 | 30 |

The current range is broadest-band by default to cover all ACS712
variants. Tighten to your motor's expected envelope (e.g. ±5 A) once
you've characterised it.

---

## 12. Serial command reference

Send single characters in the Serial Monitor input box at 115200 baud:

| Key | Effect |
|---|---|
| `b` | toggle BME280 NaN fault |
| `B` | toggle BME280 out-of-range fault (200 °C / 150 % / 50 hPa) |
| `d` | toggle DS18B20 NaN fault |
| `D` | toggle DS18B20 out-of-range fault |
| `a` | toggle ACS712 NaN fault |
| `A` | toggle ACS712 out-of-range fault |
| `c` | recalibrate ACS712 zero-offset (motor MUST be off) |
| `r` | clear all faults |
| `?` / `h` | print this help |

Useful for live demos of the validation layer without unplugging real
sensors.

---

## 13. Sensor deep-dive

### DS18B20 (1-Wire temperature)

- **Pinout** (TO-92, flat side facing you): GND (1) — DQ (2) — VDD (3).
- **Pull-up**: 4.7 kΩ between DQ and 3V3. Without it, the bus is stuck low
  and the driver returns `DEVICE_DISCONNECTED_C` (-127), which is rejected
  as invalid.
- **Resolution**: 12-bit (`DS18B20_RESOLUTION_BITS`), ~0.0625 °C per LSB.
- **Conversion time**: ≈ 750 ms at 12-bit. We poll once per second so this
  is fine; if you crank the loop faster, drop to 10-bit (≈ 94 ms).

### BME280 / BMP280 family (I²C atmospheric)

- **Auto-detection**: `begin()` first tries `Adafruit_BME280` at the
  configured address; on rejection it falls back to `Adafruit_BMP280` at
  the same address. Whichever ACKs becomes the active chip.
- **Distinguishing**: the chip-ID register `0xD0` returns `0x60` for
  genuine BME280 and `0x58` for BMP280. The diagnostic on init failure
  reads this register and prints which one is on the bus.
- **Capability flag**: `Bme280Reading.has_humidity` is `true` only on
  BME280. On BMP280 the humidity slot is silently absent from the JSON
  payload (not a fault).
- **`sensor` field**: dynamically `"bme280"` or `"bmp280"` so dashboards
  reflect the actual chip.
- **Sampling**: weather-station preset (1× oversampling, filter off,
  STANDBY 1000 ms) for low-power, ~1 Hz operation.

### ACS712 (Hall-effect current)

- **Variants**: 5 A (185 mV/A), 20 A (100 mV/A), 30 A (66 mV/A). Set
  `ACS712_SENSITIVITY_MV_PER_A` accordingly.
- **OUT idle voltage**: VCC/2 (≈ 2500 mV at VCC=5 V). Positive current
  drives OUT toward VCC; negative current toward GND.
- **Voltage divider**: ESP32 ADC tops out at 3.3 V. Our default 10 k +
  20 k divider gives a 0.667 ratio so the full 0–5 V range maps to
  0–3.3 V. Skipping the divider risks overvolting the ADC at currents
  > 4 A.
- **ADC pin**: must be on **ADC1** (`GPIO 32, 33, 34, 35, 36, 39`). ADC2
  is unusable while Wi-Fi is up.
- **Zero-offset calibration**: `begin()` averages 256 ADC samples to
  capture the real idle voltage (compensates for chip variation, board
  parasitics, USB voltage droop). Re-trigger via Serial `c` whenever
  you can guarantee the load is off.
- **Per-read averaging**: 64 samples per read (~64 µs) filters DC-motor
  brush noise.
- **Inductive loads**: always add a flyback diode across the motor
  (cathode to + side) — the back-EMF spike on switch-off can damage the
  ACS712.

---

## 14. Tested scenarios

| Test | Result |
|---|---|
| Boot heartbeat (M1) | ✅ |
| BMP280 detected at 0x76 (M2/M12) | ✅ |
| DS18B20 reads ~24–26 °C at room temp (M3/M11) | ✅ |
| JSON schema well-formed, all fields present (M4) | ✅ |
| Wi-Fi connect within 3 s + AP-toggle reconnect with exp backoff (M5) | ✅ |
| MQTT publish, mosquitto_sub receives every 10 s (M6) | ✅ |
| 60 s broker outage + restart, **0 messages lost** (M7) | ✅ |
| Fault-injection drops + status flip to `invalid_reading` (M8) | ✅ |
| README.md (M10) | ✅ |
| ACS712 plumbing — payload includes `current` reading (M13) | ✅ (wiring tuning ongoing) |

---

## 15. Known limitations

- **ACS712 calibration drift**: thermal drift on the IC means the
  zero-offset moves a few mA over minutes. Re-run `c` between long
  runs, or implement a periodic auto-zero when current is known to be
  zero.
- **MQTT QoS 0**: PubSubClient is QoS-0 only. App-layer at-least-once
  works for our single-publisher topology but is not equivalent to
  broker-acknowledged QoS 1.
- **No TLS**: broker reachable on plaintext `:1883`. Stretch goal in
  spec, not implemented.
- **No persistent buffer**: the 100-deep ring lives in RAM. A reboot
  during an outage loses queued messages. LittleFS-backed buffer was a
  stretch goal.
- **ADC nonlinearity at extremes**: ESP32 ADC is well-known to be
  nonlinear below ~150 mV and above ~3.0 V. The voltage divider keeps
  ACS712 in the linear band (~700–2200 mV at the ADC pin) for the
  expected current range.

---

## 16. Consuming the data from another app

The MQTT broker is the integration point. Any client that speaks MQTT
3.1.1 can subscribe to `retech/devices/+/readings` (or to a specific
device's topic) and decode the JSON.

### Python

A working example sits in [`tools/subscribe.py`](../tools/subscribe.py).
Setup:

```bash
pip install paho-mqtt
python tools/subscribe.py --host 192.168.137.1
```

Optional flags:
- `--port 1883`
- `--topic 'retech/devices/+/readings'`
- `--username foo --password bar` (only if you switched off anonymous)
- `--jsonl out.jsonl` (also append every raw payload to a JSON-lines file
  for downstream ingestion or replay)

The script prints one line per received payload, e.g.:

```
[2026-05-02T14:30:00Z] esp32_node_01 [ok]  temperature(ds18b20)=23.50c  temperature(bmp280)=23.70c  pressure(bmp280)=1013.25h  current(acs712)=0.42a
```

#### Minimal inline example

If you'd rather embed it in your own code:

```python
import json
import paho.mqtt.client as mqtt

BROKER = "192.168.137.1"
TOPIC  = "retech/devices/+/readings"

def on_connect(client, userdata, flags, reason_code, properties):
    print("connected:", reason_code)
    client.subscribe(TOPIC, qos=1)

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload)
    device  = payload["device_id"]
    status  = payload["status"]
    for r in payload["readings"]:
        print(f"{device} {r['type']}({r['sensor']}) = {r['value']} {r['unit']}  [{status}]")

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883, keepalive=60)
client.loop_forever()
```

### Other languages

- **Node.js**: `npm install mqtt`; the `mqtt` package exposes
  `mqtt.connect('mqtt://192.168.137.1')` and a similar message-event API.
- **Go**: `eclipse/paho.mqtt.golang`.
- **Rust**: `rumqttc`.
- **MQTT Explorer (GUI)**: free graphical client, useful for poking
  around the topic tree without writing code.

### Topic patterns

- `retech/devices/+/readings` — one device level wildcard, gives all
  devices.
- `retech/devices/esp32_node_01/readings` — exact device.
- `retech/#` — full hackathon namespace (multi-level wildcard, useful
  for discovery dashboards).

### Down-stream ingestion notes for Part 2

- Each payload is a single JSON object — append-only safe.
- `timestamp` is ISO-8601 UTC; it is the device-side capture time.
  Pre-NTP the value is `1970-01-01T...Z` — drop or backfill those at
  the ingestion layer.
- `uptime_s` resets to 0 on reboot; treat it as a per-session counter,
  not a stable cumulative metric.
- `status == "invalid_reading"` is a soft signal, not an error to drop
  the message. Keep the row, mark a quality flag, fall back to other
  sensor sources where applicable.

---

## 17. Edge ML — Part 3A

### Model architecture

Single multi-output MLP that predicts all 5 sensor channels simultaneously,
deployed directly on the ESP32 for local anomaly detection (no cloud/server).

```
Input (25)  = 5 channels × sliding window of 5
     ↓
Dense (16, ReLU)
     ↓
Dense (8, ReLU)
     ↓
Dense (5, Sigmoid)  = normalised prediction for next step of each channel
```

- **Parameters**: ~597 (25×16 + 16 + 16×8 + 8 + 8×5 + 5)
- **Quantisation**: `tf.lite.Optimize.DEFAULT` (weight compression, no representative dataset)
- **Typical TFLite model size**: 4–8 KB
- **Tensor arena on ESP32**: 16 KB (SRAM)
- **Inference latency**: <50 ms measured on ESP32 @ 240 MHz

### Multi-channel bonus claim

**A single model predicts all 5 sensor channels simultaneously** — one inference call
returns predictions for DS18B20 temp, BMP280 temp, BMP280 pressure, and ACS712 current
(and BME280 humidity if a real BME280 is connected). This satisfies the multi-sensor
bonus criterion.

### How to reproduce training

```bash
# 1. Collect data (≥30 rows recommended, >100 ideal)
python tools/subscribe.py --host 192.168.137.1 --jsonl training_data.jsonl

# 2. Install Python dependencies
pip install tensorflow numpy scikit-learn

# 3. Train and generate the C header
python tools/train_model.py
```

The script prints row count, model size in bytes, and per-channel validation MAE
— **screenshot this output** as submission evidence.

Example output:
```
============================================================
 Re-Tech Fusion — Edge ML Training
============================================================
  JSONL file : .../training_data.jsonl
  Rows found : 120
  ...
  ✓ TFLite model size : 5248 bytes  (5.12 KB)

  Per-channel MAE (normalised 0–1):
    CH0 ds18b20_T : 0.0312
    CH1 bme_T     : 0.0287
    CH2 bme_H     : 0.0000   ← constant (BMP280, no humidity)
    CH3 bme_P     : 0.0198
    CH4 acs_I     : 0.0441

  ✓ C header written : include/model_data.h
```

### Firmware integration (Part 1)

After training, `include/model_data.h` is generated automatically. Then:

1. Add EloquentTinyML dep in `platformio.ini` (already included).
2. Build + flash normally — `edge_inference.cpp` picks up the header.

Serial Monitor will show an `[EDGE]` line every 10 s:
```
[EDGE] [30s] anomaly=0 max_err=0.043 worst_ch=4 latency=18ms
```

### Anomaly demo

1. Flash the trained firmware.
2. Wait 60 s for the 5-reading window to warm up.
3. In Serial Monitor, press **`B`** (BME280 out-of-range fault injection).
4. Next `[EDGE]` line will show `anomaly=1` and `worst_ch=1` (BMP280 temperature channel).
5. Press **`r`** to clear; anomaly flag clears on the following cycle.

### Fallback: z-score statistical detection

If EloquentTinyML fails to compile (TFLite Micro dependency issues), uncomment
`-D EDGE_FALLBACK_ZSCORE` in `platformio.ini` build_flags. The same
`EdgeResult` API is used — no changes to `main.cpp` required. Inference
becomes Welford's online z-score; anomaly fires when `|x − μ| > 2σ` on any channel.
No model file and no training step are needed.

### Files

| File | Purpose |
|---|---|
| [`tools/train_model.py`](../tools/train_model.py) | Training + TFLite conversion + header generation |
| [`include/model_data.h`](../include/model_data.h) | Auto-generated C header (do not edit) |
| [`include/edge_inference.h`](../include/edge_inference.h) | Public API: `push()`, `run()`, `EdgeResult` |
| [`src/edge_inference.cpp`](../src/edge_inference.cpp) | TFLite primary + z-score fallback implementations |

---

*Built for the Re·Tech Fusion Hackathon — INSAT, University of Carthage.*
