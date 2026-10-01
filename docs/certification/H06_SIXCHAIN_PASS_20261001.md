# H06 Six-Chain Runtime — Independent PASS Manifest

- Status: **PASS**
- Certified SHA: `7c2b1bce4ca97cb3aa753ed9dff6d67a9be168b4`
- Parent SHA: `7f45ec2fa17dacb2a8a472573269b1b4c8422faf`
- Branch: `phase-b/h06-six-chain-runtime`
- Permanent tag: `arbicore-h06-sixchain-pass-20261001`
- Certification date: 2026-10-01
- Certifier: independent VPS auditor (detached checkout `/tmp/arbicore-phase-b-h06-remediation-cert-7c2b1bc`)

## Scope certified

Six-chain runtime **seam** on the canonical safety line after the H06-R1
operator-RPC-gate remediation. Non-Base chains remain operator-gated and
dormant. This does **not** certify live six-chain trading, scanner
activation, production deployment, Phase C, GENERIC_DEX, or Balancer.

## Test evidence (independent, docker, `--network none`)

- Operator-RPC gate tests: 4 passed (`test_h06_evm_eth_call_operator_rpc_gate.py`)
- H06 + H05 + H05 remediation + SP1–SP5: 141 passed (parent overlap 137 + 4 new)
- Safety / RPC / quote-seam subset: 177 passed, 2 failed
- Pre-existing parent-identical failures (not H06 regressions):
  - `test_six_chain_rpc_seam.py::test_env_template_lists_all_twelve_names`
  - `test_wave7_calldata_and_broadcast.py::TestBroadcasterGateLadder::test_missing_confirm_holds`

## Protected safety status

Blob-identical to parent `7f45ec2` and to canonical `5bd9525` for:

- `app/backend/arbicore/execution/mode.py`
- `app/backend/arbicore/execution/live_signer.py`
- `app/backend/arbicore/execution/broadcast.py`
- `app/backend/arbicore/execution/kill_switch.py`
- `app/backend/arbicore/execution/pre_broadcast.py`
- `app/backend/arbicore/safety/*`
- `app/backend/arbicore/economics/net_profit.py`
- `app/backend/arbicore/scanners/flash_loan_arbitrage/exact_size_sizer.py`

Gate 7 default remains `min_atomic_profit_usd = 25.0`.

## SHADOW / execution status

- Flash-loan default mode: SHADOW
- Broadcast allowed only in LIMITED_LIVE / FULL_LIVE
- Production env observed at certification:
  - `ARBICORE_EXECUTION_MODE=SHADOW`
  - `ARBICORE_AUTOEXEC_AUTOSTART=false`
  - `ARBICORE_RUNTIME_AUTOSTART=false`
- H05 remains opt-in
- No signing path enabled
- No broadcast path enabled

## Deployment status

- No production deploy, rebuild, or service restart for this certification
- Workspace/production backends remained on `arbicore-x-backend:g5.79-green-20260927` (`4fec11f`)
- H06 source was published to GitHub as a fast-forward only (`7f45ec2..7c2b1bc`)
