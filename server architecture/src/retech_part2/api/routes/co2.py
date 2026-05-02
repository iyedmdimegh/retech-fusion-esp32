"""CO₂ analytics endpoints — read-side queries against analytics.* tables
plus a synchronous /retrain that re-runs the M12 training pipeline.

The model artefacts live on disk (data/models/); the API just reads the
latest materialised state from the DB tables. /retrain is intentionally
synchronous for the checkpoint demo — the full training run takes ~5–15 s
on the April BILAN sample, well within an HTTP timeout.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from retech_part2.config import get_settings
from retech_part2.db import get_session
from retech_part2.schemas import (
    Co2Anomaly,
    Co2AnomaliesResponse,
    Co2BreakdownResponse,
    Co2BreakdownShare,
    Co2BreakdownTotals,
    Co2ForecastPoint,
    Co2ForecastResponse,
    Co2ModelStatus,
    Co2RetrainResponse,
    Co2SeriesPoint,
    Co2SeriesResponse,
)

router = APIRouter()
SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ---------------------------------------------------------------------------
# /api/co2/series
# ---------------------------------------------------------------------------

@router.get("/series", response_model=Co2SeriesResponse)
async def co2_series(
    session: SessionDep,
    from_: dt.datetime | None = Query(None, alias="from"),
    to: dt.datetime | None = None,
    limit: int = Query(2000, ge=1, le=20000),
) -> Co2SeriesResponse:
    sql = """
        SELECT "time", gas_nm3, elec_produced_kwh, grid_import_kwh,
               grid_export_kwh, grid_net_kwh, co2_gas_kg, co2_grid_kg,
               co2_total_kg, is_anomaly, anomaly_score
          FROM analytics.co2_hourly
         WHERE 1 = 1
    """
    params: dict[str, object] = {}
    if from_ is not None:
        sql += ' AND "time" >= :from_'
        params["from_"] = from_
    if to is not None:
        sql += ' AND "time" <= :to'
        params["to"] = to
    sql += ' ORDER BY "time" ASC LIMIT :limit'
    params["limit"] = limit

    rows = (await session.execute(text(sql), params)).mappings().all()
    return Co2SeriesResponse(
        granularity="1h",
        points=[Co2SeriesPoint(**dict(r)) for r in rows],
    )


# ---------------------------------------------------------------------------
# /api/co2/breakdown
# ---------------------------------------------------------------------------

@router.get("/breakdown", response_model=Co2BreakdownResponse)
async def co2_breakdown(
    session: SessionDep,
    from_: dt.datetime | None = Query(None, alias="from"),
    to: dt.datetime | None = None,
) -> Co2BreakdownResponse:
    sql = """
        SELECT COALESCE(SUM(co2_total_kg), 0)        AS co2_total_kg,
               COALESCE(SUM(co2_gas_kg), 0)          AS co2_from_gas_kg,
               COALESCE(SUM(co2_grid_kg), 0)         AS co2_from_grid_kg,
               COALESCE(SUM(gas_nm3), 0)             AS gas_consumed_nm3,
               COALESCE(SUM(elec_produced_kwh), 0)   AS elec_produced_kwh,
               COALESCE(SUM(grid_import_kwh), 0)     AS grid_imported_kwh,
               COALESCE(SUM(grid_export_kwh), 0)     AS grid_exported_kwh
          FROM analytics.co2_hourly
         WHERE 1 = 1
    """
    params: dict[str, object] = {}
    if from_ is not None:
        sql += ' AND "time" >= :from_'
        params["from_"] = from_
    if to is not None:
        sql += ' AND "time" <= :to'
        params["to"] = to

    row = (await session.execute(text(sql), params)).mappings().one()
    totals = Co2BreakdownTotals(**dict(row))
    # Share computed on absolute values so net-export doesn't make grid share negative.
    abs_total = abs(totals.co2_from_gas_kg) + abs(totals.co2_from_grid_kg)
    if abs_total > 0:
        share = Co2BreakdownShare(
            gas_pct=round(100 * abs(totals.co2_from_gas_kg) / abs_total, 2),
            grid_pct=round(100 * abs(totals.co2_from_grid_kg) / abs_total, 2),
        )
    else:
        share = Co2BreakdownShare(gas_pct=0.0, grid_pct=0.0)
    return Co2BreakdownResponse(from_=from_, to=to, totals=totals, share=share)


# ---------------------------------------------------------------------------
# /api/co2/forecast
# ---------------------------------------------------------------------------

@router.get("/forecast", response_model=Co2ForecastResponse)
async def co2_forecast(session: SessionDep) -> Co2ForecastResponse:
    sql = """
        WITH latest AS (
          SELECT MAX(forecast_made_at) AS made_at FROM analytics.co2_forecasts
        )
        SELECT f.target_time, f.horizon_hours, f.predicted_co2_kg, f.forecast_made_at
          FROM analytics.co2_forecasts f, latest
         WHERE f.forecast_made_at = latest.made_at
         ORDER BY f.horizon_hours ASC
    """
    rows = (await session.execute(text(sql))).mappings().all()
    if not rows:
        return Co2ForecastResponse(
            forecast_made_at=dt.datetime.now(dt.timezone.utc),
            anchor_time=None,
            forecasts=[],
        )
    made_at = rows[0]["forecast_made_at"]
    # Pull the active models' RMSE so we can attach it as the band.
    rmse_rows = (
        await session.execute(
            text(
                """
                SELECT horizon_hours, rmse FROM analytics.co2_models
                 WHERE target = 'co2_total_kg' AND is_active = TRUE
                """
            )
        )
    ).mappings().all()
    rmse_by_h = {r["horizon_hours"]: r["rmse"] for r in rmse_rows}
    return Co2ForecastResponse(
        forecast_made_at=made_at,
        anchor_time=min(r["target_time"] for r in rows) - dt.timedelta(hours=int(rows[0]["horizon_hours"])),
        forecasts=[
            Co2ForecastPoint(
                target_time=r["target_time"],
                horizon_hours=int(r["horizon_hours"]),
                predicted_co2_kg=float(r["predicted_co2_kg"]),
                rmse_band=float(rmse_by_h.get(int(r["horizon_hours"]), 0.0))
                    if rmse_by_h.get(int(r["horizon_hours"])) is not None else None,
            )
            for r in rows
        ],
    )


# ---------------------------------------------------------------------------
# /api/co2/anomalies
# ---------------------------------------------------------------------------

@router.get("/anomalies", response_model=Co2AnomaliesResponse)
async def co2_anomalies(
    session: SessionDep,
    from_: dt.datetime | None = Query(None, alias="from"),
    to: dt.datetime | None = None,
) -> Co2AnomaliesResponse:
    sql = """
        SELECT "time", co2_total_kg, anomaly_score
          FROM analytics.co2_hourly
         WHERE is_anomaly = TRUE
    """
    params: dict[str, object] = {}
    if from_ is not None:
        sql += ' AND "time" >= :from_'
        params["from_"] = from_
    if to is not None:
        sql += ' AND "time" <= :to'
        params["to"] = to
    sql += ' ORDER BY anomaly_score DESC NULLS LAST'
    rows = (await session.execute(text(sql), params)).mappings().all()
    return Co2AnomaliesResponse(
        from_=from_,
        to=to,
        count=len(rows),
        anomalies=[Co2Anomaly(**dict(r)) for r in rows],
    )


# ---------------------------------------------------------------------------
# /api/co2/models/status
# ---------------------------------------------------------------------------

@router.get("/models/status", response_model=list[Co2ModelStatus])
async def co2_models_status(session: SessionDep) -> list[Co2ModelStatus]:
    sql = """
        SELECT model_id, target, horizon_hours, algorithm,
               n_train_samples, n_test_samples,
               mae, rmse, mape, feature_count,
               artifact_path, trained_at, is_active
          FROM analytics.co2_models
         WHERE is_active = TRUE
         ORDER BY target ASC, horizon_hours ASC
    """
    rows = (await session.execute(text(sql))).mappings().all()
    return [Co2ModelStatus(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# POST /api/co2/retrain  (synchronous)
# ---------------------------------------------------------------------------

@router.post("/retrain", response_model=Co2RetrainResponse)
async def co2_retrain() -> Co2RetrainResponse:
    """Re-run the full training pipeline. Synchronous — the dataset is
    small enough that this completes well within an HTTP request window
    (~5–15 s on the April BILAN sample). For larger datasets this should
    be moved behind the existing RQ worker pattern.
    """
    from retech_part2.analytics.co2.train import run_full_training

    horizons = get_settings().co2_horizons_list
    t0 = time.perf_counter()
    try:
        result = await run_full_training(horizons=horizons)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    elapsed = time.perf_counter() - t0
    return Co2RetrainResponse(
        status="ok",
        rows_in_dataset=int(result["rows_in_dataset"]),
        forecasters_trained=len(result["forecasters"]),
        anomalies_flagged=int(result["anomalies_flagged"]),
        duration_seconds=round(elapsed, 2),
    )
