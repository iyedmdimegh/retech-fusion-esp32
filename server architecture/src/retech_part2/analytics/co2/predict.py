"""Runtime inference: load the active forecasters + anomaly detector and
produce predictions for a given anchor time."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import joblib
import pandas as pd

from retech_part2.analytics.co2.features import engineer_features, feature_columns
from retech_part2.config import get_settings


@dataclass
class HorizonForecast:
    horizon_hours: int
    target_time: dt.datetime
    predicted_co2_kg: float
    rmse_band: float


@dataclass
class ForecastBundle:
    forecast_made_at: dt.datetime
    anchor_time: dt.datetime
    forecasts: list[HorizonForecast]


def predict_horizons(
    df: pd.DataFrame,
    *,
    horizons: Iterable[int] = (1, 6, 24),
    target_col: str = "co2_total_kg",
) -> ForecastBundle:
    """Engineer features as of the LAST row of df and predict each horizon.

    Each prediction comes with the model's training-time RMSE so the UI
    can render a ±1σ confidence band.
    """
    settings = get_settings()
    models_dir = Path(settings.co2_models_dir)

    feats = engineer_features(df, target_col=target_col)
    feat_cols = feature_columns(target_col)
    usable = feats.dropna(subset=feat_cols)
    if usable.empty:
        raise RuntimeError("no row has full features — need more history")

    last = usable.iloc[[-1]]
    anchor = last.index[-1].to_pydatetime()
    made = dt.datetime.now(dt.timezone.utc)

    out: list[HorizonForecast] = []
    for h in horizons:
        artifact = models_dir / f"co2_total_h{h}.pkl"
        if not artifact.exists():
            continue
        bundle = joblib.load(artifact)
        model = bundle["model"]
        pred = float(model.predict(last[feat_cols])[0])
        rmse = float(bundle.get("rmse", 0.0))
        out.append(
            HorizonForecast(
                horizon_hours=h,
                target_time=anchor + dt.timedelta(hours=h),
                predicted_co2_kg=pred,
                rmse_band=rmse,
            )
        )

    return ForecastBundle(forecast_made_at=made, anchor_time=anchor, forecasts=out)


def predict_rolling_multistep(
    df: pd.DataFrame,
    *,
    n_steps: int = 24,
    target_col: str = "co2_total_kg",
) -> tuple[dt.datetime, list[HorizonForecast]]:
    """Roll the h=1 model forward n_steps times, feeding each prediction
    back into the feature vector. Produces one forecast per hour from
    anchor+1h to anchor+n_steps_h — a continuous near-future curve that
    starts exactly where the last actual data point ends.

    Error compounds across steps; the band widens as ``sqrt(step) * rmse``
    (heuristic but honest — recursive forecasts get noisier).

    Returns ``(anchor_datetime, list_of_per_hour_forecasts)``.
    """
    settings = get_settings()
    models_dir = Path(settings.co2_models_dir)
    artifact = models_dir / "co2_total_h1.pkl"
    if not artifact.exists():
        raise RuntimeError(f"h=1 forecaster artifact not found at {artifact}")
    bundle = joblib.load(artifact)
    model = bundle["model"]
    feat_cols = bundle["feature_cols"]
    rmse = float(bundle.get("rmse", 0.0))

    if df.empty:
        raise RuntimeError("empty input dataframe")

    work = df[[target_col]].copy()
    if work.index.tz is None:
        work.index = work.index.tz_localize("UTC")

    # Anchor = last row that has a fully-populated feature vector. With
    # lag_168h this is whichever row has at least a week of preceding history.
    feats0 = engineer_features(work, target_col=target_col)
    usable_anchor = feats0.dropna(subset=feat_cols)
    if usable_anchor.empty:
        raise RuntimeError("no row in input has a complete feature vector")
    anchor_dt = usable_anchor.index[-1].to_pydatetime()

    out: list[HorizonForecast] = []
    for step in range(1, n_steps + 1):
        feats = engineer_features(work, target_col=target_col)
        usable = feats.dropna(subset=feat_cols)
        last = usable.iloc[[-1]]
        pred = float(model.predict(last[feat_cols])[0])
        target_time = last.index[-1].to_pydatetime() + dt.timedelta(hours=1)
        out.append(
            HorizonForecast(
                horizon_hours=step,
                target_time=target_time,
                predicted_co2_kg=pred,
                rmse_band=rmse * (step ** 0.5),
            )
        )
        new_idx = pd.DatetimeIndex([target_time], tz=work.index.tz)
        new_row = pd.DataFrame({target_col: [pred]}, index=new_idx)
        work = pd.concat([work, new_row])

    return anchor_dt, out
