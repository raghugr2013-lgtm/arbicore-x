import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { CapacityPanel } from "@/components/panels/CapacityPanel";
import { CapabilityPanel } from "@/components/panels/CapabilityPanel";
import { DepthPanel } from "@/components/panels/DepthPanel";
import { DiscoveryPanel } from "@/components/panels/DiscoveryPanel";
import { EconomicsPanel } from "@/components/panels/EconomicsPanel";
import { HistoricalPanel } from "@/components/panels/HistoricalPanel";
import { HoldProbPanel } from "@/components/panels/HoldProbPanel";
import { OpportunityMonitor } from "@/components/panels/OpportunityMonitor";
import { OpportunityWidget } from "@/components/panels/OpportunityWidget";
import { PortalPricePanel } from "@/components/panels/PortalPricePanel";
import { PositionsPanel } from "@/components/panels/PositionsPanel";
import { RouteClassificationPanel } from "@/components/panels/RouteClassificationPanel";
import { SafetyPanel } from "@/components/panels/SafetyPanel";
import { SpreadPanel } from "@/components/panels/SpreadPanel";
import { StatusPanel } from "@/components/panels/StatusPanel";
import { TreasuryPanel } from "@/components/panels/TreasuryPanel";
import { VenueMatrix } from "@/components/panels/VenueMatrix";
import { RouteDialog } from "@/components/RouteDialog";
import { VerdictBadge } from "@/components/VerdictBadge";
import { fmtQty } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Dashboard() {
  const [routeId, setRouteId] = useState(null);
  const [snap, setSnap] = useState(null);
  const [positions, setPositions] = useState([]);

  useEffect(() => {
    axios.get(`${API}/routes`).then((res) => {
      if (res.data.length) setRouteId(res.data[0].id);
    }).catch(() => toast.error("Failed to load routes"));
  }, []);

  const fetchSnap = useCallback(() => {
    if (!routeId) return;
    axios.get(`${API}/routes/${routeId}/snapshot`).then((res) => setSnap(res.data)).catch(() => {});
  }, [routeId]);

  const fetchPositions = useCallback(() => {
    if (!routeId) return;
    axios.get(`${API}/positions`, { params: { route_id: routeId } }).then((res) => setPositions(res.data)).catch(() => {});
  }, [routeId]);

  useEffect(() => {
    fetchSnap();
    fetchPositions();
    const t1 = setInterval(fetchSnap, 5000);
    const t2 = setInterval(fetchPositions, 15000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [fetchSnap, fetchPositions]);

  const route = snap?.route;
  const ev = snap?.evaluation;
  const mode = route?.mode || "live";

  const toggleMode = async () => {
    const next = mode === "live" ? "simulation" : "live";
    await axios.patch(`${API}/routes/${routeId}`, { mode: next });
    toast.success(`Mode → ${next.toUpperCase()}${next === "simulation" ? " — data tagged SIM, never mixed into live history" : ""}`);
    fetchSnap();
  };

  const setExitVenue = async (ex) => {
    if (ex === route?.exit?.exchange) return;
    await axios.patch(`${API}/routes/${routeId}`, { exit: { exchange: ex } });
    toast.success(`Exit venue preset → ${ex.toUpperCase()} — engines re-evaluating`);
    fetchSnap();
  };

  if (!routeId) {
    return <div className="p-10 font-mono text-sm text-[#6b7888]" data-testid="dashboard-loading">loading routes…</div>;
  }

  return (
    <div className="px-4 pb-10 max-w-[1700px] mx-auto" data-testid="dashboard">
      {/* Route toolbar */}
      <div className="flex flex-wrap items-center gap-3 py-3 border-b border-[#1f2a36] mb-4">
        <div className="font-mono text-sm font-bold tracking-wider" data-testid="route-name">
          {route?.name || "…"}
        </div>
        <span className="text-[10px] font-mono text-[#6b7888]">
          {route ? `${route.funding.coin}@${route.funding.network} → ${route.purchase.asset}@${route.purchase.network} → ${route.exit.exchange.toUpperCase()} → ${route.settlement.coin}@${route.settlement.network}` : ""}
        </span>
        <div className="flex-1" />
        <div className="flex items-center gap-1" data-testid="route-presets">
          <span className="text-[9px] font-mono text-[#6b7888] mr-1">EXIT:</span>
          {["xt", "bitmart", "coinstore"].map((ex) => (
            <button key={ex} data-testid={`preset-${ex}`} onClick={() => setExitVenue(ex)}
                    className={`font-mono text-[10px] font-bold tracking-wider px-2.5 py-1 border transition-colors ${
                      route?.exit?.exchange === ex
                        ? "border-[#ffb224] text-[#ffb224] bg-[#ffb224]/10"
                        : "border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0]"
                    }`}>
              {ex.toUpperCase()}
            </button>
          ))}
        </div>
        <VerdictBadge verdict={ev?.verdict} size="sm" />
        <button
          data-testid="mode-toggle"
          onClick={toggleMode}
          className={`font-mono text-[10px] font-bold tracking-widest px-3 py-1.5 border ${
            mode === "simulation"
              ? "border-[#38bdf8] text-[#38bdf8] bg-[#38bdf8]/10"
              : "border-[#34d399] text-[#34d399] bg-[#34d399]/10"
          }`}
        >
          {mode === "simulation" ? "◉ SIMULATION" : "◉ LIVE"}
        </button>
        {route && <RouteDialog route={route} onChanged={fetchSnap} />}
      </div>

      {mode === "simulation" && (
        <div className="mb-3 border border-[#38bdf8]/40 bg-[#38bdf8]/5 px-3 py-1.5 font-mono text-[11px] text-[#38bdf8]" data-testid="sim-watermark">
          SIMULATION MODE — synthetic seeded data. Toggle deposit scenarios in Route Config to rehearse gate flips.
        </div>
      )}

      {/* Headline strip */}
      {ev && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-[#1f2a36] border border-[#1f2a36] mb-4 font-mono" data-testid="headline-strip">
          {[
            ["NET SPREAD", ev.spread?.net_pct != null ? `${ev.spread.net_pct > 0 ? "+" : ""}${ev.spread.net_pct.toFixed(2)}%` : "—",
             ev.spread?.net_pct > 0 ? "#34d399" : "#f87171"],
            ["RECOMMENDED SIZE", ev.capacity?.recommended != null ? fmtQty(ev.capacity.recommended) : "—", "#ffb224"],
            ["OVERALL SAFETY", ev.scores?.overall != null ? Math.round(ev.scores.overall) : "—",
             ev.scores?.overall >= 70 ? "#34d399" : ev.scores?.overall >= 45 ? "#fbbf24" : "#f87171"],
            ["ROUTE CONFIDENCE", ev.confidence?.score != null ? `${Math.round(ev.confidence.score)}%` : "—",
             ev.confidence?.score >= 70 ? "#34d399" : ev.confidence?.score >= 45 ? "#fbbf24" : "#f87171"],
            ["EXIT VENUE", ev.exchange?.toUpperCase() || "—", "#38bdf8"],
          ].map(([label, value, color]) => (
            <div key={label} className="bg-[#10161e] px-4 py-2.5">
              <div className="text-[9px] tracking-widest text-[#6b7888]">{label}</div>
              <div className="text-xl font-bold" style={{ color }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 xl:col-span-7"><OpportunityMonitor comparison={snap?.comparison} /></div>
        <div className="col-span-12 xl:col-span-5"><SafetyPanel evaluation={ev} /></div>
        <div className="col-span-12"><VenueMatrix matrix={ev?.venue_matrix} /></div>
        <div className="col-span-12"><OpportunityWidget routeId={routeId} /></div>
        <div className="col-span-12"><RouteClassificationPanel routeId={routeId} /></div>
        <div className="col-span-12 xl:col-span-7"><EconomicsPanel routeId={routeId} /></div>
        <div className="col-span-12 xl:col-span-5"><PortalPricePanel priceSource={ev?.inputs?.price_source} /></div>
        <div className="col-span-12"><CapabilityPanel asset={route?.purchase?.asset || "BDAG"} /></div>
        <div className="col-span-12 md:col-span-6 xl:col-span-4"><SpreadPanel evaluation={ev} history={snap?.spread_history} /></div>
        <div className="col-span-12 md:col-span-6 xl:col-span-4"><CapacityPanel evaluation={ev} /></div>
        <div className="col-span-12 xl:col-span-4"><DepthPanel orderbook={snap?.orderbook} /></div>
        <div className="col-span-12 xl:col-span-7"><HistoricalPanel routeId={routeId} /></div>
        <div className="col-span-12 xl:col-span-5"><HoldProbPanel evaluation={ev} /></div>
        <div className="col-span-12 xl:col-span-7">
          <PositionsPanel routeId={routeId} positions={positions} onChanged={() => { fetchPositions(); fetchSnap(); }} />
        </div>
        <div className="col-span-12 xl:col-span-5"><TreasuryPanel routeId={routeId} /></div>
        <div className="col-span-12 xl:col-span-7"><DiscoveryPanel asset={route?.purchase?.asset || "BDAG"} /></div>
        <div className="col-span-12 xl:col-span-5"><StatusPanel system={snap?.system} /></div>
      </div>
    </div>
  );
}
