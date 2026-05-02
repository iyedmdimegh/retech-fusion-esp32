# CO₂ Forecasting & Anomaly Detection (M12)

> **Status as of 2026-05-03:** *foundation only*. The schema, the shared
> data-prep helper, the dependencies, the configuration surface, and the
> test scaffolding are all in place. **The actual XGBoost forecasters and
> the IsolationForest anomaly detector were specified, the formulas were
> corrected, the migration file was written — but the training and
> inference modules were not implemented before the project pivoted to
> frontend integration (M13–M15).** This document explains the design,
> the corrections we applied to the original draft, what IS in the repo
> today, and what's still missing.

---

## 1. Why this work exists

The hackathon's checkpoint demo headline is **"plant CO₂ over time, with
near-future forecast and anomaly markers."** Three things make that hard
on the BILAN data we ingest:

1. **The meters are cumulative**, not rates. Naively multiplying a
   cumulative reading by an emission factor gives you "emissions since
   plant startup", not "emissions this hour."
2. **The plant is a cogen unit** — it generates more electricity than it
   consumes for most hours, so the grid term is *signed*. A naive grid-CO₂
   model double-counts (the gas that produced the exported electricity is
   already in the gas term) AND ignores the export benefit (exported
   electricity displaces grid electricity emitted elsewhere).
3. **The data has known anomalies** — sensor noise, blank cells, whole-
   column zeros, monotonic inversions — that we already tag at ingestion.
   An anomaly detector trained on the raw cumulative series would flag
   "the most recent points" as anomalies because they have the highest
   values; it would learn nothing useful.

The M12 milestone was supposed to deliver:

- A per-hour CO₂ time series (in kg/h) computed from the BILAN cumulative
  meters with the corrections above.
- Three forecasters at horizons +1 h / +6 h / +24 h.
- A joint-feature anomaly detector that flags suspicious *combinations*
  of gas + electricity + grid behaviour, not bad rows of any single meter.
- REST endpoints the frontend would call.
- A retrain CLI + POST endpoint so re-uploading new BILAN files can refresh
  the models without redeploying.

Of those, only the **first half of bullet 1** (the per-hour series, minus
the emission-factor multiplication) was actually built — and it lives in
the M15 consumption helper, which the energy-analytics page already uses.
The rest is documented design, not running code.

---

## 2. What's in the repo TODAY

### 2a. Schema — `alembic/versions/005_analytics_schema.py` ✅ APPLIED

Three tables in a new `analytics.` schema. Migration is at HEAD; tables
exist; **all three are empty**.

| Table | Purpose | Hypertable? |
|---|---|---|
| `analytics.co2_hourly` | Materialised hourly CO₂ + breakdown (gas / grid / total). Repopulated by each training run. The dashboard queries it. | yes (on `time`) |
| `analytics.co2_forecasts` | Forecast outputs from the most recent training run. `(forecast_made_at, target_time, horizon_hours)` PK. Replaced wholesale on each retrain. | yes (on `target_time`) |
| `analytics.co2_models` | Model registry. One row per (target, horizon) per training run. Holds metrics + the joblib artifact path. A **partial unique index** `WHERE is_active = TRUE` enforces "exactly one active model per (target, horizon)" while keeping unbounded historical rows. | no |

The deferred-unique-constraint approach the original spec called for was
swapped to a partial unique index — the spec's form would have silently
capped retrain history at one row per (target, horizon, true/false).
Documented in the migration file's docstring.

### 2b. Shared data-prep helper — `src/retech_part2/analytics/co2/pipeline.py` ✅ BUILT

`build_consumption_series(...)` does the per-interval-delta math the
forecaster would have called as its first step. It's the pre-CO₂ part of
what M12's `build_co2_dataset()` would have done — the M15 energy-analytics
page already uses it for `/api/bilan/consumption`. When M12's modeling
work resumes, it just multiplies the columns this helper returns by the
emission factors.

What it does, in order:

1. Pulls the four cumulative meters (`gas.volume_cumulative`,
   `electrical.alternator.energy_cumulative`,
   `grid.steg.import_cumulative`, `grid.steg.export_cumulative`)
   from `timeseries.bilan_readings` with optional `file_id` and date
   filters.
2. **Filters out rows tagged `whole_column_zero` or `monotonic_inversion`**
   — the validators in M6 already identified these as bad data and tagged
   them in `data_quality_flags TEXT[]`. The forecaster cannot see them.
3. Pivots long → wide.
4. **Resamples** to `1h` / `10min` / `1d` using `.last()` (cumulative
   meters → take the most recent reading in each bucket).
5. **`.ffill()`** across gaps. *Never `.fillna(0)`* on a cumulative meter —
   that would create a fake reset and a huge spurious positive delta on
   the next `.diff()`.
6. `.diff()` to get per-interval deltas.
7. Clip negatives to 0 on gas + on-site electricity (residual noise).
8. **Preserve the sign** on `grid_net = import − export` — exported
   electricity is intentional cogen behaviour; making it positive would
   destroy the entire reason cogen plants are considered a
   decarbonisation technology.

### 2c. Dependencies + configuration ✅ INSTALLED

`pyproject.toml` ships `xgboost ≥ 2.1`, `scikit-learn ≥ 1.5`, `joblib ≥ 1.4`.
All three are in the venv.

`src/retech_part2/config.py` has the M12 settings:

| Setting | Default | Source |
|---|---|---|
| `co2_gas_factor_kg_per_nm3` | `1.96` | derived from PCI 9.082 thermie/Nm³ (BILAN sheet header) + CH₄/C₂H₆ stoichiometry. Tunisian pipeline gas. |
| `co2_grid_factor_kg_per_kwh` | `0.47` | STEG 2023 sustainability report. Average grid intensity. |
| `co2_horizons` | `"1,6,24"` | hours, parsed at use site |
| `co2_test_ratio` | `0.2` | chronological train/test split |
| `co2_anomaly_contamination` | `0.02` | IsolationForest expected anomaly fraction |
| `co2_models_dir` | `"data/models"` | joblib pickles land here. Gitignored. |

These can be overridden in `.env` (`CO2_GAS_FACTOR_KG_PER_NM3=...` etc.)
without code changes — useful for when regulators / the local utility
update their figures.

### 2d. Test scaffolding — `tests/test_co2_pipeline.py` ⚠ GATED

Five tests written before the implementation (TDD-style). Each guards on
the modules it depends on, so when later milestone steps land the tests
auto-run without manual unskip:

| # | Test | Currently skips because |
|---|---|---|
| 1 | `test_cumulative_deltas_clip_inversions_and_handle_gaps` | n/a — **passes today** against the M15 helper |
| 2 | `test_net_grid_sign_preserves_export_benefit` | n/a — **passes today** |
| 3 | `test_features_do_not_leak_future_values` | `features.py` does not exist |
| 4 | `test_real_april_data_yields_sane_co2_dataset` | needs M12 `build_co2_dataset()` (factor multiplication) |
| 5 | `test_forecast_h1_beats_constant_predictor` | needs `train.py` |

Synthetic test data is built with the same messiness as real BILAN data:
NaN cells, 2-hour timestamp gaps, monotonic inversions, flat operator-pause
periods, net-export windows, and a "poison" value for leakage detection.
Tests on perfect input would catch nothing; tests on realistic noise catch
the bugs the spec was specifically guarding against.

---

## 3. What's NOT in the repo (the M12 design that didn't ship)

The following modules were specified in detail but never written. The
shapes they would have are documented here so anyone resuming the work
has the contract.

### `factors.py` — emission-factor constants with provenance

```python
# Reads from settings (so .env overrides work); asserts plausible bounds
KG_CO2_PER_NM3_NATURAL_GAS: float = settings.co2_gas_factor_kg_per_nm3   # 1.96
KG_CO2_PER_KWH_STEG_GRID: float = settings.co2_grid_factor_kg_per_kwh   # 0.47

assert 1.5 <= KG_CO2_PER_NM3_NATURAL_GAS <= 2.5
assert 0.1 <= KG_CO2_PER_KWH_STEG_GRID   <= 1.0
```

The bounds are sanity guards — refuse to use absurd factors from a
misconfigured `.env`.

### `pipeline.py` — `build_co2_dataset()` (extension, not duplication)

Would have called the existing `build_consumption_series()` helper, then
applied factors:

```python
co2_gas_kg   = gas_nm3      * KG_CO2_PER_NM3_NATURAL_GAS
co2_grid_kg  = grid_net_kwh * KG_CO2_PER_KWH_STEG_GRID    # signed!
co2_total_kg = co2_gas_kg + co2_grid_kg
```

Negative `co2_grid_kg` is preserved — that's the cogen export benefit.

### `features.py` — `engineer_features(df, target_col)`

For each input row, builds a feature vector from past values only:

| Family | Values |
|---|---|
| Lags | `t-1, t-3, t-6, t-12, t-24, t-48, t-168` hours (last is one week) |
| Rolling | mean, std, min, max for windows `[3, 6, 12, 24]` hours |
| Calendar | hour, day-of-week, month, day, is_weekend, is_business_hours (8–18 weekdays) |

**Critical: rolling windows must be left-trailing.** The test
`test_features_do_not_leak_future_values` exists specifically to catch
the case where a feature at time `t` accidentally consumes data from
`t+1` (right-aligned window, off-by-one in lag, etc.). A poison value
`1e9` is placed at row `t+1` and every feature at row `t` and earlier
is checked for derivative values exceeding `1e6`. Catches both wrong
window alignment and forward-shifted lags.

### `train.py` — two functions

1. **`train_forecasters(df, horizons=(1, 6, 24))`** — for each horizon,
   shifts the target by `-h`, splits 80/20 chronologically, fits an
   `XGBRegressor` (400 trees, depth 6, lr 0.05, subsample 0.8), measures
   MAE / RMSE / MAPE on the held-out tail, saves to
   `data/models/co2_total_h{h}.pkl` via joblib, inserts a row into
   `analytics.co2_models` with the metrics, and **deactivates the previous
   active model** for the same `(target, horizon)` so the partial unique
   index is satisfied. Returns metadata for the API to surface.
2. **`train_anomaly_detector(df)`** — fits `IsolationForest` with
   `contamination=0.02` on the **engineered feature matrix** (deltas,
   lags, rolling windows, calendar features), **never on the raw
   cumulative columns**. Saves to `data/models/anomaly_detector.pkl`.
   Writes `is_anomaly` and `anomaly_score` back to `analytics.co2_hourly`.

   The choice matters: fitting IsolationForest directly on
   `gas.volume_cumulative` would just flag the most recent rows because
   they have the highest values. Fitting on engineered features lets the
   detector learn *joint* relationships (e.g. "high gas burn but no
   electricity production" — that's a real anomaly even though both
   numbers individually look normal).

### `predict.py` — runtime inference

`predict_horizons(as_of=...)` loads the active model artefacts from
`data/models/`, pulls the most recent N hours from `analytics.co2_hourly`,
engineers features as of `as_of`, predicts each horizon, returns a
`ForecastBundle` with point forecasts plus a confidence band of ±1 RMSE
(from training-time metrics). Writes the forecasts into
`analytics.co2_forecasts`.

### `api/routes/co2.py` — six endpoints

```
GET  /api/co2/series?from=&to=&granularity=     # the time-series chart
GET  /api/co2/breakdown?from=&to=               # totals + gas/grid share %
GET  /api/co2/forecast?from_now=true            # 3 horizons, with confidence bands
GET  /api/co2/anomalies?from=&to=               # rows with is_anomaly=true
GET  /api/co2/models/status                     # active models + their MAE / trained_at
POST /api/co2/retrain                           # enqueues an RQ retrain job
```

The retrain POST hooks into the existing M7 `meta.ingestion_jobs` /
RQ-worker pattern with `job_type='co2_retrain'` — same UI plumbing as
BILAN/invoice ingest jobs.

---

## 4. The seven formula corrections we applied to the original draft

The user had a draft script (`script_for_traing.py`) that got the rough
shape right but had several correctness problems we explicitly fixed in
the M12 design. These are documented here so they don't get lost when
someone resumes the work.

| # | Bug in draft | Correction |
|---|---|---|
| 1 | Multiplied raw cumulative meters by emission factors | Take per-interval `.diff()` after resampling; clip negatives on gas/elec to zero |
| 2 | Auto-picked first column matching `power\|electric\|kwh` (would grab `electrical.alternator.energy_cumulative` — cogen output, not grid import → double-counts because the gas burned to make that electricity is already in the gas term) | Use `grid_net_kwh = grid_import.diff() − grid_export.diff()`; **keep the sign** so net-export is intentionally negative |
| 3 | Magic-number factors (`GAS_FACTOR = 1.9`, `GRID_FACTOR = 0.58`) with no documented provenance | Named constants in `factors.py` with units, sources (PCI, STEG report), `.env` overrides, and assert-bounded sanity checks |
| 4 | `.fillna(0)` on cumulative columns BEFORE diff | `.ffill()` on cumulative columns (carry last-known total forward across gaps); `.fillna(0).clip(lower=0)` only on the deltas |
| 5 | `HORIZONS = [1, 6, 24]` interpreted as 10-minute steps because BILAN cadence is ~10 min → forecasts 10 min / 1 h / 4 h, not 1 h / 6 h / 24 h | Resample to hourly first; THEN `[1, 6, 24]` actually means hours |
| 6 | IsolationForest fit on raw cumulative columns → flags "most recent points" because they have the highest values; learns nothing useful | Fit on the **same engineered feature matrix** the forecaster uses (deltas, lags, rolling windows, calendar) — never on cumulative columns directly |
| 7 | `random_state=42` only on XGB/IsolationForest. pandas groupby + dropna order can introduce nondeterminism. | Seed numpy + Python's `random` at the top of the training script in addition to per-model seeds. Determinism matters for reproducible demos. |

---

## 5. How the pieces fit together (intended end-to-end flow)

```
┌──────────────────────┐
│  user uploads        │
│  BILAN .xlsx         │
└────────┬─────────────┘
         │ POST /api/ingest/upload (M7)
         ▼
┌──────────────────────┐
│  RQ worker runs      │
│  ingest_bilan        │ — populates timeseries.bilan_readings
│  (M6)                │   with data_quality_flags tagged
└────────┬─────────────┘
         │ user clicks "Retrain CO₂ models"  (POST /api/co2/retrain)
         ▼
┌──────────────────────┐
│  RQ worker runs      │
│  train_forecasters + │
│  train_anomaly_detector
│  (M12 — NOT BUILT)   │ — populates analytics.co2_hourly,
└────────┬─────────────┘   analytics.co2_models, joblib pickles
         │
         ▼
┌──────────────────────┐    GET /api/co2/series      ┌────────────────┐
│  predict.py          │    GET /api/co2/breakdown   │  Frontend       │
│  loads active models │    GET /api/co2/forecast    │  CO₂ panel      │
│  on each forecast    │ ◄ GET /api/co2/anomalies    │  (NOT BUILT)    │
│  request             │    GET /api/co2/models/...  │                 │
└──────────────────────┘                              └────────────────┘
```

What's broken in this picture today: everything from the second box
onwards. The first box (BILAN → tagged readings in DB) is real and
working.

---

## 6. To resume the work

The scope is well-defined and the tests are already there. Order of
operations to finish M12:

1. Write `factors.py` (10 lines).
2. Extend `pipeline.py` with `build_co2_dataset()` that calls the existing
   `build_consumption_series()` and applies factors. Test 4 unblocks.
3. Write `features.py`. Test 3 unblocks. **Run test 3 — the leakage check
   is the most important guarantee in the file.**
4. Write `train.py`. Run on the April BILAN data. Should produce 3 model
   artefacts in `data/models/` and 3+1 rows in `analytics.co2_models`.
   Test 5 unblocks.
5. Write `predict.py`.
6. Write `api/routes/co2.py` and register it in `api/main.py`.
7. Wire `co2_retrain` job type into `workers/tasks.py` and the upload-page
   flow.
8. Add a CO₂ panel to the frontend (`/plant-1/co2` route, new page,
   reuses the existing chart components).

Estimated time at the same pace as M11/M15: 2–3 hours of focused work
once started.

---

## 7. References

- Original M12 specification: pasted into the conversation by the user
  before M12 began. Includes the 7 formula corrections above and the
  full module / endpoint inventory.
- Draft script the corrections came from: `script_for_traing.py` in
  the user's `Downloads/` folder.
- Existing data-prep helper used by both M15 and the planned M12:
  [src/retech_part2/analytics/co2/pipeline.py](../src/retech_part2/analytics/co2/pipeline.py)
- Tests waiting to unblock: [tests/test_co2_pipeline.py](../tests/test_co2_pipeline.py)
- Migration: [alembic/versions/005_analytics_schema.py](../alembic/versions/005_analytics_schema.py)
- Configuration: [src/retech_part2/config.py](../src/retech_part2/config.py)
  (search for `co2_`)
