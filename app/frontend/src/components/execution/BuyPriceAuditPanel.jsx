import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtPrice = (v) => (v == null ? "—" : Number(v).toExponential(4));
const fmtPct = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(3)}%`);
const fmtNum = (v) => (v == null ? "—" : Number(v).toLocaleString());

const SEV_C = { critical: "#f87171", informational: "#ffb224" };

export const BuyPriceAuditPanel = () => {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    investment_usd: "50", bdag_received: "", reported_ui_price: "", note: "",
  });
  const [posting, setPosting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    axios.get(`${API}/execution/buy-price-audit`)
      .then((r) => setD(r.data)).catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    const inv = parseFloat(form.investment_usd);
    const recv = parseFloat(form.bdag_received);
    if (!(inv > 0) || !(recv > 0)) {
      toast.error("Enter positive USDT amount and BDAG received.");
      return;
    }
    setPosting(true);
    try {
      await axios.post(`${API}/execution/buy-price-audit/empirical`, {
        investment_usd: inv, bdag_received: recv,
        reported_ui_price: form.reported_ui_price ? parseFloat(form.reported_ui_price) : null,
        note: form.note || null,
      });
      toast.success(`Recorded · effective price ≈ $${(inv / recv).toExponential(4)}/BDAG`);
      setForm({ investment_usd: "50", bdag_received: "", reported_ui_price: "", note: "" });
      load();
    } catch (err) {
      toast.error(`Record failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setPosting(false);
    }
  };

  if (!d) {
    return (
      <div className="panel" data-testid="buy-price-audit-panel">
        <div className="panel-title">BlockDAG Buy-Price Source Audit</div>
        <div className="font-mono text-[11px] text-[#6b7888]">loading audit…</div>
      </div>
    );
  }

  const primary = d.primary_sources || [];
  const secondary = d.secondary_sources || [];
  const usedRoi = d.price_used_for_roi || {};
  const ds = d.discrepancy_summary || {};
  const eq = d.empirical_quotes || {};
  const uiDelta = ds.ui_vs_sw_api_pct;
  const uiSev = ds.ui_vs_sw_api_severity;

  return (
    <div className="panel" data-testid="buy-price-audit-panel">
      <div className="panel-title">
        BlockDAG Buy-Price Source Audit — 5 sources side-by-side
        <span className="float-right text-[#3d4a59]">
          read-only{loading && <span className="text-[#38bdf8] ml-2">↻</span>}
        </span>
      </div>

      {/* PRICE USED FOR ROI banner */}
      <div className="border border-[#a78bfa]/60 bg-[#13102b] p-3 mb-3" data-testid="audit-price-used-banner">
        <div className="flex items-baseline justify-between flex-wrap gap-3">
          <div>
            <div className="text-[9px] tracking-widest uppercase text-[#a78bfa]">PRICE USED FOR ROI</div>
            <div className="font-mono text-2xl font-bold text-[#a78bfa] mt-0.5" data-testid="audit-roi-price">
              ${fmtPrice(usedRoi.value)} <span className="text-[10px] text-[#6b7888]">/ BDAG</span>
            </div>
            <div className="text-[10px] font-mono text-[#c9d4e0]" data-testid="audit-roi-source">
              source: <b>{usedRoi.source || "—"}</b>
            </div>
          </div>
          <pre className="font-mono text-[10px] text-[#c9d4e0] whitespace-pre-wrap max-w-[640px] flex-1 m-0" data-testid="audit-roi-explanation">
{usedRoi.explanation || ""}
          </pre>
        </div>
      </div>

      {/* UI vs API critical-discrepancy banner */}
      {uiDelta != null && (
        <div className="border p-2 mb-3 font-mono text-[10px]"
             style={{ borderColor: SEV_C[uiSev] + "88", background: SEV_C[uiSev] + "1a" }}
             data-testid="audit-ui-discrepancy">
          <span className="font-bold" style={{ color: SEV_C[uiSev] }}>
            {uiSev === "critical" ? "🔴 CRITICAL DISCREPANCY · " : "⚠ INFORMATIONAL · "}
          </span>
          UI displayed price <b>{fmtPrice(primary[0]?.value)}</b> vs sw-api/getInfo <b>{fmtPrice(primary[1]?.value)}</b>
          {" "}→ delta <b>{fmtPct(uiDelta)}</b> ·
          {uiSev === "critical"
            ? " This MUST be resolved before any execution development. Likely cause: the swap UI applies a bonus/discount on top of the API price that ArbiCore cannot see."
            : " Within tolerance."}
        </div>
      )}

      {/* Side-by-side 5 primary sources */}
      <div className="overflow-x-auto mb-3" data-testid="audit-primary-sources">
        <table className="w-full text-[10px] font-mono">
          <thead><tr className="panel-th text-[#6b7888]">
            <th className="text-left">#</th>
            <th className="text-left">Source</th>
            <th className="text-right">Price ($/BDAG)</th>
            <th className="text-left">Timestamp</th>
            <th className="text-center">Used for ROI</th>
            <th className="text-left">Notes</th>
          </tr></thead>
          <tbody>
            {primary.map((r) => (
              <tr key={r.slot}
                  className={`border-b border-[#1f2a36]/60 ${r.used_for_roi ? "bg-[#a78bfa]/5" : ""}`}
                  data-testid={`audit-primary-${r.slot}`}>
                <td className="py-2 px-1 align-top text-[#a78bfa] font-bold">{r.slot}</td>
                <td className="py-2 pr-2 align-top text-[#c9d4e0] font-bold">
                  {r.label}
                  {r.source_url && (
                    <div className="text-[8px] mt-0.5">
                      <a href={r.source_url} target="_blank" rel="noreferrer"
                         className="text-[#38bdf8] underline truncate inline-block max-w-[280px]">
                        {r.source_url}
                      </a>
                    </div>
                  )}
                </td>
                <td className="py-2 pr-2 align-top text-right">
                  <span className="text-[#c9d4e0] font-bold text-[12px]" data-testid={`audit-primary-${r.slot}-price`}>
                    {r.value != null ? `$${fmtPrice(r.value)}` : "—"}
                  </span>
                  {r.latency_ms != null && (
                    <div className="text-[8px] text-[#5a6573]">{r.latency_ms}ms</div>
                  )}
                  {r.age_s != null && (
                    <div className="text-[8px]" style={{ color: r.stale ? "#f87171" : "#5a6573" }}>
                      age {r.age_s}s {r.stale ? "STALE" : ""}
                    </div>
                  )}
                </td>
                <td className="py-2 pr-2 align-top text-[#6b7888]">{fmtTime(r.timestamp)}</td>
                <td className="py-2 px-1 align-top text-center">
                  {r.used_for_roi ? (
                    <span className="inline-block px-2 py-0.5 bg-[#a78bfa] text-[#0a0e13] font-bold text-[9px] tracking-wider"
                          data-testid={`audit-primary-${r.slot}-roi-badge`}>★ ROI</span>
                  ) : (
                    <span className="text-[#3d4a59]">—</span>
                  )}
                </td>
                <td className="py-2 pl-2 align-top text-[#8b97a6] max-w-[420px]">{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Secondary observability sources */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="audit-secondary">
        <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-1">SECONDARY OBSERVABILITY · not consumed by ArbiCore</div>
        <table className="w-full text-[10px] font-mono">
          <tbody>
            {secondary.map((r, i) => (
              <tr key={i} className="border-b border-[#1f2a36]/40" data-testid={`audit-secondary-${i}`}>
                <td className="py-1 pr-2 text-[#c9d4e0] font-bold">{r.label}</td>
                <td className="py-1 pr-2 text-right text-[#8b97a6]">{r.value != null ? `$${fmtPrice(r.value)}` : "—"}</td>
                <td className="py-1 pr-2 text-[#3d4a59]">{r.latency_ms != null ? `${r.latency_ms}ms` : ""}</td>
                <td className="py-1 pl-2 text-[#5a6573]">{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {secondary.find((r) => r.extras?.implied_price_from_latest_orders) && (
          <div className="text-[9px] text-[#3d4a59] mt-1 font-mono">
            Presale orderBook implied price (latest 5 orders) ≈ ${fmtPrice(secondary.find((r) => r.extras?.implied_price_from_latest_orders).extras.implied_price_from_latest_orders)} ·
            stage {secondary.find((r) => r.extras?.stage)?.extras?.stage} · next stage price ${secondary.find((r) => r.extras?.next_stage_price)?.extras?.next_stage_price}
          </div>
        )}
      </div>

      {/* Discrepancies list */}
      {(d.discrepancies || []).length > 0 && (
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="audit-discrepancies">
          <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-1">
            DISCREPANCIES vs sw-api/getInfo · critical: <span className="text-[#f87171] font-bold">{ds.critical_count}</span> ·
            informational: <span className="text-[#ffb224] font-bold">{ds.informational_count}</span>
          </div>
          <table className="w-full text-[10px] font-mono">
            <tbody>
              {(d.discrepancies || []).map((x, i) => (
                <tr key={i} data-testid={`audit-discrepancy-${i}`}>
                  <td className="py-1 pr-2 text-[#c9d4e0]">{x.source}</td>
                  <td className="py-1 pr-2 text-right text-[#8b97a6]">${fmtPrice(x.source_value)}</td>
                  <td className="py-1 px-2 text-center" style={{ color: SEV_C[x.severity] }}>{fmtPct(x.delta_pct)}</td>
                  <td className="py-1 pl-2 font-bold" style={{ color: SEV_C[x.severity] }}>{x.severity.toUpperCase()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empirical Test form ($X → BDAG received → effective price) */}
      <div className="border border-[#34d399]/40 bg-[#0a120e] p-3 mb-3" data-testid="audit-empirical-form">
        <div className="text-[9px] tracking-widest uppercase text-[#34d399] mb-2">
          EMPIRICAL TEST · pin the actual UI-displayed executable price
        </div>
        <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-5 gap-2 items-end">
          <div>
            <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Input (USDT)</div>
            <input data-testid="audit-empirical-investment" type="number" step="any" min="0" required
                   value={form.investment_usd}
                   onChange={(e) => setForm({ ...form, investment_usd: e.target.value })}
                   className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
          </div>
          <div>
            <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">BDAG received</div>
            <input data-testid="audit-empirical-received" type="number" step="any" min="0" required
                   value={form.bdag_received}
                   onChange={(e) => setForm({ ...form, bdag_received: e.target.value })}
                   className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
          </div>
          <div>
            <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">UI displayed price (optional)</div>
            <input data-testid="audit-empirical-ui-price" type="number" step="any" min="0"
                   placeholder="e.g. 0.000036"
                   value={form.reported_ui_price}
                   onChange={(e) => setForm({ ...form, reported_ui_price: e.target.value })}
                   className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
          </div>
          <div>
            <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Note</div>
            <input data-testid="audit-empirical-note" type="text"
                   value={form.note}
                   onChange={(e) => setForm({ ...form, note: e.target.value })}
                   className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
          </div>
          <button data-testid="audit-empirical-submit" type="submit" disabled={posting}
                  className="px-3 py-1 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-50 font-mono text-[10px] font-bold tracking-wider">
            {posting ? "RECORDING…" : "+ RECORD TEST"}
          </button>
        </form>
        <div className="text-[8px] text-[#3d4a59] mt-2 font-mono">
          Effective price = USDT ÷ BDAG received. This is the only way to capture what the wallet-gated swap UI actually
          quotes — no purchase or fund movement is required, just record the UI’s on-screen preview.
        </div>
      </div>

      {/* Empirical history */}
      {eq.count > 0 && (
        <div className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="audit-empirical-history">
          <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-1">
            EMPIRICAL TEST HISTORY ({eq.count}) · avg effective = ${fmtPrice(eq.avg_effective_price)} ·
            median = ${fmtPrice(eq.median_effective_price)}
          </div>
          <table className="w-full text-[9px] font-mono">
            <thead><tr className="panel-th text-[#6b7888]">
              <th className="text-left">When</th>
              <th className="text-right">USDT in</th>
              <th className="text-right">BDAG received</th>
              <th className="text-right">Effective $/BDAG</th>
              <th className="text-right">UI displayed $/BDAG</th>
              <th className="text-left">Note</th>
            </tr></thead>
            <tbody>
              {(eq.samples || []).slice(0, 12).map((q) => (
                <tr key={q.id} className="border-b border-[#1f2a36]/40" data-testid={`audit-empirical-row-${q.id}`}>
                  <td className="py-1 text-[#6b7888]">{fmtTime(q.created_at)}</td>
                  <td className="py-1 text-right text-[#c9d4e0]">${q.investment_usd}</td>
                  <td className="py-1 text-right text-[#c9d4e0]">{fmtNum(q.bdag_received)}</td>
                  <td className="py-1 text-right text-[#34d399] font-bold">${fmtPrice(q.effective_price)}</td>
                  <td className="py-1 text-right text-[#ffb224]">{q.reported_ui_price ? `$${fmtPrice(q.reported_ui_price)}` : "—"}</td>
                  <td className="py-1 text-[#5a6573] truncate max-w-[280px]">{q.note || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">{d.note}</div>
    </div>
  );
};
