"""Six-chain canonical execution-document generator — deterministic tests.

Proves every non-Base chain's flash-loan-arb candidate produces the SAME
canonical execution document the pipeline consumes, with correct
borrow_amount_wei / swap_hops / token ordering / venue / provider / economics,
while unsupported venues and missing executors stay fail-closed and no
signer/broadcast logic is touched.
"""
from __future__ import annotations

import pytest

from arbicore.execution.multichain_opportunity_doc import build_execution_document

NON_BASE = ["ethereum", "arbitrum", "optimism", "polygon", "bnb"]
# Chains with a genuinely available flash head (Balancer V2 / Aave V3). BNB has
# NEITHER on-chain today ⇒ flash-loan arb is fail-closed there (honest).
EXEC_CHAINS = ["ethereum", "arbitrum", "optimism", "polygon"]

# Per-chain token addresses (illustrative but well-formed) for the test routes.
WETH = {c: f"0x{'e'*39}1" for c in NON_BASE + ["base"]}
USDC = {c: f"0x{'d'*39}2" for c in NON_BASE + ["base"]}
DAI  = {c: f"0x{'c'*39}3" for c in NON_BASE + ["base"]}


def _dex_dex(chain, provider="balancer_v2", amount_wei=10**15):
    return {
        "chain": chain, "opportunity_id": f"opp:{chain}:dd",
        "flash_loan_provider": provider,
        "borrow": {"symbol": "WETH", "address": WETH[chain], "decimals": 18,
                   "amount_wei": amount_wei, "amount_usd": 3.20},
        "route": [
            {"dex": "uniswap_v3", "token_in": "WETH", "token_in_addr": WETH[chain],
             "token_out": "USDC", "token_out_addr": USDC[chain], "fee": 500},
            {"dex": "uniswap_v3", "token_in": "USDC", "token_in_addr": USDC[chain],
             "token_out": "WETH", "token_out_addr": WETH[chain], "fee": 3000},
        ],
        "economics": {"net_profit_usd": 0.0},
    }


def _triangular(chain):
    return {
        "chain": chain, "opportunity_id": f"opp:{chain}:tri",
        "flash_loan_provider": "balancer_v2",
        "borrow": {"symbol": "WETH", "address": WETH[chain], "decimals": 18,
                   "amount_wei": 5 * 10**14, "amount_usd": 1.6},
        "route": [
            {"dex": "uniswap_v3", "token_in": "WETH", "token_in_addr": WETH[chain],
             "token_out": "USDC", "token_out_addr": USDC[chain], "fee": 500},
            {"dex": "uniswap_v3", "token_in": "USDC", "token_in_addr": USDC[chain],
             "token_out": "DAI", "token_out_addr": DAI[chain], "fee": 100},
            {"dex": "uniswap_v3", "token_in": "DAI", "token_in_addr": DAI[chain],
             "token_out": "WETH", "token_out_addr": WETH[chain], "fee": 3000},
        ],
        "economics": {"net_profit_usd": 0.0},
    }


# ── (1)+(3)+(4)+(5)+(6)+(7) valid candidate → correct canonical document ─────
@pytest.mark.parametrize("chain", EXEC_CHAINS)
def test_valid_candidate_produces_canonical_document(chain):
    r = build_execution_document(_dex_dex(chain), executor_deployed=True)
    assert r["ok"] is True and r["verdict"] == "EXECUTABLE", (chain, r["reason"])
    doc = r["execution_document"]
    # required canonical keys the pipeline certifier consumes
    for k in ("chain", "borrow_token", "borrow_amount_wei", "borrow_amount_usd",
              "flash_loan_provider", "swap_hops"):
        assert k in doc, (chain, k)
    assert doc["chain"] == chain
    assert doc["flash_loan_provider"] == "balancer_v2"          # (6)
    assert doc["dex_path"] == ["uniswap_v3", "uniswap_v3"]       # (5)
    assert doc["opportunity_type"] == "dex_dex"
    assert doc["net_profit_usd"] == 0.0                          # (7) from route
    assert doc["token_path"] == ["WETH", "USDC", "WETH"]         # (4) ordering


@pytest.mark.parametrize("chain", EXEC_CHAINS)
def test_borrow_amount_wei_correct(chain):                      # (2)
    r = build_execution_document(_dex_dex(chain, amount_wei=777), executor_deployed=True)
    assert r["execution_document"]["borrow_amount_wei"] == 777


@pytest.mark.parametrize("chain", EXEC_CHAINS)
def test_swap_hops_correct(chain):                              # (3)
    doc = build_execution_document(_dex_dex(chain, amount_wei=999),
                                   executor_deployed=True)["execution_document"]
    hops = doc["swap_hops"]
    assert len(hops) == 2
    assert hops[0]["token_in"] == WETH[chain] and hops[0]["token_out"] == USDC[chain]
    assert hops[1]["token_in"] == USDC[chain] and hops[1]["token_out"] == WETH[chain]
    assert hops[0]["fee_tier_bps"] == 5 and hops[1]["fee_tier_bps"] == 30  # 500/3000 ppm
    assert hops[0]["amount_in_wei"] == 999 and hops[1]["amount_in_wei"] == 0  # forward
    assert all(h["amount_out_min_wei"] == 0 for h in hops)


@pytest.mark.parametrize("chain", EXEC_CHAINS)
def test_triangular_and_provider_variants(chain):
    doc = build_execution_document(_triangular(chain), executor_deployed=True)["execution_document"]
    assert doc["opportunity_type"] == "triangular"
    assert doc["token_path"] == ["WETH", "USDC", "DAI", "WETH"]
    assert len(doc["swap_hops"]) == 3
    # aave_v3 provider variant is also representable (capability head)
    r = build_execution_document(_dex_dex(chain, provider="aave_v3"), executor_deployed=True)
    assert r["ok"] and r["execution_document"]["flash_loan_provider"] == "aave_v3"


# ── (8) Unsupported venue remains fail-closed (no document) ──────────────────
@pytest.mark.parametrize("chain", EXEC_CHAINS)
def test_unsupported_venue_fail_closed(chain):
    c = _dex_dex(chain)
    c["route"][0]["dex"] = "aerodrome"          # non-UniV3 → V1 cannot settle
    r = build_execution_document(c, executor_deployed=True)
    assert r["ok"] is False
    assert r["execution_document"] is None
    assert r["verdict"] == "REQUIRES_NEW_RECEIVER"


@pytest.mark.parametrize("chain", NON_BASE)
def test_unsupported_provider_fail_closed(chain):
    r = build_execution_document(_dex_dex(chain, provider="morpho_blue"), executor_deployed=True)
    assert r["ok"] is False and r["execution_document"] is None


# ── (9) Missing executor still blocks execution (no document) ────────────────
@pytest.mark.parametrize("chain", NON_BASE)
def test_missing_executor_blocks(chain):
    r = build_execution_document(_dex_dex(chain))   # executor_deployed=None ⇒ registry
    assert r["ok"] is False and r["execution_document"] is None
    # ETH/ARB/OP/POLY hit executor gate; BNB has no Balancer head (earlier gate).
    assert r["verdict"] == "REJECTED"


@pytest.mark.parametrize("chain", NON_BASE)
def test_explicit_no_executor_blocks(chain):
    r = build_execution_document(_dex_dex(chain), executor_deployed=False)
    assert r["ok"] is False and r["execution_document"] is None


# ── (10) Signer/broadcast unchanged & never enabled ─────────────────────────
def test_never_signs_or_broadcasts():
    r = build_execution_document(_dex_dex("arbitrum"), executor_deployed=True)
    assert r["signed"] is False and r["broadcast"] is False


def test_module_imports_no_signer_or_broadcaster():
    import arbicore.execution.multichain_opportunity_doc as m
    for banned in ("live_signer", "broadcast", "auto_executor", "sign_and_send"):
        assert not any(banned in n.lower() for n in dir(m)
                       if callable(getattr(m, n, None)))


# ── Base parity: same generator works for Base too (not reduced away) ────────
def test_base_also_supported_with_deployed_executor():
    r = build_execution_document(_dex_dex("base"), executor_deployed=True)
    assert r["ok"] is True and r["execution_document"]["chain"] == "base"


# ── Structural fail-closed cases ─────────────────────────────────────────────
def test_broken_cycle_fail_closed():
    c = _dex_dex("arbitrum")
    c["route"][1]["token_out"] = "USDC"          # no longer returns to WETH
    r = build_execution_document(c, executor_deployed=True)
    assert r["ok"] is False and "cycle" in r["reason"]


def test_zero_borrow_fail_closed():
    r = build_execution_document(_dex_dex("arbitrum", amount_wei=0), executor_deployed=True)
    assert r["ok"] is False and r["execution_document"] is None


# ── BNB: no Balancer V2 / Aave V3 flash head → flash-loan arb fail-closed ────
def test_bnb_has_no_flash_head_fail_closed():
    for prov in ("balancer_v2", "aave_v3"):
        r = build_execution_document(_dex_dex("bnb", provider=prov), executor_deployed=True)
        assert r["ok"] is False and r["execution_document"] is None
        assert r["verdict"] == "REJECTED"
        assert "flash_provider_chain_supported" in r["reason"]


# ── Base MAINNET first-production-target proof ───────────────────────────────
def test_base_mainnet_canonical_document_all_fields():
    doc = build_execution_document(_dex_dex("base"), executor_deployed=True)["execution_document"]
    for k in ("chain", "borrow_token", "borrow_amount_wei", "flash_loan_provider",
              "swap_hops", "dex_path", "token_path", "net_profit_usd",
              "opportunity_type", "executor_address", "strategy"):
        assert k in doc, k
    assert doc["chain"] == "base"
    assert doc["strategy"] == "flash_loan_arbitrage"
    assert doc["flash_loan_provider"] == "balancer_v2"
    assert doc["swap_hops"] and doc["dex_path"] == ["uniswap_v3", "uniswap_v3"]


def test_base_mainnet_requires_deployed_executor_not_config():
    from arbicore.execution import executor_registry
    # Base mainnet is NOT deployed in the registry → config/presence must NOT
    # be treated as execution readiness.
    assert executor_registry.is_deployed("base") is False
    r = build_execution_document(_dex_dex("base"))          # executor_deployed=None
    assert r["ok"] is False and r["execution_document"] is None
    assert r["verdict"] == "REJECTED"
    assert "executor_deployed" in r["reason"]
