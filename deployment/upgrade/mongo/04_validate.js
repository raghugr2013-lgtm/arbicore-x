// 04_validate.js — post-deploy acceptance checks (read-only).
// Run: docker exec -i <mongo> mongo --quiet arbicore_x_prod < 04_validate.js
function ok(c){ return c ? "PASS" : "FAIL"; }

// (1) seeding restored — expect 6 config + 6 state docs
var cfg = db.arbicore_scanner_config.count();
var st  = db.arbicore_scanner_state.count();
print("scanner_config docs = " + cfg + "  [" + ok(cfg === 6) + " expect 6]");
print("scanner_state  docs = " + st  + "  [" + ok(st  === 6) + " expect 6]");

// (2) scanner state rows present (SHADOW/PAPER posture = dormant).
// Scanners are intentionally disabled (enabled=false) until an operator
// explicitly promotes them. We assert the state ROWS exist, not that they
// are running, and report the enabled flag informationally.
function stateRow(id){ return db.arbicore_scanner_state.findOne({_id:id}); }
function present(id){ return stateRow(id) !== null; }
function enabledFlag(id){ var d = stateRow(id); return !!(d && d.enabled === true); }
print("cex_arb state row     = " + present("cex_arb")     + "  [" + ok(present("cex_arb")) + " expect present]" + "  (enabled=" + enabledFlag("cex_arb") + ")");
print("funding_arb state row = " + present("funding_arb") + "  [" + ok(present("funding_arb")) + " expect present]" + "  (enabled=" + enabledFlag("funding_arb") + ")");

// (3) durable data preserved
print("opportunities count = " + db.arbicore_opportunities.count() + "  (compare to counts_pre)");

// (4) scanner production (informational only in SHADOW/PAPER).
// Dormant scanners produce nothing by design — this is NOT a failure.
var w = (new Date()).getTime()/1000 - 300;
var recent = db.arbicore_discovery_candidates.count({ claimed_by: /^cex_arb:/, verified_at: { $gte: w } });
print("recent cex_arb verifications (5m) = " + recent + "  (informational; dormant in SHADOW/PAPER)");

// (5) effective TTL indexes present
function hasIdx(c,n){ return db.getCollection(c).getIndexes().some(function(i){return i.name===n;}); }
print("ttl_30d state_snapshots = " + ok(hasIdx("arbicore_state_snapshots","ttl_30d")));
print("ttl_90d audit_log       = " + ok(hasIdx("arbicore_audit_log","ttl_90d")));

// (6) discovery backlog trimmed
print("discovery_candidates remaining = " + db.arbicore_discovery_candidates.count());
print("\nAlso verify OpenAPI: curl -s http://localhost:8001/openapi.json | grep '/api/arbicore/scanners/cex_arb/config'");
