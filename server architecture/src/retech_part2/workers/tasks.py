"""RQ task functions and a CLI for manual ingestion runs.

Tasks are sync (RQ runs sync) but call async loaders via ``asyncio.run``.
Each task threads a ``job_id`` through and writes lifecycle updates
(`pending → running → success/partial_success/failed`) to ``meta.ingestion_jobs``.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sys
import traceback
from pathlib import Path
from uuid import UUID

from sqlalchemy import update

from retech_part2._compat import apply_windows_event_loop_policy
from retech_part2.db import get_session_factory, reset_db_cache_for_new_loop
from retech_part2.ingestion.bilan.loader import IngestionResult, ingest_bilan
from retech_part2.ingestion.pdf.pipeline import (
    OcrIngestionResult,
    ingest_invoice,
)
from retech_part2.logging import configure_logging, get_logger
from retech_part2.models import IngestionJob

# Apply at module import so RQ workers get the right policy when they
# import the task module.
apply_windows_event_loop_policy()

log = get_logger("worker.tasks")


# ---------------------------------------------------------------------------
# job-record bookkeeping
# ---------------------------------------------------------------------------

async def _mark_job_running(job_id: UUID) -> None:
    factory = get_session_factory()
    async with factory() as s:
        await s.execute(
            update(IngestionJob)
            .where(IngestionJob.job_id == job_id)
            .values(status="running", started_at=dt.datetime.now(dt.timezone.utc), progress=0)
        )
        await s.commit()


async def _mark_job_done(job_id: UUID, result: IngestionResult) -> None:
    factory = get_session_factory()
    warnings_payload: dict[str, object] = {
        "rows_parsed": result.rows_parsed,
        "rows_inserted": result.rows_inserted,
        "rows_dropped_unmapped": result.rows_dropped_unmapped,
        "rows_dropped_duplicate_in_file": result.rows_dropped_duplicate_in_file,
        "duplicate": result.duplicate,
    }
    if result.unmapped_params:
        warnings_payload["unmapped_params"] = result.unmapped_params
    if result.range_violations_by_metric:
        warnings_payload["range_violations_by_metric"] = result.range_violations_by_metric
    if result.monotonic_inversions_by_metric:
        warnings_payload["monotonic_inversions_by_metric"] = result.monotonic_inversions_by_metric
    if result.whole_column_zero_rows:
        warnings_payload["whole_column_zero_rows"] = result.whole_column_zero_rows

    # Map loader status → job status. 'duplicate' means a re-ingest of an already
    # successful file — record it as 'success' from the job's perspective with
    # a warning so the API caller knows.
    job_status = "success" if result.status == "duplicate" else result.status
    if result.status == "duplicate":
        warnings_payload["note"] = "duplicate_file"

    async with factory() as s:
        await s.execute(
            update(IngestionJob)
            .where(IngestionJob.job_id == job_id)
            .values(
                status=job_status,
                progress=100,
                finished_at=dt.datetime.now(dt.timezone.utc),
                warnings=warnings_payload,
            )
        )
        await s.commit()


async def _mark_job_failed(job_id: UUID, error: str) -> None:
    factory = get_session_factory()
    async with factory() as s:
        await s.execute(
            update(IngestionJob)
            .where(IngestionJob.job_id == job_id)
            .values(
                status="failed",
                progress=0,
                finished_at=dt.datetime.now(dt.timezone.utc),
                error_message=error[:4000],  # cap to avoid blowing the column
            )
        )
        await s.commit()


# ---------------------------------------------------------------------------
# bilan
# ---------------------------------------------------------------------------

async def _run_ingest_bilan(file_path: str, job_id: UUID) -> IngestionResult:
    await _mark_job_running(job_id)
    try:
        result = await ingest_bilan(Path(file_path))
    except Exception as e:
        log.exception("task_ingest_bilan_failed", job_id=str(job_id), error=str(e))
        await _mark_job_failed(job_id, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise
    await _mark_job_done(job_id, result)
    return result


def task_ingest_bilan(file_path: str, job_id: str) -> dict:
    log.info("task_ingest_bilan_start", file=file_path, job_id=job_id)
    reset_db_cache_for_new_loop()
    result = asyncio.run(_run_ingest_bilan(file_path, UUID(job_id)))
    log.info(
        "task_ingest_bilan_done",
        job_id=job_id,
        status=result.status,
        rows_inserted=result.rows_inserted,
    )
    return {
        "status": result.status,
        "file_id": str(result.file_id) if result.file_id else None,
        "rows_inserted": result.rows_inserted,
        "rows_dropped_unmapped": result.rows_dropped_unmapped,
        "rows_dropped_duplicate_in_file": result.rows_dropped_duplicate_in_file,
        "duplicate": result.duplicate,
    }


# ---------------------------------------------------------------------------
# invoice — M8 runs OCR, leaves extraction_status='pending' for M9
# ---------------------------------------------------------------------------

async def _run_ingest_invoice(file_path: str, job_id: UUID) -> OcrIngestionResult:
    await _mark_job_running(job_id)
    factory = get_session_factory()
    try:
        result = await ingest_invoice(Path(file_path))
    except Exception as e:
        log.exception("task_ingest_invoice_failed", job_id=str(job_id), error=str(e))
        await _mark_job_failed(job_id, f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise

    # Job-record bookkeeping. OCR-done is success at this milestone; M9 will
    # update document.extraction_status to done / needs_review / failed.
    warnings_payload: dict[str, object] = {
        "doc_id": str(result.doc_id),
        "page_count": result.page_count,
        "input_kind": result.input_kind,
        "duplicate": result.duplicate,
        "page_confidences": [round(p.confidence, 3) for p in result.pages],
        "page_languages": [p.language for p in result.pages],
        "note": "OCR complete; structured extraction pending (M9)",
    }
    async with factory() as s:
        await s.execute(
            update(IngestionJob)
            .where(IngestionJob.job_id == job_id)
            .values(
                status="success",
                progress=100,
                finished_at=dt.datetime.now(dt.timezone.utc),
                warnings=warnings_payload,
            )
        )
        await s.commit()
    return result


def task_ingest_invoice(file_path: str, job_id: str) -> dict:
    log.info("task_ingest_invoice_start", file=file_path, job_id=job_id)
    reset_db_cache_for_new_loop()
    result = asyncio.run(_run_ingest_invoice(file_path, UUID(job_id)))
    log.info(
        "task_ingest_invoice_done",
        job_id=job_id,
        doc_id=str(result.doc_id),
        page_count=result.page_count,
    )
    return {
        "doc_id": str(result.doc_id),
        "page_count": result.page_count,
        "input_kind": result.input_kind,
        "duplicate": result.duplicate,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    """``python -m retech_part2.workers.tasks ingest_bilan_path <file>``.

    Bypasses the queue: creates a job row, runs the task synchronously,
    prints the resulting dict.
    """
    args = sys.argv[1:]
    if len(args) != 2 or args[0] != "ingest_bilan_path":
        print(
            "usage: python -m retech_part2.workers.tasks ingest_bilan_path <file>",
            file=sys.stderr,
        )
        return 2
    configure_logging()

    # Manually create a job row so the lifecycle bookkeeping has something to update.
    file_path = args[1]
    file_hash = None
    from retech_part2.utils.hashing import sha256_file
    file_hash = sha256_file(Path(file_path))

    async def _create_job() -> str:
        factory = get_session_factory()
        async with factory() as s:
            job = IngestionJob(
                job_type="bilan",
                source_path=file_path,
                file_hash=file_hash,
                status="pending",
            )
            s.add(job)
            await s.commit()
            await s.refresh(job)
            return str(job.job_id)

    job_id = asyncio.run(_create_job())
    print(task_ingest_bilan(file_path, job_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
