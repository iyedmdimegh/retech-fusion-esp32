// CO₂ analytics page (M12).
// Three KPI cards on top, then the actual+forecast time chart, then a
// forecast detail row, then anomalies + models tables.

import { useMemo } from "react";
import { CarbonGauge } from "../components/charts/CarbonGauge";
import { LineChart } from "../components/charts/LineChart";
import { Sparkline } from "../components/charts/Sparkline";
import { HeroKPI } from "../components/HeroKPI";
import {
  useCo2Anomalies,
  useCo2Breakdown,
  useCo2Forecast,
  useCo2Models,
  useCo2Retrain,
  useCo2Series,
} from "../lib/api/queries";

// Annual CO₂ cap for the cogen plant — visible in the gauge. Tunisian
// industrial sites of this scale typically operate under a 4-6 ktCO₂e/yr
// allowance; 5 kt is a defensible round number for the demo. Override
// later via config when a real allowance is known.
const ANNUAL_CO2_CAP_TONNES = 5000;

export function Co2Page() {
  const breakdown = useCo2Breakdown();
  const series = useCo2Series({ limit: 2000 });
  const forecast = useCo2Forecast();
  const anomalies = useCo2Anomalies();
  const models = useCo2Models();
  const retrain = useCo2Retrain();

  const seriesPoints = series.data?.points ?? [];
  const forecastPoints = forecast.data?.forecasts ?? [];
  const anomalyTimes = useMemo(
    () => new Set((anomalies.data?.anomalies ?? []).map((a) => a.time)),
    [anomalies.data],
  );

  // Build the chart series: actual past values + a CONTINUOUS dashed
  // forecast curve that picks up exactly where the last actual point ends.
  //
  // Two filters before slicing the tail, both motivated by real data
  // pathologies on multi-file ingests:
  //
  //  1. Drop rows where co2_total_kg == 0. These are mostly "padding"
  //     hours from resample().ffill() across periods with no BILAN data
  //     (e.g. May-September gap between April and October files). Showing
  //     them squashes the visible line down to the X axis.
  //  2. Drop extreme outliers (> 50,000 kg/h). The first hour after a
  //     long gap is a cross-file .diff() artifact — the cumulative meter
  //     "jumps" by months of accumulation. A real cogen plant won't emit
  //     50 t in a single hour, so this cap is safe.
  const cleanedSeries = useMemo(
    () =>
      seriesPoints.filter(
        (p) => p.co2_total_kg > 0 && p.co2_total_kg < 50_000,
      ),
    [seriesPoints],
  );

  const chart = useMemo(() => {
    if (!cleanedSeries.length) return null;
    const tail = cleanedSeries.slice(-200);
    const labels: string[] = tail.map((p) => fmtAxisDate(p.time));
    const actual: (number | null)[] = tail.map((p) => p.co2_total_kg);

    const fcSorted = [...forecastPoints].sort(
      (a, b) => a.horizon_hours - b.horizon_hours,
    );
    for (const f of fcSorted) {
      labels.push(fmtAxisDate(f.target_time));
      actual.push(null);
    }
    const forecastSeries: (number | null)[] = tail.map(() => null);
    if (tail.length && fcSorted.length) {
      // Bridge: the last actual point doubles as the first forecast point so
      // the dashed line visually grows out of the solid line, no gap.
      forecastSeries[forecastSeries.length - 1] = tail[tail.length - 1].co2_total_kg;
    }
    for (const f of fcSorted) {
      forecastSeries.push(f.predicted_co2_kg);
    }

    return { labels, actual, forecastSeries, n: tail.length };
  }, [cleanedSeries, forecastPoints]);

  // Anchor display = last cleaned actual point's time (where the dashed
  // line picks up from), or the API-provided anchor as fallback.
  const anchorTime = useMemo(() => {
    if (cleanedSeries.length) return cleanedSeries[cleanedSeries.length - 1].time;
    if (forecast.data?.anchor_time) return forecast.data.anchor_time;
    return null;
  }, [forecast.data, cleanedSeries]);

  // Detail cards: pick +1h / +6h / +24h specifically from the continuous list.
  const detailHorizons = [1, 6, 24];
  const detailForecasts = detailHorizons
    .map((h) => forecastPoints.find((f) => f.horizon_hours === h))
    .filter((f): f is NonNullable<typeof f> => !!f);

  return (
    <div>
      <div className="h-row">
        <div className="h-row__title">CO₂ analytics</div>
        <div className="h-row__hint">
          live from /api/co2/* · models stored in data/models/
        </div>
      </div>

      {/* breakdown — hero card + 2 secondary cards (each with sparkline trend) */}
      <div className="grid" style={{ gridTemplateColumns: "2fr 1fr 1fr" }}>
        <HeroKPI
          label="Total CO₂ emissions"
          value={
            breakdown.data
              ? (breakdown.data.totals.co2_total_kg / 1000).toFixed(1)
              : "—"
          }
          unit="tCO₂e"
          foot="across all ingested BILAN data"
          sub={
            breakdown.data
              ? `gas ${breakdown.data.share.gas_pct.toFixed(0)}% · grid ${breakdown.data.share.grid_pct.toFixed(0)}%`
              : undefined
          }
          loading={breakdown.isLoading}
        />
        <Kpi
          label="From gas combustion"
          value={fmtNum(breakdown.data?.totals.co2_from_gas_kg)}
          unit="kg"
          subtitle={
            breakdown.data
              ? `${breakdown.data.share.gas_pct.toFixed(1)}% of total`
              : undefined
          }
          spark={cleanedSeries.slice(-48).map((p) => p.co2_gas_kg)}
          loading={breakdown.isLoading}
        />
        <Kpi
          label="From net grid exposure"
          value={fmtNum(breakdown.data?.totals.co2_from_grid_kg)}
          unit="kg"
          subtitle={
            breakdown.data
              ? breakdown.data.totals.co2_from_grid_kg < 0
                ? `cogen export benefit (negative = avoided)`
                : `${breakdown.data.share.grid_pct.toFixed(1)}% of total`
              : undefined
          }
          tone={
            breakdown.data && breakdown.data.totals.co2_from_grid_kg < 0
              ? "ok"
              : undefined
          }
          spark={cleanedSeries.slice(-48).map((p) => p.co2_grid_kg)}
          sparkColor="var(--accent)"
          loading={breakdown.isLoading}
        />
      </div>

      {/* gauge: where are we vs the annual cap */}
      <div className="card" style={{ marginTop: 14 }}>
        <div className="card__head">
          <div>
            <div className="card__title">Carbon vs annual cap</div>
            <div className="card__sub">
              Annual cap set to {ANNUAL_CO2_CAP_TONNES.toLocaleString()} tCO₂e
              (configurable in code) · current burn extrapolated linearly
            </div>
          </div>
        </div>
        {breakdown.isLoading ? (
          <div className="skel" style={{ height: 135 }} />
        ) : breakdown.data ? (
          <CarbonGauge
            value={breakdown.data.totals.co2_total_kg / 1000}
            limit={ANNUAL_CO2_CAP_TONNES}
            unit="tCO₂e"
          />
        ) : null}
      </div>

      {/* actual + forecast chart */}
      <div className="card" style={{ marginTop: 14 }}>
        <div className="card__head">
          <div>
            <div className="card__title">CO₂ over time + next-24 h forecast</div>
            <div className="card__sub">
              Hourly · solid = actual, dashed = rolling multi-step forecast
              starting from the last data point
              {chart && ` · last ${chart.n} hours of activity`}
              {seriesPoints.length > cleanedSeries.length &&
                ` (${seriesPoints.length - cleanedSeries.length} zero / outlier rows hidden — multi-file artifact)`}
              {anomalyTimes.size > 0 &&
                ` · ${anomalyTimes.size} anomalous hour${anomalyTimes.size === 1 ? "" : "s"} flagged`}
            </div>
          </div>
          {anchorTime && (
            <div
              className="tag info"
              title="The forecast anchors on the last hourly row in the BILAN-derived dataset, NOT on real-world wall-clock time."
            >
              Last data: {new Date(anchorTime).toLocaleString()}
            </div>
          )}
        </div>
        {series.isLoading || forecast.isLoading ? (
          <div className="skel" style={{ height: 240 }} />
        ) : chart ? (
          <LineChart
            labels={chart.labels}
            series={[
              {
                name: "Actual",
                data: chart.actual,
                color: "var(--ink)",
                fill: true,
              },
              {
                name: "Forecast",
                data: chart.forecastSeries,
                color: "var(--accent)",
                dashed: true,
              },
            ]}
            height={280}
          />
        ) : (
          <EmptyState />
        )}
      </div>

      {/* forecast detail row — pick +1 / +6 / +24 from the continuous list */}
      <div className="grid gtc-3" style={{ marginTop: 14 }}>
        {detailForecasts.length === 0 && (
          <div className="card" style={{ gridColumn: "span 3" }}>
            <div className="muted tiny">
              No forecasts yet. Click "Retrain models" below.
            </div>
          </div>
        )}
        {detailForecasts.map((f) => (
          <div key={f.horizon_hours} className="kpi">
            <div className="kpi__label">+{f.horizon_hours} h after last data</div>
            <div className="kpi__row">
              <span className="kpi__val num">{fmtNum(f.predicted_co2_kg)}</span>
              <span className="kpi__unit">kg CO₂</span>
            </div>
            <div className="kpi__foot">
              target: {new Date(f.target_time).toLocaleString()}
              {f.rmse_band != null && (
                <>
                  <br />
                  ±{fmtNum(f.rmse_band)} kg (training RMSE band)
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* anomalies + models, side-by-side */}
      <div className="grid" style={{ gridTemplateColumns: "1.4fr 1fr", marginTop: 14 }}>
        <div className="card" style={{ padding: 0 }}>
          <div className="card__head" style={{ padding: "16px 18px 6px", margin: 0 }}>
            <div>
              <div className="card__title">
                Anomalies{" "}
                {anomalies.data && (
                  <span className="tag warn" style={{ marginLeft: 8 }}>
                    {anomalies.data.count}
                  </span>
                )}
              </div>
              <div className="card__sub">
                IsolationForest · contamination 2 % · top by score
              </div>
            </div>
          </div>
          {anomalies.isLoading ? (
            <div style={{ padding: 18 }}>
              <div className="skel" style={{ height: 18, marginBottom: 8 }} />
              <div className="skel" style={{ height: 18, marginBottom: 8 }} />
              <div className="skel" style={{ height: 18 }} />
            </div>
          ) : (anomalies.data?.anomalies.length ?? 0) === 0 ? (
            <div style={{ padding: 18 }} className="muted tiny">
              none flagged
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ paddingLeft: 18 }}>Time</th>
                  <th className="right">CO₂ (kg)</th>
                  <th className="right" style={{ paddingRight: 18 }}>
                    Score
                  </th>
                </tr>
              </thead>
              <tbody>
                {anomalies.data!.anomalies.slice(0, 12).map((a) => (
                  <tr key={a.time}>
                    <td style={{ paddingLeft: 18 }} className="mono">
                      {new Date(a.time).toLocaleString()}
                    </td>
                    <td className="num">{fmtNum(a.co2_total_kg)}</td>
                    <td className="num" style={{ paddingRight: 18 }}>
                      {a.anomaly_score?.toFixed(3) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card" style={{ padding: 0 }}>
          <div className="card__head" style={{ padding: "16px 18px 6px", margin: 0 }}>
            <div>
              <div className="card__title">Active models</div>
              <div className="card__sub">
                {models.data?.length ?? 0} model{models.data?.length === 1 ? "" : "s"}
                · MAE on chronological 80/20 split
              </div>
            </div>
          </div>
          {models.isLoading ? (
            <div style={{ padding: 18 }}>
              <div className="skel" style={{ height: 18, marginBottom: 8 }} />
            </div>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ paddingLeft: 18 }}>Target / horizon</th>
                  <th>Algo</th>
                  <th className="right">MAE</th>
                  <th className="right" style={{ paddingRight: 18 }}>
                    RMSE
                  </th>
                </tr>
              </thead>
              <tbody>
                {(models.data ?? []).map((m) => (
                  <tr key={m.model_id}>
                    <td style={{ paddingLeft: 18 }}>
                      <strong>{m.target}</strong>
                      <div className="muted tiny mono" style={{ marginTop: 2 }}>
                        {m.horizon_hours > 0
                          ? `+${m.horizon_hours} h`
                          : "anomaly"}
                      </div>
                    </td>
                    <td className="muted tiny mono">{m.algorithm}</td>
                    <td className="num">{m.mae == null ? "—" : fmtNum(m.mae)}</td>
                    <td className="num" style={{ paddingRight: 18 }}>
                      {m.rmse == null ? "—" : fmtNum(m.rmse)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div style={{ padding: 14, borderTop: "1px solid var(--hairline)" }}>
            <button
              className="btn"
              onClick={() => retrain.mutate()}
              disabled={retrain.isPending}
              style={{ width: "100%" }}
            >
              {retrain.isPending ? "Training… (5–15 s)" : "↻ Retrain models"}
            </button>
            {retrain.isError && (
              <div className="muted tiny" style={{ color: "var(--crit)", marginTop: 8 }}>
                {String(retrain.error)}
              </div>
            )}
            {retrain.isSuccess && (
              <div className="muted tiny" style={{ marginTop: 8 }}>
                Retrained in {retrain.data?.duration_seconds.toFixed(1)} s ·{" "}
                {retrain.data?.rows_in_dataset.toLocaleString()} rows · {" "}
                {retrain.data?.anomalies_flagged} anomalies flagged
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Kpi({
  label,
  value,
  unit,
  subtitle,
  tone,
  loading,
  spark,
  sparkColor,
}: {
  label: string;
  value: string;
  unit: string;
  subtitle?: string;
  tone?: "ok" | "warn" | "crit";
  loading?: boolean;
  spark?: (number | null | undefined)[];
  sparkColor?: string;
}) {
  const color =
    tone === "ok"
      ? "var(--ok)"
      : tone === "crit"
      ? "var(--crit)"
      : tone === "warn"
      ? "var(--warn)"
      : undefined;
  return (
    <div className="kpi">
      <div className="kpi__label">{label}</div>
      <div className="kpi__row">
        {loading ? (
          <div className="skel" style={{ width: 120, height: 28 }} />
        ) : (
          <span className="kpi__val num" style={{ color }}>
            {value}
          </span>
        )}
        <span className="kpi__unit">{unit}</span>
      </div>
      {subtitle && <div className="kpi__foot">{subtitle}</div>}
      {spark && spark.length > 0 && (
        <div style={{ marginTop: "auto" }}>
          <Sparkline data={spark} color={sparkColor ?? "var(--ink)"} fill height={32} />
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="muted tiny" style={{ padding: 12 }}>
      No CO₂ series yet. Click "Retrain models" to compute.
    </div>
  );
}

function fmtNum(n?: number | null): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1000) return Math.round(n).toLocaleString();
  return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function fmtAxisDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    hour12: false,
  });
}
