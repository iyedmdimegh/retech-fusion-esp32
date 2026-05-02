"""Feature engineering for the CO₂ forecasters.

Lags, rolling statistics, calendar features. **Trailing windows only** —
no value at time t may depend on data from t+1 or later. This is the
guarantee `tests/test_co2_pipeline.py::test_features_do_not_leak_future_values`
exists to enforce.
"""
from __future__ import annotations

import pandas as pd

LAG_HOURS: tuple[int, ...] = (1, 3, 6, 12, 24, 48, 168)
ROLLING_WINDOWS: tuple[int, ...] = (3, 6, 12, 24)


def engineer_features(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    """Build a feature matrix for hourly `df` targeting `target_col`.

    Output columns: every column of the input (untouched), plus per-target
    lags, rolling stats (mean/std/min/max), and calendar features. Caller
    is expected to drop NaN rows before training (the longest-lag rows
    will have NaN feature values).
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("engineer_features expects a DatetimeIndex")

    out = df.copy()
    s = df[target_col]

    for lag in LAG_HOURS:
        out[f"{target_col}_lag_{lag}h"] = s.shift(lag)

    for w in ROLLING_WINDOWS:
        # pandas rolling default = trailing window: row[t] uses [t-w+1, ..., t].
        # Explicit min_periods=w so the window is always exactly w wide;
        # rows where it isn't yet remain NaN (filtered before training).
        roll = s.rolling(window=w, min_periods=w)
        out[f"{target_col}_rmean_{w}h"] = roll.mean()
        out[f"{target_col}_rstd_{w}h"] = roll.std()
        out[f"{target_col}_rmin_{w}h"] = roll.min()
        out[f"{target_col}_rmax_{w}h"] = roll.max()

    out["hour"] = df.index.hour
    out["dow"] = df.index.dayofweek
    out["month"] = df.index.month
    out["day"] = df.index.day
    out["is_weekend"] = (df.index.dayofweek >= 5).astype(int)
    out["is_business_hours"] = (
        (df.index.hour >= 8) & (df.index.hour <= 18) & (df.index.dayofweek < 5)
    ).astype(int)

    return out


def feature_columns(target_col: str) -> list[str]:
    """The list of generated feature names (used by callers to slice
    a feature matrix away from the raw columns)."""
    cols = [f"{target_col}_lag_{h}h" for h in LAG_HOURS]
    for w in ROLLING_WINDOWS:
        cols.extend([
            f"{target_col}_rmean_{w}h",
            f"{target_col}_rstd_{w}h",
            f"{target_col}_rmin_{w}h",
            f"{target_col}_rmax_{w}h",
        ])
    cols.extend(["hour", "dow", "month", "day", "is_weekend", "is_business_hours"])
    return cols
