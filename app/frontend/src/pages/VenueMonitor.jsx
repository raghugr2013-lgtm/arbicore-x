import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const num = (v, d = 2) => (v == null || isNaN(v) ? "—" : Number(v).toFixed(d));
const sci = (v) => (v == null || isNaN(v) ? "—" : Number(v).toExponential(3));
const fmtTs = (iso) => (iso ? new Date(iso).toLocaleTimeString() : "—");

const CHECK_LABELS = {
  deposit_open: "Deposit Open",
  deposit_crediting_verified: "Deposit Crediting Verified",
  trading_active: "Trading Active",
  usdt_withdrawal_available: "USDT Withdrawal Available",
  api_healthy: "API Healthy",
  sufficient_depth: "Sufficient Depth",
};

const dotColor = (v) => (v === true ? "#34d399" : v === false ? "#f87171" : "#6b7888");
const dotLabel = (v) => (v === true ? "PASS" : v === false ? "FAIL" : "UNKNOWN");

const VenueCard = ({ v, onMarkVerified }) => {
  const r = v.readiness || {};
  const checks = r.checks || {};
  const score = v.health_score ?? 0;
  return (
    <div data-testid={`venue-card-${v.exchange}`}
         className="border border-[#1f2a36] bg-[#0a0e13] p-4 font-mono text-[11px]">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[#34d399] font-bold tracking-wider uppercase text-sm" data-testid={`venue-name-${v.exchange}`}>
          {v.exchange}
        </span>
        <span data-testid={`venue-ready-${v.exchange}`}
              className={`px-2 py-0.5 text-[9px] font-bold tracking-wider border ${v.full_cycle_ready ? "text-[#34d399] border-[#34d399]" : "text-[#6b7888] border-[#1f2a36]"}`}>
          {v.full_cycle_ready ? "FULL CYCLE READY" : `${r.passed ?? 0}/6 CHECKS`}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1 mb-3 text-[#c9d4e0]">
        <div>
          <div className="text-[9px] text-[#5a6573]">HEALTH SCORE</div>
          <div data-testid={`venue-health-${v.exchange}`} className="text-base">{num(score, 1)}</div>
        </div>
        <div>
          <div className="text-[9px] text-[#5a6573]">LATENCY</div>
          <div data-testid={`venue-latency-${v.exchange}`}>{num(v.latency_ms, 0)} ms</div>
        </div>
        <div>
          <div className="text-[9px] text-[#5a6573]">BEST BID</div>
          <div data-testid={`venue-bid-${v.exchange}`}>{sci((v.derived || {}).best_bid)}</div>
        </div>
        <div>
          <div className="text-[9px] text-[#5a6573]">BEST ASK</div>
          <div data-testid={`venue-ask-${v.exchange}`}>{sci((v.derived || {}).best_ask)}</div>
        </div>
        <div>
          <div className="text-[9px] text-[#5a6573]">SPREAD %</div>
          <div data-testid={`venue-spread-${v.exchange}`}>{num((v.derived || {}).spread_pct, 3)}%</div>
        </div>
        <div>
          <div className="text-[9px] text-[#5a6573]">PROFITABLE DEPTH</div>
          <div data-testid={`venue-depth-usd-${v.exchange}`}>${num((v.derived || {}).profitable_buyer_depth_usd, 0)}</div>
        </div>
        <div>
          <div className="text-[9px] text-[#5a6573]">24H VOLUME (USD)</div>
          <div data-testid={`venue-volume-${v.exchange}`}>
            {((v.ticker) || {}).volume_24h_quote_usd == null ? "—" : `$${num(v.ticker.volume_24h_quote_usd, 0)}`}
          </div>
        </div>
        <div>
          <div className="text-[9px] text-[#5a6573]">LAST CHECK</div>
          <div data-testid={`venue-last-${v.exchange}`}>{fmtTs(v.last_check_at)}</div>
        </div>
      </div>

      <div className="border-t border-[#1f2a36] pt-2">
        <div className="text-[9px] text-[#5a6573] mb-1">FULL CYCLE READINESS</div>
        <div className="grid grid-cols-1 gap-0.5">
          {Object.entries(CHECK_LABELS).map(([k, label]) => (
            <div key={k} className="flex justify-between items-center">
              <span className="text-[#c9d4e0]">{label}</span>
              <span data-testid={`venue-check-${v.exchange}-${k}`}
                    className="font-bold" style={{ color: dotColor(checks[k]) }}>
                ● {dotLabel(checks[k])}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 flex gap-1.5">
        <button data-testid={`venue-verify-deposit-${v.exchange}`}
                onClick={() => onMarkVerified(v.exchange, "deposit_credit_verified")}
                className="flex-1 text-[9px] py-1 border border-[#1f2a36] text-[#6b7888] hover:text-[#34d399] hover:border-[#34d399]/50">
          MARK DEPOSIT VERIFIED
        </button>
        <button data-testid={`venue-verify-withdraw-${v.exchange}`}
                onClick={() => onMarkVerified(v.exchange, "withdraw_credit_verified")}
                className="flex-1 text-[9px] py-1 border border-[#1f2a36] text-[#6b7888] hover:text-[#34d399] hover:border-[#34d399]/50">
          MARK WITHDRAW VERIFIED
        </button>
      </div>
    </div>
  );
};

const VenueMonitor = () => {
  const [venues, setVenues] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [status, setStatus] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [h, a, s] = await Promise.all([
        axios.get(`${API}/venues/health`).then((r) => r.data),
        axios.get(`${API}/venues/alerts?limit=20`).then((r) => r.data),
        axios.get(`${API}/venues/status`).then((r) => r.data),
      ]);
      setVenues(h.venues || []);
      setAlerts(a.alerts || []);
      setStatus(s);
    } catch (e) { /* soft fail */ }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  const markVerified = async (exchange, field) => {
    try {
      await axios.post(`${API}/venues/intelligence`, { exchange, [field]: true });
      toast.success(`${exchange}: ${field.replace(/_/g, " ")} marked`);
      load();
    } catch (e) {
      toast.error(`Failed to update ${exchange}`);
    }
  };

  const forceRefresh = async () => {
    setRefreshing(true);
    try {
      await axios.post(`${API}/venues/refresh`);
      toast.success("Venue snapshots refreshed");
      await load();
    } catch (e) { toast.error("Refresh failed"); }
    setRefreshing(false);
  };

  const ackAlert = async (alert) => {
    try {
      await axios.post(`${API}/venues/alerts/acknowledge`, { ts_ts: alert.ts_ts, exchange: alert.exchange });
      load();
    } catch (e) { /* soft */ }
  };

  // Sort: full_cycle_ready first, then by health_score desc
  const sorted = [...venues].sort((a, b) => {
    if (a.full_cycle_ready !== b.full_cycle_ready) return a.full_cycle_ready ? -1 : 1;
    return (b.health_score || 0) - (a.health_score || 0);
  });

  return (
    <div data-testid="venue-monitor" className="min-h-screen bg-[#0a0e13] text-[#c9d4e0] p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-1">
          <div>
            <h1 data-testid="venue-monitor-title" className="text-[#34d399] font-mono tracking-wider text-lg font-bold">
              VENUE MONITORING LAYER
            </h1>
            <div className="text-[10px] text-[#6b7888] font-mono mt-1">
              observational intelligence · public data only · Approval Mode unchanged
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-[10px] text-[#6b7888] font-mono text-right" data-testid="venue-status-meta">
              {status ? (
                <>
                  <div>iter <span className="text-[#34d399]">{status.iterations}</span> · {status.running ? "RUNNING" : "STOPPED"}</div>
                  <div>last poll {fmtTs(status.last_run_at)}</div>
                </>
              ) : "—"}
            </div>
            <button onClick={forceRefresh} disabled={refreshing}
                    data-testid="venue-refresh-btn"
                    className="text-[10px] font-mono px-3 py-1.5 border border-[#1f2a36] text-[#34d399] hover:border-[#34d399] disabled:opacity-50">
              {refreshing ? "REFRESHING…" : "REFRESH NOW"}
            </button>
          </div>
        </div>

        {/* Alerts strip */}
        {alerts.length > 0 && (
          <div data-testid="venue-alerts-strip" className="my-4 border border-[#1f2a36] bg-[#0f1419] p-3">
            <div className="text-[10px] text-[#ffb224] font-mono font-bold tracking-wider mb-2">ALERTS ({alerts.length})</div>
            <div className="space-y-1">
              {alerts.slice(0, 5).map((a) => (
                <div key={`${a.exchange}-${a.ts_ts}`}
                     data-testid={`venue-alert-${a.exchange}-${a.ts_ts}`}
                     className="flex justify-between items-center text-[10px] font-mono">
                  <span className={`${a.type === "FULL_CYCLE_READY" ? "text-[#34d399]" : "text-[#ffb224]"}`}>
                    [{a.type}] {a.message}
                  </span>
                  <span className="text-[#5a6573]">
                    {fmtTs(a.ts)} {!a.acknowledged && (
                      <button onClick={() => ackAlert(a)}
                              data-testid={`venue-ack-${a.exchange}-${a.ts_ts}`}
                              className="ml-2 underline hover:text-[#c9d4e0]">ACK</button>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Venue grid */}
        <div data-testid="venue-grid"
             className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sorted.map((v) => (
            <VenueCard key={v.exchange} v={v} onMarkVerified={markVerified} />
          ))}
        </div>

        {sorted.length === 0 && (
          <div data-testid="venue-empty" className="mt-8 text-center text-[#6b7888] font-mono text-xs">
            waiting for first poll cycle…
          </div>
        )}

        <div className="mt-6 text-[9px] text-[#5a6573] font-mono leading-relaxed">
          NOTE: This layer is purely observational. Active Approval Mode destination remains Coinstore.
          Alerts fire when a venue transitions into FULL CYCLE READY state across all 6 checks.
        </div>
      </div>
    </div>
  );
};

export default VenueMonitor;
