import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { fmtPrice, fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SOURCE_LABEL = {
  portal: { text: "LIVE PORTAL", color: "#34d399" },
  position: { text: "POSITION COST", color: "#38bdf8" },
  manual_override: { text: "MANUAL OVERRIDE", color: "#ffb224" },
  manual_fallback: { text: "MANUAL FALLBACK", color: "#fbbf24" },
};

export const PortalPricePanel = ({ priceSource }) => {
  const [data, setData] = useState(null);
  const [hist, setHist] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    axios.get(`${API}/portal/price`).then((r) => setData(r.data)).catch(() => {});
    axios.get(`${API}/portal/price/history?hours=24`)
      .then((r) => setHist((r.data.points || []).map((p) => ({ t: fmtTime(p.ts), p: p.bdag_price }))))
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  const refresh = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/portal/price/refresh`);
      toast.success("Portal price refreshed");
      load();
    } catch {
      toast.error("Refresh failed");
    }
    setBusy(false);
  };

  const src = SOURCE_LABEL[priceSource] || null;

  return (
    <div className="panel" data-testid="portal-price-panel">
      <div className="panel-title">
        BlockDAG Portal Price
        <span className="float-right flex items-center gap-2">
          <span className="text-[#3d4a59]">read-only · sw-api/getInfo</span>
          <button data-testid="portal-price-refresh-btn" onClick={refresh} disabled={busy}
                  className="font-mono text-[9px] font-bold tracking-widest px-2 py-1 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 disabled:opacity-50">
            {busy ? "…" : "REFRESH"}
          </button>
        </span>
      </div>
      {!data && <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>}
      {data && (
        <>
          <div className="flex items-end gap-3">
            <div>
              <div className="font-mono text-[9px] uppercase tracking-widest text-[#6b7888]">Live swap price</div>
              <div data-testid="portal-price-value" className="font-mono text-2xl font-bold text-[#34d399]">
                {fmtPrice(data.bdag_price)}
              </div>
            </div>
            <div className="flex-1" />
            <div className="text-right">
              <div className={`font-mono text-[10px] font-bold ${data.stale ? "text-[#f87171]" : "text-[#34d399]"}`}
                   data-testid="portal-price-status">
                {data.stale ? "○ STALE" : "● LIVE"}
              </div>
              <div className="font-mono text-[9px] text-[#6b7888]">
                {data.fetched_at ? fmtTime(data.fetched_at) : "—"} · poll {data.poll_interval_s}s
              </div>
            </div>
          </div>
          {src && (
            <div className="mt-2 font-mono text-[10px]" data-testid="portal-price-effective-source">
              <span className="text-[#6b7888]">Effective buy price source: </span>
              <span style={{ color: src.color }} className="font-bold">{src.text}</span>
            </div>
          )}
          <div className="h-20 mt-2" data-testid="portal-price-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={hist} margin={{ top: 4, right: 4, bottom: 0, left: -28 }}>
                <YAxis tick={{ fontSize: 8, fill: "#6b7888" }} domain={["auto", "auto"]} width={50} />
                <Tooltip
                  contentStyle={{ background: "#10161e", border: "1px solid #1f2a36", fontSize: 11, fontFamily: "IBM Plex Mono" }}
                  formatter={(v) => fmtPrice(v)}
                />
                <Line type="linear" dataKey="p" stroke="#34d399" dot={false} strokeWidth={1.5} isAnimationActive={false} name="portal price" />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="font-mono text-[9px] text-[#3d4a59] mt-1">
            Pay-coin USD: ETH {fmtPrice(data.coin_prices?.ETH)} · BNB {fmtPrice(data.coin_prices?.BNB)} · 24h history points: {hist.length}
          </div>
        </>
      )}
    </div>
  );
};
