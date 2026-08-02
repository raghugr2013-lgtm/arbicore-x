import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const VERDICT = {
  READ_VERIFIED: { c: "#34d399", t: "READ VERIFIED" },
  NEEDS_READONLY_KEY: { c: "#ffb224", t: "NEEDS READ-ONLY KEY" },
  KEY_ERROR: { c: "#f87171", t: "KEY ERROR" },
  CONNECTIVITY_ERROR: { c: "#f87171", t: "CONNECTIVITY ERROR" },
};
const CAP = {
  verified: "#34d399", pending: "#ffb224", failed: "#f87171",
  declared_untested: "#6b7888", unknown_untested: "#6b7888", "n/a": "#6b7888", pass: "#34d399", fail: "#f87171",
};
const ICON = { pass: "✓", verified: "✓", pending: "○", fail: "✕", failed: "✕", "n/a": "—", declared_untested: "·", unknown_untested: "·" };

const VenueCard = ({ v, onVerify, onRemove }) => {
  const vd = VERDICT[v.verdict] || { c: "#6b7888", t: v.verdict };
  return (
    <div className="border border-[#1f2a36] bg-[#0a0e13] p-3" data-testid={`integration-venue-${v.exchange}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-xs font-bold">{v.venue_name} <span className="text-[#6b7888]">· {v.role.toUpperCase()}</span></span>
        <span data-testid={`integration-verdict-${v.exchange}`} className="font-mono text-[10px] font-bold px-1.5 py-0.5 border"
              style={{ borderColor: vd.c, color: vd.c }}>{vd.t}</span>
      </div>
      <div className="flex items-center gap-2 mb-2">
        <div className="flex-1 h-1.5 bg-[#1f2a36]">
          <div className="h-full" style={{ width: `${v.readiness_score}%`, background: vd.c }} />
        </div>
        <span className="font-mono text-[10px] font-bold" style={{ color: vd.c }}>{v.readiness_score}%</span>
      </div>
      <div className="font-mono text-[9px] text-[#8b97a6] mb-2">
        connectivity: <span style={{ color: v.connectivity.ok ? "#34d399" : "#f87171" }}>{v.connectivity.ok ? "OK" : "FAIL"}</span>
        {v.connectivity.latency_ms != null && ` · ${v.connectivity.latency_ms}ms`} · {v.connectivity.detail}
      </div>

      <div className="text-[8px] uppercase tracking-widest text-[#6b7888] mb-1">Capability verification</div>
      <div className="space-y-0.5 mb-2">
        {v.capabilities.map((c) => (
          <div key={c.cap} className="flex items-center justify-between font-mono text-[9px]">
            <span className="text-[#8b97a6]">{c.label} {c.write && <span className="text-[#f87171]">⚠write</span>}</span>
            <span style={{ color: CAP[c.status] || "#6b7888" }}>{ICON[c.status] || "·"} {c.status} <span className="text-[#3d4a59]">({c.tier})</span></span>
          </div>
        ))}
      </div>

      <div className="text-[8px] uppercase tracking-widest text-[#6b7888] mb-1">Checklist</div>
      <div className="space-y-0.5 mb-2">
        {v.checklist.map((c, i) => (
          <div key={i} className="flex items-center gap-1.5 font-mono text-[9px]">
            <span style={{ color: CAP[c.status] || "#6b7888" }}>{ICON[c.status] || "·"}</span>
            <span className="text-[#8b97a6]">{c.item}</span>
            <span className="text-[#3d4a59] truncate">— {c.detail}</span>
          </div>
        ))}
      </div>

      <div className="font-mono text-[9px] text-[#6b7888] border-t border-[#1f2a36] pt-1.5 mb-2">
        health: REST {v.health.rest_success_rate_pct ?? "—"}% ok · {v.health.rest_avg_latency_ms ?? "—"}ms · poll {v.health.balance_poll_status || "—"}
      </div>

      {v.key ? (
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[9px] text-[#6b7888] truncate">key {v.key.key_mask} · {v.key.status}</span>
          <div className="flex gap-1 shrink-0">
            <button data-testid={`integration-verify-${v.exchange}`} onClick={() => onVerify(v.key.id, v.exchange)}
                    className="term-btn-secondary">VERIFY</button>
            <button data-testid={`integration-remove-${v.exchange}`} onClick={() => onRemove(v.key.id, v.exchange)}
                    className="font-mono text-[10px] font-bold px-2 py-1 border border-[#f87171]/50 text-[#f87171] hover:bg-[#f87171]/10">REMOVE</button>
          </div>
        </div>
      ) : (
        <div className="font-mono text-[9px] text-[#ffb224]">No read-only key — add one below to verify credentials.</div>
      )}
    </div>
  );
};

export const IntegrationPrepPanel = () => {
  const [status, setStatus] = useState(null);
  const [monitor, setMonitor] = useState(null);
  const [form, setForm] = useState({ exchange: "coinstore", label: "", api_key: "", api_secret: "", passphrase: "" });

  const load = useCallback(() => {
    axios.get(`${API}/execution/integration/status`).then((r) => setStatus(r.data)).catch(() => {});
    axios.get(`${API}/execution/integration/monitor`).then((r) => setMonitor(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  const verify = async (keyId, ex) => {
    try {
      const { data } = await axios.post(`${API}/execution/integration/verify/${keyId}`);
      const ok = data.read_permission_verified;
      ok ? toast.success(`${ex.toUpperCase()} read access verified`)
         : toast.error(`${ex.toUpperCase()}: ${data.credential_validation.message}`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Verify failed");
    }
  };

  const removeKey = async (keyId, ex) => {
    try {
      await axios.delete(`${API}/vault/keys/${keyId}`);
      toast.success(`${ex.toUpperCase()} key removed`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Remove failed");
    }
  };

  const addKey = async () => {
    try {
      const body = { exchange: form.exchange, label: form.label || `${form.exchange} read-only`,
        api_key: form.api_key.trim(), api_secret: form.api_secret.trim() };
      if (form.passphrase.trim()) body.passphrase = form.passphrase.trim();
      const { data } = await axios.post(`${API}/vault/keys`, body);
      toast.success("Read-only key stored — verifying…");
      setForm({ ...form, label: "", api_key: "", api_secret: "", passphrase: "" });
      await verify(data.id, form.exchange);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Add key failed");
    }
  };

  return (
    <div className="panel" data-testid="integration-prep-panel">
      <div className="panel-title">
        Real API Integration Prep (E4) — read-only
        <span className="float-right text-[#3d4a59]">no trading · no withdrawals · no fund movement</span>
      </div>

      {monitor && (
        <div className="flex flex-wrap gap-3 mb-3 font-mono text-[9px] text-[#6b7888]" data-testid="integration-monitor-strip">
          <span>connectivity monitor: <span style={{ color: monitor.running ? "#34d399" : "#6b7888" }}>{monitor.running ? "● up" : "○ down"}</span> · every {monitor.probe_interval_s}s</span>
          {Object.entries(monitor.venues || {}).map(([ex, m]) => (
            <span key={ex}>{ex.toUpperCase()}: {m.success_rate_pct ?? "—"}% ok · {m.avg_latency_ms ?? "—"}ms ({m.samples})</span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-3">
        {(status?.venues || []).map((v) => <VenueCard key={v.exchange} v={v} onVerify={verify} onRemove={removeKey} />)}
      </div>

      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="integration-add-key-form">
        <div className="text-[10px] uppercase tracking-widest text-[#6b7888] mb-2">Add a READ-ONLY exchange key</div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="block">
            <span className="text-[9px] uppercase tracking-widest text-[#6b7888]">Exchange</span>
            <select data-testid="key-exchange-select" value={form.exchange} onChange={(e) => setForm({ ...form, exchange: e.target.value })} className="term-input w-28">
              <option value="coinstore">COINSTORE</option>
              <option value="bitmart">BITMART</option>
            </select>
          </label>
          <label className="block"><span className="text-[9px] uppercase tracking-widest text-[#6b7888]">Label</span>
            <input data-testid="key-label-input" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} className="term-input w-28" placeholder="read-only" /></label>
          <label className="block"><span className="text-[9px] uppercase tracking-widest text-[#6b7888]">API key</span>
            <input data-testid="key-apikey-input" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} className="term-input w-40" /></label>
          <label className="block"><span className="text-[9px] uppercase tracking-widest text-[#6b7888]">API secret</span>
            <input data-testid="key-apisecret-input" type="password" value={form.api_secret} onChange={(e) => setForm({ ...form, api_secret: e.target.value })} className="term-input w-40" /></label>
          {form.exchange === "bitmart" && (
            <label className="block"><span className="text-[9px] uppercase tracking-widest text-[#6b7888]">Memo</span>
              <input data-testid="key-memo-input" value={form.passphrase} onChange={(e) => setForm({ ...form, passphrase: e.target.value })} className="term-input w-28" /></label>
          )}
          <button data-testid="add-key-btn" onClick={addKey} className="term-btn-primary">+ STORE & VERIFY</button>
        </div>
        <div className="font-mono text-[9px] text-[#3d4a59] mt-2">
          Secrets are Fernet-encrypted at rest and never returned. Create the key with READ-ONLY scope — E4 verifies read access only.
        </div>
      </div>
    </div>
  );
};
