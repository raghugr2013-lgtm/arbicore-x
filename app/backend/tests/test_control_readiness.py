"""Phase B/C/F — Control Center readiness engine + anti-bypass regression.

Verifies the backend-authoritative ExecutionReadinessEngine and mode
transition guard, and that the Control Center can NEVER enable
LIMITED_LIVE / FULL_AUTOMATION or bypass Phase-0 safety gates.
"""
import asyncio

from arbicore.control import (
    ExecutionReadinessEngine, OPERATOR_MODES, RED, YELLOW, GREEN,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakeKS:
    def __init__(self, engaged=False):
        self._engaged = engaged

    async def state(self):
        class _S:  # noqa: D401
            pass
        s = _S()
        s.engaged = self._engaged
        return s


class _FakeWallets:
    def __init__(self, gas=0):
        self._gas = gas

    async def list_all(self, chain=None, execution_role=None):
        if execution_role == "gas":
            return [{"address": "0x0", "execution_role": "gas"}] * self._gas
        return []


def _engine(**kw):
    return ExecutionReadinessEngine(
        db=None, kill_switch=kw.get("ks", _FakeKS()),
        wallet_registry=kw.get("wallets", _FakeWallets(0)),
    )


def test_operator_modes_shape():
    assert OPERATOR_MODES == (
        "SHADOW", "PAPER", "PROFIT_ENGINE", "LIMITED_LIVE", "FULL_AUTOMATION")


def test_evaluate_returns_all_components_and_modes():
    rep = _run(_engine().evaluate())
    assert rep["overall_status"] in (RED, YELLOW, GREEN)
    names = {c["name"] for c in rep["components"]}
    for req in ("SYSTEM", "CONFIGURATION", "SECURITY", "WALLET_SIGNER",
                "SIMULATION", "CONTRACTS", "SHADOW_VALIDATION", "PAPER_VALIDATION"):
        assert req in names
    assert set(rep["modes"].keys()) == set(OPERATOR_MODES)


def test_limited_live_always_red_and_not_activatable():
    rep = _run(_engine().evaluate())
    ll = rep["modes"]["LIMITED_LIVE"]
    assert ll["status"] == RED
    assert ll["can_activate"] is False
    assert ll["blockers"]


def test_full_automation_always_red():
    rep = _run(_engine().evaluate())
    fa = rep["modes"]["FULL_AUTOMATION"]
    assert fa["status"] == RED
    assert fa["can_activate"] is False


def test_transition_to_limited_live_refused():
    d = _run(_engine().can_transition("LIMITED_LIVE"))
    assert d["allowed"] is False
    d2 = _run(_engine().can_transition("FULL_AUTOMATION"))
    assert d2["allowed"] is False


def test_transition_to_shadow_allowed():
    d = _run(_engine().can_transition("SHADOW"))
    assert d["allowed"] is True


def test_unknown_mode_refused():
    d = _run(_engine().can_transition("YOLO_LIVE"))
    assert d["allowed"] is False


def test_security_reflects_engaged_kill_switch():
    rep = _run(_engine(ks=_FakeKS(engaged=True)).evaluate())
    sec = next(c for c in rep["components"] if c["name"] == "SECURITY")
    assert sec["status"] == YELLOW
    assert any("ENGAGED" in w for w in sec["warnings"])


class _FakeSecretsColl:
    def __init__(self, signer_addr=None):
        self._addr = signer_addr

    async def find_one(self, query, projection=None):
        if query.get("scope") == "evm_sign" and self._addr is not None:
            return {"derived_address": self._addr}
        return None


class _FakeDB:
    def __init__(self, signer_addr=None):
        self._coll = _FakeSecretsColl(signer_addr)

    def __getitem__(self, name):
        return self._coll

    async def command(self, *a, **k):
        return {"ok": 1}


def test_wallet_signer_yellow_with_gas_only_no_signer():
    # Gas wallet present but NO signer in vault → YELLOW, requirement names signer.
    eng = ExecutionReadinessEngine(db=_FakeDB(signer_addr=None),
                                   kill_switch=_FakeKS(),
                                   wallet_registry=_FakeWallets(gas=1))
    rep = _run(eng.evaluate())
    w = next(c for c in rep["components"] if c["name"] == "WALLET_SIGNER")
    assert w["status"] == YELLOW
    assert any("signer" in r.lower() for r in w["requirements"])
    assert any("gas" in p.lower() for p in w["passed"])


def test_wallet_signer_green_when_gas_and_signer_present():
    # Gas wallet + matching signer in vault → GREEN.
    eng = ExecutionReadinessEngine(
        db=_FakeDB(signer_addr="0x00000000000000000000000000000000000000aa"),
        kill_switch=_FakeKS(), wallet_registry=_FakeWallets(gas=1))
    rep = _run(eng.evaluate())
    w = next(c for c in rep["components"] if c["name"] == "WALLET_SIGNER")
    assert w["status"] == GREEN
