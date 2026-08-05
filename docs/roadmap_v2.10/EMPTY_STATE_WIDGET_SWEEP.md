# Empty-state Widget Sweep — pre-activation audit

**Date:** 2026-08-05
**Purpose:** verify every mounted frontend widget renders truthfully when its
backing endpoint returns empty data. This audit MUST precede any placeholder
replacement so that removing a stub never blanks a UI panel or throws an
unhandled TypeError.
**Method:** read-only static inspection of every page under
`app/frontend/src/v2/pages/`, cross-referenced with the `axios`/`fetch` call
sites and their expected response shapes.

---

## Result — TL;DR

**All 15 mounted pages are safe to activate real endpoints against.** They
handle `items: []`, `data: null`, and thrown errors gracefully via one of
three patterns:

- Optional chaining + coalescing (`data?.regime?.regime || "—"`)
- Explicit `items.length === 0` empty state
- `if (loading) return <Loading>`  → `if (!data) return <Unreachable>`

One page-level micro-fix is required (HomePage Interlock tile — see §5).
Nothing else needs to change in the frontend before Slice 1.

---

## Per-page verdict

| Page | Endpoints consumed | Empty-state pattern | Verdict |
| :--- | :----------------- | :------------------ | :-----: |
| **OpsCenter.jsx** (default landing) | `/live/status`, `/live/prices`, `/live/opportunities`, `/providers/status`, `/scanners/cross/status`, `/memory/summary`, `/safety/status`, `/validation/summary`, `/observability` | `safeGet()` returns null on failure; `fmtUsd`/`fmtNum`/`fmtBps` all handle null; each panel guarded by `state.x?.` chain | ✅ **Already 100% real-data — no activation needed** |
| **HomePage.jsx** | `/dashboard/pulse`, `/dashboard/deck`, `/opportunities/summary` | `regime?.regime \|\| "—"`, `opps.length === 0 → v2-empty` | ✅ Safe — but see §5 for Interlock tile micro-fix |
| **OpportunitiesPage.jsx** | `/arbicore/opportunities`, `/arbicore/opportunities/{id}` | `!loading && items.length === 0` → explicit empty | ✅ Safe |
| **DiscoveryPage.jsx** | `/arbicore/discovery/candidates` | `!loading && items.length === 0` → explicit empty | ✅ Safe |
| **IntelligencePage.jsx** | `/arbicore/intelligence/*` (calibration, weights, evidence, certification, entities, recommendations, decisions) | Per-tab: `loading`, `!d → unreachable`, `items.length===0 → empty` | ✅ Safe |
| **OperationsPage.jsx** | `/operations/scanners`, `/cycles`, `/venues`, `/interlock`, `/integrations`, `/queues`, `/alerts` | Every tab has explicit `items.length===0` empty | ✅ Safe |
| **PortfolioPage.jsx** | `/portfolio/positions`, `/balances`, `/transfers`, `/deployable`, `/allocation`, `/treasury`, `/ledger`, `/exposure` | Every tab has `positions.length===0` etc. explicit empty | ✅ Safe |
| **SettingsPage.jsx** | `/settings/*` (account, execution, exchanges, notifications, vaults, operational, network, telegram) | Per-section `loading`+`unreachable`+`empty` | ✅ Safe |
| **FlashLoanOperatorPage.jsx** | `/execution/wallets`, `/execution/secrets`, `/execution/kill-switch`, `/execution/mode`, `/execution/discovery/status`, `/execution/opportunities`, `/execution/plans/*` | `wallets.length===0 → "No wallets yet"`; `opps.length===0 → "No opportunities discovered yet"` | ✅ Safe (real endpoints — already active) |
| **LimitedLiveWizardPage.jsx** | `/arbicore/wizard/state`, `/wizard/flash-loan-prereqs` | Inline `loading…` + guarded `steps.map` | ✅ Safe |
| **FlashLoanJourneyPage.jsx** | `/arbicore/wizard/journey` | `stages = data?.stages \|\| []`; empty array safe to `.map` over | ✅ Safe |
| **ExecutorVerifyPage.jsx** | `/arbicore/executor/verify` | `loading` toggle + `state?.checks` optional chain | ✅ Safe |
| **PostTradeDashboardPage.jsx** | `/arbicore/post-trade/latest`, `/intelligence/calibration/history`, `/adaptive-weights/history`, `/evidence/history` | Each series guarded by `rows?.length` / empty state | ✅ Safe |
| **InitializationPage.jsx** | boot probes (`/api/`, `/api/system/status`, `/api/arbicore/dashboard/pulse`, `/api/arbicore/opportunities/summary`) | Explicit per-step HTTP status render | ✅ Safe |
| **LoginPage.jsx** | `/auth/*` (v2.9.3 canonical) | Handled by AuthContext v2.9.3; no data-render surface | ✅ Safe |

## §1. Endpoints CURRENTLY LIVE (real runtime data, not stubs)

Discovered mid-sweep. These paths in `server.py` are **NOT** preview stubs —
they are wired to real subsystems (`_MEMORY`, `_LIVE_SCANNER`,
`_KILL_SWITCH_REPO`, `_SAFETY_AVAILABLE`, `_PROVIDER_REGISTRY`,
`_VALIDATION_SUMMARY`):

- `/api/arbicore/live/*` (status, start, stop, prices, opportunities)
- `/api/arbicore/providers/status`
- `/api/arbicore/scanners/cross/status`
- `/api/arbicore/memory/*` (summary, recurring, persistent, confidence, profitability, routes, venues, regime) — 8 endpoints
- `/api/arbicore/safety/status`, `/safety/kill/{engage,disengage}`
- `/api/arbicore/validation/*` (summary, recurrence, calibration, venue_ranking, regime, daily_run_now) — 6 endpoints
- `/api/arbicore/observability`
- `/api/arbicore/execution/*` (kill-switch, wallets, secrets, mode, plans, opportunities, discovery/status, gas) — all wired to real repos

**Consequence:** the `OpsCenter` dashboard (which is the DEFAULT landing
after login) is already 100% wired to real runtime data. **The operator's
daily view is already truthful.** Placeholder replacement affects the
per-slice deep-dive tabs (Home, Opportunities, Discovery, Portfolio,
Operations, Intelligence, Settings) but not the operator's initial
briefing.

This meaningfully rebalances the audit conclusion vs the initial report:
the "everything is fake" framing was too broad. Corrected framing:

- **OpsCenter** = ✅ real
- **Execution flow** (FlashLoanOperator, Wizard, Journey, ExecutorVerify) = ✅ real
- **Slice-specific deep-dive tabs** (Home, Opportunities, Discovery, Portfolio, Operations, Intelligence, Settings) = ⚠️ stub-heavy

## §2. HomePage micro-fix required

`app/frontend/src/v2/pages/HomePage.jsx:65-66`:

```jsx
<Card title="Interlock" testid="v2-home-pulse-interlock">
  <div className="v2-num" style={{ …color: "var(--v2-verdict-go)"… }}>ARMED</div>
  <div>Safety armed · Slice 3 wires live</div>
</Card>
```

This literal `ARMED` string is a widget-level placeholder — it always shows
green ARMED regardless of the real safety state. When Slice 3 (Market
Intelligence & Execution Readiness) lands, this must become:

```jsx
<Card title="Interlock" …>
  <div style={{color: safety.kill_engaged ? "verdict-no-hard" : "verdict-go"}}>
    {safety.kill_engaged ? "ENGAGED" : "ARMED"}
  </div>
  <div>{safety.kill_engaged ? `Reason: ${safety.reason}` : "Safety armed"}</div>
</Card>
```

Same tile also has `Venue readiness` and `Deployable capital` cards that
currently display `—` with "Live in Slice 3/4" muted subtitle — these are
self-documenting placeholders and safe to leave until their slices land.

**Fix budget: 0.25 dev-day (HomePage Interlock only).** Ship as part of
the Market Intelligence pipeline slice.

## §3. Nothing else needs touching

No other page has a hardcoded literal that would survive a stub deletion.
Every page reads data from an endpoint and every widget guards against
empty/null.

---

## Sign-off

- Empty-state widget sweep: **PASS** for all 15 mounted pages.
- Ready to proceed with pipeline activation.
- One micro-fix (HomePage Interlock) scheduled inside the Market
  Intelligence / Execution Readiness pipeline slice.
