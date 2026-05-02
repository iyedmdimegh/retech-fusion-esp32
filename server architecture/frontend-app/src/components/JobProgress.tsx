// Polled status card for a single ingestion job. Shows spinner while
// pending/running, then a structured summary on success/partial_success/failed.

import { Link } from "react-router-dom";
import { isTerminalStatus, useJob, type IngestionJob } from "../lib/api/queries";

export function JobProgress({ jobId }: { jobId: string }) {
  const { data: job, isLoading, isError, error } = useJob(jobId);

  if (isLoading) {
    return <Card title={`Job ${jobId.slice(0, 8)}…`} subtitle="loading…" />;
  }
  if (isError || !job) {
    return (
      <Card title={`Job ${jobId.slice(0, 8)}…`} subtitle="failed to fetch">
        <pre style={{ fontSize: 11, color: "var(--ink-mute)" }}>{String(error)}</pre>
      </Card>
    );
  }

  const terminal = isTerminalStatus(job.status);
  const tone =
    job.status === "success"
      ? "ok"
      : job.status === "partial_success"
      ? "warn"
      : job.status === "failed"
      ? "crit"
      : "info";

  return (
    <Card
      title={
        <span>
          Job <span className="mono">{jobId.slice(0, 8)}…</span>{" "}
          <span className={`tag ${tone}`} style={{ marginLeft: 8 }}>
            {job.status}
          </span>
        </span>
      }
      subtitle={
        terminal
          ? "ingestion complete"
          : "polling every 1s — this usually takes 10-30 s for a real BILAN file"
      }
    >
      {!terminal && <Spinner />}
      {terminal && <JobSummary job={job} />}
    </Card>
  );
}

function JobSummary({ job }: { job: IngestionJob }) {
  const w = (job.warnings ?? {}) as Record<string, unknown>;
  const rowsInserted = numField(w, "rows_inserted");
  const rowsDropUnmapped = numField(w, "rows_dropped_unmapped");
  const rowsDropDup = numField(w, "rows_dropped_duplicate_in_file");
  const wholeColZero = numField(w, "whole_column_zero_rows");
  const monoInversions = w["monotonic_inversions_by_metric"] as
    | Record<string, number>
    | undefined;

  return (
    <div className="kv" style={{ marginTop: 4 }}>
      <span>
        Rows inserted <strong>{fmtNum(rowsInserted)}</strong>
      </span>
      {rowsDropUnmapped != null && (
        <span>
          Unmapped <strong>{fmtNum(rowsDropUnmapped)}</strong>
        </span>
      )}
      {rowsDropDup != null && (
        <span>
          Intra-file dups <strong>{fmtNum(rowsDropDup)}</strong>
        </span>
      )}
      {wholeColZero != null && wholeColZero > 0 && (
        <span>
          Whole-column-zero rows <strong>{fmtNum(wholeColZero)}</strong>
        </span>
      )}
      {monoInversions && (
        <span>
          Monotonic inversions{" "}
          <strong>
            {Object.values(monoInversions).reduce((s, n) => s + n, 0)} across{" "}
            {Object.keys(monoInversions).length} metrics
          </strong>
        </span>
      )}
      {job.error_message && (
        <span style={{ color: "var(--crit)", flexBasis: "100%" }}>
          {job.error_message}
        </span>
      )}
      <span style={{ flexBasis: "100%", marginTop: 8 }}>
        <Link to={`/plant-1/energy`} className="btn">
          View energy analytics →
        </Link>
      </span>
    </div>
  );
}

function Card({
  title,
  subtitle,
  children,
}: {
  title: React.ReactNode;
  subtitle?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="card">
      <div className="card__head">
        <div>
          <div className="card__title">{title}</div>
          {subtitle && <div className="card__sub">{subtitle}</div>}
        </div>
      </div>
      {children}
    </div>
  );
}

function Spinner() {
  return (
    <div style={{ padding: "8px 0", display: "flex", alignItems: "center", gap: 10 }}>
      <div
        className="skel"
        style={{ width: 14, height: 14, borderRadius: "50%" }}
      />
      <div className="muted tiny">processing…</div>
    </div>
  );
}

function numField(obj: Record<string, unknown>, key: string): number | null {
  const v = obj[key];
  return typeof v === "number" ? v : null;
}

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}
