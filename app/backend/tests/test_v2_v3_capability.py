"""Hermetic tests for V-2 (Algebra venue wiring) and V-3 (version-aware executor
capability). No arbicore package boot, no Mongo/RPC — modules are loaded by file
path against the real snapshot source.
"""
import importlib.util
import os
import sys
import types

_SRC = os.environ.get("ACX_SRC")
if not _SRC:
    _SRC = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "arbicore")
    )


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---- load pure deps by path -------------------------------------------------
route_search = _load(os.path.join(_SRC, "scanners/flash_loan_arbitrage/route_search.py"),
                     "rs_mod")
registries = _load(os.path.join(_SRC, "chains/registries.py"), "reg_mod")
execap = _load(os.path.join(_SRC, "scanners/flash_loan_arbitrage/executor_capability.py"),
              "execap_mod")

# ---- build_pool_graph: exec source with injected deps (strip relative imports)
with open(os.path.join(_SRC, "discovery/multichain_venues.py")) as fh:
    _mc_src = fh.read()
_mc_src = _mc_src.replace(
    "from ..scanners.flash_loan_arbitrage.route_search import PoolNode", "")
_mc_src = _mc_src.replace("from ..chains import registries", "")
_mc_ns = {"PoolNode": route_search.PoolNode, "registries": registries}
exec(compile(_mc_src, "multichain_venues.py", "exec"), _mc_ns)
build_pool_graph = _mc_ns["build_pool_graph"]


# ============================ V-2 ============================================

def test_v2_algebra_routable_on_arbitrum():
    """Camelot V3 (algebra) must now appear in Arbitrum's route probe graph."""
    pools = build_pool_graph("arbitrum")
    dexes = {p.dex_protocol for p in pools}
    assert "uniswap_v3" in dexes                 # unchanged
    assert "camelot_v3" in dexes                 # V-2 NEW (algebra)
    # algebra pools carry the single-pool-per-pair 'algebra' param, fee placeholder 0
    algebra = [p for p in pools if p.dex_protocol == "camelot_v3"]
    assert algebra and all(p.fee_bps == 0 for p in algebra)


def test_v2_algebra_routable_on_polygon():
    pools = build_pool_graph("polygon")
    assert "quickswap_v3" in {p.dex_protocol for p in pools}   # V-2 NEW


def test_v2_curve_and_solidly_still_excluded():
    """Curve (ethereum) & Velodrome/solidly (optimism) have no live quoter yet →
    must NOT be fabricated into the probe graph (honest CODE remainder)."""
    eth = {p.dex_protocol for p in build_pool_graph("ethereum")}
    op = {p.dex_protocol for p in build_pool_graph("optimism")}
    assert "curve_stable" not in eth
    assert "velodrome_v2" not in op
    assert "uniswap_v3" in eth and "uniswap_v3" in op          # unchanged baseline


def test_v2_base_unaffected():
    # Base keeps its own dedicated registry path; multichain graph is empty.
    assert build_pool_graph("base") == []


# ============================ V-3 ============================================

def test_v3_v1_profile_is_unchanged_univ3_only():
    assert execap.SUPPORTED_DEXES == frozenset({"uniswap_v3"})
    assert execap.capability_profile_for("v1")["dexes"] == frozenset({"uniswap_v3"})
    assert execap.capability_profile_for(None)["dexes"] == frozenset({"uniswap_v3"})
    assert execap.capability_profile_for("bogus")["dexes"] == frozenset({"uniswap_v3"})


def test_v3_default_call_is_backward_compatible():
    """No version passed ⇒ historical UniV3-only verdict (live path unchanged)."""
    specs = {"p1": {"dex": "uniswap_v3"}, "p2": {"dex": "aerodrome"}}
    cap = execap.evaluate_executor_capability(route_pools=["p1", "p2"], pool_specs=specs)
    assert cap.status == execap.ExecutorCapabilityStatus.UNSUPPORTED   # aerodrome not v1


def test_v3_v2_profile_admits_algebra_and_aerodrome():
    specs = {"p1": {"dex": "uniswap_v3"}, "p2": {"dex": "aerodrome"},
             "p3": {"dex": "camelot_v3"}}
    cap = execap.evaluate_executor_capability(
        route_pools=["p1", "p2", "p3"], pool_specs=specs, receiver_version="v2")
    assert cap.status == execap.ExecutorCapabilityStatus.SUPPORTED


def test_v3_v2_still_fail_closed_on_curve():
    specs = {"p1": {"dex": "uniswap_v3"}, "p2": {"dex": "curve_stable"}}
    cap = execap.evaluate_executor_capability(
        route_pools=["p1", "p2"], pool_specs=specs, receiver_version="v2")
    assert cap.status == execap.ExecutorCapabilityStatus.UNSUPPORTED   # curve not in v2


def test_v3_unverifiable_venue_fails_closed():
    specs = {"p1": {"dex": "uniswap_v3"}, "p2": {}}   # p2 no dex
    cap = execap.evaluate_executor_capability(
        route_pools=["p1", "p2"], pool_specs=specs, receiver_version="v2")
    assert cap.status == execap.ExecutorCapabilityStatus.UNVERIFIABLE


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} V2/V3 tests passed")
