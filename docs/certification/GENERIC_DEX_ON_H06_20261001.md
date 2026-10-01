# GENERIC_DEX on certified H06 — Checkpoint

- Status: **PASS** (extract-port; SHADOW / no deploy / not scanner-activated)
- Implementation SHA: `f57e8538536f4f1921eef3d4739721df4c627e38`
- Immediate parent: `96390f2b3df78b04f75e57e4ec85a619b46fa60f` (P1b cert docs)
- P1b SHA: `d7e2418415a9a8246268f7bbc92e8bf95aba44fe`
- H06 PASS: `7c2b1bce4ca97cb3aa753ed9dff6d67a9be168b4`
- Tag: `arbicore-generic-dex-on-h06-20261001`
- Date: 2026-10-01
- Source reused: `f4d4c62` engine + tests (byte-identical; includes `57618f6` gas integration)

## Files changed vs P1b

- `app/backend/arbicore/scanners/generic_dex_route_engine.py` (added)
- `app/backend/tests/test_generic_dex_route_engine.py` (added)
- `app/backend/tests/test_generic_dex_gas_integration.py` (added)

Not modified: `quoter.py`, Balancer P0/P1/P1b modules, protected safety/economics, composition/scanner boot.

The engine is library-only. It is **not** wired into `runtime/composition.py` and does not start discovery.

## Tests

- GENERIC_DEX engine + gas: **53 passed** (pre-existing asyncio mark warnings in extracted gas tests; not weakened)
- Combined P0+P1+P1b+GENERIC_DEX+H06 safety/economics: **218 passed**

## Safety

- `MIN_ATOMIC_PROFIT_USD = 25.0`; constructor may only raise the floor
- Protected execution/safety/economics unchanged vs `7c2b1bc`
- No signing, broadcast, or live execution
- Production remains `arbicore-x-backend:g5.79-green-20260927` / SHADOW / autostart false
