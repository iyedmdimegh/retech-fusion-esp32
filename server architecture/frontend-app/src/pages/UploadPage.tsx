import { useState } from "react";
import { Link } from "react-router-dom";
import { UploadDropzone } from "../components/UploadDropzone";
import { JobProgress } from "../components/JobProgress";
import { useRecentJobs, useUploadBilan } from "../lib/api/queries";

export function UploadPage() {
  const upload = useUploadBilan();
  const recent = useRecentJobs({ type: "bilan", limit: 5 });
  const [duplicateNote, setDuplicateNote] = useState<{
    job_id: string;
    parsed_at?: string;
  } | null>(null);

  const handleFile = (file: File) => {
    setDuplicateNote(null);
    upload.mutate(file, {
      onSuccess: (resp) => {
        if (resp.deduped) {
          setDuplicateNote({ job_id: resp.job_id });
        }
      },
    });
  };

  return (
    <div>
      <div className="h-row">
        <div className="h-row__title">Upload BILAN report</div>
        <div className="h-row__hint">Excel · processed by the M6 ingestion pipeline</div>
      </div>

      <UploadDropzone onFile={handleFile} disabled={upload.isPending} />

      {upload.isPending && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="card__head">
            <div>
              <div className="card__title">Uploading…</div>
              <div className="card__sub">posting to /api/ingest/upload</div>
            </div>
          </div>
        </div>
      )}

      {upload.isError && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="card__head">
            <div>
              <div className="card__title" style={{ color: "var(--crit)" }}>
                Upload failed
              </div>
              <div className="card__sub">{String(upload.error)}</div>
            </div>
          </div>
        </div>
      )}

      {duplicateNote && (
        <div className="insight" style={{ marginTop: 14 }}>
          <h4>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="8" cy="8" r="6.5" />
              <path d="M5 8h6M8 5v6" />
            </svg>
            Already ingested
          </h4>
          <p>
            This file has already been processed. No new rows inserted. The previous
            job is{" "}
            <span className="mono">{duplicateNote.job_id.slice(0, 8)}…</span>.
          </p>
          <Link to="/plant-1/energy" className="btn" style={{ marginTop: 10 }}>
            View its analytics →
          </Link>
        </div>
      )}

      {upload.isSuccess && !duplicateNote && upload.data?.job_id && (
        <div style={{ marginTop: 14 }}>
          <JobProgress jobId={upload.data.job_id} />
        </div>
      )}

      <div className="h-row">
        <div className="h-row__title">Recent BILAN jobs</div>
        <div className="h-row__hint">live from /api/jobs?type=bilan</div>
      </div>
      <div className="card" style={{ padding: 0 }}>
        {recent.isLoading && (
          <div style={{ padding: 14 }}>
            <div className="skel" style={{ height: 18, marginBottom: 8 }} />
            <div className="skel" style={{ height: 18 }} />
          </div>
        )}
        {recent.data && recent.data.length === 0 && (
          <div style={{ padding: 14 }} className="muted tiny">
            no jobs yet
          </div>
        )}
        {recent.data && recent.data.length > 0 && (
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ paddingLeft: 18 }}>Job</th>
                <th>Status</th>
                <th>Source</th>
                <th className="right" style={{ paddingRight: 18 }}>
                  Created
                </th>
              </tr>
            </thead>
            <tbody>
              {recent.data.map((j) => (
                <tr key={j.job_id}>
                  <td style={{ paddingLeft: 18 }} className="mono">
                    {j.job_id.slice(0, 8)}…
                  </td>
                  <td>
                    <span
                      className={`tag ${
                        j.status === "success"
                          ? "ok"
                          : j.status === "partial_success"
                          ? "warn"
                          : j.status === "failed"
                          ? "crit"
                          : "info"
                      }`}
                    >
                      {j.status}
                    </span>
                  </td>
                  <td className="muted tiny mono">{j.source_path ?? "—"}</td>
                  <td className="num" style={{ paddingRight: 18 }}>
                    {j.created_at ? new Date(j.created_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
