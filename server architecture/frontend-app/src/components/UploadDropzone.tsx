import { useCallback } from "react";
import { useDropzone } from "react-dropzone";

const ACCEPTED = {
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/vnd.ms-excel": [".xls"],
};

export function UploadDropzone({
  onFile,
  disabled,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      const f = accepted[0];
      if (f) onFile(f);
    },
    [onFile],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    multiple: false,
    disabled,
  });

  return (
    <div
      {...getRootProps()}
      className={`dz ${isDragActive ? "is-over" : ""}`}
      style={{ cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1 }}
    >
      <input {...getInputProps()} />
      <div className="dz__icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M12 3v12M7 8l5-5 5 5M3 17v3a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-3" />
        </svg>
      </div>
      <div className="dz__title">
        {isDragActive ? "Drop the .xlsx here" : "Drop a BILAN file or click to browse"}
      </div>
      <div className="dz__sub">
        .xlsx · processed via the existing M6 BILAN ingestion pipeline
      </div>
    </div>
  );
}
