"""Focused H09 regression tests — P0 / P1-a / P1-b.

Proves the chain-scoped candidate-bound simulation gate:
  * derives signer presence ONLY from authoritative vault evidence (never a
    candidate-supplied boolean),
  * requires derived_address == configured executor signer,
  * enforces candidate binding (quote_block / calldata / receiver_version),
  * pins the read-only eth_call to the EXACT quoted block,
  * never signs or broadcasts, and preserves existing fail-closed semantics.

Hermetic: no network, no DB, no keys. Injected seams only.
"""
import pytest

import arbicore.control.chain_execution_readiness as cer
from arbicore.scanners.flash_loan_arbitrage import live_readiness_probes as lrp
from arbicore.scanners.flash_loan_arbitrage.executor_capability import SUPPORTED_DEXES

_DEX = next(iter(SUPPORTED_DEXES))


class _Pool:
    dex_protocol = _DEX


class _Cap:
    def __init__(self, deployed=True, version_verified=True):
        self.deployed = deployed
        self.version_verified = version_verified
        self.receiver_version = "v1"
        self.bytecode_verified = True

    def supports(self, _h):
        return True


async def _sim_ok(chain, *, eth_call, candidate, quote_facts, executor_address,
                  receiver_capability, signer_evidence=None):
    # Fake probe: echoes a passing on-chain sim bound to the quoted block.
    return {"passed": True, "simulation_kind": "onchain_eth_call",
            "quote_block": quote_facts["quote_block"], "signed": False,
            "broadcast": False, "_signer_evidence_seen": signer_evidence}


def _kw(*, signer_evidence_fn=None, candidate=None, cap=None, executor="0xExec",
        chain_id=8453, simulation_probe_fn=_sim_ok):
    if candidate is None:
        candidate = {"borrow_amount_usd": 10000.0,
                     "executor_entry_calldata": "0x64ba4bc1",
                     "rpc_url": "http://sim"}

    async def _chain_id(_c):
        return chain_id

    async def _quote(_c, _eth, _cand):
        return {"route_quote_status": "ok", "chain": _c, "size_basis": "exact",
                "quote_notional_usd": _cand.get("borrow_amount_usd"),
                "quote_block": 777, "gross_profit_pct": 1.0,
                "quoted_amount_in_wei": 1000}

    async def _econ(_c, _facts, **_k):
        return None

    return dict(
        eth_call_factory=lambda _c: object(),
        chain_id_reader=_chain_id,
        pool_graph_fn=lambda _c: [_Pool()],
        gas_model_fn=lambda _c: object(),
        economic_rpc_fn=lambda _c: True,
        receiver_capability_fn=lambda _c: (cap if cap is not None else _Cap()),
        executor_address_fn=lambda _c: executor,
        liquidity_probe_fn=None,
        quote_probe_fn=_quote,
        economics_probe_fn=_econ,
        simulation_probe_fn=simulation_probe_fn,
        signer_evidence_fn=signer_evidence_fn,
        candidate=candidate,
    )


def _good_signer():
    async def _fn():
        return {"present": True, "derived_address": "0xabc",
                "matches_expected": True}
    return _fn


async def _run(**kw):
    return await cer.evaluate_chain_execution_readiness("base", **_kw(**kw))


# A — authoritative signer + matching config + full binding => SIMULATION PASS
@pytest.mark.asyncio
async def test_A_authoritative_signer_passes():
    r = await _run(signer_evidence_fn=_good_signer())
    assert r["stages"]["SIMULATION"]["status"] == cer.PASS


# B — candidate boolean cannot bypass MISSING vault evidence
@pytest.mark.asyncio
async def test_B_candidate_boolean_cannot_bypass_missing_vault():
    cand = {"borrow_amount_usd": 10000.0, "executor_entry_calldata": "0x64ba4bc1",
            "rpc_url": "http://sim", "signer_present": True}  # fabricated
    r = await _run(signer_evidence_fn=None, candidate=cand)  # no vault provider
    s = r["stages"]["SIMULATION"]
    assert s["status"] == cer.BLOCKED
    assert s["reason"] == "simulation_requires_authoritative_vault_signer"


# C — signer present but derived address mismatches configured signer => BLOCK
@pytest.mark.asyncio
async def test_C_signer_mismatch_blocks():
    async def _mismatch():
        return {"present": True, "derived_address": "0xabc",
                "matches_expected": False}
    r = await _run(signer_evidence_fn=_mismatch)
    assert r["stages"]["SIMULATION"]["status"] == cer.BLOCKED
    assert r["stages"]["SIMULATION"]["reason"] == \
        "simulation_requires_authoritative_vault_signer"


# D — missing candidate binding (calldata / receiver_version) => BLOCK
@pytest.mark.asyncio
async def test_D_missing_binding_blocks():
    no_calldata = {"borrow_amount_usd": 10000.0, "rpc_url": "http://sim"}
    r1 = await _run(signer_evidence_fn=_good_signer(), candidate=no_calldata)
    assert r1["stages"]["SIMULATION"]["reason"] == "simulation_requires_candidate_calldata"

    r2 = await _run(signer_evidence_fn=_good_signer(),
                    cap=_Cap(version_verified=False))
    assert r2["stages"]["SIMULATION"]["reason"] == \
        "simulation_requires_verified_receiver_version"


# E — wrong chain / no executor binding => BLOCK (not PASS)
@pytest.mark.asyncio
async def test_E_wrong_chain_or_executor_blocks():
    r1 = await _run(signer_evidence_fn=_good_signer(), chain_id=1)  # RPC bound wrong
    assert r1["stages"]["SIMULATION"]["status"] == cer.BLOCKED
    r2 = await _run(signer_evidence_fn=_good_signer(), executor=None)
    assert r2["stages"]["SIMULATION"]["status"] == cer.BLOCKED
    assert r2["stages"]["SIMULATION"]["reason"] == "no_executor_address"


# F — a passing SIMULATION remains unsigned / unbroadcast
@pytest.mark.asyncio
async def test_F_pass_is_unsigned_unbroadcast():
    r = await _run(signer_evidence_fn=_good_signer())
    ev = r["stages"]["SIMULATION"]["evidence"]
    assert ev.get("signed") is False and ev.get("broadcast") is False
    assert r["signed"] is False and r["broadcast"] is False


# G — existing fail-closed behavior intact (no RPC)
@pytest.mark.asyncio
async def test_G_failclosed_no_rpc():
    kw = _kw(signer_evidence_fn=_good_signer())
    kw["eth_call_factory"] = lambda _c: None
    r = await cer.evaluate_chain_execution_readiness("base", **kw)
    assert r["stages"]["SIMULATION"]["status"] == cer.BLOCKED
    assert r["stages"]["SIMULATION"]["reason"] == "no_rpc_for_simulation"


# Unit — _default_simulation_probe: candidate boolean ignored + block pin genuine
@pytest.mark.asyncio
async def test_unit_probe_ignores_candidate_bool_and_pins_block(monkeypatch):
    captured = {}

    async def _fake_probe(**kw):
        captured.update(kw)
        return {"passed": True, "block_tag": kw["block_tag"],
                "signed": False, "broadcast": False}

    monkeypatch.setattr(lrp, "probe_atomic_simulation", _fake_probe)

    # candidate claims signer_present True, but NO authoritative evidence.
    res = await cer._default_simulation_probe(
        "base", eth_call=object(),
        candidate={"executor_entry_calldata": "0x64ba4bc1", "rpc_url": "http://sim",
                   "signer_present": True},
        quote_facts={"quote_block": 777}, executor_address="0xExec",
        receiver_capability=None, signer_evidence=None)
    assert captured["signer_present"] is False          # fabricated bool ignored
    assert captured["from_address"] is None
    assert captured["block_tag"] == hex(777)            # pinned to quoted block
    assert res["quote_block"] == 777                    # derived from pin, not copied

    # authoritative evidence present + matching => signer used as from_address
    captured.clear()
    res2 = await cer._default_simulation_probe(
        "base", eth_call=object(),
        candidate={"executor_entry_calldata": "0x64ba4bc1", "rpc_url": "http://sim"},
        quote_facts={"quote_block": 777}, executor_address="0xExec",
        receiver_capability=None,
        signer_evidence={"present": True, "derived_address": "0xSigner",
                         "matches_expected": True})
    assert captured["signer_present"] is True
    assert captured["from_address"] == "0xSigner"
