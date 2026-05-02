// "Top N" list with a horizontal bar per row. Ported from
// frontend/project/factory.jsx:108–130 (the "Top energy-consuming machines"
// section in the Claude Design prototype). The .rank* CSS classes are
// already in styles.css.
//
// On the prototype this was hardcoded ("Compressor C-204", "Furnace F-101",
// ...). Here it's wired to /api/bilan/top-metrics, which ranks the cumulative
// meters in the YAML by total consumption (max - min, filtering bad rows).

export interface RankListItem {
  name: string;          // headline label
  sub?: string;          // small label below name
  value: number;         // numeric value (used for both the number + the bar pct)
  unit: string;          // e.g. "kWh", "Nm³"
  warn?: boolean;        // tints the bar amber + adds a small tag
  warnTag?: string;      // text inside the warn tag
}

export function RankList({
  items,
  loading,
  emptyText = "no data",
}: {
  items: RankListItem[];
  loading?: boolean;
  emptyText?: string;
}) {
  if (loading) {
    return (
      <div className="rank">
        {[0, 1, 2].map((i) => (
          <div key={i} className="rank__row">
            <div>
              <div className="skel" style={{ height: 16, width: "60%", marginBottom: 6 }} />
              <div className="skel" style={{ height: 5, width: "100%", marginTop: 8 }} />
            </div>
            <div className="skel" style={{ width: 60, height: 18 }} />
          </div>
        ))}
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="muted tiny" style={{ padding: 8 }}>
        {emptyText}
      </div>
    );
  }

  const peak = Math.max(1, ...items.map((i) => Math.abs(i.value)));

  return (
    <div className="rank">
      {items.map((m, idx) => {
        const pct = (Math.abs(m.value) / peak) * 100;
        return (
          <div key={`${idx}-${m.name}`} className="rank__row">
            <div>
              <div className="rank__name">
                {m.name}
                {m.warn && (
                  <span className="tag warn" style={{ marginLeft: 8 }}>
                    {m.warnTag ?? "warn"}
                  </span>
                )}
                {m.sub && <small>{m.sub}</small>}
              </div>
              <div className="rank__bar">
                <span
                  style={{
                    width: `${pct}%`,
                    background: m.warn ? "var(--warn)" : "var(--ink)",
                  }}
                />
              </div>
            </div>
            <div className="rank__val">
              {fmt(m.value)}
              <small>{m.unit}</small>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function fmt(n: number): string {
  if (Math.abs(n) >= 1000) return Math.round(n).toLocaleString();
  return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
}
