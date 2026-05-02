"""Train CO₂ forecasters + anomaly detector. Persists models to disk and
metadata to ``analytics.co2_models``. Also (re)populates ``analytics.co2_hourly``
with the dataset used for training so the API can read a stable snapshot.

Determinism: numpy + Python random + per-model seeds all set to 42.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import UUID

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sqlalchemy import text
from xgboost import XGBRegressor

from retech_part2._compat import apply_windows_event_loop_policy
from retech_part2.analytics.co2.features import engineer_features, feature_columns
from retech_part2.analytics.co2.pipeline import build_co2_dataset
from retech_part2.config import get_settings
from retech_part2.db import get_session_factory, reset_db_cache_for_new_loop
from retech_part2.logging import configure_logging, get_logger

random.seed(42)
np.random.seed(42)

log = get_logger("co2.train")

TARGET_COL = "co2_total_kg"
ANOMALY_ARTIFACT = "anomaly_detector.pkl"


@dataclass
class ModelMetadata:
    target: str
    horizon_hours: int
    algorithm: str
    n_train_samples: int
    n_test_samples: int
    mae: float
    rmse: float
    mape: float | None
    feature_count: int
    artifact_path: str


# ---------------------------------------------------------------------------
# data prep
# ---------------------------------------------------------------------------


def _load_hourly_dataset() -> pd.DataFrame:
    """Build the hourly CO₂ dataset across ALL ingested BILAN files."""
    df = build_co2_dataset(granularity="1h")
    if df.empty:
        raise RuntimeError(
            "build_co2_dataset returned empty — no BILAN data ingested yet?"
        )
    return df


# ---------------------------------------------------------------------------
# forecasters
# ---------------------------------------------------------------------------


def _train_one_horizon(
    df: pd.DataFrame,
    horizon: int,
    test_ratio: float,
    models_dir: Path,
) -> tuple[XGBRegressor, ModelMetadata]:
    """Train one XGBoost forecaster for `horizon` hours ahead."""
    feats = engineer_features(df, target_col=TARGET_COL)
    feat_cols = feature_columns(TARGET_COL)
    target_name = f"{TARGET_COL}_t{horizon}"
    feats[target_name] = df[TARGET_COL].shift(-horizon)

    usable = feats.dropna(subset=feat_cols + [target_name])
    if len(usable) < 30:
        raise RuntimeError(
            f"only {len(usable)} usable rows for horizon h={horizon} — "
            "need more BILAN data before training is meaningful"
        )

    split = int(len(usable) * (1 - test_ratio))
    X_train, X_test = usable[feat_cols].iloc[:split], usable[feat_cols].iloc[split:]
    y_train, y_test = usable[target_name].iloc[:split], usable[target_name].iloc[split:]

    model = XGBRegressor(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
    )
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, pred)))
    nz = y_test.abs() > 1e-6
    mape = (
        float(np.mean(np.abs((y_test[nz] - pred[nz]) / y_test[nz]))) if nz.any() else None
    )

    artifact_path = models_dir / f"co2_total_h{horizon}.pkl"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "feature_cols": feat_cols, "rmse": rmse}, artifact_path)

    meta = ModelMetadata(
        target=TARGET_COL,
        horizon_hours=horizon,
        algorithm="xgboost",
        n_train_samples=len(X_train),
        n_test_samples=len(X_test),
        mae=mae,
        rmse=rmse,
        mape=mape,
        feature_count=len(feat_cols),
        artifact_path=str(artifact_path).replace("\\", "/"),
    )
    log.info(
        "co2_forecaster_trained",
        horizon=horizon,
        n_train=meta.n_train_samples,
        n_test=meta.n_test_samples,
        mae=round(mae, 2),
        rmse=round(rmse, 2),
    )
    return model, meta


def train_forecasters(
    df: pd.DataFrame, horizons: Iterable[int] = (1, 6, 24)
) -> list[ModelMetadata]:
    settings = get_settings()
    models_dir = Path(settings.co2_models_dir)
    out: list[ModelMetadata] = []
    for h in horizons:
        _, meta = _train_one_horizon(df, h, settings.co2_test_ratio, models_dir)
        out.append(meta)
    return out


# ---------------------------------------------------------------------------
# anomaly detector
# ---------------------------------------------------------------------------


def train_anomaly_detector(df: pd.DataFrame) -> tuple[IsolationForest, ModelMetadata, pd.Series, pd.Series]:
    """Fit IsolationForest on the SAME engineered feature matrix the
    forecaster uses — never on raw cumulative columns. Returns the model,
    metadata, and per-row (is_anomaly, anomaly_score) Series for the
    rows that had usable features.
    """
    settings = get_settings()
    models_dir = Path(settings.co2_models_dir)

    feats = engineer_features(df, target_col=TARGET_COL)
    feat_cols = feature_columns(TARGET_COL)
    usable = feats.dropna(subset=feat_cols)
    if len(usable) < 30:
        raise RuntimeError(
            f"only {len(usable)} rows have full features for the anomaly detector"
        )

    X = usable[feat_cols].to_numpy()
    model = IsolationForest(
        contamination=settings.co2_anomaly_contamination,
        random_state=42,
        n_estimators=200,
    )
    model.fit(X)

    # IsolationForest .predict returns 1 (normal) / -1 (anomaly).
    # .score_samples returns log-likelihood: higher = more normal.
    is_anomaly = pd.Series(model.predict(X) == -1, index=usable.index, name="is_anomaly")
    anomaly_score = pd.Series(
        -model.score_samples(X),  # negate so higher = more anomalous
        index=usable.index,
        name="anomaly_score",
    )

    artifact_path = models_dir / ANOMALY_ARTIFACT
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "feature_cols": feat_cols}, artifact_path)

    meta = ModelMetadata(
        target="anomaly",
        horizon_hours=0,
        algorithm="isolation_forest",
        n_train_samples=len(X),
        n_test_samples=0,
        mae=float("nan"),
        rmse=float("nan"),
        mape=None,
        feature_count=len(feat_cols),
        artifact_path=str(artifact_path).replace("\\", "/"),
    )
    log.info(
        "co2_anomaly_detector_trained",
        n_samples=meta.n_train_samples,
        flagged=int(is_anomaly.sum()),
        contamination=settings.co2_anomaly_contamination,
    )
    return model, meta, is_anomaly, anomaly_score


# ---------------------------------------------------------------------------
# DB writeback
# ---------------------------------------------------------------------------


async def _write_co2_hourly(
    df: pd.DataFrame,
    is_anomaly: pd.Series,
    anomaly_score: pd.Series,
) -> None:
    """Replace analytics.co2_hourly with the freshly-computed series
    plus per-row anomaly flags."""
    factory = get_session_factory()
    async with factory() as s:
        await s.execute(text("DELETE FROM analytics.co2_hourly"))
        if not df.empty:
            joined = df.join(is_anomaly, how="left").join(anomaly_score, how="left")
            joined["is_anomaly"] = joined["is_anomaly"].fillna(False).astype(bool)
            rows = []
            for ts, row in joined.iterrows():
                rows.append(
                    {
                        "time": ts.to_pydatetime(),
                        "gas_nm3": float(row["gas_nm3"]),
                        "elec_produced_kwh": float(row["elec_produced_kwh"]),
                        "grid_import_kwh": float(row["grid_import_kwh"]),
                        "grid_export_kwh": float(row["grid_export_kwh"]),
                        "grid_net_kwh": float(row["grid_net_kwh"]),
                        "co2_gas_kg": float(row["co2_gas_kg"]),
                        "co2_grid_kg": float(row["co2_grid_kg"]),
                        "co2_total_kg": float(row["co2_total_kg"]),
                        "is_anomaly": bool(row["is_anomaly"]),
                        "anomaly_score": (
                            float(row["anomaly_score"])
                            if pd.notna(row["anomaly_score"])
                            else None
                        ),
                    }
                )
            await s.execute(
                text(
                    """
                    INSERT INTO analytics.co2_hourly
                       ("time", gas_nm3, elec_produced_kwh, grid_import_kwh,
                        grid_export_kwh, grid_net_kwh, co2_gas_kg, co2_grid_kg,
                        co2_total_kg, is_anomaly, anomaly_score)
                    VALUES (:time, :gas_nm3, :elec_produced_kwh, :grid_import_kwh,
                            :grid_export_kwh, :grid_net_kwh, :co2_gas_kg, :co2_grid_kg,
                            :co2_total_kg, :is_anomaly, :anomaly_score)
                    """
                ),
                rows,
            )
        await s.commit()


async def _register_models(metas: list[ModelMetadata]) -> None:
    factory = get_session_factory()
    async with factory() as s:
        # Deactivate any currently-active models so the partial unique index
        # accepts the fresh row.
        for m in metas:
            await s.execute(
                text(
                    """
                    UPDATE analytics.co2_models
                       SET is_active = FALSE
                     WHERE target = :t AND horizon_hours = :h AND is_active = TRUE
                    """
                ),
                {"t": m.target, "h": m.horizon_hours},
            )
        for m in metas:
            await s.execute(
                text(
                    """
                    INSERT INTO analytics.co2_models
                          (target, horizon_hours, algorithm,
                           n_train_samples, n_test_samples,
                           mae, rmse, mape, feature_count, artifact_path, is_active)
                    VALUES (:target, :horizon, :algo,
                            :ntr, :nte,
                            :mae, :rmse, :mape, :fc, :ap, TRUE)
                    """
                ),
                {
                    "target": m.target,
                    "horizon": m.horizon_hours,
                    "algo": m.algorithm,
                    "ntr": m.n_train_samples,
                    "nte": m.n_test_samples,
                    "mae": None if np.isnan(m.mae) else m.mae,
                    "rmse": None if np.isnan(m.rmse) else m.rmse,
                    "mape": m.mape,
                    "fc": m.feature_count,
                    "ap": m.artifact_path,
                },
            )
        await s.commit()


async def _write_initial_forecasts(df: pd.DataFrame, horizons: Iterable[int]) -> None:
    """Roll the h=1 forecaster forward to produce a continuous next-N-hours
    series anchored on the last data row. ``forecast_made_at`` is set to the
    ANCHOR timestamp (not wall-clock) so the field name reflects what it
    actually represents — when the data ends, where the forecast starts.
    """
    from retech_part2.analytics.co2.predict import predict_rolling_multistep

    n_steps = max(24, max(horizons))
    try:
        anchor_dt, forecasts = predict_rolling_multistep(
            df, n_steps=n_steps, target_col=TARGET_COL,
        )
    except RuntimeError as e:
        log.warning("co2_no_forecast_anchor", reason=str(e))
        return

    rows = [
        {
            "fmade": anchor_dt,
            "ttime": f.target_time,
            "h": f.horizon_hours,
            "kg": f.predicted_co2_kg,
        }
        for f in forecasts
    ]

    factory = get_session_factory()
    async with factory() as s:
        await s.execute(text("DELETE FROM analytics.co2_forecasts"))
        if rows:
            await s.execute(
                text(
                    """
                    INSERT INTO analytics.co2_forecasts
                           (forecast_made_at, target_time, horizon_hours, predicted_co2_kg)
                    VALUES (:fmade, :ttime, :h, :kg)
                    """
                ),
                rows,
            )
        await s.commit()
    log.info(
        "co2_forecasts_written",
        n=len(rows),
        anchor=anchor_dt.isoformat(),
        last_target=forecasts[-1].target_time.isoformat() if forecasts else None,
    )


# ---------------------------------------------------------------------------
# top-level orchestration
# ---------------------------------------------------------------------------


async def run_full_training(horizons: Iterable[int] = (1, 6, 24)) -> dict:
    log.info("co2_training_start", horizons=list(horizons))
    df = _load_hourly_dataset()
    log.info("co2_dataset_built", rows=len(df), date_range=[
        df.index.min().isoformat(), df.index.max().isoformat()
    ])

    forecaster_metas = train_forecasters(df, horizons=horizons)
    _, anomaly_meta, is_anomaly, anomaly_score = train_anomaly_detector(df)

    await _write_co2_hourly(df, is_anomaly, anomaly_score)
    await _register_models([*forecaster_metas, anomaly_meta])
    await _write_initial_forecasts(df, horizons)

    log.info("co2_training_done", n_models=len(forecaster_metas) + 1)
    return {
        "rows_in_dataset": len(df),
        "forecasters": [m.__dict__ for m in forecaster_metas],
        "anomaly": anomaly_meta.__dict__,
        "anomalies_flagged": int(is_anomaly.sum()),
    }


def main() -> int:
    apply_windows_event_loop_policy()
    configure_logging()
    horizons = get_settings().co2_horizons_list
    if "--horizons" in sys.argv:
        idx = sys.argv.index("--horizons")
        horizons = [int(x) for x in sys.argv[idx + 1].split(",")]
    reset_db_cache_for_new_loop()
    result = asyncio.run(run_full_training(horizons=horizons))
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
