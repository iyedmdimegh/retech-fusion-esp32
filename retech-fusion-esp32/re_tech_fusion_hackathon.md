# Re·Tech Fusion — Industrial AI & IoT Hackathon
**INSAT — University of Carthage**

> End-to-end intelligent system: raw IoT sensor data → predictive modeling → anomaly detection → actionable insights.

---

## 🏗️ Challenge Overview

Industrial companies manage multiple sites, acquired subsidiaries, and heterogeneous energy data. Consolidating energy data for CO₂ emission calculations is currently slow, manual, error-prone, and not scalable.

**Core focus:** document extraction, unit normalization, and CO₂ estimation.

Teams are encouraged to prioritize **depth over breadth**. Innovation is always rewarded.

---

## 📅 Timeline

| Time | Event |
|---|---|
| Day 1 — 14:00 | Opening Ceremony |
| Day 1 — 23:00 | Part 1 Announcement |
| Day 2 — 14:00 | Part 1 Submission Deadline |
| Day 2 — Midnight | Part 2 Submission Deadline + Part 3 Announcement |
| Day 3 — 05:00 | Part 3 Submission Deadline + Start of 1-Hour Grace Period |
| Day 3 — 07:00 | Presentation Submission Deadline |
| Day 3 — 09:00 | Pitching Session Starts |

- **Team size:** 5 members
- **Late penalty:** 20% per hour, per part

---

## Part 1 — IoT Device & Protocol
**Announced:** Day 1 at 23:00 | **Deadline:** Day 2 at 14:00

### Objective
Build a connected device or software client that reads from multiple sensors and transmits data reliably, securely, and continuously to a server.

### Deliverables
- Physical IoT device (ESP32, Arduino with BT/WiFi, LoRa, etc.) OR software simulator
- At least 3 distinct sensor types (e.g. CO₂, temperature, power consumption, humidity, pressure, IMU…)
- Continuous data transmission via **HTTP POST** or **MQTT**
- README documenting setup, sensor types, and connection method

### Scoring

| Criterion | Description | Points |
|---|---|---|
| Solution functional | Server receives valid data within timeframe | 30 |
| Multi-sensor coordination | Distinct sensor types, correct units, all active simultaneously | 25 |
| Protocol design & security | Reconnection handling, optional TLS/HTTPS | 15 |
| Uptime & continuity | % of 5-min windows with ≥1 valid message | 15 |
| Data quality | % of values within valid physical ranges (no null, no -999) | 10 |
| **Bonus — Innovation** | OTA update, device-side buffering, custom sensors | +15 |

### Advantages
- Automatic disconnection handling and reconnects without data loss
- Factory-style documentation format

---

## Part 2 — Data Pipeline, Unification & Modeling
**Deadline:** Day 3 at 00:00 (25 hours)

### Context
Energy data is heterogeneous: different suppliers, different document formats (PDF invoices, scanned bills, Excel tables), and different measurement units. Teams must build a coherent pipeline unifying everything for CO₂ estimation, anomaly detection, and a functional dashboard.

### Test Dataset (distributed at 00:00)
- Heterogeneous energy documents: PDFs, scanned bills, multi-sheet Excel files
- Mixed units: **kWh, MWh, Gcal, BTU, toe, GJ** → all must normalize to one unit
- Ground-truth annotation file for model validation
- IoT readings from Part 1

### Deliverables

#### 2.1 — Data Extraction & Unification Pipeline
- Automatic extraction: date, energy quantity, unit, supplier, site
- Unit normalization to canonical unit (**kWh recommended**) with traceable conversion factors
- Merge document data with IoT sensor data into unified timestamped framework
- Business-layer dashboard: KPIs, gains, losses, anomalies
- Fully reproducible pipeline — no manual interventions

#### 2.2 — CO₂ Emission & Energy Modeling
- CO₂ estimation from unified energy data using emission factors
- Energy trend forecasting (short-term minimum, multi-horizon ideal)
- **(Optional)** Anomaly & fault detection in IoT stream and document data
  - Each anomaly must include: type, timestamp, sensor/site, confidence score

#### 2.3 — Interface & Dashboard
- Visual dashboard: unified data, CO₂ KPIs, trends, anomalies
- Any technology accepted: Grafana, React, Streamlit, plain HTML
- Must be **live-testable**

### Scoring

| Criterion | Description | Points |
|---|---|---|
| Document extraction accuracy | F1 score across all test documents | 40 |
| Unit normalization accuracy | Accuracy on organizer-prepared conversions | 25 |
| CO₂ estimation quality | Prediction vs. ground truth reference values | 15 |
| Dashboard quality | Jury: clarity, relevance, usability | 20 |
| Dockerized pipeline | `docker compose up` from cold start, API documented | 20 |
| **Bonus — Anomaly detection** | Detection with ground truth scoring | +15 |
| **Bonus — Innovation** | Novel algorithm, creative visualization, extra data sources | +25 |

### Submission Methods
- GitHub repo with README, code, and demo video/screenshots
- POST extraction results as JSON to challenge platform (instant F1 score feedback)
- Live demo URL if deployed

### Minimum Viable Solution
- Basic extraction from at least one document type (PDF or Excel)
- Correct unit normalization to kWh
- A simple dashboard

---

## Part 3 — Edge Intelligence OR Energy Recovery Design
**Announced:** Day 2 Midnight | **Deadline:** Day 3 at 05:00

> Choose one track or attempt both for maximum points.

---

### Track A — Edge Inference & On-Device Anomaly Detection

**Objective:** Deploy a lightweight model directly on the microcontroller. When network fails, the device continues operating intelligently — predicts sensor values, detects anomalies locally, and resumes cloud sync on reconnect.

#### Deliverables
- Trained predictive model compressed for constrained hardware (ESP32, RPi Zero, or emulated)
- Model size within hardware RAM constraints
- Inference latency < 200ms on device
- Local anomaly detection without server contact
- Evidence of deployment: photo, video, or emulator log

#### Scoring

| Criterion | Description | Points |
|---|---|---|
| Model size constraint met | Binary check | 15 |
| Inference latency on device | Measured average via logs | 10 |
| Prediction accuracy (MAE ratio) | Held-out sequence from Part 2 data | 25 |
| Working model visible & testable | Continuity of service | 25 |
| **Bonus — Multi-sensor model** | Single model predicting multiple sensor types | +15 |

---

### Track B — Waste Heat Recovery Opportunity Design

**Objective:** Design a method or tool to systematically identify, characterize, and rank heat recovery opportunities at an industrial site.

#### Deliverables
- Systematic method/tool to identify waste heat sources from site data
- Characterization of each source: temperature level, thermal flux, availability, location
- Prioritization framework: recoverable energy potential, CO₂ reduction, integration complexity, implementation cost, ROI
- At least **3 concrete recovery scenarios** with quantified impact estimates
- Format: tool, decision model, scored spreadsheet, or software prototype

#### Scoring

| Criterion | Description | Points |
|---|---|---|
| Source identification completeness | Coverage and accuracy of waste heat sources | 20 |
| Prioritization framework quality | Multi-criteria model: rigor, weighting, usability | 25 |
| Quantified impact estimates | Energy, CO₂, and ROI with traceable calculations | 20 |
| Deliverable quality | Clarity, reproducibility, practical applicability | 10 |
| **Bonus — Interactive tool** | Working prototype (simulation, notebook, math evidence) | +15 |

---

## Pitching Session — Top Teams
**Day 3 starting at 08:30 | 15 min per team (8 min presentation + 7 min Q&A)**

### Format

| Section | Expected Content |
|---|---|
| 8 min presentation | Problem framing, architecture overview, key design decisions, what you'd do with more time |
| 7 min Q&A | Technical choices, failure modes, scalability, business applicability |

### Scoring

| Criterion | Description | Points |
|---|---|---|
| Technical depth + jury decision | Understanding of algorithms, trade-offs, failure modes | 35 |
| Scalability & industrial relevance | Would it work at real scale? Does it address sponsor needs? | 25 |

### Tips for a Great Pitch
- **Show end-to-end data flow:** device → server → pipeline → dashboard → anomaly alert in one demo
- **Quantify everything:** uptime %, F1 score, model size in KB, CO₂ kg saved, money on the table
- **Acknowledge what broke** and how you fixed it — juries trust self-aware teams
- **Connect to sponsor's actual problem:** heterogeneous formats, scalability

---

## 📋 Rules

- Teams of up to 5 participants — no cross-team code/model collaboration
- All code must be original or use open-source libraries with compatible licenses
- LLM use is permitted — teams are accountable for results
- All submissions pushed before **Day 3 at 05:00** (late = 20% penalty per hour per part)
- Teams are responsible for their own network, power, and hardware

---

## 🔧 Suggested Tools & Libraries

- **IoT/Firmware:** Arduino, ESP-IDF
- **MQTT client:** `paho-mqtt` (Python)
- **JSON on microcontrollers:** ArduinoJson
- **API testing:** Postman, curl
- **Dashboard:** Grafana, React, Streamlit, plain HTML
- **Containerization:** Docker Compose

---

*Note: Recommendations are suggestions only. Any technology, language, or methodology is accepted. Sometimes the best results come from algorithmic/science-inspired methods rather than sophisticated models — don't be afraid to experiment.*
