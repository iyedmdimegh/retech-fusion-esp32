# Re·Tech Fusion — ESP32 IoT Node (Part 1)

Firmware for the ESP32 device that streams environmental readings to an MQTT
broker on the LAN. Built for the **Re·Tech Fusion (NRTF) Hackathon** at INSAT.
The schema published here is consumed by Part 2 (ingestion + dashboard) and
Part 3 (edge ML).

- **Two sensors**: GY-BME280 (I²C, temperature / humidity / pressure) and
  DS18B20 (1-Wire, temperature).
- **Network**: Wi-Fi STA + MQTT publish every 10 s.
- **Resilient**: exponential-backoff reconnect for both Wi-Fi and MQTT, plus a
  100-deep RAM ring buffer that drains oldest-first on reconnect.
- **Validating**: NaN and out-of-range readings are dropped from the array and
  flip `status` to `invalid_reading` — never `null`, never `-999`.

---

## 1. Hardware

| Item | Notes |
|---|---|
| **MCU** | ESP32 dev board (`esp32dev` / WROOM-32 module) |
| **Sensor 1** | GY-BME280 breakout, 3.3 V variant, I²C @ 0x76 |
| **Sensor 2** | DS18B20 in TO-92, 1-Wire, with **4.7 kΩ pull-up** between DQ and 3.3 V |
| **Wiring** | Breadboard + jumper wires |
| **Network** | Same Wi-Fi LAN (or laptop's Mobile Hotspot) as the broker host |

> ⚠ The BME280 module is **3.3 V only** — connecting it to the ESP32's 5 V / VIN
> pin will destroy the chip silently. Always use the **3V3** pin.

---

## 2. Wiring

### Pinout table

| Function | ESP32 pin | Sensor pin |
|---|---|---|
| BME280 VCC | 3V3 | VCC |
| BME280 GND | GND | GND |
| BME280 SDA | GPIO 21 | SDA |
| BME280 SCL | GPIO 22 | SCL |
| DS18B20 VDD | 3V3 | VDD (pin 3) |
| DS18B20 DQ | GPIO 4 | DQ (pin 2) — also via 4.7 kΩ to 3V3 |
| DS18B20 GND | GND | GND (pin 1) |

All pin assignments live in [`include/config.h`](include/config.h) — no magic
numbers anywhere else in the source.

### ASCII diagram

```
         ESP32 dev board                     GY-BME280
         ┌──────────────┐                  ┌──────────────┐
         │          3V3 ├────────┬─────────┤ VCC          │
         │          GND ├────────┼──┬──────┤ GND          │
         │       GPIO21 ├────────┼──┼──────┤ SDA          │
         │       GPIO22 ├────────┼──┼──────┤ SCL          │
         │              │        │  │      └──────────────┘
         │              │        │  │
         │              │        │  │      DS18B20  (flat side facing you)
         │              │        │  │           ┌─────┐
         │              │        ├──┼───────────┤ VDD │ pin 3
         │              │        │  ├───────────┤ GND │ pin 1
         │              │        │  │   ┌───────┤ DQ  │ pin 2
         │       GPIO 4 ├────────┼──┼───┤
         │              │        │  │  ┌┴┐
         │              │        │  │  │ │ 4.7 kΩ pull-up
         │              │        │  │  └┬┘
         │              │        └──┼───┘ ── (DQ pulled HIGH to 3V3)
         │              │           │
         └──────────────┘
```

---

## 3. Software setup

### Toolchain

- [VS Code](https://code.visualstudio.com/) with the
  [PlatformIO IDE extension](https://platformio.org/install/ide?install=vscode).

Open the repo folder in VS Code; PlatformIO will index and download the pinned
libraries automatically on first build.

### Pinned libraries (declared in [`platformio.ini`](platformio.ini))

| Library | Version |
|---|---|
| `paulstoffregen/OneWire` | `^2.3.8` |
| `milesburton/DallasTemperature` | `^3.11.0` |
| `adafruit/Adafruit BME280 Library` | `^2.2.4` |
| `adafruit/Adafruit Unified Sensor` | `^1.1.14` |
| `bblanchon/ArduinoJson` | `^6.21.5` |
| `knolleary/PubSubClient` | `^2.8` |

### Secrets

Wi-Fi and broker credentials live in [`include/secrets.h`](include/secrets.h.example),
which is **gitignored**. Copy the template:

```powershell
Copy-Item include/secrets.h.example include/secrets.h
```

Edit it:

```cpp
#define WIFI_SSID         "your-ssid"
#define WIFI_PASSWORD     "your-password"
#define MQTT_BROKER_HOST  "192.168.137.1"   // laptop IP on the ESP32's network
#define MQTT_BROKER_PORT  1883
#define MQTT_USERNAME     ""                // empty == anonymous
#define MQTT_PASSWORD     ""
```

### Dummy-sensor mode

The build flag `-D USE_DUMMY_SENSORS=1` (in [`platformio.ini`](platformio.ini))
makes the sensor modules return constant values matching the schema example
(BME: 23.7 °C / 45.2 % / 1013.25 hPa; DS: 23.5 °C). Used while the bench
hardware was unavailable — **remove this flag to use real sensors**.

---

## 4. Mosquitto on Windows (broker host)

### Install

In **PowerShell as Administrator**:

```powershell
winget install --id EclipseFoundation.Mosquitto -e --accept-source-agreements --accept-package-agreements
New-NetFirewallRule -DisplayName "Mosquitto MQTT 1883" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow
```

Verify:

```powershell
Test-Path 'C:\Program Files\mosquitto\mosquitto.exe'   # should be True
```

### Run the broker

A LAN-anonymous config is committed at [`tools/mosquitto.conf`](tools/mosquitto.conf):

```
listener 1883 0.0.0.0
allow_anonymous true
```

In a regular PowerShell window in the project root:

```powershell
& 'C:\Program Files\mosquitto\mosquitto.exe' -c .\tools\mosquitto.conf -v
```

Leave it open. You should see `Opening ipv4 listen socket on port 1883`.

### Subscribe (verify reception)

In a second PowerShell window:

```powershell
& 'C:\Program Files\mosquitto\mosquitto_sub.exe' -h 192.168.137.1 -t 'retech/devices/+/readings' -v
```

Replace `192.168.137.1` with the broker IP on the ESP32's network (from
`ipconfig`; for a Windows Mobile Hotspot it's typically `192.168.137.1`).

> ⚠ This config is **insecure by design** — anonymous + plaintext on `0.0.0.0`.
> Use only on a private hackathon LAN / hotspot. Never on a public IP.

---

## 5. Build, flash, monitor

In VS Code with PlatformIO:

1. **Build** — ✓ icon on the status bar.
2. **Upload** — → icon (USB).
3. **Serial Monitor** — 🔌 icon, opens at 115200 baud.
4. Press **EN/RST** on the ESP32 to capture the boot banner.

Or via CLI:

```powershell
pio run -t upload
pio device monitor -b 115200
```

---

## 6. JSON schema

Topic: `retech/devices/{device_id}/readings` (default `retech/devices/esp32_node_01/readings`).

QoS 0 over MQTT (PubSubClient limitation); at-least-once is achieved at the
application layer via the ring buffer + retry. Retained = false.

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
    {"type": "pressure",    "value": 1013.25, "unit": "hPa",     "sensor": "bme280"}
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
| `device_id` | string | from `DEVICE_ID` in [`config.h`](include/config.h) |
| `site` | string | from `SITE_ID` in [`config.h`](include/config.h) |
| `timestamp` | string (ISO-8601 UTC, `Z` suffix) | NTP-synced once Wi-Fi is up; placeholder `1970-01-01T...Z` until then |
| `readings[]` | array of objects | up to 4 entries; entry has `type`, `value`, `unit`, `sensor` |
| `status` | string | `"ok"` or `"invalid_reading"` |
| `rssi` | int | dBm, 0 when not connected |
| `uptime_s` | int | seconds since boot |
| `fw_version` | string | from `FW_VERSION` in [`config.h`](include/config.h) |

A reading is **dropped** from the array (never emitted as `null`) when:
- the sensor's `ok` flag is false, OR
- the value is `NaN`, OR
- the value is outside the validation range below.

When *anything* is dropped, top-level `status` becomes `"invalid_reading"`.

### Validation ranges

| Quantity | Min | Max |
|---|---|---|
| temperature (°C) | -40 | 85 |
| humidity (%) | 0 | 100 |
| pressure (hPa) | 300 | 1100 |

---

## 7. Architecture

```
                   ┌────────────────┐
                   │   main.cpp     │  10 s tick → buildAndQueuePayload
                   └───────┬────────┘                 │
            ┌──────────────┼──────────────┐           ▼
   sensors_bme280 ◄── readAndPrint ──► sensors_ds18b20
       │                                          │
       └──────────────┬───────────────────────────┘
                      ▼
            ┌──────────────────┐                    ┌──────────────┐
            │  schema (JSON)   │                    │   buffer     │
            └────────┬─────────┘                    │ ring 100×512 │
                     │                              └──────┬───────┘
                     ▼                                     │
            ┌──────────────────┐                           │
            │   network (Wi-Fi)│      drainBufferIfPossible│
            │   reconnect/NTP  │                           │
            └────────┬─────────┘                           ▼
                     ▼                              ┌──────────────┐
            ┌──────────────────┐                    │   mqtt       │
            │ PubSubClient over│◄─────publish───────┤  reconnect   │
            │  TCP, QoS 0      │                    └──────────────┘
            └──────────────────┘
```

Module map:

| File | Responsibility |
|---|---|
| [`include/config.h`](include/config.h) | All pins, intervals, thresholds, ranges |
| [`include/secrets.h`](include/secrets.h.example) | Wi-Fi + broker credentials (gitignored) |
| [`sensors_bme280.{h,cpp}`](src/sensors_bme280.cpp) | I²C / Adafruit driver wrapper |
| [`sensors_ds18b20.{h,cpp}`](src/sensors_ds18b20.cpp) | OneWire / Dallas driver wrapper |
| [`schema.{h,cpp}`](src/schema.cpp) | ArduinoJson v6 payload builder + validators |
| [`network.{h,cpp}`](src/network.cpp) | Wi-Fi STA, NTP, exponential-backoff reconnect |
| [`mqtt.{h,cpp}`](src/mqtt.cpp) | PubSubClient wrapper, exponential-backoff reconnect |
| [`buffer.{h,cpp}`](src/buffer.cpp) | 100-deep static ring buffer for offline payloads |
| [`main.cpp`](src/main.cpp) | Orchestration, sensor cache, fault-injection serial CLI |

### Resilience design

- **Wi-Fi**: state machine `Disconnected → Connecting → Connected`; per-attempt
  timeout 15 s; exponential backoff 1 → 2 → 4 → 8 → 16 → 32 → 60 s capped.
- **MQTT**: same state machine and backoff; lazy-reconnects only when Wi-Fi is
  up; logs the PubSubClient state code on every failure for triage.
- **Buffer**: every payload goes into the ring first; a separate drainer
  publishes oldest-first whenever MQTT is up. FIFO overflow drops oldest and
  increments a counter (also logged when full). At-least-once at app layer:
  a failed publish keeps the entry at the head and retries on the next pass.
- **Loop**: 100 % non-blocking — `millis()`-based timers, no `delay()` for
  scheduling.

---

## 8. Serial command reference (debug / demo aid)

Press a key in the Serial Monitor input box at any time:

| Key | Effect |
|---|---|
| `b` | toggle BME280 NaN fault (dropped readings; status → `invalid_reading`) |
| `B` | toggle BME280 out-of-range fault (200 °C / 150 % / 50 hPa) |
| `d` | toggle DS18B20 NaN fault |
| `D` | toggle DS18B20 out-of-range fault |
| `r` | clear all faults |
| `?` | print help |

Useful when running on real hardware for "live unplug" demos, or in
`USE_DUMMY_SENSORS` mode for everything.

---

## 9. Tested scenarios

All tests run on `esp32dev` + dummy-sensor build flag, broker on Windows 11
laptop reachable at `192.168.137.1` over Mobile Hotspot.

| Test | Expected | Result |
|---|---|---|
| **M1 boot** | `[INFO] Booted fw v1.0.0` once per second | ✅ |
| **M3 dummy sensor read** | constants every second matching schema example | ✅ |
| **M4 JSON shape** | well-formed, 4 readings, all fields present | ✅ |
| **M5 Wi-Fi connect** | IP + RSSI logged within ~3 s | ✅ |
| **M5 AP-toggle reconnect** | exponential backoff visible (1, 2, 4, 8 …); reconnect on AP return | ✅ |
| **M6 MQTT publish** | one message every 10 s on `mosquitto_sub` | ✅ |
| **M7 60 s broker outage** | broker stopped 60 s; on restart all queued messages drained, **0 lost** | ✅ |
| **M8 fault drop + status flip** | dropped reading absent from array, no `null`/`-999`, `status` flips to `invalid_reading` | ✅ |

---

## 10. Demo run (judge-friendly)

Three terminals on the laptop, one ESP32 connected to its Mobile Hotspot.

```powershell
# Terminal 1 — broker
& 'C:\Program Files\mosquitto\mosquitto.exe' -c .\tools\mosquitto.conf -v

# Terminal 2 — subscriber
& 'C:\Program Files\mosquitto\mosquitto_sub.exe' -h 192.168.137.1 -t 'retech/devices/+/readings' -v

# Terminal 3 — flash + serial monitor (PlatformIO)
pio run -t upload
pio device monitor -b 115200
```

Demo script (5 minutes):

1. **Boot + connect** — point at the Wi-Fi connect line and the first
   `MQTT published` line on the device monitor; show one full payload landing
   in Terminal 2.
2. **Resilience** — Ctrl+C in Terminal 1 (broker dies). Wait 30 s. Show
   `queued offline` lines accumulating on the device. Restart broker. Show the
   queue drain to zero and zero lost messages.
3. **Validation** — type `d` in Serial Monitor. Next payload in Terminal 2 has
   3 readings, no DS-temp, `status:"invalid_reading"`. Type `r` to clear.

---

## 11. Known limitations

- **M2 / M3 hardware deferred.** The bench BME280 module did not respond on
  I²C (bus electrically healthy, no ACK at 0x76 or 0x77 — likely DOA). The
  firmware is shipped with `-D USE_DUMMY_SENSORS=1` in
  [`platformio.ini`](platformio.ini), which returns constant values from both
  sensor drivers. The real I²C and OneWire driver paths are coded and intact;
  removing the flag and rebuilding restores them.
- **M9 not implemented.** No cross-sensor drift alert and no ArduinoOTA in
  this build (deferred to focus on the core ingest path).
- **MQTT QoS 0.** PubSubClient is QoS-0-only. At-least-once is implemented at
  the application layer via the ring buffer and the publish-success-driven
  retry. Acceptable for a Part-2 dashboard that re-derives state from
  message stream; not a substitute for true broker-acknowledged QoS 1.
- **No TLS.** Broker reachable on plaintext `1883`. The hackathon spec lists
  TLS as a stretch goal — not pursued here.
- **No persistent buffer.** The 100-deep ring lives in RAM only; a reboot
  during an outage loses the queued messages. LittleFS-backed buffer was a
  stretch goal.

---

## 12. Repo layout

```
nrtf3/
├── README.md                  ← this file
├── platformio.ini             ← env, board, libs, USE_DUMMY_SENSORS flag
├── tools/
│   └── mosquitto.conf         ← LAN-anonymous broker config
├── include/
│   ├── config.h               ← all pins / intervals / thresholds
│   ├── secrets.h.example      ← template for Wi-Fi + broker credentials
│   ├── sensors_bme280.h
│   ├── sensors_ds18b20.h
│   ├── schema.h
│   ├── network.h
│   ├── mqtt.h
│   └── buffer.h
└── src/
    ├── main.cpp               ← orchestration + serial CLI
    ├── sensors_bme280.cpp
    ├── sensors_ds18b20.cpp
    ├── schema.cpp
    ├── network.cpp
    ├── mqtt.cpp
    └── buffer.cpp
```
