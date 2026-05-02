"""analytics schema for M12 CO₂ pipeline

Revision ID: 005_analytics_schema
Revises: 002_readings_dedup_constraint
Create Date: 2026-05-02

Three tables in a new ``analytics`` schema:

* ``analytics.co2_hourly``     — hourly time-series of CO₂ + breakdown.
                                 Hypertable on ``time``. Repopulated by each
                                 training run.
* ``analytics.co2_forecasts``  — most recent forecast outputs. Hypertable on
                                 ``target_time``.
* ``analytics.co2_models``     — model registry. One row per (target, horizon)
                                 per training run. The "active" model per
                                 (target, horizon) is enforced by a partial
                                 unique index on (target, horizon_hours)
                                 WHERE is_active = TRUE — this allows
                                 unbounded historical rows with is_active=false
                                 (the spec's deferred UNIQUE on the boolean
                                 itself would have capped historical rows at one).

Migration numbering note: the prompt called for ``005_analytics_schema.py``
but migrations 003/004 (planned for the M9-stub document subtype tables) were
never written — checkpoint pivot moved that scope. Keeping the requested
filename ``005_analytics_schema`` so the spec maps cleanly; the down_revision
chains from ``002_readings_dedup_constraint`` (the actual current head).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "005_analytics_schema"
down_revision: Union[str, None] = "002_readings_dedup_constraint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics;")

    # ---- co2_hourly ----
    op.execute(
        """
        CREATE TABLE analytics.co2_hourly (
            "time"            TIMESTAMPTZ NOT NULL,
            gas_nm3           DOUBLE PRECISION,
            elec_produced_kwh DOUBLE PRECISION,
            grid_import_kwh   DOUBLE PRECISION,
            grid_export_kwh   DOUBLE PRECISION,
            grid_net_kwh      DOUBLE PRECISION,
            co2_gas_kg        DOUBLE PRECISION,
            co2_grid_kg       DOUBLE PRECISION,
            co2_total_kg      DOUBLE PRECISION,
            is_anomaly        BOOLEAN DEFAULT FALSE,
            anomaly_score     DOUBLE PRECISION,
            PRIMARY KEY ("time")
        );
        """
    )
    op.execute("SELECT create_hypertable('analytics.co2_hourly', 'time');")
    op.execute("CREATE INDEX ix_co2_hourly_time_desc ON analytics.co2_hourly (\"time\" DESC);")

    # ---- co2_forecasts ----
    op.execute(
        """
        CREATE TABLE analytics.co2_forecasts (
            forecast_made_at  TIMESTAMPTZ NOT NULL,
            target_time       TIMESTAMPTZ NOT NULL,
            horizon_hours     INT NOT NULL,
            predicted_co2_kg  DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (forecast_made_at, target_time, horizon_hours)
        );
        """
    )
    op.execute("SELECT create_hypertable('analytics.co2_forecasts', 'target_time');")
    op.execute(
        "CREATE INDEX ix_co2_forecasts_made_at ON analytics.co2_forecasts (forecast_made_at DESC);"
    )

    # ---- co2_models registry ----
    op.execute(
        """
        CREATE TABLE analytics.co2_models (
            model_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            trained_at      TIMESTAMPTZ DEFAULT NOW(),
            target          TEXT NOT NULL,
            horizon_hours   INT NOT NULL,
            algorithm       TEXT NOT NULL,
            n_train_samples INT,
            n_test_samples  INT,
            mae             DOUBLE PRECISION,
            rmse            DOUBLE PRECISION,
            mape            DOUBLE PRECISION,
            feature_count   INT,
            artifact_path   TEXT NOT NULL,
            is_active       BOOLEAN DEFAULT TRUE
        );
        """
    )
    op.execute(
        "CREATE INDEX ix_co2_models_target_horizon_trained "
        "ON analytics.co2_models (target, horizon_hours, trained_at DESC);"
    )
    # Partial unique index: exactly one active per (target, horizon_hours).
    # Lets us keep arbitrary inactive history.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_co2_models_one_active_per_target_horizon
        ON analytics.co2_models (target, horizon_hours)
        WHERE is_active = TRUE;
        """
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE;")
