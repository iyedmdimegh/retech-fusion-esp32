"""Post-insert validation for BILAN readings.

Two checks land here:
  * **Range** — value outside the YAML's ``range: [min, max]``. Applies to
    every metric with a defined range, including ``derived: true`` ones (a
    derived efficiency must still fall within 0..100 %).
  * **Monotonic** — cumulative meter went backward in time order. Applies to
    metrics with ``monotonic: true`` and **NOT** ``derived: true`` (derived
    series fluctuate by definition).

Both run as bulk SQL UPDATEs against the hypertable for speed. Returns
per-metric counts so the loader / CLI can surface them to the user.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from retech_part2.ingestion.bilan.mapping import MappingEntry


@dataclass(frozen=True)
class Inversion:
    metric_id: str
    time: object  # datetime
    value: float
    prev_time: object
    prev_value: float
    dip: float


# ---------------------------------------------------------------------------
# range checks
# ---------------------------------------------------------------------------

_RANGE_UPDATE = text(
    """
    UPDATE timeseries.bilan_readings
       SET data_quality_flags = COALESCE(data_quality_flags, ARRAY[]::text[])
                                 || ARRAY['range_violation']
     WHERE file_id = :file_id
       AND metric_id = :metric_id
       AND (value < :lo OR value > :hi)
       AND NOT ('range_violation' = ANY(COALESCE(data_quality_flags, ARRAY[]::text[])))
    """
)


async def apply_range_checks(
    session: AsyncSession,
    *,
    file_id: UUID,
    entries: Iterable[MappingEntry],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.range is None:
            continue
        lo, hi = entry.range
        result = await session.execute(
            _RANGE_UPDATE,
            {"file_id": file_id, "metric_id": entry.metric_id, "lo": lo, "hi": hi},
        )
        if result.rowcount:
            counts[entry.metric_id] = result.rowcount
    await session.commit()
    return counts


# ---------------------------------------------------------------------------
# monotonic checks
# ---------------------------------------------------------------------------

_MONOTONIC_UPDATE = text(
    """
    WITH ordered AS (
        SELECT time, file_id, metric_id, value,
               LAG(value) OVER (PARTITION BY metric_id ORDER BY time, ctid) AS prev_value
          FROM timeseries.bilan_readings
         WHERE file_id = :file_id AND metric_id = :metric_id
    )
    UPDATE timeseries.bilan_readings r
       SET data_quality_flags = COALESCE(r.data_quality_flags, ARRAY[]::text[])
                                 || ARRAY['monotonic_inversion']
      FROM ordered o
     WHERE r.file_id   = o.file_id
       AND r.metric_id = o.metric_id
       AND r.time      = o.time
       AND o.prev_value IS NOT NULL
       AND o.value < o.prev_value
       AND NOT ('monotonic_inversion' = ANY(COALESCE(r.data_quality_flags, ARRAY[]::text[])))
    """
)


async def apply_monotonic_checks(
    session: AsyncSession,
    *,
    file_id: UUID,
    entries: Iterable[MappingEntry],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        if not entry.monotonic or entry.derived:
            continue
        result = await session.execute(
            _MONOTONIC_UPDATE,
            {"file_id": file_id, "metric_id": entry.metric_id},
        )
        if result.rowcount:
            counts[entry.metric_id] = result.rowcount
    await session.commit()
    return counts


# ---------------------------------------------------------------------------
# whole-column-zero detection
# ---------------------------------------------------------------------------
# Every cumulative meter going to 0 at the same instant is almost certainly a
# system-wide logging gap (instrument disconnect, source-system blank), not a
# per-meter glitch. Tagging it separately lets Phase 3 distinguish the two.

_WHOLE_COLUMN_ZERO_UPDATE = text(
    """
    WITH zero_times AS (
        SELECT time
          FROM timeseries.bilan_readings
         WHERE file_id = :file_id
           AND value = 0
           AND metric_id = ANY(:cumulative_ids)
         GROUP BY time
         HAVING COUNT(DISTINCT metric_id) >= 3
    )
    UPDATE timeseries.bilan_readings r
       SET data_quality_flags = COALESCE(r.data_quality_flags, ARRAY[]::text[])
                                 || ARRAY['whole_column_zero']
      FROM zero_times z
     WHERE r.file_id = :file_id
       AND r.time = z.time
       AND r.value = 0
       AND r.metric_id = ANY(:cumulative_ids)
       AND NOT ('whole_column_zero' = ANY(COALESCE(r.data_quality_flags, ARRAY[]::text[])))
    """
)


async def apply_whole_column_zero_check(
    session: AsyncSession,
    *,
    file_id: UUID,
    entries: Iterable[MappingEntry],
) -> int:
    """Tag rows where ≥3 cumulative metrics at the same time are all 0.

    Runs after the monotonic check (the inversion-to-0 case is what triggers
    the suspicion in the first place). Returns total rows tagged.
    """
    cumulative_ids = [e.metric_id for e in entries if e.monotonic and not e.derived]
    if not cumulative_ids:
        return 0
    result = await session.execute(
        _WHOLE_COLUMN_ZERO_UPDATE,
        {"file_id": file_id, "cumulative_ids": cumulative_ids},
    )
    await session.commit()
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# diagnostics: worst inversions for one metric
# ---------------------------------------------------------------------------

_WORST_INVERSIONS = text(
    """
    WITH ordered AS (
        SELECT time, value,
               LAG(value) OVER (ORDER BY time, ctid) AS prev_value,
               LAG(time)  OVER (ORDER BY time, ctid) AS prev_time
          FROM timeseries.bilan_readings
         WHERE file_id = :file_id AND metric_id = :metric_id
    )
    SELECT time, value, prev_time, prev_value, (prev_value - value) AS dip
      FROM ordered
     WHERE prev_value IS NOT NULL AND value < prev_value
     ORDER BY (prev_value - value) DESC
     LIMIT :limit
    """
)


async def get_worst_inversions(
    session: AsyncSession,
    *,
    file_id: UUID,
    metric_id: str,
    limit: int = 5,
) -> list[Inversion]:
    result = await session.execute(
        _WORST_INVERSIONS,
        {"file_id": file_id, "metric_id": metric_id, "limit": limit},
    )
    return [
        Inversion(
            metric_id=metric_id,
            time=row.time,
            value=float(row.value),
            prev_time=row.prev_time,
            prev_value=float(row.prev_value),
            dip=float(row.dip),
        )
        for row in result.all()
    ]
