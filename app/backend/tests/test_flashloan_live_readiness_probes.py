"""Deterministic tests for the additive, fail-closed live readiness probes
(arbicore.scanners.flash_loan_arbitrage.live_readiness_probes) and their
integration with the Limited-Live eligibility decision.

Covers every new path: missing RPC, missing executor, absent calldata, missing
signer, a passing simulation; Balancer liquidity confirmed/insufficient/unknown/
unresolved-token/no-rpc; freshness fresh/missing-ts/stale/missing-block/reorg/
lagged; and honest mode / kill-switch reporting including disabled mode and an
engaged kill switch. No network or DB — everything is injected.
"""
import pytest

from arbicore.scanners.flash_loan_arbitrage.live_readiness_probes import (
    probe_atomic_simulation, probe_balancer_liquidity, probe_freshness,
    probe_mode_and_kill_switch, FRESH_QUOTE_MAX_AGE_S,
)
from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
    ProviderStatus, BALANCER_V2_VAULT,
)

EXECUTOR = "0x000000000000000000000000000000000000E0EC"


# --------------------------------------------------------------------------
# Fakes (no network / no DB)
# --------------------------------------------------------------------------
class _FakeSim:
    def __init__(self, *, rpc_url, executor_address=None, executor_bytecode=None,
                 passed=True):
        self.rpc_url = rpc_url
        self.executor_address = executor_address
        self._passed = passed

    def readiness(self):
        return {"executor_address_set": bool(self.executor_address),
                "executor_bytecode_available": False, "rpc_configured": True}

    async def capability_self_test(self):
        return {"code_injection": True, "reason": None}

    async def simulate_atomic(self, *, entry_calldata, signer_present=False,
                              block_tag="latest", **_kw):
        if not signer_present:
            return {"available": False, "passed": False,
                    "reason": "execution signer not present in vault"}
        return {"available": True, "passed": self._passed, "stage": "atomic_call",
                "reason": None, "block_tag": block_tag,
                "signed": False, "broadcast": False}


class _FakeProvider:
    """Minimal EthJsonRpcProvider stand-in for read_balancer_liquidity."""

    def __init__(self, *, has_code=True, balance_wei=None):
        self._has_code = has_code
        self._balance = balance_wei
        self.closed = False

    async def _call(self, method, params):
        if method == "eth_getCode":
            return "0x60016000f3" if self._has_code else "0x"
        return None

    async def eth_call(self, tx, block="latest"):
        if self._balance is None:
            raise RuntimeError("balance read failed")
        return hex(self._balance)

    async def close(self):
        self.closed = True


class _FakeModeRepo:
    def __init__(self, db, mode="SHADOW"):
        self._mode = getattr(db, "mode", mode)

    async def get_mode(self):
        return self._mode


class _FakeKillRepo:
    class _State:
        def __init__(self, engaged):
            self.engaged = engaged

    def __init__(self, db, engaged=False):
        self._engaged = getattr(db, "kill_engaged", engaged)

    async def state(self):
        return self._State(self._engaged)


class _DB:
    def __init__(self, mode="SHADOW", kill_engaged=False):
        self.mode = mode
        self.kill_engaged = kill_engaged


def _bundle(**over):
    b = {
        "route": {"borrow_token": "WETH", "route_pools": ["p1", "p2"]},
        "quotes": {"route_quote_status": "ok", "gross_profit_pct": 0.9,
                   "verified_at_ts": 1000.0, "quote_block": 100},
        "economics": {"atomic_profit_usd": 50.0, "borrow_token_price_usd": 3000.0},
        "input_amount_usd": 10_000.0,
    }
    b.update(over)
    return b


# --------------------------------------------------------------------------
# 1) Atomic simulation
# --------------------------------------------------------------------------
async def test_atomic_sim_no_rpc_is_unknown():
    r = await probe_atomic_simulation(bundle=_bundle(), executor_address=EXECUTOR,
                                      rpc_url="", sim_factory=_FakeSim)
    assert r["available"] is False and r["passed"] is False
    assert r["status"] == "UNKNOWN" and "rpc" in r["reason"]
    assert r["signed"] is False and r["broadcast"] is False


async def test_atomic_sim_no_executor_denies():
    r = await probe_atomic_simulation(bundle=_bundle(), executor_address=None,
                                      rpc_url="http://rpc", sim_factory=_FakeSim)
    assert r["available"] is False and r["status"] == "DENY"
    assert "executor_address_absent" in r["reason"]


async def test_atomic_sim_absent_calldata_denies_but_runs_selftest():
    r = await probe_atomic_simulation(bundle=_bundle(), executor_address=EXECUTOR,
                                      rpc_url="http://rpc", sim_factory=_FakeSim)
    assert r["available"] is False and r["status"] == "DENY"
    assert "calldata_absent" in r["reason"]
    assert r["capability_self_test"]["code_injection"] is True


async def test_atomic_sim_missing_signer_denies():
    b = _bundle(execution_plan={"executor_entry_calldata": "0xdeadbeef"})
    r = await probe_atomic_simulation(bundle=b, executor_address=EXECUTOR,
                                      rpc_url="http://rpc", signer_present=False,
                                      sim_factory=_FakeSim)
    assert r["passed"] is False and "signer" in r["reason"]


async def test_atomic_sim_full_pass_when_signer_and_calldata_present():
    b = _bundle(execution_plan={"executor_entry_calldata": "0xdeadbeef"})
    r = await probe_atomic_simulation(bundle=b, executor_address=EXECUTOR,
                                      rpc_url="http://rpc", signer_present=True,
                                      sim_factory=_FakeSim)
    assert r["available"] is True and r["passed"] is True
    assert r["signed"] is False and r["broadcast"] is False


# --------------------------------------------------------------------------
# 2) Balancer liquidity
# --------------------------------------------------------------------------
async def test_balancer_no_rpc_returns_none():
    assert await probe_balancer_liquidity(bundle=_bundle(), rpc_url="") is None


async def test_balancer_unresolved_token_is_unknown():
    b = _bundle(route={"borrow_token": "NOTATOKEN", "route_pools": ["p1"]})
    r = await probe_balancer_liquidity(bundle=b, rpc_url="http://rpc")
    assert r is not None and r.status == ProviderStatus.UNKNOWN
    assert r.reason == "borrow_token_unresolved"


async def test_balancer_confirmed_when_liquidity_ge_borrow():
    # 100 WETH * $3000 = $300k ≥ $10k borrow ⇒ ON_CHAIN_CONFIRMED
    prov = _FakeProvider(has_code=True, balance_wei=100 * 10 ** 18)
    r = await probe_balancer_liquidity(bundle=_bundle(), rpc_url="http://rpc",
                                       provider_factory=lambda: prov)
    assert r.status == ProviderStatus.ON_CHAIN_CONFIRMED
    assert r.source_address == BALANCER_V2_VAULT
    assert prov.closed is True


async def test_balancer_unavailable_when_liquidity_below_borrow():
    # 1 WETH * $3000 = $3k < $10k borrow ⇒ UNAVAILABLE (never fabricated)
    prov = _FakeProvider(has_code=True, balance_wei=1 * 10 ** 18)
    r = await probe_balancer_liquidity(bundle=_bundle(), rpc_url="http://rpc",
                                       provider_factory=lambda: prov)
    assert r.status == ProviderStatus.UNAVAILABLE


async def test_balancer_unknown_when_balance_read_fails():
    prov = _FakeProvider(has_code=True, balance_wei=None)  # eth_call raises
    r = await probe_balancer_liquidity(bundle=_bundle(), rpc_url="http://rpc",
                                       provider_factory=lambda: prov)
    assert r.status == ProviderStatus.UNKNOWN


async def test_balancer_unknown_when_price_missing():
    b = _bundle(economics={"atomic_profit_usd": 50.0})  # no borrow_token_price_usd
    prov = _FakeProvider(has_code=True, balance_wei=100 * 10 ** 18)
    r = await probe_balancer_liquidity(bundle=b, rpc_url="http://rpc",
                                       provider_factory=lambda: prov)
    assert r.status == ProviderStatus.UNKNOWN  # token_price_unavailable


# --------------------------------------------------------------------------
# 3) Freshness
# --------------------------------------------------------------------------
def test_freshness_fresh():
    r = probe_freshness(bundle=_bundle(), current_block=102, now_ts=1005.0)
    assert r["ok"] is True and r["block_lag"] == 2 and r["quote_age_s"] == 5.0


def test_freshness_missing_timestamp_denies():
    b = _bundle(quotes={"route_quote_status": "ok", "quote_block": 100})
    r = probe_freshness(bundle=b, current_block=100, now_ts=1000.0)
    assert r["ok"] is False and r["reason"] == "quote_timestamp_missing"


def test_freshness_stale_quote_age_denies():
    r = probe_freshness(bundle=_bundle(), current_block=101,
                        now_ts=1000.0 + FRESH_QUOTE_MAX_AGE_S + 1)
    assert r["ok"] is False and r["reason"].startswith("quote_stale")


def test_freshness_missing_current_block_denies():
    r = probe_freshness(bundle=_bundle(), current_block=None, now_ts=1005.0)
    assert r["ok"] is False and r["reason"] == "current_block_unavailable"


def test_freshness_reorg_denies():
    r = probe_freshness(bundle=_bundle(), current_block=99, now_ts=1005.0)
    assert r["ok"] is False and r["reason"].startswith("reorg")


def test_freshness_block_lag_denies():
    r = probe_freshness(bundle=_bundle(), current_block=200, now_ts=1005.0)
    assert r["ok"] is False and r["reason"].startswith("block_stale")


# --------------------------------------------------------------------------
# 4) Mode + kill switch
# --------------------------------------------------------------------------
async def test_mode_kill_db_unavailable_denies():
    r = await probe_mode_and_kill_switch(db=None)
    assert r["mode_allows"] is False and r["kill_switch_ok"] is False
    assert r["reason"] == "db_unavailable"


async def test_mode_shadow_denies_but_kill_ok():
    r = await probe_mode_and_kill_switch(
        db=_DB(mode="SHADOW", kill_engaged=False),
        mode_repo_factory=_FakeModeRepo, kill_repo_factory=_FakeKillRepo)
    assert r["mode"] == "SHADOW" and r["mode_allows"] is False
    assert r["kill_switch_engaged"] is False and r["kill_switch_ok"] is True


async def test_mode_limited_live_allows():
    r = await probe_mode_and_kill_switch(
        db=_DB(mode="LIMITED_LIVE"),
        mode_repo_factory=_FakeModeRepo, kill_repo_factory=_FakeKillRepo)
    assert r["mode_allows"] is True


async def test_kill_switch_engaged_denies():
    r = await probe_mode_and_kill_switch(
        db=_DB(mode="LIMITED_LIVE", kill_engaged=True),
        mode_repo_factory=_FakeModeRepo, kill_repo_factory=_FakeKillRepo)
    assert r["kill_switch_engaged"] is True and r["kill_switch_ok"] is False


# --------------------------------------------------------------------------
# Integration: probes → eligibility decision (fail-closed + honest pass)
# --------------------------------------------------------------------------
def _confirmed_bundle():
    b = _bundle()
    b.update({
        "source_component": "flash_loan_arb_verifier",
        "verification_status": "CONFIRMED",
        "gates": {"gate_7": {"status": "PASS"}, "gate_8": {"status": "PASS"},
                  "gate_9": {"status": "PASS"}},
        "diagnostics": {"audit_run_id": "run1", "scanner_tick_id": 1,
                        "candidate_id": "cand1"},
    })
    return b


def _controls(*, mode_allows, kill_ok, atomic_passed=True, bal_confirmed=True,
              fresh=True):
    from arbicore.scanners.flash_loan_arbitrage.readiness_assessment import (
        ReadinessControls,
    )
    from arbicore.scanners.flash_loan_arbitrage.executor_capability import (
        ExecutorCapability, ExecutorCapabilityStatus,
    )
    from arbicore.scanners.flash_loan_arbitrage.provider_liquidity import (
        ProviderLiquidity,
    )
    from arbicore.scanners.flash_loan_arbitrage.borrow_sizing import (
        BorrowSizeEval, select_borrow_size,
    )
    cap = ExecutorCapability(status=ExecutorCapabilityStatus.SUPPORTED,
                             supported_pools=["p1", "p2"], unsupported_pools=[],
                             unverifiable_pools=[], executor_address=EXECUTOR,
                             reason="ok")
    bal = ProviderLiquidity(
        provider="balancer_v2", chain="base",
        status=(ProviderStatus.ON_CHAIN_CONFIRMED if bal_confirmed
                else ProviderStatus.UNAVAILABLE),
        liquidity_usd=300_000.0)
    size = select_borrow_size([BorrowSizeEval(
        size_usd=10_000.0, net_profit_usd=50.0, gross_spread_pct=0.9,
        quote_complete=True, economics_ok=True,
        liquidity_sufficient=bal_confirmed, executor_supported=True,
        atomic_sim_passed=atomic_passed)])
    return ReadinessControls(
        executor_capability=cap, balancer_liquidity=bal, borrow_size=size,
        atomic_sim={"available": True, "passed": atomic_passed},
        freshness_ok=fresh, mode_allows=mode_allows, kill_switch_ok=kill_ok)


def test_integration_all_pass_and_limited_live_enabled_is_eligible():
    from arbicore.scanners.flash_loan_arbitrage.readiness_assessment import (
        assess_candidate_readiness,
    )
    rec = assess_candidate_readiness(
        _confirmed_bundle(), _controls(mode_allows=True, kill_ok=True))
    assert rec["limited_live"]["eligible"] is True
    assert rec["signed"] is False and rec["broadcast"] is False


def test_integration_disabled_mode_denies_even_if_everything_else_passes():
    from arbicore.scanners.flash_loan_arbitrage.readiness_assessment import (
        assess_candidate_readiness,
    )
    rec = assess_candidate_readiness(
        _confirmed_bundle(), _controls(mode_allows=False, kill_ok=True))
    assert rec["limited_live"]["eligible"] is False
    assert any("mode_allows" in d for d in rec["limited_live"]["deny_reasons"])


def test_integration_engaged_kill_switch_denies():
    from arbicore.scanners.flash_loan_arbitrage.readiness_assessment import (
        assess_candidate_readiness,
    )
    rec = assess_candidate_readiness(
        _confirmed_bundle(), _controls(mode_allows=True, kill_ok=False))
    assert rec["limited_live"]["eligible"] is False
    assert any("kill_switch_ok" in d for d in rec["limited_live"]["deny_reasons"])


def test_integration_stale_freshness_denies():
    from arbicore.scanners.flash_loan_arbitrage.readiness_assessment import (
        assess_candidate_readiness,
    )
    rec = assess_candidate_readiness(
        _confirmed_bundle(),
        _controls(mode_allows=True, kill_ok=True, fresh=False))
    assert rec["limited_live"]["eligible"] is False
    assert any("freshness_ok" in d for d in rec["limited_live"]["deny_reasons"])
