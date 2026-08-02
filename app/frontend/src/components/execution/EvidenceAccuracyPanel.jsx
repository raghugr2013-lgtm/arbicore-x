import { useCallback, useEffect, useState } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const BUCKET_C = {
  "Exchange Sourced": "#34d399",
  "Blockchain Sourced": "#38bdf8",
  "Measured Transaction": "#a78bfa",
  "User Configured": "#ffb224",
  "Assumption": "#f87171",
};

export const EvidenceAccuracyPanel = () => {
  const [d, setD] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/execution/evidence-accuracy`).then((r) => setD(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [load]);

  if (!d) {
    return (
      <div className="panel" data-testid="evidence-accuracy-panel">
        <div className="panel-title">Evidence Accuracy Report</div>
        <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>
      </div>
    );
  }

  const s = d.summary || {};
  const snap = d.live_snapshot || {};
  const replaced = d.replaced || [];
  const remaining = d.remaining_assumptions || [];

  return (
    <div className="panel" data-testid="evidence-accuracy-panel">
      <div className="panel-title">
        Evidence Accuracy Report — assumptions replaced by real-world evidence
        <span className="float-right text-[#3d4a59]">read-only diff</span>
      </div>

      <div className="border border-[#34d399]/40 bg-[#0a120e] p-3 mb-3" data-testid="evidence-accuracy-summary">
        <div className="font-mono text-[10px] text-[#c9d4e0] mb-1">{s.headline}</div>
        <div className="flex flex-wrap gap-3 text-[10px] font-mono mt-2">
          <span>Replaced: <b className="text-[#34d399]" data-testid="ea-replaced-count">{s.assumptions_replaced_with_evidence}</b></span>
          <span>Remaining: <b className="text-[#ffb224]" data-testid="ea-remaining-count">{s.assumptions_remaining}</b></span>
          <span>Evidence grade: <b className="text-[#a78bfa]" data-testid="ea-pct-evidence">{s.pct_evidence_grade}%</b></span>
        </div>
      </div>

      {/* Assumption Status taxonomy (5-way bucket) */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="assumption-status-taxonomy">
        <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-1">ASSUMPTION STATUS · 5-way taxonomy</div>
        <div className="flex flex-wrap gap-2 font-mono text-[10px]">
          {(d.assumption_status_taxonomy || []).map((k) => (
            <span key={k} className="px-2 py-0.5 border" style={{ borderColor: BUCKET_C[k] + "66", color: BUCKET_C[k] }}>
              {k}
            </span>
          ))}
        </div>
      </div>

      {/* Live snapshot of consumed values */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="evidence-live-snapshot">
        <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-1">LIVE consumed values (right now)</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1 font-mono text-[10px]">
          <div><span className="text-[#6b7888]">BDAG transfer fee consumed:</span> <b className="text-[#a78bfa]">{snap.bdag_transfer_fee_consumed_bdag} BDAG</b> ({snap.bdag_transfer_evidence_count} measurements / window {snap.bdag_transfer_evidence_window})</div>
          <div><span className="text-[#6b7888]">Coinstore taker fee:</span> <b className="text-[#34d399]">{snap.coinstore_taker_fee_pct}%</b></div>
          <div><span className="text-[#6b7888]">Coinstore USDT BEP20 withdrawal:</span> <b className="text-[#34d399]">${snap.coinstore_usdt_withdrawal_fee_usd}</b></div>
          <div><span className="text-[#6b7888]">Coinstore BDAG deposit fee:</span> <b className="text-[#34d399]">${snap.coinstore_bdag_deposit_fee_usd}</b></div>
          <div><span className="text-[#6b7888]">Coinstore BDAG minimum deposit:</span> <b className="text-[#ffb224]">{snap.coinstore_bdag_minimum_deposit_bdag} BDAG</b></div>
        </div>
      </div>

      {/* Replaced (before → after) */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2 mb-3" data-testid="evidence-replaced">
        <div className="text-[9px] tracking-widest uppercase text-[#34d399] mb-2">REPLACED · assumption → evidence</div>
        <div className="space-y-2">
          {replaced.map((r) => (
            <div key={r.fee_id} className="grid grid-cols-1 md:grid-cols-[200px_1fr_24px_1fr] gap-2 items-start font-mono text-[10px] border-b border-[#1f2a36]/40 pb-2" data-testid={`evidence-replaced-${r.fee_id}`}>
              <div className="text-[#c9d4e0] font-bold">{r.fee_name}<br /><span className="text-[8px] text-[#3d4a59]">{r.fee_id}</span></div>
              <div className="border border-[#f87171]/30 bg-[#1a0d0d] p-2">
                <div className="text-[8px] uppercase tracking-widest text-[#f87171] mb-0.5">BEFORE · assumption-based</div>
                <div className="text-[#8b97a6]"><b>Class:</b> {r.before.classification}</div>
                <div className="text-[#8b97a6]"><b>Status:</b> {r.before.assumption_status}</div>
                <div className="text-[#5a6573]">Source: {r.before.source}</div>
                <div className="text-[#5a6573]">Confidence: {r.before.confidence} · Rec: {r.before.recommendation}</div>
              </div>
              <div className="text-[#a78bfa] text-center text-xl self-center">→</div>
              <div className="border border-[#34d399]/30 bg-[#0a130d] p-2">
                <div className="text-[8px] uppercase tracking-widest text-[#34d399] mb-0.5">AFTER · evidence-based</div>
                <div className="text-[#c9d4e0]"><b>Class:</b> {r.after.classification}</div>
                <div className="text-[#c9d4e0]"><b>Status:</b> {r.after.assumption_status}</div>
                <div className="text-[#8b97a6]">Source: {r.after.source}</div>
                <div className="text-[#8b97a6]">Confidence: {r.after.confidence} · Rec: {r.after.recommendation}</div>
                {r.magnitude_note && <div className="text-[#5a6573] mt-1 italic">{r.magnitude_note}</div>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Remaining */}
      <div className="border border-[#ffb224]/30 bg-[#11100a] p-2" data-testid="evidence-remaining">
        <div className="text-[9px] tracking-widest uppercase text-[#ffb224] mb-2">REMAINING ASSUMPTIONS</div>
        <div className="space-y-2 font-mono text-[10px]">
          {remaining.map((r) => (
            <div key={r.fee_id} className="border-b border-[#1f2a36]/40 pb-1" data-testid={`evidence-remaining-${r.fee_id}`}>
              <div className="text-[#c9d4e0] font-bold">{r.fee_name} <span className="text-[8px] text-[#3d4a59]">· {r.fee_id}</span></div>
              <div className="text-[#8b97a6]"><b>Class:</b> {r.current_classification}</div>
              <div className="text-[#6b7888]">Rationale: {r.rationale}</div>
              <div className="text-[#5a6573] italic">Action for E5: {r.action_for_e5}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">{d.note}</div>
    </div>
  );
};
