/* global React */

const { useState: useStateC, useRef: useRefC, useEffect: useEffectC } = React;

function Chatbot({ open, onClose }) {
  const [msgs, setMsgs] = useStateC([
    { who: 'bot', text: 'Hi — I have full context of your IoT stream, documents and CO₂ ledger. Ask me anything.', t: '13:40' },
    { who: 'me',  text: 'Why did energy spike on Tuesday at 3 pm?', t: '13:41' },
    { who: 'bot', text: 'On Tue 2026-04-29 15:00–15:40, total draw rose +18% vs the 4-week baseline. Root cause: Compressor C-204 ran in load mode for 38 min with a +0.6 bar drift — likely filter clogging. The edge SVD predictor flagged it locally; cloud Isolation Forest confirmed (score 0.87). Estimated cost impact: €312, +1.4 tCO₂e.', t: '13:41' },
  ]);
  const [val, setVal] = useStateC('');
  const bodyRef = useRefC(null);

  useEffectC(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [msgs, open]);

  const send = (text) => {
    if (!text.trim()) return;
    const now = new Date();
    const t = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
    setMsgs(m => [...m, { who: 'me', text, t }]);
    setVal('');
    setTimeout(() => {
      setMsgs(m => [...m, { who: 'bot', text: canned(text), t }]);
    }, 700);
  };

  const suggest = [
    'Carbon footprint trend this quarter',
    'Top heat recovery opportunities',
    'Generate monthly report for Sfax-A',
  ];

  if (!open) return null;
  return (
    <div className="chat" role="dialog" aria-label="Carbon assistant">
      <div className="chat__head">
        <div className="chat__title">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="2" y="3.5" width="12" height="9" rx="1"/><path d="M5 7h6M5 9.5h4"/></svg>
          NRTF · Assistant
        </div>
        <button className="chat__close" onClick={onClose} aria-label="Close">×</button>
      </div>
      <div className="chat__body" ref={bodyRef}>
        {msgs.map((m, i) => (
          <div key={i} className={`chat__msg ${m.who}`}>
            <div className="chat__bub">{m.text}</div>
            <div className="chat__time">{m.who === 'bot' ? 'Assistant' : 'You'} · {m.t}</div>
          </div>
        ))}
        <div className="chat__suggest">
          {suggest.map(s => <button key={s} onClick={() => send(s)}>{s}</button>)}
        </div>
      </div>
      <div className="chat__input">
        <input value={val} onChange={(e) => setVal(e.target.value)}
               onKeyDown={(e) => { if (e.key === 'Enter') send(val); }}
               placeholder="Ask about KPIs, anomalies, reports…" />
        <button onClick={() => send(val)} aria-label="Send">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M2 8h11M9 4l4 4-4 4"/></svg>
        </button>
      </div>
    </div>
  );
}

function canned(q) {
  const s = q.toLowerCase();
  if (s.includes('footprint') || s.includes('quarter')) {
    return 'Q1-26 emissions: 1,468 tCO₂e — down 8.1% vs Q1-25 (1,597 t). Drivers: heat recovery commissioning at Sfax-A (-180 t), grid factor improvement (-92 t). Offset partially by Tunis-B production ramp (+143 t).';
  }
  if (s.includes('recovery') || s.includes('heat')) {
    return 'Top 3 ranked by 5-criteria scoring (energy, CO₂, complexity, CAPEX, payback): ① Boiler flue → feedwater preheat — 620 MWh/yr, −290 tCO₂e/yr, 2.1 yr payback. ② Compressor heat → DHW — 184 MWh/yr, 1.4 yr payback. ③ Condensate recovery loop — 96 MWh/yr, 3.6 yr payback.';
  }
  if (s.includes('report')) {
    return 'Drafting monthly report for Sfax-A (April 2026) — pulling KPIs, anomaly summary, carbon ledger and audit trail. Estimated 4 pages. Ready in ~12s. Want me to email it to plant ops?';
  }
  return 'I traced this against the unified time-series + extracted documents. Let me know if you want me to drill into a specific line, machine or period.';
}

window.Chatbot = Chatbot;
