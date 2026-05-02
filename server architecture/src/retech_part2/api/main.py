from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from retech_part2 import __version__
from retech_part2._compat import apply_windows_event_loop_policy

# Apply the Selector policy before uvicorn creates the loop.
apply_windows_event_loop_policy()
from retech_part2.api.routes import (
    bilan,
    co2,
    documents,
    export,
    health,
    ingest,
    jobs,
    readings,
    search,
)
from retech_part2.logging import configure_logging

# Vite dev server defaults; both 127.0.0.1 and localhost forms because the
# browser uses whichever the user typed.
_FRONTEND_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Re-Tech Fusion — Phase 2",
        version=__version__,
        description="Data platform: BILAN ingestion, invoice OCR, MQTT (stubbed), query/export.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_FRONTEND_DEV_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, tags=["health"])
    app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(readings.router, prefix="/api", tags=["readings"])
    app.include_router(bilan.router, prefix="/api/bilan", tags=["bilan"])
    app.include_router(co2.router, prefix="/api/co2", tags=["co2"])
    app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    app.include_router(export.router, prefix="/api/export", tags=["export"])

    return app


app = create_app()
