"""D-5.2 Completion — RpcChainLivenessLoader tests."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from arbicore.scanners.cross_chain_arbitrage.chain_liveness import (
    ChainLivenessRegistry, RpcChainLivenessLoader,
)


def _cfg() -> Dict[str, Any]:
    return {
        "chains": {
            "ethereum": {"enabled": False, "gas_token": "ETH",
                          "rpc_env_var": "ETH_RPC_URL"},
            "arbitrum": {"enabled": False, "gas_token": "ETH",
                          "rpc_env_var": "ARB_RPC_URL"},
            "polygon":  {"enabled": False, "gas_token": "MATIC",
                          "rpc_env_var": "POLY_RPC_URL"},
            "solana":   {"enabled": False, "gas_token": "SOL",
                          "rpc_env_var": "SOL_RPC_URL"},
        }
    }


def _env_resolver(mapping: Dict[str, str]):
    def _get(key, default=""):
        return mapping.get(key, default)
    return _get


def test_skips_chains_without_rpc_url():
    loader = RpcChainLivenessLoader(
        config_loader=_cfg, env_resolver=_env_resolver({}))
    out = asyncio.run(loader())
    assert out == {}
    asyncio.run(loader.close())


def test_evm_probe_low_congestion(monkeypatch):
    loader = RpcChainLivenessLoader(
        config_loader=_cfg,
        env_resolver=_env_resolver({"ETH_RPC_URL": "http://eth.example"}),
    )

    async def _ok(*a, **kw):
        return {"result": hex(20_000_000_000)}  # 20 gwei — calm
    monkeypatch.setattr(
        "arbicore.scanners.cross_chain_arbitrage.chain_liveness."
        "_parse_hex",
        lambda s: float(int(s, 16)) if isinstance(s, str) and s.startswith("0x")
                  else None)
    monkeypatch.setattr(
        "arbicore.scanners.http_retry.post_json_with_retry", _ok)
    out = asyncio.run(loader())
    assert "ethereum" in out
    eth = out["ethereum"]
    assert eth["ok"] is True
    assert eth["congestion_score"] < 50.0
    asyncio.run(loader.close())


def test_evm_probe_high_congestion(monkeypatch):
    loader = RpcChainLivenessLoader(
        config_loader=_cfg,
        env_resolver=_env_resolver({"ETH_RPC_URL": "http://eth.example"}),
    )

    async def _ok(*a, **kw):
        return {"result": hex(150_000_000_000)}  # 150 gwei — congested
    monkeypatch.setattr(
        "arbicore.scanners.http_retry.post_json_with_retry", _ok)
    out = asyncio.run(loader())
    assert out["ethereum"]["congestion_score"] >= 90.0
    asyncio.run(loader.close())


def test_solana_probe_calm(monkeypatch):
    loader = RpcChainLivenessLoader(
        config_loader=_cfg,
        env_resolver=_env_resolver({"SOL_RPC_URL": "http://sol.example"}),
    )

    async def _ok(*a, **kw):
        return {"result": [{"prioritizationFee": 500}] * 5}
    monkeypatch.setattr(
        "arbicore.scanners.http_retry.post_json_with_retry", _ok)
    out = asyncio.run(loader())
    assert "solana" in out
    assert out["solana"]["congestion_score"] < 50.0
    assert out["solana"]["gas_token"] == "SOL"
    asyncio.run(loader.close())


def test_solana_probe_congested(monkeypatch):
    loader = RpcChainLivenessLoader(
        config_loader=_cfg,
        env_resolver=_env_resolver({"SOL_RPC_URL": "http://sol.example"}),
    )

    async def _ok(*a, **kw):
        return {"result": [{"prioritizationFee": 200_000}] * 5}
    monkeypatch.setattr(
        "arbicore.scanners.http_retry.post_json_with_retry", _ok)
    out = asyncio.run(loader())
    assert out["solana"]["congestion_score"] >= 90.0
    asyncio.run(loader.close())


def test_rpc_exception_yields_ok_false(monkeypatch):
    loader = RpcChainLivenessLoader(
        config_loader=_cfg,
        env_resolver=_env_resolver({"ETH_RPC_URL": "http://bad.example"}),
    )

    async def _boom(*a, **kw):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(
        "arbicore.scanners.http_retry.post_json_with_retry", _boom)
    out = asyncio.run(loader())
    eth = out["ethereum"]
    assert eth["ok"] is False
    assert "RuntimeError" in eth["last_error"]
    asyncio.run(loader.close())


def test_loader_caches_per_chain(monkeypatch):
    loader = RpcChainLivenessLoader(
        config_loader=_cfg,
        ttl_cache_s=60.0,
        env_resolver=_env_resolver({"ETH_RPC_URL": "http://eth.example"}),
    )
    calls = {"n": 0}

    async def _ok(*a, **kw):
        calls["n"] += 1
        return {"result": hex(20_000_000_000)}
    monkeypatch.setattr(
        "arbicore.scanners.http_retry.post_json_with_retry", _ok)
    asyncio.run(loader())
    asyncio.run(loader())
    assert calls["n"] == 1
    asyncio.run(loader.close())


def test_registry_integration_with_rpc_loader(monkeypatch):
    """End-to-end: ChainLivenessRegistry + RpcChainLivenessLoader."""
    loader = RpcChainLivenessLoader(
        config_loader=_cfg,
        env_resolver=_env_resolver({"ETH_RPC_URL": "http://eth.example"}),
    )

    async def _ok(*a, **kw):
        return {"result": hex(80_000_000_000)}  # 80 gwei — congested
    monkeypatch.setattr(
        "arbicore.scanners.http_retry.post_json_with_retry", _ok)

    reg = ChainLivenessRegistry(config_loader=_cfg, liveness_loader=loader)
    asyncio.run(reg.refresh())
    snap = reg.get("ethereum")
    assert snap.ok is True
    assert snap.congestion_score > 50.0
    asyncio.run(loader.close())


def test_loader_inv2_no_emission_bus():
    import arbicore.scanners.cross_chain_arbitrage.chain_liveness as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "from ...runtime.event_bus" not in text


def test_loader_reuses_http_retry_substrate():
    """Substrate-reuse audit: loader must consume http_retry imports."""
    import arbicore.scanners.cross_chain_arbitrage.chain_liveness as mod
    text = open(mod.__file__).read()
    assert "post_json_with_retry" in text
    assert "RetryConfig" in text
    assert "TTLCache" in text
