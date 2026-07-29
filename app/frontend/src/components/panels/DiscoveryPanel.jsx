import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Radar } from "lucide-react";
import { fmtTime, fmtUsd } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const DiscoveryPanel = ({ asset }) => {
  const [data, setData] = useState(null);
  const [scanning, setScanning] = useState(false);

  const fetchLatest = useCallback(() => {
    axios.get(`${API}/discovery/latest`, { params: { asset } }).then((res) => setData(res.data)).catch(() => {});
  }, [asset]);

  useEffect(() => {
    fetchLatest();
    const t = setInterval(fetchLatest, 60000);
    return () => clearInterval(t);
  }, [fetchLatest]);

  const runScan = async () => {
    setScanning(true);
    try {
      const res = await axios.post(`${API}/discovery/scan`, null, { params: { asset } });
      setData(res.data);
      const n = res.data.new_findings?.length || 0;
      toast.success(n ? `Scan complete — ${n} new finding(s)` : "Scan complete — no new venues/listings");
    } catch {
      toast.error("Scan failed");
    } finally {
      setScanning(false);
    }
  };

  const venues = (data?.venues || []).filter((v) => v.source !== "connector" ? v.listed : true)
    .sort((a, b) => (b.listed === true) - (a.listed === true));
  const cg = data?.sources?.coingecko;

  return (
    <div className="panel" data-testid="discovery-panel">
      <div className="panel-title">
        Exchange Discovery Service — {asset} venue map
        <button data-testid="discovery-scan-btn" onClick={runScan} disabled={scanning}
                className="term-btn-secondary float-right flex items-center gap-1.5 -mt-1">
          <Radar size={12} className={scanning ? "spin" : ""} /> {scanning ? "SCANNING…" : "SCAN NOW"}
        </button>
      </div>
      <div className="text-[9px] font-mono text-[#6b7888] mb-2" data-testid="discovery-sources">
        last scan: {data?.ts ? fmtTime(data.ts) : "never"} · sources: connectors ✓ · coingecko{" "}
        <span className={cg === "ok" ? "text-[#34d399]" : "text-[#fbbf24]"}>{cg || "—"}</span>
      </div>
      {venues.length === 0 ? (
        <div className="text-[11px] font-mono text-[#6b7888] py-3">
          No scan data yet — hit SCAN NOW to map {asset} venues across connectors + aggregators.
        </div>
      ) : (
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr className="panel-th">
              <th className="text-left">Venue</th>
              <th className="text-left">Source</th>
              <th className="text-right">24h Vol</th>
              <th className="text-left">Connector</th>
            </tr>
          </thead>
          <tbody>
            {venues.slice(0, 10).map((v, i) => (
              <tr key={i} data-testid={`discovery-row-${v.key}`} className={`border-b border-[#1f2a36]/50 ${v.listed ? "" : "opacity-40"}`}>
                <td className="py-1 uppercase font-bold text-xs">{v.name || v.key}</td>
                <td className="text-[#6b7888]">{v.listed ? v.source : "not listed"}</td>
                <td className="text-right">{fmtUsd(v.volume_24h_quote)}</td>
                <td>
                  {v.connector_live ? <span className="text-[#34d399]">live</span>
                    : v.connector_known ? <span className="text-[#fbbf24]">stub</span>
                    : <span className="text-[#f87171]">none — coverage gap</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {(data?.new_findings || []).length > 0 && (
        <div className="mt-2 border border-[#34d399]/30 bg-[#34d399]/5 px-2 py-1 text-[10px] font-mono text-[#34d399]" data-testid="discovery-findings">
          {data.new_findings.map((f, i) => <div key={i}>★ {f.type}: {f.name} {f.pair}</div>)}
        </div>
      )}
    </div>
  );
};
