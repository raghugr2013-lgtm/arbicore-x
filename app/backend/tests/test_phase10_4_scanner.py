"""Phase 10.4 · Scanner Configuration (multi-family) — unit tests (offline).

Every test uses the in-process fake Mongo layer from `test_phase10_config`.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.config.persistent import ConfigRepo, NetworkConfigRepo
from arbicore.config.scanner_config import (
    ScannerConfigRepo, SCANNER_GLOBAL_KIND, MARKET_FAMILIES,
    DEFAULT_SCANNER_GLOBAL,
)
from arbicore.data.scanner_config_defaults import (
    CANONICAL_FAMILIES, FAMILY_DEFAULTS,
)

# Reuse the fake Mongo layer defined in the Phase-10 config tests.
from tests.test_phase10_config import _FakeDB  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Canonical defaults + seed
# --------------------------------------------------------------------------- #

class TestScannerSeed:
    def test_seed_populates_every_family(self):
        db = _FakeDB()
        r = ScannerConfigRepo(ConfigRepo(db))
        snap = _run(r.ensure_seeded())
        assert set(snap["families"].keys()) == set(CANONICAL_FAMILIES)
        assert snap["global"]["paused"] is False
        assert snap["global"]["worker_concurrency"] > 0

    def test_seed_uses_canonical_defaults(self):
        db = _FakeDB()
        r = ScannerConfigRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        fl = _run(r.get_family("flash_loan_arb"))
        # Canonical default: flash-loan family ships disabled — operator must
        # opt in per D-4.1 institutional safety.
        assert fl["enabled"] is False
        assert "providers" in fl
        assert "balancer_v2" in fl["providers"]
        assert fl["providers"]["balancer_v2"]["fee_bps"] == 0
        cex = _run(r.get_family("cex_arb"))
        assert cex["enabled"] is True
        assert "BTCUSDT" in cex["tier_a_pairs"]

    def test_seed_is_idempotent(self):
        db = _FakeDB()
        r = ScannerConfigRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        _run(r.apply_family("cex_arb",
                             patch={"interval_s": 15},
                             actor="op", reason="tune"))
        _run(r.ensure_seeded())  # must not overwrite
        cex = _run(r.get_family("cex_arb"))
        assert cex["interval_s"] == 15


# --------------------------------------------------------------------------- #
# Global validation
# --------------------------------------------------------------------------- #

class TestGlobalValidation:
    def _r(self):
        return ScannerConfigRepo(ConfigRepo(_FakeDB()))

    def test_valid_full_global(self):
        r = self._r()
        v = r.validate_global({
            "worker_concurrency": 4,
            "max_concurrent_scans": 4,
            "opportunity_cache_s": 30,
            "opportunity_expiry_s": 300,
            "networks": {"base": {"enabled": True, "max_gas_gwei": 0.1,
                                    "max_latency_ms": 1500,
                                    "rpc_priority": 0}},
            "market_families": {"uniswap_v3": True, "curve": False},
        })
        assert v["ok"] is True

    def test_rejects_negative_worker_concurrency(self):
        r = self._r()
        v = r.validate_global({"worker_concurrency": -1})
        assert v["ok"] is False

    def test_rejects_unknown_market_family(self):
        r = self._r()
        v = r.validate_global({"market_families": {"pancake_v4": True}})
        assert v["ok"] is False

    def test_rejects_unknown_chain(self):
        r = self._r()
        v = r.validate_global({"networks": {"solana": {"enabled": True}}})
        assert v["ok"] is False

    def test_warning_when_no_chain_enabled(self):
        r = self._r()
        v = r.validate_global({"networks": {"base": {"enabled": False}}})
        assert v["ok"] is True
        assert any("no chain enabled" in w for w in v["warnings"])

    def test_live_validation_warns_on_missing_rpc(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
        db = _FakeDB()
        n = NetworkConfigRepo(ConfigRepo(db))
        _run(n.ensure_seed_from_env())
        r = ScannerConfigRepo(ConfigRepo(db), network_repo=n)
        v = _run(r.validate_global_live(
            {"networks": {"ethereum": {"enabled": True}}}
        ))
        assert v["ok"] is True
        assert any("ethereum" in w and "no RPC" in w for w in v["warnings"])


# --------------------------------------------------------------------------- #
# Family validation
# --------------------------------------------------------------------------- #

class TestFamilyValidation:
    def _r(self):
        return ScannerConfigRepo(ConfigRepo(_FakeDB()))

    def test_valid_family_patch(self):
        r = self._r()
        v = r.validate_family("cex_arb", {
            "enabled": True, "interval_s": 30,
            "gate_thresholds": {"default": {"min_spread_pct": 0.30,
                                              "min_depth_usd": 5000,
                                              "min_confidence": 55}},
        })
        assert v["ok"] is True

    def test_rejects_unknown_family(self):
        r = self._r()
        v = r.validate_family("triangular", {"enabled": True})
        assert v["ok"] is False

    def test_rejects_negative_interval(self):
        r = self._r()
        v = r.validate_family("cex_arb", {"interval_s": 0})
        assert v["ok"] is False

    def test_rejects_bad_gate_type(self):
        r = self._r()
        v = r.validate_family("cex_arb",
                               {"gate_thresholds": {"BTCUSDT": {"min_spread_pct": "no"}}})
        assert v["ok"] is False

    def test_flash_loan_warning_when_no_provider(self):
        r = self._r()
        v = r.validate_family("flash_loan_arb", {
            "enabled": True,
            "providers": {"balancer_v2": {"enabled": False, "fee_bps": 0},
                          "aave_v3": {"enabled": False, "fee_bps": 5}},
        })
        assert v["ok"] is True
        assert any("no flash-loan provider" in w for w in v["warnings"])


# --------------------------------------------------------------------------- #
# Apply / Rollback / Draft — per family + global
# --------------------------------------------------------------------------- #

class TestApplyRollback:
    def test_apply_family_then_rollback(self):
        db = _FakeDB()
        r = ScannerConfigRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        _run(r.apply_family("cex_arb", patch={"interval_s": 15},
                             actor="op", reason="tune"))
        assert _run(r.get_family("cex_arb"))["interval_s"] == 15
        _run(r.rollback_family("cex_arb", actor="op"))
        # Rollback restores the previous "next" — which is the seed default.
        assert _run(r.get_family("cex_arb"))["interval_s"] == \
                FAMILY_DEFAULTS["cex_arb"]["interval_s"]

    def test_apply_global_and_pause(self):
        db = _FakeDB()
        r = ScannerConfigRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        _run(r.pause(actor="op"))
        assert _run(r.get_global())["paused"] is True
        _run(r.resume(actor="op"))
        assert _run(r.get_global())["paused"] is False

    def test_reload_stamps_runtime(self):
        db = _FakeDB()
        r = ScannerConfigRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        out = _run(r.reload(actor="op"))
        assert out["runtime"]["last_reload_at"]
        assert out["runtime"]["last_reload_by"] == "op"

    def test_draft_then_apply_family(self):
        db = _FakeDB()
        r = ScannerConfigRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        _run(r.save_family_draft("dex_arb",
                                   {"verifier_concurrency": 8},
                                   actor="op"))
        assert _run(r.get_family_draft("dex_arb")) is not None
        _run(r.apply_family("dex_arb", actor="op", reason="promote"))
        assert _run(r.get_family("dex_arb"))["verifier_concurrency"] == 8
        assert _run(r.get_family_draft("dex_arb")) is None

    def test_history_tracks_per_family(self):
        db = _FakeDB()
        r = ScannerConfigRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        _run(r.apply_family("cex_arb", patch={"interval_s": 15}, actor="op"))
        _run(r.apply_family("cex_arb", patch={"interval_s": 20}, actor="op"))
        _run(r.apply_family("dex_arb", patch={"verifier_concurrency": 6}, actor="op"))
        cex_h = _run(r.family_history("cex_arb"))
        dex_h = _run(r.family_history("dex_arb"))
        # seed + 2 applies for cex; seed + 1 apply for dex
        assert len(cex_h) == 3
        assert len(dex_h) == 2

    def test_snapshot_returns_all_families(self):
        db = _FakeDB()
        r = ScannerConfigRepo(ConfigRepo(db))
        _run(r.ensure_seeded())
        snap = _run(r.snapshot())
        assert set(snap["family_ids"]) == set(CANONICAL_FAMILIES)
        assert set(snap["family_labels"].keys()) == set(CANONICAL_FAMILIES)
        assert set(snap["market_families_supported"]) == set(MARKET_FAMILIES)
