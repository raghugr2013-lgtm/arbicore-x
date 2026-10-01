# Balancer P0 on certified H06 — Checkpoint

- Status: **PASS** (extract-port; SHADOW / no deploy)
- Implementation SHA: `520b0cc2351fd5df461b79ff4cf72a19d0b7442e`
- Immediate parent: `28a9da3c272e5163eced98eea3f462fb20d50640` (H06 PASS manifest)
- Certified H06 SHA: `7c2b1bce4ca97cb3aa753ed9dff6d67a9be168b4`
- Tag: `arbicore-p0-balancer-quote-on-h06-20261001`
- Date: 2026-10-01
- Source reused: `f27da21` discovery + tests (byte-identical); quoter registration adapted to H06

## Files changed vs H06

- `app/backend/arbicore/discovery/balancer_v2_pool_discovery.py` (added, identical to f27da21)
- `app/backend/tests/test_p0_balancer_v2_quote.py` (added, identical to f27da21)
- `app/backend/arbicore/execution/quoter.py` (+79 lines only: `BalancerV2Quoter` class + `default_backends` registration)

`quoter.py` was **not** replaced. Existing UniV3/Aerodrome/Sushi/Pancake/Algebra backends remain.

## Compatibility refinement

Required: insert `BalancerV2Quoter()` into H06's longer `default_backends` list (H06 already had Sushi/Pancake/Camelot/QuickSwap). `_eth_call` / `HopQuote` / `_fallback_hop` signatures matched; no adapter rewrite.

## Tests

- `test_p0_balancer_v2_quote.py`: **40 passed**
- P0 + H06/H05/SP/quoter/economics subset: **236 passed, 1 failed**
- Pre-existing on H06 (identical blob, not caused by P0):
  `test_phase10_10_8_live_quoter.py::TestUniV3QuoterV2::test_unsupported_chain`
  (H06 maps Polygon to UniV3 QuoterV2, so the old no-adapter assertion is stale)

## Safety

- Protected execution/safety/economics blobs unchanged vs `7c2b1bc`
- `$25` Gate 7 unchanged
- Read-only quote adapter; no signing/broadcast
- SHADOW; no production deploy
