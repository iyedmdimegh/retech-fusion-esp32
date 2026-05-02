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


# ============================================================
# analytics — BILAN consumption series
# ============================================================

class ConsumptionPoint(BaseModel):
    time: dt.datetime
    gas_nm3: float
    elec_produced_kwh: float
    grid_import_kwh: float
    grid_export_kwh: float
    grid_net_kwh: float


class ConsumptionTotals(BaseModel):
    gas_nm3: float
    elec_produced_kwh: float
    grid_import_kwh: float
    grid_export_kwh: float
    grid_net_kwh: float


class ConsumptionResponse(BaseModel):
    granularity: str
    from_: dt.datetime | None = None
    to: dt.datetime | None = None
    series: list[ConsumptionPoint]
    totals: ConsumptionTotals

    model_config = ConfigDict(populate_by_name=True)


class TopMetric(BaseModel):
    metric_id: str          # canonical id from mapping.yaml
    label: str              # raw French label from BILAN sheet
    category: str           # mapping category — used as the row subtitle
    unit: str
    total_delta: float      # max(value) - min(value) for cumulative meters
    n_readings: int


# ============================================================
# analytics — CO₂ series, breakdown, forecast, anomalies, model registry
# ============================================================

class Co2SeriesPoint(BaseModel):
    time: dt.datetime
    gas_nm3: float
    elec_produced_kwh: float
    grid_import_kwh: float
    grid_export_kwh: float
    grid_net_kwh: float
    co2_gas_kg: float
    co2_grid_kg: float
    co2_total_kg: float
    is_anomaly: bool
    anomaly_score: float | None = None


class Co2SeriesResponse(BaseModel):
    granularity: str
    points: list[Co2SeriesPoint]


class Co2BreakdownTotals(BaseModel):
    co2_total_kg: float
    co2_from_gas_kg: float
    co2_from_grid_kg: float
    gas_consumed_nm3: float
    elec_produced_kwh: float
    grid_imported_kwh: float
    grid_exported_kwh: float


class Co2BreakdownShare(BaseModel):
    gas_pct: float
    grid_pct: float


class Co2BreakdownResponse(BaseModel):
    from_: dt.datetime | None = None
    to: dt.datetime | None = None
    totals: Co2BreakdownTotals
    share: Co2BreakdownShare

    model_config = ConfigDict(populate_by_name=True)


class Co2ForecastPoint(BaseModel):
    target_time: dt.datetime
    horizon_hours: int
    predicted_co2_kg: float
    rmse_band: float | None = None


class Co2ForecastResponse(BaseModel):
    forecast_made_at: dt.datetime
    anchor_time: dt.datetime | None = None
    forecasts: list[Co2ForecastPoint]


class Co2Anomaly(BaseModel):
    time: dt.datetime
    co2_total_kg: float
    anomaly_score: float | None = None


class Co2AnomaliesResponse(BaseModel):
    from_: dt.datetime | None = None
    to: dt.datetime | None = None
    count: int
    anomalies: list[Co2Anomaly]

    model_config = ConfigDict(populate_by_name=True)


class Co2ModelStatus(BaseModel):
    model_id: uuid.UUID
    target: str
    horizon_hours: int
    algorithm: str
    n_train_samples: int | None = None
    n_test_samples: int | None = None
    mae: float | None = None
    rmse: float | None = None
    mape: float | None = None
    feature_count: int | None = None
    artifact_path: str
    trained_at: dt.datetime | None = None
    is_active: bool


class Co2RetrainResponse(BaseModel):
    status: str
    rows_in_dataset: int
    forecasters_trained: int
    anomalies_flagged: int
    duration_seconds: float
