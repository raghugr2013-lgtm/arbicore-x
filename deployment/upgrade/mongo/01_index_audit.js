// 01_index_audit.js — READ-ONLY. Reports existing indexes on arbicore_* collections
// so the operator can spot IndexOptionsConflict risks before cutover.
// Run: docker exec -i <mongo> mongo --quiet arbicore_x_prod < 01_index_audit.js
//  (or mongosh). Drop ONLY a conflicting index by name; the new build rebuilds it.
//
// Expected index names created by the audited build (see readiness report §3):
var EXPECTED = {
  "arbicore_opportunities": ["_id_","opportunity_id_unique","subject_id_idx","type_status_idx","created_at_desc"],
  "arbicore_outcomes": ["_id_","outcome_id_unique","opp_id_idx","due_at_sparse","evaluated_idx","subject_id_idx"],
  "arbicore_state_snapshots": ["_id_","subject_time_idx","opp_type_idx","ttl_30d"],
  "arbicore_audit_log": ["_id_","ts_idx","opp_id_idx","actor_idx","ttl_90d"],
  "arbicore_route_stats": ["_id_","route_key_unique","updated_at_desc"],
  "arbicore_provenance_audit": ["_id_","source_idx","updated_at_desc"],
  "arbicore_signal_metrics": ["_id_","signal_id_idx","subject_id_idx","aggregated_at_desc"],
  "arbicore_wallet_metrics": ["_id_","wallet_id_unique","entity_id_idx","updated_at_desc"],
  "arbicore_temporal_sequences": ["_id_","subject_id_idx","discovered_at_desc","ttl_90d"],
  "arbicore_sequence_patterns": ["_id_","pattern_id_unique","support_idx","confidence_idx"],
  "arbicore_regime_snapshots": ["_id_","captured_at_desc","dominant_regime_idx","ttl_90d"],
  "arbicore_entities": ["_id_","entity_id_unique","entity_type_idx","last_seen_desc"],
  "arbicore_entity_refs": ["_id_","ref_unique","entity_id_idx"],
  "arbicore_entity_clusters": ["_id_","cluster_id_unique","score_desc","detected_desc"]
};

print("=== arbicore_* index audit ===");
Object.keys(EXPECTED).forEach(function(c){
  if (db.getCollectionNames().indexOf(c) < 0) { print(c + ": (collection absent — will be created on boot)"); return; }
  var have = db.getCollection(c).getIndexes().map(function(i){ return i.name; });
  print("\n-- " + c);
  print("   existing: " + have.join(", "));
  // names that exist but are NOT in the expected set => potential conflict to review
  var unexpected = have.filter(function(n){ return EXPECTED[c].indexOf(n) < 0; });
  if (unexpected.length) print("   REVIEW (unexpected names — verify spec, drop if it conflicts): " + unexpected.join(", "));
});
print("\nNOTE: a true conflict only occurs if an EXISTING index shares a NAME with an expected one");
print("but has a different key/options. If so: db.<coll>.dropIndex(\"<name>\") then let boot rebuild it.");
