"""initial schema — meta / timeseries / documents

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-05-02

Implements the full Phase-2 schema in three logical Postgres schemas:
- meta        : devices, bilan_files, ingestion_jobs
- timeseries  : readings, device_status, bilan_readings (TimescaleDB hypertables)
- documents   : documents, ocr_pages (with French FTS), invoices, invoice_line_items
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- extensions ----
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # ---- schemas ----
    op.execute("CREATE SCHEMA IF NOT EXISTS meta;")
    op.execute("CREATE SCHEMA IF NOT EXISTS timeseries;")
    op.execute("CREATE SCHEMA IF NOT EXISTS documents;")

    # ============ schema: meta ============
    op.execute("""
        CREATE TABLE meta.devices (
            device_id     TEXT PRIMARY KEY,
            site          TEXT NOT NULL,
            fw_version    TEXT,
            first_seen    TIMESTAMPTZ DEFAULT NOW(),
            last_seen     TIMESTAMPTZ
        );
    """)

    op.execute("""
        CREATE TABLE meta.bilan_files (
            file_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            file_hash         TEXT UNIQUE NOT NULL,
            filename          TEXT NOT NULL,
            parsed_at         TIMESTAMPTZ DEFAULT NOW(),
            date_range_start  DATE,
            date_range_end    DATE,
            rows_inserted     INT,
            rows_dropped      INT,
            unmapped_params   JSONB,
            status            TEXT NOT NULL,
            warnings          JSONB
        );
    """)

    op.execute("""
        CREATE TABLE meta.ingestion_jobs (
            job_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            job_type      TEXT NOT NULL,
            source_path   TEXT,
            file_hash     TEXT,
            status        TEXT NOT NULL,
            progress      INT DEFAULT 0,
            error_message TEXT,
            warnings      JSONB,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            started_at    TIMESTAMPTZ,
            finished_at   TIMESTAMPTZ
        );
    """)
    op.execute("CREATE INDEX ix_ingestion_jobs_status_created ON meta.ingestion_jobs (status, created_at DESC);")

    # ============ schema: timeseries ============
    op.execute("""
        CREATE TABLE timeseries.readings (
            time          TIMESTAMPTZ NOT NULL,
            ingested_at   TIMESTAMPTZ DEFAULT NOW(),
            device_id     TEXT NOT NULL REFERENCES meta.devices(device_id),
            sensor        TEXT NOT NULL,
            type          TEXT NOT NULL,
            value         DOUBLE PRECISION NOT NULL,
            unit          TEXT NOT NULL
        );
    """)
    op.execute("SELECT create_hypertable('timeseries.readings', 'time');")
    op.execute("CREATE INDEX ix_readings_device_type_time ON timeseries.readings (device_id, type, time DESC);")

    op.execute("""
        CREATE TABLE timeseries.device_status (
            time          TIMESTAMPTZ NOT NULL,
            device_id     TEXT NOT NULL,
            status        TEXT NOT NULL,
            rssi          INTEGER,
            uptime_s      BIGINT,
            fw_version    TEXT,
            drift_alert   BOOLEAN DEFAULT FALSE
        );
    """)
    op.execute("SELECT create_hypertable('timeseries.device_status', 'time');")
    op.execute("CREATE INDEX ix_device_status_device_time ON timeseries.device_status (device_id, time DESC);")

    op.execute("""
        CREATE TABLE timeseries.bilan_readings (
            time                  TIMESTAMPTZ NOT NULL,
            file_id               UUID NOT NULL REFERENCES meta.bilan_files(file_id),
            metric_id             TEXT NOT NULL,
            value                 DOUBLE PRECISION NOT NULL,
            unit                  TEXT NOT NULL,
            raw_label             TEXT NOT NULL,
            timestamp_synthetic   BOOLEAN DEFAULT FALSE,
            data_quality_flags    TEXT[],
            UNIQUE (file_id, time, metric_id)
        );
    """)
    op.execute("SELECT create_hypertable('timeseries.bilan_readings', 'time');")
    op.execute("CREATE INDEX ix_bilan_readings_metric_time ON timeseries.bilan_readings (metric_id, time DESC);")
    op.execute("CREATE INDEX ix_bilan_readings_file ON timeseries.bilan_readings (file_id);")

    # ============ schema: documents ============
    op.execute("""
        CREATE TABLE documents.documents (
            doc_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            file_hash             TEXT UNIQUE NOT NULL,
            doc_type              TEXT NOT NULL,
            source_file           TEXT NOT NULL,
            page_count            INT,
            uploaded_at           TIMESTAMPTZ DEFAULT NOW(),
            extraction_status     TEXT NOT NULL,
            extraction_method     TEXT,
            extraction_confidence DOUBLE PRECISION,
            extraction_warnings   JSONB
        );
    """)

    op.execute("""
        CREATE TABLE documents.ocr_pages (
            doc_id          UUID NOT NULL REFERENCES documents.documents(doc_id) ON DELETE CASCADE,
            page_number     INT NOT NULL,
            image_path      TEXT,
            text            TEXT,
            ocr_confidence  DOUBLE PRECISION,
            PRIMARY KEY (doc_id, page_number)
        );
    """)
    op.execute("""
        CREATE INDEX ocr_pages_fts ON documents.ocr_pages
            USING GIN (to_tsvector('french', COALESCE(text, '')));
    """)

    op.execute("""
        CREATE TABLE documents.invoices (
            doc_id          UUID PRIMARY KEY REFERENCES documents.documents(doc_id) ON DELETE CASCADE,
            vendor          TEXT,
            invoice_number  TEXT,
            invoice_date    DATE,
            due_date        DATE,
            currency        TEXT,
            subtotal        NUMERIC(14,2),
            tax             NUMERIC(14,2),
            total           NUMERIC(14,2),
            user_edited     BOOLEAN DEFAULT FALSE,
            edited_at       TIMESTAMPTZ
        );
    """)

    op.execute("""
        CREATE TABLE documents.invoice_line_items (
            id              BIGSERIAL PRIMARY KEY,
            doc_id          UUID NOT NULL REFERENCES documents.invoices(doc_id) ON DELETE CASCADE,
            line_no         INT,
            description     TEXT,
            quantity        NUMERIC,
            unit_price      NUMERIC(14,2),
            line_total      NUMERIC(14,2)
        );
    """)
    op.execute("CREATE INDEX ix_invoice_line_items_doc_line ON documents.invoice_line_items (doc_id, line_no);")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS documents CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS timeseries CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS meta CASCADE;")
