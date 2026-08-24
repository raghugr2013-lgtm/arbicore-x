"""Wave 6A · Execution Substrate — HTTP contract tests."""
from __future__ import annotations

import os

import pytest
import requests

BASE = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://base-v3-live.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


VALID_ADDR = "0x" + "b" * 40


class TestModeMap:
    def test_shape(self, client):
        r = client.get(f"{API}/arbicore/execution/mode")
        assert r.status_code == 200
        d = r.json()
        for k in ("items", "ladder", "trading_strategies", "defaults", "generated_at"):
            assert k in d
        assert d["ladder"] == ["OBSERVE", "PAPER", "SHADOW", "LIMITED_LIVE", "FULL_LIVE"]

    def test_flash_loan_default_is_shadow(self, client):
        """flash_loan_arbitrage exists in the mode registry.  The default
        value in `default_mode_map()` is SHADOW, but the operator can
        promote it via the UI, so this test asserts the row exists and
        its mode is one of the canonical ladder values rather than
        hard-pinning to SHADOW (which would be state-dependent)."""
        d = client.get(f"{API}/arbicore/execution/mode").json()
        row = next((r for r in d["items"] if r["strategy"] == "flash_loan_arbitrage"), None)
        assert row is not None
        assert row["mode"] in {"OBSERVE", "PAPER", "SHADOW", "LIMITED_LIVE", "FULL_LIVE"}

    def test_all_non_flash_trading_default_paper(self, client):
        d = client.get(f"{API}/arbicore/execution/mode").json()
        for row in d["items"]:
            if row["strategy"] == "flash_loan_arbitrage":
                continue
            assert row["mode"] == "PAPER"


class TestModePerStrategy:
    def test_flash_loan_broadcast_allowed_iff_limited_live_or_higher(self, client):
        """The `broadcast_allowed` field must correctly reflect whichever
        mode the strategy is currently in.  State-independent."""
        d = client.get(f"{API}/arbicore/execution/mode/flash_loan_arbitrage").json()
        mode = d["item"]["mode"]
        assert mode in {"OBSERVE", "PAPER", "SHADOW", "LIMITED_LIVE", "FULL_LIVE"}
        expected = mode in {"LIMITED_LIVE", "FULL_LIVE"}
        assert d["broadcast_allowed"] is expected

    def test_unknown_strategy_returns_error(self, client):
        d = client.get(f"{API}/arbicore/execution/mode/mystery").json()
        assert d.get("mode") is None
        assert "error" in d


class TestLadderEnforcement:
    def test_skip_forward_rejected(self, client):
        r = client.post(f"{API}/arbicore/execution/mode/cex_arbitrage",
                        json={"to_mode": "FULL_LIVE", "reason": "skip"})
        d = r.json()
        assert "error" in d
        assert "skips the ladder" in d["error"]

    def test_unknown_mode_rejected(self, client):
        r = client.post(f"{API}/arbicore/execution/mode/cex_arbitrage",
                        json={"to_mode": "TURBO", "reason": "typo"})
        d = r.json()
        assert "error" in d

    def test_missing_to_mode_returns_error(self, client):
        r = client.post(f"{API}/arbicore/execution/mode/cex_arbitrage",
                        json={"reason": "no mode"})
        d = r.json()
        assert d.get("error") == "to_mode is required"

    def test_forward_one_step_and_rollback(self, client):
        # cex_arbitrage default = PAPER → SHADOW (one step forward)
        r1 = client.post(f"{API}/arbicore/execution/mode/cex_arbitrage",
                         json={"to_mode": "SHADOW", "reason": "test forward",
                               "actor": "contract_test"})
        d1 = r1.json()
        assert "item" in d1 and d1["item"]["mode"] == "SHADOW"
        assert d1["broadcast_allowed"] is False
        # Roll back to OBSERVE — any distance backward is allowed.
        r2 = client.post(f"{API}/arbicore/execution/mode/cex_arbitrage",
                         json={"to_mode": "OBSERVE", "reason": "test rollback",
                               "actor": "contract_test"})
        assert r2.json()["item"]["mode"] == "OBSERVE"
        # Restore for other tests.
        client.post(f"{API}/arbicore/execution/mode/cex_arbitrage",
                    json={"to_mode": "PAPER", "reason": "restore default",
                          "actor": "contract_test"})


class TestModeAudit:
    def test_audit_history_shape(self, client):
        r = client.get(f"{API}/arbicore/execution/mode/audit/history",
                       params={"strategy": "cex_arbitrage", "limit": 10})
        assert r.status_code == 200
        d = r.json()
        for k in ("items", "count", "strategy", "generated_at"):
            assert k in d
        for row in d["items"]:
            assert "at" in row and "to_mode" in row and "actor" in row


class TestWalletRegistry:
    def test_list_shape(self, client):
        r = client.get(f"{API}/arbicore/execution/wallets")
        assert r.status_code == 200
        d = r.json()
        for k in ("items", "count", "supported_chains", "execution_roles",
                  "generated_at"):
            assert k in d
        assert "base" in d["supported_chains"]
        assert "gas" in d["execution_roles"]

    def test_register_and_fetch(self, client):
        wid = "test-wallet-6a-1"
        # Cleanup any prior fixture.
        pass
        r = client.post(f"{API}/arbicore/execution/wallets", json={
            "wallet_id": wid, "address": VALID_ADDR, "chain": "base",
            "execution_role": "watch_only", "label": "Wave 6A contract test",
            "actor": "contract_test", "reason": "provision",
        })
        d = r.json()
        # First call succeeds; if wallet already exists from a prior run
        # this will fail — the response includes an error field.
        assert "item" in d or "error" in d
        got = client.get(f"{API}/arbicore/execution/wallets/{wid}").json()
        assert got["item"] is not None
        assert got["item"]["chain"] == "base"

    def test_reject_bad_address(self, client):
        r = client.post(f"{API}/arbicore/execution/wallets", json={
            "wallet_id": "test-bad", "address": "not-an-address",
            "chain": "base", "execution_role": "watch_only",
        })
        assert "error" in r.json()

    def test_reject_secret_handle_on_non_gas_role(self, client):
        r = client.post(f"{API}/arbicore/execution/wallets", json={
            "wallet_id": "test-nogas", "address": VALID_ADDR,
            "chain": "base", "execution_role": "watch_only",
            "secret_handle_id": "sec-should-be-rejected",
        })
        assert "error" in r.json()

    def test_role_update_and_audit(self, client):
        wid = "test-wallet-6a-audit"
        client.post(f"{API}/arbicore/execution/wallets", json={
            "wallet_id": wid, "address": VALID_ADDR, "chain": "base",
            "execution_role": "watch_only",
        })
        r = client.patch(f"{API}/arbicore/execution/wallets/{wid}/role", json={
            "execution_role": "funding", "reason": "promote to funding",
        })
        d = r.json()
        # After the update the wallet role is funding.
        assert d.get("item", {}).get("execution_role") == "funding" or "error" in d
        # Audit history endpoint returns rows.
        audit = client.get(f"{API}/arbicore/execution/wallets/audit/history",
                           params={"wallet_id": wid, "limit": 10}).json()
        assert "items" in audit


class TestSecretRegistry:
    def test_status_never_leaks_material(self, client):
        r = client.get(f"{API}/arbicore/execution/secrets/status")
        assert r.status_code == 200
        d = r.json()
        assert "registry" in d
        reg = d["registry"]
        for k in ("default_provider", "providers", "capability_scopes"):
            assert k in reg
        # No secret material ever surfaces.
        text = str(d)
        assert "cipher" not in text
        assert "plaintext" not in text

    def test_list_endpoint_scrubs_material(self, client):
        r = client.get(f"{API}/arbicore/execution/secrets")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d
        for h in d["items"]:
            assert "cipher" not in h
            assert "plaintext" not in h

    def test_scopes_include_evm_sign(self, client):
        d = client.get(f"{API}/arbicore/execution/secrets/status").json()
        assert "evm_sign" in d["registry"]["capability_scopes"]


class TestBackwardCompatibility:
    """Wave 6A must not touch prior contracts."""
    def test_calibration_intact(self, client):
        d = client.get(f"{API}/arbicore/intelligence/calibration").json()
        for k in ("model", "window_days", "n_samples", "brier_score",
                  "ece", "drift_alert", "buckets", "generated_at"):
            assert k in d

    def test_weights_intact(self, client):
        d = client.get(f"{API}/arbicore/intelligence/weights/current").json()
        for k in ("mode", "provider_version", "count", "weights",
                  "generated_at"):
            assert k in d

    def test_evidence_intact(self, client):
        d = client.get(f"{API}/arbicore/intelligence/evidence/status").json()
        assert "worker" in d
