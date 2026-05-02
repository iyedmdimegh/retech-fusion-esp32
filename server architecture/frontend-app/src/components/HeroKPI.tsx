// Big dark "headline" KPI card. Visually distinct from the regular KPI card —
// used for the one most-important number on a page. Ported from
// frontend/project/components.jsx:241 (.hero CSS class is already in styles.css).

import type { ReactNode } from "react";

export function HeroKPI({
  label,
  value,
  unit,
  delta,
  deltaDir = "flat",
  isGood = true,
  foot,
  sub,
  icon,
  loading,
}: {
  label: string;
  value: ReactNode;
  unit: string;
  delta?: string;
  deltaDir?: "up" | "down" | "flat";
  isGood?: boolean;
  foot?: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  loading?: boolean;
}) {
  const cls = deltaDir === "flat" ? "flat" : isGood ? "down" : "up";
  const arrow = deltaDir === "up" ? "↑" : deltaDir === "down" ? "↓" : "·";
  return (
    <div className="hero">
      <div className="hero__top">
        <div className="hero__icon">
          {icon ?? (
            <svg
              width="18"
              height="18"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
            >
              <path d="M9 1L3 9h4l-1 6 6-8H8z" />
            </svg>
          )}
        </div>
        {delta && (
          <span className={`pill ${cls}`}>
            {arrow} {delta}
          </span>
        )}
      </div>
      <div>
        <div className="hero__label">{label}</div>
        <div style={{ marginTop: 8 }}>
          {loading ? (
            <div
              className="skel"
              style={{ width: 140, height: 48, borderRadius: 4 }}
            />
          ) : (
            <>
              <span className="hero__val num">{value}</span>
              <span className="hero__unit">{unit}</span>
            </>
          )}
        </div>
      </div>
      {(foot || sub) && (
        <div className="hero__foot">
          <span>{foot}</span>
          {sub && <strong>{sub}</strong>}
        </div>
      )}
    </div>
  );
}
