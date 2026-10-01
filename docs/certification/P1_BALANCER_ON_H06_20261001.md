# Balancer P1 on certified H06 — Checkpoint

- Status: **PASS** (extract-port; SHADOW / no deploy)
- Implementation SHA: `76eb0033325d91767b701b37cde27d427b416d3e`
- Immediate parent: `ae8a4de1b5ae65ea8ae915238065a19aa0d936ee` (P0 cert docs)
- P0 SHA: `520b0cc2351fd5df461b79ff4cf72a19d0b7442e`
- H06 PASS: `7c2b1bce4ca97cb3aa753ed9dff6d67a9be168b4`
- Tag: `arbicore-p1-balancer-enum-on-h06-20261001`
- Date: 2026-10-01
- Source reused: `334385e` enumeration + tests (byte-identical)

## Files changed vs P0

- `app/backend/arbicore/discovery/balancer_v2_pool_enumeration.py` (added)
- `app/backend/tests/test_p1_balancer_v2_enumeration.py` (added)

P0 discovery, P0 tests, and `quoter.py` were not modified.

## Tests

- P1 focused: **36 passed**
- P0 + P1 + H06 RPC-gate + SP1 + SP5 + mode + Gate 7 economics: **138 passed**

## Safety

- Protected execution/safety/economics unchanged vs `7c2b1bc`
- `$25` floor unchanged
- Read-only candidate discovery; unconfigured subgraph = DISCOVERY_UNAVAILABLE
- SHADOW; no production deploy
