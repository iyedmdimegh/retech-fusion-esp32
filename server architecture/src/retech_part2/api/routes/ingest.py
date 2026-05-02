"""File-upload endpoint. Accepts .xlsx and .pdf, dedups by SHA-256, enqueues
to the appropriate RQ queue, returns the job_id.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from retech_part2.config import get_settings
from retech_part2.utils.files import ensure_dir
from retech_part2.utils.hashing import sha256_bytes
from retech_part2.workers.enqueue import (
    EXT_TO_JOB_TYPE,
    UnsupportedExtension,
    enqueue_file,
)

router = APIRouter()


class UploadResponse(BaseModel):
    job_id: str
    status: str
    job_type: str
    deduped: bool
    file_hash: str
    saved_path: str


@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    settings = get_settings()

    if not file.filename:
        raise HTTPException(400, "filename required")
    ext = Path(file.filename).suffix.lower()
    if ext not in EXT_TO_JOB_TYPE:
        raise HTTPException(415, f"unsupported extension {ext}; expected .xlsx or .pdf")

    target_dir = settings.inbox_xlsx_path if ext == ".xlsx" else settings.inbox_pdf_path
    ensure_dir(target_dir)
    target_path = Path(target_dir) / file.filename

    # Slurp body, hash, write atomically (write→fsync→close→rename is overkill here;
    # a single write is fine because the watcher is filtered to .xlsx/.pdf and will
    # also wait for stable size before acting).
    body = await file.read()
    if not body:
        raise HTTPException(400, "empty upload")
    file_hash = sha256_bytes(body)
    target_path.write_bytes(body)

    try:
        result = await enqueue_file(target_path, file_hash=file_hash)
    except UnsupportedExtension as e:
        raise HTTPException(415, str(e))

    return UploadResponse(
        job_id=str(result.job_id),
        status=result.status,
        job_type=result.job_type,
        deduped=result.deduped,
        file_hash=file_hash,
        saved_path=str(target_path),
    )
