/* global React, LineChart, BarChart, HeroKPI, KPI, Sparkline, genSeries */
const { useMemo: useMemoH } = React;

function HoldingDashboard({ range, factories, onDrill }) {
  const labelsByRange = {
    Week: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    Month: ['W1', 'W2', 'W3', 'W4'],
    Year: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
  };
  const labels = labelsByRange[range];
  const energy = useMemoH(() => genSeries(101, labels.length, 1850, 240, -120), [labels.length]);
  const energyPrev = useMemoH(() => genSeries(202, labels.length, 1900, 240, 0), [labels.length]);
  const co2 = useMemoH(() => genSeries(303, labels.length, 720, 110, -60), [labels.length]);

  return (
    <div>
      {/* Hero row: 1/2 hero + 2 secondary */}
      <div className="grid" style={{ gridTemplateColumns: '2fr 1fr 1fr' }}>
        <HeroKPI
          label="Total energy consumed"
          value="14,820"
          unit="MWh"
          delta="6.3%"
          deltaDir="down" isGood
          foot="Across 5 factories · this month"
          sub="−982 MWh vs Apr"
        />
        <KPI
          icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M2 12c2-3 4-3 6 0s4 3 6 0"/><path d="M2 8c2-3 4-3 6 0s4 3 6 0"/></svg>}
          label="CO₂ emissions"
          value="5,872"
          unit="tCO₂e"
          delta="8.1%"
          deltaDir="down" isGood
          foot="Grid factor 0.468 · Tunisia"
        />
        <KPI
          icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M8 2v12M5 5h4.5a2 2 0 0 1 0 4H5"/><path d="M5 9h5a2 2 0 0 1 0 4H5"/></svg>}
          label="Energy cost"
          value="2.41"
          unit="M TND"
          delta="2.4%"
          deltaDir="up" isGood={false}
          foot="incl. carbon tax (€86/t)"
        />
      </div>

      <div className="grid gtc-3" style={{ marginTop: 14 }}>
        <KPI
          icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M8 1v8M5 6l3 3 3-3M2 14h12"/></svg>}
          label="Self-generated"
          value="18.4"
          unit="%"
          delta="3.2 pp"
          deltaDir="up" isGood
          foot="Solar 12.1% · Heat recovery 6.3%"
        />
        <KPI
          icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M2 12c0-3 2-5 6-5s6 2 6 5"/><circle cx="8" cy="4" r="2"/></svg>}
          label="Carbon intensity"
          value="0.396"
          unit="kgCO₂e/kWh"
          delta="4.2%"
          deltaDir="down" isGood
          foot="Per unit produced: 0.61"
        />
        <KPI
          icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="8" cy="8" r="6"/><path d="M8 4v4l3 2"/></svg>}
          label="Avoided emissions"
          value="412"
          unit="tCO₂e"
          delta="YTD"
          deltaDir="flat"
          foot="via heat recovery + solar"
        />
      </div>

      {/* Chart row: big trend + comparison */}
      <div className="grid" style={{ gridTemplateColumns: '2fr 1fr', marginTop: 14 }}>
        <div className="card">
          <div className="card__head">
            <div>
              <div className="card__title">Energy consumption</div>
              <div className="card__sub">MWh — current vs previous period</div>
            </div>
            <span className="card__menu">{range} ▾</span>
          </div>
          <LineChart
            labels={labels}
            series={[
              { name: 'Current', data: energy, color: 'var(--ink)', fill: true },
              { name: 'Previous', data: energyPrev, color: 'var(--accent)', dashed: true },
            ]}
          />
        </div>
        <div className="card">
          <div className="card__head">
            <div>
              <div className="card__title">CO₂ emissions</div>
              <div className="card__sub">tCO₂e — last 12 months</div>
            </div>
          </div>
          <LineChart
            labels={['J','F','M','A','M','J','J','A','S','O','N','D']}
            series={[{ name: 'CO₂', data: genSeries(404, 12, 580, 80, -120), color: 'var(--secondary)', fill: true }]}
            height={210}
          />
        </div>
      </div>

      {/* Factory comparison */}
      <div className="h-row">
        <div className="h-row__title">Factory comparison</div>
        <div className="h-row__hint">Click a row to drill down</div>
      </div>
      <div className="card" style={{ padding: 0 }}>
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ paddingLeft: 20 }}>Factory</th>
              <th>Status</th>
              <th className="right">Energy (MWh)</th>
              <th className="right">CO₂ (t)</th>
              <th className="right">Cost (€)</th>
              <th className="right" style={{ width: 180 }}>vs cap</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {factories.map(f => (
              <tr key={f.id} onClick={() => onDrill(f.id)}>
                <td style={{ paddingLeft: 20 }}>
                  <strong>{f.name}</strong>
                  <div className="muted tiny mono" style={{ marginTop: 2 }}>{f.id} · {f.country}</div>
                </td>
                <td>
                  <span className={`tag ${f.status === 'crit' ? 'crit' : f.status === 'warn' ? 'warn' : 'ok'}`}>
                    {f.status === 'crit' ? 'Critical' : f.status === 'warn' ? 'Warning' : 'Nominal'}
                  </span>
                </td>
                <td className="num">{f.energy.toLocaleString()}</td>
                <td className="num">{f.co2.toLocaleString()}</td>
                <td className="num">{f.cost.toLocaleString()}</td>
                <td className="right">
                  <div className="frow" style={{ justifyContent: 'flex-end', gap: 10 }}>
                    <div className={`bar ${f.cap > 0.9 ? 'crit' : f.cap > 0.6 ? 'warn' : 'ok'}`} style={{ width: 96 }}>
                      <span style={{ width: `${Math.min(f.cap, 1.1) * 100}%` }}></span>
                    </div>
                    <span className="num tiny" style={{ width: 28 }}>{Math.round(f.cap * 100)}%</span>
                  </div>
                </td>
                <td className="right muted" style={{ paddingRight: 20 }}>›</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

window.HoldingDashboard = HoldingDashboard;
