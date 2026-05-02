from __future__ import annotations

import datetime as dt
import decimal
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ============================================================
# meta
# ============================================================

class Device(Base):
    __tablename__ = "devices"
    __table_args__ = {"schema": "meta"}

    device_id: Mapped[str] = mapped_column(Text, primary_key=True)
    site: Mapped[str] = mapped_column(Text, nullable=False)
    fw_version: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class BilanFile(Base):
    __tablename__ = "bilan_files"
    __table_args__ = {"schema": "meta"}

    file_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    file_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    date_range_start: Mapped[dt.date | None] = mapped_column(Date)
    date_range_end: Mapped[dt.date | None] = mapped_column(Date)
    rows_inserted: Mapped[int | None] = mapped_column(Integer)
    rows_dropped: Mapped[int | None] = mapped_column(Integer)
    unmapped_params: Mapped[list | dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    warnings: Mapped[list | dict | None] = mapped_column(JSONB)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("ix_ingestion_jobs_status_created", "status", "created_at"),
        {"schema": "meta"},
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text)
    file_hash: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list | dict | None] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


# ============================================================
# timeseries (TimescaleDB hypertables)
# ============================================================

class Reading(Base):
    """Live ESP32 reading. Hypertable on `time`."""

    __tablename__ = "readings"
    __table_args__ = (
        Index("ix_readings_device_type_time", "device_id", "type", "time"),
        {"schema": "timeseries"},
    )

    time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    ingested_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    device_id: Mapped[str] = mapped_column(
        Text, ForeignKey("meta.devices.device_id"), primary_key=True, nullable=False
    )
    sensor: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    type: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    value: Mapped[float] = mapped_column(Double, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)


class DeviceStatus(Base):
    __tablename__ = "device_status"
    __table_args__ = (
        Index("ix_device_status_device_time", "device_id", "time"),
        {"schema": "timeseries"},
    )

    time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    device_id: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    rssi: Mapped[int | None] = mapped_column(Integer)
    uptime_s: Mapped[int | None] = mapped_column(BigInteger)
    fw_version: Mapped[str | None] = mapped_column(Text)
    drift_alert: Mapped[bool | None] = mapped_column(Boolean, server_default="false")


class BilanReading(Base):
    """One BILAN sample per (file, timestamp, metric). Hypertable on `time`."""

    __tablename__ = "bilan_readings"
    __table_args__ = (
        UniqueConstraint("file_id", "time", "metric_id", name="uq_bilan_readings_file_time_metric"),
        Index("ix_bilan_readings_metric_time", "metric_id", "time"),
        Index("ix_bilan_readings_file", "file_id"),
        {"schema": "timeseries"},
    )

    # ORM-side composite PK so SQLAlchemy is happy. Real DB has UNIQUE constraint
    # on the same columns (idempotency) — semantically equivalent for inserts.
    time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    file_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("meta.bilan_files.file_id"),
        primary_key=True,
        nullable=False,
    )
    metric_id: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    value: Mapped[float] = mapped_column(Double, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    raw_label: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp_synthetic: Mapped[bool | None] = mapped_column(Boolean, server_default="false")
    data_quality_flags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))


# ============================================================
# documents
# ============================================================

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "documents"}

    doc_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    file_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    extraction_status: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str | None] = mapped_column(Text)
    extraction_confidence: Mapped[float | None] = mapped_column(Double)
    extraction_warnings: Mapped[list | dict | None] = mapped_column(JSONB)


class OcrPage(Base):
    __tablename__ = "ocr_pages"
    __table_args__ = {"schema": "documents"}

    doc_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.documents.doc_id", ondelete="CASCADE"),
        primary_key=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_path: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[float | None] = mapped_column(Double)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = {"schema": "documents"}

    doc_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.documents.doc_id", ondelete="CASCADE"),
        primary_key=True,
    )
    vendor: Mapped[str | None] = mapped_column(Text)
    invoice_number: Mapped[str | None] = mapped_column(Text)
    invoice_date: Mapped[dt.date | None] = mapped_column(Date)
    due_date: Mapped[dt.date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(Text)
    subtotal: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2))
    tax: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2))
    total: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2))
    user_edited: Mapped[bool | None] = mapped_column(Boolean, server_default="false")
    edited_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    __table_args__ = (
        Index("ix_invoice_line_items_doc_line", "doc_id", "line_no"),
        {"schema": "documents"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.invoices.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    line_no: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[decimal.Decimal | None] = mapped_column(Numeric)
    unit_price: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2))
    line_total: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 2))
