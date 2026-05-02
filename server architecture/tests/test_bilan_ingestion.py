"""Integration tests for the BILAN ingestion path. Requires a running DB.

Implementation note: collapsed into a single async test by design. Spinning up
multiple ``asyncio.run()`` calls across pytest fixtures + test functions
breaks on Windows because the SQLAlchemy async engine caches connections
bound to whichever event loop created them, and the proactor cleanup chokes
when the original loop is gone. Running the whole lifecycle inside one loop
sidesteps the problem and still exercises every branch.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy import delete, text

from retech_part2.db import get_session_factory
from retech_part2.ingestion.bilan.loader import ingest_bilan
from retech_part2.ingestion.bilan.mapping import load_mappings
from retech_part2.models import BilanFile
from retech_part2.utils.hashing import sha256_file

SAMPLE_FILE = (
    Path(__file__).parent.parent / "data" / "samples" / "avril-report1_2442026.xlsx"
)
pytestmark = pytest.mark.skipif(
    not SAMPLE_FILE.exists(), reason=f"sample file not present at {SAMPLE_FILE}"
)


async def _wipe_existing_for(file_hash: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("SELECT file_id FROM meta.bilan_files WHERE file_hash = :h"),
            {"h": file_hash},
        )
        row = result.first()
        if row is None:
            return
        file_id = row.file_id
        await session.execute(
            text("DELETE FROM timeseries.bilan_readings WHERE file_id = :id"),
            {"id": file_id},
        )
        await session.execute(delete(BilanFile).where(BilanFile.file_id == file_id))
        await session.commit()


async def test_full_ingestion_lifecycle() -> None:
    """End-to-end: clean slate → ingest → assert shape, accounting, validator
    output → re-ingest → assert idempotent."""
    file_hash = sha256_file(SAMPLE_FILE)
    await _wipe_existing_for(file_hash)

    # ---- first ingest --------------------------------------------------
    first = await ingest_bilan(SAMPLE_FILE)

    # basic shape
    assert first.status in ("success", "partial_success"), first.status
    assert first.duplicate is False
    assert first.file_id is not None
    assert first.rows_inserted > 100_000

    # row accounting (parser → mapper → dedup → COPY must lose nothing unexpected)
    expected_inserts = (
        first.rows_parsed
        - first.rows_dropped_unmapped
        - first.rows_dropped_duplicate_in_file
    )
    assert first.rows_inserted == expected_inserts, (
        f"unexplained gap: parsed={first.rows_parsed} "
        f"inserted={first.rows_inserted} unmapped={first.rows_dropped_unmapped} "
        f"intra-file-dup={first.rows_dropped_duplicate_in_file}"
    )

    # date range is what we expect
    assert first.date_range == (dt.date(2025, 4, 1), dt.date(2025, 4, 20))

    factory = get_session_factory()

    # gas.flow_rate values look plausible (~270 Nm3/h)
    async with factory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT MIN(value) AS lo, MAX(value) AS hi, AVG(value) AS mean
                      FROM timeseries.bilan_readings
                     WHERE file_id = :id AND metric_id = 'gas.flow_rate'
                    """
                ),
                {"id": first.file_id},
            )
        ).one()
    assert row.mean is not None and 50 < float(row.mean) < 500, (
        f"gas.flow_rate mean={row.mean} (lo={row.lo}, hi={row.hi})"
    )

    # every metric_id in the DB must come from the YAML
    yaml_ids = {e.metric_id for e in load_mappings()}
    async with factory() as session:
        db_ids = {
            r.metric_id
            for r in (
                await session.execute(
                    text(
                        "SELECT DISTINCT metric_id FROM timeseries.bilan_readings "
                        "WHERE file_id = :id"
                    ),
                    {"id": first.file_id},
                )
            ).all()
        }
    assert db_ids.issubset(yaml_ids), f"unknown metric_ids in DB: {db_ids - yaml_ids}"

    # validator: gas.volume_cumulative had backward steps, must be flagged
    async with factory() as session:
        flagged = int(
            (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM timeseries.bilan_readings
                         WHERE file_id = :id
                           AND metric_id = 'gas.volume_cumulative'
                           AND 'monotonic_inversion' = ANY(data_quality_flags)
                        """
                    ),
                    {"id": first.file_id},
                )
            ).scalar_one()
        )
    assert flagged >= 1, "expected at least one monotonic_inversion on gas.volume_cumulative"

    # validator: derived efficiency metrics must NOT receive monotonic flags
    async with factory() as session:
        bad = int(
            (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM timeseries.bilan_readings
                         WHERE file_id = :id
                           AND metric_id LIKE 'efficiency.%'
                           AND 'monotonic_inversion' = ANY(data_quality_flags)
                        """
                    ),
                    {"id": first.file_id},
                )
            ).scalar_one()
        )
    assert bad == 0, f"derived metrics should not get monotonic_inversion; got {bad} rows"

    # ---- second ingest (idempotency) -----------------------------------
    second = await ingest_bilan(SAMPLE_FILE)
    assert second.duplicate is True
    assert second.status == "duplicate"
    assert second.rows_inserted == 0
    assert second.file_id == first.file_id

    # DB row count for this file must be unchanged
    async with factory() as session:
        count_after = int(
            (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM timeseries.bilan_readings "
                        "WHERE file_id = :id"
                    ),
                    {"id": first.file_id},
                )
            ).scalar_one()
        )
    assert count_after == first.rows_inserted, (
        f"row count drifted after re-ingest: before={first.rows_inserted} after={count_after}"
    )
