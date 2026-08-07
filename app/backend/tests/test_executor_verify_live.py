"""Iteration 2: verify FlashLoanReceiver executor on Base Sepolia + regressions."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fallback: read from frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = BASE_URL.rstrip("/")

EXECUTOR_ADDR = "0x99c0b64e8F24fc1aADb07dAbA938d9f11dCD1052"
OWNER_ADDR = "0x65afB0a65Fd22F88022915F53eD48DA34fb02003"
EXPECTED_VAULT = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
EXPECTED_ROUTER = "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"
EXPECTED_AAVE = "0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27"
CHAIN_ID = 84532


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


# ---------- Executor verify (bug-fix verification) ----------
class TestExecutorVerify:
    def test_verify_ready_all_checks(self, client):
        r = client.get(f"{BASE_URL}/api/arbicore/executor/verify", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("overall_status") == "READY", data
        assert data.get("ready") is True, data
        assert data.get("address", "").lower() == EXECUTOR_ADDR.lower()

        checks = data["checks"]
        # critical READY checks
        for k in ("address_configured", "rpc_available", "contract_deployed",
                  "vault_matches", "router_matches", "aave_pool_matches"):
            assert checks[k]["status"] == "READY", f"{k}={checks[k]}"

        assert str(CHAIN_ID) in checks["address_configured"]["detail"] or \
               EXECUTOR_ADDR.lower() in checks["address_configured"]["detail"].lower()
        assert checks["rpc_available"]["chain_id"] == CHAIN_ID
        # bytecode ~4987 bytes
        assert "bytecode" in checks["contract_deployed"]["detail"].lower()
        assert EXPECTED_VAULT.lower() in checks["vault_matches"]["detail"].lower()
        assert EXPECTED_ROUTER.lower() in checks["router_matches"]["detail"].lower()
        assert EXPECTED_AAVE.lower() in checks["aave_pool_matches"]["detail"].lower()

        # owner_matches is INFO
        assert checks["owner_matches"]["status"] == "INFO"
        assert OWNER_ADDR.lower() in checks["owner_matches"]["detail"].lower()

        # expected block reflects chain 84532
        exp = data["expected"]
        assert exp["chain_id"] == CHAIN_ID
        assert exp["vault"].lower() == EXPECTED_VAULT.lower()
        assert exp["router"].lower() == EXPECTED_ROUTER.lower()
        assert exp["aave_pool"].lower() == EXPECTED_AAVE.lower()


# ---------- Wizard state ----------
class TestWizardState:
    def test_wizard_state_executor_ready_wallet_blocking(self, client):
        r = client.get(f"{BASE_URL}/api/arbicore/wizard/state", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        steps = data.get("steps", [])
        assert isinstance(steps, list) and steps
        by_key = {s["key"]: s for s in steps}
        assert by_key["executor"]["status"] == "READY", by_key["executor"]
        assert by_key["executor_verify"]["status"] == "READY", by_key["executor_verify"]
        assert by_key["kill_switch"]["status"] == "READY", by_key["kill_switch"]
        assert by_key["wallet"]["status"] == "BLOCKED", by_key["wallet"]
        # mode WAIT (SHADOW)
        assert by_key["mode"]["status"] in ("WAIT", "BLOCKED"), by_key["mode"]

        assert data.get("overall_status") == "BLOCKED"
        blockers = data.get("blockers") or data.get("blocking_steps") or []
        assert "wallet" in blockers, data
        # only wallet should be blocking
        non_wallet = [b for b in blockers if b != "wallet"]
        assert non_wallet == [], f"unexpected blockers: {non_wallet}"


# ---------- Execution mode governance ----------
class TestExecutionMode:
    def test_flash_loan_arbitrage_shadow(self, client):
        r = client.get(f"{BASE_URL}/api/arbicore/execution/mode", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("items", [])
        fla = next((x for x in items if x.get("strategy") == "flash_loan_arbitrage"), None)
        assert fla is not None, data
        assert fla.get("mode") == "SHADOW", fla


# ---------- Regressions ----------
class TestRegressions:
    def test_opportunity_probe_default(self, client):
        r = client.post(f"{BASE_URL}/api/arbicore/wizard/opportunity-probe",
                        json={}, timeout=45)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True, data
        tiers = data.get("tiers") or []
        fees = [t.get("fee_ppm") or t.get("fee") for t in tiers]
        assert set(fees) >= {500, 3000, 10000}, fees
        assert data.get("any_live_pool") is True, data

    def test_rpc_check(self, client):
        r = client.get(f"{BASE_URL}/api/arbicore/rpc/check", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "READY" or data.get("overall_status") == "READY", data
        # chain_id 84532
        cid = data.get("chain_id") or (data.get("detail") or "")
        if isinstance(cid, str):
            assert "84532" in cid
        else:
            assert cid == CHAIN_ID
        bn = data.get("block_number")
        assert isinstance(bn, int) and bn > 0, data


# ---------- No broadcast side effects ----------
class TestNoBroadcastSideEffects:
    def test_no_broadcast_in_journal(self, client):
        # try common journal endpoints; skip if none exist
        candidates = [
            "/api/arbicore/journal/recent",
            "/api/arbicore/journal",
            "/api/arbicore/opportunities/journal",
        ]
        found = False
        for path in candidates:
            r = client.get(f"{BASE_URL}{path}", timeout=20)
            if r.status_code == 200:
                found = True
                try:
                    data = r.json()
                except Exception:
                    continue
                # search nested for BROADCAST_SENT
                text = str(data).upper()
                assert "BROADCAST_SENT" not in text, f"{path} contains BROADCAST_SENT"
        if not found:
            pytest.skip("No journal endpoint available")
