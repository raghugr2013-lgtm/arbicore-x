import pytest

from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
    MORPHO_BLUE_CHAINS,
    SEL_BALANCE_OF,
    SEL_GET_RESERVE_DATA,
    runtime_flashloan_available,
    runtime_flash_liquidity_tokens,
)


TOKEN = "0x0000000000000000000000000000000000000011"
MORPHO = "0x0000000000000000000000000000000000000022"


def _balance_hex(tokens: float, decimals: int = 6) -> str:
    return "0x" + int(tokens * (10 ** decimals)).to_bytes(32, "big").hex()


class FakeRpc:
    def __init__(
        self,
        *,
        code="0x6001600055",
        balance="0x",
        code_error=False,
        balance_error=False,
    ):
        self.code = code
        self.balance = balance
        self.code_error = code_error
        self.balance_error = balance_error
        self.calls = []

    async def get_code(self, address):
        self.calls.append(("eth_getCode", address))
        if self.code_error:
            raise RuntimeError("rpc code failure")
        return self.code

    async def eth_call(self, to, data):
        self.calls.append((to, data))

        if data.startswith(SEL_GET_RESERVE_DATA):
            raise AssertionError("Morpho path must NEVER call Aave getReserveData")

        if data.startswith(SEL_BALANCE_OF):
            if self.balance_error:
                raise RuntimeError("rpc balance failure")
            return self.balance

        raise AssertionError(f"unexpected eth_call: {to} {data}")


def _available_kwargs(fake):
    return dict(
        eth_call=fake.eth_call,
        provider="morpho_blue",
        chain="base",
        token_address=TOKEN,
        token_decimals=6,
        token_price_usd=1.0,
        borrow_amount_usd=10_000.0,
        eth_get_code=fake.get_code,
    )


@pytest.mark.asyncio
async def test_morpho_sufficient_liquidity_is_true(monkeypatch):
    monkeypatch.setattr(
        "arbicore.scanners.flash_loan_arbitrage.provider_liquidity._morpho_singleton",
        lambda chain: MORPHO,
    )

    fake = FakeRpc(balance=_balance_hex(20_000))

    result = await runtime_flashloan_available(
        **_available_kwargs(fake)
    )

    assert result is True
    assert ("eth_getCode", MORPHO) in fake.calls
    assert any(
        call[0] == TOKEN and call[1].startswith(SEL_BALANCE_OF)
        for call in fake.calls
    )
    assert not any(
        call[1].startswith(SEL_GET_RESERVE_DATA)
        for call in fake.calls
        if len(call) == 2 and isinstance(call[1], str)
    )


@pytest.mark.asyncio
async def test_morpho_insufficient_liquidity_is_false(monkeypatch):
    monkeypatch.setattr(
        "arbicore.scanners.flash_loan_arbitrage.provider_liquidity._morpho_singleton",
        lambda chain: MORPHO,
    )

    fake = FakeRpc(balance=_balance_hex(5_000))

    result = await runtime_flashloan_available(
        **_available_kwargs(fake)
    )

    assert result is False


@pytest.mark.asyncio
async def test_morpho_missing_bytecode_is_false(monkeypatch):
    monkeypatch.setattr(
        "arbicore.scanners.flash_loan_arbitrage.provider_liquidity._morpho_singleton",
        lambda chain: MORPHO,
    )

    fake = FakeRpc(code="0x")

    result = await runtime_flashloan_available(
        **_available_kwargs(fake)
    )

    assert result is False
    assert fake.calls == [("eth_getCode", MORPHO)]


@pytest.mark.asyncio
async def test_morpho_code_rpc_failure_is_unknown(monkeypatch):
    monkeypatch.setattr(
        "arbicore.scanners.flash_loan_arbitrage.provider_liquidity._morpho_singleton",
        lambda chain: MORPHO,
    )

    fake = FakeRpc(code_error=True)

    result = await runtime_flashloan_available(
        **_available_kwargs(fake)
    )

    assert result is None


@pytest.mark.asyncio
async def test_morpho_balance_rpc_failure_is_unknown(monkeypatch):
    monkeypatch.setattr(
        "arbicore.scanners.flash_loan_arbitrage.provider_liquidity._morpho_singleton",
        lambda chain: MORPHO,
    )

    fake = FakeRpc(
        balance_error=True,
    )

    result = await runtime_flashloan_available(
        **_available_kwargs(fake)
    )

    assert result is None


@pytest.mark.asyncio
async def test_morpho_malformed_code_is_unknown(monkeypatch):
    monkeypatch.setattr(
        "arbicore.scanners.flash_loan_arbitrage.provider_liquidity._morpho_singleton",
        lambda chain: MORPHO,
    )

    fake = FakeRpc(code="not-hex")

    result = await runtime_flashloan_available(
        **_available_kwargs(fake)
    )

    assert result is None


@pytest.mark.asyncio
async def test_morpho_unsupported_chain_is_false_without_rpc(monkeypatch):
    monkeypatch.setattr(
        "arbicore.scanners.flash_loan_arbitrage.provider_liquidity._morpho_singleton",
        lambda chain: MORPHO,
    )

    fake = FakeRpc(balance=_balance_hex(20_000))

    result = await runtime_flashloan_available(
        **dict(
            _available_kwargs(fake),
            chain="arbitrum",
        )
    )

    assert "arbitrum" not in MORPHO_BLUE_CHAINS
    assert result is False
    assert fake.calls == []


@pytest.mark.asyncio
async def test_morpho_runtime_liquidity_tokens_uses_real_holder(monkeypatch):
    monkeypatch.setattr(
        "arbicore.scanners.flash_loan_arbitrage.provider_liquidity._morpho_singleton",
        lambda chain: MORPHO,
    )

    fake = FakeRpc(balance=_balance_hex(12_345))

    tokens = await runtime_flash_liquidity_tokens(
        fake.eth_call,
        provider="morpho_blue",
        chain="base",
        token_address=TOKEN,
        token_decimals=6,
    )

    assert tokens == pytest.approx(12_345)


@pytest.mark.asyncio
async def test_morpho_without_code_seam_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "arbicore.scanners.flash_loan_arbitrage.provider_liquidity._morpho_singleton",
        lambda chain: MORPHO,
    )

    fake = FakeRpc(balance=_balance_hex(20_000))

    result = await runtime_flashloan_available(
        fake.eth_call,
        provider="morpho_blue",
        chain="base",
        token_address=TOKEN,
        token_decimals=6,
        token_price_usd=1.0,
        borrow_amount_usd=10_000.0,
    )

    assert result is None
    assert fake.calls == []
