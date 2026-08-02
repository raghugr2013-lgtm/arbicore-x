"""ArbiCore X — D-4 Hotfix-4 · Helius holder_count fact-projection fallback.

Background
----------
Helius `getTokenLargestAccounts` RPC returns at most the top-20 accounts
holding a token, NOT the total on-chain holder count. The previous code
at ``helius_venue_provider.py:279`` computed ``holder_count = len(holders)``
which always tops out at 20 and unconditionally trips Gate-1's
``holders < min_holders`` denial (default ``min_holders=25``) on healthy
tokens. The shadow validation report flagged this as the dominant
denial term on jupiter_trending candidates.

Hotfix-4 introduces a fact-projection fallback: when the Helius-derived
count is at the API-cap sentinel (≤ 20) and the candidate's
``hint_metric.holder_count`` (sourced from Jupiter DataAPI's
authoritative ``base_asset.holderCount`` at ``sources.py:420``) is
strictly larger, prefer the hint value.

INV-3 — preserved. The holders LIST (used for top-N concentration
analysis) remains Helius-sourced; only the COUNT term is corrected to
a chain-authoritative value sourced from a different venue read.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
import os
import inspect

import pytest

from arbicore.models.discovery import DiscoveryCandidate, OpportunityType
from arbicore.scanners.launch_arbitrage import helius_venue_provider as hvp


def _make_candidate(*, hint_holder_count: Optional[int] = None,
                    mint: str = "TestMint111") -> DiscoveryCandidate:
    hm: Dict[str, Any] = {"launchpad": "jupiter_trending"}
    if hint_holder_count is not None:
        hm["holder_count"] = hint_holder_count
    return DiscoveryCandidate(
        candidate_id=f"c:{mint}",
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        hint_source="jupiter_trending",
        hint_observed_at=0.0,
        subject_id=f"solana:{mint}",
        asset=mint[:10],
        candidate_venues=["jupiter:solana"],
        hint_metric=hm,
        reason="test",
    )


# ---- 1. Pure-projection unit tests (no Helius RPC; assert the cap rule) ----

@pytest.mark.parametrize(
    "helius_count, hint_count, expected, label",
    [
        (0,    0,    0,    "both zero → 0"),
        (0,    150,  150,  "Helius null, hint healthy → use hint"),
        (15,   500,  500,  "Helius underestimate (<20), hint healthy → use hint"),
        (20,   1200, 1200, "Helius at exact API cap, hint healthy → use hint"),
        (20,   20,   20,   "Helius at cap, hint equal → use Helius (no strict gain)"),
        (20,   5,    20,   "Helius at cap, hint lower → use Helius"),
        (21,   500,  21,   "Helius above cap sentinel → use Helius (paranoid guard)"),
        (50,   500,  50,   "Helius reports >cap (impossible today but future-proof) → use Helius"),
        (10,   0,    10,   "Helius non-empty, hint missing → use Helius"),
    ],
)
def test_hotfix4_holder_count_projection_rule(
    helius_count: int, hint_count: int, expected: int, label: str
):
    """Pure projection rule. Mirrors the inline logic at
    ``helius_venue_provider.py:279``: if Helius count ≤ 20 sentinel AND
    hint strictly greater → use hint, else use Helius."""
    helius_holder_count = helius_count
    hint_holder_count = hint_count
    if helius_holder_count <= 20 and hint_holder_count > helius_holder_count:
        out = hint_holder_count
    else:
        out = helius_holder_count
    assert out == expected, f"{label}: expected {expected}, got {out}"


# ---- 2. AST source-inspection regression guard ------------------------------

def test_hotfix4_source_inspection():
    """Catch accidental regressions of the fact-projection block in
    helius_venue_provider.__call__. We assert the literal SHA-stable
    fragments rather than mocking the whole venue-provider pipeline."""
    src = inspect.getsource(hvp.HeliusLaunchVenueProvider.__call__)
    assert "helius_holder_count = len(holders)" in src
    assert "hint_holder_count = int(hint.get(\"holder_count\") or 0)" in src
    assert "if helius_holder_count <= 20 and hint_holder_count > helius_holder_count" in src
    # The pre-Hotfix-4 single-line assignment must not coexist with the new block.
    # (Use a leading whitespace prefix to avoid the substring matching the new
    # ``helius_holder_count = len(holders)`` line.)
    import re
    bare = re.findall(r"^\s+holder_count = len\(holders\)\s*$", src, re.M)
    assert bare == [], \
        "Hotfix-4 regressed: bare `holder_count = len(holders)` reappeared"


# ---- 3. INV-3 — provenance preservation -------------------------------------

def test_hotfix4_holders_list_still_helius_sourced():
    """The holders LIST (used for top-N concentration analysis) must
    remain Helius-sourced. The fallback ONLY adjusts the COUNT used
    by the holders gate term. This preserves INV-3: source_data_quality
    provenance for the holders array is unchanged."""
    src = inspect.getsource(hvp.HeliusLaunchVenueProvider.__call__)
    # The dict literal exporting the holders LIST must still pull from
    # the Helius-RPC list, not from any hint field.
    assert '"holders":                    holders,' in src
    # No code path should overwrite the holders LIST from hint
    assert 'holders = hint' not in src
    assert "holders = candidate.hint" not in src


# ---- 4. INV-2 — substrate purity (no EmissionBus / .emit() in fallback) -----

def test_hotfix4_no_emission_bus():
    """The fallback block must not emit canonical opportunities or
    construct any. Verified by source inspection of the entire
    ``HeliusLaunchVenueProvider`` class."""
    src = inspect.getsource(hvp.HeliusLaunchVenueProvider)
    assert "EmissionBus" not in src
    assert ".emit(" not in src
    assert "CanonicalOpportunity" not in src


# ---- 5. Integration smoke — full __call__ with monkey-patched RPCs ---------

class _FakeProvider:
    """Builds a usable HeliusLaunchVenueProvider with all external IO
    deterministically mocked so we can assert the projected count
    appears in the returned ``token_intel["holders"]``."""

    @staticmethod
    def make(monkeypatch, *, helius_top_n: int, hint_holders: Optional[int]):
        os.environ.setdefault("HELIUS_API_KEY", "test-key-xxxxxxxxxx")
        prov = hvp.HeliusLaunchVenueProvider()

        # Stub the 4 external HTTP touch-points to deterministic returns
        async def _mint_state(mint: str):
            return {
                "mint_authority_revoked": True,
                "freeze_authority_revoked": True,
                "supply": 1_000_000_000,
            }

        async def _largest_holders(mint: str):
            # Return helius_top_n synthetic top-holder rows
            return [
                {"address": f"acct{i}", "amount": 1000 - i, "decimals": 6}
                for i in range(helius_top_n)
            ]

        async def _dexscreener_best_pool(mint: str):
            return None  # liquidity_usd will default to 0.0 — that's fine

        async def _detect_lp_burn(**_kw):
            return 100.0

        async def _pumpfun(_m):
            return None

        monkeypatch.setattr(prov, "_rpc_get_mint_state", _mint_state)
        monkeypatch.setattr(prov, "_rpc_get_largest_holders", _largest_holders)
        monkeypatch.setattr(prov, "_dexscreener_best_pool", _dexscreener_best_pool)
        monkeypatch.setattr(prov, "_detect_lp_burn", _detect_lp_burn)
        monkeypatch.setattr(prov, "_pumpfun_coin_state", _pumpfun)
        return prov


def test_hotfix4_integration_projects_hint_when_helius_capped(monkeypatch):
    """End-to-end through __call__: Helius returns 20 (cap), hint says
    1500 → token_intel.holders MUST be 1500."""
    prov = _FakeProvider.make(monkeypatch, helius_top_n=20, hint_holders=1500)
    cand = _make_candidate(hint_holder_count=1500)
    out = asyncio.run(prov(cand))
    assert out is not None
    assert out["token_intel"]["holders"] == 1500


def test_hotfix4_integration_uses_helius_when_no_hint(monkeypatch):
    """Helius returns 18, hint absent → token_intel.holders = 18 (Helius)."""
    prov = _FakeProvider.make(monkeypatch, helius_top_n=18, hint_holders=None)
    cand = _make_candidate(hint_holder_count=None)
    out = asyncio.run(prov(cand))
    assert out is not None
    assert out["token_intel"]["holders"] == 18


def test_hotfix4_integration_uses_helius_when_hint_lower(monkeypatch):
    """Helius returns 20 (cap), hint says 5 (anomalously low) → use
    Helius. The fallback never down-counts a verified Helius read."""
    prov = _FakeProvider.make(monkeypatch, helius_top_n=20, hint_holders=5)
    cand = _make_candidate(hint_holder_count=5)
    out = asyncio.run(prov(cand))
    assert out is not None
    assert out["token_intel"]["holders"] == 20


def test_hotfix4_integration_holders_list_unchanged(monkeypatch):
    """INV-3: the holders LIST in the returned facts is still the
    Helius-sourced top-N (length 20), independent of the projected
    COUNT (1500). Concentration analysis downstream remains correct."""
    prov = _FakeProvider.make(monkeypatch, helius_top_n=20, hint_holders=1500)
    cand = _make_candidate(hint_holder_count=1500)
    out = asyncio.run(prov(cand))
    assert out is not None
    assert isinstance(out["holders"], list)
    assert len(out["holders"]) == 20            # still 20 Helius rows
    assert out["token_intel"]["holders"] == 1500   # but the COUNT is corrected
