# v2.11.3 · VPS Production-State Audit Playbook

**Purpose**: verify which Mongo actually contains ArbiCore production data BEFORE choosing Path A vs. Path B. **Do not migrate or reconfigure based on defaults or assumptions.**

**Where to run**: on the VPS, with the operator's shell (root or the `docker`-group user).

**Runtime**: <2 minutes end-to-end. **Read-only** — no mutations.

---

## What this build agent can and cannot do

I do **not** have SSH/docker access to the production VPS from this sandbox. The audit commands below must be run by the operator on the VPS itself and the outputs pasted back for me to make a recommendation grounded in facts (not defaults).

What I have already verified locally in the preview container:
- Application code (v2.11 through v2.11.3) does not depend on a specific Mongo hostname — it reads `MONGO_URL` from env.
- Boot instrumentation (v2.11.2) emits `BOOT: <handler> start/done` lines for every startup handler.
- Non-blocking calibration & adaptive-weights workers (v2.11.1) — verified end-to-end locally.
- Compose fail-fast guards (v2.11.3) — `${VAR:?msg}` grammar is standard docker-compose, will reject missing values at `up` time.

The audit below is the **only remaining unknown**, and it must be answered from the VPS.

---

## Step 1 · Verify both Mongo containers exist & are healthy

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Networks}}' | grep -E 'mongo|MONGO'
```

Expected shape:
```
NAMES              STATUS                     NETWORKS
factory-mongo      Up X hours (healthy)       vqb-network
arbicore-x-mongo   Up X hours (healthy)       arbicore-x-net
```

If either container is missing or unhealthy, note that in the report. If `arbicore-x-mongo` does not exist at all, Path A requires bringing it up fresh (see the doc). If `factory-mongo` does not exist, Path B is off the table entirely.

---

## Step 2 · List all databases in EACH Mongo

### factory-mongo

```bash
docker exec factory-mongo mongosh --quiet --eval '
  db.adminCommand({listDatabases:1}).databases
    .filter(d => !["admin","config","local"].includes(d.name))
    .forEach(d => print(d.name.padEnd(30), (d.sizeOnDisk/1024/1024).toFixed(2)+" MiB"))
' 2>/dev/null || \
docker exec factory-mongo mongo --quiet --eval '
  db.adminCommand({listDatabases:1}).databases
    .filter(function(d){return !["admin","config","local"].includes(d.name)})
    .forEach(function(d){print(d.name+"  "+(d.sizeOnDisk/1024/1024).toFixed(2)+" MiB")})
'
```

If `factory-mongo` has auth enabled, prepend the credentials:
```bash
docker exec factory-mongo mongosh --quiet -u <USER> -p <PASS> --authenticationDatabase admin --eval '...'
```

### arbicore-x-mongo

```bash
docker exec arbicore-x-mongo mongosh --quiet --eval '
  db.adminCommand({listDatabases:1}).databases
    .filter(d => !["admin","config","local"].includes(d.name))
    .forEach(d => print(d.name.padEnd(30), (d.sizeOnDisk/1024/1024).toFixed(2)+" MiB"))
' 2>/dev/null || \
docker exec arbicore-x-mongo mongo --quiet --eval '
  db.adminCommand({listDatabases:1}).databases
    .filter(function(d){return !["admin","config","local"].includes(d.name)})
    .forEach(function(d){print(d.name+"  "+(d.sizeOnDisk/1024/1024).toFixed(2)+" MiB")})
'
```

---

## Step 3 · Inspect ArbiCore-canonical collections in EACH Mongo

Run these against **each** Mongo, substituting the actual db name from Step 2 (typically `arbicore_x`, `arbicore_prod`, or a variant).

```bash
DB=arbicore_x                                    # ← substitute if different

# Use the same mongosh / mongo command style as above.
docker exec <mongo-container> mongosh --quiet --eval "
  db = db.getSiblingDB('${DB}');
  var canon = [
    'arbicore_opportunities',
    'arbicore_opportunity_journal',
    'auth_users',
    'auth_sessions',
    'calibration_models',
    'adaptive_weights',
    'execution_plans',
    'capital_policy_audit',
    'kill_switch_audit',
    'wallet_registry',
    'entity_registry',
    'mid_events',
    'evidence_bundles',
    'execution_mode_audit'
  ];
  canon.forEach(function(name){
    var c = db.getCollection(name).countDocuments({});
    print(name.padEnd(35) + ' ' + c);
  });
"
```

The output tells you the *actual* state of each collection in each Mongo.

---

## Step 4 · Inspect the CURRENT backend's runtime `MONGO_URL`

```bash
docker inspect arbicore-x-backend --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(MONGO_URL|DB_NAME|NETWORK|ARBICORE_)'
docker inspect arbicore-x-backend --format 'networks: {{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

This is the ground truth for what the current (broken) backend is trying to reach and on which network.

---

## Step 5 · Inspect Opportunity Center's runtime config

```bash
docker ps --format 'table {{.Names}}' | grep -i opportunity
# If there is a container, e.g. arbicore-x-opportunity-center:
docker inspect arbicore-x-opportunity-center --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -E '^(MONGO|VITE_|REACT_|DB_)'
```

---

## Decision Matrix

| Step 3 result | Data location | Path | Rationale |
|---|---|---|---|
| **`factory-mongo` has ArbiCore collections with >0 documents (esp. `arbicore_opportunities`, `arbicore_opportunity_journal`, `auth_users`)**; `arbicore-x-mongo` is empty | Production data lives in factory-mongo | **Path B** (fix networking only, keep factory-mongo) | Do NOT migrate. Preserve existing data + audit trail. Smallest safe fix. |
| **`arbicore-x-mongo` has ArbiCore collections with >0 documents**; `factory-mongo` has no ArbiCore db (or only stale/empty) | Production data lives in arbicore-x-mongo | **Path A** (greenfield) | Backend config was wrong all along — pointing at factory-mongo but the real data is in arbicore-x-mongo. Switching to Path A aligns config with actual data. |
| **Both are empty (or only empty collections)** | No production data yet | **Path A** (recommended) | Fresh start — pick the isolation-safe option. |
| **Both have ArbiCore data with overlapping documents** | Ambiguous | **STOP — human decision required** | Manual reconciliation before any switch. |
| **`factory-mongo` container does not exist** | N/A | **Path A** (mandatory) | Only arbicore-x-mongo is available. |
| **`arbicore-x-mongo` container does not exist** | Data must be in factory-mongo | **Path B** (mandatory) | The greenfield container was never brought up. |

---

## Report back

Paste the outputs of Steps 1-5 into the conversation. I will then:
1. Confirm the exact Path (A or B) based on your findings.
2. Emit the smallest possible fix — networking only if the data location is already correct.
3. Provide the verification commands to prove the backend is healthy.

**No configuration changes should be made on the VPS until this audit output is received.**

---

## What NOT to do until the audit is complete

- Do **not** run `docker compose up -f docker-compose.yml` — that would try to bring up an `arbicore-x-mongo` on `arbicore-x-net` regardless of whether one already exists.
- Do **not** delete or recreate any Mongo container.
- Do **not** modify `.env.shared` yet.
- Do **not** attempt any mongodump/mongorestore.
