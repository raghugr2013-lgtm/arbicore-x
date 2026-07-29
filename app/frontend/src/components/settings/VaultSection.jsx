import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { formatApiErrorDetail } from "@/context/AuthContext";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const EXCHANGES = ["xt", "mexc", "gate", "bitmart", "coinstore"];

const StatusBadge = ({ status }) => {
  const map = {
    healthy: "border-[#34d399] text-[#34d399] bg-[#34d399]/10",
    error: "border-[#f87171] text-[#f87171] bg-[#f87171]/10",
    untested: "border-[#6b7888] text-[#6b7888]",
  };
  return (
    <span className={`font-mono text-[9px] font-bold tracking-wider px-2 py-0.5 border ${map[status] || map.untested}`}>
      {(status || "untested").toUpperCase()}
    </span>
  );
};

export const VaultSection = () => {
  const [keys, setKeys] = useState([]);
  const [form, setForm] = useState({ exchange: "xt", label: "", api_key: "", api_secret: "", passphrase: "" });
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(null);

  const load = useCallback(() => {
    axios.get(`${API}/vault/keys`).then((r) => setKeys(r.data)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const addKey = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await axios.post(`${API}/vault/keys`, {
        ...form,
        label: form.label || undefined,
        passphrase: form.passphrase || undefined,
      });
      toast.success("Key stored — encrypted at rest (Fernet)");
      setForm({ exchange: "xt", label: "", api_key: "", api_secret: "", passphrase: "" });
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    }
    setBusy(false);
  };

  const testKey = async (id) => {
    setTesting(id);
    try {
      const { data } = await axios.post(`${API}/vault/keys/${id}/test`);
      data.ok ? toast.success(data.message) : toast.error(data.message);
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    }
    setTesting(null);
  };

  const deleteKey = async (id) => {
    await axios.delete(`${API}/vault/keys/${id}`).catch(() => {});
    toast.success("Key deleted");
    load();
  };

  return (
    <div className="space-y-4" data-testid="vault-section">
      <div className="border border-[#f87171]/40 bg-[#f87171]/5 px-3 py-2 font-mono text-[11px] text-[#f87171]" data-testid="vault-readonly-banner">
        READ-ONLY KEYS ONLY — grant only “Read” permission when creating exchange keys. ArbiCore never trades, withdraws, or moves funds.
      </div>

      <div className="panel">
        <div className="panel-title">Stored keys ({keys.length})</div>
        {keys.length === 0 && <div className="font-mono text-[11px] text-[#6b7888] py-2">no keys stored yet</div>}
        {keys.length > 0 && (
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="panel-th">
                <th className="text-left">Exchange</th><th className="text-left">Label</th>
                <th className="text-left">Key</th><th className="text-left">Status</th>
                <th className="text-left">Last test</th><th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id} className="border-b border-[#1f2a36]/50" data-testid={`vault-row-${k.id}`}>
                  <td className="py-2 uppercase font-bold">{k.exchange}</td>
                  <td className="text-[#6b7888]">{k.label}</td>
                  <td className="text-[#6b7888]" data-testid={`vault-mask-${k.id}`}>{k.key_mask}</td>
                  <td data-testid={`vault-status-${k.id}`}><StatusBadge status={k.status} /></td>
                  <td className="text-[10px] text-[#6b7888]">
                    {k.last_tested_at ? fmtTime(k.last_tested_at) : "—"}
                    {k.last_test_message && <div className="max-w-[220px] truncate" title={k.last_test_message}>{k.last_test_message}</div>}
                  </td>
                  <td className="text-right whitespace-nowrap">
                    <button data-testid={`vault-test-btn-${k.id}`} onClick={() => testKey(k.id)} disabled={testing === k.id}
                            className="font-mono text-[10px] font-bold px-2 py-1 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 mr-2 disabled:opacity-50">
                      {testing === k.id ? "TESTING…" : "TEST"}
                    </button>
                    <button data-testid={`vault-delete-btn-${k.id}`} onClick={() => deleteKey(k.id)}
                            className="font-mono text-[10px] font-bold px-2 py-1 border border-[#f87171] text-[#f87171] hover:bg-[#f87171]/10">
                      DELETE
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel">
        <div className="panel-title">Add read-only key</div>
        <form onSubmit={addKey} className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Exchange</label>
            <select data-testid="vault-add-exchange" value={form.exchange}
                    onChange={(e) => setForm({ ...form, exchange: e.target.value })}
                    className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none">
              {EXCHANGES.map((ex) => <option key={ex} value={ex}>{ex.toUpperCase()}</option>)}
            </select>
          </div>
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Label (optional)</label>
            <input data-testid="vault-add-label" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}
                   placeholder="e.g. main read-only"
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">API key</label>
            <input data-testid="vault-add-key" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                   required minLength={8} autoComplete="off"
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">API secret</label>
            <input data-testid="vault-add-secret" type="password" value={form.api_secret}
                   onChange={(e) => setForm({ ...form, api_secret: e.target.value })}
                   required minLength={8} autoComplete="off"
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
          <div>
            <label className="block font-mono text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Memo / passphrase (BitMart)</label>
            <input data-testid="vault-add-passphrase" value={form.passphrase}
                   onChange={(e) => setForm({ ...form, passphrase: e.target.value })}
                   autoComplete="off" placeholder="optional"
                   className="w-full bg-[#0a0f14] border border-[#1f2a36] px-3 py-2 font-mono text-sm text-[#c9d4e0] focus:border-[#ffb224] focus:outline-none" />
          </div>
          <div className="flex items-end">
            <button data-testid="vault-add-submit" type="submit" disabled={busy}
                    className="w-full font-mono text-[11px] font-bold tracking-widest px-3 py-2 border border-[#34d399] text-[#34d399] bg-[#34d399]/10 hover:bg-[#34d399]/20 disabled:opacity-50">
              {busy ? "STORING…" : "STORE ENCRYPTED"}
            </button>
          </div>
        </form>
        <p className="mt-3 font-mono text-[9px] text-[#3d4a59]">
          Secrets are encrypted with Fernet (AES-128-CBC + HMAC) before hitting the database and are never returned by the API.
          “TEST” performs a single read-only balance call to verify the key works.
        </p>
      </div>
    </div>
  );
};
