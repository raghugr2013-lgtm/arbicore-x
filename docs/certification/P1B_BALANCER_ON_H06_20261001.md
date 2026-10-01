# Balancer P1b on certified H06 — Checkpoint

- Status: **PASS** (extract-port; SHADOW / no deploy)
- Implementation SHA: `d7e2418415a9a8246268f7bbc92e8bf95aba44fe`
- Immediate parent: `686365fb13cc031420c4b07dd2a852f8825cc5d9` (P1 cert docs)
- P1 SHA: `76eb0033325d91767b701b37cde27d427b416d3e`
- H06 PASS: `7c2b1bce4ca97cb3aa753ed9dff6d67a9be168b4`
- Tag: `arbicore-p1b-balancer-onchain-on-h06-20261001`
- Date: 2026-10-01
- Source reused: `457bad0` on-chain source + tests (byte-identical)

## Files changed vs P1

- `app/backend/arbicore/discovery/balancer_v2_onchain_source.py` (added)
- `app/backend/tests/test_p1b_balancer_v2_onchain_source.py` (added)

P0 discovery, P1 enumeration, and `quoter.py` were not modified.

## Tests

- P1b focused: **19 passed**
- P0 + P1 + P1b + H06 RPC-gate + SP1 + mode + Gate 7: **146 passed**

## Safety

- Protected execution/safety/economics unchanged vs `7c2b1bc`
- `$25` floor unchanged
- Read-only `eth_getLogs`; no API key; RPC failures fail closed
- SHADOW; no production deploy
