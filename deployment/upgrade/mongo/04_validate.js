// 04_validate.js — post-deploy acceptance checks (read-only).
// Run: docker exec -i <mongo> mongo --quiet arbicore_x_prod < 04_validate.js
function ok(c){ return c ? "PASS" : "FAIL"; }

// (1) seeding restored — expect 6 config + 6 state docs
var cfg = db.arbicore_scanner_config.count();
var st  = db.arbicore_scanner_state.count();
print("scanner_config docs = " + cfg + "  [" + ok(cfg === 6) + " expect 6]");
print("scanner_state  docs = " + st  + "  [" + ok(st  === 6) + " expect 6]");

// (2) running scanners preserved (env flags) — cex_arb & funding_arb enabled
function enabled(id){ var d = db.arbicore_scanner_state.findOne({_id:id}); return d && d.enabled === true; }
print("cex_arb enabled     = " + enabled("cex_arb")     + "  [" + ok(enabled("cex_arb")) + "]");
print("funding_arb enabled = " + enabled("funding_arb") + "  [" + ok(enabled("funding_arb")) + "]");

// (3) durable data preserved
print("opportunities count = " + db.arbicore_opportunities.count() + "  (compare to counts_pre)");

// (4) scanners producing post-cutover (recent CEX claims)
var w = (new Date()).getTime()/1000 - 300;
var recent = db.arbicore_discovery_candidates.count({ claimed_by: /^cex_arb:/, verified_at: { $gte: w } });
print("recent cex_arb verifications (5m) = " + recent + "  [" + ok(recent > 0) + " expect >0]");

// (5) effective TTL indexes present
function hasIdx(c,n){ return db.getCollection(c).getIndexes().some(function(i){return i.name===n;}); }
print("ttl_30d state_snapshots = " + ok(hasIdx("arbicore_state_snapshots","ttl_30d")));
print("ttl_90d audit_log       = " + ok(hasIdx("arbicore_audit_log","ttl_90d")));

// (6) discovery backlog trimmed
print("discovery_candidates remaining = " + db.arbicore_discovery_candidates.count());
print("\nAlso verify OpenAPI: curl -s http://localhost:8001/openapi.json | grep '/api/arbicore/scanners/cex_arb/config'");
