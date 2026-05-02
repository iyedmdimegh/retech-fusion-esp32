// Diverging bar chart for signed values like grid_net_kwh.
// Positive bars above the zero baseline (red = importing, bad);
// negative bars below (green = exporting, cogen benefit).
//
// Built on the same SVG primitives as LineChart so the look is consistent.

import { useEffect, useRef, useState } from "react";

export function SignedBarChart({
  data,
  labels,
  height = 220,
  posColor = "var(--crit)",
  negColor = "var(--ok)",
}: {
  data: number[];
  labels: string[];
  height?: number;
  posColor?: string;
  negColor?: string;
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
  const maxAbs = Math.max(1, ...data.map((v) => Math.abs(v)));
  const max = Math.ceil(maxAbs * 1.1);
  const min = -max;
  const rng = max - min;
  const n = labels.length;
  const groupW = (w - padL - padR) / n;
  const barW = Math.max(1, groupW * 0.7);
  const yAt = (v: number) => padT + (1 - (v - min) / rng) * (height - padT - padB);
  const y0 = yAt(0);

  const ticks = 4;
  const tickVals = Array.from({ length: ticks + 1 }, (_, i) => min + (rng * i) / ticks);

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
              style={
                Math.abs(v) < 1e-6
                  ? { stroke: "var(--ink-mute)", strokeWidth: 1 }
                  : undefined
              }
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
          if (v === 0) return null;
          if (v > 0) {
            const y = yAt(v);
            return (
              <rect
                key={i}
                x={x}
                y={y}
                width={barW}
                height={Math.max(1, y0 - y)}
                rx="1.5"
                fill={posColor}
              />
            );
          } else {
            const y = y0;
            return (
              <rect
                key={i}
                x={x}
                y={y}
                width={barW}
                height={Math.max(1, yAt(v) - y0)}
                rx="1.5"
                fill={negColor}
              />
            );
          }
        })}
      </svg>
    </div>
  );
}
