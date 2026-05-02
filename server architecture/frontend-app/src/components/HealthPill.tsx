// Live indicator that proves the API client is talking to a real backend.

import { useHealth } from "../lib/api/queries";

export function HealthPill() {
  const { data, isError } = useHealth();
  const ok = !isError && data?.status === "ok";
  return (
    <div className="live" style={{ color: ok ? "var(--ok)" : "var(--crit)" }}>
      <span className="pulse" />
      {ok ? "API ONLINE" : "API DOWN"}
    </div>
  );
}
