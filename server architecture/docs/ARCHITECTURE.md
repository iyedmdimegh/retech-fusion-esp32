# NRTF Phase 2 — Architecture & Data Pipelines

> Snapshot of the system as it exists today (2026-05-03). What's wired,
> what's stubbed, what flows through which pipe. Read this alongside
> [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) (deeper schema reference) and
> [forecasting_and_anomaly_detection.md](forecasting_and_anomaly_detection.md)
> (M12 design + status).

---

## 1. The big picture in one diagram

```
                                                     Phase 3 (separate teammate)
                                                            ▲
                                                            │ canonical features + flags
                                                            │
   ┌──────────────────────┐    ┌─────────────────────────────┴──────────────────────┐
   │ ESP32 nodes (Phase 1)│    │                  NRTF Phase 2  (this repo)         │
   │  publishes via MQTT  │───▶│  Postgres + TimescaleDB · Redis · Mosquitto        │
   └──────────────────────┘    │  FastAPI  ·  RQ workers  ·  drop-folder watcher    │
                               │  MQTT subscriber  ·  XGBoost + IsolationForest     │
                               └────────────────────────────┬───────────────────────┘
                                                            │
                                            CORS-allowed fetch on :5173
                                                            ▼
                              ┌──────────────────────────────────────────┐
                              │  Vite + React + TS (frontend-app/)       │
                              │  /plant-1/energy /co2 /upload /assistant │
                              └──────────────────────────────────────────┘

   ┌──────────────────────┐
   │ BILAN Excel reports  │───▶ drop into inbox/xlsx/  or  POST /api/ingest/upload
   └──────────────────────┘

   ┌──────────────────────┐
   │ PDFs / scanned images│───▶ drop into inbox/pdf/   or  POST /api/ingest/upload
   └──────────────────────┘
```

---

## 2. Where we are right now

### Working end-to-end ✅

* **Live MQTT ingestion** — ESP32 publishes JSON every 10 s to
  `retech/devices/+/readings` on the broker at `192.168.137.1:1883`. The
  subscriber dedups via the `readings_dedup_key` UNIQUE constraint and
  drops pre-NTP messages (year < 2020). 60+ rows verified across
  bme280 / bmp280 / ds18b20 / acs712 sensors.
* **BILAN Excel ingestion** — drop or upload, watcher picks up, RQ worker
  parses (`bilan/parser.py`), maps via `mapping.yaml`, dedups within file,
  COPYs into `timeseries.bilan_readings`, then runs three validators
  (range / monotonic / whole-column-zero). Idempotent on file SHA-256.
  ~143 k rows from the April sample, plus the user's October file
  (~5 k clean hourly rows after delta).
* **CO₂ analytics (M12, complete)** — `analytics.co2_hourly` populated
  via `build_co2_dataset()`; three XGBoost forecasters trained at
  +1 h / +6 h / +24 h horizons, IsolationForest fit on engineered
  feature matrix (29 features), `predict_rolling_multistep` produces a
  continuous 24-step forecast curve anchored on the last data point.
  Models persisted to `data/models/`.
* **Document OCR (M8)** — drop a PDF/image (`.pdf .jpg .png .tiff .webp`),
  pdf2image renders, Tesseract OCRs (French; auto-retry French+Arabic on
  Arabic-script detection), text + per-page confidence land in
  `documents.ocr_pages`. Images cached to `data/ocr_cache/{hash}/`.
* **Frontend** — Vite + React + TS. Four routes: `/plant-1/energy`,
  `/plant-1/co2`, `/plant-1/upload`, `/plant-1/assistant`. Live data
  through TanStack Query, openapi-typescript-generated client, vendored
  fonts so the demo survives a Wi-Fi outage.

### Stubbed / deferred ⚠

* **Document structured extraction** (M9) — OCR runs and stores text +
  `extraction_status='pending'`, but no Qwen / regex extractor turns it
  into structured invoice fields yet. Deferred to checkpoint 2.
* **Assistant** — `/plant-1/assistant` shows the prototype's chat UI with
  hardcoded canned responses + a "demo placeholder" banner. Real LLM
  with RAG over the unified data is checkpoint-2 work.
* **MQTT live readings panel in the frontend** — backend is live and
  growing rows by the second, but no `/plant-1/devices` page yet.
  Quick add when needed (~30 min).

### What's deliberately out of scope

* Multi-factory anything — Plants 2–5 in the sidebar are explicit
  "awaiting first data ingestion" stubs. We have one cogen plant
  (`esp32_node_01` / `insat_lab_zone_a`).
* WebSocket / SSE streaming — polling at 5–10 s is enough for the
  demo.
* Auth — there is none.

---

## 3. Tech stack

| Layer | Choice | Why |
|---|---|---|
| DB | Postgres 16 + TimescaleDB | Hypertables for time-series, regular tables for documents + analytics |
| Cache / queue | Redis 7 | RQ job queue |
| Broker | Mosquitto 2 | What Phase 1 publishes to |
| API | FastAPI + uvicorn (async) | Auto OpenAPI at `/docs`, type-checked client gen on the frontend |
| ORM | SQLAlchemy 2.x async + asyncpg | Reads / writes from API |
| Migrations | Alembic | One linear chain (`001` → `002` → `005`) |
| Bulk inserts | `psycopg[binary]` COPY | ~100× faster than ORM for ~150 k BILAN rows |
| Excel parser | openpyxl | |
| Fuzzy match | rapidfuzz `token_sort_ratio` | spec said `token_set_ratio` but it scores subsets at 100 → wrong; documented |
| YAML | PyYAML | metric mapping + ranges + flags |
| PDF render | pdf2image + system poppler | |
| OCR | pytesseract + system tesseract (`fra` + `ara` packs) | |
| Image proc | Pillow + opencv-python-headless | Deskew + adaptive threshold + denoise |
| Worker | RQ + `SimpleWorker` on Windows | `os.fork` doesn't exist on Windows |
| File watcher | watchdog + `PollingObserver` on Windows / WSL | native ReadDirectoryChangesW / inotify is flaky on Win volumes & WSL2 9P mounts |
| MQTT client | paho-mqtt (sync, with sync psycopg writes) | paho threading + asyncio is a known hazard |
| Forecasting | XGBoost + scikit-learn (IsolationForest) + joblib | Right-sized for ~5 k rows, explainable, fits in RAM |
| Logging | structlog | JSON in prod, console locally |
| Frontend | Vite + React 19 + TypeScript 5.7 | No Next, no Router 7 |
| Server state | TanStack Query v5 | Polling, cache invalidation |
| API client | openapi-fetch + openapi-typescript codegen | Types regenerated from `/openapi.json` |
| Routing | react-router-dom v6 | Plain BrowserRouter |
| Charts | hand-rolled SVG (`LineChart`, `SignedBarChart`, `BarChart`, `Sparkline`, `CarbonGauge`) ported from the Claude Design prototype | Zero charting deps |
| Drop-zone | react-dropzone | |

---

## 4. Process model — what runs where

Five processes for a fully-live demo:

```
┌────────────────────────────────────────────┐
│ Docker stack (always on)                   │
│   retech_postgres   :55432                 │
│   retech_redis      :6379                  │
│   retech_mosquitto  :1883                  │
└────────────────────────────────────────────┘

  ▲ all four below need .env loaded → run from project root

t1: API           python -m uvicorn retech_part2.api.main:app --port 8000
t2: RQ worker     python -m retech_part2.workers.run_worker
t3: drop watcher  python -m retech_part2.ingestion.watcher
t4: MQTT subscriber  python -m retech_part2.ingestion.mqtt.run_subscriber

t5: frontend      cd frontend-app && npm run dev    # → http://localhost:5173
```

Every Python entry point calls `apply_windows_event_loop_policy()` (from
`_compat.py`) before doing anything async — the default `ProactorEventLoop`
on Windows breaks asyncpg cleanup when a process calls `asyncio.run()`
repeatedly. The MQTT subscriber sidesteps this entirely by being pure-sync.

---

## 5. The three input pipelines

### 5a. BILAN Excel pipeline

Real industrial monthly report. ~50 columns of cumulative meters at ~10-min
cadence. Dates have a locale-swap bug, the time column has a verbose label,
gap columns lack timestamps, ~912 rows have intra-file duplicates.

```
inbox/xlsx/foo.xlsx       (or POST /api/ingest/upload)
       │
       ▼
watcher (PollingObserver) waits for size to stabilise → sha256
       │
       ▼
shared enqueue helper: dedup against meta.ingestion_jobs → enqueue RQ task
       │
       ▼
RQ worker runs ingestion.bilan.loader.ingest_bilan
   1.  dedup against meta.bilan_files (cleanup stale pending/failed rows)
   2.  parser.parse_bilan(file)              (handles dates / merged cells / gaps / dups)
   3.  mapping.match(raw_label, category) → canonical metric_id
   4.  intra-file dedup by (time, metric_id)        — ~912 dropped on April sample
   5.  INSERT meta.bilan_files (status='pending')
   6.  psycopg COPY into timeseries.bilan_readings  (sync conn, separate from async session)
   7.  validator.apply_range_checks         → 'range_violation' flag
   8.  validator.apply_monotonic_checks     → 'monotonic_inversion' flag
   9.  validator.apply_whole_column_zero_check → 'whole_column_zero' flag
  10.  UPDATE meta.bilan_files: rows_inserted, warnings, final status
       │
       ▼
data_quality_flags TEXT[] on each row
   downstream queries CHOOSE to filter or include
```

The seven landmines from the parser brief are each baked into a test in
[test_bilan_dates.py](../tests/test_bilan_dates.py),
[test_bilan_parser.py](../tests/test_bilan_parser.py),
[test_bilan_mapping.py](../tests/test_bilan_mapping.py),
[test_bilan_ingestion.py](../tests/test_bilan_ingestion.py).

### 5b. Document (PDF / image) pipeline — M8 (OCR-only)

```
inbox/pdf/invoice.pdf       (or .jpg .jpeg .png .tiff .webp, or POST upload)
       │
       ▼
watcher → shared enqueue → RQ worker → task_ingest_invoice
       │
       ▼
ingestion.pdf.pipeline.ingest_invoice
   1.  dedup against documents.documents on file_hash
   2.  preprocessing.load_pages(file)        (PDF → pdf2image, image → PIL[1])
   3.  INSERT documents.documents (extraction_status='pending')
   4.  for each page:
        a. cache RGB image at data/ocr_cache/{hash}/page_{n}.png
        b. preprocess_for_ocr (grayscale → deskew → adaptive threshold → denoise)
        c. ocr_page (Tesseract; 'fra', retry 'fra+ara' if Arabic chars detected)
        d. INSERT documents.ocr_pages (text, ocr_confidence, image_path)
```

`extraction_status` stays `pending` — M9 will populate
`documents.invoices` + `documents.invoice_line_items` when it lands.

### 5c. MQTT live ingestion (M11)

```
ESP32 every 10 s    publishes JSON to  retech/devices/{device_id}/readings (QoS 0 + app retry)
       │
       ▼
MqttSubscriber (paho-mqtt, sync, dedicated psycopg connection)
   on_message:
     1.  json.loads
     2.  EspReadingsPayload.model_validate
     3.  drop if timestamp.year < 2020   (pre-NTP)
     4.  upsert meta.devices              (last_seen = NOW())
     5.  per element in payload.readings:
          INSERT timeseries.readings ON CONFLICT ON CONSTRAINT readings_dedup_key DO NOTHING
     6.  INSERT timeseries.device_status   (status, rssi, uptime_s, fw_version)
   heartbeat thread emits counters every 30 s

scripts/replay_mqtt_jsonl.py reuses process_payload — same writes, same
dedup, but reads from a JSONL file. Demo-day backup if the broker / ESP32
isn't available.
```

---

## 6. The analytics pipeline (M12 — CO₂ forecasting + anomaly)

The most layered pipe. Read alongside the 7 formula corrections in
[forecasting_and_anomaly_detection.md §4](forecasting_and_anomaly_detection.md).

```
timeseries.bilan_readings
       │ (filter: data_quality_flags must NOT contain whole_column_zero or monotonic_inversion)
       ▼
analytics.co2.pipeline.build_consumption_series
   pull cumulative meters → resample to 1h → ffill → diff → clip neg on gas+elec
   PRESERVE sign on grid_net (cogen export → negative)
       │
       ▼ apply emission factors (1.96 kg/Nm³, 0.47 kg/kWh — env-overridable)
analytics.co2.pipeline.build_co2_dataset
   adds co2_gas_kg, co2_grid_kg (signed!), co2_total_kg
       │
       ▼
analytics.co2.train.run_full_training
   1.  engineer_features  (lags 1/3/6/12/24/48/168h, rolling 3/6/12/24h
                           mean/std/min/max, calendar features) — 29 features
   2.  per horizon h ∈ {1, 6, 24}: shift target -h, 80/20 chronological split,
       XGBRegressor(400 trees, depth 6, lr 0.05), measure MAE/RMSE/MAPE,
       save to data/models/co2_total_h{h}.pkl
   3.  IsolationForest on the SAME engineered feature matrix
       (NEVER on raw cumulative columns), contamination 0.02
   4.  WIPE & REPOPULATE analytics.co2_hourly with full series + per-row flags
   5.  WIPE & INSERT analytics.co2_models (deactivate old active rows;
       partial unique index enforces "one active per (target, horizon)")
   6.  predict_rolling_multistep — roll the h=1 model forward 24 hours,
       feeding each prediction back into the feature vector → 24 hourly
       forecasts. forecast_made_at = ANCHOR (last data row), not wall-clock.
   7.  WIPE & INSERT 24 rows into analytics.co2_forecasts
       │
       ▼
GET /api/co2/series        → analytics.co2_hourly
GET /api/co2/breakdown     → SUM totals from co2_hourly + share %
GET /api/co2/forecast      → 24 rows from co2_forecasts + RMSE bands from co2_models
GET /api/co2/anomalies     → rows where is_anomaly=true, sorted by score
GET /api/co2/models/status → active rows from co2_models
POST /api/co2/retrain      → re-runs run_full_training synchronously (~5–15 s)
```

The frontend's `/plant-1/co2` page consumes all six. The chart filters out
`co2_total_kg = 0` rows (multi-file `ffill` artifacts) and rows >50,000 kg
(cross-file `.diff()` outliers) before rendering — both are real artifacts
when multiple BILAN files with month-long gaps are mixed.

---

## 7. Database schema — what holds what

Three logical Postgres schemas, plus the new `analytics` schema added in
M12. Full column-level reference is in
[PROJECT_HANDOFF.md §6](PROJECT_HANDOFF.md). Quick map:

| Schema | Table | Role |
|---|---|---|
| `meta` | `devices` | one row per ESP32 (live MQTT upserts here) |
| `meta` | `bilan_files` | one row per ingested BILAN file; idempotency on `file_hash` |
| `meta` | `ingestion_jobs` | every upload / drop / retrain — pending → running → success / partial_success / failed |
| `timeseries` | `readings` | live ESP32 readings (hypertable). UNIQUE `(device_id, time, sensor, type)` for dedup |
| `timeseries` | `device_status` | one row per MQTT message: status, RSSI, uptime, fw_version |
| `timeseries` | `bilan_readings` | the analytical heart — UNIQUE `(file_id, time, metric_id)`, `data_quality_flags TEXT[]` |
| `documents` | `documents` | one row per uploaded file; `extraction_status` lifecycle |
| `documents` | `ocr_pages` | per page: cached image path + OCR text + per-word mean confidence; French FTS GIN index |
| `documents` | `invoices` + `invoice_line_items` | empty until M9 lands |
| `analytics` | `co2_hourly` | hypertable, materialised by training; per-hour CO₂ + flags |
| `analytics` | `co2_forecasts` | hypertable; 24 hourly rows from the rolling multi-step |
| `analytics` | `co2_models` | model registry; partial UNIQUE INDEX `WHERE is_active = TRUE` for current-active selection |

Migrations: `001_initial_schema` → `002_readings_dedup_constraint` (M11) →
`005_analytics_schema` (M12). Numbers 003 / 004 were planned for the
M9-stub doc-subtype tables but the checkpoint pivot dropped that scope —
the chain is contiguous, the gap is intentional.

---

## 8. Frontend — what each page does

Routes wrapped in a single `Shell` (sidebar + topbar with API health pill).

| Route | Page | Wires to | Components |
|---|---|---|---|
| `/plant-1/energy` | EnergyPage | `/api/bilan/files`, `/api/bilan/consumption`, `/api/bilan/top-metrics` | LineChart × 2, SignedBarChart, KPI cards × 3 with Sparklines, RankList |
| `/plant-1/co2` | Co2Page | `/api/co2/{series,breakdown,forecast,anomalies,models/status,retrain}` | HeroKPI, KPI cards × 2 with Sparklines, CarbonGauge, LineChart (actual + 24-step rolling forecast), 3 forecast detail cards, anomalies table, models registry, retrain button |
| `/plant-1/upload` | UploadPage | `/api/ingest/upload`, `/api/jobs?type=bilan`, `/api/jobs/{id}` | react-dropzone, polled JobProgress card, recent-jobs table |
| `/plant-1/assistant` | ChatbotPage | nothing (canned responses) | "demo placeholder" banner + chat UI from prototype |

Everything else from the prototype (multi-factory comparison, hardcoded
machine names, real-time-status pill driven by random walk, etc.) is
intentionally absent because there's no real data behind it.

---

## 9. The seven Windows-specific fixes (don't undo these)

These are baked in. Each was burned-in the hard way during M2 / M7 / M11
verification.

1. **Postgres host port = 55432**, not 5432. A system PostgreSQL service
   squats on 5432. `.env` overrides; `.env.example` documents.
2. **Use `timescale/timescaledb:latest-pg16`**, NOT `-ha`. The Spilo HA
   image silently ignores `POSTGRES_USER` / `PASSWORD` / `DB`.
3. **Every Python entry point calls `apply_windows_event_loop_policy()`**.
   The default `ProactorEventLoop` blows up asyncpg cleanup on repeated
   `asyncio.run()`.
4. **`reset_db_cache_for_new_loop()` before each `asyncio.run()`** in
   long-lived processes (workers, watcher).
5. **`SimpleWorker` on Windows.** RQ default uses `os.fork()`.
6. **`PollingObserver` on Windows / WSL.** Native FS watchers are flaky
   on Win volumes & WSL2 9P mounts.
7. **PIL `MAX_IMAGE_PIXELS = 500_000_000`.** The default 178M trips on
   our PDFs at 300 DPI.

---

## 10. CLIs you can run any time

```powershell
# pure parser, no DB
python -m retech_part2.ingestion.bilan.parser data/samples/avril-report1_2442026.xlsx

# mapping table (raw_label, category) → metric_id for any file
python -m retech_part2.ingestion.bilan.mapping data/samples/avril-report1_2442026.xlsx

# real ingest with diagnostics + idempotency check
python -m retech_part2.ingestion.bilan.loader data/samples/avril-report1_2442026.xlsx

# RQ worker task synchronously (bypasses queue)
python -m retech_part2.workers.tasks ingest_bilan_path data/samples/avril-report1_2442026.xlsx

# full CO₂ training run (forecasters + anomaly detector)
python -m retech_part2.analytics.co2.train

# OCR every fixture under data/samples/invoices/
python scripts/ocr_fixtures_report.py

# user-supplied factor CO₂ estimate (separate from M12 model)
python scripts/co2_simple_estimate.py

# replay MQTT JSONL — demo-day fallback
python scripts/replay_mqtt_jsonl.py data/fixtures/mqtt_recording_sample.jsonl

# seed the fake device row (idempotent)
python scripts/seed_db.py
```

---

## 11. Honest weaknesses of the current state

* **Multi-file mix in CO₂ training** — when you ingest a second BILAN
  file that doesn't temporally adjoin the first (April + October, with
  May–Sept missing), `resample('1h').ffill()` produces a long flat run
  followed by a single huge `.diff()` jump. The training currently sees
  this. The frontend filters the artifacts at render time. The right
  fix is **per-`file_id` training** — `analytics.co2_hourly` keyed on
  `file_id`, the page picks one to display. ~30 min when you want it.
* **Forecast bands are wide** — RMSE on h=24 is comparable to the mean
  prediction. Honest. With ~5 k rows of noisy two-file data, the band
  reflects real uncertainty.
* **MAPE on h=24 is ~1.0** — useless metric here because the test set
  has rows where actual ≈ 0. MAE / RMSE are what to trust.
* **Document path stops at OCR** — fixtures are uploaded, OCR'd, and
  searchable via French FTS, but no structured fields are extracted.
* **No auth on any endpoint, no rate limiting.** Demo only.
* **CSV / Parquet export endpoints not implemented** — was on the
  M10 list, never landed (the demo doesn't use them).

---

## 12. Where to look for what

* Architecture / data flow → **this file**
* Schema details (every column) → [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md)
* Forecasting / anomaly design + corrections → [forecasting_and_anomaly_detection.md](forecasting_and_anomaly_detection.md)
* Past milestone state for an LLM picking up cold → [checkpointM8.md](checkpointM8.md)
  (predates M9-stub deferral and M11–M15+ work but still useful for the
  early decisions)
