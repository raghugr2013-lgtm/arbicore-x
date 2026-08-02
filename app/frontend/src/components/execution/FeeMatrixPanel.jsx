import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const CONF = { high: "#34d399", medium: "#ffb224", low: "#f87171" };

const Num = ({ label, value, onChange, step = "0.01", testId }) => (
  <div>
    <div className="text-[8px] uppercase tracking-widest text-[#6b7888] mb-0.5">{label}</div>
    <input data-testid={testId} type="number" step={step} value={value} onChange={(e) => onChange(e.target.value)}
      className="w-full bg-[#0a0e13] border border-[#1f2a36] px-2 py-1 font-mono text-xs text-[#c9d4e0] focus:border-[#38bdf8] outline-none" />
  </div>
);

export const FeeMatrixPanel = () => {
  const [d, setD] = useState(null);
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => axios.get(`${API}/execution/fees`).then((r) => { setD(r.data); setF(r.data.fees); }).catch(() => {});
  useEffect(() => { load(); }, []);

  const set = (path, val) => {
    setF((prev) => {
      const n = JSON.parse(JSON.stringify(prev));
      const ks = path.split(".");
      let o = n;
      for (let i = 0; i < ks.length - 1; i++) o = o[ks[i]];
      o[ks[ks.length - 1]] = val === "" ? "" : Number(val);
      return n;
    });
  };

  const save = async () => {
    setBusy(true);
    try {
      await axios.patch(`${API}/execution/fees`, {
        purchase_gas_usd: Number(f.purchase_gas_usd),
        bdag_transfer_fee_base: Number(f.bdag_transfer_fee_base),
        taker_fee_pct: { bitmart: Number(f.taker_fee_pct.bitmart), coinstore: Number(f.taker_fee_pct.coinstore) },
        usdt_withdrawal_fee_usd: { bitmart: Number(f.usdt_withdrawal_fee_usd.bitmart), coinstore: Number(f.usdt_withdrawal_fee_usd.coinstore) },
      });
      toast.success("Fee overrides saved");
      load();
    } catch (e) { toast.error("Save failed"); } finally { setBusy(false); }
  };

  if (!f) return <div className="panel" data-testid="fee-matrix-panel"><div className="panel-title">Verified Fee Matrix</div><div className="font-mono text-[11px] text-[#6b7888]">loading…</div></div>;

  return (
    <div className="panel" data-testid="fee-matrix-panel">
      <div className="panel-title">Verified Fee Matrix (E4.6) — editable overrides</div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-3">
        <Num label="BitMart taker %" value={f.taker_fee_pct.bitmart} onChange={(v) => set("taker_fee_pct.bitmart", v)} testId="fee-taker-bitmart" />
        <Num label="Coinstore taker %" value={f.taker_fee_pct.coinstore} onChange={(v) => set("taker_fee_pct.coinstore", v)} testId="fee-taker-coinstore" />
        <Num label="BSC purchase gas $" value={f.purchase_gas_usd} onChange={(v) => set("purchase_gas_usd", v)} testId="fee-gas" />
        <Num label="BDAG transfer (base)" value={f.bdag_transfer_fee_base} step="0.0001" onChange={(v) => set("bdag_transfer_fee_base", v)} testId="fee-transfer" />
        <Num label="BitMart USDT wd $" value={f.usdt_withdrawal_fee_usd.bitmart} onChange={(v) => set("usdt_withdrawal_fee_usd.bitmart", v)} testId="fee-wd-bitmart" />
        <Num label="Coinstore USDT wd $" value={f.usdt_withdrawal_fee_usd.coinstore} onChange={(v) => set("usdt_withdrawal_fee_usd.coinstore", v)} testId="fee-wd-coinstore" />
      </div>
      <button data-testid="fee-save-btn" disabled={busy} onClick={save}
        className="px-3 py-1 mb-3 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 font-mono text-[10px] font-bold disabled:opacity-40">
        SAVE OVERRIDES
      </button>

      <div className="text-[8px] uppercase tracking-widest text-[#6b7888] mb-1">Verified defaults & provenance</div>
      <table className="w-full text-[9px] font-mono">
        <thead><tr className="panel-th"><th className="text-left">Fee item</th><th className="text-left">Value</th><th>Conf.</th><th className="text-left">Source</th></tr></thead>
        <tbody>
          {(d.provenance || []).map((p, i) => (
            <tr key={i} className="border-b border-[#1f2a36]/50">
              <td className="py-0.5 text-[#c9d4e0]">{p.item}</td>
              <td className="py-0.5 text-[#8b97a6]">{p.value}</td>
              <td className="py-0.5 text-center font-bold" style={{ color: CONF[p.confidence] }}>{p.confidence}</td>
              <td className="py-0.5 text-[#6b7888]">{p.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
