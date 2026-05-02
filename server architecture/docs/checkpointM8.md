# Checkpoint M8 — context for the next chat

> You are taking over an in-progress hackathon project. Read this file
> end-to-end before doing anything. It contains every decision, every
> non-obvious project fact, the exact state of code and DB, what milestone
> to do next, and how the user wants to collaborate. The goal is that you
> can resume immediately without re-asking questions or re-discovering
> things that have already been settled.

---

## 0. The bare minimum if you only have 60 seconds

* Project: **Re-Tech Fusion (NRTF) Phase 2** at INSAT, 15-hour hackathon.
  This is the **data platform** between Phase 1 (ESP32+MQTT, separate
  teammate) and Phase 3 (edge ML, separate teammate).
* User: iyed Mdimegh. Windows 11 + Docker Desktop + Python 3.11.7. The
  Python venv pip installs into is `C:\Users\iyed1\.virtualenvs\myproject-k2xV8Dm1\`
  — that's the active env.
* Working dir: `c:\Users\iyed1\OneDrive\Desktop\work\HACKATHON\nrtf3\server architecture`.
  This is a subfolder of a larger git repo where Phase 1 firmware lives in
  sibling folders. The git toplevel is `.../nrtf3/`. We commit from this
  subfolder, but git operates at the toplevel.
* **Status: M1–M8 done, M9 next, M10 pending.** All 50 tests pass. Live
  pipeline (drop file → watcher → worker → DB) verified for both BILAN
  and invoice paths.
* **Don't undo the Windows fixes** in [_compat.py](../src/retech_part2/_compat.py),
  the SimpleWorker selection, the port-55432 change, or the PIL bomb-limit
  raise. Each was burned-in the hard way. See § 5 below.
* **Read [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) too** — it's the
  human-teammate doc. Has the architecture diagrams and table-by-table
  schema reference you'll need.

---

## 1. Project brief (condensed from the original prompt)

### Scope

**IN scope** (build):
1. Docker Compose: Postgres + TimescaleDB, Redis (RQ queue), Mosquitto.
2. DB schema covering 3 input sources, with proper time-series tables.
3. **BILAN Excel parser** — primary, heavily-graded ingestion path. Real
   sample at `data/samples/avril-report1_2442026.xlsx`.
4. **PDF/OCR invoice pipeline** — local-only extractor chain (see § 4).
5. File-upload REST API + drop-folder watcher + RQ workers.
6. Query/export endpoints for Phase 3 (CSV + Parquet).
7. Idempotency, validation, confidence scoring, ingestion-job tracking.
8. README, Makefile, demo scripts, sample fixtures.

**OUT of scope** (deferred, but with clean hooks):
* MQTT subscriber implementation — Phase 1 ESP32 not ready. Build a stub
  that documents the contract; schema for live readings already deployed.
  Stub at [src/retech_part2/ingestion/mqtt/subscriber.py](../src/retech_part2/ingestion/mqtt/subscriber.py).
* Custom web UI — Swagger at `/docs` is the only UI for now.
* WebSocket streaming — not needed without a UI.

### Hardware constraint

RTX 3050 with **6 GB VRAM**, 24 GB RAM. Do NOT attempt Qwen2.5-VL-7B
locally — will OOM. Allowed local model: Qwen2.5-VL-3B Q4 via Ollama
(~3 GB VRAM). Ask before pulling.

### Tech stack — pinned, no substitutions without asking

Already locked in [pyproject.toml](../pyproject.toml). Don't add new deps
without checking with the user. Notable choices:

* SQLAlchemy 2.x async + asyncpg + Alembic
* Pydantic v2 + pydantic-settings
* `psycopg[binary]` for COPY-based bulk inserts (ORM is too slow for ~150k rows)
* `openpyxl`, `rapidfuzz`, `PyYAML`
* `pdf2image` (+ system poppler), `pytesseract` (+ system tesseract with
  `fra` and `ara` packs), Pillow, `opencv-python-headless`
* `httpx`, `ollama` (Python client), `paho-mqtt`
* `redis`, `rq`, `watchdog`, `structlog`
* `pytest`, `pytest-asyncio` for tests

---

## 2. How the user wants to work — read this carefully

These are direct quotes / paraphrases from the original prompt. **Follow
them exactly** — they're not aspirational, they're how the user actually
collaborates.

* **Incremental, one milestone at a time.** After each milestone, STOP,
  tell the user exactly what to run and what to look for, **wait for
  their reply before continuing**. Do not skip ahead.
* **Never assume.** Paths, credentials, API keys, OS specifics, dependency
  additions — ask first.
* **Short, action-oriented responses.** Don't narrate. State decisions and
  results directly.
* **Stop and debug if a verification fails.** Don't push past a problem.
* **Propose smaller scope if a milestone is dragging.** Don't silently
  burn hours.
* **No Co-Authored-By trailer in git commits.** This is in user memory.
* **Default to writing no comments.** Only add a comment when the WHY is
  non-obvious. Don't reference the current task or "added for X". The
  PROJECT_HANDOFF.md and this checkpoint are the rare cases where docs
  are explicitly requested.

The user has been receptive to deviating from the spec when there's a
real reason — see § 4 for examples. They reward "I tried this, it broke
because X, here's why I'm doing Y instead." They push back on
unjustified changes. They appreciate when you explain trade-offs and
present a recommendation, not a finished decision.

---

## 3. Milestone status

| ID  | Title                                          | State    | Notes                                      |
|-----|------------------------------------------------|----------|--------------------------------------------|
| M1  | Bootstrap: Docker, FastAPI skeleton, Alembic   | done     | All three containers healthy               |
| M2  | DB schema (10 tables, 3 hypertables, FTS)      | done     | One Alembic migration                      |
| M3  | BILAN dates module + tests                     | done     | 13 tests, real-file integration            |
| M4  | BILAN structural parser + tests                | done     | 13 tests, parses 143,694 readings          |
| M5  | YAML mapping + canonical metric_ids            | done     | 23 tests, 52/52 pairs mapped (zero unmapped) |
| M6  | BILAN ingestion to TimescaleDB                 | done     | 1 integration test, idempotent             |
| M7  | Upload API + drop-folder watcher + RQ          | done     | End-to-end verified, worker resume tested  |
| M8  | PDF/OCR pipeline (Tesseract, multi-format)     | **done** | Fixtures report ran, live pipeline verified |
| M9  | Structured invoice extraction (Qwen + regex)   | **NEXT** | See § 9                                   |
| M10 | Query/search/export endpoints + README polish  | pending  | See § 10                                   |

---

## 4. Decisions made along the way (DON'T re-litigate these)

These are user-driven changes from the original spec. They're load-bearing.

### 4.1. Invoice extraction is **local-only**, no DashScope

User dropped the cloud API tier before M1. Two extractors only:
* `qwen_local` — Ollama, model from `OLLAMA_MODEL` env var (default `qwen2.5vl:3b`)
* `tesseract_regex` — must be a real, well-tuned extractor, not a throwaway

Selectable via `EXTRACTION_STRATEGY` env var with values:
`qwen_then_regex` (default), `qwen_only`, `regex_only`, `regex_then_qwen`.

`extract_qwen_api.py` was removed from the plan. **Do not add an httpx call
to DashScope or any cloud Qwen.** Reason: hackathon Wi-Fi may fail during
demo. User wants robust offline path.

Saved in memory: `project_nrtf_phase2_extraction.md`.

### 4.2. Real fixtures, no synthetic generator, no ReportLab

Before M8, user dropped real contest documents into
`data/samples/invoices/`. Mix of PDFs and loose images:

```
data/samples/invoices/
  data 2.0.pdf                                          (real STEG electricity invoice)
  doc 2.pdf
  fiche releve donne .pdf                               (one page is 95% confidence!)
  sxada.pdf                                             (worst quality, every page <50%)
  WhatsApp Image 2026-04-27 at 21.39.25 (29).jpeg
  WhatsApp Image 2026-04-27 at 21.39.25 (30).jpeg
  WhatsApp Image 2026-04-27 at 21.39.25 (31).jpeg
  WhatsApp Image 2026-04-27 at 21.39.25 (32).jpeg      (industrial alarm log, not an invoice)
```

User said: "Skip ReportLab and the synthetic generator entirely — don't
add the dep, don't write the script."

Multi-format input was added: the upload endpoint and watcher accept
`.pdf .jpg .jpeg .png .tiff .tif .webp`. `EXT_TO_JOB_TYPE` in
[workers/enqueue.py](../src/retech_part2/workers/enqueue.py) routes them
all to `task_ingest_invoice`. Loose images are treated as 1-page documents.

The router function `load_pages(file_path) -> list[PIL.Image.Image]` in
[ingestion/pdf/preprocessing.py](../src/retech_part2/ingestion/pdf/preprocessing.py)
returns the same shape regardless of input — downstream code never branches
on PDF vs image.

### 4.3. token_sort_ratio, NOT token_set_ratio (M5 deviation from spec)

The original spec said "rapidfuzz with token-set ratio". I switched to
`token_sort_ratio` because token-set scores any subset at 100, which broke:
* `"Energie en kWh"` fuzzy-matched to the much longer
  `"Energie éléctrique au borne de l'alternateur en KWh"` at score 100.
* `"Energymeter eau chaude Alpha"` couldn't be distinguished from
  `"…Alpha Sanitaire"` for context — both scored 100.

User explicitly approved this in M6 message: *"Approve the token-sort
change — it's the right algorithm here, keep the docstring note explaining
why."* The docstring note is in [mapping.py](../src/retech_part2/ingestion/bilan/mapping.py).

### 4.4. Cumulative meters have real-world inversions (don't assert strict monotonicity)

The spec claimed BILAN cumulative meters (gas volume, operating hours)
are "monotonically non-decreasing in column order." On the real April
sample, this is **not strictly true** — gas volume dips by 12 Nm3 once,
operating hours drops to 0 several times. User confirmed this is
expected ("yes thats true, gas-volume is NOT strictly non-decreasing in
column order") with a "second-guess if needed" caveat.

Tests use rate-based asserts (≤1% inversions, last > first) instead of
strict non-decreasing. Working hypothesis: real industrial telemetry has
sensor noise, manual operator overrides, blank cells defaulting to 0,
and meter resets. Alternative explanation worth ruling out if a future
file shows a different pattern: parser bug.

Saved in memory: `project_nrtf_bilan_data_quality.md`.

### 4.5. `whole_column_zero` flag (added before M7)

User asked for this refinement at M6 close-out: when the monotonic
validator detects an inversion to value=0 AND ≥2 other cumulative metrics
at the same time also read 0, also tag the row with `whole_column_zero`
(in addition to `monotonic_inversion`). Lets Phase 3 distinguish
single-meter glitches from system-wide logging gaps.

Implemented in
[validator.py:apply_whole_column_zero_check](../src/retech_part2/ingestion/bilan/validator.py).
On the real sample: 72 rows tagged across 6 distinct timestamps × 12
cumulative meters. 100% overlap with `monotonic_inversion`.

### 4.6. Intra-file duplicates dropped (added during M6)

The real BILAN file has ~912 rows where two columns share the same
`(date, time)` for the same metric. The hypertable's `UNIQUE (file_id,
time, metric_id)` rejects duplicates → COPY would fail mid-stream. Added
a dedup step in `loader.py` per the spec ("trust column order = first
wins"). Counted separately as `rows_dropped_duplicate_in_file`. User
approved: "keep the separate counter as you've structured it."

### 4.7. Worker resume + automated idempotency check baked into M6

User wanted these tested as part of the milestone, not as manual steps:
* CLI runs ingest twice, asserts second is `duplicate=True, rows_inserted=0`,
  asserts DB count unchanged.
* `test_full_ingestion_lifecycle` does the same in pytest.

CLI: `python -m retech_part2.ingestion.bilan.loader <file.xlsx>`.

### 4.8. PollingObserver for watchdog on Windows / WSL

User-flagged before M7 started: native `Observer` (ReadDirectoryChangesW
on Windows, inotify on Linux) is unreliable on Windows-mounted volumes
and WSL2 9P/CIFS mounts. Detection in
[ingestion/watcher.py:_is_windows_or_wsl](../src/retech_part2/ingestion/watcher.py)
checks `sys.platform` + `/proc/version` for "microsoft".

### 4.9. PIL pixel-bomb limit raised to 500M

PIL's default 178M-pixel guard rejects two of the contest PDFs at 300 DPI.
We control the inputs (operator-uploaded invoices, not adversarial), so
raising the limit is safe. Set in
[preprocessing.py](../src/retech_part2/ingestion/pdf/preprocessing.py)
at module load. **Don't lower it.**

---

## 5. Project facts discovered (the Windows-quirks list)

These are saved in `project_nrtf_phase2_dev_env.md` (memory). All fixes
are already in code.

1. **Postgres host port = 55432, not 5432.** A system PostgreSQL service
   squats on 5432 and asyncpg connects to it (auth fails for `retech`
   role). `.env` has `POSTGRES_PORT=55432`. **Don't undo.**
2. **Use `timescale/timescaledb:latest-pg16`, NOT `-ha`.** The HA (Spilo)
   variant silently ignores `POSTGRES_USER`/`PASSWORD`/`DB`.
3. **Every Python entry point calls `apply_windows_event_loop_policy()`.**
   The default `ProactorEventLoop` blows up asyncpg cleanup on repeated
   `asyncio.run()` calls. Wired into `api/main.py`, `workers/run_worker.py`,
   `workers/tasks.py`, `ingestion/watcher.py`, `tests/conftest.py`.
4. **`reset_db_cache_for_new_loop()` before each `asyncio.run()`** in
   long-lived processes. The async engine binds to the loop that created
   it. Called in `workers/tasks.py` at the start of each task and in
   `watcher.py` before each per-event enqueue.
5. **`SimpleWorker` on Windows.** RQ default `Worker` uses `os.fork()`.
   Selection logic in `workers/run_worker.py`.
6. **`PollingObserver` on Windows/WSL.** See § 4.8.
7. **PIL `MAX_IMAGE_PIXELS = 500_000_000`.** See § 4.9.

If a new bug surfaces and you're tempted to "fix" any of these — **don't.
Read the relevant memory file first**, then ask the user.

---

## 6. BILAN data findings (so you don't re-discover)

From running parser + mapper + ingester on `avril-report1_2442026.xlsx`:

* **143,694 readings parsed** from the file.
* **0 unmapped pairs** — every (raw_label, category) hits the YAML.
* **912 intra-file duplicates dropped** (same time + metric_id).
* **142,782 rows COPYed** into `timeseries.bilan_readings`.
* **38 distinct raw_labels**, **52 distinct (raw_label, category) pairs**
  (some labels reused across categories like "Energie en kWh" appearing
  in 4 energymeter groups).
* **Date range**: April 1–20, 2025.
* **Synthetic timestamps**: 44,448 readings (30.9%) carry one — these come
  from gap columns where we interpolated between neighbours.
* **Monotonic inversions found**: 14 cumulative metrics, 7–32 inversions
  each. Total ~357 rows tagged `monotonic_inversion`.
* **Whole-column-zero**: 72 rows across 6 distinct timestamps.
* **Range violations**: 0 (no metric value out of YAML bounds).
* **Final status**: `partial_success` (warnings exist but ingestion succeeded).

---

## 7. Invoice / OCR findings (so you can prioritise M9 correctly)

From `python scripts/ocr_fixtures_report.py` on the 8 contest fixtures:

| Fixture | Type | Pages | Mean conf | Worst page |
|---|---|---|---|---|
| `data 2.0.pdf` | pdf | 1 | 58.4% | 58.4% — **REAL invoice (STEG electricity, 134,408 DINARS total)** |
| `doc 2.pdf` | pdf | 3 | 47.3% | 30.7% |
| `fiche releve donne .pdf` | pdf | 4 | 64.1% | 38.9% (and one page at **95%**) |
| `sxada.pdf` | pdf | 3 | **37.3%** | 28.1% — **Qwen-mandatory** (every page < 50%) |
| WhatsApp(29).jpeg | image | 1 | 61.7% | – |
| WhatsApp(30).jpeg | image | 1 | 70.8% | – |
| WhatsApp(31).jpeg | image | 1 | 64.5% | – |
| WhatsApp(32).jpeg | image | 1 | **79.5%** | – — **alarm log, NOT an invoice** |

**Aggregate:** 15 pages, mean **56.3%**, median 58.4%, **40% of pages
below 50%**. All `fra` (no Arabic detected anywhere).

**M9 prioritisation signal: Qwen needs to be a workhorse, not a fallback.**
Mean confidence is well below the 90% "regex is enough" line.

**Open question I asked the user but they hadn't answered before they
asked for this checkpoint:** what should the M9 schema do for
non-invoice fixtures (alarm log screenshot, control panel images)? Four
options I offered:
* (a) keep the spec's invoice-field schema and accept null fields
* (b) widen schema to include log fields (timestamp, alarm code, message)
* (c) treat WhatsApp images as actual invoices (need to peek)
* (d) extract everything possible, save raw OCR text, let Phase 3 query

Worth asking again at the start of M9.

---

## 8. Memory entries saved (auto-loaded into future chats)

The path: `C:\Users\iyed1\.claude\projects\c--Users-iyed1-OneDrive-Desktop-work-HACKATHON-nrtf3\memory\`.
The index file `MEMORY.md` references:

* `feedback_no_coauthor_trailer.md` — drop the "Co-Authored-By: Claude"
  line from all commit messages.
* `project_dummy_sensors_mode.md` — Phase 1 firmware quirk; not relevant
  to Phase 2 work.
* `project_nrtf_phase2_extraction.md` — see § 4.1.
* `project_nrtf_phase2_dev_env.md` — see § 5. **3 sub-quirks documented.**
* `project_nrtf_bilan_data_quality.md` — see § 4.4.

These auto-load. You don't need to re-read them, but they're the source
of truth — if anything in this checkpoint contradicts them, trust the
memory file.

---

## 9. M9 — what you need to build next

Full spec from the original brief:

### Interface every extractor implements

```python
class InvoiceExtractor(Protocol):
    name: str
    async def extract(self, pages: list[PageData]) -> InvoiceExtractionResult: ...
```

`PageData` carries both the raw image bytes AND the Tesseract text.
`InvoiceExtractionResult` has the typed invoice fields plus `raw_response`
and `extractor_confidence`.

### Tier 1: `extract_qwen_local.py` (primary, since DashScope is dropped)

Use Ollama with `OLLAMA_MODEL` (default `qwen2.5vl:3b`). Vision-language
model — send page images directly. Same JSON contract as the regex
extractor would output. Will be slow (~10–30 s per page on the 3050).

**Tell the user when to run `ollama pull qwen2.5vl:3b`.** They have
Ollama installed but haven't pulled the model. The user explicitly said:
"I have Ollama installed but haven't pulled the model yet — tell me when
to run ollama pull qwen2.5vl:3b."

System prompt template (from spec):

```
You are an invoice data extractor. Extract the following fields from the
invoice image. Return ONLY a JSON object matching this schema, no prose:

{
  "vendor": "string (company name issuing the invoice)",
  "invoice_number": "string",
  "invoice_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD or null",
  "currency": "ISO 4217 code (TND, EUR, USD, ...)",
  "subtotal": number,
  "tax": number,
  "total": number,
  "line_items": [
    {"description": "string", "quantity": number, "unit_price": number, "line_total": number}
  ]
}

Numbers must be plain (no thousands separators, decimal point, no currency symbol).
If a field is unreadable, use null. Do not invent values.
The invoice may be in French or Arabic. Tunisian VAT is typically 19%.
```

### Tier 2: `extract_regex.py` (well-tuned, NOT a throwaway)

Operates on Tesseract text already in `documents.ocr_pages`. Heuristic
regexes:
* vendor — top of page, longest non-numeric line
* invoice number — `(?:Facture|Invoice|N°)\s*[:#]?\s*(\S+)`
* date — multiple French formats
* total — currency-pattern near "Total" / "Net à payer" / "TTC"
* tax — near "TVA"
* subtotal — near "HT" / "Sous-total"

Lower confidence than Qwen but still real.

### Orchestrator: `pdf/pipeline.py` extension

Read `EXTRACTION_STRATEGY` from settings, build the chain accordingly:

```python
async def extract_invoice(doc_id: UUID, pages: list[PageData]) -> InvoiceExtractionResult:
    config = get_config()
    chain = []
    if config.EXTRACTION_STRATEGY in ("qwen_then_regex", "qwen_only"):
        chain.append(QwenLocalExtractor())
    if config.EXTRACTION_STRATEGY in ("regex_then_qwen", "regex_only"):
        chain.append(RegexExtractor())
    # Then fallback if not _only
    if config.EXTRACTION_STRATEGY == "qwen_then_regex":
        chain.append(RegexExtractor())
    if config.EXTRACTION_STRATEGY == "regex_then_qwen":
        chain.append(QwenLocalExtractor())

    last_error = None
    for extractor in chain:
        try:
            result = await extractor.extract(pages)
            if validate_invoice(result).confidence >= config.MIN_CONFIDENCE:
                result.method = extractor.name
                return result
        except Exception as e:
            last_error = e
            log.warning("extractor_failed", extractor=extractor.name, error=str(e))
            continue
    return best_candidate or raise_extraction_failed(last_error)
```

### Validator: `pdf/validator.py`

Confidence starts at 1.0 and gets docked:
* `subtotal + tax ≈ total` (1% tolerance) — −0.2 if fails
* `sum(line_totals) ≈ subtotal` (1% tolerance) — −0.15 if fails
* `invoice_date` parseable and within last 5 years — −0.2 if fails
* `vendor` non-empty and ≥ 2 chars — −0.15 if fails
* `total > 0` — −0.3 if fails
* Currency in known list — −0.05 if fails

`extraction_status` set to:
* `done` if confidence ≥ 0.8
* `needs_review` if 0.5 ≤ confidence < 0.8
* `failed` if confidence < 0.5

### Storage

* INSERT into `documents.invoices` and `documents.invoice_line_items`.
* UPDATE `documents.documents` with `extraction_method`,
  `extraction_confidence`, `extraction_status`, `extraction_warnings`.

### Verify

1. Run a fixture (start with `data 2.0.pdf` since it's a real invoice)
   through the pipeline. With Qwen: confidence ≥ 0.9, all fields populated.
2. Set `EXTRACTION_STRATEGY=regex_only`, re-run on a fresh duplicate
   (need to wipe documents.documents first). Some fields populated, lower
   confidence.
3. Endpoint `GET /api/documents/{id}` returns the structured invoice.
   *(Note: this endpoint is M10. For M9 verify, query the DB directly or
   use a tiny throwaway endpoint.)*

### Things to think about before starting M9

* Get the answer from the user on the schema question (§ 7). Half the
  fixtures aren't classical invoices.
* Confirm OLLAMA is reachable at `http://localhost:11434` before pulling
  the model — `curl http://localhost:11434/api/tags` should return JSON.
* The 3050 has 6 GB VRAM. `qwen2.5vl:3b` quantised should fit (~3 GB),
  but verify with `nvidia-smi` after first inference.
* Per-page Qwen time: 10–30 s. With 15 pages across the fixture set,
  full-corpus M9 verification could take 5+ minutes. Plan accordingly.

---

## 10. M10 — what comes after M9 (for context)

### Endpoints to add

```
GET  /api/devices                                  # from meta.devices
GET  /api/readings?device_id=&type=&from=&to=&limit=  # empty until MQTT
GET  /api/bilan/files                              # list ingested BILAN files
GET  /api/bilan/files/{file_id}                    # one file's metadata + warnings
GET  /api/bilan/metrics                            # distinct metric_ids in DB
GET  /api/bilan/series?metric_id=&from=&to=&file_id=  # paged time-series
GET  /api/documents?status=&from=&to=&limit=       # list documents
GET  /api/documents/{doc_id}                       # full record + line items + page text
PATCH /api/documents/{doc_id}                      # accept user edits
GET  /api/search?q=                                # PG full-text search over ocr_pages
GET  /api/export?source=bilan&from=&to=&format=csv|parquet  # streaming
```

### Other M10 work

* `scripts/replay_mqtt_jsonl.py` — backup demo path if MQTT isn't ready.
* README polish (the user-facing version, not this checkpoint).
* `scripts/demo.sh` — end-to-end smoke for demo day.

---

## 11. Code state right now

### What's in the repo

50 files committed worth of code. Top-level layout:

```
.
├── docker-compose.yml
├── docker/mosquitto/mosquitto.conf
├── pyproject.toml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/001_initial_schema.py
├── inbox/
│   ├── xlsx/.gitkeep              (drop folder, gitignored contents)
│   └── pdf/.gitkeep               (also accepts images)
├── data/
│   ├── samples/avril-report1_2442026.xlsx
│   ├── samples/invoices/          (8 contest fixtures)
│   ├── fixtures/synthetic_mini.xlsx, synthetic_mini2.xlsx (for worker resume test)
│   └── ocr_cache/                 (gitignored; populated by OCR runs)
├── scripts/
│   ├── seed_db.py
│   └── ocr_fixtures_report.py
├── src/retech_part2/
│   ├── _compat.py
│   ├── config.py, db.py, models.py, schemas.py, logging.py
│   ├── api/main.py + routes/{health, ingest, jobs, readings, bilan, documents, search, export}.py
│   ├── ingestion/
│   │   ├── bilan/{dates, parser, mapping, mapping.yaml, validator, loader}.py
│   │   ├── pdf/{preprocessing, ocr_tesseract, pipeline}.py
│   │   ├── mqtt/subscriber.py     (stub)
│   │   └── watcher.py
│   ├── workers/{enqueue, tasks, run_worker}.py
│   └── utils/{hashing, files}.py
├── tests/
│   ├── conftest.py
│   ├── test_bilan_dates.py        (13 tests)
│   ├── test_bilan_parser.py       (13 tests)
│   ├── test_bilan_mapping.py      (23 tests)
│   └── test_bilan_ingestion.py    (1 lifecycle test)
└── docs/
    ├── PROJECT_HANDOFF.md          (for human teammate)
    └── checkpointM8.md             (this file)
```

### What's running where

Three processes when working live:
* **API** on port 8000 — `python -m uvicorn retech_part2.api.main:app --host 127.0.0.1 --port 8000`
* **Worker** — `python -m retech_part2.workers.run_worker` (SimpleWorker on Windows)
* **Watcher** — `python -m retech_part2.ingestion.watcher` (PollingObserver on Windows)

I stopped all three at end of M8 verification. The Docker stack
(postgres/redis/mosquitto) is still up.

### How to verify state

```powershell
# stack
docker compose ps

# tests (50 should pass)
python -m pytest -v

# DB row counts
docker exec -e PGPASSWORD=retech retech_postgres psql -h 127.0.0.1 -U retech -d retech -c "
SELECT 'bilan_readings' AS t, COUNT(*) FROM timeseries.bilan_readings
UNION ALL SELECT 'bilan_files', COUNT(*) FROM meta.bilan_files
UNION ALL SELECT 'ingestion_jobs', COUNT(*) FROM meta.ingestion_jobs
UNION ALL SELECT 'documents', COUNT(*) FROM documents.documents
UNION ALL SELECT 'ocr_pages', COUNT(*) FROM documents.ocr_pages
UNION ALL SELECT 'invoices', COUNT(*) FROM documents.invoices;
"
```

After my last M8 run, expect:
* `bilan_readings`: 0 (was wiped before live invoice test)
* `bilan_files`: 0
* `ingestion_jobs`: 2 (the M8 live-pipeline tests, both invoice)
* `documents`: 2 (the live test fixtures)
* `ocr_pages`: 2
* `invoices`: 0 (M9 will populate)

---

## 12. Test state

```
============================= test session starts =============================
collected 50 items
tests\test_bilan_dates.py .............                                  [ 26%]
tests\test_bilan_ingestion.py .                                          [ 28%]
tests\test_bilan_mapping.py .......................                      [ 74%]
tests\test_bilan_parser.py .............                                 [100%]
============================= 50 passed in 56.79s =============================
```

The integration test requires the live DB. It wipes any existing ingestion
of the sample file, runs ingest, asserts shape/accounting/validator output,
re-ingests, asserts idempotent.

No tests yet for: M7 upload endpoint, M7 watcher (manually verified), M8
OCR pipeline (manually verified via fixtures report + live-pipeline drop).
M9 should add tests for the extractor chain.

---

## 13. CLIs you can use for diagnostics

```powershell
# Pure parser, no DB
python -m retech_part2.ingestion.bilan.parser data/samples/avril-report1_2442026.xlsx

# Mapping table (raw_label, category) -> metric_id for any file
python -m retech_part2.ingestion.bilan.mapping data/samples/avril-report1_2442026.xlsx

# Full ingest with diagnostics + idempotency check
python -m retech_part2.ingestion.bilan.loader data/samples/avril-report1_2442026.xlsx

# RQ worker task synchronously (bypasses queue)
python -m retech_part2.workers.tasks ingest_bilan_path data/samples/avril-report1_2442026.xlsx

# OCR every fixture under data/samples/invoices/, print confidence table
python scripts/ocr_fixtures_report.py

# Seed the fake device row (idempotent, ON CONFLICT DO NOTHING)
python scripts/seed_db.py
```

---

## 14. Things to do at the start of M9

In this order:

1. **Re-read this checkpoint and PROJECT_HANDOFF.md.** Note anything that
   surprises you.
2. **Ask the user the schema question from § 7** (what to do with
   non-invoice fixtures like the WhatsApp alarm log).
3. **Confirm Ollama is up:**
   `curl http://localhost:11434/api/tags`
4. **Tell the user to run `ollama pull qwen2.5vl:3b`.** Wait for them to
   confirm before continuing.
5. **Build the extractors** — `extract_qwen_local.py`, `extract_regex.py`.
6. **Build the orchestrator** in `pipeline.py` (extends what's there).
7. **Build the validator** — `pdf/validator.py`.
8. **Wire into `task_ingest_invoice`** — currently this just runs OCR and
   stops. M9 makes it run extraction too and update `documents.invoices`
   + `documents.documents.extraction_status`.
9. **Verify on `data 2.0.pdf` first** (it's the real invoice). Then run
   the full fixture set.
10. **STOP after M9, wait for the user to verify**, then move to M10.

---

## 15. Communication style — match the user's tone

* They write short messages, expect short responses. Verbose summaries
  bore them.
* They use lowercase informally ("go", "yes", "continue", "is it done yet?").
* They're technically sharp — don't over-explain.
* They will sometimes write commands in casual notation ("scada" instead
  of `sxada.pdf`). Reading carefully and asking is fine.
* They appreciate when you flag trade-offs and offer to adjust scope.
  Examples that worked: "the spec said X but real data shows Y; I'm
  doing Z; tell me to revert if you'd rather", "spec target is N pages
  but we only have M; here's why".
* They've explicitly invited you to "second-guess" their claims when you
  have a reason. Don't be sycophantic; tell them when their assumption
  doesn't match the data.
* They liked the diagnostic output dumps (M6 worst-inversions table,
  M8 confidence table). When something is uncertain, surface the data
  and let them decide.

---

## 16. Open threads / TODOs the user might bring up

* **The schema question for M9** (§ 7) — they hadn't answered when this
  checkpoint was requested.
* **PDF render time at 300 DPI is brutal** (~70-100s/page). Suggested
  M9 sub-task: render at 200 DPI first, only re-render at 300 if first-pass
  confidence is low. Bring up if discussing demo throughput.
* **Two-page-only render** for very large PDFs (`fiche releve donne .pdf`
  is 4 pages and took 5 minutes). For Qwen, may want to skip past page 1
  if invoice fields all appear there. Could be a M9 optimisation.
* **No tests yet for the OCR pipeline.** Manual verification only. Could
  add one in M9 once the full extract pipeline exists.

---

## 17. Files you should open first when starting

In order:
1. `docs/checkpointM8.md` (this file)
2. `docs/PROJECT_HANDOFF.md` (architecture + schema reference)
3. `src/retech_part2/ingestion/pdf/pipeline.py` (where M9 lands)
4. `src/retech_part2/ingestion/pdf/ocr_tesseract.py` (input to extractors)
5. `src/retech_part2/models.py` (look at `Document`, `Invoice`,
   `InvoiceLineItem`, `OcrPage`)
6. `src/retech_part2/config.py` (the `EXTRACTION_STRATEGY` literal +
   ollama / extraction settings)
7. `src/retech_part2/workers/tasks.py` (`task_ingest_invoice` is what
   M9 has to extend)

That should be enough to start coding M9 without re-deriving anything.

---

## End of checkpoint

If anything in here is wrong or stale by the time you read it, trust the
git log and the live DB over the document. The code is the source of
truth; this checkpoint is just the map.

Good luck. Go ask the user the M9 schema question first — don't start
writing extractors until you know what fields they want for the
non-invoice fixtures.
