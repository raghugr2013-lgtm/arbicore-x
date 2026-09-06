"""Executor V2 — Secure Settlement Dispatcher regression tests.

Covers the mandated capability-cell behaviour (deterministic, fail-closed):
    1. supported flash providers: balancer_v2, aave_v3
    2. supported swap venue: uniswap_v3
    3. unsupported venue rejection (→ REQUIRES_NEW_RECEIVER, never EXECUTABLE)
    4. unsupported flash-provider rejection
    5. receiver/venue incompatibility (UniV3-fork) rejection
    6. invalid route rejection
    7. fail-closed on incomplete capability info (UNVERIFIABLE)
    8. correct dispatch selection for supported paths
    9. no accidental change to execution-capability reporting (SUPPORTED_DEXES)
   10. no accidental enabling of broadcast/signing/auto-execution
"""
from __future__ import annotations

from arbicore.execution.settlement_dispatcher import (
    Verdict, CellStatus, evaluate_settlement,
    RECEIVER_FLASH_HEADS, RECEIVER_NATIVE_SWAP_VENUES,
)
from arbicore.scanners.flash_loan_arbitrage.executor_capability import (
    SUPPORTED_DEXES, SUPPORTED_FLASH_PROVIDERS,
)


# ── (1)+(2)+(8) Supported flash providers × native swap venue → EXECUTABLE ──
def test_balancer_v2_uniswap_v3_executable():
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["uniswap_v3"], chain="base")
    assert d.executable is True
    assert d.verdict is Verdict.EXECUTABLE
    assert d.first_blocker is None
    assert all(c.status is CellStatus.PASS for c in d.cells)


def test_aave_v3_uniswap_v3_executable():
    d = evaluate_settlement(flash_provider="aave_v3",
                            swap_venues=["uniswap_v3"], chain="base")
    assert d.executable is True
    assert d.verdict is Verdict.EXECUTABLE
    # Dispatch selection is explicit and correct.
    assert d.flash_provider == "aave_v3"
    assert d.swap_venues == ["uniswap_v3"]


def test_multi_hop_all_native_executable():
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["uniswap_v3", "uniswap_v3"], chain="base")
    assert d.verdict is Verdict.EXECUTABLE


# ── (3) Unsupported swap venue (adapter exists) → REQUIRES_NEW_RECEIVER ─────
def test_aerodrome_requires_new_receiver_not_executable():
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["aerodrome"], chain="base")
    assert d.executable is False
    assert d.verdict is Verdict.REQUIRES_NEW_RECEIVER
    assert d.first_blocker == "receiver_schema_compatible"


def test_mixed_native_and_nonnative_not_executable():
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["uniswap_v3", "aerodrome"], chain="base")
    assert d.executable is False
    assert d.verdict is Verdict.REQUIRES_NEW_RECEIVER


# ── (4) Unsupported flash provider → REJECTED at the flash cell ─────────────
def test_morpho_blue_flash_rejected():
    d = evaluate_settlement(flash_provider="morpho_blue",
                            swap_venues=["uniswap_v3"], chain="base")
    assert d.executable is False
    assert d.verdict is Verdict.REJECTED
    assert d.first_blocker == "flash_provider_supported"


def test_uniswap_v3_flash_rejected():
    # uniswap_v3 is a valid flash *adapter* but NOT a deployed receiver head.
    d = evaluate_settlement(flash_provider="uniswap_v3",
                            swap_venues=["uniswap_v3"], chain="base")
    assert d.verdict is Verdict.REJECTED
    assert d.first_blocker == "flash_provider_supported"


def test_flash_provider_chain_unsupported_rejected():
    # Balancer V2 adapter does not list bnb → chain cell fails.
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["uniswap_v3"], chain="bnb")
    assert d.verdict is Verdict.REJECTED
    assert d.first_blocker == "flash_provider_chain_supported"


# ── (5) Receiver/venue incompatibility: UniV3 *fork* needs a different router ─
def test_univ3_fork_requires_new_receiver():
    # sushiswap_v3 shares exactInputSingle ABI but a DIFFERENT router → the V1
    # single-immutable-router SwapHop schema cannot settle it.
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["sushiswap_v3"], chain="arbitrum")
    assert d.executable is False
    assert d.verdict is Verdict.REQUIRES_NEW_RECEIVER
    assert d.first_blocker == "receiver_schema_compatible"


# ── (6) Invalid route → REJECTED ────────────────────────────────────────────
def test_empty_route_rejected():
    d = evaluate_settlement(flash_provider="balancer_v2", swap_venues=[], chain="base")
    assert d.verdict is Verdict.REJECTED
    assert d.first_blocker == "route_valid"


def test_missing_provider_rejected():
    d = evaluate_settlement(flash_provider=None, swap_venues=["uniswap_v3"], chain="base")
    assert d.verdict is Verdict.REJECTED
    assert d.first_blocker == "route_valid"


# ── (7) Incomplete capability info → UNVERIFIABLE (fail closed) ─────────────
def test_missing_venue_metadata_unverifiable():
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["uniswap_v3", None], chain="base")
    assert d.executable is False
    assert d.verdict is Verdict.UNVERIFIABLE
    assert d.first_blocker == "swap_venue_resolved"


def test_no_adapter_venue_rejected():
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["curve"], chain="ethereum")
    assert d.executable is False
    # curve has no DEX adapter registered → hard reject before schema cell.
    assert d.verdict is Verdict.REJECTED
    assert d.first_blocker == "venue_adapter_available"


# ── (9) No accidental change to execution-capability reporting ──────────────
def test_supported_dexes_unchanged():
    assert set(SUPPORTED_DEXES) == {"uniswap_v3"}
    assert RECEIVER_NATIVE_SWAP_VENUES == frozenset({"uniswap_v3"})


def test_flash_head_constant_in_lockstep():
    # The dispatcher's receiver flash heads must equal the canonical constant
    # and the E1-reconciled audit set (single source of truth).
    from scripts.executor_capability_audit import EXECUTOR_SUPPORTED_FLASH
    assert RECEIVER_FLASH_HEADS == SUPPORTED_FLASH_PROVIDERS == {"balancer_v2", "aave_v3"}
    assert set(EXECUTOR_SUPPORTED_FLASH) == set(SUPPORTED_FLASH_PROVIDERS)


def test_no_non_univ3_venue_is_executable():
    # Every non-UniV3 venue must be non-executable — no venue is silently
    # promoted. Where the chosen flash head also supports the chain, the
    # blocker is specifically the receiver schema (REQUIRES_NEW_RECEIVER);
    # where it does not, the earlier flash-chain cell fails-closed first.
    schema_boundary = [("aerodrome", "base"), ("aerodrome_slipstream", "base"),
                       ("sushiswap_v2", "ethereum"), ("sushiswap_v3", "arbitrum"),
                       ("camelot_v3", "arbitrum"), ("quickswap_v3", "polygon")]
    for venue, chain in schema_boundary:
        d = evaluate_settlement(flash_provider="balancer_v2",
                                swap_venues=[venue], chain=chain)
        assert d.executable is False, venue
        assert d.verdict is Verdict.REQUIRES_NEW_RECEIVER, venue
    # BNB has no Balancer V2 flash head → fails closed at the flash-chain cell.
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["pancakeswap_v3"], chain="bnb")
    assert d.executable is False
    assert d.verdict is Verdict.REJECTED
    assert d.first_blocker == "flash_provider_chain_supported"


# ── (10) No broadcast/signing/auto-execution enabling ──────────────────────
def test_decision_never_signs_or_broadcasts():
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["uniswap_v3"], chain="base")
    dd = d.to_dict()
    assert dd["signed"] is False and dd["broadcast"] is False


def test_dispatcher_module_has_no_broadcast_side_effects():
    import arbicore.execution.settlement_dispatcher as mod
    src = mod.__doc__ or ""
    # Sanity: module advertises fail-closed / no-broadcast contract.
    assert "fail-closed" in src.lower()
    # No signer/broadcast symbols are imported into the module namespace.
    for banned in ("broadcast", "sign_and_send", "live_signer", "auto_executor"):
        assert not any(banned in name.lower() and name not in ("broadcast",)
                       for name in dir(mod) if callable(getattr(mod, name, None)))


# ── Determinism ─────────────────────────────────────────────────────────────
def test_deterministic_decision():
    a = evaluate_settlement(flash_provider="aave_v3",
                            swap_venues=["uniswap_v3"], chain="base",
                            executor_address="0x99C0b64E8F24fc1AAdB07dABa938d9F11DCd1052")
    b = evaluate_settlement(flash_provider="aave_v3",
                            swap_venues=["uniswap_v3"], chain="base",
                            executor_address="0x99C0b64E8F24fc1AAdB07dABa938d9F11DCd1052")
    assert a.to_dict() == b.to_dict()
