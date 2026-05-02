"""readings dedup constraint

Revision ID: 002_readings_dedup_constraint
Revises: 001_initial_schema
Create Date: 2026-05-02

The ESP32 firmware publishes at QoS 0 with an app-level retry loop (RAM
ring buffer flushes on reconnect). That means we routinely receive the same
(device_id, time, sensor, type) tuple more than once. A UNIQUE constraint
on those four columns lets the subscriber INSERT ... ON CONFLICT DO NOTHING
and silently collapse the duplicates.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "002_readings_dedup_constraint"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE timeseries.readings
        ADD CONSTRAINT readings_dedup_key
        UNIQUE (device_id, "time", sensor, type);
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE timeseries.readings DROP CONSTRAINT IF EXISTS readings_dedup_key;"
    )
