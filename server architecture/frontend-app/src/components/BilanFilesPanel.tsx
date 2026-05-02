// M14 proof-of-life panel: lists ingested BILAN files from the live backend.
// Replaces the prototype's hardcoded "production_apr_2026.xlsx" row.

import { useBilanFiles } from "../lib/api/queries";

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

function fmtNum(n?: number | null): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "success"
      ? "ok"
      : status === "partial_success"
      ? "warn"
      : status === "failed"
      ? "crit"
      : "info";
  return <span className={`tag ${tone}`}>{status}</span>;
}

export function BilanFilesPanel() {
  const { data, isLoading, isError, error } = useBilanFiles(50);

  if (isLoading) {
    return (
      <div className="card">
        <div className="card__head">
          <div>
            <div className="card__title">BILAN files</div>
            <div className="card__sub">Loading from /api/bilan/files…</div>
          </div>
        </div>
        <div className="skel" style={{ height: 18, marginBottom: 8 }} />
        <div className="skel" style={{ height: 18, marginBottom: 8 }} />
        <div className="skel" style={{ height: 18 }} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="card">
        <div className="card__head">
          <div>
            <div className="card__title">BILAN files</div>
            <div className="card__sub" style={{ color: "var(--crit)" }}>
              fetch failed
            </div>
          </div>
        </div>
        <pre style={{ fontSize: 11, color: "var(--ink-mute)" }}>
          {String(error)}
        </pre>
      </div>
    );
  }

  const files = data ?? [];

  return (
    <div className="card" style={{ padding: 0 }}>
      <div
        className="card__head"
        style={{ padding: "16px 18px 6px", margin: 0 }}
      >
        <div>
          <div className="card__title">BILAN files</div>
          <div className="card__sub">
            {files.length === 0
              ? "no files ingested yet — drop a .xlsx into inbox/xlsx/"
              : `${files.length} file(s) ingested · live from /api/bilan/files`}
          </div>
        </div>
      </div>
      {files.length > 0 && (
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ paddingLeft: 18 }}>Filename</th>
              <th>Status</th>
              <th className="right">Date range</th>
              <th className="right">Rows in</th>
              <th className="right">Rows dropped</th>
              <th className="right" style={{ paddingRight: 18 }}>
                Parsed at
              </th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.file_id}>
                <td style={{ paddingLeft: 18 }}>
                  <strong>{f.filename}</strong>
                  <div
                    className="muted tiny mono"
                    style={{ marginTop: 2 }}
                  >
                    {f.file_hash.slice(0, 16)}…
                  </div>
                </td>
                <td>
                  <StatusBadge status={f.status} />
                </td>
                <td className="num">
                  {fmtDate(f.date_range_start)} → {fmtDate(f.date_range_end)}
                </td>
                <td className="num">{fmtNum(f.rows_inserted)}</td>
                <td className="num">{fmtNum(f.rows_dropped)}</td>
                <td className="num" style={{ paddingRight: 18 }}>
                  {fmtDate(f.parsed_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
