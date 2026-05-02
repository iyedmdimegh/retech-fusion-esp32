// Semicircle "vs cap" gauge. Ported from frontend/project/components.jsx:288.
// Shows current CO₂ value against a cap as a filled arc; tints the fill ok/warn/crit
// based on how close to the cap we are. Used on the Co₂ page to make
// "are we on track or over?" readable in one glance.

export function CarbonGauge({
  value,
  limit,
  unit = "tCO₂e",
}: {
  value: number;
  limit: number;
  unit?: string;
}) {
  const safeLimit = Math.max(1, limit);
  const pct = Math.min(value / safeLimit, 1.1);
  const cx = 110,
    cy = 110,
    r = 84,
    sw = 16;

  const arc = (start: number, end: number, color: string, op = 1) => {
    const sa = (start * Math.PI) / 180;
    const ea = (end * Math.PI) / 180;
    const x1 = cx + r * Math.cos(sa);
    const y1 = cy + r * Math.sin(sa);
    const x2 = cx + r * Math.cos(ea);
    const y2 = cy + r * Math.sin(ea);
    const large = end - start > 180 ? 1 : 0;
    return (
      <path
        d={`M${x1} ${y1} A${r} ${r} 0 ${large} 1 ${x2} ${y2}`}
        stroke={color}
        strokeOpacity={op}
        strokeWidth={sw}
        fill="none"
        strokeLinecap="round"
      />
    );
  };

  const fillEnd = 180 + pct * 180;
  const zone = pct < 0.6 ? "ok" : pct < 0.9 ? "warn" : "crit";
  const color =
    zone === "ok" ? "var(--ok)" : zone === "warn" ? "var(--warn)" : "var(--crit)";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 18,
      }}
    >
      <svg width="220" height="135" viewBox="0 0 220 135">
        {arc(180, 360, "var(--paper)")}
        {arc(180, fillEnd, color)}
      </svg>
      <div style={{ flex: 1 }}>
        <div
          className="display num"
          style={{ fontSize: 38, lineHeight: 1, color }}
        >
          {Math.round(pct * 100)}
          <span style={{ fontSize: 20, color: "var(--ink-mute)" }}>%</span>
        </div>
        <div className="muted tiny" style={{ marginTop: 6 }}>
          {fmt(value)} of {fmt(limit)} {unit} cap
        </div>
        <div
          style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}
        >
          <span className="tag ok">Safe under 60%</span>
          <span className="tag warn">Warn 60–90%</span>
          <span className="tag crit">Exceeded over 90%</span>
        </div>
      </div>
    </div>
  );
}

function fmt(n: number): string {
  if (Math.abs(n) >= 1000) return Math.round(n).toLocaleString();
  return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
}
