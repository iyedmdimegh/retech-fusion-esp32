"""BILAN file metadata + time-series queries."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from retech_part2.db import get_session
from retech_part2.models import BilanFile
from retech_part2.schemas import BilanFileOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/files", response_model=list[BilanFileOut])
async def list_files(
    session: SessionDep,
    limit: int = Query(50, ge=1, le=500),
) -> list[BilanFile]:
    stmt = select(BilanFile).order_by(BilanFile.parsed_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())
