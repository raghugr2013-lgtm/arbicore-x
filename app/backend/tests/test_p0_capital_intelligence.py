"""P0 — Wallet & Capital Intelligence engine (read-only, reconciliation)."""
import asyncio
import types

from arbicore.capital.wallet_intelligence import WalletIntelligenceEngine


def _run(c):
    return asyncio.get_event_loop().run_until_complete(c)


class _FakeReading:
    def __init__(self, eth):
        self._eth = eth

    def to_dict(self):
        wei = int(self._eth * 1e18)
        return {"symbol": "ETH", "balance_native": self._eth, "balance_wei": wei,
                "balance_usd": round(self._eth * 2500, 4), "block_number": 123,
                "rpc_endpoint_redacted": "https://mainnet.base.org", "ok": True}


class _FakeBalanceReader:
    def __init__(self, eth):
        self._eth = eth

    async def read(self, *, chain, address):
        return _FakeReading(self._eth)


def _engine(eth_balance=1.0):
    eng = WalletIntelligenceEngine(rpc_url="", balance_reader=_FakeBalanceReader(eth_balance),
                                   eth_price_provider=None)
    # deterministic price
    async def _price():
        return 2500.0
    eng._eth_price_usd = _price  # type: ignore
    # no on-chain ERC-20 (rpc_url empty → _erc20_balance returns 0)
    return eng


WALLET = "0x998d6efF2b28b72c44f7a334c42678eb4cCaad25".lower()


def test_live_balances_native_only():
    eng = _engine(0.5)
    out = _run(eng.live_balances(WALLET))
    assert out["ok"] is True
    assert out["native"]["balance"] == 0.5
    assert out["native"]["value_usd"] == 1250.0
    assert out["tokens"] == []  # no rpc → no erc20
    assert out["total_value_usd"] == 1250.0


def test_reconciliation_identity_holds_with_known_flows():
    """start + inflows − outflows − fees = end (native ETH identity)."""
    eng = _engine(1.0)  # live end balance = 1.0 ETH

    async def _fake_stmt(address, **kw):
        # one inflow (+2 ETH), one outflow (−0.9 ETH) with 0.1 ETH fee
        return {
            "transactions": [
                {"direction": "in", "native_amount": 2.0, "fee_eth": 0.0},
                {"direction": "out", "native_amount": 0.9, "fee_eth": 0.1},
            ],
            "count": 2, "source_ok": True, "source_reason": None,
            "eth_price_usd": 2500.0,
        }
    eng.transaction_statement = _fake_stmt  # type: ignore

    rec = _run(eng.capital_reconciliation(WALLET))
    # start = end - in + out + fees = 1.0 - 2.0 + 0.9 + 0.1 = 0.0
    assert abs(rec["start_balance"] - 0.0) < 1e-9
    assert rec["inflows"] == 2.0
    assert rec["outflows"] == 0.9
    assert abs(rec["fees"] - 0.1) < 1e-9
    assert rec["end_balance"] == 1.0
    assert abs(rec["residual"]) < 1e-9
    assert rec["reconciled"] is True
    assert rec["statement_complete"] is True


def test_reconciliation_flags_incomplete_statement():
    eng = _engine(0.004)

    async def _fake_stmt(address, **kw):
        return {"transactions": [], "count": 0, "source_ok": False,
                "source_reason": "explorer API key not configured",
                "eth_price_usd": 2500.0}
    eng.transaction_statement = _fake_stmt  # type: ignore

    rec = _run(eng.capital_reconciliation(WALLET))
    assert rec["reconciled"] is True  # trivially (no known flows)
    assert rec["statement_complete"] is False
    assert "explorer" in (rec["statement_note"] or "").lower()


def test_classify_tx_dex_and_flash():
    eng = _engine()
    dex = eng._classify_tx({"to": "0x2626664c2603336E57B271c5C0b26F421741e481", "input": "0x414bf389"})
    assert dex["tx_type"] == "dex_swap" and dex["venue"] == "uniswap_v3"
    flash = eng._classify_tx({"to": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5", "input": "0xab9c4b5d"})
    assert flash["tx_type"] == "flash_loan" and flash["flash_provider"] == "aave_v3_pool"
    native = eng._classify_tx({"to": "0xabc", "input": "0x"})
    assert native["tx_type"] == "native_transfer"


def test_money_trail_net_by_token():
    eng = _engine()

    async def _fake_es(module, action, address, extra=None):
        # a flash-loan arb: borrow 10 WETH in, repay 9.99 WETH out, keep proceeds
        return {"ok": True, "result": [
            {"hash": "0xAA", "tokenSymbol": "WETH", "tokenDecimal": "18",
             "value": str(10 * 10**18), "from": "0xpool", "to": WALLET,
             "contractAddress": "0x4200000000000000000000000000000000000006"},
            {"hash": "0xAA", "tokenSymbol": "WETH", "tokenDecimal": "18",
             "value": str(int(9.99 * 10**18)), "from": WALLET, "to": "0xpool",
             "contractAddress": "0x4200000000000000000000000000000000000006"},
        ]}
    eng._es = _fake_es  # type: ignore

    async def _price():
        return 2500.0
    eng._eth_price_usd = _price  # type: ignore

    out = _run(eng.money_trail(WALLET, "0xAA"))
    assert out["ok"] is True
    assert out["leg_count"] == 2
    # net WETH = +10 - 9.99 = +0.01
    assert abs(out["net_by_token"]["WETH"] - 0.01) < 1e-6
    assert out["realized_pl_usd"] is not None
