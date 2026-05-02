# Re·Tech Fusion Hackathon — Solution Context Document
**Team Solution Brief — INSAT / University of Carthage**

> **Purpose of this document:** Single source of truth describing our end-to-end solution for the Re·Tech Fusion Industrial AI & IoT Hackathon. Any LLM reading this should be able to fully understand our architecture, design choices, and how each scoring criterion is addressed. Use this when generating documentation, pitch material, README files, code, or answering questions about the project.

---

## 1. Executive Summary

We built a **complete vertical stack** that takes raw industrial energy data — both from physical IoT sensors we deploy and from heterogeneous legacy documents (PDFs, Excel sheets, scanned bills, images) — unifies it into a single canonical format (kWh), estimates CO₂ emissions, detects anomalies in real time, runs intelligently even when the network drops, and exposes everything through a business-oriented dashboard plus a natural-language LLM interface.

We are competing on **all three parts** and **both Part 3 tracks (A and B)** to maximize scoring.

**One-line elevator pitch:** *From sensor pin to carbon ledger — a fully Dockerized, edge-resilient, LLM-queryable industrial energy intelligence platform.*

---

## 2. System Architecture (End-to-End Data Flow)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PHYSICAL LAYER (Part 1)                          │
│  ESP32 DevKit (PoC) ──► BME280: temperature, humidity, pressure (I2C)    │
│                     ──► DS18B20: temperature (OneWire)                   │
│                     ──► Cross-sensor drift detection (±2°C threshold)    │
│                                                                          │
│  Sampling: 1 s | Publish: every 10 s | NTP-synced UTC timestamps         │
│  Buffering: 100-message ring buffer survives Wi-Fi/MQTT outages          │
│  Reconnect: exponential backoff | On-device: SVD predictor (Part 3A)     │
│                                                                          │
│  Target product: custom industrial PCB (ESP32-S3/C6) — Wi-Fi/BLE/RS485/  │
│  CAN/RS232/LoRaWAN/NB-IoT, 5–30V input, galvanic isolation, 4–20 mA loop │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │  MQTT — wireless
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      INGESTION & UNIFICATION (Part 2)                    │
│                                                                          │
│  IoT stream ──┐                                                          │
│               ├──► Time-series DB ──► Unified timestamped framework      │
│  Document   ──┘                                                          │
│  upload drive (CSV / Excel / PDF / PNG / scans)                          │
│      │                                                                   │
│      ▼                                                                   │
│  Automated extraction pipeline (OCR + table parsing + LLM-assisted)      │
│      │                                                                   │
│      ▼                                                                   │
│  Unit normalizer — 38 unit types × 7 categories ──► canonical kWh        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    INTELLIGENCE LAYER (Part 2 + 3)                       │
│                                                                          │
│  • CO₂ estimation engine (multi-horizon forecasting)                     │
│  • Isolation Forest anomaly detection (cloud, full data)                 │
│  • SVD on-device model (edge, Part 3A)                                   │
│  • Waste heat recovery scoring tool (Part 3B)                            │
│  • LLM agent (RAG over all data) — natural language Q&A                  │
│  • N8N workflow → alerts admins on anomaly                               │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              PRESENTATION LAYER — Business Dashboard                     │
│  KPIs • CO₂ ledger • Energy trends • Anomaly feed • Heat recovery ROI    │
│                Dockerized • Documented • Deployed                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Part 1 — IoT Device & Protocol (Full Implementation)

We deliver Part 1 in two stages: a **working PoC** running today on an ESP32 DevKit with breakout sensors, and a **target product** — a custom industrial PCB designed for real plant deployment. The PoC validates the full firmware pipeline before migrating to the production board.

### 3.1 PoC Hardware Stack (current prototype)
- **MCU:** ESP32 DevKit (Wi-Fi + Bluetooth, sufficient RAM for on-device inference)
- **Sensor #1 — BME280** (auto-fallback to BMP280) on I²C `0x76`: **temperature, humidity, pressure** (3 distinct measurement types from one sensor)
- **Sensor #2 — DS18B20** on OneWire (GPIO 4): independent **temperature** reading
- **Cross-sensor validation:** the two temperature sources are compared continuously with a **±2 °C drift threshold**, enabling automatic sensor-fault detection — a genuine industrial reliability feature

This delivers **4 distinct measurement streams** (temperature ×2, humidity, pressure) from 2 physical sensors, exceeding the required ≥3 distinct sensor types.

### 3.2 Target Product — Custom Industrial PCB
The production board (already laid out, see PCB renders in repo) is built around the **ESP32-S3 / ESP32-C6** with industrial-grade specifications:

| Area | Capabilities |
|---|---|
| **Sensors** | Environmental, inertial (vibration), acoustic (leak detection), **4–20 mA current loop** |
| **Comms** | Wi-Fi · BLE · RS485 · CAN (TJA1040) · RS232 · LoRaWAN (RAK4270) · NB-IoT/GSM (SIM7022 / SIM800C) |
| **Power** | 5–30 V DC input, 3.3 V regulation, over-voltage protection, reverse-polarity protection, deep sleep, BMS-ready |
| **Isolation** | Galvanic barriers on RS485 and field inputs (24 V) |

This addresses the sponsor's real-world pain point: factory floors are noisy, hostile electrical environments where a bare DevKit will not survive. Showing the jury both a working PoC **and** a credible production design demonstrates engineering maturity.

### 3.3 Protocol & Transmission
- **Protocol:** MQTT — lightweight, pub/sub, broker-based
- **Sampling rate:** **1 s** (sensor read + range validation)
- **Publish rate:** **10 s** (one batched JSON payload per device)
- **Timestamping:** **NTP-synced UTC** on every payload
- **Topic structure:** `retech/devices/{device_id}/readings`
- **Payload:** structured JSON containing device ID, site, UTC timestamp, an array of readings (each with type, value, unit, sensor source), status, RSSI, uptime, and firmware version

Example payload (topic `retech/devices/esp32_node_01/readings`):
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

### 3.4 Resilience Features
| Feature | Implementation |
|---|---|
| **Auto-reconnection** | Wi-Fi/MQTT watchdog with **exponential backoff** — no data loss across drops |
| **Device-side buffering** | **100-message ring buffer** queued during outages; drained to broker on reconnect |
| **NTP time sync** | UTC timestamps on every payload regardless of upload time |
| **Range validation** | Each reading checked against physical bounds before being queued |
| **Cross-sensor drift detection** | BME280 vs DS18B20 temperature delta > 2 °C → flagged as suspect |
| **Status & telemetry** | RSSI, uptime, firmware version included in every payload for fleet observability |
| **Hardware-free testing** | `USE_DUMMY_SENSORS=1` build flag enables firmware testing without physical hardware |

### 3.5 Repository & Project Structure
The firmware lives in a clean PlatformIO project at **https://github.com/iyedmdimegh/retech-fusion-esp32** with a one-command quickstart (`pio run -t upload`), Mosquitto broker config, secrets template, and PCB renders under `docs/images/`.

### 3.6 Part 1 Scoring Coverage
| Criterion | Points | How we cover it |
|---|---|---|
| Solution functional | 30 | Server receives valid JSON every 10 s, validated end-to-end |
| Multi-sensor coordination | 25 | 4 measurement streams from 2 sensors, synchronized, correct units, cross-validated |
| Protocol design & security | 15 | MQTT + auth-protected broker + reconnect logic with exponential backoff |
| Uptime & continuity | 15 | 100-msg ring buffer guarantees ≥1 valid message per 5-min window during outages |
| Data quality | 10 | Physical-range validation + cross-sensor drift detection (±2 °C) |
| **Bonus — Innovation** | +15 | Cross-sensor drift detection + production PCB design (multi-protocol, isolated, 4–20 mA, deep-sleep) showing real industrial-deployment thinking |

---

## 4. Part 2 — Data Pipeline, Unification & Modeling (Full Implementation)

### 4.1 Universal Document Ingestion
**The user uploads any kind of file to a drive** and our system handles it automatically:
- **CSV / TSV** → pandas parser with delimiter sniffing
- **Excel (.xlsx, .xls, multi-sheet)** → openpyxl with sheet auto-detection
- **PDF (text-based)** → pdfplumber / PyMuPDF for text + tables
- **PDF (scanned) / PNG / JPG** → Tesseract OCR + layout analysis
- **LLM-assisted extraction** for unstructured invoices: prompt the LLM with extracted text and a strict JSON schema (date, supplier, site, energy quantity, unit) for hard-to-parse formats

### 4.2 Unit Normalization Engine
**38 energy unit types across 7 categories** all normalize to the **international canonical unit: kWh**.

| Category | Example units |
|---|---|
| Electrical | Wh, kWh, MWh, GWh, J, kJ, MJ |
| Thermal | cal, kcal, Gcal, BTU, MMBTU, therm |
| Fuel-based | toe (tonne oil equivalent), tce, boe, m³ natural gas, L diesel, L gasoline |
| SI energy | J, kJ, MJ, GJ, TJ |
| Imperial / mixed | ft·lbf, hp·h, BTU/h |
| Volumetric (gas) | Nm³, scf |
| Refrigeration | RT (refrigeration ton-hour) |

Conversion factors are stored in a **traceable JSON config file** so any audit can verify the conversion path.

### 4.3 CO₂ Emission Engine
- Each normalized energy reading is multiplied by an **emission factor** (kg CO₂eq / kWh) appropriate to its energy source (grid mix, natural gas, diesel, etc.)
- Tunisia-specific grid factor used for STEG; supplier-specific factors where given
- Output: **Carbon ledger** (`bilan carbone`) per site, per supplier, per period

### 4.4 Forecasting
- **Multi-horizon CO₂ estimation:** short-term (hours), medium (days), long (weeks)
- Models: ARIMA / Prophet baseline + a learned residual model
- Feature engineering: hour-of-day, day-of-week, temperature, production volume

### 4.5 Anomaly Detection
- **Algorithm:** Isolation Forest (cloud-side, full data context)
- **Each anomaly carries:** `type`, `timestamp`, `sensor_id`, `site`, `confidence_score`
- **Alerting:** **N8N workflow** triggers email/Slack to admins when an anomaly is raised
- Detects sensor faults (stuck values, drift, dropouts) AND anomalous consumption patterns (unexpected spikes, off-hour usage)

### 4.6 Dashboard
- **Business-oriented and user-friendly** — designed for plant managers, not engineers
- **Live-testable** at a deployed URL
- Sections:
  - Real-time IoT feed
  - Energy KPIs (consumption, generation, gains, losses)
  - **CO₂ ledger** (current + forecast)
  - Anomaly feed with severity
  - Document upload & extraction status
  - Heat recovery opportunities (Part 3B)
  - LLM chat panel

### 4.7 Deployment
- **Fully Dockerized:** `docker compose up` brings the entire stack from cold start
- **API documented** (OpenAPI/Swagger)
- **Reproducible** — no manual interventions
- All services: ingestion API, extraction worker, normalizer, ML inference, dashboard, N8N, MQTT broker, time-series DB

### 4.8 Part 2 Scoring Coverage
| Criterion | Points | How we cover it |
|---|---|---|
| Document extraction accuracy | 40 | OCR + LLM-assisted extraction across all 4 formats |
| Unit normalization accuracy | 25 | 38 units / 7 categories with traceable factors |
| CO₂ estimation quality | 15 | Calibrated emission factors + multi-horizon model |
| Dashboard quality | 20 | Business-oriented, KPI-driven, live |
| Dockerized pipeline | 20 | One-command deploy + Swagger docs |
| **Bonus — Anomaly detection** | +15 | Isolation Forest + N8N alerts |
| **Bonus — Innovation** | +25 | LLM-assisted extraction + LLM Q&A agent + production-grade industrial PCB design |

---

## 5. Part 3 — Both Tracks Implemented

### 5.1 Track A — Edge Inference & On-Device Anomaly Detection

**The model on our IoT device continues operating intelligently when the network fails — it predicts sensor values and detects anomalies locally, then resumes cloud sync when reconnected.**

#### 5.1.1 Model: SVD-based predictor
- **Approach:** SVD (Singular Value Decomposition) used to learn a low-rank representation of the multi-sensor time series. Inference reduces to small matrix multiplications — **fits ESP32 RAM**.
- **Why SVD:** No floating-point heavy training required on-device, easy to compress, deterministic latency, naturally produces a reconstruction error that **doubles as anomaly score**.
- **Training:** done offline on the Part 2 historical dataset; only the truncated U, Σ, V matrices are flashed to the device.

#### 5.1.2 Constraints met
| Constraint | Target | Our result |
|---|---|---|
| Model size in RAM | ESP32 budget | Truncated SVD ≪ available RAM |
| Inference latency | < 200 ms | Single matrix-vector multiply, well under budget |
| Multi-sensor prediction | Bonus | **Single SVD model predicts all sensor channels jointly** (qualifies for +15 bonus) |
| Local anomaly detection | Required | Reconstruction-error threshold; no server contact needed |

#### 5.1.3 Network-failure behavior
1. Device continues sampling every 2s
2. SVD predictor produces expected next values
3. Reconstruction error vs. actual → if above threshold → anomaly logged locally
4. All readings + local anomalies queued in flash buffer
5. On reconnect → flush buffer to cloud, resume normal sync

### 5.2 Track B — Waste Heat Recovery Opportunity Design

**A systematic tool to identify, characterize, and rank heat recovery opportunities at an industrial site.**

#### 5.2.1 Source identification
Automatic scan of the unified data + site metadata to detect candidate waste heat sources:
- Exhaust gases (boilers, furnaces, dryers)
- Cooling circuits (compressors, chillers, condensers)
- Hot effluents / process water
- Surface losses (uninsulated pipes, walls)
- Flue gas streams

#### 5.2.2 Characterization (per source)
Each identified source is profiled with:
- **Temperature level** (low <100°C / medium 100–400°C / high >400°C)
- **Thermal flux** (kW available)
- **Availability** (hours/year, intermittent vs. continuous)
- **Location** (proximity to potential heat sinks)

#### 5.2.3 Multi-criteria prioritization framework
Weighted scoring across 5 axes:
| Criterion | Weight | What it captures |
|---|---|---|
| Recoverable energy potential | 30% | kWh/year recoverable |
| CO₂ reduction | 25% | tons CO₂eq avoided/year |
| Integration complexity | 15% | distance to sink, retrofit difficulty |
| Implementation cost | 15% | CAPEX estimate |
| ROI / payback | 15% | years to break even |

Output: ranked opportunity list with weighted total score.

#### 5.2.4 Three concrete recovery scenarios (quantified)
For each industrial site analyzed, we generate **at least 3 scenarios** such as:
1. **Boiler flue gas → preheat feedwater** (economizer): X kWh/yr recovered, Y tCO₂/yr saved, ROI Z years
2. **Compressor heat → space heating / DHW**: quantified
3. **Condensate recovery loop**: quantified

All numbers are traceable: each comes with the source temperature, mass flow, ΔT exploitable, and emission factor used.

#### 5.2.5 Interactive tool (bonus)
A **working notebook + dashboard tab** lets the user:
- Adjust weights of the 5 criteria
- See live re-ranking of opportunities
- Run sensitivity analysis on energy price / carbon price
- Export a ranked report

### 5.3 Part 3 Scoring Coverage

**Track A**
| Criterion | Points | Coverage |
|---|---|---|
| Model size constraint | 15 | Truncated SVD fits ESP32 |
| Inference latency | 10 | <200ms — measured via serial logs |
| Prediction accuracy | 25 | MAE ratio reported on held-out Part 2 sequence |
| Working & testable | 25 | Live demo, video, emulator log |
| **Bonus — Multi-sensor model** | +15 | Single SVD covers all channels |

**Track B**
| Criterion | Points | Coverage |
|---|---|---|
| Source identification | 20 | Full taxonomy + automatic detection |
| Prioritization framework | 25 | 5-criteria weighted model |
| Quantified impact | 20 | 3+ scenarios with traceable numbers |
| Deliverable quality | 10 | Reproducible tool + report |
| **Bonus — Interactive tool** | +15 | Working dashboard with sensitivity analysis |

---

## 6. Bonus Innovations (cross-cutting)

### 6.1 LLM Conversational Agent
An **LLM with full data context** (RAG over IoT stream + extracted documents + anomaly log + CO₂ ledger) that answers user inquiries in natural language about:
- "Why did energy consumption spike on Tuesday at 3pm?"
- "What's our carbon footprint trend this quarter?"
- "Which sites have the most heat recovery potential?"
- "Show me anomalies on the boiler line last week"

### 6.2 Responsible AI Use
**The system does not use unnecessary AI** — we are aware of the environmental cost of large model inference (water consumption from datacenter cooling, electricity draw). Design choices:
- Lightweight SVD on edge (instead of an LSTM/transformer)
- Isolation Forest in cloud (instead of deep anomaly models)
- LLM only invoked on user query, not on every record
- Document extraction uses LLM **only** for hard cases; structured docs go through deterministic parsers first

This is itself a story we tell the jury — the project is about reducing emissions, so the project must walk the talk.

### 6.3 Production-Ready Industrial PCB
Beyond the PoC running on a DevKit, we have designed a **custom industrial PCB** (ESP32-S3/C6 based) with multi-protocol connectivity (Wi-Fi · BLE · RS485 · CAN · RS232 · LoRaWAN · NB-IoT/GSM), 5–30 V industrial power, galvanic isolation on field inputs, and 4–20 mA current-loop support. This addresses the sponsor's real pain point: most factories already have legacy field equipment speaking RS485/4–20 mA in noisy 24 V environments where a bare DevKit cannot survive. Showing both a working PoC **and** a credible production design demonstrates the path from hackathon to deployment.

### 6.4 N8N Automation Layer
Visual workflow automation means non-developers (plant operators) can adjust alert routing, escalation rules, and notification channels without code changes.

---

## 7. Pitch Narrative (8-min presentation skeleton)

1. **Problem framing (1 min)** — "Industrial CO₂ accounting is manual, slow, error-prone, and doesn't scale across acquired subsidiaries."
2. **Architecture overview (2 min)** — One slide of the data flow diagram from §2
3. **Live demo (3 min)** — End-to-end: device → MQTT → dashboard → upload a PDF invoice → extraction → normalized kWh → CO₂ → anomaly alert via N8N → ask the LLM "why did this happen?"
4. **Key design decisions (1.5 min)** — Why SVD on edge, why Isolation Forest in cloud, why N8N, why the responsible-AI angle
5. **What we'd do with more time (0.5 min)** — More emission-factor coverage, multi-tenant, federated learning across sites

### Quantified one-liners to drop in pitch
- "X% uptime over the test window"
- "F1 = X.XX on document extraction"
- "Model size: X KB on ESP32"
- "Inference latency: X ms"
- "Y kg CO₂ accounted for in the demo run"
- "Z heat recovery opportunities identified, top one saves W tCO₂/yr"

---

## 8. Tech Stack Summary

| Layer | Tools |
|---|---|
| Firmware (PoC) | PlatformIO, Arduino framework on ESP32 DevKit, BME280 + DS18B20 drivers, PubSubClient (MQTT), ArduinoJson, NTPClient |
| Target PCB | ESP32-S3 / ESP32-C6, multi-protocol comms (Wi-Fi/BLE/RS485/CAN/RS232/LoRaWAN/NB-IoT), galvanic isolation, 4–20 mA loop |
| Backend | Python (FastAPI), MQTT broker (Mosquitto), time-series DB (InfluxDB or TimescaleDB) |
| Extraction | pdfplumber, PyMuPDF, openpyxl, pandas, Tesseract, LLM (for hard cases) |
| ML | scikit-learn (Isolation Forest), NumPy SVD, Prophet/ARIMA |
| Edge ML | Truncated SVD flashed as static matrices |
| Automation | N8N |
| LLM agent | RAG with vector store over unified data |
| Dashboard | React or Streamlit (live-testable URL) |
| Orchestration | Docker Compose |

---

## 9. Rules Compliance Checklist

- [x] Team ≤ 5 members, no cross-team collaboration
- [x] All code original or open-source-licensed
- [x] LLM use disclosed; team accountable for outputs
- [x] All deliverables pushed before Day 3 / 05:00
- [x] Self-hosted network, power, hardware
- [x] Submission via GitHub repo + JSON POST to platform + live demo URL

---

## 10. How to use this document

If you are an LLM helping with this project:
- For **README**: pull from §1, §2, §8
- For **pitch deck**: pull from §7 with quantified numbers from §3.4, §4.8, §5.3
- For **technical Q&A**: deep-dive sections §3, §4, §5
- For **scoring rationale**: the "Scoring Coverage" tables at the end of each part section
- For **demo script**: §7 step 3
- Always preserve the **responsible-AI** framing from §6.2 — it's a differentiator the jury will remember
