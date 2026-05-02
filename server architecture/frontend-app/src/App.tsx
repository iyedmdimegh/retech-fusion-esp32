// M14 proof-of-life shell. Sidebar + topbar shells from the prototype CSS,
// with one real data panel (BILAN files) wired to the live backend.
// M15+ will fill in the rest.

import { BilanFilesPanel } from "./components/BilanFilesPanel";
import { HealthPill } from "./components/HealthPill";

function App() {
  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div className="app">
      {/* sidebar — visual shell only for M14 */}
      <aside className="sb">
        <div className="sb__brand">NRTF</div>
        <div className="sb__group">Menu</div>
        <div className="sb__nav">
          <button className="sb__item is-active">Dashboard</button>
          <button className="sb__item">Reports</button>
          <button className="sb__item">Schedules</button>
        </div>
        <div className="sb__group">Plants</div>
        <div className="sb__factories">
          <button className="sb__factory is-active">
            <div>Plant 1<small>insat_lab_zone_a</small></div>
            <span className="dot" style={{ background: "var(--ok)" }} />
          </button>
          <button className="sb__factory">
            <div>Plant 2<small>awaiting data</small></div>
            <span className="dot" style={{ background: "var(--ink-mute)" }} />
          </button>
        </div>
      </aside>

      {/* shell */}
      <div className="shell">
        <div className="top">
          <div>
            <h1 className="top__h1">Energy overview</h1>
            <div className="top__sub">{today} · M14 proof-of-life</div>
          </div>
          <div className="top__spacer" />
          <HealthPill />
        </div>

        <div className="main">
          <div className="h-row">
            <div className="h-row__title">BILAN files</div>
            <div className="h-row__hint">live from /api/bilan/files</div>
          </div>
          <BilanFilesPanel />
        </div>
      </div>
    </div>
  );
}

export default App;
