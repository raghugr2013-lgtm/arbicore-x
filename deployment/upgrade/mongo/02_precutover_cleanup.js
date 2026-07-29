// 02_precutover_cleanup.js — CONTROLLED trim of EXPIRED discovery candidates.
//
// WHY: DiscoveryCandidate.expires_at is a FLOAT epoch, so the Mongo TTL index on it
// is NON-FUNCTIONAL (TTL reaps only BSON Date fields). The 2.9M backlog will NOT be
// auto-reaped by the upgrade. This script trims it manually, in bounded batches with
// pauses, to keep Mongo 4.4.30 IO low. It deletes ONLY already-expired, non-claimable
// queue rows (transient) — NEVER durable records (opportunities/outcomes/audit).
//
// Run: docker exec -i <mongo> mongo --quiet arbicore_x_prod < 02_precutover_cleanup.js
//  (mongosh also works). Safe to run repeatedly / resume.
//
var COLL  = "arbicore_discovery_candidates";
var BATCH = 50000;        // ids per delete batch
var PAUSE_MS = 2000;      // pause between batches to smooth IO
var now = (new Date()).getTime() / 1000.0;   // float epoch, matches stored expires_at

var col = db.getCollection(COLL);
var before = col.count();
print("[cleanup] " + COLL + " total before = " + before);

// Target: expired (non-claimable) rows. expires_at is a float epoch.
var FILTER = { expires_at: { $lt: now } };
var eligible = col.count(FILTER);
print("[cleanup] eligible (expires_at < now) = " + eligible);

var deleted = 0;
while (true) {
  var ids = col.find(FILTER, { _id: 1 }).limit(BATCH).toArray().map(function(d){ return d._id; });
  if (ids.length === 0) break;
  var r = col.deleteMany({ _id: { $in: ids } });
  deleted += (r.deletedCount || ids.length);
  print("[cleanup] deleted so far = " + deleted);
  sleep(PAUSE_MS);
}
print("[cleanup] DONE. deleted=" + deleted + ", remaining=" + col.count());
print("[cleanup] NOTE: active/unexpired candidates are preserved; this only removed stale queue rows.");
