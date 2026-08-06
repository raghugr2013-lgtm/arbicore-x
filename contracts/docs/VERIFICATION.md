# ArbiCore X — Executor Verification Checklist

Post-deploy checklist that MUST pass before promoting the executor from
`SHADOW` to `LIMITED_LIVE` mode. Every item below produces an
artefact — attach every artefact to the operator handover doc.

---

## 0. Pre-flight (before ever calling `--broadcast`)

- [ ] `forge build` on `/app/contracts` compiles clean (only lints, no
      errors).
- [ ] `forge test` reports **8 / 8 passing** (see
      `contracts/tests/FlashLoanReceiver.t.sol`).
- [ ] `cast sig 'execute(address[],uint256[],bytes)'` returns
      `0x64ba4bc1`.
- [ ] `cast sig 'executeAave(address,uint256,bytes)'` returns
      `0x4343d8b2`.
- [ ] Python-side selector parity — the Python encoder emits the same
      selectors:
      ```bash
      cd /app/app/backend && python3 -c "
      from arbicore.execution.calldata import (
          encode_executor_execute, encode_executor_execute_aave)
      assert encode_executor_execute(
          executor_address='0x0000000000000000000000000000000000000001',
          tokens=['0x0000000000000000000000000000000000000002'],
          amounts=[1]).selector_hex == '0x64ba4bc1'
      assert encode_executor_execute_aave(
          executor_address='0x0000000000000000000000000000000000000001',
          asset='0x0000000000000000000000000000000000000002',
          amount_wei=1).selector_hex == '0x4343d8b2'
      print('selectors OK')"
      ```

## 1. On-chain identity

- [ ] Deployed address is captured in
      `broadcast/Deploy.s.sol/<chainId>/run-latest.json`.
- [ ] `cast call <address> "owner()(address)" --rpc-url <chain>` returns
      the deployer EOA (matches the address in `--private-key`).
- [ ] `cast call <address> "balancerVault()(address)" --rpc-url <chain>`
      returns `0xBA12222222228d8Ba445958a75a0704d566BF2C8` (Balancer V2
      Vault, same on every chain).
- [ ] `cast call <address> "aavePool()(address)" --rpc-url <chain>`
      returns the canonical Aave V3 Pool for the chain
      (Base: `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5`).
- [ ] `cast call <address> "uniRouter()(address)" --rpc-url <chain>`
      returns the canonical Uniswap V3 SwapRouter02 for the chain
      (Base: `0x2626664c2603336E57B271c5C0b26F421741e481`).

## 2. Source verification

- [ ] BaseScan page for the deployed address shows the contract as
      **verified** (green tick).
- [ ] Constructor args on BaseScan match the values printed by
      `Deploy.s.sol`.
- [ ] BaseScan-reported compiler version is `0.8.24 + optimizer=200 +
      via_ir`.
- [ ] Runtime bytecode length reported by BaseScan matches the local
      artefact:
      ```bash
      python3 -c "import json; d = json.load(open('/app/contracts/out/FlashLoanReceiver.sol/FlashLoanReceiver.json')); print(len(d['deployedBytecode']['object']) // 2, 'bytes')"
      ```

## 3. Selector round-trip

- [ ] A dry-run `cast call` of the executor with a maliciously
      unauthorised payload returns the correct revert selector:
      ```bash
      # From an address that is NOT the owner:
      cast call <address> "execute(address[],uint256[],bytes)" "[]" "[]" "0x" --rpc-url <chain> --from 0xdead000000000000000000000000000000000000
      # ⇒ Error: revert data 0x30cd7471 (NotOwner)
      ```
- [ ] `cast call <address> "receiveFlashLoan(address[],uint256[],uint256[],bytes)" "[]" "[]" "[]" "0x" --rpc-url <chain>`
      ⇒ revert data `0xea8e4eb5` (`NotAuthorized`).
- [ ] `cast call <address> "executeOperation(address,uint256,uint256,address,bytes)" 0x…02 1 0 0x…01 "0x" --rpc-url <chain>`
      ⇒ revert data `0xea8e4eb5` (`NotAuthorized`).

## 4. Backend config wiring

- [ ] `backend/.env` contains
      `ARBICORE_EXECUTOR_ADDRESS_BASE=<deployed-address>`.
- [ ] `sudo supervisorctl restart backend` completes without error.
- [ ] `GET /api/arbicore/runtime/config` returns the address inside
      `executor_addresses.base`.
- [ ] `resolve_executor_address(chain="base")` in
      `arbicore/config/persistent.py` returns the deployed address (via
      Python REPL).

## 5. Regression

- [ ] Full backend regression (`testing_agent`) reports **≥ 221/221
      passing** (baseline post-Slice-7 = 221).
- [ ] Foundry suite reports **8/8 passing**.

## 6. Operational readiness

- [ ] Executor address is documented in the on-call runbook.
- [ ] The rescue key (deployer EOA) is stored offline / in a hardware
      wallet — the runtime signer for LIMITED_LIVE broadcasts is a
      *different* EOA registered via the operator wizard.
- [ ] Kill-switch UI acknowledges the executor is deployed
      (`/api/arbicore/operations/interlock` reports the correct gates
      once the interlock repo is wired).

## 7. Sign-off

Every item ticked → attach the artefact bundle to the operator
handover doc and proceed to Paper Validation. **Do not** promote to
`LIMITED_LIVE` mode until Paper + Shadow Certification pass.
