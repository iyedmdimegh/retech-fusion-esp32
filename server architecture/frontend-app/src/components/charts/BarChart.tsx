// Single-series rounded bar chart for non-negative quantities (gas, kWh).

import { useEffect, useRef, useState } from "react";

export function BarChart({
  data,
  labels,
  color = "var(--ink)",
  height = 220,
}: {
  data: number[];
  labels: string[];
  color?: string;
  height?: number;
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

  if (data.length === 0) {
    return (
      <div ref={ref} className="chart-wrap" style={{ height }}>
        <div className="muted tiny" style={{ padding: 12 }}>
          no data
        </div>
      </div>
    );
  }

  const padL = 44,
    padR = 8,
    padT = 14,
    padB = 26;
  const maxRaw = Math.max(0, ...data);
  const max = Math.ceil(maxRaw * 1.1) || 1;
  const n = labels.length;
  const groupW = (w - padL - padR) / n;
  const barW = Math.max(1, groupW * 0.7);
  const yAt = (v: number) => padT + (1 - v / max) * (height - padT - padB);
  const ticks = 4;
  const tickVals = Array.from({ length: ticks + 1 }, (_, i) => (max * i) / ticks);

  return (
    <div ref={ref} className="chart-wrap" style={{ height }}>
      <svg width={w} height={height}>
        {tickVals.map((v, i) => (
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
              x={padL + groupW * (i + 0.5)}
              y={height - padB + 14}
              textAnchor="middle"
            >
              {lab}
            </text>
          );
        })}
        {data.map((v, i) => {
          const x = padL + groupW * i + (groupW - barW) / 2;
          const y = yAt(v);
          const h = Math.max(0.5, height - padB - y);
          return <rect key={i} x={x} y={y} width={barW} height={h} rx="2" fill={color} />;
        })}
      </svg>
    </div>
  );
}
