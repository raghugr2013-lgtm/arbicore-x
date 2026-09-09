# ArbiCore X v2 — VPS Software-Certification Runbook (Phase A + B)

**Certification / staging ONLY. Not permission for live trading.**
Signing / broadcast / auto-exec / Full-Live / Limited-Live stay **OFF**. No real
transaction. No new receiver deployment. The production container is **not**
restarted or replaced. All work runs in an isolated `arbicore-cert` project.

Commit under test: the approved `p1-batch2-h07-h08-h09` (verify with `git rev-parse HEAD`).

---

## 0. Prerequisites (on the VPS, NOT this pod)
- The operator's six **read-only** RPC endpoints (per chain; may be comma-lists for failover).
- The deployed executor/receiver address for the non-production target chain (84532).
- Docker + docker compose on the VPS. The production stack keeps running untouched.

## 1. Check out the exact approved commit (separate working copy)
```bash
git fetch --all
git checkout p1-batch2-h07-h08-h09        # or the vps-cert branch derived from it
git rev-parse HEAD                          # record this commit in the report
```

## 2. Create the git-ignored cert env (secrets stay on the VPS)
```bash
cp deployment/cert/cert.env.example deployment/cert/cert.env
# edit deployment/cert/cert.env and fill the six ARBICORE_RPC_URL_<CHAIN> values
# (+ ARBICORE_EXECUTOR_ADDRESS_BASE). Leave price-feed/sizer/sim flags false unless
# a real operator price feed / exact simulator is wired. NEVER commit this file.
```

## 3. Run the isolated, read-only certification stack
```bash
mkdir -p vps_cert_out
GITSHA=$(git rev-parse HEAD) docker compose -p arbicore-cert \
  -f deployment/compose/docker-compose.certification.yml \
  --env-file deployment/cert/cert.env \
  up --build --abort-on-container-exit
```
The one-shot `certify` service runs `python -m scripts.vps_certify`, writes the
report, and exits. It serves no traffic and starts no scanner/executor.

## 4. Collect the evidence (no secrets inside)
```bash
cat vps_cert_out/certification_report.md          # 12-section human report
cat vps_cert_out/certification_evidence.json      # machine-readable evidence
```

## 5. Tear down the cert stack (production untouched)
```bash
docker compose -p arbicore-cert \
  -f deployment/compose/docker-compose.certification.yml down -v
```
(`-v` removes ONLY the isolated `arbicore-cert-mongo-data` volume.)

---

## What each status means (fail-closed)
- **PASS** — real positive evidence obtained (e.g., endpoint verified for its chain id).
- **FAIL** — active contradiction (e.g., endpoint reports the wrong chain id).
- **BLOCKED** — evidence unavailable/unreachable (never upgraded to PASS).
- **UNKNOWN** — reachable but insufficient to certify (e.g., no failover peer; needs on-chain verify).
- **NOT_CONFIGURED** — the operator input for this check is absent (fail closed).

## Interpreting Phase B (H08 / bytecode / immutables) — target chain 84532
- H08 becomes anything other than BLOCKED **only** when the deployed receiver is
  on-chain-verified AND explicitly declares `supported_providers` in the registry
  record. Editing the registry alone does not make it TRUE — the bytecode /
  immutable / owner / entrypoint checks (section 7) must also verify against the
  artifact. If `supported_providers` is absent → H08 stays **BLOCKED/FALSE**.
- Do **not** deploy a new receiver as part of this run. A new on-chain deployment
  requires separate explicit approval.

## Before any Opportunity Race / Limited Live (do NOT start now)
All of: six-chain RPC PASS (+failover), H05 PASS with a live exact-size quote,
H07 live composition PASS per chain, H08 on-chain-verified + provider declared,
H09 complete candidate binding + exact-sim PASS + chain match, section-7 bytecode/
immutable/owner verified — AND explicit operator approval with signing/broadcast
still gated. Certification PASS is necessary but NOT sufficient for live trading.
