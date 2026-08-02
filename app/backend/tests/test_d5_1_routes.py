"""D-5.1 — HTTP route tests for cross_chain_arb endpoints."""
from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from arbicore.routes import scanners as scanner_routes


def _build_app(monkeypatch) -> FastAPI:
    app = FastAPI()

    async def _no_auth():
        return {"id": "test", "username": "ops"}
    app.dependency_overrides[scanner_routes.require_auth] = _no_auth

    cfg = {
        "_id": "cross_chain_arb",
        "enabled": False,
        "interval_s": 45,
        "default_notional_usd": 1000.0,
        "bridges": {
            "lifi":     {"enabled": False,
                          "credentials_env_var": "LIFI_API_KEY"},
            "stargate": {"enabled": False,
                          "credentials_env_var": "STARGATE_API_KEY"},
        },
        "chains": {
            "ethereum": {"enabled": False, "chain_id": 1,
                          "rpc_env_var": "ETH_RPC_URL", "gas_token": "ETH"},
            "arbitrum": {"enabled": False, "chain_id": 42161,
                          "rpc_env_var": "ARBITRUM_RPC_URL",
                          "gas_token": "ETH"},
            "base":     {"enabled": False, "chain_id": 8453,
                          "rpc_env_var": "BASE_RPC_URL", "gas_token": "ETH"},
            "optimism": {"enabled": False, "chain_id": 10,
                          "rpc_env_var": "OPTIMISM_RPC_URL",
                          "gas_token": "ETH"},
            "polygon":  {"enabled": False, "chain_id": 137,
                          "rpc_env_var": "POLYGON_RPC_URL",
                          "gas_token": "MATIC"},
            "solana":   {"enabled": False, "chain_id": 0,
                          "rpc_env_var": "SOLANA_RPC_URL", "gas_token": "SOL"},
        },
        "gate_thresholds": {"default": {
            "min_bridge_health_score": 70.0,
            "min_bridge_liveness_score": 75.0,
            "min_bridge_inventory_pct": 30.0,
            "max_inbound_latency_p95_s": 1800.0,
            "max_chain_congestion_score": 80.0,
            "max_chain_finality_s": 1800.0,
            "max_cross_chain_mev_risk_class": "MEDIUM",
        }},
        "roi_probability": {"min_sample_size": 2, "winsor_low_pct": 5.0},
        "transfer_model": {"corridor_overrides": {}},
        "verifier_concurrency": 2,
    }
    state = {"enabled": False}

    cfg_repo = MagicMock()
    cfg_repo.get = AsyncMock(return_value=cfg)

    async def _upd(_id, patch):
        cfg.update(patch)
        return cfg
    cfg_repo.update = AsyncMock(side_effect=_upd)
    state_repo = MagicMock()
    state_repo.get = AsyncMock(return_value=state)

    async def _set(_id, enabled, **kw):
        state["enabled"] = enabled
        return state
    state_repo.set_enabled = AsyncMock(side_effect=_set)
    monkeypatch.setattr(scanner_routes, "get_scanner_config_repo",
                        lambda: cfg_repo)
    monkeypatch.setattr(scanner_routes, "get_scanner_state_repo",
                        lambda: state_repo)

    from arbicore.scanners.cross_chain_arbitrage.scanner import (
        CrossChainArbitrageScanner,
    )
    scanner_mock = MagicMock(spec=CrossChainArbitrageScanner)
    scanner_mock.scanner_id = "cross_chain_arb"
    scanner_mock.stats = {
        "iterations": 0, "rows_emitted": 0, "verifier_confirmed": 0,
        "verifier_denied": 0, "verifier_errors": 0,
        "candidates_claimed": 0,
        "gate_rejections": {
            "gate_7_bridge_liveness": 0,
            "gate_8_chain_liveness": 0,
            "gate_9_cross_chain_mev": 0,
        },
        "denied_venue_unreadable": 0,
    }
    scanner_mock.transfer_provider_is_default = True
    sreg = MagicMock()
    sreg.ids.return_value = ["lifi_aggregator", "stargate_direct"]
    sreg.all.return_value = []
    vreg = MagicMock()
    vreg.types.return_value = ["CROSS_CHAIN_ARBITRAGE"]
    scanner_mock.source_registry = sreg
    scanner_mock.verifier_registry = vreg
    cl = MagicMock()
    cl.all_snapshots.return_value = {}
    scanner_mock.chain_liveness = cl
    scanner_mock.start = AsyncMock(return_value=None)
    monkeypatch.setattr(scanner_routes, "get_cross_chain_arb_scanner",
                        lambda: scanner_mock)

    app.include_router(scanner_routes.router)
    return app


def _do(app, method, url, **kw):
    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app),
                                base_url="http://test") as c:
            fn = getattr(c, method.lower())
            return await fn(url, **kw)
    return asyncio.run(_run())


def test_status_endpoint(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "GET", "/api/arbicore/scanners/cross_chain_arb/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanner_id"] == "cross_chain_arb"
    assert body["wave"] == "D-5.1"
    assert body["enabled"] is False
    assert body["transfer_provider"] == "default-noop"
    assert "lifi" in body["config"]["bridges"]
    assert "ethereum" in body["config"]["chains"]


def test_kill_endpoint(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "POST", "/api/arbicore/scanners/cross_chain_arb/kill")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_resume_endpoint(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "POST", "/api/arbicore/scanners/cross_chain_arb/resume")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


def test_config_update_endpoint(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "PUT",
                "/api/arbicore/scanners/cross_chain_arb/config",
                json={"interval_s": 90})
    assert resp.status_code == 200
    assert resp.json()["interval_s"] == 90


def test_config_update_rejects_empty(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "PUT",
                "/api/arbicore/scanners/cross_chain_arb/config",
                json={})
    assert resp.status_code == 400


def test_bridge_enable_endpoint(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "POST",
                "/api/arbicore/scanners/cross_chain_arb/bridges/lifi/enable")
    assert resp.status_code == 200
    assert resp.json()["bridges"]["lifi"]["enabled"] is True


def test_bridge_disable_endpoint(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "POST",
                "/api/arbicore/scanners/cross_chain_arb/bridges/stargate/disable")
    assert resp.status_code == 200
    assert resp.json()["bridges"]["stargate"]["enabled"] is False


def test_bridge_unknown_is_404(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "POST",
                "/api/arbicore/scanners/cross_chain_arb/bridges/wormhole/enable")
    assert resp.status_code == 404


def test_chain_enable_endpoint(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "POST",
                "/api/arbicore/scanners/cross_chain_arb/chains/ethereum/enable")
    assert resp.status_code == 200
    assert resp.json()["chains"]["ethereum"]["enabled"] is True


def test_chain_unknown_is_404(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "POST",
                "/api/arbicore/scanners/cross_chain_arb/chains/aptos/enable")
    assert resp.status_code == 404


def test_source_health_endpoint(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "GET",
                "/api/arbicore/scanners/cross_chain_arb/source-health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanner_id"] == "cross_chain_arb"
    assert "sources" in body
    assert "chain_liveness" in body
    assert body["transfer_provider_is_default"] is True


def test_preview_endpoint(monkeypatch):
    app = _build_app(monkeypatch)
    resp = _do(app, "GET",
                "/api/arbicore/scanners/cross_chain_arb/preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scanner_id"] == "cross_chain_arb"
    assert "invariants" in body
    assert "bridges" in body
    assert "chains" in body
    assert "registry_provenance" in body
    assert body["registry_provenance"]["lifi_quote_real"] == "REAL"
