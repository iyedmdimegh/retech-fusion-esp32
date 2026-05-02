"""Shared analytics helpers for the BILAN consumption / CO₂ pipeline.

This module owns the cumulative-meter → per-interval-delta logic. Both the
plain `/api/bilan/consumption` endpoint AND the (forthcoming) M12 CO₂
pipeline call into ``build_consumption_series`` so the per-interval math
lives in exactly one place.

The same correctness rules from M12 apply here:

* Pull cumulative meters as long-format rows.
* **Filter out** rows tagged ``whole_column_zero`` or ``monotonic_inversion``
  in ``data_quality_flags`` — those are known-bad and would create huge
  spurious deltas (whole-column zeros) or go backwards (inversions).
* Pivot to wide.
* Resample to the requested granularity using ``.last()`` (cumulative
  meters → take the most recent reading in each bucket).
* ``.ffill()`` across any gaps. **Never ``.fillna(0)`` on a cumulative
  meter** — that would produce a fake reset and a huge positive delta on
  the next ``.diff()``.
* ``.diff()`` to get per-interval deltas.
* Clip negatives to 0 on gas + on-site electricity (real meters don't go
  backwards; if they do, the validator already flagged the row and we
  excluded it; any residual is a tiny rounding error).
* **Preserve the sign on grid_net** — exporting more than importing is
  intentional cogen behaviour, not an error.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Literal
from uuid import UUID

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from retech_part2.config import get_settings

Granularity = Literal["10min", "1h", "1d"]

# Cumulative meters we resample. Order matters only for column ordering in
# the output DataFrame.
GAS_VOLUME = "gas.volume_cumulative"
ELEC_PRODUCED = "electrical.alternator.energy_cumulative"
GRID_IMPORT = "grid.steg.import_cumulative"
GRID_EXPORT = "grid.steg.export_cumulative"

CUMULATIVE_METRIC_IDS: tuple[str, ...] = (
    GAS_VOLUME,
    ELEC_PRODUCED,
    GRID_IMPORT,
    GRID_EXPORT,
)

# pandas resample rule per UI granularity
_RESAMPLE_RULE: dict[str, str] = {
    "10min": "10min",
    "1h": "1h",
    "1d": "1D",
}

# data_quality_flags values that disqualify a reading from the analytics
_BAD_FLAGS: tuple[str, ...] = ("whole_column_zero", "monotonic_inversion")


@lru_cache
def _get_sync_engine() -> Engine:
    """Singleton sync engine for pandas read_sql. Separate from the async
    engine the API uses for ORM queries — pandas is sync-only.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url_sync,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=4,
    )


def build_consumption_series(
    *,
    file_id: UUID | None = None,
    from_dt: dt.datetime | None = None,
    to_dt: dt.datetime | None = None,
    granularity: Granularity = "1h",
    db_engine: Engine | None = None,
) -> pd.DataFrame:
    """Pull cumulative meters → per-interval deltas → grid_net.

    Returns a DataFrame indexed by UTC datetime with columns:
        gas_nm3, elec_produced_kwh, grid_import_kwh, grid_export_kwh, grid_net_kwh

    Empty DataFrame (with the right columns) if the filter excludes everything.
    """
    if granularity not in _RESAMPLE_RULE:
        raise ValueError(
            f"granularity must be one of {sorted(_RESAMPLE_RULE)}, got {granularity!r}"
        )

    engine = db_engine or _get_sync_engine()

    # Build the WHERE clause params dynamically; all bind via SQLAlchemy text params.
    sql = """
        SELECT time, metric_id, value
          FROM timeseries.bilan_readings
         WHERE metric_id = ANY(%(metrics)s)
           AND (data_quality_flags IS NULL
                OR NOT (data_quality_flags && %(bad_flags)s))
    """
    params: dict[str, object] = {
        "metrics": list(CUMULATIVE_METRIC_IDS),
        "bad_flags": list(_BAD_FLAGS),
    }
    if file_id is not None:
        sql += " AND file_id = %(file_id)s"
        params["file_id"] = str(file_id)
    if from_dt is not None:
        sql += " AND time >= %(from_dt)s"
        params["from_dt"] = from_dt
    if to_dt is not None:
        sql += " AND time <= %(to_dt)s"
        params["to_dt"] = to_dt

    long_df = pd.read_sql(sql, engine, params=params, parse_dates=["time"])

    return _consumption_from_long(long_df, granularity)


def _consumption_from_long(
    long_df: pd.DataFrame,
    granularity: Granularity,
) -> pd.DataFrame:
    """Pure compute. Extracted so future tests can call without DB."""
    out_cols = [
        "gas_nm3",
        "elec_produced_kwh",
        "grid_import_kwh",
        "grid_export_kwh",
        "grid_net_kwh",
    ]
    if long_df.empty:
        return pd.DataFrame(columns=out_cols).astype(float)

    if long_df["time"].dt.tz is None:
        long_df["time"] = long_df["time"].dt.tz_localize("UTC")

    wide = (
        long_df
        .pivot_table(index="time", columns="metric_id", values="value", aggfunc="last")
        .sort_index()
    )

    rule = _RESAMPLE_RULE[granularity]
    resampled = wide.resample(rule).last().ffill()

    deltas = resampled.diff()

    out = pd.DataFrame(index=deltas.index)
    out["gas_nm3"] = deltas.get(GAS_VOLUME, pd.Series(dtype=float)).clip(lower=0).fillna(0)
    out["elec_produced_kwh"] = deltas.get(ELEC_PRODUCED, pd.Series(dtype=float)).clip(lower=0).fillna(0)
    grid_import = deltas.get(GRID_IMPORT, pd.Series(dtype=float)).clip(lower=0).fillna(0)
    grid_export = deltas.get(GRID_EXPORT, pd.Series(dtype=float)).clip(lower=0).fillna(0)
    out["grid_import_kwh"] = grid_import
    out["grid_export_kwh"] = grid_export
    out["grid_net_kwh"] = grid_import - grid_export   # signed; export → negative

    return out


# ---------------------------------------------------------------------------
# CO₂ extension: per-interval consumption × emission factors.
# build_co2_dataset = build_consumption_series + factor multiplication.
# Both forecasters and the API /api/co2/breakdown call into this.
# ---------------------------------------------------------------------------


def build_co2_dataset(
    *,
    file_id: UUID | None = None,
    from_dt: dt.datetime | None = None,
    to_dt: dt.datetime | None = None,
    granularity: Granularity = "1h",
    db_engine: Engine | None = None,
) -> pd.DataFrame:
    """Returns DataFrame indexed by UTC datetime with the consumption columns
    plus three CO₂ columns:

        co2_gas_kg   = gas_nm3       * KG_CO2_PER_NM3_NATURAL_GAS
        co2_grid_kg  = grid_net_kwh  * KG_CO2_PER_KWH_STEG_GRID    # signed!
        co2_total_kg = co2_gas_kg + co2_grid_kg

    Negative ``co2_grid_kg`` is preserved — it's the cogen export benefit
    (exported electricity displaces grid electricity emitted elsewhere).
    """
    from retech_part2.analytics.co2.factors import (
        KG_CO2_PER_KWH_STEG_GRID,
        KG_CO2_PER_NM3_NATURAL_GAS,
    )

    df = build_consumption_series(
        file_id=file_id,
        from_dt=from_dt,
        to_dt=to_dt,
        granularity=granularity,
        db_engine=db_engine,
    )
    df = df.copy()
    df["co2_gas_kg"] = df["gas_nm3"] * KG_CO2_PER_NM3_NATURAL_GAS
    df["co2_grid_kg"] = df["grid_net_kwh"] * KG_CO2_PER_KWH_STEG_GRID
    df["co2_total_kg"] = df["co2_gas_kg"] + df["co2_grid_kg"]
    return df
