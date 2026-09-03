"""QA (iteration_7): snapshot shape + safety for the READ-ONLY near-threshold
signal in scripts.m3_0_spread_widener_watch. Fully offline: all live providers
are monkeypatched, no RPC, no signer, no broadcaster.
"""
from types import SimpleNamespace

import pytest

import scripts.m3_0_spread_widener_watch as W


# ---- fail-closed with no RPC ------------------------------------------------

@pytest.mark.asyncio
async def test_scan_once_fail_closed_without_rpc(monkeypatch):
    import arbicore.searcher.runtime as rt
    monkeypatch.setattr(rt, "make_base_eth_call_from_env", lambda *a, **k: None)
    snap = await W._scan_once()
    assert snap["error"] == "no Base RPC configured (fail-closed)"
    assert "flagged" not in snap


# ---- snapshot shape with fake providers ------------------------------------

class _FakeEcon:
    def __init__(self, *a, **k):
        pass

    def assess(self, **kw):
        # net derives from gross deterministically
        return SimpleNamespace(atomic_profit_usd=float(kw["gross_profit_pct"]) * 10.0)


_ROUTES = {
    # gross -> net = gross*10
    "PA": 5.0,    # net 50  -> above min_net 35 (flagged)
    "PB": 3.0,    # net 30  -> gap 5   (near)
    "PC": 2.0,    # net 20  -> gap 15  (near)
    "PD": -5.0,   # net -50 -> gap 85  (excluded, out of band)
}


def _install_fakes(monkeypatch):
    import arbicore.searcher.runtime as rt
    import arbicore.searcher.price_feed as pf
    import arbicore.scanners.flash_loan_arbitrage.live_quote_provider as lqp
    import arbicore.scanners.flash_loan_arbitrage.economics as ec
    import arbicore.searcher.aero_resolver as ar

    monkeypatch.setattr(rt, "make_base_eth_call_from_env", lambda *a, **k: object())
    monkeypatch.setattr(rt, "build_base_tvl_provider", lambda *a, **k: None)
    monkeypatch.setattr(rt, "make_base_congestion_source_from_env", lambda *a, **k: None)
    monkeypatch.setattr(pf, "build_base_price_feed_from_env", lambda *a, **k: None)
    monkeypatch.setattr(ec, "FlashLoanEconomicsAssessor", _FakeEcon)

    async def _noop_resolve(*a, **k):
        return None
    monkeypatch.setattr(ar, "resolve_and_propagate", _noop_resolve)

    async def _fake_provider(hm, borrow_usd):
        g = _ROUTES.get(hm["route_pools"][0])
        if g is None:
            return None
        return {"route_quote_status": "ok", "gross_profit_pct": g,
                "hop_legs": [{"h": 1}], "min_pool_tvl_usd_in_route": 1e6}
    monkeypatch.setattr(lqp, "make_live_quote_provider",
                        lambda *a, **k: _fake_provider)

    cycles = [{"name": f"c_{p}", "borrow_token": "WETH",
               "route_pools": [p, "x"], "cycle_token_path": ["WETH", "USDC", "WETH"]}
              for p in _ROUTES]
    monkeypatch.setattr(W, "_enumerate_cycles", lambda: cycles)

    async def _no_confirmed(limit: int = 20):
        return []
    monkeypatch.setattr(W, "_load_confirmed_cycles", _no_confirmed)


@pytest.mark.asyncio
async def test_snapshot_shape_and_near_threshold(monkeypatch):
    _install_fakes(monkeypatch)
    snap = await W._scan_once()

    # thresholds untouched: M3 floor 25 + buffer 10
    assert snap["thresholds"]["min_net_usd"] == pytest.approx(35.0)
    assert snap["thresholds"]["near_band_usd"] == pytest.approx(25.0)

    # safety
    assert snap["safe"] is True
    assert snap["signed_or_broadcast"] is False
    assert snap["focus"] is False

    assert snap["routes_scanned"] == 4
    assert snap["flagged_count"] == 1
    assert [r["name"] for r in snap["flagged"]] == ["c_PA"]

    # near-threshold: nearest first, excludes above-threshold and far-below
    assert snap["near_threshold_count"] == 2
    names = [r["name"] for r in snap["near_threshold"]]
    assert names == ["c_PB", "c_PC"]
    assert all(r["near_threshold"] is True for r in snap["near_threshold"])
    assert snap["near_threshold"][0]["net_gap_usd"] == pytest.approx(5.0)

    # focus pools = union(flagged, near)
    assert snap["focus_route_pools"] == [["PA", "x"], ["PB", "x"], ["PC", "x"]]


@pytest.mark.asyncio
async def test_focused_resampling_restricts_universe(monkeypatch):
    _install_fakes(monkeypatch)
    snap = await W._scan_once(focus_route_pools=[["PB", "x"], ["PC", "x"]])
    assert snap["focus"] is True
    assert snap["routes_scanned"] == 2
    assert snap["flagged_count"] == 0
    assert snap["near_threshold_count"] == 2
    assert snap["safe"] is True and snap["signed_or_broadcast"] is False


@pytest.mark.asyncio
async def test_near_band_env_override_does_not_change_min_net(monkeypatch):
    _install_fakes(monkeypatch)
    monkeypatch.setenv("ARBICORE_SPREAD_WATCH_NEAR_BAND_USD", "6")
    snap = await W._scan_once()
    assert snap["thresholds"]["min_net_usd"] == pytest.approx(35.0)
    assert snap["near_threshold_count"] == 1
    assert snap["near_threshold"][0]["name"] == "c_PB"
    assert snap["flagged_count"] == 1


# ---- source-level safety: no signer / broadcaster ---------------------------

def test_watcher_source_has_no_signer_or_broadcast():
    import inspect
    # ignore comments/prose lines — only executable code matters
    src = "\n".join(l for l in inspect.getsource(W).splitlines()
                    if not l.strip().startswith(("#", "*", "\"\"\"")))
    for bad in ("Broadcaster", "sign_transaction", "send_raw_transaction",
                "eth_sendRawTransaction", "private_key", "PRIVATE_KEY",
                "signed_raw_tx"):
        assert bad not in src, f"unexpected {bad!r} in watcher source"
