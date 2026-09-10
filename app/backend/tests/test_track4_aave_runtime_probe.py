"""Track 4 + Track 2 + Track 8 — runtime flash-loan provider capability.

Deterministic, offline (fake ``eth_call``) proofs that the chain-generic runtime
flash-loan liquidity probe:
  * genuinely reads Aave V3 liquidity (getReserveData → aToken.balanceOf),
  * fails closed on any read failure / unpriceable token,
  * refuses providers with no runtime reader (e.g. morpho_blue) — registry
    presence is NEVER runtime capability,
  * is chain-generic without Base-RPC leakage (an aave read on a non-Base chain
    hits that chain's Pool address, never Base's),
  * and that readiness reflects ACTUAL capability (no static "executable" claim;
    execution stays UNPROVEN until a deployed receiver supports a flash head).
"""
from __future__ import annotations

import pytest

from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
    AAVE_V3_POOL, BALANCER_V2_VAULT, RUNTIME_PROBE_PROVIDERS,
    SEL_BALANCE_OF, SEL_GET_RESERVE_DATA,
    runtime_flashloan_available,
)

# A syntactically-valid Base token + aToken (checksum irrelevant to decoding).
TOKEN = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"   # USDC (Base)
ATOKEN = "0x4e65fE4DbA92790696d040ac24Aa414708F5c0AB"


def _word(addr: str) -> str:
    return addr.lower().replace("0x", "").rjust(64, "0")


def _reserve_data_with_atoken(atoken: str) -> str:
    """9th 32-byte word (index 8) is aTokenAddress; pad the rest with zeros."""
    words = ["0" * 64] * 8 + [_word(atoken)] + ["0" * 64] * 6
    return "0x" + "".join(words)


def _balance_hex(tokens: float, decimals: int) -> str:
    return hex(int(tokens * (10 ** decimals)))


class _FakeEthCall:
    """Records every (to, data) and returns scripted responses per selector."""

    def __init__(self, *, reserve_atoken=None, balance_by_holder=None,
                 raise_on=None):
        self.calls = []
        self._reserve_atoken = reserve_atoken
        self._balance_by_holder = balance_by_holder or {}
        self._raise_on = raise_on or set()

    async def __call__(self, to, data):
        self.calls.append((to.lower(), data))
        sel = data[:10]
        if sel in self._raise_on:
            raise RuntimeError("rpc_failure")
        if sel == SEL_GET_RESERVE_DATA:
            if self._reserve_atoken is None:
                return "0x"  # reserve not listed → decode returns None
            return _reserve_data_with_atoken(self._reserve_atoken)
        if sel == SEL_BALANCE_OF:
            holder = "0x" + data[10:][-40:]
            return self._balance_by_holder.get(holder.lower())
        raise AssertionError(f"unexpected selector {sel}")


# ---------------------------------------------------------------------------
# Aave V3 — genuine liquidity read
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_aave_v3_confirmed_when_liquidity_ge_borrow():
    fake = _FakeEthCall(
        reserve_atoken=ATOKEN,
        balance_by_holder={ATOKEN.lower(): _balance_hex(50_000, 6)})
    avail = await runtime_flashloan_available(
        fake, provider="aave_v3", chain="base",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is True
    # Proof it read the real Aave Pool + the resolved aToken (not the vault).
    assert any(c[0] == AAVE_V3_POOL["base"].lower()
               and c[1].startswith(SEL_GET_RESERVE_DATA) for c in fake.calls)
    assert any(c[1].startswith(SEL_BALANCE_OF)
               and ATOKEN.lower()[2:] in c[1] for c in fake.calls)


@pytest.mark.asyncio
async def test_aave_v3_unavailable_when_liquidity_below_borrow():
    fake = _FakeEthCall(
        reserve_atoken=ATOKEN,
        balance_by_holder={ATOKEN.lower(): _balance_hex(500, 6)})
    avail = await runtime_flashloan_available(
        fake, provider="aave_v3", chain="base",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is False   # definitive: confirmed liquidity < borrow


# ---------------------------------------------------------------------------
# Aave V3 — fail-closed on read failure / unlisted reserve / unpriceable
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_aave_v3_reserve_read_failure_is_none():
    fake = _FakeEthCall(reserve_atoken=ATOKEN, raise_on={SEL_GET_RESERVE_DATA})
    avail = await runtime_flashloan_available(
        fake, provider="aave_v3", chain="base",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is None   # UNKNOWN ⇒ DENY


@pytest.mark.asyncio
async def test_aave_v3_balance_read_failure_is_none():
    fake = _FakeEthCall(reserve_atoken=ATOKEN, raise_on={SEL_BALANCE_OF})
    avail = await runtime_flashloan_available(
        fake, provider="aave_v3", chain="base",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is None


@pytest.mark.asyncio
async def test_aave_v3_reserve_not_listed_is_false():
    fake = _FakeEthCall(reserve_atoken=None)   # getReserveData → "0x"
    avail = await runtime_flashloan_available(
        fake, provider="aave_v3", chain="base",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is False   # definitive: token not an Aave reserve here


@pytest.mark.asyncio
async def test_unpriceable_token_is_none():
    fake = _FakeEthCall(reserve_atoken=ATOKEN,
                        balance_by_holder={ATOKEN.lower(): _balance_hex(9e9, 6)})
    for px in (None, 0.0, -1.0):
        avail = await runtime_flashloan_available(
            fake, provider="aave_v3", chain="base",
            token_address=TOKEN, token_decimals=6,
            token_price_usd=px, borrow_amount_usd=10_000.0)
        assert avail is None


# ---------------------------------------------------------------------------
# Unsupported / no-runtime-reader providers fail closed (Morpho evidence-first)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_morpho_blue_has_no_runtime_reader_fails_closed():
    assert "morpho_blue" not in RUNTIME_PROBE_PROVIDERS
    fake = _FakeEthCall()
    avail = await runtime_flashloan_available(
        fake, provider="morpho_blue", chain="base",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is False
    assert fake.calls == []   # NEVER issues a read for an unverifiable provider


@pytest.mark.asyncio
async def test_unknown_provider_fails_closed():
    fake = _FakeEthCall()
    avail = await runtime_flashloan_available(
        fake, provider="curve", chain="base",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is False
    assert fake.calls == []


# ---------------------------------------------------------------------------
# Track 2 — chain-generic, no Base-RPC leakage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_aave_v3_non_base_hits_that_chains_pool_not_base():
    """An Arbitrum aave probe must query the Arbitrum Pool, never Base's."""
    fake = _FakeEthCall(
        reserve_atoken=ATOKEN,
        balance_by_holder={ATOKEN.lower(): _balance_hex(50_000, 6)})
    avail = await runtime_flashloan_available(
        fake, provider="aave_v3", chain="arbitrum",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is True
    pool_targets = {c[0] for c in fake.calls if c[1].startswith(SEL_GET_RESERVE_DATA)}
    assert AAVE_V3_POOL["arbitrum"].lower() in pool_targets
    assert AAVE_V3_POOL["base"].lower() not in pool_targets


@pytest.mark.asyncio
async def test_aave_v3_unsupported_chain_is_false():
    fake = _FakeEthCall()
    avail = await runtime_flashloan_available(
        fake, provider="aave_v3", chain="solana",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is False
    assert fake.calls == []   # no aave pool for chain ⇒ no read


@pytest.mark.asyncio
async def test_balancer_v2_not_on_bnb_is_false():
    fake = _FakeEthCall()
    avail = await runtime_flashloan_available(
        fake, provider="balancer_v2", chain="bnb",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is False
    assert fake.calls == []


@pytest.mark.asyncio
async def test_balancer_v2_reads_vault_holder():
    fake = _FakeEthCall(
        balance_by_holder={BALANCER_V2_VAULT.lower(): _balance_hex(1_000_000, 6)})
    avail = await runtime_flashloan_available(
        fake, provider="balancer_v2", chain="base",
        token_address=TOKEN, token_decimals=6,
        token_price_usd=1.0, borrow_amount_usd=10_000.0)
    assert avail is True
    assert any(c[1].startswith(SEL_BALANCE_OF)
               and BALANCER_V2_VAULT.lower()[2:] in c[1] for c in fake.calls)


# ---------------------------------------------------------------------------
# Token-unit liquidity read (RUNTIME-PROVEN reserve; no USD price needed)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flash_liquidity_tokens_aave_reads_real_balance():
    from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
        runtime_flash_liquidity_tokens)
    fake = _FakeEthCall(
        reserve_atoken=ATOKEN,
        balance_by_holder={ATOKEN.lower(): _balance_hex(12_345, 6)})
    tokens = await runtime_flash_liquidity_tokens(
        fake, provider="aave_v3", chain="arbitrum",
        token_address=TOKEN, token_decimals=6)
    assert tokens == 12_345.0
    assert AAVE_V3_POOL["arbitrum"].lower() in {c[0] for c in fake.calls}


@pytest.mark.asyncio
async def test_flash_liquidity_tokens_balancer_reads_vault():
    from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
        runtime_flash_liquidity_tokens)
    fake = _FakeEthCall(
        balance_by_holder={BALANCER_V2_VAULT.lower(): _balance_hex(777, 6)})
    tokens = await runtime_flash_liquidity_tokens(
        fake, provider="balancer_v2", chain="arbitrum",
        token_address=TOKEN, token_decimals=6)
    assert tokens == 777.0


@pytest.mark.asyncio
async def test_flash_liquidity_tokens_fail_closed_on_read_error():
    from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
        runtime_flash_liquidity_tokens)
    fake = _FakeEthCall(reserve_atoken=ATOKEN, raise_on={SEL_BALANCE_OF})
    tokens = await runtime_flash_liquidity_tokens(
        fake, provider="aave_v3", chain="arbitrum",
        token_address=TOKEN, token_decimals=6)
    assert tokens is None


@pytest.mark.asyncio
async def test_flash_liquidity_tokens_unsupported_provider_is_none():
    from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
        runtime_flash_liquidity_tokens)
    fake = _FakeEthCall()
    tokens = await runtime_flash_liquidity_tokens(
        fake, provider="morpho_blue", chain="arbitrum",
        token_address=TOKEN, token_decimals=6)
    assert tokens is None
    assert fake.calls == []
