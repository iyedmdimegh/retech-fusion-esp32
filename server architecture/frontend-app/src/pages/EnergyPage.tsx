import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { LineChart } from "../components/charts/LineChart";
import { SignedBarChart } from "../components/charts/SignedBarChart";
import { Sparkline } from "../components/charts/Sparkline";
import { RankList, type RankListItem } from "../components/RankList";
import {
  useBilanConsumption,
  useBilanFiles,
  useBilanTopMetrics,
  type Granularity,
} from "../lib/api/queries";

const GRANULARITIES: { id: Granularity; label: string }[] = [
  { id: "10min", label: "10 min" },
  { id: "1h", label: "Hourly" },
  { id: "1d", label: "Daily" },
];

export function EnergyPage() {
  const [search, setSearch] = useSearchParams();
  const filesQ = useBilanFiles(50);

  const fileIdParam = search.get("file_id") ?? undefined;
  const granularity =
    (search.get("granularity") as Granularity | null) ?? "1h";
  const fromParam = search.get("from") ?? undefined;
  const toParam = search.get("to") ?? undefined;

  // Default to most-recent file if URL didn't pin one and we have files.
  useEffect(() => {
    if (!fileIdParam && filesQ.data && filesQ.data.length > 0) {
      const next = new URLSearchParams(search);
      next.set("file_id", filesQ.data[0].file_id);
      setSearch(next, { replace: true });
    }
  }, [fileIdParam, filesQ.data, search, setSearch]);

  const selectedFile = useMemo(
    () => filesQ.data?.find((f) => f.file_id === fileIdParam),
    [filesQ.data, fileIdParam],
  );

  // Default the date range to the file's full range if not pinned in URL.
  const effectiveFrom = fromParam ?? toIsoStart(selectedFile?.date_range_start);
  const effectiveTo = toParam ?? toIsoEnd(selectedFile?.date_range_end);

  const consumptionQ = useBilanConsumption({
    file_id: fileIdParam,
    from: effectiveFrom,
    to: effectiveTo,
    granularity,
    enabled: !!fileIdParam,
  });

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(search);
    if (value == null) next.delete(key);
    else next.set(key, value);
    setSearch(next, { replace: true });
  };

  return (
    <div>
      <div className="h-row">
        <div className="h-row__title">Energy consumption</div>
        <div className="h-row__hint">live from /api/bilan/consumption</div>
      </div>

      {/* controls */}
      <div className="card">
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "2fr 1fr 1fr 1fr",
            gap: 12,
            alignItems: "end",
          }}
        >
          <Field label="BILAN file">
            <select
              className="ctrl"
              value={fileIdParam ?? ""}
              onChange={(e) => setParam("file_id", e.target.value)}
              disabled={filesQ.isLoading}
            >
              {filesQ.data?.map((f) => (
                <option key={f.file_id} value={f.file_id}>
                  {f.filename} ({fmtDate(f.date_range_start)} →{" "}
                  {fmtDate(f.date_range_end)})
                </option>
              ))}
            </select>
          </Field>
          <Field label="From">
            <input
              type="date"
              className="ctrl"
              value={isoToDate(effectiveFrom)}
              onChange={(e) =>
                setParam("from", e.target.value ? `${e.target.value}T00:00:00Z` : null)
              }
            />
          </Field>
          <Field label="To">
            <input
              type="date"
              className="ctrl"
              value={isoToDate(effectiveTo)}
              onChange={(e) =>
                setParam("to", e.target.value ? `${e.target.value}T23:59:59Z` : null)
              }
            />
          </Field>
          <Field label="Granularity">
            <div className="seg" style={{ height: 36 }}>
              {GRANULARITIES.map((g) => (
                <button
                  key={g.id}
                  className={`seg__btn ${g.id === granularity ? "is-active" : ""}`}
                  style={{ height: 28 }}
                  onClick={() => setParam("granularity", g.id)}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </Field>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid gtc-3" style={{ marginTop: 14 }}>
        <Kpi
          label="Total gas consumed"
          value={fmtNum(consumptionQ.data?.totals.gas_nm3)}
          unit="Nm³"
          spark={consumptionQ.data?.series.slice(-72).map((p) => p.gas_nm3)}
          loading={consumptionQ.isLoading}
        />
        <Kpi
          label="On-site electricity produced"
          value={fmtNum(consumptionQ.data?.totals.elec_produced_kwh)}
          unit="kWh"
          spark={consumptionQ.data?.series.slice(-72).map((p) => p.elec_produced_kwh)}
          sparkColor="var(--accent)"
          loading={consumptionQ.isLoading}
        />
        <Kpi
          label="Net grid balance"
          value={fmtNum(consumptionQ.data?.totals.grid_net_kwh)}
          unit="kWh"
          tone={
            consumptionQ.data && consumptionQ.data.totals.grid_net_kwh < 0
              ? "ok"
              : "warn"
          }
          subtitle={
            consumptionQ.data?.totals.grid_net_kwh != null
              ? consumptionQ.data.totals.grid_net_kwh < 0
                ? "net exporter (cogen surplus)"
                : "net importer"
              : undefined
          }
          spark={consumptionQ.data?.series.slice(-72).map((p) => p.grid_net_kwh)}
          sparkColor="var(--secondary)"
          loading={consumptionQ.isLoading}
        />
      </div>

      {/* charts */}
      {consumptionQ.isLoading && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="skel" style={{ height: 220 }} />
        </div>
      )}

      {consumptionQ.data && (
        <ConsumptionCharts data={consumptionQ.data} granularity={granularity} />
      )}

      {consumptionQ.isError && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="card__title" style={{ color: "var(--crit)" }}>
            Failed to load series
          </div>
          <pre style={{ fontSize: 11, color: "var(--ink-mute)" }}>
            {String(consumptionQ.error)}
          </pre>
        </div>
      )}

      <TopMetricsSection />
    </div>
  );
}

function TopMetricsSection() {
  const top = useBilanTopMetrics(8);
  const items: RankListItem[] = (top.data ?? []).map((m) => ({
    name: friendlyMetricName(m.metric_id),
    sub: `${m.label.trim()} · ${m.category}`,
    value: m.total_delta,
    unit: m.unit,
  }));

  return (
    <>
      <div className="h-row">
        <div className="h-row__title">Top consuming subsystems</div>
        <div className="h-row__hint">
          ranked by cumulative-meter delta · all ingested data
        </div>
      </div>
      <div className="card">
        <RankList
          items={items}
          loading={top.isLoading}
          emptyText="no cumulative-meter data yet"
        />
      </div>
    </>
  );
}

function friendlyMetricName(metric_id: string): string {
  // "electrical.alternator.energy_cumulative" → "Alternator energy (cogen output)"
  const parts = metric_id.split(".");
  const last = parts[parts.length - 1].replace(/_/g, " ");
  const head = parts.slice(0, -1).join(" / ").replace(/_/g, " ");
  return `${head} — ${last}`;
}

function ConsumptionCharts({
  data,
  granularity,
}: {
  data: { series: Array<{
    time: string;
    gas_nm3: number;
    elec_produced_kwh: number;
    grid_net_kwh: number;
  }> };
  granularity: Granularity;
}) {
  const labels = data.series.map((p) => labelForGranularity(p.time, granularity));
  const gas = data.series.map((p) => p.gas_nm3);
  const elec = data.series.map((p) => p.elec_produced_kwh);
  const net = data.series.map((p) => p.grid_net_kwh);

  return (
    <>
      <ChartCard title="Gas consumption" sub={`Nm³ per ${labelGran(granularity)}`}>
        <LineChart
          labels={labels}
          series={[
            { name: "Gas", data: gas, color: "var(--ink)", fill: true },
          ]}
        />
      </ChartCard>
      <ChartCard
        title="On-site electricity production"
        sub={`kWh per ${labelGran(granularity)} · cogen alternator`}
      >
        <LineChart
          labels={labels}
          series={[
            { name: "Production", data: elec, color: "var(--accent)", fill: true },
          ]}
        />
      </ChartCard>
      <ChartCard
        title="Net grid exchange"
        sub="kWh · positive = importing from STEG, negative = exporting (cogen surplus)"
      >
        <SignedBarChart data={net} labels={labels} />
      </ChartCard>
    </>
  );
}

function ChartCard({
  title,
  sub,
  children,
}: {
  title: string;
  sub: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="card__head">
        <div>
          <div className="card__title">{title}</div>
          <div className="card__sub">{sub}</div>
        </div>
      </div>
      {children}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div
        className="muted tiny"
        style={{ marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.06 }}
      >
        {label}
      </div>
      {children}
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
          <div className="skel" style={{ width: 100, height: 28 }} />
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

function fmtNum(n?: number | null): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 100_000) return Math.round(n).toLocaleString();
  return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

function isoToDate(iso?: string | null): string {
  if (!iso) return "";
  return iso.slice(0, 10);
}

function toIsoStart(d?: string | null): string | undefined {
  if (!d) return undefined;
  return `${d}T00:00:00Z`;
}

function toIsoEnd(d?: string | null): string | undefined {
  if (!d) return undefined;
  return `${d}T23:59:59Z`;
}

function labelGran(g: Granularity): string {
  return g === "10min" ? "10 min" : g === "1h" ? "hour" : "day";
}

function labelForGranularity(iso: string, g: Granularity): string {
  const d = new Date(iso);
  if (g === "1d") {
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
  if (g === "1h") {
    return d.toLocaleString(undefined, {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      hour12: false,
    });
  }
  return d.toLocaleString(undefined, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
