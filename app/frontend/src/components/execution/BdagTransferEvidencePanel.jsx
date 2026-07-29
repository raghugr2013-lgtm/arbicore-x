import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmtBdag = (v) =>
  v == null ? "—" : Number(v) < 0.001 ? Number(v).toExponential(3) : Number(v).toFixed(9);

export const BdagTransferEvidencePanel = () => {
  const [d, setD] = useState(null);
  const [form, setForm] = useState({ amount_bdag: "", fee_bdag: "", tx_hash: "", note: "" });
  const [posting, setPosting] = useState(false);

  const load = useCallback(() => {
    axios.get(`${API}/execution/bdag-transfers`).then((r) => setD(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  const submit = async (e) => {
    e.preventDefault();
    const a = parseFloat(form.amount_bdag);
    const f = parseFloat(form.fee_bdag);
    if (!(a > 0) || !(f >= 0)) {
      toast.error("Enter a positive BDAG amount and a non-negative measured fee.");
      return;
    }
    setPosting(true);
    try {
      await axios.post(`${API}/execution/bdag-transfers`, {
        amount_bdag: a, fee_bdag: f,
        tx_hash: form.tx_hash || null, note: form.note || null,
        source: form.tx_hash ? "blockchain_tx" : "operator_attested",
      });
      toast.success("Transfer measurement recorded.");
      setForm({ amount_bdag: "", fee_bdag: "", tx_hash: "", note: "" });
      load();
    } catch (err) {
      toast.error(`Record failed: ${err.message || err}`);
    } finally {
      setPosting(false);
    }
  };

  if (!d) {
    return (
      <div className="panel" data-testid="bdag-transfer-evidence-panel">
        <div className="panel-title">BDAG Transfer Fee Evidence</div>
        <div className="font-mono text-[11px] text-[#6b7888]">loading evidence…</div>
      </div>
    );
  }

  const ra = d.rolling_average || {};
  const recent = d.recent_transfers || [];

  return (
    <div className="panel" data-testid="bdag-transfer-evidence-panel">
      <div className="panel-title">
        BDAG Transfer Fee Evidence — wallet → exchange
        <span className="float-right text-[#3d4a59]">measured · rolling avg over ≤{ra.window}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-[#1f2a36] border border-[#1f2a36] mb-3 font-mono" data-testid="bdag-transfer-summary">
        <div className="bg-[#10161e] px-3 py-2">
          <div className="text-[8px] tracking-widest text-[#6b7888]">MEASUREMENTS</div>
          <div className="text-xl font-bold text-[#34d399]" data-testid="bdag-transfer-count">{ra.count ?? 0}</div>
        </div>
        <div className="bg-[#10161e] px-3 py-2">
          <div className="text-[8px] tracking-widest text-[#6b7888]">AVG FEE (BDAG)</div>
          <div className="text-xl font-bold text-[#a78bfa]" data-testid="bdag-transfer-avg">{fmtBdag(ra.avg_fee_bdag)}</div>
        </div>
        <div className="bg-[#10161e] px-3 py-2">
          <div className="text-[8px] tracking-widest text-[#6b7888]">MIN / MAX</div>
          <div className="text-[11px] font-bold text-[#c9d4e0]">{fmtBdag(ra.min_fee_bdag)} … {fmtBdag(ra.max_fee_bdag)}</div>
        </div>
        <div className="bg-[#10161e] px-3 py-2">
          <div className="text-[8px] tracking-widest text-[#6b7888]">MEDIAN</div>
          <div className="text-[11px] font-bold text-[#c9d4e0]">{fmtBdag(ra.median_fee_bdag)}</div>
        </div>
        <div className="bg-[#10161e] px-3 py-2">
          <div className="text-[8px] tracking-widest text-[#6b7888]">AVG AMOUNT (BDAG)</div>
          <div className="text-[11px] font-bold text-[#c9d4e0]">{ra.avg_amount_bdag ?? "—"}</div>
        </div>
      </div>

      <div className="overflow-x-auto border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="bdag-transfer-table">
        <table className="w-full text-[10px] font-mono">
          <thead><tr className="panel-th text-[#6b7888]">
            <th className="text-left">Time</th>
            <th className="text-right">Amount (BDAG)</th>
            <th className="text-right">Fee (BDAG)</th>
            <th className="text-left">Tx hash</th>
            <th className="text-left">Source</th>
            <th className="text-left">Note</th>
          </tr></thead>
          <tbody>
            {recent.length === 0 && (
              <tr><td colSpan={6} className="text-center py-3 text-[#3d4a59]">No measurements yet — add one below.</td></tr>
            )}
            {recent.map((t) => (
              <tr key={t.id} className="border-b border-[#1f2a36]/50" data-testid={`bdag-transfer-row-${t.id}`}>
                <td className="py-1 text-[#6b7888]">{fmtTime(t.created_at)}</td>
                <td className="py-1 text-right text-[#c9d4e0]">{t.amount_bdag}</td>
                <td className="py-1 text-right text-[#34d399]">{fmtBdag(t.fee_bdag)}</td>
                <td className="py-1 text-[#38bdf8] truncate max-w-[200px]">{t.tx_hash || "—"}</td>
                <td className="py-1 text-[#8b97a6]">{t.source}</td>
                <td className="py-1 text-[#5a6573] truncate max-w-[260px]">{t.note || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form onSubmit={submit} className="border border-[#1f2a36] bg-[#0a0e13] p-2 grid grid-cols-1 md:grid-cols-5 gap-2 items-end" data-testid="bdag-transfer-form">
        <div>
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Amount transferred (BDAG)</div>
          <input data-testid="bdag-transfer-amount-input" type="number" step="any" min="0" required
                 value={form.amount_bdag} onChange={(e) => setForm({ ...form, amount_bdag: e.target.value })}
                 className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
        </div>
        <div>
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Measured fee (BDAG)</div>
          <input data-testid="bdag-transfer-fee-input" type="number" step="any" min="0" required
                 value={form.fee_bdag} onChange={(e) => setForm({ ...form, fee_bdag: e.target.value })}
                 className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
        </div>
        <div>
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Tx hash (optional)</div>
          <input data-testid="bdag-transfer-hash-input" type="text"
                 value={form.tx_hash} onChange={(e) => setForm({ ...form, tx_hash: e.target.value })}
                 className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
        </div>
        <div>
          <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Note</div>
          <input data-testid="bdag-transfer-note-input" type="text"
                 value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })}
                 className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
        </div>
        <button data-testid="bdag-transfer-submit" type="submit" disabled={posting}
                className="px-3 py-1 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-50 font-mono text-[10px] font-bold tracking-wider">
          {posting ? "RECORDING…" : "+ ADD MEASUREMENT"}
        </button>
      </form>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        Replaces the hardcoded 0.001 BDAG assumption with the measured rolling average. Consumed by
        {" "}{(d.consumers || []).join(", ")}. No fund movement.
      </div>
    </div>
  );
};
