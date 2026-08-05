// ==UserScript==
// @name         ArbiCore Companion
// @namespace    arbicore
// @version      1.0.0
// @description  Observe-only: capture pre-trade BDAG executable quotes from purchase3.blockdag.network/swap and POST them to ArbiCore. Does NOT sign, submit, or touch MetaMask flow.
// @match        https://purchase3.blockdag.network/*
// @match        https://*.coinstore.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      *
// @run-at       document-start
// ==/UserScript==

/* global GM_xmlhttpRequest, GM_setValue, GM_getValue */

(function () {
  'use strict';

  // ─── Configure once, then forget ────────────────────────────────────
  // 1. Paste your ArbiCore preview URL:
  const ARBICORE_BASE = GM_getValue('arbicore_base',
    'https://arbix-router-repair.preview.emergentagent.com');
  // 2. Paste the Quote Capture key from ArbiCore Settings (one-time):
  const QUOTE_KEY = GM_getValue('arbicore_key', '');

  if (!QUOTE_KEY) {
    console.warn('[ArbiCore] No quote-capture key set. Run: GM_setValue("arbicore_key", "<KEY>") from a userscript console.');
  }

  const log = (...a) => console.log('%c[ArbiCore]', 'color:#34d399;font-weight:bold;', ...a);

  // ─── Heartbeat (proves connectivity) ────────────────────────────────
  GM_xmlhttpRequest({
    method: 'GET',
    url: ARBICORE_BASE + '/api/public/quote-capture/health',
    onload: (r) => log('connected →', r.status, r.responseText && r.responseText.slice(0, 120)),
    onerror: (e) => log('ArbiCore unreachable', e),
  });

  // ─── Quote shape detector ───────────────────────────────────────────
  function findQuote(obj) {
    try {
      const flat = JSON.stringify(obj);
      // Look for BDAG-allocation-shaped fields and pairing input-amount fields.
      const m = flat.match(/"(bdagAmount|bdagAllocated|youReceive|outputAmount|amountOut|bdag|tokens|toAmount|receive(?:Amount)?)"\s*:\s*"?([0-9.eE+-]+)/i);
      const a = flat.match(/"(amount|usdAmount|payAmount|payUsd|fromAmount|inputAmount|amountIn|spend(?:Amount)?)"\s*:\s*"?([0-9.eE+-]+)/i);
      if (!m || !a) return null;
      const bdag = parseFloat(m[2]);
      const input = parseFloat(a[2]);
      // Sanity guards — BDAG comes in 6+ digit allocations for $1+ inputs.
      if (!(bdag > 1000 && input > 0 && input < 1e7)) return null;
      return { input_amount: input, bdag_allocated: bdag };
    } catch (e) { return null; }
  }

  function send(quote, source, raw) {
    if (!QUOTE_KEY) return;
    GM_xmlhttpRequest({
      method: 'POST',
      url: ARBICORE_BASE + '/api/public/quote-capture',
      headers: { 'Content-Type': 'application/json', 'X-ArbiCore-Quote-Key': QUOTE_KEY },
      data: JSON.stringify({ ...quote, source, raw: raw ? Object.assign({}, raw) : null,
                             note: 'userscript ' + location.host }),
      onload: (r) => log('captured', source, '→', r.status, '· $' + (quote.input_amount / quote.bdag_allocated).toExponential(4) + '/BDAG'),
      onerror: () => log('POST failed', source),
    });
  }

  // ─── fetch + XHR + WebSocket interceptors ───────────────────────────
  const _fetch = window.fetch;
  window.fetch = async (...args) => {
    const r = await _fetch(...args);
    try {
      const c = r.clone();
      const ct = c.headers.get('content-type') || '';
      if (ct.includes('json')) {
        c.json().then((j) => {
          const q = findQuote(j);
          if (q) send(q, 'swap_ui_api_response', j);
        }).catch(() => {});
      }
    } catch (e) { /* swallow */ }
    return r;
  };

  const OX = window.XMLHttpRequest;
  window.XMLHttpRequest = function () {
    const x = new OX();
    const oo = x.open;
    x.open = function (...a) { this._url = a[1]; return oo.apply(x, a); };
    x.addEventListener('load', () => {
      try {
        const j = JSON.parse(x.responseText);
        const q = findQuote(j);
        if (q) send(q, 'swap_ui_xhr', { url: x._url, body: j });
      } catch (e) { /* not json */ }
    });
    return x;
  };

  const OWS = window.WebSocket;
  window.WebSocket = function (...args) {
    const w = new OWS(...args);
    w.addEventListener('message', (ev) => {
      try {
        const j = JSON.parse(ev.data);
        const q = findQuote(j);
        if (q) send(q, 'swap_ui_websocket', j);
      } catch (e) { /* not json */ }
    });
    return w;
  };

  log('armed on', location.host, '— ArbiCore base', ARBICORE_BASE, '— key', QUOTE_KEY ? 'SET' : 'MISSING');
})();
