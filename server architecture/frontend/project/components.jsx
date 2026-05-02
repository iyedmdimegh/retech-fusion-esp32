/* global React */
const { useState, useEffect, useRef, useMemo } = React;

function seeded(seed) {
  let s = seed >>> 0;
  return () => {s = s * 1664525 + 1013904223 >>> 0;return s / 4294967296;};
}
function genSeries(seed, n, base, amp, trend = 0) {
  const r = seeded(seed);
  const out = [];
  for (let i = 0; i < n; i++) {
    const noise = (r() - 0.5) * amp;
    const wave = Math.sin(i / (n / 6)) * amp * 0.4;
    const tr = i / n * trend;
    out.push(Math.max(0, base + noise + wave + tr));
  }
  return out;
}

// Sparkline ─────────────────────────────────────────────────
function Sparkline({ data, color = 'var(--ink)', fill = false, height = 36, width = 120 }) {
  if (!data || !data.length) return null;
  const min = Math.min(...data),max = Math.max(...data);
  const rng = max - min || 1;
  const pts = data.map((v, i) => {
    const x = i / (data.length - 1) * width;
    const y = height - (v - min) / rng * (height - 4) - 2;
    return [x, y];
  });
  const d = pts.map((p, i) => i ? `L${p[0].toFixed(1)} ${p[1].toFixed(1)}` : `M${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const area = d + ` L${width} ${height} L0 ${height} Z`;
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ display: 'block' }}>
      {fill && <path d={area} fill={color} opacity="0.12" />}
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" />
    </svg>);

}

// Smooth line chart ─────────────────────────────────────────
function LineChart({ series, labels, height = 240, showGrid = true, smoothed = true }) {
  const ref = useRef(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    const ro = new ResizeObserver((es) => {for (const e of es) setW(e.contentRect.width);});
    if (ref.current) ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  const padL = 36,padR = 8,padT = 14,padB = 26;
  const allVals = series.flatMap((s) => s.data.filter((v) => v != null));
  const minRaw = Math.min(...allVals),maxRaw = Math.max(...allVals);
  const min = Math.floor(minRaw * 0.92),max = Math.ceil(maxRaw * 1.08);
  const rng = max - min || 1;
  const n = labels.length;
  const xAt = (i) => padL + i / (n - 1) * (w - padL - padR);
  const yAt = (v) => padT + (1 - (v - min) / rng) * (height - padT - padB);
  const ticks = 4;
  const tickVals = Array.from({ length: ticks + 1 }, (_, i) => min + rng * i / ticks);

  const smoothPath = (data) => {
    const pts = data.map((v, i) => v == null ? null : [xAt(i), yAt(v)]).filter(Boolean);
    if (!pts.length) return '';
    if (!smoothed) return pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
    let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
    for (let i = 1; i < pts.length; i++) {
      const p0 = pts[i - 1],p1 = pts[i];
      const cx = (p0[0] + p1[0]) / 2;
      d += ` C${cx.toFixed(1)} ${p0[1].toFixed(1)} ${cx.toFixed(1)} ${p1[1].toFixed(1)} ${p1[0].toFixed(1)} ${p1[1].toFixed(1)}`;
    }
    return d;
  };
  const areaPath = (data) => {
    const sp = smoothPath(data);
    const last = data.length - 1;
    return sp + ` L${xAt(last)} ${height - padB} L${xAt(0)} ${height - padB} Z`;
  };

  return (
    <div ref={ref} className="chart-wrap" style={{ height }}>
      <svg width={w} height={height}>
        {showGrid && tickVals.map((v, i) =>
        <g key={i}>
            <line className="grid-line" x1={padL} x2={w - padR} y1={yAt(v)} y2={yAt(v)} />
            <text className="svg-text" x={padL - 8} y={yAt(v) + 3} textAnchor="end">{Math.round(v).toLocaleString()}</text>
          </g>
        )}
        {labels.map((lab, i) => {
          if (n > 12 && i % Math.ceil(n / 8) !== 0 && i !== n - 1) return null;
          return <text key={i} className="svg-text" x={xAt(i)} y={height - padB + 14} textAnchor="middle">{lab}</text>;
        })}
        {series.map((s, idx) =>
        <g key={idx}>
            {s.fill && <path d={areaPath(s.data)} fill={s.color} opacity="0.10" />}
            <path d={smoothPath(s.data)} fill="none" stroke={s.color} strokeWidth={s.dashed ? 1.6 : 2}
          strokeDasharray={s.dashed ? '5 4' : null} strokeLinecap="round" />
          </g>
        )}
      </svg>
    </div>);

}

// Bar chart (rounded) ───────────────────────────────────────
function BarChart({ series, labels, height = 220 }) {
  const ref = useRef(null);
  const [w, setW] = useState(640);
  useEffect(() => {
    const ro = new ResizeObserver((es) => {for (const e of es) setW(e.contentRect.width);});
    if (ref.current) ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  const padL = 36,padR = 8,padT = 14,padB = 26;
  const allVals = series.flatMap((s) => s.data);
  const max = Math.ceil(Math.max(...allVals) * 1.1);
  const groups = labels.length;
  const groupW = (w - padL - padR) / groups;
  const barW = (groupW - 16) / series.length;
  const yAt = (v) => padT + (1 - v / max) * (height - padT - padB);
  const ticks = 4;
  const tickVals = Array.from({ length: ticks + 1 }, (_, i) => max * i / ticks);
  return (
    <div ref={ref} className="chart-wrap" style={{ height }}>
      <svg width={w} height={height}>
        {tickVals.map((v, i) =>
        <g key={i}>
            <line className="grid-line" x1={padL} x2={w - padR} y1={yAt(v)} y2={yAt(v)} />
            <text className="svg-text" x={padL - 8} y={yAt(v) + 3} textAnchor="end">{Math.round(v)}</text>
          </g>
        )}
        {labels.map((lab, i) =>
        <text key={i} className="svg-text" x={padL + groupW * (i + 0.5)} y={height - padB + 14} textAnchor="middle">{lab}</text>
        )}
        {series.map((s, si) =>
        <g key={si}>
            {s.data.map((v, i) => {
            const x = padL + groupW * i + 8 + si * barW;
            const y = yAt(v);
            const h = Math.max(2, height - padB - y);
            return <rect key={i} x={x} y={y} width={barW - 4} height={h} rx="3" fill={s.color} />;
          })}
          </g>
        )}
      </svg>
    </div>);

}

// Sidebar ────────────────────────────────────────────────────
function Sidebar({ view, setView, factory, setFactory, factories }) {
  return (
    <aside className="sb">
      <div className="sb__brand"></div>

      <div className="sb__group">Menu</div>
      <div className="sb__nav">
        <button className={`sb__item ${view === 'holding' ? 'is-active' : ''}`} onClick={() => setView('holding')}>
          <svg className="glyph" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="2" width="5" height="5" rx="1" /><rect x="9" y="2" width="5" height="5" rx="1" /><rect x="2" y="9" width="5" height="5" rx="1" /><rect x="9" y="9" width="5" height="5" rx="1" /></svg>
          Dashboard
        </button>
        <button className="sb__item">
          <svg className="glyph" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 2h7l3 3v9H3z" /><path d="M10 2v3h3" /></svg>
          Reports
        </button>
        <button className="sb__item">
          <svg className="glyph" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="6" /><path d="M8 4v4l3 2" /></svg>
          Schedules
        </button>
      </div>

      <div className="sb__group">Factories</div>
      <div className="sb__factories">
        {factories.map((f) =>
        <button
          key={f.id}
          className={`sb__factory ${view === 'factory' && factory === f.id ? 'is-active' : ''}`}
          onClick={() => {setView('factory');setFactory(f.id);}}>
          
            <div>
              {f.name}
              <small>{f.id}</small>
            </div>
            <span className="dot" style={{ background: f.status === 'crit' ? 'var(--crit)' : f.status === 'warn' ? 'var(--warn)' : 'var(--ok)' }}></span>
          </button>
        )}
      </div>

      <div className="sb__group">Tools</div>
      <div className="sb__nav">
        <button className="sb__item">
          <svg className="glyph" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="2.5" /><path d="M8 1v2M8 13v2M1 8h2M13 8h2" /></svg>
          Settings
        </button>
        <button className="sb__item">
          <svg className="glyph" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="6.5" /><path d="M8 4v4M8 11h.01" /></svg>
          Help
        </button>
      </div>

      <div className="sb__promo">
        <div className="icp">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 1l5 3v4c0 4-5 7-5 7s-5-3-5-7V4z" /></svg>
        </div>
        <h4>Carbon report</h4>
        <p>Generate the monthly audit-ready report.</p>
        <button>Generate</button>
      </div>
    </aside>);

}

// Top bar ────────────────────────────────────────────────────
function TopBar({ title, subtitle, range, setRange, alertCount }) {
  return (
    <div className="top">
      <div>
        <h1 className="top__h1">{title}</h1>
        <div className="top__sub">{subtitle}</div>
      </div>
      <div className="top__spacer"></div>

      <div className="live"><span className="pulse"></span> LIVE · 13:42 UTC</div>

      <div className="seg">
        {['Week', 'Month', 'Year'].map((r) =>
        <button key={r} className={`seg__btn ${range === r ? 'is-active' : ''}`} onClick={() => setRange(r)}>{r}</button>
        )}
      </div>

      <button className="iconbtn" title="Search">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="7" cy="7" r="4.5" /><path d="M11 11l3 3" /></svg>
      </button>
      <button className="iconbtn" title="Notifications">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 6a4 4 0 0 1 8 0c0 4 2 5 2 5H2s2-1 2-5" /><path d="M7 13a1 1 0 0 0 2 0" /></svg>
        {alertCount > 0 && <span className="badge"></span>}
      </button>
    </div>);

}

// Hero KPI ───────────────────────────────────────────────────
function HeroKPI({ label, value, unit, delta, deltaDir = 'down', isGood = true, foot, sub }) {
  const cls = deltaDir === 'flat' ? 'flat' : isGood ? 'down' : 'up';
  const arrow = deltaDir === 'up' ? '↑' : deltaDir === 'down' ? '↓' : '·';
  return (
    <div className="hero">
      <div className="hero__top">
        <div className="hero__icon">
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M9 1L3 9h4l-1 6 6-8H8z" /></svg>
        </div>
        <span className={`pill ${cls}`}>{arrow} {delta}</span>
      </div>
      <div>
        <div className="hero__label">{label}</div>
        <div style={{ marginTop: 8 }}>
          <span className="hero__val num">{value}</span>
          <span className="hero__unit">{unit}</span>
        </div>
      </div>
      <div className="hero__foot">
        <span>{foot}</span>
        {sub && <strong>{sub}</strong>}
      </div>
    </div>);

}

// Secondary KPI ─────────────────────────────────────────────
function KPI({ icon, label, value, unit, delta, deltaDir = 'down', isGood = true, foot }) {
  const cls = deltaDir === 'flat' ? 'flat' : isGood ? 'down' : 'up';
  const arrow = deltaDir === 'up' ? '↑' : deltaDir === 'down' ? '↓' : '·';
  return (
    <div className="kpi">
      <div className="kpi__top">
        <div className="kpi__icon">{icon}</div>
        <span className={`pill ${cls}`}>{arrow} {delta}</span>
      </div>
      <div className="kpi__label">{label}</div>
      <div className="kpi__row">
        <span className="kpi__val num">{value}</span>
        {unit && <span className="kpi__unit">{unit}</span>}
      </div>
      {foot && <div className="kpi__foot">{foot}</div>}
    </div>);

}

// Carbon gauge — soft semicircle ────────────────────────────
function CarbonGauge({ value, limit }) {
  const pct = Math.min(value / limit, 1.1);
  const cx = 110,cy = 110,r = 84,sw = 16;
  const arc = (start, end, color, op = 1) => {
    const sa = start * Math.PI / 180;
    const ea = end * Math.PI / 180;
    const x1 = cx + r * Math.cos(sa);
    const y1 = cy + r * Math.sin(sa);
    const x2 = cx + r * Math.cos(ea);
    const y2 = cy + r * Math.sin(ea);
    const large = end - start > 180 ? 1 : 0;
    return <path d={`M${x1} ${y1} A${r} ${r} 0 ${large} 1 ${x2} ${y2}`} stroke={color} strokeOpacity={op} strokeWidth={sw} fill="none" strokeLinecap="round" />;
  };
  const fillEnd = 180 + pct * 180;
  const zone = pct < 0.6 ? 'ok' : pct < 0.9 ? 'warn' : 'crit';
  const color = zone === 'ok' ? 'var(--ok)' : zone === 'warn' ? 'var(--warn)' : 'var(--crit)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 18 }}>
      <svg width="220" height="135" viewBox="0 0 220 135">
        {arc(180, 360, 'var(--paper)')}
        {arc(180, fillEnd, color)}
      </svg>
      <div style={{ flex: 1 }}>
        <div className="display num" style={{ fontSize: 38, lineHeight: 1, color }}>
          {Math.round(pct * 100)}<span style={{ fontSize: 20, color: 'var(--ink-mute)' }}>%</span>
        </div>
        <div className="muted tiny" style={{ marginTop: 6 }}>{value.toLocaleString()} of {limit.toLocaleString()} tCO₂e cap</div>
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="tag ok">Safe under 60%</span>
          <span className="tag warn">Warn 60–90%</span>
          <span className="tag crit">Exceeded over 90%</span>
        </div>
      </div>
    </div>);

}

Object.assign(window, {
  seeded, genSeries,
  Sparkline, LineChart, BarChart, CarbonGauge,
  Sidebar, TopBar, HeroKPI, KPI
});