# ArbiCore X — Security-gate reconciliation (read-only)

**Verdict: BLOCKED** (security gate / P2 reconsideration)  
**Probe UTC:** `2026-10-10T08:32:58Z` (live checks) · Report written after S2-A primary cutover PASS  
**Mode:** Read-only · no mutations · no revokes · no restarts · no wallet moves · no firewall changes  

**Preserved evidence (accepted):**  
- S2-A primary cutover **PASS** — `s2a_alchemy_containment_20261009/S2A_ALCHEMY_ROTATION_EXECUTION_REPORT.md`  
- 429 investigation **ACCEPTABLE WITH EXPLANATION** — `s2a_alchemy_containment_20261009/S2A_ALCHEMY_429_INVESTIGATION.md`  

**Live posture (this audit):** backend `s2a-rpc-redact-5bd952568aed` @ `sha256:69fe2459…` healthy · **SHADOW** · AUTOEXEC=`false` · RUNTIME=`false` · legacy b7/h05/w1 **exited** · g5.79 **out of scope** · `sendRawTransaction` 30m = **0** · log redaction **present** · 30m unredacted Alchemy URLs = **0**

Probe artifact: `s2a_alchemy_containment_20261009/gate_recon_probe.json`

---

## Executive summary

| # | Blocker | Live verdict |
|---|---|---|
| A | Alchemy log redaction + primary cutover | **PASS WITH LIMITATIONS** |
| B | Old Alchemy primary / ENV key revocation | **UNKNOWN** (not revoked; residual in backups + still valid at provider until revoke) |
| C | Alchemy Mongo fallbacks `[1..5]` | **PASS WITH LIMITATIONS** (retained by policy; still live secrets) |
| D | Vault key rotation (S1-B) | **PASS WITH LIMITATIONS** |
| E | Legacy isolation / single writer | **PASS** |
| F | MongoDB root / least privilege | **FAIL** |
| G | Plaintext admin + JWT in ENV/`.env` | **FAIL** |
| H | Public `/docs` + bootstrap token | **FAIL** |
| I | Deployer private-key exposure / migration | **FAIL** (balances **PASS**-ish zero; key still on disk) |

**Security gate for P2: BLOCKED.** S2-A and S1-B progress do **not** clear Mongo root, public docs/bootstrap, deployer key-on-disk, or plaintext admin/JWT.

---

## Blocker-by-blocker evidence

### A — Alchemy RPC log redaction + primary endpoint cutover

| | |
|---|---|
| **Verdict** | **PASS WITH LIMITATIONS** |
| **Verified** | Cutover `2026-10-10T06:58:48Z`; probe `08:32Z`; 30m log sample this audit |
| **Method** | Image file presence; `docker logs` unredacted regex; cutover post-verify fps |

| Check | Result |
|---|---|
| `log_redaction.py` in running image | **Present** |
| 30m unredacted `alchemy.com/v2/<token>` | **0** |
| 30m `/v2/[REDACTED]` | 794 |
| Live Mongo/ENV primary fp | **`ca6545ba`** (not `24dab5d1` / not `5e5d5bb1`) |
| Six-chain primary health (cutover) | PASS |

**Limitations:** Fallbacks not rotated; old primary/ENV keys not provider-revoked; staging file `/tmp/s2a_alchemy_replacements.env` still on host (`0600`); cutover backups retain pre-cutover secrets.

**Evidence:** `S2A_ALCHEMY_ROTATION_EXECUTION_REPORT.md`, `cutover_post_verify.json`, `gate_recon_probe.json`, this audit log sample.

---

### B — Old Alchemy primary / ENV credential containment & revoke

| | |
|---|---|
| **Verdict** | **UNKNOWN** for provider revoke · **PASS WITH LIMITATIONS** for app config displacement |
| **Verified** | `2026-10-10T08:32Z` |

| Surface | Old fp | Live status |
|---|---|---|
| Mongo `[0]` | `24dab5d1` | **Displaced** → `ca6545ba` |
| `.env` bootstrap/archive/per-chain | `5e5d5bb1` | **Displaced** → `ca6545ba` |
| Mongo `[1..5]` | `e315c86f`…`124bc59c` | **Still configured** (retain policy) |
| Provider-side revoke of `24dab5d1` / `5e5d5bb1` | — | **UNKNOWN** (no Alchemy dashboard check this audit) |
| Approved backup | `24dab5d1` in pre-cutover dump | Expected recovery archive under `/home/raghu/arbicore_backups/s2a_alchemy_cutover_20261010T065530Z/` |
| Legacy stopped ENV | `ce00e63d` (historical) | Containers exited — not production path |

**Evidence:** `cutover_mongo_apply_summary.json`, `cutover_dotenv_fps_post.json`, `cutover_backup_verify.json`, `gate_recon_probe.json`.

---

### C — Fallback registry

| | |
|---|---|
| **Verdict** | **PASS WITH LIMITATIONS** |
| **Note** | Intentional `FALLBACK_POLICY=retain_existing`. Not a cutover defect; still a residual secret inventory until a later fallback rotation/revoke stage. |

---

### D — Vault (`VAULT_KEY`) rotation

| | |
|---|---|
| **Verdict** | **PASS WITH LIMITATIONS** |
| **Verified** | Live ENV sha12 this audit; S1-B post-rotation report `2026-10-09` |

| Check | Result |
|---|---|
| Active backend `VAULT_KEY` sha12 | `fb5ca619211e` |
| Legacy b7 Config.Env vault sha12 | `a46000441419` (container **exited**) |
| S1-B prior verdict | PASS WITH LIMITATIONS |

**Evidence:** `s1b_vault_rotation_preflight_20261009/S1B_POST_ROTATION_VERIFICATION.md`; live inspect this audit.

---

### E — Legacy isolation

| | |
|---|---|
| **Verdict** | **PASS** |
| **Verified** | `2026-10-10T08:32Z` |

b7 / h05 / w1 **exited**. Only `arbicore-x-backend-new` is the production `arbicore_x` writer. g5.79 remains separate / out of scope.

**Limitation (not FAIL of isolation):** stopped Config.Env still holds older admin/JWT/Alchemy/vault material — must not be started.

---

### F — MongoDB root / least privilege

| | |
|---|---|
| **Verdict** | **FAIL** |
| **Verified** | `2026-10-10T08:32:58Z` |
| **Method** | Parse `MONGO_URL` username; `usersInfo` on `admin` and `arbicore_x` via app connection |

| Check | Result |
|---|---|
| App Mongo username | **`root`** (`authSource=admin`, host `factory-mongo`) |
| `admin` DB users | only `root` |
| `arbicore_x` DB-scoped users | **[]** (none) |

**Evidence:** `gate_recon_probe.json` → `checks.mongo`.

---

### G — Plaintext admin password + JWT

| | |
|---|---|
| **Verdict** | **FAIL** |
| **Verified** | `2026-10-10T08:32:58Z` |

| Check | Result |
|---|---|
| Container ENV admin pass | present · len 36 · sha12 `6757aa3396d8` |
| Container ENV JWT | present · len 64 · sha12 `066b178751e1` |
| Live `.env` (v2 upgrade backend) | same sha12s · plaintext on disk |
| Username | still `admin` |
| Legacy stopped Config.Env | older sha12s `6780d7b21193` / `7013ef842946` |

Rotation relative to ancient legacy values remains in place, but **plan criterion “not plaintext in ENV/files” is unmet**.

**Evidence:** `gate_recon_probe.json` → `admin_jwt_env`, `dotenv_plaintext`, `legacy_stopped`.

---

### H — Public `/docs` + bootstrap token

| | |
|---|---|
| **Verdict** | **FAIL** |
| **Verified** | `2026-10-10T08:32:58Z` |
| **Method** | HTTP GET status only |

| Endpoint | HTTP |
|---|---:|
| `127.0.0.1:8001/docs` | **200** |
| `127.0.0.1:8001/openapi.json` | **200** |
| `144-91-78-175.sslip.io/docs` | **200** |
| `144-91-78-175.sslip.io/openapi.json` | **200** |
| `ARBICORE_BOOTSTRAP_TOKEN` in ENV/`.env` | present · len 64 · sha12 `d5a682fbe887` |

**Evidence:** `gate_recon_probe.json` → `docs_openapi`, `bootstrap_token`.

---

### I — Deployer private key / wallet migration

| | |
|---|---|
| **Verdict** | **FAIL** (exposure) · balance **PASS WITH LIMITATIONS** (zero) |
| **Verified** | `2026-10-10T08:33Z` |

| Check | Result |
|---|---|
| `arbicore-x-v2/contracts/.env` `DEPLOYER_PRIVATE_KEY` | **Present** · len 64 · sha12 `7e792fd2e48f` · mode `0600` |
| `arbicore-x-cert/contracts/.env` | **Absent** (this tree) |
| `.deployer_address.txt` (cert + v2) | `0x65af…2003` |
| Address vs key consistency | **Mismatch** vs S1-B derived `0x3b37…41Cd` from same sha12 key (file address ≠ key-derived address) |
| Foundry keystore | present · mode `0600` |
| In backend container ENV | **No** |
| Base balance `0x65af…2003` | **0 ETH** (via live Base Alchemy primary) |
| Base balance `0x3b37…41Cd` | **0 ETH** |

**Evidence:** path inventory this audit; `gate_deployer_balances.json`.

---

## Production vs legacy vs approved archives

| Class | Items | Treatment |
|---|---|---|
| **Production live** | Mongo root; plaintext admin/JWT/bootstrap in ENV+`.env`; public docs; deployer key in v2 `contracts/.env`; fallback Alchemy fps; staging file in `/tmp` | Gate blockers / residuals |
| **Stopped legacy** | b7/h05/w1 Config.Env (old admin/JWT/Alchemy/vault) | Keep **stopped**; scrub/remove under change control |
| **Approved recovery** | S1-B vault escrow/backups; S2-A cutover backup `…/s2a_alchemy_cutover_20261010T065530Z/` | Retain restricted; not “unused” secrets |

---

## Prioritised remediation table

| Pri | Item | Smallest safe fix | Depends on | Backup / recovery | Validation | Downtime | Human approval |
|---:|---|---|---|---|---|---|---|
| 1 | Public `/docs` + OpenAPI | Edge deny `/docs` `/redoc` `/openapi.json` (Caddy/nginx) **or** disable FastAPI docs in prod image | Edge config change window | Snapshot Caddy/nginx config | Public URLs → 404/401; local admin path policy documented | Seconds (reload) | **Yes** — edge change |
| 2 | Bootstrap token | Rotate token; remove from non-essential backups; invalidate old | Pri 1 helpful | `.env` backup 0600 | Old token rejected; new token works only if bootstrap still required | Backend recreate ~1m | **Yes** |
| 3 | Mongo least privilege | Create `arbicore_app` user on `arbicore_x`; switch `MONGO_URL`; keep root break-glass offline | Mongo admin window; app grant matrix | `mongodump` + URI backup | App healthy; `usersInfo` shows app user; root unused by app | ~1–3m recreate | **Yes** — shared `factory-mongo` |
| 4 | Admin/JWT hygiene | Rotate again **or** move to Docker secrets/files with 0600 mounts; scrub backup copies of live plaintext where policy allows | Auth downtime tolerance | Escrow new secrets | Login 401 old / 200 new; sha12 changed; session_version bump | ~1–2m | **Yes** |
| 5 | Deployer key containment | Remove plaintext `DEPLOYER_PRIVATE_KEY` from tree; keep Foundry keystore only; reconcile address file; confirm dust balances | Operator wallet policy | Keystore backup offline | `contracts/.env` has no key; balances still 0; no key in backend ENV | None if file-only | **Yes** |
| 6 | Alchemy old primary/ENV revoke | After monitoring; revoke `24dab5d1` + `5e5d5bb1` in Alchemy UI; **do not** revoke fallbacks or g5.79 | S2-A PASS + 429 ACCEPTABLE (done) | Keep cutover backup | Auth fail on revoked key probe; prod healthy on `ca6545ba` | None | **Yes — separate revoke auth** |
| 7 | Alchemy fallback rotation | Later stage: replace `[1..5]` then revoke old fallback fps | Pri 6 complete or explicit combined plan | Network doc backup | fps map + chain health | ~1–2m | **Yes** |
| 8 | Legacy container disposal | Remove or recreate without old Config.Env after secret rotations | Pri 4–7 as applicable | None beyond inventory | `docker ps -a` clean / no old sha12s | None if rm only | **Yes** |
| 9 | Off-host DR for vault/backups | Copy escrow off-box | Ops channel | Verify restore drill off-host | Checklist sign-off | None | **Yes** |

**MEV aged-slice replay:** remains a **separate research workstream** — not part of this security gate; do not expand strategy scope or alter replay datasets under this plan.

---

## Independent security-gate acceptance criteria (before P2 may be reconsidered)

P2 stays **BLOCKED** until **all** of the following are verified on the **live** production path (fresh evidence, not stale reports alone):

1. **Docs/OpenAPI** not publicly reachable (or explicitly authenticated) — re-probe public host → not 200.  
2. **Bootstrap token** rotated; old sha12 absent from live ENV; bootstrap attack path closed or disabled.  
3. **Mongo app user** non-root; `MONGO_URL` username ≠ `root`; app healthy on least-privilege user.  
4. **Admin/JWT** not solely long-lived plaintext in world-readable locations; rotation attestation + login tests.  
5. **Deployer private key** absent from git worktrees/ENV; keystore-only or offline; address inventory consistent; balances understood.  
6. **Alchemy:** redaction still effective (0 unredacted); primary = intended new fps; **provider revoke** of displaced primary/ENV keys completed **or** explicitly accepted residual with dated risk acceptance; fallbacks either rotated or explicitly risk-accepted.  
7. **Vault** active key only on live path; legacy stopped or scrubbed.  
8. **Controls unchanged:** SHADOW, AUTOEXEC=false, RUNTIME=false, signing/broadcast off, legacy stopped — unless a later execution gate separately authorises change.  
9. **P2 image/digest** still requires its own apply-check authorisation after the above.

Meeting S2-A PASS alone is **necessary but not sufficient**.

---

## GO / BLOCKED

| Gate | Decision |
|---|---|
| S2-A primary rotation acceptance | **GO** (already PASS; 429 ACCEPTABLE WITH EXPLANATION) |
| Old Alchemy **revoke** | **BLOCKED** pending separate explicit revoke authorisation (recommended after this recon review) |
| **Overall execution security gate / P2 reconsider** | **BLOCKED** |

---

## Safety confirmation

- No production mutations, deployments, credential revokes, wallet transfers, firewall changes, or container starts by this audit.  
- Secrets referenced only as presence/length/sha12/fp8.  
- Stopped for human review.
