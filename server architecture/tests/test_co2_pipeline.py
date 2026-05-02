"""M12 CO₂ pipeline tests.

Five tests, written before the implementation lands (TDD-ish):

  1. cumulative deltas test — synthetic gas meter with NaN cells, a 2-hour
     timestamp gap, a backward inversion, and a flat no-consumption period
  2. net-grid-sign test — synthetic import/export streams where export beats
     import in some hours; assert grid_net and co2_grid go negative
  3. no-leakage test — synthetic series with a "poison" value at row[t+1];
     assert no rolling/lag feature at row[t] picks it up
  4. real-data test — runs build_co2_dataset against the actually-ingested
     April 2025 BILAN data; bounds the row count, the positive share, the
     export-hour count, and the total CO₂
  5. forecast roundtrip — trains forecasters on the real data and asserts
     the h=1 MAE beats a "predict the mean" baseline (i.e., MAE < std)

Each test guards on the modules / data it depends on. As later milestone
steps land (pipeline.py → features.py → train.py → BILAN ingest), the
guards relax automatically — no manual @skipif maintenance.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# module-level guards (auto-skip until prerequisites land)
# ---------------------------------------------------------------------------

try:
    from retech_part2.analytics.co2.pipeline import (
        build_co2_dataset,
        build_co2_dataset_from_long,
    )
    HAS_PIPELINE = True
except ImportError:
    HAS_PIPELINE = False

try:
    from retech_part2.analytics.co2.features import engineer_features
    HAS_FEATURES = True
except ImportError:
    HAS_FEATURES = False

try:
    from retech_part2.analytics.co2.train import train_forecasters
    HAS_TRAIN = True
except ImportError:
    HAS_TRAIN = False


def _has_bilan_data() -> bool:
    """Return True iff the DB has enough April 2025 gas data for the real-data tests."""
    try:
        import psycopg
        from retech_part2.config import get_settings
        with psycopg.connect(get_settings().postgres_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM timeseries.bilan_readings "
                    "WHERE metric_id = 'gas.volume_cumulative'"
                )
                row = cur.fetchone()
                return bool(row and row[0] >= 1000)
    except Exception:
        return False


HAS_BILAN_DATA = _has_bilan_data()


pipeline_required = pytest.mark.skipif(
    not HAS_PIPELINE,
    reason="pipeline.py not yet implemented (M12 step 3)",
)
features_required = pytest.mark.skipif(
    not HAS_FEATURES,
    reason="features.py not yet implemented (M12 step 4)",
)
real_data_required = pytest.mark.skipif(
    not (HAS_PIPELINE and HAS_BILAN_DATA),
    reason="needs pipeline.py (M12 step 3) and ingested BILAN data",
)
forecast_required = pytest.mark.skipif(
    not (HAS_TRAIN and HAS_PIPELINE and HAS_BILAN_DATA),
    reason="needs train.py (M12 step 4) plus ingested BILAN data",
)


# ---------------------------------------------------------------------------
# synthetic-data helpers
# ---------------------------------------------------------------------------

def _make_long(metric_id: str, times: list[pd.Timestamp], values: list[float]) -> pd.DataFrame:
    """Build a long-format DataFrame in the same shape as
    ``SELECT time, metric_id, value FROM timeseries.bilan_readings``.
    """
    return pd.DataFrame({"time": times, "metric_id": metric_id, "value": values})


def _stack(*dfs: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(list(dfs), ignore_index=True)


def _messy_cumulative_gas() -> pd.DataFrame:
    """A 24-hour cumulative gas meter with every kind of mess we know exists
    in the real BILAN data:

    * Hour 0..4   normal accumulation (+50 Nm³/h)
    * Hour 5      NaN cell (sensor dropout) → row dropped from input
    * Hour 6..9   accumulation continues (recovers to where it should be)
    * Hour 10,11  rows missing entirely (timestamp gap)
    * Hour 12     accumulation resumes (the meter advanced by ~150 Nm³ during
                  the gap — three hours of consumption land in one bucket;
                  this matches real-meter behaviour after a logger outage)
    * Hour 13,14  normal
    * Hour 15     **inversion** — meter goes backward by 12 Nm³ (mirrors the
                  real 2025-04-05 03:04:50 dip we found in M6)
    * Hour 16,17  normal
    * Hour 18..22 **flat** (operator pause / weekend, no consumption)
    * Hour 23     accumulation resumes
    """
    base = pd.Timestamp("2025-04-01 00:00:00", tz="UTC")
    times = [base + dt.timedelta(hours=h) for h in range(24)]
    # Build the ideal series, then dirty it.
    values: list[float | None] = [1000.0 + 50.0 * h for h in range(24)]

    values[5] = float("nan")          # NaN dropout
    values[15] = values[14] - 12.0    # inversion: 1700 -> 1688
    # Flat period: hours 19..22 hold steady at hour 18's value.
    flat_value = values[18]
    for h in range(19, 23):
        values[h] = flat_value
    # Hour 23 resumes a small amount.
    values[23] = flat_value + 50.0

    df = _make_long("gas.volume_cumulative", times, [float(v) if v == v else float("nan") for v in values])

    # Drop hours 10 & 11 (timestamp gap)
    df = df[~df["time"].isin([times[10], times[11]])].copy()
    # Drop the NaN row (hour 5) — model the case where the source DB filter
    # already excluded it. Ingestion never inserts NaN values into the DB.
    df = df.dropna(subset=["value"]).reset_index(drop=True)
    return df


def _import_export_with_export_window() -> pd.DataFrame:
    """24-hour grid streams where the plant exports more than it imports
    during hours 11..15. Net should go negative there and CO₂ contribution
    too (cogen export benefit).
    """
    base = pd.Timestamp("2025-04-01 00:00:00", tz="UTC")
    times = [base + dt.timedelta(hours=h) for h in range(24)]

    # Hourly increments per stream (each cumulative)
    imp_inc: list[float] = [10.0] * 24
    exp_inc: list[float] = [0.0] * 24
    # During hours 11..15: import drops to 0, export jumps to 20 kWh/h
    for h in range(11, 16):
        imp_inc[h] = 0.0
        exp_inc[h] = 20.0

    imp_cum = list(np.cumsum(imp_inc))
    exp_cum = list(np.cumsum(exp_inc))

    return _stack(
        _make_long("grid.steg.import_cumulative", times, imp_cum),
        _make_long("grid.steg.export_cumulative", times, exp_cum),
    )


# ---------------------------------------------------------------------------
# 1. cumulative deltas test
# ---------------------------------------------------------------------------

@pipeline_required
def test_cumulative_deltas_clip_inversions_and_handle_gaps() -> None:
    long_df = _messy_cumulative_gas()
    df = build_co2_dataset_from_long(long_df, granularity="1h")

    assert "gas_nm3" in df.columns
    # All hourly deltas must be non-negative — the inversion at hour 15 must
    # be clipped, not propagated.
    negative_deltas = df.loc[df["gas_nm3"] < 0, "gas_nm3"]
    assert len(negative_deltas) == 0, (
        f"expected all gas_nm3 deltas ≥ 0, got negatives: {negative_deltas.tolist()}"
    )

    # Hour 15 specifically: the inversion bucket should be exactly 0.
    ts15 = pd.Timestamp("2025-04-01 15:00:00", tz="UTC")
    if ts15 in df.index:
        assert df.loc[ts15, "gas_nm3"] == pytest.approx(0.0), (
            f"inversion bucket should clip to 0, got {df.loc[ts15, 'gas_nm3']}"
        )

    # Flat period (hours 19..22) should produce 0 deltas.
    for h in range(19, 23):
        ts = pd.Timestamp(f"2025-04-01 {h:02d}:00:00", tz="UTC")
        if ts in df.index:
            assert df.loc[ts, "gas_nm3"] == pytest.approx(0.0), (
                f"flat-period bucket {ts} should be 0, got {df.loc[ts, 'gas_nm3']}"
            )

    # Total accumulated delta should be close to (max - min) of the meter,
    # within the bonus introduced by clipping the inversion (the post-inversion
    # recovery looks like extra consumption). For our synthetic series:
    #   true consumption ≈ 950 Nm³ (1000 → 1950)
    #   plus the 12 Nm³ inversion that gets re-counted on recovery
    total_delta = float(df["gas_nm3"].sum())
    assert 940 <= total_delta <= 990, (
        f"sum of deltas {total_delta:.1f} outside expected window [940, 990]"
    )

    # The 2-hour timestamp gap should NOT have produced a NaN row in output —
    # resample('1h') creates the bucket; ffill carries the cumulative forward;
    # the diff is 0 for those buckets and the consumption that happened during
    # the gap shows up in the next valid bucket.
    for h in [10, 11]:
        ts = pd.Timestamp(f"2025-04-01 {h:02d}:00:00", tz="UTC")
        if ts in df.index:
            assert df.loc[ts, "gas_nm3"] == pytest.approx(0.0), (
                f"gap bucket {ts} should be 0 (ffilled), got {df.loc[ts, 'gas_nm3']}"
            )


# ---------------------------------------------------------------------------
# 2. net grid sign test
# ---------------------------------------------------------------------------

@pipeline_required
def test_net_grid_sign_preserves_export_benefit() -> None:
    long_df = _import_export_with_export_window()
    df = build_co2_dataset_from_long(long_df, granularity="1h")

    assert "grid_net_kwh" in df.columns
    assert "co2_grid_kg" in df.columns

    # During the export window (hours 11..15) net should be negative.
    export_hours = [pd.Timestamp(f"2025-04-01 {h:02d}:00:00", tz="UTC") for h in range(11, 16)]
    export_hours_present = [t for t in export_hours if t in df.index]
    assert export_hours_present, "expected some export-window rows in the resampled output"

    for ts in export_hours_present:
        assert df.loc[ts, "grid_net_kwh"] < 0, (
            f"{ts}: expected grid_net_kwh < 0 (export > import), "
            f"got {df.loc[ts, 'grid_net_kwh']}"
        )
        assert df.loc[ts, "co2_grid_kg"] < 0, (
            f"{ts}: expected co2_grid_kg < 0 (cogen export benefit), "
            f"got {df.loc[ts, 'co2_grid_kg']}"
        )

    # During pure-import hours net should be positive (import = 10, export = 0).
    import_hours_ts = pd.Timestamp("2025-04-01 05:00:00", tz="UTC")
    if import_hours_ts in df.index:
        assert df.loc[import_hours_ts, "grid_net_kwh"] > 0
        assert df.loc[import_hours_ts, "co2_grid_kg"] > 0

    # Sanity: the *signed* sum across the day is positive (the plant imported
    # 19 hours × 10 kWh = 190 net of 5 hours × 20 = 100, so +90 net, and CO₂
    # contribution is +90 × 0.47 ≈ +42 kg).
    daily_total_net_kwh = float(df["grid_net_kwh"].sum())
    assert daily_total_net_kwh == pytest.approx(90.0, abs=5.0), (
        f"expected ~+90 kWh net, got {daily_total_net_kwh:.1f}"
    )


# ---------------------------------------------------------------------------
# 3. no-leakage test
# ---------------------------------------------------------------------------

@features_required
def test_features_do_not_leak_future_values() -> None:
    """Build a clean series with one POISON value at row N. For every row before
    row N, no rolling / lag / window feature must contain values derived from
    row N. Catches the most common left-vs-right window mistake.
    """
    POISON = 1.0e9
    n = 50
    poison_row = 30
    base = pd.Timestamp("2025-04-01 00:00:00", tz="UTC")
    idx = pd.date_range(base, periods=n, freq="1h", tz="UTC")
    values = np.linspace(100.0, 200.0, n)
    values[poison_row] = POISON
    df = pd.DataFrame({"co2_total_kg": values}, index=idx)

    feats = engineer_features(df, target_col="co2_total_kg")

    # Every row strictly before the poison must have no feature value derived
    # from the poison. We define "derived from" as: any numeric feature whose
    # absolute value exceeds POISON / 1000 (= 1e6, way above plausible CO₂).
    safe_threshold = POISON / 1000
    poison_traces: list[tuple[int, str, float]] = []
    for row_idx in range(poison_row):
        row = feats.iloc[row_idx]
        for col, val in row.items():
            if col == "co2_total_kg":
                continue
            if pd.isna(val):
                continue
            try:
                fv = float(val)
            except (TypeError, ValueError):
                continue
            if abs(fv) >= safe_threshold:
                poison_traces.append((row_idx, str(col), fv))

    assert not poison_traces, (
        f"feature values derived from POISON leaked backward in time: "
        f"{poison_traces[:5]}"
    )


# ---------------------------------------------------------------------------
# 4. real-data test
# ---------------------------------------------------------------------------

@real_data_required
def test_real_april_data_yields_sane_co2_dataset() -> None:
    from sqlalchemy import create_engine
    from retech_part2.config import get_settings

    eng = create_engine(get_settings().database_url_sync)
    df = build_co2_dataset(db_engine=eng, granularity="1h")

    # Row count: April 1..20 = 20 days × 24h = 480 hours, allow lower bound for
    # gaps where we don't have data.
    assert 380 <= len(df) <= 480, f"expected 380..480 hourly rows, got {len(df)}"

    # The plant is mostly emitting (gas dominates).
    pos_share = float((df["co2_total_kg"] > 0).mean())
    assert pos_share >= 0.95, f"co2_total_kg should be > 0 in ≥95% of hours, got {pos_share:.1%}"

    # At least one hour where the plant is a net grid exporter (cogen benefit).
    assert (df["co2_grid_kg"] < 0).any(), (
        "expected at least one hour with co2_grid_kg < 0 (net export displacing grid)"
    )

    # 20-day total in the right ballpark (100..1000 tonnes for a cogen plant
    # at this scale).
    total_kg = float(df["co2_total_kg"].sum())
    assert 100_000 <= total_kg <= 1_000_000, (
        f"20-day total CO₂ {total_kg:,.0f} kg outside plausible range [100..1000] tonnes"
    )

    # Schema spot-check
    expected_cols = {
        "gas_nm3", "elec_produced_kwh", "grid_import_kwh", "grid_export_kwh",
        "grid_net_kwh", "co2_gas_kg", "co2_grid_kg", "co2_total_kg",
    }
    missing = expected_cols - set(df.columns)
    assert not missing, f"missing columns in build_co2_dataset output: {missing}"


# ---------------------------------------------------------------------------
# 5. forecast roundtrip
# ---------------------------------------------------------------------------

@forecast_required
def test_forecast_h1_beats_constant_predictor() -> None:
    """Train forecasters on the real data; the h=1 MAE must come in below the
    standard deviation of the test target (a constant predictor at the mean
    has MAE ≈ 0.8 × σ for a normal distribution, so σ is a generous upper
    bound — failing this means the model isn't doing meaningful work).
    """
    from sqlalchemy import create_engine
    from retech_part2.config import get_settings

    eng = create_engine(get_settings().database_url_sync)
    df = build_co2_dataset(db_engine=eng, granularity="1h")

    metadatas = train_forecasters(df, horizons=(1,))
    h1_models = [m for m in metadatas if m.horizon_hours == 1 and m.target == "co2_total_kg"]
    assert h1_models, "train_forecasters did not return a co2_total_kg @ h=1 model"
    m = h1_models[0]

    test_target_std = float(df["co2_total_kg"].iloc[-int(len(df) * 0.2):].std())
    assert m.mae < test_target_std, (
        f"h=1 MAE {m.mae:.2f} must be < test-set σ {test_target_std:.2f} "
        f"(otherwise the model is no better than predicting the mean)"
    )
