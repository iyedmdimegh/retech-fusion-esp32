"""Ingestion-job listing and status."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from retech_part2.db import get_session
from retech_part2.models import IngestionJob
from retech_part2.schemas import IngestionJobOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[IngestionJobOut])
async def list_jobs(
    session: SessionDep,
    status: str | None = Query(None, description="filter by status"),
    type: str | None = Query(None, description="filter by job_type (bilan|invoice)"),
    limit: int = Query(50, ge=1, le=500),
) -> list[IngestionJob]:
    stmt = select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(IngestionJob.status == status)
    if type:
        stmt = stmt.where(IngestionJob.job_type == type)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{job_id}", response_model=IngestionJobOut)
async def get_job(job_id: UUID, session: SessionDep) -> IngestionJob:
    job = await session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(404, f"job {job_id} not found")
    return job
