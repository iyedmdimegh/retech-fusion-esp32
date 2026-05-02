/* global React, ReactDOM, Sidebar, TopBar, HoldingDashboard, FactoryDashboard, Chatbot, TweaksPanel, useTweaks, TweakSection, TweakColor, TweakRadio */

const { useState, useEffect } = React;

const FACTORIES = [
  { id: 'TN-SFA', name: 'Sfax-A',    country: 'Tunisia', status: 'warn', energy: 4820, co2: 1820, cost: 678000, cap: 0.76, devices: 142, alertCount: 6 },
  { id: 'TN-TUN', name: 'Tunis-B',   country: 'Tunisia', status: 'crit', energy: 3940, co2: 1612, cost: 552000, cap: 0.93, devices: 98,  alertCount: 4 },
  { id: 'TN-BIZ', name: 'Bizerte-C', country: 'Tunisia', status: 'ok',   energy: 2480, co2:  982, cost: 348000, cap: 0.42, devices: 64,  alertCount: 1 },
  { id: 'IT-MIL', name: 'Milan-D',   country: 'Italy',   status: 'ok',   energy: 2210, co2:  864, cost: 412000, cap: 0.51, devices: 71,  alertCount: 0 },
  { id: 'FR-LYO', name: 'Lyon-E',    country: 'France',  status: 'ok',   energy: 1370, co2:  594, cost: 422000, cap: 0.38, devices: 58,  alertCount: 1 },
];

function App() {
  const [view, setView] = useState('holding');
  const [factoryId, setFactoryId] = useState('TN-SFA');
  const [range, setRange] = useState('Month');
  const [chatOpen, setChatOpen] = useState(false);

  const factory = FACTORIES.find(f => f.id === factoryId);
  const totalAlerts = FACTORIES.reduce((s, f) => s + f.alertCount, 0);

  const [tweaks, setTweak] = useTweaks({
    accent: '#baa98b',
    secondary: '#786c5c',
    ink: '#272a3b',
    paper: '#eef0f3',
  });

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty('--accent', tweaks.accent);
    root.style.setProperty('--secondary', tweaks.secondary);
    root.style.setProperty('--ink', tweaks.ink);
    root.style.setProperty('--paper', tweaks.paper);
  }, [tweaks]);

  const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  const title = view === 'holding' ? 'Energy overview' : factory.name;
  const sub = view === 'holding'
    ? `${today} · 5 factories · live IoT + documents`
    : `${factory.id} · ${factory.country} · ${factory.devices} devices online`;

  return (
    <div className="app" data-screen-label="NRTF Dashboard">
      <Sidebar
        view={view} setView={setView}
        factory={factoryId} setFactory={setFactoryId}
        factories={FACTORIES}
      />
      <div className="shell">
        <TopBar
          title={title} subtitle={sub}
          range={range} setRange={setRange}
          alertCount={totalAlerts}
        />
        <div className="main">
          {view === 'holding' && (
            <HoldingDashboard
              range={range} factories={FACTORIES}
              onDrill={(id) => { setFactoryId(id); setView('factory'); }}
            />
          )}
          {view === 'factory' && (
            <FactoryDashboard factory={factory} range={range} />
          )}
        </div>
      </div>

      {!chatOpen && (
        <button className="fab" onClick={() => setChatOpen(true)} aria-label="Open assistant">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M4 5h16v11H8l-4 4z"/>
            <path d="M8 9h8M8 12h6"/>
          </svg>
          <span className="dotg"></span>
        </button>
      )}
      <Chatbot open={chatOpen} onClose={() => setChatOpen(false)} />

      <TweaksPanel title="Tweaks">
        <TweakSection title="Palette">
          <TweakColor label="Primary (ink)" value={tweaks.ink} onChange={v => setTweak('ink', v)} />
          <TweakColor label="Secondary" value={tweaks.secondary} onChange={v => setTweak('secondary', v)} />
          <TweakColor label="Accent" value={tweaks.accent} onChange={v => setTweak('accent', v)} />
          <TweakColor label="Background" value={tweaks.paper} onChange={v => setTweak('paper', v)} />
        </TweakSection>
        <TweakSection title="Demo flow">
          <button className="btn" style={{ width: '100%' }} onClick={() => setView('holding')}>↺ Back to overview</button>
          <button className="btn btn--ghost" style={{ width: '100%', marginTop: 8 }} onClick={() => { setFactoryId('TN-TUN'); setView('factory'); }}>
            ⚠ Drill into critical factory
          </button>
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
