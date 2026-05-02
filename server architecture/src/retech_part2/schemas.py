"""Pydantic v2 response/request schemas."""
from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class _ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# meta
# ============================================================

class DeviceOut(_ORMBase):
    device_id: str
    site: str
    fw_version: str | None = None
    first_seen: dt.datetime | None = None
    last_seen: dt.datetime | None = None


class BilanFileOut(_ORMBase):
    file_id: uuid.UUID
    file_hash: str
    filename: str
    parsed_at: dt.datetime | None = None
    date_range_start: dt.date | None = None
    date_range_end: dt.date | None = None
    rows_inserted: int | None = None
    rows_dropped: int | None = None
    unmapped_params: list[Any] | dict[str, Any] | None = None
    status: str
    warnings: list[Any] | dict[str, Any] | None = None


class IngestionJobOut(_ORMBase):
    job_id: uuid.UUID
    job_type: str
    source_path: str | None = None
    file_hash: str | None = None
    status: str
    progress: int = 0
    error_message: str | None = None
    warnings: list[Any] | dict[str, Any] | None = None
    created_at: dt.datetime | None = None
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None


# ============================================================
# timeseries
# ============================================================

class ReadingOut(_ORMBase):
    time: dt.datetime
    ingested_at: dt.datetime | None = None
    device_id: str
    sensor: str
    type: str
    value: float
    unit: str


class DeviceStatusOut(_ORMBase):
    time: dt.datetime
    device_id: str
    status: str
    rssi: int | None = None
    uptime_s: int | None = None
    fw_version: str | None = None
    drift_alert: bool | None = None


class BilanReadingOut(_ORMBase):
    time: dt.datetime
    file_id: uuid.UUID
    metric_id: str
    value: float
    unit: str
    raw_label: str
    timestamp_synthetic: bool | None = None
    data_quality_flags: list[str] | None = None


# ============================================================
# documents
# ============================================================

class DocumentOut(_ORMBase):
    doc_id: uuid.UUID
    file_hash: str
    doc_type: str
    source_file: str
    page_count: int | None = None
    uploaded_at: dt.datetime | None = None
    extraction_status: str
    extraction_method: str | None = None
    extraction_confidence: float | None = None
    extraction_warnings: list[Any] | dict[str, Any] | None = None


class OcrPageOut(_ORMBase):
    doc_id: uuid.UUID
    page_number: int
    image_path: str | None = None
    text: str | None = None
    ocr_confidence: float | None = None


class InvoiceLineItemOut(_ORMBase):
    id: int
    doc_id: uuid.UUID
    line_no: int | None = None
    description: str | None = None
    quantity: decimal.Decimal | None = None
    unit_price: decimal.Decimal | None = None
    line_total: decimal.Decimal | None = None


class InvoiceOut(_ORMBase):
    doc_id: uuid.UUID
    vendor: str | None = None
    invoice_number: str | None = None
    invoice_date: dt.date | None = None
    due_date: dt.date | None = None
    currency: str | None = None
    subtotal: decimal.Decimal | None = None
    tax: decimal.Decimal | None = None
    total: decimal.Decimal | None = None
    user_edited: bool | None = None
    edited_at: dt.datetime | None = None
