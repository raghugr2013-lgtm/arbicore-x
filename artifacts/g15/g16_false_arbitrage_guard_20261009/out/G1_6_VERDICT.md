# G1.6 Final verdict

**Verdict:** PASS WITH LIMITATIONS

## Acceptance
- Existing classifications recoverable: **True**
- Flag counts: `{'NO_FLAG': 6065, 'POTENTIAL_CROSS_TX_MIRROR': 118, 'REPEATED_POOL_ROUTE': 98, 'BOTH_FLAGS': 6}`
- Flagged rows: 222 / 6287 Base winners
- Unique mirror pairs: 68
- Frozen source sha256: `f525083f2ef218ce4532993c1dcc41e8807d0db68824408d9d4675d4ad871714` (unchanged during run)
- Unit tests: **11 passed**

## Limitations
- G1.5 gcpipe/families_lib.py not present in core export tarball on host; guard implemented offline from winners schema
- Amount tolerance fixed at 5%; linkage uses pool+reverse+size+block window (same_searcher/operator recorded but not required)

## Non-impact confirmation
- Collectors / Base tracker / live ledger / production: untouched
- Frozen Oct 8 export: read-only
- No strategy implementation or deployment
