// Smooth-Bézier line chart, ported from the prototype's components.jsx
// (frontend/project/components.jsx:41-101). Hand-rolled SVG, zero deps.

import { useEffect, useRef, useState } from "react";

export interface LineSeries {
  name: string;
  data: (number | null)[];
  color: string;
  fill?: boolean;
  dashed?: boolean;
}

export function LineChart({
  series,
  labels,
  height = 240,
  showGrid = true,
  smoothed = true,
}: {
  series: LineSeries[];
  labels: string[];
  height?: number;
  showGrid?: boolean;
  smoothed?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    const ro = new ResizeObserver((es) => {
      for (const e of es) setW(e.contentRect.width);
    });
    if (ref.current) ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  const padL = 44,
    padR = 8,
    padT = 14,
    padB = 26;
  const allVals = series.flatMap((s) =>
    s.data.filter((v): v is number => v != null),
  );
  if (allVals.length === 0 || labels.length === 0) {
    return (
      <div ref={ref} className="chart-wrap" style={{ height }}>
        <div className="muted tiny" style={{ padding: 12 }}>
          no data
        </div>
      </div>
    );
  }
  const minRaw = Math.min(...allVals);
  const maxRaw = Math.max(...allVals);
  const min = Math.floor(minRaw * 0.92);
  const max = Math.ceil(maxRaw * 1.08);
  const rng = max - min || 1;
  const n = labels.length;
  const xAt = (i: number) => padL + (i / Math.max(1, n - 1)) * (w - padL - padR);
  const yAt = (v: number) => padT + (1 - (v - min) / rng) * (height - padT - padB);
  const ticks = 4;
  const tickVals = Array.from({ length: ticks + 1 }, (_, i) => min + (rng * i) / ticks);

  const smoothPath = (data: (number | null)[]) => {
    const pts: [number, number][] = data
      .map<[number, number] | null>((v, i) => (v == null ? null : [xAt(i), yAt(v)]))
      .filter((p): p is [number, number] => !!p);
    if (!pts.length) return "";
    if (!smoothed)
      return pts
        .map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`)
        .join(" ");
    let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
    for (let i = 1; i < pts.length; i++) {
      const p0 = pts[i - 1];
      const p1 = pts[i];
      const cx = (p0[0] + p1[0]) / 2;
      d += ` C${cx.toFixed(1)} ${p0[1].toFixed(1)} ${cx.toFixed(1)} ${p1[1].toFixed(1)} ${p1[0].toFixed(1)} ${p1[1].toFixed(1)}`;
    }
    return d;
  };
  const areaPath = (data: (number | null)[]) => {
    const sp = smoothPath(data);
    if (!sp) return "";
    const last = data.length - 1;
    return sp + ` L${xAt(last)} ${height - padB} L${xAt(0)} ${height - padB} Z`;
  };

  return (
    <div ref={ref} className="chart-wrap" style={{ height }}>
      <svg width={w} height={height}>
        {showGrid &&
          tickVals.map((v, i) => (
            <g key={i}>
              <line
                className="grid-line"
                x1={padL}
                x2={w - padR}
                y1={yAt(v)}
                y2={yAt(v)}
              />
              <text
                className="svg-text"
                x={padL - 8}
                y={yAt(v) + 3}
                textAnchor="end"
              >
                {Math.round(v).toLocaleString()}
              </text>
            </g>
          ))}
        {labels.map((lab, i) => {
          if (n > 12 && i % Math.ceil(n / 8) !== 0 && i !== n - 1) return null;
          return (
            <text
              key={i}
              className="svg-text"
              x={xAt(i)}
              y={height - padB + 14}
              textAnchor="middle"
            >
              {lab}
            </text>
          );
        })}
        {series.map((s, idx) => (
          <g key={idx}>
            {s.fill && <path d={areaPath(s.data)} fill={s.color} opacity="0.10" />}
            <path
              d={smoothPath(s.data)}
              fill="none"
              stroke={s.color}
              strokeWidth={s.dashed ? 1.6 : 2}
              strokeDasharray={s.dashed ? "5 4" : undefined}
              strokeLinecap="round"
            />
          </g>
        ))}
      </svg>
    </div>
  );
}
