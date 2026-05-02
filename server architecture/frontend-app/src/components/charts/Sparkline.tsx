// Inline mini line chart, no axes. Ported from frontend/project/components.jsx:21
// (Claude Design prototype). Used inside KPI cards to give a trend at-a-glance
// alongside the headline number.

export function Sparkline({
  data,
  color = "var(--ink)",
  fill = false,
  height = 36,
  width = 120,
}: {
  data: (number | null | undefined)[];
  color?: string;
  fill?: boolean;
  height?: number;
  width?: number;
}) {
  const cleaned = data.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!cleaned.length) return null;
  const min = Math.min(...cleaned);
  const max = Math.max(...cleaned);
  const rng = max - min || 1;
  const pts = cleaned.map<[number, number]>((v, i) => {
    const x = (i / Math.max(1, cleaned.length - 1)) * width;
    const y = height - ((v - min) / rng) * (height - 4) - 2;
    return [x, y];
  });
  const d = pts
    .map((p, i) =>
      i ? `L${p[0].toFixed(1)} ${p[1].toFixed(1)}` : `M${p[0].toFixed(1)} ${p[1].toFixed(1)}`,
    )
    .join(" ");
  const area = d + ` L${width} ${height} L0 ${height} Z`;
  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ display: "block" }}
    >
      {fill && <path d={area} fill={color} opacity="0.12" />}
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" />
    </svg>
  );
}
