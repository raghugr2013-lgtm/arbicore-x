// ==UserScript==
// @name         ArbiCore Companion v2 (Multi-size Batch)
// @namespace    arbicore
// @version      2.1.0
// @description  Multi-size verified-quote capture for BlockDAG Live Swap.  v2.1 adds DOM-reading capture (auto-detects the USDT input + BDAG output rendered in the swap UI) and a manual CAPTURE NOW button, because the swap UI computes its quote client-side and never fires a network call we can sniff.  Network sniffing kept as a secondary path.  Includes a diagnostic mode that logs every DOM scan + a TEST MODE that fabricates quotes locally.  Observe-only — never signs, never moves funds.
// @match        https://purchase3.blockdag.network/*
// @match        https://*.coinstore.com/*
// @match        about:blank
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
// @connect      *
// @run-at       document-start
// ==/UserScript==

/* global GM_xmlhttpRequest, GM_setValue, GM_getValue, GM_registerMenuCommand */
/* eslint-disable no-undef */
/* oxlint-disable no-undef */

(function () {
  'use strict';

  // ── Config (persisted via GM_setValue) ────────────────────────────────────
  const ARBICORE_BASE = GM_getValue('arbicore_base',
    'https://flashloan-readiness.preview.emergentagent.com');
  const QUOTE_KEY = GM_getValue('arbicore_key', '');
  const TEST_MODE = GM_getValue('arbicore_test_mode', false) === true;
  const DEBUG = GM_getValue('arbicore_debug', false) === true;
  const SIZE_TOL_PCT = 5;          // a quote matches a target size if within ±5%
  const BATCH_WINDOW_S = 90;       // batch is "complete" once all sizes filled OR 90s elapses
  const FLUSH_DEBOUNCE_MS = 1200;
  const DOM_POLL_INTERVAL_MS = 700;
  const DOM_STABLE_MS = 1500;      // a value pair must hold steady this long before we trust it

  const log = (...a) => console.log('%c[ArbiCore-v2]', 'color:#34d399;font-weight:bold;', ...a);
  const warn = (...a) => console.warn('%c[ArbiCore-v2]', 'color:#ffb224;font-weight:bold;', ...a);
  const dbg = (...a) => { if (DEBUG) console.log('%c[ArbiCore-v2 dbg]', 'color:#6b7888', ...a); };

  GM_registerMenuCommand('Set ArbiCore base URL', () => {
    const v = prompt('ArbiCore base URL', GM_getValue('arbicore_base', ARBICORE_BASE));
    if (v) { GM_setValue('arbicore_base', v); log('arbicore_base saved →', v); }
  });
  GM_registerMenuCommand('Set ArbiCore quote-capture key', () => {
    const v = prompt('Quote-capture key', GM_getValue('arbicore_key', QUOTE_KEY));
    if (v) { GM_setValue('arbicore_key', v); log('arbicore_key saved'); }
  });
  GM_registerMenuCommand('Toggle TEST MODE', () => {
    const next = !(GM_getValue('arbicore_test_mode', false) === true);
    GM_setValue('arbicore_test_mode', next);
    alert('ArbiCore TEST MODE → ' + (next ? 'ON (reload page)' : 'OFF (reload page)'));
  });
  GM_registerMenuCommand('Toggle DEBUG logging', () => {
    const next = !(GM_getValue('arbicore_debug', false) === true);
    GM_setValue('arbicore_debug', next);
    alert('ArbiCore DEBUG → ' + (next ? 'ON (reload page)' : 'OFF (reload page)'));
  });

  // ── State ─────────────────────────────────────────────────────────────────
  let targets = [];                  // [{size_usd, captured, effective_price, captured_at, source}]
  let batchStartedAt = 0;
  let flushTimer = null;
  let lastScan = { usd: null, bdag: null, since: 0 };   // for DOM-stability detection
  let lastIngestPair = null;         // dedup last successful capture
  window.__arbicore = {              // expose for devtools poking
    scan: () => scanDOM(),
    state: () => ({ targets, lastScan, lastIngestPair, TEST_MODE, DEBUG }),
    captureNow: () => captureCurrentDOM(true),
  };

  function fetchTargets() {
    const stored = GM_getValue('arbicore_target_sizes', '');
    let sizes = [];
    if (stored && typeof stored === 'string') {
      sizes = stored.split(',').map((s) => parseFloat(s.trim())).filter((n) => n >= 50);
    }
    if (!sizes.length) sizes = [50, 100, 150];
    targets = sizes.map((s) => ({ size_usd: s, captured: false }));
    renderPanel();
  }

  // ── Network sniffer (secondary path) ─────────────────────────────────────
  function findQuoteInJson(obj) {
    try {
      const flat = JSON.stringify(obj);
      const m = flat.match(/"(bdagAmount|bdagAllocated|youReceive|outputAmount|amountOut|bdag|tokens|toAmount|receive(?:Amount)?)"\s*:\s*"?([0-9.eE+-]+)/i);
      const a = flat.match(/"(amount|usdAmount|payAmount|payUsd|fromAmount|inputAmount|amountIn|spend(?:Amount)?)"\s*:\s*"?([0-9.eE+-]+)/i);
      if (!m || !a) return null;
      const bdag = parseFloat(m[2]);
      const input = parseFloat(a[2]);
      if (!(bdag > 1000 && input > 0 && input < 1e7)) return null;
      return { input_amount: input, bdag_allocated: bdag };
    } catch (e) { return null; }
  }

  // ── DOM reader (PRIMARY path) ────────────────────────────────────────────
  function isVisible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return false;
    const s = window.getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none';
  }

  function parseNum(s) {
    if (!s) return null;
    const cleaned = String(s).replace(/[,\s]/g, '');
    const n = parseFloat(cleaned);
    return isNaN(n) ? null : n;
  }

  // Find the most likely USDT-input value on the page.
  function readUsdtInputValue() {
    const inputs = [...document.querySelectorAll('input')];
    let best = null;
    for (const el of inputs) {
      if (!isVisible(el)) continue;
      const v = parseNum(el.value);
      if (v == null) continue;
      // sensible USDT input range
      if (v < 1 || v > 100000) continue;
      // prefer inputs near text containing "USDT" or "USD"
      let score = v;
      const labelText = (el.closest('div,section,form')?.textContent || '').toUpperCase();
      if (/USDT|USD\b/.test(labelText)) score += 1e6;
      if (el.placeholder && /amount|usdt/i.test(el.placeholder)) score += 1e5;
      if (!best || score > best.score) best = { value: v, el, score };
    }
    return best ? best.value : null;
  }

  // Find the most likely BDAG output value on the page.
  // Heuristic: search every visible text-node element for "<number> BDAG"
  // OR any element where the immediate sibling text contains "BDAG" and the node
  // value is a large number (BDAG quantities are typically > 1000 per $1).
  function readBdagOutputValue() {
    // 1. text containing "<number> BDAG" or "BDAG <number>"
    const all = [...document.querySelectorAll('div,span,p,strong,em,b,td,h1,h2,h3,h4,h5,h6,output,label')];
    let best = null;
    for (const el of all) {
      if (!isVisible(el)) continue;
      if (el.children.length > 6) continue;   // skip large containers
      const t = (el.textContent || '').trim();
      if (!t || t.length > 80) continue;
      if (!/\bBDAG\b/i.test(t)) continue;
      // strip currency words and parse the largest numeric token
      const nums = (t.match(/[\d,]+\.?\d*/g) || []).map(parseNum).filter((n) => n != null && n > 100);
      if (!nums.length) continue;
      const v = Math.max(...nums);
      if (v < 1000) continue;        // BDAG is high-supply: $50 typically yields > 1M BDAG
      if (!best || v > best.value) best = { value: v, el };
    }
    return best ? best.value : null;
  }

  function scanDOM() {
    const usd = readUsdtInputValue();
    const bdag = readBdagOutputValue();
    const result = { usd, bdag, ts: Date.now() };
    dbg('scanDOM', result);
    return result;
  }

  function captureCurrentDOM(manual = false) {
    const { usd, bdag } = scanDOM();
    if (!(usd && bdag)) {
      if (manual) warn('CAPTURE NOW failed — no usd input or no bdag output detected. Toggle DEBUG and check console.');
      return false;
    }
    // dedup
    if (lastIngestPair && lastIngestPair.usd === usd && lastIngestPair.bdag === bdag) {
      if (manual) warn('CAPTURE NOW: same pair as last capture — no new bucket filled.');
      return false;
    }
    lastIngestPair = { usd, bdag };
    log('captured (DOM)', { usd, bdag });
    ingest({ input_amount: usd, bdag_allocated: bdag }, manual ? 'dom_manual' : 'dom_auto',
           { method: 'dom', usd, bdag });
    return true;
  }

  // Poll the DOM. If the same (usd, bdag) pair holds steady for DOM_STABLE_MS,
  // auto-capture it.
  function startDomPolling() {
    setInterval(() => {
      const { usd, bdag } = scanDOM();
      if (!(usd && bdag)) {
        lastScan = { usd: null, bdag: null, since: 0 };
        return;
      }
      const stable = lastScan.usd === usd && lastScan.bdag === bdag && lastScan.since > 0;
      if (!stable) {
        lastScan = { usd, bdag, since: Date.now() };
        return;
      }
      if (Date.now() - lastScan.since >= DOM_STABLE_MS) {
        if (captureCurrentDOM(false)) {
          // pause auto-capture briefly so we don't re-fire for the same pair
          lastScan.since = Date.now() + 2000;
        }
      }
    }, DOM_POLL_INTERVAL_MS);
  }

  // ── Capture pipeline (shared) ────────────────────────────────────────────
  function bucketForSize(input_usd) {
    let best = null;
    let bestDelta = Infinity;
    for (const t of targets) {
      const delta = Math.abs((input_usd - t.size_usd) / t.size_usd) * 100;
      if (delta <= SIZE_TOL_PCT && delta < bestDelta) {
        best = t; bestDelta = delta;
      }
    }
    return best;
  }

  function ingest(quote, source, raw) {
    const { input_amount, bdag_allocated } = quote;
    const effective_price = input_amount / bdag_allocated;
    const t = bucketForSize(input_amount);
    if (!t) {
      dbg('ingest: no bucket for', input_amount, '— targets:', targets.map((x) => x.size_usd));
      return;
    }
    if (!batchStartedAt) batchStartedAt = Date.now();
    t.captured = true;
    t.effective_price = effective_price;
    t.bdag_quoted = bdag_allocated;
    t.captured_at = new Date().toISOString();
    t.captured_at_ts = Math.floor(Date.now() / 1000);
    t.source = source;
    t.raw = raw;
    renderPanel();
    scheduleFlush();
  }

  function scheduleFlush() {
    if (flushTimer) clearTimeout(flushTimer);
    flushTimer = setTimeout(() => {
      const allDone = targets.every((t) => t.captured);
      const tooOld = batchStartedAt && (Date.now() - batchStartedAt) / 1000 > BATCH_WINDOW_S;
      if (allDone || tooOld) flushBatch();
    }, FLUSH_DEBOUNCE_MS);
  }

  function flushBatch() {
    const captures = targets.filter((t) => t.captured).map((t) => ({
      size_usd: t.size_usd,
      effective_price: t.effective_price,
      bdag_quoted: t.bdag_quoted,
      captured_at: t.captured_at,
      source: t.source || 'userscript_v2',
      raw: t.raw || null,
    }));
    if (!captures.length) { warn('nothing to flush'); return; }
    if (!QUOTE_KEY) { warn('missing key — set arbicore_key via menu'); return; }
    GM_xmlhttpRequest({
      method: 'POST',
      url: ARBICORE_BASE + '/api/public/quote-capture-batch',
      headers: { 'Content-Type': 'application/json', 'X-ArbiCore-Quote-Key': QUOTE_KEY },
      data: JSON.stringify({ captures, sent_from: location.host, v: '2.1', test_mode: TEST_MODE }),
      onload: (r) => {
        log('batch posted →', r.status, r.responseText && r.responseText.slice(0, 160));
        targets.forEach((t) => { t.captured = false; t.effective_price = undefined; });
        batchStartedAt = 0;
        lastIngestPair = null;
        renderPanel();
      },
      onerror: () => warn('batch POST failed'),
    });
  }

  // ── Floating panel ───────────────────────────────────────────────────────
  function renderPanel() {
    if (typeof document === 'undefined') return;
    let el = document.getElementById('arbicore-panel-v2');
    if (!el) {
      el = document.createElement('div');
      el.id = 'arbicore-panel-v2';
      el.style.cssText = `
        position:fixed;bottom:12px;right:12px;z-index:2147483647;
        background:#0a0e13;border:1px solid #1f2a36;color:#c9d4e0;
        padding:10px 12px;font:11px/1.4 monospace;min-width:300px;
        box-shadow:0 4px 20px rgba(0,0,0,0.6);border-radius:2px;`;
      document.body && document.body.appendChild(el);
    }
    if (!document.body) {
      window.addEventListener('DOMContentLoaded', renderPanel, { once: true });
      return;
    }
    const filled = targets.filter((t) => t.captured).length;
    const total = targets.length;
    const seen = lastScan && lastScan.usd ? `${lastScan.usd} ⇢ ${lastScan.bdag ? lastScan.bdag.toLocaleString() : '—'} BDAG` : 'idle';
    el.innerHTML = `
      <div style="color:#34d399;font-weight:bold;letter-spacing:0.5px;margin-bottom:4px;">
        ARBICORE COMPANION v2.1 ${TEST_MODE ? '· TEST' : ''} ${DEBUG ? '· DBG' : ''}
      </div>
      <div style="color:#6b7888;margin-bottom:2px;">batch ${filled}/${total} · ${ARBICORE_BASE.replace(/^https?:\/\//,'').slice(0,32)}…</div>
      <div style="color:#5a6573;margin-bottom:6px;">seeing: ${seen}</div>
      ${targets.map((t) => `
        <div style="display:flex;justify-content:space-between;padding:2px 0;">
          <span style="color:${t.captured?'#34d399':'#8b97a6'}">${t.captured?'✓':'○'} $${t.size_usd}</span>
          <span style="color:#5a6573">${t.captured ? t.effective_price.toExponential(3) : '—'}</span>
        </div>`).join('')}
      <div style="display:flex;gap:6px;margin-top:8px;">
        <button id="arbicore-v2-capture" style="flex:2;background:#0f1419;color:#34d399;border:1px solid #34d399;padding:4px 6px;cursor:pointer;font:10px monospace;font-weight:bold;">CAPTURE NOW</button>
        <button id="arbicore-v2-flush" style="flex:1;background:#1f2a36;color:#c9d4e0;border:1px solid #1f2a36;padding:4px 6px;cursor:pointer;font:10px monospace;">FLUSH</button>
        <button id="arbicore-v2-reset" style="flex:1;background:#1f2a36;color:#f87171;border:1px solid #1f2a36;padding:4px 6px;cursor:pointer;font:10px monospace;">RESET</button>
        ${TEST_MODE ? `<button id="arbicore-v2-mock" style="flex:1;background:#1f2a36;color:#ffb224;border:1px solid #1f2a36;padding:4px 6px;cursor:pointer;font:10px monospace;">MOCK</button>` : ''}
      </div>
      <div style="color:#3d4a59;font-size:9px;margin-top:6px;">${QUOTE_KEY ? 'key SET' : 'key MISSING'} · type then <b>CAPTURE NOW</b> per size · auto-cap after ${DOM_STABLE_MS}ms steady</div>
    `;
    document.getElementById('arbicore-v2-capture').onclick = () => captureCurrentDOM(true);
    document.getElementById('arbicore-v2-flush').onclick = flushBatch;
    document.getElementById('arbicore-v2-reset').onclick = () => {
      targets.forEach((t) => { t.captured = false; t.effective_price = undefined; });
      batchStartedAt = 0; lastIngestPair = null; renderPanel();
    };
    if (TEST_MODE) document.getElementById('arbicore-v2-mock').onclick = mockFillAll;
  }

  // ── TEST MODE — fabricate quotes (pipeline check, no swap UI needed) ────
  function mockFillAll() {
    const base = parseFloat(GM_getValue('arbicore_test_buy_price', '0.0000391'));
    targets.forEach((t, i) => {
      const px = base * (1 + (i * 0.0008));
      const bdag = t.size_usd / px;
      ingest({ input_amount: t.size_usd, bdag_allocated: bdag },
             'userscript_v2_test_mode', { mocked: true, base });
    });
    log('mock-filled all sizes');
  }

  // ── Network interception (secondary; harmless when nothing matches) ────
  if (!TEST_MODE) {
    const _fetch = window.fetch;
    window.fetch = async (...args) => {
      const r = await _fetch(...args);
      try {
        const c = r.clone();
        const ct = c.headers.get('content-type') || '';
        if (ct.includes('json')) {
          c.json().then((j) => {
            const q = findQuoteInJson(j);
            if (q) { log('captured (network fetch)', q); ingest(q, 'swap_ui_api_response', j); }
          }).catch(() => {});
        }
      } catch (e) {}
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
          const q = findQuoteInJson(j);
          if (q) { log('captured (network xhr)', q); ingest(q, 'swap_ui_xhr', { url: x._url }); }
        } catch (e) {}
      });
      return x;
    };
  }

  fetchTargets();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { renderPanel(); startDomPolling(); }, { once: true });
  } else {
    renderPanel();
    startDomPolling();
  }

  log('v2.1 armed on', location.host, '·', TEST_MODE ? 'TEST MODE' : 'live capture', DEBUG ? '· DBG ON' : '');
})();
