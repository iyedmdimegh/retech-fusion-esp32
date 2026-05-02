# Re-Tech Fusion — Phase 2 (Data Platform)

Phase 2 of the NRTF Hackathon at INSAT. Ingests data from three sources, normalizes them into a single analytical store, and exposes query/export APIs for Phase 3 (edge ML).

- **Live MQTT** — schema deployed; subscriber stubbed until Phase 1 (ESP32) is wired.
- **BILAN Excel reports** — primary, heavily-graded ingestion path. Real sample provided.
- **Scanned PDF invoices** — three-tier OCR pipeline (Ollama Qwen → Tesseract+regex), strategy selectable via `.env`.

The default UI is FastAPI's auto-generated Swagger at `http://localhost:8000/docs`.

---

## Status

Currently at **M1 — Bootstrap**. Subsequent milestones land schema, parsers, OCR, the file-upload API, the worker queue, and export endpoints.

---

## Prerequisites (Windows native)

1. **Docker Desktop** — running. Confirm with `docker compose version`.
2. **Python 3.11+** on `PATH`. Confirm with `python --version`.
3. **GNU make** — needed for the `make` shortcuts. Install via Chocolatey (`choco install make`) or use Git Bash. If you'd rather skip make, every target maps to a one-liner shown in [Makefile](Makefile).
4. **uv** *(recommended)* or `pip` for dep management. uv install: <https://docs.astral.sh/uv/getting-started/installation/>.
5. **Tesseract OCR** with French data (needed at M8). Windows installer: <https://github.com/UB-Mannheim/tesseract/wiki>. Make sure `tesseract.exe` is on `PATH` and install the `fra` (French) language pack.
6. **Poppler** for `pdf2image` (needed at M8). Windows binaries: <https://github.com/oschwartz10612/poppler-windows/releases>. Add the `bin/` directory to `PATH`.
7. **Ollama** *(needed at M9)*. Install from <https://ollama.com/>. Model pull happens on instruction during M9 — do **not** pull yet.

---

## Quick start

```powershell
# 1. clone & enter
cd "c:\Users\iyed1\OneDrive\Desktop\work\HACKATHON\nrtf3\server architecture"

# 2. configure environment
copy .env.example .env

# 3. install Python deps (pick one)
uv sync                     # preferred
# pip install -e ".[dev]"   # fallback

# 4. start the docker stack
make up                     # docker compose up -d

# 5. run database migrations (no-op until M2 lands the schema)
make migrate

# 6. start the API
make api                    # http://localhost:8000/docs

# 7. start the worker (in a second terminal — M7 onward)
make worker

# 8. start the drop-folder watcher (in a third terminal — M7 onward)
make watcher
```

Verify:

```powershell
curl http://localhost:8000/health
# {"status":"ok"}

docker compose ps
# postgres, redis, mosquitto — all healthy
```

---

## Architecture

```
                ┌──────────────────────────────────────────┐
                │              FastAPI (REST)              │
                │  /ingest /jobs /readings /bilan          │
                │  /documents /search /export /health      │
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
     │   meta           │                          │   RQ Workers    │
     └────────▲─────────┘                          │  • bilan parse  │
              │                                    │  • pdf OCR      │
              │ inserts                            │  • mqtt (stub)  │
              └────────────────────────────────────┴────────┬────────┘
                                                            │
              ┌──────────────┬──────────────────────────────┘
              │              │
       ┌──────┴──────┐  ┌────┴───────────┐
       │ inbox/xlsx/ │  │  inbox/pdf/    │
       │ (watchdog)  │  │  (watchdog)    │
       └─────────────┘  └────────────────┘

       ┌─────────────────────┐
       │  Mosquitto          │ (deployed, idle until Phase 1 ready)
       │  topic: retech/...  │
       └─────────────────────┘
```

---

## Configuration

Every variable lives in [.env.example](.env.example). Copy to `.env` before running. Highlights:

- `DATABASE_URL` is derived from `POSTGRES_*` in [src/retech_part2/config.py](src/retech_part2/config.py).
- `EXTRACTION_STRATEGY` selects the invoice-extraction chain. One of:
  - `qwen_then_regex` *(default)* — try Ollama Qwen first, fall back to Tesseract+regex on failure or low confidence.
  - `qwen_only` — Qwen only; fail otherwise.
  - `regex_only` — Tesseract+regex only (fastest, no model required).
  - `regex_then_qwen` — regex first, escalate to Qwen on low confidence.
- `OLLAMA_HOST` (default `http://localhost:11434`) and `OLLAMA_MODEL` (default `qwen2.5vl:3b`) are not hardcoded.
- `MIN_CONFIDENCE` (0..1) — threshold below which an extractor is considered insufficient and the orchestrator falls back to the next tier.

---

## Deferred work (intentional)

- **MQTT subscriber** — stubbed at [src/retech_part2/ingestion/mqtt/subscriber.py](src/retech_part2/ingestion/mqtt/subscriber.py). Topic, QoS and payload contract are documented; activation waits for Phase 1.
- **Custom dashboard / web UI** — Swagger at `/docs` is the only UI for now.
- **WebSocket streaming** — not needed without a UI.

---

## Repository layout

See the milestone plan in the project brief; the on-disk layout mirrors it.
