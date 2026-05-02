# Re-Tech Fusion (NRTF) Phase 2 — Teammate Handoff

> Read this before touching the code. It explains what we're building, where
> we are right now, every database table, the data flow end-to-end, every
> entry point, every CLI, and how to run the whole stack from scratch.

---

## 1. The big picture

Phase 2 of NRTF is the **data platform** for the INSAT Re-Tech Fusion
hackathon. It sits between three input sources and one downstream consumer:

```
   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │ ESP32 / MQTT │    │ BILAN Excel  │    │ PDF / image  │
   │ (Phase 1)    │    │ reports      │    │ invoices     │
   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
          │ live                │ batch             │ scanned
          │ (deferred)          │                   │
          ▼                     ▼                   ▼
        ┌────────────────────────────────────────────────┐
        │           NRTF Phase 2 — this project          │
        │  Postgres + TimescaleDB · Redis · Mosquitto    │
        │  FastAPI · RQ workers · drop-folder watcher    │
        └────────────────────────────────────────────────┘
                              │
                              ▼ query / export (CSV / Parquet)
                  ┌─────────────────────────┐
                  │ Phase 3 — edge ML       │
                  │ (separate teammate)     │
                  └─────────────────────────┘
```

Other teammates own Phase 1 (firmware) and Phase 3 (ML). **We expose the
data; we don't model it.**

---

## 2. Status — where we are right now

We work in milestones. Each milestone is independently verifiable.

| ID  | Milestone                                | Status          |
|-----|-------------------------------------------|-----------------|
| M1  | Bootstrap (Docker, FastAPI skeleton)      | done            |
| M2  | Database schema + Alembic migration       | done            |
| M3  | BILAN dates module + tests                | done            |
| M4  | BILAN structural parser + tests           | done            |
| M5  | Semantic mapping + canonical metric IDs   | done            |
| M6  | BILAN ingestion to TimescaleDB            | done            |
| M7  | File-upload API + drop-folder watcher + RQ | done           |
| M8  | PDF/OCR pipeline (Tesseract, multi-format) | done           |
| **M9**  | **Structured invoice extraction (Qwen + regex)** | **next up** |
| M10 | Query / search / export endpoints, README polish | pending |

**What works today end-to-end:**

* Drop a BILAN `.xlsx` into `inbox/xlsx/` (or `POST /api/ingest/upload`) →
  a job appears in `/api/jobs` → ~140k normalised rows land in
  `timeseries.bilan_readings`. Idempotent (re-uploading is a no-op).
* Drop a `.pdf`, `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`, or `.webp` into
  `inbox/pdf/` (or upload) → Tesseract OCR runs, image gets cached, text +
  per-page confidence land in `documents.ocr_pages`. The structured fields
  (vendor, invoice number, total, line items) **stay empty until M9**.
* MQTT broker is up and the schema for live readings is deployed, but no
  subscriber is wired (Phase 1 hardware not ready).

---

## 3. Tech stack

| Layer       | Choice                              | Why                                                 |
|-------------|-------------------------------------|-----------------------------------------------------|
| DB          | Postgres 16 + TimescaleDB extension | Hypertables for time-series, Postgres for documents |
| Cache/queue | Redis 7                             | RQ job queue                                        |
| Broker      | Mosquitto 2                         | Phase 1 will publish here                           |
| API         | FastAPI + uvicorn (async)           | Auto OpenAPI at `/docs`                             |
| ORM         | SQLAlchemy 2.x async + asyncpg      |                                                     |
| Migrations  | Alembic                             |                                                     |
| Validation  | Pydantic v2 + pydantic-settings     |                                                     |
| Bulk inserts| `psycopg[binary]` COPY              | ~100x faster than ORM for the BILAN bulk path      |
| Excel       | `openpyxl`                          |                                                     |
| Fuzzy match | `rapidfuzz` (`token_sort_ratio`)    |                                                     |
| YAML        | `PyYAML`                            |                                                     |
| PDF render  | `pdf2image` + `poppler` (system)    |                                                     |
| OCR         | `pytesseract` + `tesseract` (system, `fra` + `ara` packs) |        |
| Image proc  | `Pillow`, `opencv-python-headless`  | Deskew, threshold, denoise                          |
| Worker      | `rq` (`SimpleWorker` on Windows)    |                                                     |
| File watch  | `watchdog` (`PollingObserver` on Windows/WSL) |                                          |
| Logging     | `structlog`                         | JSON in prod, console locally                       |

Python 3.11+. Managed with `pip install -e ".[dev]"` (uv is not installed
in our dev env, but the `pyproject.toml` is uv-compatible).

---

## 4. Architecture

```
                ┌──────────────────────────────────────────┐
                │              FastAPI (REST)              │
                │  /health  /api/ingest/upload             │
                │  /api/jobs  /api/jobs/{id}               │
                │  + auto OpenAPI at /docs                 │
                └────────────┬───────────────┬─────────────┘
                             │               │
              ┌──────────────┘               └──────────────┐
              │                                             │
     ┌────────▼─────────┐                          ┌────────▼────────┐
     │   Postgres +     │                          │     Redis       │
     │   TimescaleDB    │                          │  (RQ queue)     │
     │  schemas:        │                          └────────┬────────┘
     │   timeseries     │                                   │
     │   documents      │                          ┌────────▼────────┐
     │   meta           │                          │   RQ Worker     │
     └────────▲─────────┘                          │  • bilan parse  │
              │                                    │  • pdf OCR      │
              │ inserts                            │  • mqtt (stub)  │
              └────────────────────────────────────┴────────┬────────┘
                                                            │
              ┌──────────────┬──────────────────────────────┘
              │              │
       ┌──────┴──────┐  ┌────┴───────────┐
       │ inbox/xlsx/ │  │  inbox/pdf/    │  ← also accepts .jpg .png
       │ (watchdog)  │  │  (watchdog)    │     .tiff .webp
       └─────────────┘  └────────────────┘

       ┌─────────────────────┐
       │  Mosquitto          │ (deployed, idle until Phase 1 ready)
       │  topic: retech/...  │
       └─────────────────────┘
```

Three separate processes when running:

1. **API** — `make api` → uvicorn on port 8000.
2. **Worker** — `make worker` → consumes RQ jobs (sync, runs each ingest).
3. **Watcher** — `make watcher` → polls inbox folders, enqueues new files.

The API and watcher both call the same shared **`workers.enqueue.enqueue_file()`**
helper to dedup and create jobs, so dropping a file or POSTing it produces
identical results.

---

## 5. The three input pipelines

### 5a. BILAN Excel pipeline (the heavily-graded one)

Input: a monthly Excel file from the cogeneration plant
(`avril-report1_2442026.xlsx` is our reference). 850 KB, 50+ industrial
parameters logged ~every 10 min for 20 days.

```
  inbox/xlsx/foo.xlsx
        │
        ▼
  watcher (PollingObserver) waits for file size to stabilise
        │
        ▼
  workers.enqueue.enqueue_file:
    sha256 → check meta.ingestion_jobs for existing → enqueue or return existing
        │
        ▼
  RQ worker picks up "task_ingest_bilan(file_path, job_id)"
        │
        ▼
  ingestion.bilan.loader.ingest_bilan:
    1. dedup against meta.bilan_files (status in success/partial_success → no-op)
       cleanup any stale 'pending'/'failed' rows
    2. parser.parse_bilan(file)        ── M3+M4
       returns ParsedBilan with ~143k ParsedReadings
    3. resolve every (raw_label, category) via mapping.match()  ── M5
       drop unmapped, count them
    4. dedup within file by (time, metric_id)   ── M6
       (real source data has ~912 duplicate timestamp rows)
    5. INSERT meta.bilan_files (status='pending')
    6. psycopg COPY into timeseries.bilan_readings  ← sync conn, separate from
                                                       async session, dies in finally
    7. validator.apply_range_checks       (range_violation flag)
       validator.apply_monotonic_checks   (monotonic_inversion flag)
       validator.apply_whole_column_zero_check  (whole_column_zero flag)
    8. UPDATE meta.bilan_files with rows_inserted, warnings, final status
```

#### Landmines the parser handles

The April 2025 sample has six "everyone gets these wrong" gotchas. Each is
hardcoded into a test so we don't regress:

1. **Date locale swap.** Excel parsed `DD/MM/YYYY` as `MM/DD/YYYY` — April 1
   becomes 2025-01-04, April 12 becomes 2025-12-04. Days 13+ couldn't swap
   (no 13th month) so they got dumped as strings. Both formats coexist in
   the same file, switchover around column 1728. See
   [src/retech_part2/ingestion/bilan/dates.py](../src/retech_part2/ingestion/bilan/dates.py).
2. **Header row varies.** "Date" lives in column B at row 10; the time row
   right below has a verbose label
   `"Heure de l'inspection périodique"`. We find Date by literal match,
   then locate the time row **structurally** (next row whose first data
   cell is a `datetime.time`). See `_find_time_row` in
   [src/retech_part2/ingestion/bilan/parser.py](../src/retech_part2/ingestion/bilan/parser.py).
3. **Merged cells in column A** for category labels ("Energie Moteur" spans
   rows 16–25). pandas `ffill()` doesn't see the merge, so we walk
   `ws.merged_cells.ranges` and forward-fill explicitly.
4. **~927 gap columns** with values but no date/time. Two-pass linear
   interpolation between nearest valid timestamps; rows flagged
   `timestamp_synthetic=True`.
5. **Whitespace anomalies in labels** (`"Energie en kWh "`,
   `"Temperature entrée  (TT02)"` with double space). Normalised via
   `re.sub(r"\s+", " ").strip()` before matching.
6. **Empty parameter rows** (row 13, "Puissance électrique nette"). Listed
   in `parameter_summary` with count 0 so M5/M6 know they were seen.
7. **Within-file duplicates** (~912 rows in the sample where two columns
   share the same `(date, time)` for the same metric). Dropped in
   `loader.py` per spec ("trust column order = first wins"). Counted
   separately in `rows_dropped_duplicate_in_file`.

#### Monotonic / range / whole-column-zero validators

After bulk insert, three validator passes mark `data_quality_flags`:

* **`range_violation`** — value outside the YAML's `range: [min, max]`. Runs
  for every metric with a defined range, including `derived: true` ones
  (efficiencies still must fall in 0–100%).
* **`monotonic_inversion`** — for metrics with `monotonic: true` AND not
  `derived: true`, any row where value < previous value (in time order).
* **`whole_column_zero`** — when ≥3 cumulative metrics at the same instant
  all read 0. Distinguishes a system-wide logging gap from a single-meter
  glitch. Always coexists with `monotonic_inversion`.

On the real April sample: 14 metrics flagged with monotonic inversions
(7–32 each), 6 timestamps × 12 metrics = 72 rows tagged whole_column_zero,
0 range violations.

### 5b. Invoice PDF/image pipeline (M8 state)

Same trigger paths as BILAN — drop a file or POST `/api/ingest/upload`.

```
  inbox/pdf/foo.pdf  (or .jpg .png .tiff .webp)
        │
        ▼
  watcher → enqueue → RQ worker → task_ingest_invoice
        │
        ▼
  ingestion.pdf.pipeline.ingest_invoice:
    1. dedup against documents.documents on file_hash
    2. preprocessing.load_pages(file):
         PDF  → pdf2image.convert_from_path (300 DPI, poppler under the hood)
         image → PIL open, convert to RGB, return [image]
       Same shape (list of PIL.Image.Image) regardless of input type.
    3. INSERT documents.documents (extraction_status='pending')
    4. for each page:
         a. cache the original RGB image at data/ocr_cache/{hash}/page_{n}.png
         b. preprocessing.preprocess_for_ocr  (grayscale → deskew → adaptive
            threshold → denoise)
         c. ocr_tesseract.ocr_page  (fra; if Arabic chars detected, retry fra+ara
            and keep higher-confidence result)
         d. INSERT documents.ocr_pages (text, ocr_confidence, image_path)
```

`extraction_status` stays `pending` — M9 will run extraction (Qwen first,
regex fallback) and update it to `done` / `needs_review` / `failed`.

OCR confidence on our 8 contest fixtures: mean 56.3%, median 58.4%, 40% of
pages below 50%. `sxada.pdf` is the worst (every page <42%). M9 needs Qwen
as a workhorse, not just a fallback.

### 5c. MQTT pipeline (deferred)

Schema lives in `timeseries.readings` and `timeseries.device_status` —
both are hypertables, indexed by `(device_id, time DESC)`. The subscriber
class at
[src/retech_part2/ingestion/mqtt/subscriber.py](../src/retech_part2/ingestion/mqtt/subscriber.py)
is a stub that documents the contract:

* topic pattern `retech/devices/+/readings`, QoS 1
* validate payload against `ReadingsPayload` Pydantic model
* upsert `meta.devices`, insert per-reading rows, insert device_status row
* offline detection: if no message in >30s, insert synthetic
  `device_status` row with `status='offline'`

There's also a planned `scripts/replay_mqtt_jsonl.py` for replaying captured
JSONL traces — this is our backup demo path if MQTT isn't ready.

---

## 6. Database schema (every table, every column)

Postgres database `retech`, three logical schemas: `meta`, `timeseries`,
`documents`. Migration:
[alembic/versions/001_initial_schema.py](../alembic/versions/001_initial_schema.py).
ORM mirror: [src/retech_part2/models.py](../src/retech_part2/models.py).
Pydantic response shapes:
[src/retech_part2/schemas.py](../src/retech_part2/schemas.py).

### Schema `meta` — operational metadata

#### `meta.devices`
| Column      | Type        | Role                                        |
|-------------|-------------|---------------------------------------------|
| device_id   | TEXT PK     | ESP32 ID. Currently one fake row from `seed_db.py`. |
| site        | TEXT NOT NULL | Where the device is installed              |
| fw_version  | TEXT        | Last reported firmware                      |
| first_seen  | TIMESTAMPTZ | DEFAULT NOW()                               |
| last_seen   | TIMESTAMPTZ | Updated by MQTT subscriber when wired      |

#### `meta.bilan_files`
One row per ingested BILAN Excel file. `file_hash` UNIQUE = idempotency.

| Column            | Type           | Role                                                     |
|-------------------|----------------|----------------------------------------------------------|
| file_id           | UUID PK        | DEFAULT `gen_random_uuid()`. Foreign keyed by readings.  |
| file_hash         | TEXT UNIQUE NOT NULL | sha256 of the file                                |
| filename          | TEXT NOT NULL  |                                                          |
| parsed_at         | TIMESTAMPTZ    |                                                          |
| date_range_start  | DATE           | min reading time                                         |
| date_range_end    | DATE           | max reading time                                         |
| rows_inserted     | INT            | from COPY                                                |
| rows_dropped      | INT            | unmapped + intra-file duplicates                         |
| unmapped_params   | JSONB          | `[{"raw_label":..,"category":..}, ...]`                  |
| status            | TEXT NOT NULL  | pending / success / partial_success / failed             |
| warnings          | JSONB          | `range_violations_by_metric`, `monotonic_inversions_by_metric`, `whole_column_zero_rows`, `intra_file_duplicates_dropped` |

#### `meta.ingestion_jobs`
One row per upload / drop event. Tracks the worker's lifecycle.

| Column         | Type           | Role                                              |
|----------------|----------------|---------------------------------------------------|
| job_id         | UUID PK        | DEFAULT `gen_random_uuid()`                       |
| job_type       | TEXT NOT NULL  | `bilan` or `invoice`                              |
| source_path    | TEXT           | path under `inbox/`                               |
| file_hash      | TEXT           | for the dedup helper                              |
| status         | TEXT NOT NULL  | pending → running → success / partial_success / failed |
| progress       | INT            | 0..100 (currently 0 or 100, no fine-grained)     |
| error_message  | TEXT           | traceback on failure                              |
| warnings       | JSONB          | dump of IngestionResult counts                    |
| created_at     | TIMESTAMPTZ    | DEFAULT NOW()                                     |
| started_at     | TIMESTAMPTZ    | when worker picked it up                          |
| finished_at    | TIMESTAMPTZ    |                                                   |

Index on `(status, created_at DESC)` for the jobs list endpoint.

### Schema `timeseries` — TimescaleDB hypertables

All three are hypertables partitioned by `time`.

#### `timeseries.readings` (live ESP32 readings, populated by MQTT later)
| Column      | Type             | Role                                                    |
|-------------|------------------|---------------------------------------------------------|
| time        | TIMESTAMPTZ NOT NULL | from the device's clock (NOT NOW(); Phase 1 buffers offline) |
| ingested_at | TIMESTAMPTZ      | when we received it                                     |
| device_id   | TEXT NOT NULL    | FK → `meta.devices.device_id`                           |
| sensor      | TEXT NOT NULL    | `bme280`, `ds18b20`, etc.                               |
| type        | TEXT NOT NULL    | `temperature`, `humidity`, `pressure`                   |
| value       | DOUBLE PRECISION |                                                         |
| unit        | TEXT NOT NULL    |                                                         |

Index `(device_id, type, time DESC)` for typical queries.

#### `timeseries.device_status`
| Column       | Type             | Role                                          |
|--------------|------------------|-----------------------------------------------|
| time         | TIMESTAMPTZ NOT NULL |                                           |
| device_id    | TEXT NOT NULL    |                                               |
| status       | TEXT NOT NULL    | `ok`, `invalid_reading`, `offline`            |
| rssi         | INTEGER          |                                               |
| uptime_s     | BIGINT           |                                               |
| fw_version   | TEXT             |                                               |
| drift_alert  | BOOLEAN          | DEFAULT FALSE                                 |

Index `(device_id, time DESC)`.

#### `timeseries.bilan_readings` (the analytical heart)
| Column                | Type             | Role                                                     |
|-----------------------|------------------|----------------------------------------------------------|
| time                  | TIMESTAMPTZ NOT NULL | normalised by `dates.fix_bilan_date` + interpolation |
| file_id               | UUID NOT NULL    | FK → `meta.bilan_files.file_id`                          |
| metric_id             | TEXT NOT NULL    | canonical ID from `mapping.yaml` (e.g. `gas.flow_rate`)  |
| value                 | DOUBLE PRECISION |                                                          |
| unit                  | TEXT NOT NULL    | from the YAML                                            |
| raw_label             | TEXT NOT NULL    | original column-B string after whitespace normalisation  |
| timestamp_synthetic   | BOOLEAN          | TRUE if `time` was interpolated from neighbours          |
| data_quality_flags    | TEXT[]           | `range_violation`, `monotonic_inversion`, `whole_column_zero` |

`UNIQUE (file_id, time, metric_id)` — enforces idempotency at the row
level, so repeated COPYs can't double-insert.

Indexes: `(metric_id, time DESC)` for time-series queries by metric;
`(file_id)` for bulk delete.

### Schema `documents` — invoices and OCR

#### `documents.documents`
| Column                  | Type           | Role                                              |
|-------------------------|----------------|---------------------------------------------------|
| doc_id                  | UUID PK        | DEFAULT `gen_random_uuid()`                       |
| file_hash               | TEXT UNIQUE NOT NULL | sha256 of the input                         |
| doc_type                | TEXT NOT NULL  | `invoice` for now                                 |
| source_file             | TEXT NOT NULL  | path under `inbox/pdf/`                           |
| page_count              | INT            | 1 for loose images, N for PDFs                    |
| uploaded_at             | TIMESTAMPTZ    | DEFAULT NOW()                                     |
| extraction_status       | TEXT NOT NULL  | pending / done / failed / needs_review            |
| extraction_method       | TEXT           | `qwen_local`, `tesseract_regex` (set in M9)       |
| extraction_confidence   | DOUBLE PRECISION | 0..1 from M9 validator                          |
| extraction_warnings     | JSONB          | per-field flags from M9 validator                 |

After M8 every successfully-OCR'd doc has `extraction_status='pending'` —
M9 sets it to `done`, `needs_review`, or `failed`.

#### `documents.ocr_pages` — one row per page
| Column         | Type             | Role                                          |
|----------------|------------------|-----------------------------------------------|
| doc_id         | UUID NOT NULL    | FK → `documents.documents` ON DELETE CASCADE  |
| page_number    | INT NOT NULL     | starts at 1                                   |
| image_path     | TEXT             | `data/ocr_cache/{hash}/page_{n}.png`          |
| text           | TEXT             | raw Tesseract output                          |
| ocr_confidence | DOUBLE PRECISION | mean per-word conf, 0..1                      |

PRIMARY KEY `(doc_id, page_number)`.
GIN index `ocr_pages_fts` on `to_tsvector('french', COALESCE(text, ''))`
for full-text search.

#### `documents.invoices` — populated in M9
| Column          | Type             | Role                                          |
|-----------------|------------------|-----------------------------------------------|
| doc_id          | UUID PK          | FK → `documents.documents` ON DELETE CASCADE  |
| vendor          | TEXT             |                                               |
| invoice_number  | TEXT             |                                               |
| invoice_date    | DATE             |                                               |
| due_date        | DATE             |                                               |
| currency        | TEXT             | ISO 4217 (TND, EUR, ...)                      |
| subtotal        | NUMERIC(14,2)    |                                               |
| tax             | NUMERIC(14,2)    |                                               |
| total           | NUMERIC(14,2)    |                                               |
| user_edited     | BOOLEAN          | M10 will let users patch fields               |
| edited_at       | TIMESTAMPTZ      |                                               |

#### `documents.invoice_line_items`
| Column      | Type             | Role                                          |
|-------------|------------------|-----------------------------------------------|
| id          | BIGSERIAL PK     |                                               |
| doc_id      | UUID NOT NULL    | FK → `documents.invoices` ON DELETE CASCADE   |
| line_no     | INT              |                                               |
| description | TEXT             |                                               |
| quantity    | NUMERIC          |                                               |
| unit_price  | NUMERIC(14,2)    |                                               |
| line_total  | NUMERIC(14,2)    |                                               |

Index `(doc_id, line_no)`.

---

## 7. Code layout (what lives where)

```
server architecture/
├── docker-compose.yml          # Postgres + Redis + Mosquitto
├── docker/mosquitto/mosquitto.conf
├── pyproject.toml              # all deps pinned
├── alembic.ini
├── alembic/
│   ├── env.py                  # async engine, reads pydantic settings
│   └── versions/001_initial_schema.py   # the ONE schema migration
├── inbox/
│   ├── xlsx/                   # drop BILAN files here (watcher-monitored)
│   └── pdf/                    # drop invoices (.pdf or images) here
├── data/
│   ├── samples/                # committed reference inputs
│   │   ├── avril-report1_2442026.xlsx
│   │   └── invoices/           # the 8 contest fixtures
│   ├── fixtures/               # synthetic test fixtures
│   └── ocr_cache/{hash}/page_N.png   # generated; gitignored
├── scripts/
│   ├── seed_db.py              # one fake device row
│   └── ocr_fixtures_report.py  # M8 verification (run on every fixture)
├── src/retech_part2/
│   ├── _compat.py              # WindowsSelectorEventLoopPolicy
│   ├── config.py               # pydantic-settings, reads .env
│   ├── db.py                   # async engine, session factory, cache reset
│   ├── models.py               # SQLAlchemy 2.x ORM mirror of every table
│   ├── schemas.py              # Pydantic v2 response shapes
│   ├── logging.py              # structlog setup
│   ├── api/
│   │   ├── main.py             # FastAPI app factory + router mounts
│   │   └── routes/
│   │       ├── health.py       # GET /health
│   │       ├── ingest.py       # POST /api/ingest/upload
│   │       ├── jobs.py         # GET /api/jobs, /api/jobs/{id}
│   │       ├── readings.py     # (M2 schema; queries land in M10)
│   │       ├── bilan.py        # (M10)
│   │       ├── documents.py    # (M10)
│   │       ├── search.py       # (M10)
│   │       └── export.py       # (M10)
│   ├── ingestion/
│   │   ├── bilan/
│   │   │   ├── dates.py        # M3 — Excel locale-swap reverser
│   │   │   ├── parser.py       # M4 — structural parser, ParsedBilan
│   │   │   ├── mapping.py      # M5 — YAML loader + match()
│   │   │   ├── mapping.yaml    # M5 — canonical metric definitions
│   │   │   ├── validator.py    # M6 — range / monotonic / whole_column_zero
│   │   │   └── loader.py       # M6 — orchestrates parse→map→COPY→validate
│   │   ├── pdf/
│   │   │   ├── preprocessing.py # M8 — load_pages, preprocess_for_ocr
│   │   │   ├── ocr_tesseract.py # M8 — ocr_page (fra, retry fra+ara)
│   │   │   └── pipeline.py      # M8 — ingest_invoice end-to-end
│   │   ├── mqtt/subscriber.py  # STUB — contract documented
│   │   └── watcher.py          # M7 — PollingObserver on Win/WSL
│   ├── workers/
│   │   ├── enqueue.py          # M7 — shared dedup-and-enqueue helper
│   │   ├── tasks.py            # M7+ — task_ingest_bilan / _invoice
│   │   └── run_worker.py       # M7 — RQ worker entrypoint (SimpleWorker on Win)
│   └── utils/{hashing,files}.py
└── tests/
    ├── conftest.py             # applies WindowsSelectorEventLoopPolicy
    ├── test_bilan_dates.py     # 13 tests (M3)
    ├── test_bilan_parser.py    # 13 tests (M4)
    ├── test_bilan_mapping.py   # 23 tests (M5)
    └── test_bilan_ingestion.py # 1 integration test (M6, full lifecycle)
```

50 tests total, all passing.

---

## 8. How to launch from scratch

Assumes Windows + Docker Desktop running. Adjust paths for macOS/Linux.

### One-time setup

```powershell
# 0. system tools you need on Windows
#   - Docker Desktop (running)
#   - Python 3.11+
#   - Tesseract OCR with French + Arabic data:
#     https://github.com/UB-Mannheim/tesseract/wiki
#   - Poppler:
#     https://github.com/oschwartz10612/poppler-windows/releases
#   - GNU make (optional, for `make ...` shortcuts): choco install make

# 1. clone & cd
cd "c:\Users\iyed1\OneDrive\Desktop\work\HACKATHON\nrtf3\server architecture"

# 2. configure environment
copy .env.example .env
# edit .env if needed — most defaults work, but on Windows:
#   POSTGRES_PORT=55432  (system Postgres squats 5432; we live on 55432)
#   TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
#   POPPLER_PATH=C:\poppler\poppler-25.12.0\Library\bin

# 3. install Python deps
pip install -e ".[dev]"

# 4. start the docker stack (Postgres + Redis + Mosquitto)
docker compose up -d
docker compose ps   # all three should show (healthy) within ~30s

# 5. run the database migration
python -m alembic upgrade head

# 6. seed the one fake device (so MQTT-side queries don't blow up later)
python scripts/seed_db.py
```

### Day-to-day — three terminals

```powershell
# terminal 1: API
python -m uvicorn retech_part2.api.main:app --reload --host 0.0.0.0 --port 8000
#   Swagger UI at http://127.0.0.1:8000/docs
#   Health     at http://127.0.0.1:8000/health

# terminal 2: RQ worker (consumes ingestion jobs)
python -m retech_part2.workers.run_worker

# terminal 3: drop-folder watcher (auto-detects new files in inbox/)
python -m retech_part2.ingestion.watcher
```

Equivalent `make` targets (need GNU make installed):
`make api`, `make worker`, `make watcher`. See [Makefile](../Makefile) for
the full list (`up`, `down`, `migrate`, `test`, `seed`, `clean`).

### Try it

```powershell
# Drop the BILAN file via the watcher
copy "data\samples\avril-report1_2442026.xlsx" inbox\xlsx\
# Within ~20s the job appears at GET /api/jobs

# Or upload via the API
curl -F "file=@data\samples\avril-report1_2442026.xlsx" http://127.0.0.1:8000/api/ingest/upload

# Same for an invoice
copy "data\samples\invoices\data 2.0.pdf" inbox\pdf\
```

---

## 9. APIs available right now

`http://127.0.0.1:8000/docs` is the live spec. Today's endpoints:

| Method | Path                       | What it does                                       |
|--------|----------------------------|----------------------------------------------------|
| GET    | `/health`                  | `{"status":"ok"}`                                  |
| POST   | `/api/ingest/upload`       | Multipart upload. Auto-routes by extension to the bilan or invoice queue. Idempotent — same file returns the existing `job_id` with `deduped: true`. |
| GET    | `/api/jobs`                | List jobs. Filters: `status=`, `type=` (bilan/invoice), `limit=` (1..500). |
| GET    | `/api/jobs/{job_id}`       | Single job, including `warnings` JSONB.            |

M10 will add: `/api/devices`, `/api/readings`, `/api/bilan/files`,
`/api/bilan/series`, `/api/documents`, `/api/search` (full-text),
`/api/export?format=csv|parquet`.

---

## 10. Configuration (`.env`)

Every variable is documented inline in
[.env.example](../.env.example). The ones that actually need attention:

| Var                  | Default                | When to change                                    |
|----------------------|------------------------|---------------------------------------------------|
| `POSTGRES_PORT`      | `5432`                 | **55432 on this box** — system Postgres holds 5432 |
| `TESSERACT_CMD`      | empty (use PATH)       | Set to absolute path on Windows non-PATH installs |
| `POPPLER_PATH`       | empty (use PATH)       | Same                                              |
| `EXTRACTION_STRATEGY`| `qwen_then_regex`      | `regex_only` / `qwen_only` / `regex_then_qwen` (M9) |
| `OLLAMA_HOST`        | `http://localhost:11434` |                                                 |
| `OLLAMA_MODEL`       | `qwen2.5vl:3b`         | M9 — pull with `ollama pull qwen2.5vl:3b`        |
| `MIN_CONFIDENCE`     | `0.8`                  | Threshold for the M9 extractor chain              |
| `PDF_RENDER_DPI`     | `300`                  | Lower (200) speeds OCR ~2× at modest accuracy cost |

All read by [src/retech_part2/config.py](../src/retech_part2/config.py)
via pydantic-settings. Cached via `@lru_cache`.

---

## 11. Windows-specific gotchas (saved hard-learned)

These are real, we hit each one, and the fixes are baked in. **Don't undo them.**

1. **Postgres port 55432, not 5432.** A system PostgreSQL service squats on
   5432 and steals connections from the host. Docker's port forward maps to
   55432. `.env` has `POSTGRES_PORT=55432`; `.env.example` documents it.
2. **`timescale/timescaledb:latest-pg16`, NOT `-ha`.** The `-ha` (Spilo)
   variant silently ignores `POSTGRES_USER`/`PASSWORD`/`DB` and never
   creates the application role.
3. **`SimpleWorker`, NOT `Worker`.** RQ's default worker uses `os.fork()`
   which doesn't exist on Windows.
   [src/retech_part2/workers/run_worker.py](../src/retech_part2/workers/run_worker.py)
   selects `SimpleWorker` on Windows.
4. **`WindowsSelectorEventLoopPolicy` everywhere.** The default
   `ProactorEventLoop` blows up on asyncpg cleanup when a process calls
   `asyncio.run()` repeatedly (worker per task, watcher per event).
   [src/retech_part2/_compat.py](../src/retech_part2/_compat.py) is
   imported by every entry point.
5. **`reset_db_cache_for_new_loop()` before each `asyncio.run()`** in
   long-lived processes. The async engine binds to the loop that created
   it; reusing it from a fresh loop raises
   `"Future attached to a different loop"`. Called in
   [workers/tasks.py](../src/retech_part2/workers/tasks.py) and
   [ingestion/watcher.py](../src/retech_part2/ingestion/watcher.py).
6. **`PollingObserver` on Windows / WSL.** The native FS watchers are
   unreliable on Windows volumes and WSL2 9P mounts. We auto-detect via
   `sys.platform` + `/proc/version` check and pick the polling backend.
7. **PIL pixel-bomb limit raised** to 500M pixels. The default 178M is too
   conservative for our PDFs at 300 DPI.

---

## 12. Test suite

```powershell
python -m pytest -v
```

Currently 50 tests, all green:

| File                          | Count | Notes                                     |
|-------------------------------|-------|-------------------------------------------|
| `test_bilan_dates.py`         | 13    | Date locale-swap, all input shapes        |
| `test_bilan_parser.py`        | 13    | Real-file integration, structure, gaps    |
| `test_bilan_mapping.py`       | 23    | YAML, fuzzy match, context disambiguation |
| `test_bilan_ingestion.py`     | 1     | Full lifecycle: clean → ingest → re-ingest idempotency. Hits the live DB. |

Tests skip cleanly if the BILAN sample file isn't at
`data/samples/avril-report1_2442026.xlsx`.

---

## 13. CLIs you can run any time

| Command                                                         | What it does                                       |
|------------------------------------------------------------------|----------------------------------------------------|
| `python -m retech_part2.ingestion.bilan.parser <file.xlsx>`      | Print parameter summary + per-day synthesis histogram. Pure parser, no DB. |
| `python -m retech_part2.ingestion.bilan.mapping <file.xlsx>`     | Print every distinct `(raw_label, category)` → `metric_id` (or UNMAPPED) for the file. |
| `python -m retech_part2.ingestion.bilan.loader <file.xlsx>`      | Real ingest with full diagnostics: row accounting, monotonic inversions per metric (worst 5), idempotency check. |
| `python -m retech_part2.workers.tasks ingest_bilan_path <file>` | Run the worker task synchronously (bypasses RQ).   |
| `python scripts/ocr_fixtures_report.py`                          | OCR every file in `data/samples/invoices/` and print the confidence table that drives M9 prioritisation. |
| `python scripts/seed_db.py`                                      | Insert / re-confirm the one fake device row.       |

---

## 14. What's coming next (M9 + M10)

**M9 — structured invoice extraction.** Three-tier extractor chain
selectable via `EXTRACTION_STRATEGY`:

* `qwen_local` — Ollama with `qwen2.5vl:3b` (~3 GB VRAM, fits the 3050).
* `tesseract_regex` — heuristic regexes on the OCR text already in
  `documents.ocr_pages`.

Confidence-driven validator decides done / needs_review / failed.

**M10 — query/search/export endpoints + README polish.** Adds the read
endpoints Phase 3 will hit, the French-FTS search endpoint, and the
CSV/Parquet export streams.

---

If anything in here is wrong or unclear, ping me and I'll fix it before
you start. The most fragile parts of the system are the four
`data_quality_flags` semantics and the Windows event-loop dance — those
are where surprises live.
