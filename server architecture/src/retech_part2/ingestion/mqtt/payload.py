"""Pydantic v2 wire-protocol models for the ESP32 → broker payload.

Schema is what Phase 1 publishes today (firmware ≥ M13). The readings array
is variable length: a BME280 node emits 5 readings (temp + humidity + pressure
+ ds18b20 temp + acs712 current); a BMP280 node emits 4 (no humidity). We
do not validate count — we iterate.

Drop messages with ``timestamp.year < 2020`` (the device emits 1970-01-01
before NTP sync).
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

PRE_NTP_YEAR_CUTOFF = 2020


class EspReading(BaseModel):
    type: str       # temperature | humidity | pressure | current
    value: float
    unit: str       # celsius | percent | hPa | ampere
    sensor: str     # bme280 | bmp280 | ds18b20 | acs712


class EspReadingsPayload(BaseModel):
    device_id: str
    site: str
    timestamp: dt.datetime          # device's UTC clock; may lag on ring-buffer flush
    readings: list[EspReading] = Field(default_factory=list)
    status: Literal["ok", "invalid_reading"] = "ok"
    rssi: int | None = None
    uptime_s: int | None = None
    fw_version: str | None = None

    def is_pre_ntp(self) -> bool:
        return self.timestamp.year < PRE_NTP_YEAR_CUTOFF
