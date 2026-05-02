"""End-to-end ingestion of a BILAN file into TimescaleDB.

Sequence:
  1. SHA-256 the file. If a `success` / `partial_success` row already exists in
     `meta.bilan_files` with this hash → idempotent no-op (single warning
     `duplicate_file`). If a `pending` / `failed` row exists, clean it up
     (delete its readings + the row itself) and proceed fresh — half-ingested
     state is not safe to leave around.
  2. Parse the workbook in a worker thread (openpyxl is CPU-bound).
  3. Resolve every (raw_label, category) via the YAML mapping; readings whose
     pair is unmapped are skipped and recorded in `unmapped_params`.
  4. Insert a `meta.bilan_files` row with status='pending'. The returned
     `file_id` is what the readings reference.
  5. Bulk-insert via **psycopg COPY** in a fresh **synchronous** connection
     (per the project decision — do NOT share the SQLAlchemy async session
     for this; COPY is sync-only in psycopg).
  6. Run the validator: range checks (every metric with `range:`) and monotonic
     checks (`monotonic: true` AND NOT `derived: true`). Both write
     `data_quality_flags` array entries via SQL UPDATE.
  7. Update `meta.bilan_files` with the final status, row counts, warnings.

The COPY connection is opened just for step 5 and closed in a `finally`.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID

import psycopg
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from retech_part2.config import get_settings
from retech_part2.db import get_session_factory
from retech_part2.ingestion.bilan import mapping as mapping_module
from retech_part2.ingestion.bilan.parser import ParsedBilan, parse_bilan
from retech_part2.ingestion.bilan.validator import (
    apply_monotonic_checks,
    apply_range_checks,
    apply_whole_column_zero_check,
)
from retech_part2.logging import get_logger
from retech_part2.models import BilanFile
from retech_part2.utils.hashing import sha256_file

log = get_logger("bilan.loader")

DUPLICATE_WARNING = "duplicate_file"
TERMINAL_STATUSES: frozenset[str] = frozenset({"success", "partial_success"})

_COPY_SQL = (
    "COPY timeseries.bilan_readings "
    "(time, file_id, metric_id, value, unit, raw_label, "
    "timestamp_synthetic, data_quality_flags) "
    "FROM STDIN"
)
_COPY_TYPES = (
    "timestamptz",
    "uuid",
    "text",
    "float8",
    "text",
    "text",
    "bool",
    "text[]",
)


@dataclass
class IngestionResult:
    status: Literal["success", "partial_success", "failed", "duplicate"]
    file_hash: str
    file_id: UUID | None
    rows_parsed: int
    rows_mapped: int
    rows_inserted: int
    rows_dropped_unmapped: int
    rows_dropped_duplicate_in_file: int = 0
    duplicate: bool = False
    date_range: tuple[dt.date, dt.date] | None = None
    unmapped_params: list[dict[str, str]] = field(default_factory=list)
    range_violations_by_metric: dict[str, int] = field(default_factory=dict)
    monotonic_inversions_by_metric: dict[str, int] = field(default_factory=dict)
    whole_column_zero_rows: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# step 1 — dedup check
# ---------------------------------------------------------------------------

async def _existing_terminal_file(session: AsyncSession, file_hash: str) -> BilanFile | None:
    result = await session.execute(
        select(BilanFile).where(BilanFile.file_hash == file_hash)
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        return None
    if existing.status in TERMINAL_STATUSES:
        return existing
    # Stale row from a previous failed/in-progress run — wipe it so we can retry.
    log.warning(
        "stale_bilan_file_row_found",
        file_hash=file_hash,
        prior_status=existing.status,
        file_id=str(existing.file_id),
    )
    await session.execute(
        text("DELETE FROM timeseries.bilan_readings WHERE file_id = :id"),
        {"id": existing.file_id},
    )
    await session.execute(delete(BilanFile).where(BilanFile.file_id == existing.file_id))
    await session.commit()
    return None


# ---------------------------------------------------------------------------
# step 5 — sync COPY in its own psycopg connection
# ---------------------------------------------------------------------------

def _copy_rows_sync(dsn: str, file_id: UUID, rows: list[tuple]) -> int:
    """Open a fresh sync psycopg connection, COPY rows, return inserted count.

    NOT shared with the async SQLAlchemy session by design.
    """
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            with cur.copy(_COPY_SQL) as cp:
                cp.set_types(list(_COPY_TYPES))
                for row in rows:
                    cp.write_row(row)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM timeseries.bilan_readings WHERE file_id = %s",
                (file_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------

async def ingest_bilan(file_path: Path) -> IngestionResult:
    settings = get_settings()
    factory = get_session_factory()

    file_hash = sha256_file(file_path)
    log.info("ingest_start", file=str(file_path), file_hash=file_hash[:16])

    # 1. dedup check
    async with factory() as session:
        existing = await _existing_terminal_file(session, file_hash)
        if existing is not None:
            log.info(
                "ingest_duplicate",
                file_hash=file_hash[:16],
                file_id=str(existing.file_id),
                prior_status=existing.status,
            )
            return IngestionResult(
                status="duplicate",
                file_hash=file_hash,
                file_id=existing.file_id,
                rows_parsed=0,
                rows_mapped=0,
                rows_inserted=0,
                rows_dropped_unmapped=0,
                duplicate=True,
                date_range=(existing.date_range_start, existing.date_range_end)
                    if existing.date_range_start and existing.date_range_end else None,
                warnings=[DUPLICATE_WARNING],
            )

    # 2. parse
    parsed: ParsedBilan = await asyncio.to_thread(parse_bilan, file_path)
    log.info(
        "ingest_parsed",
        rows_parsed=len(parsed.readings),
        date_range=[parsed.date_range[0].isoformat(), parsed.date_range[1].isoformat()],
        parser_warnings=len(parsed.parse_warnings),
    )

    # 3. apply mapping
    mapped_rows: list[tuple] = []
    unmapped: dict[tuple[str, str], int] = {}
    for r in parsed.readings:
        entry = (
            mapping_module.match(r.raw_label, r.category)
            if r.category
            else mapping_module.match(r.raw_label)
        )
        if entry is None:
            key = (r.raw_label, r.category)
            unmapped[key] = unmapped.get(key, 0) + 1
            continue
        mapped_rows.append(
            (
                r.time,            # time
                None,              # file_id (filled after we insert bilan_files)
                entry.metric_id,
                r.value,
                entry.unit,
                r.raw_label,
                bool(r.timestamp_synthetic),
                [],                # data_quality_flags
            )
        )

    rows_dropped = sum(unmapped.values())
    log.info("ingest_mapped", mapped=len(mapped_rows), dropped_unmapped=rows_dropped)

    # 3b. dedup within the file. Real BILAN data sometimes records two
    # consecutive samples at the same logged timestamp for the same metric
    # (operator double-press, clock not advancing, etc.). The hypertable's
    # UNIQUE (file_id, time, metric_id) constraint would reject the COPY
    # mid-stream — so we drop the later occurrence here. Per the spec, column
    # order is the true logging sequence, so "first wins" maps to "earliest
    # column wins", which is what we want.
    seen: set[tuple[dt.datetime, str]] = set()
    deduped: list[tuple] = []
    duplicates_in_file = 0
    for row in mapped_rows:
        key = (row[0], row[2])  # (time, metric_id)
        if key in seen:
            duplicates_in_file += 1
            continue
        seen.add(key)
        deduped.append(row)
    if duplicates_in_file:
        log.warning("ingest_intra_file_duplicates_dropped", count=duplicates_in_file)
    mapped_rows = deduped

    # 4. insert bilan_files (status=pending)
    async with factory() as session:
        bf = BilanFile(
            file_hash=file_hash,
            filename=file_path.name,
            date_range_start=parsed.date_range[0],
            date_range_end=parsed.date_range[1],
            status="pending",
        )
        session.add(bf)
        await session.commit()
        await session.refresh(bf)
        file_id: UUID = bf.file_id
    log.info("bilan_file_row_inserted", file_id=str(file_id))

    # backfill file_id into the rows we'll COPY
    rows_with_fk = [
        (t, file_id, mid, val, unit, raw, synth, flags)
        for (t, _, mid, val, unit, raw, synth, flags) in mapped_rows
    ]

    # 5. COPY in a sync psycopg connection
    inserted = await asyncio.to_thread(
        _copy_rows_sync, settings.postgres_dsn, file_id, rows_with_fk
    )
    log.info("ingest_copy_done", inserted=inserted)

    # 6. validation pass
    async with factory() as session:
        entries = mapping_module.load_mappings()
        range_violations = await apply_range_checks(session, file_id=file_id, entries=entries)
        inversions = await apply_monotonic_checks(session, file_id=file_id, entries=entries)
        whole_column_zeros = await apply_whole_column_zero_check(
            session, file_id=file_id, entries=entries
        )
    log.info(
        "ingest_validated",
        range_violations=range_violations,
        monotonic_inversions=inversions,
        whole_column_zeros=whole_column_zeros,
    )

    # 7. final status update
    has_issues = (
        bool(unmapped)
        or bool(range_violations)
        or bool(inversions)
        or duplicates_in_file > 0
        or whole_column_zeros > 0
    )
    status: Literal["success", "partial_success"] = (
        "partial_success" if has_issues else "success"
    )
    warnings_payload: dict[str, object] | None = None
    if has_issues:
        warnings_payload = {}
        if range_violations:
            warnings_payload["range_violations_by_metric"] = range_violations
        if inversions:
            warnings_payload["monotonic_inversions_by_metric"] = inversions
        if duplicates_in_file:
            warnings_payload["intra_file_duplicates_dropped"] = duplicates_in_file
        if whole_column_zeros:
            warnings_payload["whole_column_zero_rows"] = whole_column_zeros

    unmapped_list = [{"raw_label": l, "category": c} for (l, c) in unmapped]

    async with factory() as session:
        await session.execute(
            update(BilanFile)
            .where(BilanFile.file_id == file_id)
            .values(
                rows_inserted=inserted,
                rows_dropped=rows_dropped + duplicates_in_file,
                unmapped_params=unmapped_list or None,
                status=status,
                warnings=warnings_payload,
            )
        )
        await session.commit()

    return IngestionResult(
        status=status,
        file_hash=file_hash,
        file_id=file_id,
        rows_parsed=len(parsed.readings),
        rows_mapped=len(mapped_rows),
        rows_inserted=inserted,
        rows_dropped_unmapped=rows_dropped,
        rows_dropped_duplicate_in_file=duplicates_in_file,
        date_range=parsed.date_range,
        unmapped_params=unmapped_list,
        range_violations_by_metric=range_violations,
        monotonic_inversions_by_metric=inversions,
        whole_column_zero_rows=whole_column_zeros,
    )


# ---------------------------------------------------------------------------
# CLI: python -m retech_part2.ingestion.bilan.loader <file>
#
# Performs:
#   - one ingest, prints rows-parsed vs rows-inserted with explicit drop accounting
#   - the worst monotonic inversions for any flagged metric (so they can be
#     sanity-checked against the column-order observation from M4)
#   - a second ingest, asserts duplicate + zero inserts, asserts DB row count
#     unchanged (idempotency baked in)
#   - a sample query against gas.flow_rate
# ---------------------------------------------------------------------------

async def _row_count_for_file(file_id: UUID) -> int:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM timeseries.bilan_readings WHERE file_id = :id"),
            {"id": file_id},
        )
        return int(result.scalar_one())


async def _print_inversion_diagnostics(file_id: UUID, metric_id: str, limit: int = 5) -> None:
    from retech_part2.ingestion.bilan.validator import get_worst_inversions
    factory = get_session_factory()
    async with factory() as session:
        worst = await get_worst_inversions(session, file_id=file_id, metric_id=metric_id, limit=limit)
    if not worst:
        return
    print(f"\n  worst inversions for {metric_id}:")
    print(f"    {'time':<26}{'value':>16}{'prev_time':>26}{'prev_value':>16}{'dip':>14}")
    for inv in worst:
        print(
            f"    {str(inv.time):<26}{inv.value:>16.2f}{str(inv.prev_time):>26}"
            f"{inv.prev_value:>16.2f}{inv.dip:>14.2f}"
        )


async def _print_sample_gas_flow_rate(file_id: UUID) -> None:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text(
                """
                SELECT time, value
                  FROM timeseries.bilan_readings
                 WHERE file_id = :id AND metric_id = 'gas.flow_rate'
                 ORDER BY time
                 LIMIT 10
                """
            ),
            {"id": file_id},
        )
        rows = result.all()
    print(f"\nSample query: gas.flow_rate (first 10 by time):")
    for row in rows:
        print(f"  {row.time}  {row.value:>10.2f} Nm3/h")


def _print_summary(label: str, result: IngestionResult) -> None:
    print(f"\n=== {label} ===")
    print(f"  hash                  : {result.file_hash[:16]}…")
    print(f"  status                : {result.status}")
    print(f"  duplicate             : {result.duplicate}")
    print(f"  rows_parsed           : {result.rows_parsed:,}")
    print(f"  rows_mapped           : {result.rows_mapped:,}")
    print(f"  rows_inserted         : {result.rows_inserted:,}")
    print(f"  dropped (unmapped)    : {result.rows_dropped_unmapped:,}")
    print(f"  dropped (duplicate in file): {result.rows_dropped_duplicate_in_file:,}")
    if result.unmapped_params:
        print(f"  unmapped pairs     :")
        for u in result.unmapped_params:
            print(f"    raw_label={u['raw_label']!r}  category={u['category']!r}")
    if result.range_violations_by_metric:
        print(f"  range violations   :")
        for m, n in sorted(result.range_violations_by_metric.items(), key=lambda kv: -kv[1]):
            print(f"    {m}: {n} reading(s) outside YAML range")
    if result.monotonic_inversions_by_metric:
        print(f"  monotonic inversions:")
        for m, n in sorted(result.monotonic_inversions_by_metric.items(), key=lambda kv: -kv[1]):
            print(f"    {m}: {n} backward step(s) in time order")
    if result.whole_column_zero_rows:
        print(
            f"  whole-column-zero rows : {result.whole_column_zero_rows:,}"
            f" (≥3 cumulative meters at the same time all read 0)"
        )


async def _cli(file_path: Path) -> int:
    from retech_part2.logging import configure_logging
    configure_logging()

    # ----- ingest #1 -----
    r1 = await ingest_bilan(file_path)
    _print_summary("INGEST 1", r1)

    if r1.status == "failed" or r1.file_id is None:
        print("\nFAILED before validation could run.")
        return 1

    # rows accounting check (user-requested)
    explained_drops = r1.rows_dropped_unmapped + r1.rows_dropped_duplicate_in_file
    expected_inserts = r1.rows_parsed - explained_drops
    actual_delta = r1.rows_parsed - r1.rows_inserted
    if r1.rows_inserted != expected_inserts:
        print(
            f"\n  ⚠ UNEXPLAINED ROW-COUNT GAP:"
            f" parsed={r1.rows_parsed:,}  inserted={r1.rows_inserted:,}"
            f"  expected={expected_inserts:,}  delta={actual_delta:,}"
            f"  (explained: unmapped={r1.rows_dropped_unmapped:,},"
            f" intra-file dup={r1.rows_dropped_duplicate_in_file:,})"
        )
        return 2
    else:
        print(
            f"\n  row accounting OK:"
            f" parsed({r1.rows_parsed:,}) = inserted({r1.rows_inserted:,})"
            f" + unmapped({r1.rows_dropped_unmapped:,})"
            f" + intra-file-dup({r1.rows_dropped_duplicate_in_file:,})"
        )

    # diagnostic for inversions on cumulative meters
    for metric_id in r1.monotonic_inversions_by_metric:
        await _print_inversion_diagnostics(r1.file_id, metric_id)

    # sample query
    await _print_sample_gas_flow_rate(r1.file_id)

    # ----- ingest #2 (idempotency) -----
    r2 = await ingest_bilan(file_path)
    _print_summary("INGEST 2 (idempotency)", r2)

    db_count_after = await _row_count_for_file(r1.file_id)

    print(f"\n=== IDEMPOTENCY CHECK ===")
    print(f"  ingest 2 returned duplicate flag : {r2.duplicate}")
    print(f"  ingest 2 rows_inserted           : {r2.rows_inserted}  (expected 0)")
    print(f"  DB row count after ingest 1      : {r1.rows_inserted:,}")
    print(f"  DB row count after ingest 2      : {db_count_after:,}")

    if not r2.duplicate or r2.rows_inserted != 0 or db_count_after != r1.rows_inserted:
        print("\n  ⚠ IDEMPOTENCY FAILED")
        return 3
    print("\n  idempotency OK ✓")
    return 0


def main() -> int:
    import sys
    if len(sys.argv) != 2:
        print(
            "usage: python -m retech_part2.ingestion.bilan.loader <path-to-xlsx>",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_cli(Path(sys.argv[1]).resolve()))


if __name__ == "__main__":
    raise SystemExit(main())
