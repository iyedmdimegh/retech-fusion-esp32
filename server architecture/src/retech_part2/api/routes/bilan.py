"""BILAN file metadata + per-interval consumption series."""
from __future__ import annotations

import asyncio
import datetime as dt
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from retech_part2.analytics.co2.pipeline import build_consumption_series
from retech_part2.db import get_session
from retech_part2.models import BilanFile
from retech_part2.schemas import (
    BilanFileOut,
    ConsumptionPoint,
    ConsumptionResponse,
    ConsumptionTotals,
    TopMetric,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/files", response_model=list[BilanFileOut])
async def list_files(
    session: SessionDep,
    limit: int = Query(50, ge=1, le=500),
) -> list[BilanFile]:
    stmt = select(BilanFile).order_by(BilanFile.parsed_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/top-metrics", response_model=list[TopMetric])
async def top_metrics(
    session: SessionDep,
    limit: int = Query(8, ge=1, le=30),
) -> list[TopMetric]:
    """Top-N cumulative-meter metrics ranked by total consumption (max-min).

    Only ``monotonic`` and not ``derived`` metrics qualify (the YAML knows).
    Excludes rows tagged ``whole_column_zero`` / ``monotonic_inversion`` —
    same data-quality filter the rest of the analytics use.
    """
    from retech_part2.ingestion.bilan.mapping import load_mappings

    entries = [e for e in load_mappings() if e.monotonic and not e.derived]
    if not entries:
        return []
    by_metric_id = {e.metric_id: e for e in entries}

    sql = text(
        """
        SELECT metric_id,
               unit,
               (MAX(value) - MIN(value)) AS total_delta,
               COUNT(*)                  AS n_readings
          FROM timeseries.bilan_readings
         WHERE metric_id = ANY(:ids)
           AND (data_quality_flags IS NULL
                OR NOT (data_quality_flags && ARRAY['whole_column_zero', 'monotonic_inversion']))
         GROUP BY metric_id, unit
         ORDER BY total_delta DESC
         LIMIT :limit
        """
    )
    rows = (
        await session.execute(sql, {"ids": list(by_metric_id), "limit": limit})
    ).mappings().all()

    out: list[TopMetric] = []
    for r in rows:
        e = by_metric_id.get(r["metric_id"])
        if e is None:
            continue
        out.append(
            TopMetric(
                metric_id=r["metric_id"],
                label=e.match_text,
                category=e.category,
                unit=r["unit"],
                total_delta=float(r["total_delta"] or 0.0),
                n_readings=int(r["n_readings"]),
            )
        )
    return out


@router.get("/consumption", response_model=ConsumptionResponse)
async def get_consumption(
    file_id: UUID | None = None,
    from_: dt.datetime | None = Query(None, alias="from"),
    to: dt.datetime | None = None,
    granularity: Literal["10min", "1h", "1d"] = "1h",
) -> ConsumptionResponse:
    """Per-interval consumption series for the energy-analytics page.

    pandas + read_sql is sync; we offload to a thread so the async loop
    stays free.
    """
    df = await asyncio.to_thread(
        build_consumption_series,
        file_id=file_id,
        from_dt=from_,
        to_dt=to,
        granularity=granularity,
    )

    series = [
        ConsumptionPoint(
            time=ts.to_pydatetime(),
            gas_nm3=float(row.gas_nm3),
            elec_produced_kwh=float(row.elec_produced_kwh),
            grid_import_kwh=float(row.grid_import_kwh),
            grid_export_kwh=float(row.grid_export_kwh),
            grid_net_kwh=float(row.grid_net_kwh),
        )
        for ts, row in df.iterrows()
    ]
    totals = ConsumptionTotals(
        gas_nm3=float(df["gas_nm3"].sum()),
        elec_produced_kwh=float(df["elec_produced_kwh"].sum()),
        grid_import_kwh=float(df["grid_import_kwh"].sum()),
        grid_export_kwh=float(df["grid_export_kwh"].sum()),
        grid_net_kwh=float(df["grid_net_kwh"].sum()),
    )

    return ConsumptionResponse(
        granularity=granularity,
        from_=from_,
        to=to,
        series=series,
        totals=totals,
    )
