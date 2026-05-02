// Assistant page (Phase 2 placeholder). The chat shell + canned response
// logic comes from the Claude Design prototype (frontend/project/chatbot.jsx);
// the prototype's regex-based answers are kept verbatim because the real
// LLM-with-RAG agent is deferred to checkpoint 2 (per the M13 decision).
//
// The placeholder banner at the top makes the demo intent honest — a judge
// who clicks here doesn't see a fake AI answering questions, they see "this
// is wired to the layout but not yet connected to a model."

import { useEffect, useRef, useState } from "react";

interface Msg {
  who: "bot" | "me";
  text: string;
  t: string;
}

const SEED: Msg[] = [
  {
    who: "bot",
    text:
      "Hi — I'll have full context of the IoT stream, the BILAN reports and the CO₂ ledger once the LLM tier lands in checkpoint 2. " +
      "Try one of the suggestions below to see the canned-response stub.",
    t: "—",
  },
];

const SUGGESTIONS = [
  "Carbon footprint trend this quarter",
  "Top heat recovery opportunities",
  "Generate monthly report for Plant 1",
];

export function ChatbotPage() {
  const [msgs, setMsgs] = useState<Msg[]>(SEED);
  const [val, setVal] = useState("");
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [msgs]);

  const send = (text: string) => {
    if (!text.trim()) return;
    const now = new Date();
    const t = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    setMsgs((m) => [...m, { who: "me", text, t }]);
    setVal("");
    setTimeout(() => {
      setMsgs((m) => [...m, { who: "bot", text: canned(text), t }]);
    }, 700);
  };

  return (
    <div>
      <div className="h-row">
        <div className="h-row__title">Assistant</div>
        <div className="h-row__hint">checkpoint 2 — placeholder</div>
      </div>

      {/* honesty banner */}
      <div
        className="insight"
        style={{ borderLeft: "3px solid var(--info)", marginBottom: 14 }}
      >
        <h4>
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <circle cx="8" cy="8" r="6.5" />
            <path d="M8 5v4M8 11h.01" />
          </svg>
          Demo placeholder — full assistant coming in checkpoint 2
        </h4>
        <p>
          This panel is wired to the page layout and styling but is not yet
          connected to a real LLM. Suggestion chips trigger the prototype's
          canned answers so the conversation flow is visible to the judges.
          The intended implementation in checkpoint 2 is RAG over the IoT
          stream, BILAN time-series, document OCR text and the CO₂ ledger.
        </p>
      </div>

      {/* the chat — single-column, fills the page */}
      <div
        className="card"
        style={{ padding: 0, display: "flex", flexDirection: "column", minHeight: 460 }}
      >
        <div
          className="chat__head"
          style={{ borderTopLeftRadius: "var(--r)", borderTopRightRadius: "var(--r)" }}
        >
          <div className="chat__title">
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.4"
            >
              <rect x="2" y="3.5" width="12" height="9" rx="1" />
              <path d="M5 7h6M5 9.5h4" />
            </svg>
            NRTF · Assistant (placeholder)
          </div>
        </div>

        <div
          ref={bodyRef}
          className="chat__body"
          style={{ flex: 1, minHeight: 320 }}
        >
          {msgs.map((m, i) => (
            <div key={i} className={`chat__msg ${m.who}`}>
              <div className="chat__bub">{m.text}</div>
              <div className="chat__time">
                {m.who === "bot" ? "Assistant" : "You"} · {m.t}
              </div>
            </div>
          ))}
          <div className="chat__suggest">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="chat__input">
          <input
            value={val}
            onChange={(e) => setVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") send(val);
            }}
            placeholder="Ask about KPIs, anomalies, reports… (canned answers only)"
          />
          <button onClick={() => send(val)} aria-label="Send">
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
            >
              <path d="M2 8h11M9 4l4 4-4 4" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

// Verbatim from frontend/project/chatbot.jsx::canned. Three regex buckets,
// then a generic fallback. Kept the original copy because it talks the
// hackathon's narrative ("Q1-26 emissions: 1,468 tCO₂e ...") in a way that
// matches the rest of the prototype's tone.
function canned(q: string): string {
  const s = q.toLowerCase();
  if (s.includes("footprint") || s.includes("quarter")) {
    return (
      "Q1-26 emissions: 1,468 tCO₂e — down 8.1% vs Q1-25 (1,597 t). " +
      "Drivers: heat recovery commissioning at Sfax-A (-180 t), grid factor " +
      "improvement (-92 t). Offset partially by Tunis-B production ramp (+143 t)."
    );
  }
  if (s.includes("recovery") || s.includes("heat")) {
    return (
      "Top 3 ranked by 5-criteria scoring (energy, CO₂, complexity, CAPEX, payback): " +
      "① Boiler flue → feedwater preheat — 620 MWh/yr, −290 tCO₂e/yr, 2.1 yr payback. " +
      "② Compressor heat → DHW — 184 MWh/yr, 1.4 yr payback. " +
      "③ Condensate recovery loop — 96 MWh/yr, 3.6 yr payback."
    );
  }
  if (s.includes("report")) {
    return (
      "Drafting monthly report for Plant 1 (April 2026) — pulling KPIs, " +
      "anomaly summary, carbon ledger and audit trail. Estimated 4 pages. " +
      "Ready in ~12 s. Want me to email it to plant ops?"
    );
  }
  return (
    "I traced this against the unified time-series + extracted documents. " +
    "Let me know if you want me to drill into a specific line, machine or period."
  );
}
