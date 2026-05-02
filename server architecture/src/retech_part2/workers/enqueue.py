"""Shared dedup-and-enqueue helper used by both the upload endpoint and the
drop-folder watcher.

Behaviour:
  * Compute (or accept pre-computed) SHA-256 of the file.
  * Look up `meta.ingestion_jobs` for any job with this hash whose status is
    not 'failed'. If one exists, return it — re-uploading is a no-op.
  * Otherwise insert a fresh `pending` job row and enqueue the matching RQ
    task (`task_ingest_bilan` for .xlsx, `task_ingest_invoice` for .pdf).

The function is async for the DB writes; the RQ enqueue itself is sync (RQ's
client is sync), which is fine to call from inside an async context.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from redis import Redis
from rq import Queue
from sqlalchemy import select

from retech_part2.config import get_settings
from retech_part2.db import get_session_factory
from retech_part2.logging import get_logger
from retech_part2.models import IngestionJob
from retech_part2.utils.hashing import sha256_file

log = get_logger("enqueue")

EXT_TO_JOB_TYPE: dict[str, str] = {
    ".xlsx": "bilan",
    # Invoice inputs: PDFs and loose images. Loose images are treated as
    # single-page documents; the OCR pipeline doesn't branch on type.
    ".pdf": "invoice",
    ".jpg": "invoice",
    ".jpeg": "invoice",
    ".png": "invoice",
    ".tiff": "invoice",
    ".tif": "invoice",
    ".webp": "invoice",
}
TASK_BY_TYPE: dict[str, str] = {
    "bilan": "retech_part2.workers.tasks.task_ingest_bilan",
    "invoice": "retech_part2.workers.tasks.task_ingest_invoice",
}


@dataclass
class EnqueueResult:
    job_id: UUID
    status: str
    deduped: bool
    job_type: str


class UnsupportedExtension(ValueError):
    pass


async def enqueue_file(
    file_path: Path,
    *,
    file_hash: str | None = None,
    queue_name: str = "default",
) -> EnqueueResult:
    settings = get_settings()
    factory = get_session_factory()

    ext = file_path.suffix.lower()
    job_type = EXT_TO_JOB_TYPE.get(ext)
    if job_type is None:
        raise UnsupportedExtension(
            f"unsupported extension {ext!r}; expected one of {sorted(EXT_TO_JOB_TYPE)}"
        )

    if file_hash is None:
        file_hash = sha256_file(file_path)

    async with factory() as session:
        existing = (
            await session.execute(
                select(IngestionJob)
                .where(IngestionJob.file_hash == file_hash)
                .where(IngestionJob.status != "failed")
                .order_by(IngestionJob.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            log.info(
                "enqueue_dedup_hit",
                job_id=str(existing.job_id),
                status=existing.status,
                file_hash=file_hash[:16],
            )
            return EnqueueResult(
                job_id=existing.job_id,
                status=existing.status,
                deduped=True,
                job_type=existing.job_type,
            )

        job = IngestionJob(
            job_type=job_type,
            source_path=str(file_path),
            file_hash=file_hash,
            status="pending",
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        new_job_id = job.job_id

    # RQ enqueue (sync client; safe to call from async context).
    redis = Redis.from_url(settings.redis_url)
    queue = Queue(queue_name, connection=redis)
    task_name = TASK_BY_TYPE[job_type]
    queue.enqueue(task_name, str(file_path), str(new_job_id))

    log.info(
        "enqueue_new_job",
        job_id=str(new_job_id),
        job_type=job_type,
        file=str(file_path),
        file_hash=file_hash[:16],
    )
    return EnqueueResult(
        job_id=new_job_id, status="pending", deduped=False, job_type=job_type
    )
