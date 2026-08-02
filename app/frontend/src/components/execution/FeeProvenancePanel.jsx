import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const CLASS_C = {
  "Live API": "#34d399",
  "Measured (live order book)": "#34d399",
  "Exchange (audited default)": "#ffb224",
  "Blockchain (hardcoded buffer)": "#fbbf24",
  "Blockchain (hardcoded estimate)": "#fbbf24",
  "Historical measurement": "#38bdf8",
  "User configured": "#a78bfa",
  "Hardcoded assumption": "#f87171",
};
const REC_C = {
  "Production Grade": "#34d399",
  "Needs Verification": "#ffb224",
  "Assumption Only": "#f87171",
};

const fmtVal = (v) => {
  if (v == null) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  if (typeof v === "number") return v < 0.001 ? v.toExponential(2) : String(v);
  return String(v);
};

const download = async (path, filename) => {
  try {
    const r = await axios.get(`${API}${path}`, { responseType: "blob" });
    const url = window.URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click();
    a.remove(); window.URL.revokeObjectURL(url);
    toast.success(`Downloaded ${filename}`);
  } catch (e) {
    toast.error(`Download failed: ${e.message || e}`);
  }
};

export const FeeProvenancePanel = () => {
  const [d, setD] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/fee-provenance`).then((r) => setD(r.data)).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  if (!d) {
    return (
      <div className="panel" data-testid="fee-provenance-panel">
        <div className="panel-title">Fee Provenance Report</div>
        <div className="font-mono text-[11px] text-[#6b7888]">loading provenance…</div>
      </div>
    );
  }

  const s = d.summary || {};
  const rec = s.recommendation_counts || {};

  return (
    <div className="panel" data-testid="fee-provenance-panel">
      <div className="panel-title">
        Fee Provenance Report — every fee classified
        <span className="float-right text-[#3d4a59]">read-only · {d.fees?.length || 0} fees</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3" data-testid="fee-provenance-summary">
        <div className="border border-[#1f2a36] bg-[#0a0e13] px-3 py-2">
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Total fees</div>
          <div className="font-mono text-xl font-bold text-[#c9d4e0]">{s.total_fees ?? 0}</div>
        </div>
        <div className="border border-[#1f2a36] bg-[#0a0e13] px-3 py-2">
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Live / measured</div>
          <div className="font-mono text-xl font-bold text-[#34d399]" data-testid="fee-real-count">{s.real_count ?? 0}</div>
        </div>
        <div className="border border-[#1f2a36] bg-[#0a0e13] px-3 py-2">
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Static / assumed</div>
          <div className="font-mono text-xl font-bold text-[#ffb224]" data-testid="fee-assumed-count">{s.assumed_count ?? 0}</div>
        </div>
        <div className="border border-[#1f2a36] bg-[#0a0e13] px-3 py-2">
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Grades</div>
          <div className="font-mono text-[10px] leading-tight mt-1 space-y-0.5">
            <div><span style={{ color: REC_C["Production Grade"] }}>PROD</span> <b>{rec["Production Grade"] || 0}</b> · <span style={{ color: REC_C["Needs Verification"] }}>VERIFY</span> <b>{rec["Needs Verification"] || 0}</b> · <span style={{ color: REC_C["Assumption Only"] }}>ASSUME</span> <b>{rec["Assumption Only"] || 0}</b></div>
          </div>
        </div>
      </div>

      <div className="border border-[#ffb224]/30 bg-[#ffb224]/5 px-3 py-2 mb-3 font-mono text-[10px] text-[#c9d4e0]" data-testid="fee-trust-verdict">
        <span className="text-[#ffb224] font-bold tracking-wider">TRUST VERDICT · </span>{d.trust_verdict}
      </div>

      <div className="overflow-x-auto" data-testid="fee-provenance-table">
        <table className="w-full text-[10px] font-mono">
          <thead>
            <tr className="panel-th text-[#6b7888]">
              <th className="text-left">Fee</th>
              <th className="text-left">Value</th>
              <th className="text-left">Class</th>
              <th className="text-left">Source</th>
              <th className="text-left">Refresh</th>
              <th className="text-center">Conf.</th>
              <th className="text-center">Grade</th>
              <th className="text-left">Consumers</th>
            </tr>
          </thead>
          <tbody>
            {(d.fees || []).map((f) => (
              <tr key={f.id} className="border-b border-[#1f2a36]/50" data-testid={`fee-row-${f.id}`}>
                <td className="py-1.5 pr-2 align-top text-[#c9d4e0] font-bold">{f.name}</td>
                <td className="py-1.5 pr-2 align-top text-[#8b97a6]">{fmtVal(f.current_value)} <span className="text-[#3d4a59]">{f.unit}</span></td>
                <td className="py-1.5 pr-2 align-top whitespace-nowrap" style={{ color: CLASS_C[f.classification] || "#8b97a6" }}>{f.classification}</td>
                <td className="py-1.5 pr-2 align-top text-[#6b7888] max-w-[280px]">{f.source}</td>
                <td className="py-1.5 pr-2 align-top text-[#6b7888]">{f.refresh_frequency}</td>
                <td className="py-1.5 px-1 align-top text-center text-[#8b97a6]">{f.confidence}</td>
                <td className="py-1.5 px-1 align-top text-center whitespace-nowrap" style={{ color: REC_C[f.recommendation] || "#8b97a6" }}>
                  <b>{f.recommendation}</b>
                </td>
                <td className="py-1.5 pl-2 align-top text-[#5a6573] text-[9px]">{(f.consumers || []).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap gap-2 mt-3" data-testid="fee-provenance-downloads">
        <button data-testid="fee-provenance-download-md"
                onClick={() => download("/execution/fee-provenance/download?format=md", "fee_provenance.md")}
                className="px-3 py-1 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 font-mono text-[10px] font-bold tracking-wider">
          ↓ DOWNLOAD MARKDOWN
        </button>
        <button data-testid="fee-provenance-download-json"
                onClick={() => download("/execution/fee-provenance/download?format=json", "fee_provenance.json")}
                className="px-3 py-1 border border-[#a78bfa] text-[#a78bfa] hover:bg-[#a78bfa]/10 font-mono text-[10px] font-bold tracking-wider">
          ↓ DOWNLOAD JSON
        </button>
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        Read-only provenance inspection. Identifies every assumption remaining in ROI calculations.
        Listed consumers cover Opportunity Engine, Gate, Arbitrage Intel, Certification, Safety Interlock,
        Sizing, and future E5. No execution.
      </div>
    </div>
  );
};
