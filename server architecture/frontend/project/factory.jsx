/* global React, LineChart, BarChart, CarbonGauge, HeroKPI, KPI, genSeries */
const { useState: useStateF, useMemo: useMemoF, useEffect: useEffectF } = React;

function FactoryDashboard({ factory, range }) {
  const [tab, setTab] = useStateF('realtime');
  return (
    <div>
      <div className="tabs">
        <button className={`tabs__tab ${tab === 'realtime' ? 'is-active' : ''}`} onClick={() => setTab('realtime')}>
          Real-time &amp; KPIs
        </button>
        <button className={`tabs__tab ${tab === 'anomalies' ? 'is-active' : ''}`} onClick={() => setTab('anomalies')}>
          Anomalies &amp; Alerts <span className="tabs__count">{factory.alertCount}</span>
        </button>
        <button className={`tabs__tab ${tab === 'docs' ? 'is-active' : ''}`} onClick={() => setTab('docs')}>
          Data &amp; Documents
        </button>
      </div>

      {tab === 'realtime' && <FactoryRealtime range={range} factory={factory} />}
      {tab === 'anomalies' && <FactoryAnomalies />}
      {tab === 'docs' && <FactoryDocs />}
    </div>
  );
}

function FactoryRealtime({ range, factory }) {
  const labelsByRange = {
    Week: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    Month: ['W1', 'W2', 'W3', 'W4'],
    Year: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
  };
  const labels = labelsByRange[range];
  const energy = useMemoF(() => genSeries(11, labels.length, 420, 60, -30), [labels.length]);
  const energyHist = useMemoF(() => genSeries(12, labels.length, 460, 50), [labels.length]);
  const co2 = useMemoF(() => genSeries(13, labels.length, 168, 22, -10), [labels.length]);

  const [livePower, setLivePower] = useStateF(2487);
  useEffectF(() => {
    const id = setInterval(() => {
      setLivePower(p => Math.max(2200, Math.min(2780, p + (Math.random() - 0.5) * 40)));
    }, 1500);
    return () => clearInterval(id);
  }, []);

  return (
    <div>
      <div className="grid" style={{ gridTemplateColumns: '2fr 1fr 1fr' }}>
        <HeroKPI
          label="Total energy consumed"
          value={(factory.energy).toLocaleString()}
          unit="MWh"
          delta="5.4%"
          deltaDir="down" isGood
          foot={`${factory.devices} IoT meters · sampling 1s · publish 10s`}
          sub={`Live: ${Math.round(livePower).toLocaleString()} kW`}
        />
        <KPI
          icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M2 12c2-3 4-3 6 0s4 3 6 0"/><path d="M2 8c2-3 4-3 6 0s4 3 6 0"/></svg>}
          label="CO₂ emissions"
          value={factory.co2.toLocaleString()}
          unit="tCO₂e"
          delta="4.2%" deltaDir="down" isGood
          foot="incl. 1-month forecast"
        />
        <KPI
          icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M8 1v8M5 6l3 3 3-3"/></svg>}
          label="Self-generated"
          value="432"
          unit="kW"
          delta="18%" deltaDir="up" isGood
          foot="Solar 280 · Heat recovery 152"
        />
      </div>

      <div className="grid" style={{ gridTemplateColumns: '2fr 1fr', marginTop: 14 }}>
        <div className="card">
          <div className="card__head">
            <div>
              <div className="card__title">Energy consumption</div>
              <div className="card__sub">Real-time vs historical avg · {range.toLowerCase()}</div>
            </div>
            <span className="card__menu">{range} ▾</span>
          </div>
          <LineChart
            labels={labels}
            series={[
              { name: 'Current', data: energy, color: 'var(--ink)', fill: true },
              { name: 'Historical', data: energyHist, color: 'var(--accent)', dashed: true },
            ]}
          />
        </div>
        <div className="card">
          <div className="card__head">
            <div>
              <div className="card__title">Carbon vs cap</div>
              <div className="card__sub">Annual plafond</div>
            </div>
          </div>
          <CarbonGauge value={1820} limit={2400} />
        </div>
      </div>

      <div className="h-row">
        <div className="h-row__title">Top energy-consuming machines</div>
        <div className="h-row__hint">Last 24h</div>
      </div>
      <div className="card">
        <div className="rank">
          {[
            { n: 'Compressor C-204', loc: 'Line 2 · Compressed air', kwh: 4128, pct: 100 },
            { n: 'Furnace F-101', loc: 'Line 1 · Thermal', kwh: 3680, pct: 89 },
            { n: 'Chiller CH-301', loc: 'Utilities · Cooling', kwh: 2240, pct: 54, warn: true },
            { n: 'Extruder E-208', loc: 'Line 2 · Forming', kwh: 1840, pct: 45 },
            { n: 'Drying oven D-115', loc: 'Line 1 · Drying', kwh: 1402, pct: 34 },
          ].map((m, i) => (
            <div key={i} className="rank__row">
              <div>
                <div className="rank__name">
                  {m.n}
                  {m.warn && <span className="tag warn" style={{ marginLeft: 8 }}>+22%</span>}
                  <small>{m.loc}</small>
                </div>
                <div className="rank__bar"><span style={{ width: `${m.pct}%`, background: m.warn ? 'var(--warn)' : 'var(--ink)' }}></span></div>
              </div>
              <div className="rank__val">{m.kwh.toLocaleString()}<small>kWh</small></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FactoryAnomalies() {
  const [filter, setFilter] = useStateF('all');
  const alerts = [
    { sev: 'crit', t: '2026-05-02 13:38', src: 'Chiller CH-301', srcSub: 'Line 3 · Utilities', msg: 'Compressor current draw 22% above 7-day baseline.', sub: 'Isolation Forest 0.87 · Confidence 0.91' },
    { sev: 'crit', t: '2026-05-02 12:14', src: 'Furnace F-101', srcSub: 'Line 1 · Thermal', msg: 'Exhaust temperature exceeded threshold (412°C > 380°C) for 11 minutes.', sub: 'Possible heat recovery opportunity' },
    { sev: 'warn', t: '2026-05-02 11:42', src: 'Compressor C-204', srcSub: 'Line 2 · Compressed air', msg: 'Pressure drift +0.6 bar over 4h. Suggests filter or leak.', sub: 'Edge SVD reconstruction error 0.18' },
    { sev: 'warn', t: '2026-05-02 09:08', src: 'Drying oven D-115', srcSub: 'Line 1', msg: 'Energy/output ratio worsened by 8% vs Apr average.', sub: 'No upstream schedule change detected' },
    { sev: 'info', t: '2026-05-02 06:00', src: 'Solar array PV-A', srcSub: 'Roof North', msg: 'Self-generation 18% above forecast — sunny conditions extended.', sub: 'Surplus 142 kWh exported to grid' },
    { sev: 'info', t: '2026-05-01 22:14', src: 'BME280-12', srcSub: 'Line 2 control room', msg: 'Cross-sensor drift cleared — DS18B20-12 within ±0.4°C.', sub: 'Auto-resolved · Buffer drained 47 messages' },
  ];
  const filtered = filter === 'all' ? alerts : alerts.filter(a => a.sev === filter);
  const counts = { crit: alerts.filter(a => a.sev === 'crit').length, warn: alerts.filter(a => a.sev === 'warn').length };

  return (
    <div>
      <div className="grid gtc-3">
        <KPI label="Open alerts" value={alerts.length} unit="" delta="last 24h" deltaDir="flat" foot="Across all lines" icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M8 1l7 12H1z"/><path d="M8 6v3M8 11h.01"/></svg>} />
        <KPI label="Critical" value={counts.crit} unit="" delta="2 unresolved" deltaDir="up" isGood={false} foot="Mean ack 3.4 min" icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="8" cy="8" r="6.5"/><path d="M8 4v4M8 11h.01"/></svg>} />
        <KPI label="Auto-resolved" value="71" unit="%" delta="6 pp" deltaDir="up" isGood foot="Last 30 days" icon={<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 8l3 3 7-7"/></svg>} />
      </div>

      <div className="h-row">
        <div className="h-row__title">Alert timeline</div>
        <div className="seg" style={{ height: 36 }}>
          {[['all','All'],['crit','Critical'],['warn','Warning'],['info','Info']].map(([k,l]) => (
            <button key={k} className={`seg__btn ${filter===k?'is-active':''}`} onClick={() => setFilter(k)} style={{ height: 28 }}>{l}</button>
          ))}
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        {filtered.map((a, i) => (
          <div key={i} className="alert">
            <div className={`alert__sev ${a.sev}`}></div>
            <div className="alert__time">{a.t}</div>
            <div className="alert__src">
              {a.src}
              <small>{a.srcSub}</small>
            </div>
            <div className="alert__msg">
              <span className={`tag ${a.sev}`} style={{ marginRight: 8 }}>{a.sev}</span>
              {a.msg}
              <small>{a.sub}</small>
            </div>
            <div className="alert__open">›</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FactoryDocs() {
  const [over, setOver] = useStateF(false);
  const [selected, setSelected] = useStateF('STEG-2026-04.pdf');
  const docs = [
    { t: 'pdf', name: 'STEG-2026-04.pdf', kind: 'Electricity invoice', date: '2026-04-30', size: '284 KB', status: 'parsed' },
    { t: 'xls', name: 'production_apr_2026.xlsx', kind: 'Production output', date: '2026-05-01', size: '1.2 MB', status: 'parsed' },
    { t: 'pdf', name: 'gas_supplier_q1.pdf', kind: 'Natural gas (scanned)', date: '2026-04-12', size: '672 KB', status: 'ocr' },
    { t: 'csv', name: 'meter_export_2026-04.csv', kind: 'Submeter export', date: '2026-05-01', size: '4.8 MB', status: 'parsed' },
    { t: 'pdf', name: 'energy_audit_2025.pdf', kind: 'Annual audit report', date: '2025-12-18', size: '3.4 MB', status: 'parsed' },
  ];

  return (
    <div className="grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
      <div>
        <div className={`dz ${over ? 'is-over' : ''}`}
             onDragOver={(e) => { e.preventDefault(); setOver(true); }}
             onDragLeave={() => setOver(false)}
             onDrop={(e) => { e.preventDefault(); setOver(false); }}>
          <div className="dz__icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 3v12M7 8l5-5 5 5M3 17v3a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-3"/></svg>
          </div>
          <div className="dz__title">Drop documents to extract</div>
          <div className="dz__sub">PDF · Excel · CSV · scanned images. OCR + LLM extraction.</div>
        </div>

        <div className="h-row">
          <div className="h-row__title">Document library</div>
          <div className="muted tiny mono">{docs.length} files</div>
        </div>
        <div className="card" style={{ padding: 0 }}>
          {docs.map((d, i) => (
            <div key={i} className="docrow"
                 style={{ background: selected === d.name ? 'var(--paper)' : '' }}
                 onClick={() => setSelected(d.name)}>
              <div className={`ic ${d.t}`}>{d.t.toUpperCase()}</div>
              <div>
                <div className="name">{d.name}</div>
                <div className="meta">{d.kind}</div>
              </div>
              <div className="meta">{d.size}</div>
              <div className="meta">{d.date}</div>
              <span className={`tag ${d.status === 'parsed' ? 'ok' : 'info'}`}>
                {d.status === 'parsed' ? 'Parsed' : 'OCR…'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="insight">
          <h4>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="6.5"/><path d="M5 8h6M8 5v6"/></svg>
            AI extraction summary
          </h4>
          <div className="muted tiny mono" style={{ marginBottom: 8 }}>{selected}</div>
          <p>Tunisian Electricity & Gas invoice for April 2026. Site <strong>Sfax-A</strong>. Tariff M-T (medium voltage, time-of-use).</p>
          <div className="kv">
            <span>Energy <strong>438,210 kWh</strong></span>
            <span>Peak <strong>112,030 kWh</strong></span>
            <span>Off-peak <strong>326,180 kWh</strong></span>
            <span>Total <strong>€61,348</strong></span>
            <span>CO₂eq <strong>205.1 t</strong></span>
            <span>Factor <strong>0.468 kg/kWh</strong></span>
          </div>
          <p style={{ marginTop: 12 }}>
            <strong>Anomaly note:</strong> peak-hour usage <strong>+14% vs Mar-2026</strong>. Likely driver: Line 2 extruder runtime extended.
          </p>
        </div>

        <div style={{ height: 14 }}></div>

        <div className="card" style={{ padding: 0 }}>
          <div className="card__head" style={{ padding: '16px 18px 6px', margin: 0 }}>
            <div>
              <div className="card__title">Extracted line items</div>
              <div className="card__sub">All normalised to kWh</div>
            </div>
            <span className="tag ok">5 of 5</span>
          </div>
          <table className="tbl">
            <tbody>
              {[
                ['Energy — peak', '112,030 kWh', '€18,920'],
                ['Energy — off-peak', '326,180 kWh', '€32,128'],
                ['Demand charge', '410 kW', '€6,890'],
                ['Reactive power', '4,820 kvarh', '€812'],
                ['Carbon adjustment', '205.1 t · €86/t', '€2,598'],
              ].map((r, i) => (
                <tr key={i}>
                  <td style={{ paddingLeft: 18 }}>{r[0]}</td>
                  <td className="num">{r[1]}</td>
                  <td className="num" style={{ paddingRight: 18 }}>{r[2]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

window.FactoryDashboard = FactoryDashboard;
