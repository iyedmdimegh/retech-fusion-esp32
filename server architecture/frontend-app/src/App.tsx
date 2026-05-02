// Routed shell. Sidebar + topbar wrap the route outlet.
// Real factory routing kicks in at /plant-1/upload and /plant-1/energy.

import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { HealthPill } from "./components/HealthPill";
import { ChatbotPage } from "./pages/ChatbotPage";
import { Co2Page } from "./pages/Co2Page";
import { EnergyPage } from "./pages/EnergyPage";
import { UploadPage } from "./pages/UploadPage";

const PLANTS: {
  id: string;
  name: string;
  site: string;
  status: "ok" | "stub";
}[] = [
  { id: "plant-1", name: "Plant 1", site: "insat_lab_zone_a", status: "ok" },
  { id: "plant-2", name: "Plant 2", site: "awaiting first data", status: "stub" },
  { id: "plant-3", name: "Plant 3", site: "awaiting first data", status: "stub" },
  { id: "plant-4", name: "Plant 4", site: "awaiting first data", status: "stub" },
  { id: "plant-5", name: "Plant 5", site: "awaiting first data", status: "stub" },
];

const NAV: { to: string; label: string }[] = [
  { to: "/plant-1/energy", label: "Energy" },
  { to: "/plant-1/co2", label: "CO₂ analytics" },
  { to: "/plant-1/upload", label: "Upload" },
  { to: "/plant-1/assistant", label: "Assistant" },
];

function Shell({ children }: { children: React.ReactNode }) {
  const today = new Date().toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const loc = useLocation();
  const sectionTitle = loc.pathname.includes("/upload")
    ? "Upload BILAN data"
    : loc.pathname.includes("/co2")
    ? "CO₂ analytics"
    : loc.pathname.includes("/assistant")
    ? "Assistant"
    : "Energy overview";

  return (
    <div className="app">
      <aside className="sb">
        <div className="sb__brand">NRTF</div>

        <div className="sb__group">Menu</div>
        <div className="sb__nav">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `sb__item ${isActive ? "is-active" : ""}`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </div>

        <div className="sb__group">Plants</div>
        <div className="sb__factories">
          {PLANTS.map((p) => {
            const active = p.status === "ok" && loc.pathname.startsWith(`/${p.id}`);
            return (
              <Link
                key={p.id}
                to={p.status === "ok" ? `/${p.id}/energy` : "#"}
                className={`sb__factory ${active ? "is-active" : ""}`}
                style={{
                  cursor: p.status === "ok" ? "pointer" : "not-allowed",
                  opacity: p.status === "ok" ? 1 : 0.55,
                }}
                onClick={(e) => {
                  if (p.status === "stub") e.preventDefault();
                }}
              >
                <div>
                  {p.name}
                  <small>
                    {p.status === "ok" ? p.site : "Awaiting first data ingestion"}
                  </small>
                </div>
                <span
                  className="dot"
                  style={{
                    background:
                      p.status === "ok" ? "var(--ok)" : "var(--ink-mute)",
                  }}
                />
              </Link>
            );
          })}
        </div>
      </aside>

      <div className="shell">
        <div className="top">
          <div>
            <h1 className="top__h1">{sectionTitle}</h1>
            <div className="top__sub">{today} · Plant 1 · INSAT lab</div>
          </div>
          <div className="top__spacer" />
          <HealthPill />
        </div>
        <div className="main">{children}</div>
      </div>
    </div>
  );
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/plant-1/energy" replace />} />
      <Route
        path="/plant-1/energy"
        element={
          <Shell>
            <EnergyPage />
          </Shell>
        }
      />
      <Route
        path="/plant-1/co2"
        element={
          <Shell>
            <Co2Page />
          </Shell>
        }
      />
      <Route
        path="/plant-1/upload"
        element={
          <Shell>
            <UploadPage />
          </Shell>
        }
      />
      <Route
        path="/plant-1/assistant"
        element={
          <Shell>
            <ChatbotPage />
          </Shell>
        }
      />
      <Route
        path="*"
        element={
          <Shell>
            <div className="card" style={{ marginTop: 24 }}>
              <div className="card__title">Not found</div>
              <div className="card__sub">
                That URL has no page. Try the sidebar.
              </div>
            </div>
          </Shell>
        }
      />
    </Routes>
  );
}

export default App;
