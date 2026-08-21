# ArbiCore X — Non-Destructive VPS Deployment & Data-Continuity Runbook

**Nature of operation:** REDEPLOY over an existing production stack. NOT a fresh install.
**Data to preserve:** ~11 days of intelligence in `factory-mongo → arbicore_x`.
**Safety posture:** SHADOW active. LIMITED_LIVE + FULL_AUTOMATION operator-gated (never auto-activated).
**Golden rule:** Before ANY destructive/irreversible action → STOP and request explicit operator approval.

---

## 0. Confirmed facts (from operator VPS inspection — authoritative)

| Item | Value |
|------|-------|
| Authoritative Mongo container | `factory-mongo` (Mongo **7.0.39**) |
| Authoritative database | `arbicore_x` |
| Authoritative Mongo volume | `factory-mongo_factory_mongo_data` |
| Effective target | `factory-mongo:27017` / `DB_NAME=arbicore_x` |
| NON-authoritative (do NOT use/migrate) | `arbicore-x-mongo` (Mongo 4.4) |
| VAULT_KEY | **REUSE existing exactly — do NOT rotate/regenerate** |
| MONGO_URL / DB_NAME | **Preserve existing — do NOT change** |
| Redeploy scope | ONLY `backend`, `frontend`, `opportunity-center` |
| Never touch | `factory-mongo`, its volume, Caddy, backups |

### Pre-deploy baseline counts (operator-verified)
```
mid_opportunities                416
mid_decisions                    208
mid_opportunity_lifetime         208
mid_routes                        20
arbicore_paper_evidence          214
adaptive_weight_recommendations    2
calibration_models                 2
evidence_bundles                   2
arbicore_opportunity_journal       1
arbicore_opportunities             1
opportunities                      1
alerts_log                         2
```
Mandatory continuity set: `mid_opportunities`, `mid_decisions`, `mid_opportunity_lifetime`,
`mid_routes`, `arbicore_paper_evidence`, `calibration_models`,
`adaptive_weight_recommendations`, `evidence_bundles`.

---

## 1. PRE-DEPLOY — capture inventory (READ-ONLY, no writes, no secret exposure)

Run inside the Mongo container. This performs ZERO writes.
```
# Snapshot every collection + count from the authoritative DB.
docker exec factory-mongo mongosh --quiet arbicore_x --eval '
  db.getCollectionNames().sort().forEach(function(c){
    print(c + "\t" + db.getCollection(c).countDocuments());
  });
' | tee /root/arbicore_predeploy_inventory.txt

# Fingerprint the snapshot for tamper-evidence.
sha256sum /root/arbicore_predeploy_inventory.txt | tee /root/arbicore_predeploy_inventory.sha256
```
> If Mongo requires auth, append `-u "$MONGO_USER" -p "$MONGO_PASS" --authenticationDatabase admin`
> using shell variables — never inline literal credentials.

**GATE:** Confirm the printed counts match the baseline above (≥). If a collection is missing
or lower than baseline BEFORE deploy → STOP (you are pointed at the wrong DB, e.g. Mongo 4.4).

---

## 2. PRE-DEPLOY — verify env continuity WITHOUT printing values

```
# Presence-only check (prints KEY names + boolean, never values).
for K in MONGO_URL DB_NAME VAULT_KEY ARBICORE_GAS_WALLET_ADDRESS \
         ARBICORE_EXECUTOR_ADDRESS_BASE ARBICORE_AUTOEXEC_AUTOSTART \
         ARBICORE_RUNTIME_AUTOSTART; do
  if grep -q "^$K=" /path/to/backend/.env; then echo "$K present"; else echo "$K MISSING"; fi
done
```
Required at deploy time:
- `DB_NAME=arbicore_x`, `MONGO_URL` → `factory-mongo:27017`
- `VAULT_KEY` present and **identical to current value** (do NOT touch this line)
- `ARBICORE_AUTOEXEC_AUTOSTART=false`
- `ARBICORE_RUNTIME_AUTOSTART=false`

---

## 3. DEPLOY — additive / non-destructive only

```
# From the compose project directory. Build only the 3 app services.
docker compose build backend frontend opportunity-center

# Recreate ONLY those 3, without touching their deps (factory-mongo, Caddy).
docker compose up -d --no-deps backend frontend opportunity-center
```
FORBIDDEN (do not run): `docker compose down -v`, any Mongo volume deletion,
`db.dropDatabase()`, `drop()`/`deleteMany()` on production collections,
recreating `factory-mongo`, or repointing to `arbicore-x-mongo`.

> If `factory-mongo` recreation ever appears unavoidable → **STOP and report** (Rule 7).

---

## 4. POST-DEPLOY — prove data continuity (post_count ≥ pre_count)

```
# Re-snapshot after deploy.
docker exec factory-mongo mongosh --quiet arbicore_x --eval '
  db.getCollectionNames().sort().forEach(function(c){
    print(c + "\t" + db.getCollection(c).countDocuments());
  });
' | tee /root/arbicore_postdeploy_inventory.txt

# Diff pre vs post — any collection missing or a DROP in count is a FAILURE.
join -t $'\t' -a1 -a2 -e MISSING -o 0,1.2,2.2 \
  <(sort /root/arbicore_predeploy_inventory.txt) \
  <(sort /root/arbicore_postdeploy_inventory.txt) \
  | awk -F'\t' '{flag=($2>$3||$3=="MISSING")?"  <-- REGRESSION":""; printf "%-34s pre=%-8s post=%-8s%s\n",$1,$2,$3,flag}'
```
PASS = every collection present AND `post ≥ pre` for the mandatory continuity set.

---

## 5. POST-DEPLOY — application read + write + signer + safety checks

```
API=https://<your-caddy-domain>

# (a) Backend reachable
curl -s -o /dev/null -w "root %{http_code}\n" $API/api/

# (b) Auth enforced — anonymous MUST be 401
curl -s -o /dev/null -w "anon-matrix %{http_code}\n" $API/api/arbicore/engine/readiness-matrix

# (c) Operator login (use shell vars; do not inline the password)
curl -s -c cj.txt -X POST $API/api/auth/login -H 'Content-Type: application/json' \
  -d "{\"username\":\"$OP_USER\",\"password\":\"$OP_PASS\"}" -o /dev/null

# (d) READ historical data + safety flags in one shot
curl -s -b cj.txt $API/api/arbicore/engine/readiness-matrix | python3 -c "import sys,json;d=json.load(sys.stdin);m=d['modes'];print('mode',d['current_mode'],'| LL',m['LIMITED_LIVE']['can_activate'],'| FA',m['FULL_AUTOMATION']['can_activate'],'| overall',d['overall_status'])"
# EXPECT: mode SHADOW | LL False | FA False | overall YELLOW

# (e) Historical read path — engine can serve stored intelligence
curl -s -b cj.txt "$API/api/arbicore/engine/history?limit=1"     | python3 -c "import sys,json;print('history read ok:',len(json.load(sys.stdin).get('items',[]))>=0)"
curl -s -b cj.txt "$API/api/arbicore/engine/checkpoint"          | python3 -c "import sys,json;json.load(sys.stdin);print('checkpoint read ok')"

# (f) New WRITE path — a shadow scan must persist a fresh evidence record
curl -s -b cj.txt -X POST "$API/api/arbicore/engine/scan-once"   | python3 -c "import sys,json;d=json.load(sys.stdin);print('scan wrote opportunities:',len(d.get('opportunities',[])))"
#   Then re-run the count on arbicore_paper_evidence / mid_* and confirm it grew (writes working).

# (g) Signer vault readable (no key ever returned)
curl -s -b cj.txt "$API/api/arbicore/engine/settings/signer"     | python3 -c "import sys,json;d=json.load(sys.stdin);print('signer present:',d.get('present'),'| matches:',d.get('matches_expected'))"
# EXPECT: present True | matches True   (VAULT_KEY reused correctly)

# (h) Executor ABI intact
curl -s -b cj.txt "$API/api/arbicore/engine/executor-abi"        | python3 -c "import sys,json;d=json.load(sys.stdin);print('entrypoint:',d.get('entrypoint'))"

# (i) Secret-leak scan — nothing sensitive in logs
docker compose logs --since 15m backend | grep -Ei 'private_key|signed_tx|raw_tx|eth_send|personal_sign|BEGIN.*KEY|[0-9a-fA-F]{64}' && echo 'LEAK FOUND (investigate)' || echo 'no secret leak detected'
```

---

## 6. GO / NO-GO CHECKLIST (maps to the 17 rules)

| # | Check | Rule | Result |
|---|-------|------|--------|
| 1 | Target = `factory-mongo:27017` / `arbicore_x` (NOT Mongo 4.4) | 1,2,5 | ☐ |
| 2 | Pre-deploy inventory captured + SHA256 fingerprinted | 8 | ☐ |
| 3 | `VAULT_KEY` line untouched (reused, not rotated) | 4 | ☐ |
| 4 | `MONGO_URL` / `DB_NAME` unchanged | 5 | ☐ |
| 5 | Only `backend`/`frontend`/`opportunity-center` rebuilt & recreated | 7 | ☐ |
| 6 | `factory-mongo`, its volume, Caddy, backups untouched | 6,14 | ☐ |
| 7 | No `down -v` / drop / truncate / volume delete executed | 6 | ☐ |
| 8 | Post-deploy: every collection present, `post ≥ pre` | 9 | ☐ |
| 9 | App READS historical records (history/checkpoint ok) | 10 | ☐ |
| 10 | App WRITES new records (scan-once grows counts) | 10 | ☐ |
| 11 | `AUTOEXEC_AUTOSTART=false`, `RUNTIME_AUTOSTART=false`, SHADOW active | 11 | ☐ |
| 12 | LIMITED_LIVE + FULL_AUTOMATION `can_activate=false` | 11,17 | ☐ |
| 13 | Signer `present=true`, `matches_expected=true`, no key leaked | 12 | ☐ |
| 14 | No schema-migration mutated historical docs; new fields optional | 15 | ☐ |
| 15 | Anonymous `/api/arbicore/*` → 401; operator login works | 17 | ☐ |
| 16 | No secret values in logs / API responses | 13,17 | ☐ |
| 17 | Caddy/domain serving; `/api`→backend, `/`→frontend | 17 | ☐ |

**GO** only when every row is ✅.
**NO-GO / STOP** immediately if: wrong Mongo target, any collection missing or count regression,
`factory-mongo` recreation appears required, a proposed migration is destructive, or SHADOW/lock
state is not honored. Report the finding and await explicit operator approval (Rules 6,7,16).

---

## 7. Rollback (non-destructive)

App-only rollback — Mongo/Caddy stay put:
```
# Redeploy the previous image tags for the 3 app services only.
docker compose up -d --no-deps backend frontend opportunity-center   # with prior tags
```
The database is never rolled back or restored as part of app rollback — the 11-day
intelligence carries forward untouched. Existing backup artifacts remain the disaster-recovery
path and are not modified by any step in this runbook.
