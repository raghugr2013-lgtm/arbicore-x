import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { fmtTime } from "@/lib/fmt";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const fmtPrice = (v) => (v == null ? "—" : Number(v).toExponential(4));
const fmtNum = (v) => (v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 }));

// Operator console snippet — runs inside the swap page after wallet connection.
// Observes fetch + XHR + WebSocket + __NEXT_DATA__ for BDAG-quote shaped payloads
// and PRINTS them in a clearly-formatted block the operator can paste into the
// manual capture form below. The snippet does NOT POST anywhere (cookie-less
// cross-origin) — it's strictly an in-console observer.
const BOOKMARKLET_SRC = `(()=>{const log=(t,o)=>console.log("%c[ArbiCore-CAP] "+t,"color:#34d399;font-weight:bold;",o);
const isQuote=(o)=>{try{if(!o||typeof o!=='object')return null;const flat=JSON.stringify(o);
const m=flat.match(/("(bdagAmount|bdagAllocated|youReceive|outputAmount|amountOut|bdag|tokens|toAmount)"\\s*:\\s*"?([0-9.eE+-]+))/i);
const a=flat.match(/("(amount|usdAmount|payAmount|payUsd|fromAmount|inputAmount|amountIn)"\\s*:\\s*"?([0-9.eE+-]+))/i);
if(m&&a){const bdag=parseFloat(m[3]),input=parseFloat(a[3]);
if(bdag>1000&&input>0&&input<1e6)return{input_amount:input,bdag_allocated:bdag,raw:o};} }catch(e){}return null;};
const showCap=(src,o)=>{const q=isQuote(o);if(q){q.source=src;q.effective_price=q.input_amount/q.bdag_allocated;
console.log("%c┌─────── CAPTURED QUOTE ───────┐","color:#a78bfa;font-weight:bold;");
console.log("%c│ source: "+src,"color:#c9d4e0;");
console.log("%c│ input_amount: "+q.input_amount,"color:#c9d4e0;");
console.log("%c│ bdag_allocated: "+q.bdag_allocated,"color:#c9d4e0;");
console.log("%c│ effective_price: $"+q.effective_price.toExponential(4)+"/BDAG","color:#34d399;font-weight:bold;");
console.log("%c└──────────────────────────────┘","color:#a78bfa;");
console.log("Paste into ArbiCore's Quote Capture form ↓");}};
const of=window.fetch;window.fetch=async(...a)=>{const r=await of(...a);try{const c=r.clone();c.json().then(j=>showCap("swap_ui_api_response",j)).catch(()=>{});}catch(e){}return r;};
const OXHR=window.XMLHttpRequest;window.XMLHttpRequest=function(){const x=new OXHR();const oo=x.open;x.open=function(...a){this._url=a[1];return oo.apply(x,a);};
x.addEventListener('load',()=>{try{const j=JSON.parse(x.responseText);showCap("swap_ui_xhr:"+x._url,j);}catch(e){}});return x;};
const OWS=window.WebSocket;window.WebSocket=function(...a){const w=new OWS(...a);w.addEventListener('message',(ev)=>{try{const j=JSON.parse(ev.data);showCap("swap_ui_websocket",j);}catch(e){}});return w;};
log("Quote Capture probe armed. Type an amount in the swap input now.",null);})();`;

const COMPACT_BOOKMARKLET = BOOKMARKLET_SRC.replace(/\s+/g, " ").replace(/\n/g, "");

export const QuoteCapturePanel = () => {
  const [d, setD] = useState(null);
  const [form, setForm] = useState({ input_amount: "50", bdag_allocated: "", source: "swap_ui_state_observed", note: "" });
  const [posting, setPosting] = useState(false);
  const [snippetShown, setSnippetShown] = useState(false);

  const load = useCallback(() => {
    axios.get(`${API}/execution/quote-capture`).then((r) => setD(r.data)).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const previewEff = useMemo(() => {
    const a = parseFloat(form.input_amount), b = parseFloat(form.bdag_allocated);
    return a > 0 && b > 0 ? a / b : null;
  }, [form.input_amount, form.bdag_allocated]);

  const submit = async (e) => {
    e.preventDefault();
    const a = parseFloat(form.input_amount), b = parseFloat(form.bdag_allocated);
    if (!(a > 0) || !(b > 0)) { toast.error("Enter positive input + BDAG amounts."); return; }
    setPosting(true);
    try {
      await axios.post(`${API}/execution/quote-capture`, {
        input_amount: a, bdag_allocated: b,
        source: form.source || "manual",
        note: form.note || null,
      });
      toast.success(`Quote captured · $${(a/b).toExponential(4)}/BDAG`);
      setForm({ ...form, bdag_allocated: "", note: "" });
      load();
    } catch (err) {
      toast.error(`Capture failed: ${err.response?.data?.detail || err.message}`);
    } finally { setPosting(false); }
  };

  const copySnippet = async () => {
    try {
      await navigator.clipboard.writeText(COMPACT_BOOKMARKLET);
      toast.success("Bookmarklet copied. Paste into swap page DevTools console after wallet connection.");
    } catch { toast.error("Copy failed — select the snippet manually."); }
  };

  if (!d) return (
    <div className="panel" data-testid="quote-capture-panel">
      <div className="panel-title">Executable Quote Capture</div>
      <div className="font-mono text-[11px] text-[#6b7888]">loading…</div>
    </div>
  );

  const latest = d.latest || {};
  const rolling = d.rolling || {};
  const recent = d.recent_captures || [];
  const fresh = latest.available && latest.fresh;

  return (
    <div className="panel" data-testid="quote-capture-panel">
      <div className="panel-title">
        Executable Quote Capture — operator-attested pre-trade BDAG allocations
        <span className="float-right text-[#3d4a59]">PRIMARY buy-price authority · {rolling.count || 0} captures</span>
      </div>

      {/* Authoritative latest banner */}
      <div className="border p-3 mb-3"
           style={{ borderColor: (fresh ? "#34d399" : "#6b7888") + "66",
                    background: (fresh ? "#34d399" : "#6b7888") + "1a" }}
           data-testid="quote-capture-latest">
        <div className="flex items-baseline justify-between flex-wrap gap-3">
          <div>
            <div className="text-[9px] tracking-widest uppercase"
                 style={{ color: fresh ? "#34d399" : "#6b7888" }}>
              {fresh ? "AUTHORITATIVE · fresh capture" : "NO FRESH CAPTURE"}
            </div>
            <div className="font-mono text-2xl font-bold mt-0.5"
                 style={{ color: fresh ? "#34d399" : "#6b7888" }}
                 data-testid="quote-capture-latest-price">
              {latest.available ? `$${fmtPrice(latest.effective_price)}` : "—"}
              {latest.available && <span className="text-[10px] text-[#6b7888]"> / BDAG</span>}
            </div>
            {latest.available && (
              <div className="text-[10px] font-mono text-[#c9d4e0] mt-1">
                from ${latest.input_amount} → <b>{fmtNum(latest.bdag_allocated)}</b> BDAG ·
                source <b>{latest.source}</b> · age <b>{latest.age_s}s</b>
                {" "}/ fresh ≤ {latest.fresh_window_s}s
              </div>
            )}
          </div>
          {rolling.count > 0 && (
            <div className="font-mono text-[10px] text-[#8b97a6] max-w-[420px] text-right">
              rolling-{rolling.rolling_window} mean ${fmtPrice(rolling.avg_effective_price)} ·
              median ${fmtPrice(rolling.median_effective_price)} ·
              range [${fmtPrice(rolling.min_effective_price)} – ${fmtPrice(rolling.max_effective_price)}]
            </div>
          )}
        </div>
      </div>

      {/* Bookmarklet snippet (collapsible) */}
      <div className="border border-[#38bdf8]/30 bg-[#0a1018] p-2 mb-3" data-testid="quote-capture-bookmarklet">
        <div className="flex items-baseline justify-between mb-1">
          <span className="text-[9px] tracking-widest uppercase text-[#38bdf8]">
            CONSOLE PROBE · paste into swap page DevTools after wallet connection
          </span>
          <div className="flex gap-2">
            <button data-testid="quote-capture-copy-snippet" onClick={copySnippet}
                    className="px-2 py-0.5 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 font-mono text-[9px] font-bold tracking-wider">
              COPY
            </button>
            <button data-testid="quote-capture-toggle-snippet" onClick={() => setSnippetShown(!snippetShown)}
                    className="px-2 py-0.5 border border-[#1f2a36] text-[#6b7888] hover:text-[#c9d4e0] font-mono text-[9px] font-bold tracking-wider">
              {snippetShown ? "HIDE" : "SHOW"}
            </button>
          </div>
        </div>
        <div className="font-mono text-[10px] text-[#c9d4e0]">
          1. Connect MetaMask to <code className="text-[#38bdf8]">purchase3.blockdag.network/swap</code> ·
          2. Open DevTools → Console ·
          3. Paste snippet · run ·
          4. Type a USDT amount in the swap input ·
          5. Each BDAG-quote shape detected in fetch/XHR/WebSocket prints a "CAPTURED QUOTE" block ·
          6. Copy the values into the form below ↓
        </div>
        {snippetShown && (
          <pre className="mt-2 p-2 bg-[#0a0e13] border border-[#1f2a36] font-mono text-[9px] text-[#c9d4e0] whitespace-pre-wrap break-all max-h-[180px] overflow-y-auto">
            {COMPACT_BOOKMARKLET}
          </pre>
        )}
        <div className="font-mono text-[8px] text-[#3d4a59] mt-1">
          The probe is OBSERVE-ONLY — it does not POST or transmit anything. It only prints what it sees
          in the page's own network traffic. Nothing is signed or submitted.
        </div>
      </div>

      {/* Manual capture form */}
      <form onSubmit={submit} className="border border-[#34d399]/40 bg-[#0a120e] p-3 mb-3" data-testid="quote-capture-form">
        <div className="text-[9px] tracking-widest uppercase text-[#34d399] mb-2">
          MANUAL CAPTURE · type the values the swap UI shows
        </div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-2 items-end">
          <div>
            <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Input amount</div>
            <input data-testid="quote-capture-input-amount" type="number" step="any" min="0" required
                   value={form.input_amount}
                   onChange={(e) => setForm({ ...form, input_amount: e.target.value })}
                   className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
          </div>
          <div>
            <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">BDAG allocated</div>
            <input data-testid="quote-capture-bdag-allocated" type="number" step="any" min="0" required
                   placeholder="e.g. 1388889"
                   value={form.bdag_allocated}
                   onChange={(e) => setForm({ ...form, bdag_allocated: e.target.value })}
                   className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
          </div>
          <div>
            <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Source</div>
            <select data-testid="quote-capture-source"
                    value={form.source}
                    onChange={(e) => setForm({ ...form, source: e.target.value })}
                    className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]">
              <option value="swap_ui_state_observed">swap_ui_state_observed</option>
              <option value="swap_ui_api_response">swap_ui_api_response</option>
              <option value="swap_ui_websocket">swap_ui_websocket</option>
              <option value="swap_ui_pre_signature_payload">swap_ui_pre_signature_payload</option>
              <option value="manual_screenshot">manual_screenshot</option>
              <option value="manual">manual</option>
            </select>
          </div>
          <div>
            <div className="text-[8px] uppercase tracking-widest text-[#6b7888]">Note</div>
            <input data-testid="quote-capture-note" type="text" value={form.note}
                   onChange={(e) => setForm({ ...form, note: e.target.value })}
                   className="w-full bg-[#0e141c] border border-[#1f2a36] px-2 py-1 font-mono text-[11px] text-[#c9d4e0]" />
          </div>
          <button data-testid="quote-capture-submit" type="submit" disabled={posting}
                  className="px-3 py-1 border border-[#34d399] text-[#34d399] hover:bg-[#34d399]/10 disabled:opacity-50 font-mono text-[10px] font-bold tracking-wider">
            {posting ? "RECORDING…" : "+ CAPTURE"}
          </button>
        </div>
        {previewEff != null && (
          <div className="mt-2 font-mono text-[10px] text-[#a78bfa]">
            preview · effective price = <b>${previewEff.toExponential(4)}</b> / BDAG
          </div>
        )}
      </form>

      {/* Recent captures table */}
      <div className="border border-[#1f2a36] bg-[#0a0e13] p-2" data-testid="quote-capture-history">
        <div className="text-[9px] tracking-widest uppercase text-[#6b7888] mb-1">
          RECENT CAPTURES ({recent.length})
        </div>
        {recent.length === 0 ? (
          <div className="font-mono text-[10px] text-[#3d4a59] py-3 text-center">No captures yet — paste the probe or use the manual form.</div>
        ) : (
          <table className="w-full text-[10px] font-mono">
            <thead><tr className="panel-th text-[#6b7888]">
              <th className="text-left">When</th>
              <th className="text-right">Input</th>
              <th className="text-right">BDAG</th>
              <th className="text-right">Eff. price</th>
              <th className="text-left">Source</th>
              <th className="text-left">Note</th>
            </tr></thead>
            <tbody>
              {recent.map((c) => (
                <tr key={c.id} className="border-b border-[#1f2a36]/40" data-testid={`quote-capture-row-${c.id}`}>
                  <td className="py-1 text-[#6b7888]">{fmtTime(c.created_at)}</td>
                  <td className="py-1 text-right text-[#c9d4e0]">{c.input_token} {c.input_amount}</td>
                  <td className="py-1 text-right text-[#c9d4e0]">{fmtNum(c.bdag_allocated)}</td>
                  <td className="py-1 text-right text-[#34d399] font-bold">${fmtPrice(c.effective_price)}</td>
                  <td className="py-1 text-[#a78bfa]">{c.source}</td>
                  <td className="py-1 text-[#5a6573] truncate max-w-[280px]">{c.note || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="font-mono text-[8px] text-[#3d4a59] mt-2">
        Precedence in the Quote Resolver above: <b className="text-[#34d399]">captured_quote</b> (fresh &lt; {latest.fresh_window_s || 300}s)
        → executed_calibration (rolling-avg) → ui_quote_api (wallet-gated, stub) → sw_api_fallback.
        No execution. No signing. No fund movement.
      </div>
    </div>
  );
};
