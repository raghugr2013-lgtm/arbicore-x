# ArbiCore X — Critical-Path Board (Base Full Live decision)

**Role:** Critical-path coordinator (inspect / reconcile / plan only)  
**UTC:** `2026-10-10T13:00:00Z` (approx.; live probes this session)  
**Mode:** No deploy · no signing · no broadcast · no strategy activation · no production settings change  
**Overall Full Live readiness:** **NOT READY**  
**Overall security gate / P2:** **BLOCKED**  
**Limited Live proven:** **FALSE** (handoff checklist)

---

## 1. Critical-path board

| ID | Work item | Status | Auth | Evidence / criteria |
|---|---|---|---|---|
| A-R1 | Public `/docs` edge deny | **COMPLETED** | Prior R1 auth | `artifacts/security/r1_edge_docs_deny_20261010T085028Z/` · live recheck `api.arbicorex.in/docs` **404**, `/api/` **200** |
| A-R2 | Bootstrap disable | **COMPLETED** | Prior R2 auth | `r2_bootstrap_disable_20261010T090646Z/` · live setup **503** |
| A-R3 | Mongo least privilege | **COMPLETED** (PASS WITH LIMITATIONS) | Prior R3 auth | `r3_mongo_leastpriv_apply_20261010T105128Z/` · closeout `r3_closeout_r4_plan_20261010T105818Z/` · live `MONGO_URL` user **`arbicore_app`** · Factory/root residual logged |
| A-R4-APPLY | Admin/JWT rotation | **COMPLETED** (PASS WITH LIMITATIONS) | Prior R4-APPLY | `r4_admin_jwt_apply_20261010T110918Z/` · live sha12 `112c88ac69e1` / `f98650d468b2` |
| A-R4-SCRUB-PF | R4-SCRUB preflight | **COMPLETED** | Read-only | `r4_scrub_preflight_20261010T111949Z/R4_SCRUB_PREFLIGHT.md` — **READY** then superseded by Phase A |
| A-R4-SCRUB-A | R4-SCRUB Phase A quarantine | **COMPLETED** | **Explicit Phase A auth** (transcript `62a95c24-…`) | `r4_scrub_phase_a_20261010T122730Z/` · **PASS** · 17 moved · hold → `2026-10-24T12:29:00Z` · no shred · Phase B **not** done |
| A-R4-DESTROY | Quarantine shred after hold | **PENDING** | Not authorised | Hold active; destroy blocked until ≥ hold + separate auth |
| A-R4-PHASE-B | Legacy `docker rm` ×4 | **PENDING** | Not authorised | Four containers still **exited** (rechecked) |
| A-R5 | Deployer key containment | **AUTHORISED for preflight only** → **READY FOR R5-APPLY** | Preflight done; **APPLY not auth** | [`artifacts/security/r5_deployer_preflight_20261010T125755Z/R5_DEPLOYER_KEY_CONTAINMENT_PREFLIGHT.md`](security/r5_deployer_preflight_20261010T125755Z/R5_DEPLOYER_KEY_CONTAINMENT_PREFLIGHT.md) · plaintext still present · A/B/C address split |
| A-R6 | Alchemy old primary/ENV revoke | **BLOCKED** (UNKNOWN) | **No revoke auth** | S2-A cutover PASS · displaced fps `24dab5d1` / `5e5d5bb1` · provider revoke **not verified** · `S2A_ALCHEMY_ROTATION_EXECUTION_REPORT.md` §6–7 |
| A-S2A / A-S1B | Alchemy redaction+cutover / vault | **COMPLETED** (PASS WITH LIMITATIONS) | Prior | `s2a_alchemy_containment_20261009/` · `s1b_vault_rotation_preflight_20261009/` · live primary fp **`ca6545ba`** · six `ARBICORE_RPC_URL_*` **SET** |
| A-GATE | Overall security / P2 reconsider | **BLOCKED** | — | Matrix + reconciliation acceptance §: R5+R6 (or dated risk acceptance) still required |
| B-G15 | Offline Base coverage audit | **COMPLETED** | Research-only | `artifacts/g15/audit_offline_base_replay_20261009/` · exact coverage 7/6287 · hot-path **NO-GO** |
| B-G16 | False-arb guard offline | **COMPLETED** (limitations) | Research-only | `artifacts/g15/g16_false_arbitrage_guard_20261009/G1_6_CLOSEOUT.md` |
| B-V4INV | UniV4 inventory | **COMPLETED** → **DO NOT IMPLEMENT** | Research-only | `univ4_inventory/UNIV4_BASE_INVENTORY.md` |
| B-DEX-266 | DEX↔DEX 266-candidate main replay | **PENDING / BLOCKED** | Not started | **No on-disk artifact** defines the “266-candidate” cohort or pass/fail package under this workspace (searched cert tree + projects). Do **not** invent criteria. |
| B-DEX-15 | DEX↔DEX 15-tx hold-out | **PENDING / BLOCKED** | Not started | Same — no hold-out package found |
| B-LAT | Discovery→decision latency diagnosis + smallest fix (no deploy) | **COMPLETED (diagnose)** · fix **PENDING deploy** | P2 deploy **not** authorised | Bottleneck = **queue wait** (p50 discovery→claim **~375 s**; active verify p50 **~1.6 s**) · `artifacts/performance/p1_readonly_baseline/` · smallest fix packaged as P2 durable `claimed_at` + stage timing · `artifacts/performance/p2_release/` · **READY FOR EXPLICIT DEPLOY AUTH** but security gate **BLOCKS** P2 |
| B-TRI | Triangular replay (shared infra, own criteria) | **PENDING** | Not started | Prior stored-gross / SHADOW economics exist (`docs/certification/PHASE_0_5_TRIANGULAR_*`, shadow analyses) but **no** Base triangular replay decision package with independent GO/INVESTIGATE/REJECT recorded for this path |
| B-MORPHO | Morpho E1/E2 offline | **PENDING** (optional, non-blocking) | Not started as E1/E2 package | Lending census: `ALPHA_DISCOVERY_2_0_LENDING_LIQUIDATION_GROUND_TRUTH_CENSUS_20261005.md` — Base Morpho events thin / no $25 net engineering GO. **No liquidator build / paper eval** |
| B-FAM-DEX | Family decision DEX↔DEX | **NOT RECORDED** | — | Need B-DEX-266 + B-DEX-15 |
| B-FAM-TRI | Family decision triangular | **NOT RECORDED** | — | Need B-TRI |
| B-FAM-MOR | Family decision Morpho liq. | **NOT RECORDED** (census leans REJECT for eng. gate) | — | Census ≠ formal family REJECT until E1/E2 offline dispositioned |
| C-LL | Limited Live gates 1–13 | **OPEN** (proven=FALSE) | No LL auth | `reports/handoff/ARBICORE_X_LIMITED_LIVE_GATES.md` — gates 2–3 FAIL historically; 4–11 not proven; 13 not given |
| C-FL | Full Live gates 1–20 | **OPEN** (after LL) | No FL auth | `reports/handoff/ARBICORE_X_FULL_LIVE_GATES.md` |
| CTRL | SHADOW / AUTOEXEC / RUNTIME / signing | **HELD** | — | Live: SHADOW · AUTOEXEC=false · RUNTIME=false · digest `69fe2459…` healthy |

**Status legend:** COMPLETED · PENDING · BLOCKED · AUTHORISED (ready, not executed) · NOT RECORDED

---

## 2. Gate register (evidence path + pass/fail)

### Workstream A — Security

| Gate | Pass criteria | Evidence path | Current |
|---|---|---|---|
| R1 | Public docs/OpenAPI not 200 | `r1_edge_docs_deny_*` + live HTTP | **PASS** |
| R2 | Bootstrap unset → setup 503 | `r2_bootstrap_disable_*` + live | **PASS** |
| R3 | App Mongo ≠ root; healthy | `r3_mongo_leastpriv_apply_*` + closeout | **PASS WITH LIMITATIONS** |
| R4 live | New admin/JWT; login tests; controls held | `r4_admin_jwt_apply_*` | **PASS WITH LIMITATIONS** |
| R4-SCRUB Phase A | 17 carriers quarantined; S1–S6; no shred | `r4_scrub_phase_a_20261010T122730Z/` | **PASS** (hold active) |
| R4 destroy / Phase B | Hold expired + auth; shred / `docker rm` | — | **PENDING** |
| R5 | Deployer key absent from worktree plaintext; address inventory consistent; balances understood | Recon: `SECURITY_GATE_RECONCILIATION.md` §I · `gate_deployer_balances.json` · live file still SET | **FAIL / BLOCKED** |
| R6 | Provider revoke of displaced primary/ENV **or** dated risk acceptance | S2-A revoke-ready note; no dashboard proof | **UNKNOWN / BLOCKED** |
| S2-A / S1-B | Redaction + primary cutover; vault active | respective artifact dirs | **PASS WITH LIMITATIONS** |
| Overall / P2 | All required controls verified; residuals dispositioned | Matrix § Independent acceptance | **BLOCKED** |

**Historical limitations retained:** ransom-note / pre-2026-09-07 log gap; Factory Mongo still root; approved recovery archives retain pre-rotation secrets; quarantine not destroyed; fallback Alchemy fps retained by policy; plaintext admin/JWT still in live `.env`/ENV by design of current ops model.

### Workstream B — Base strategy validation

| Gate | Pass criteria | Evidence path | Current |
|---|---|---|---|
| Coverage audit | Offline match tiers reproducible | `BASE_G15_OFFLINE_ROUTE_COVERAGE_AUDIT.md` | **DONE** (research GO only) |
| DEX main 266 | Pre-declared GO/INVESTIGATE/REJECT on **established** 266 cohort — **no threshold relaxation** | **Missing package** | **BLOCKED** |
| DEX hold-out 15 | Independent 15-tx hold-out under same bar | **Missing package** | **BLOCKED** |
| Latency smallest fix | Bottleneck named; minimal patch proposed; **not** deployed without auth | P1 baseline + P2 package | Diagnosis **DONE**; deploy **NOT AUTH** |
| Triangular replay | Own independent criteria + GO/INVESTIGATE/REJECT | Not present as decision package | **PENDING** |
| Morpho E1/E2 offline | Offline only; must not delay DEX primary | Census exists; E1/E2 package absent | **PENDING** (deferrable) |
| Family decisions | Explicit GO / INVESTIGATE / REJECT each | — | **NOT RECORDED** |

### Workstream C — Release readiness (rechecked; not inferred complete)

| Area | Outstanding | Evidence / note |
|---|---|---|
| Tx execution | No controlled real execution; V1 receiver UniV3-limited | LL gates 6–11; executor docs |
| Risk / kill | Kill engaged boot_default; LIVE off — **controls held**, not “execution proven” | Live env + P1 baseline |
| Recovery | DR archives present; R4 quarantine restore script exists; destroy/Phase B open | `restore_from_quarantine.sh`; backups under `/home/raghu/arbicore_backups/` |
| Monitoring | No FL-grade live dashboards/alerts proven | FL gate 18 open |
| Wallet funding | Deployer/executor addresses 0 ETH on Base (recon); funding gate open | `gate_deployer_balances.json` |
| Certification | Six-network RPC env still SET (recheck); Base remains research focus; LL/FL checklists open | Live env probe this session; `SIX_NETWORK_*` docs are older — **do not treat APPLY as done from old cert alone** |
| Security before P2 | R5+R6 open | Matrix |

---

## 3. Minimum remaining tasks → **Limited Live** decision

1. **Security:** Close **R5** and **R6** (execute under separate auth) **or** record dated risk acceptance for each residual.  
2. **Strategy:** Obtain/locate the **established** DEX 266 + 15 hold-out criteria package; run offline; record family verdict (**no** threshold cut).  
3. **Triangular:** Independent offline replay + family verdict (can follow DEX if shared infra ready).  
4. **Latency:** Optional for LL *decision* if economics already fail; P2 deploy only after security gate + explicit deploy auth (measurement fix, not alpha).  
5. **LL checklist:** Clear gates 2–3 with a real qualifying edge (not fabricated); prove 4–7; then separate auth for gate 8 canary; 9–11 on receipt; gate 13 human approval.  
6. Morpho offline E1/E2 only if it does not delay (1)–(3).

---

## 4. Additional gates before **Full Live**

Everything in §3 **plus** all rows in `reports/handoff/ARBICORE_X_FULL_LIVE_GATES.md` (multi-chain/venue/strategy proof, race stability, RPC failover, nonce/lifecycle, reorg, accounting, limits, monitoring, multi-day reliability, explicit FL approval). Limited Live must be **proven** first.

---

## 5. Parallel vs sequential

| Parallel (safe) | Sequential (must order) |
|---|---|
| Security R5 prep/preflight ‖ Strategy criteria locate + offline DEX/tri replays ‖ Morpho offline E1/E2 (if spare) ‖ docs/board updates | R4 destroy **after** hold ≥ `2026-10-24T12:29:00Z` + auth |
| R6 revoke prep (UI checklist) ‖ R5 file containment prep | R6 revoke **after** S2-A acceptance (done) **and** separate revoke auth; never revoke fallbacks/g5.79 without explicit scope |
| P2 patch review/re-verify offline | **P2 deploy after** security gate clears (or explicit exception) **and** deploy auth |
| Family decision write-ups after their replays | Limited Live canary **after** security + family GO + LL gates 1–7 + approval |
| | Full Live **only after** Limited Live proven |

Security remediation and strategy research **remain separate workstreams** (no coupling of auth).

---

## 6. Single next task (one only)

**Explicit R5-APPLY Phase 1** — quarantine/redact plaintext `DEPLOYER_PRIVATE_KEY` from `arbicore-x-v2/contracts/.env` only (per R5 preflight); no shred, no keystore delete, no txs, no P2.

Rationale: R5 preflight is **READY**; exposure remains open; address A/B/C mismatch is documented.

---

## 7. Explicit non-actions this session

- No R5/R6 mutation · no quarantine destroy · no Phase B · no P2 deploy  
- No 266/15 replay invented · no triangular/Morpho new runs started  
- No threshold relaxation · no LIVE/signing/broadcast · Base remains sole strategy-research focus · six-network env left intact  

**Stopped for review.**
