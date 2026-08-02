"""Phase E3 — Shadow recovery + stuck-fund integration test (best-effort).

Strategy:
  1. Save current state (bitmart role, shadow_enabled, min_net_spread_pct).
  2. Disable bitmart (role=disabled), enable shadow, drop floor to -100.
  3. Wait up to 120s for a shadow cycle to surface and reach BDAG_RECEIVED
     and then STUCK_WAITING_DEPOSIT with stuck=true.
  4. Re-enable bitmart as backup. Wait up to 60s for a 'recovery_reroute'
     shadow_decision and stuck=false with sell_venue=bitmart.
  5. ALWAYS restore: bitmart=backup, shadow_enabled=false,
     min_net_spread_pct=2.0, abort any open shadow cycles.

If the live market doesn't surface an opportunity in time, the test SKIPs
(this is market-dependent, as noted by the main agent).
"""
import os
import time
from pathlib import Path

import pytest
import requests

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    envp = Path("/app/frontend/.env")
    if envp.exists():
        for line in envp.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                _BASE = line.split("=", 1)[1].strip()
                break
BASE = _BASE.rstrip("/")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore#2026"}, timeout=15)
    assert r.status_code == 200, r.text
    return s


def _cycles(client):
    return client.get(f"{BASE}/api/execution/cycles", timeout=15).json().get("cycles", [])


def test_stuck_then_recovery(client):
    orig_cfg = client.get(f"{BASE}/api/execution/config", timeout=15).json()
    orig_floor = orig_cfg["limits"]["min_net_spread_pct"]
    orig_shadow = orig_cfg.get("shadow_enabled", False)

    # disable bitmart so only deposit-gate-closed/unknown remain
    client.patch(f"{BASE}/api/execution/venues/bitmart", json={"role": "disabled"}, timeout=15)
    client.patch(f"{BASE}/api/execution/config",
                 json={"limits": {"min_net_spread_pct": -100}, "shadow_enabled": True},
                 timeout=15)

    stuck_cycle_id = None
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            cs = _cycles(client)
            sc = [c for c in cs if c.get("mode") == "shadow" and c.get("stuck")]
            if sc:
                stuck_cycle_id = sorted(sc, key=lambda c: c["created_at"])[-1]["id"]
                break
            time.sleep(8)
        if not stuck_cycle_id:
            pytest.skip("no stuck shadow cycle surfaced within 120s (market-dependent)")

        # Verify stuck shape
        cyc = client.get(f"{BASE}/api/execution/cycles/{stuck_cycle_id}", timeout=15).json()
        assert cyc["stuck"] is True
        assert cyc.get("recommended_action")

        # restore bitmart=backup, expect recovery
        client.patch(f"{BASE}/api/execution/venues/bitmart", json={"role": "backup"}, timeout=15)

        deadline = time.time() + 60
        recovered = False
        while time.time() < deadline:
            cyc = client.get(f"{BASE}/api/execution/cycles/{stuck_cycle_id}", timeout=15).json()
            actions = [d.get("action") for d in cyc.get("shadow_decisions", [])]
            if "recovery_reroute" in actions and cyc.get("stuck") is False:
                recovered = True
                break
            time.sleep(5)
        assert recovered, "recovery_reroute not observed within 60s after re-enabling bitmart"
        cyc = client.get(f"{BASE}/api/execution/cycles/{stuck_cycle_id}", timeout=15).json()
        assert cyc.get("sell_venue") == "bitmart", f"expected sell_venue=bitmart, got {cyc.get('sell_venue')}"
    finally:
        # MANDATORY cleanup
        client.patch(f"{BASE}/api/execution/venues/bitmart", json={"role": "backup"}, timeout=15)
        client.patch(f"{BASE}/api/execution/config",
                     json={"limits": {"min_net_spread_pct": orig_floor},
                           "shadow_enabled": orig_shadow},
                     timeout=15)
        # abort any open shadow cycles
        for c in _cycles(client):
            if c.get("mode") == "shadow" and c["state"] not in ("COMPLETE", "ABORTED"):
                client.post(f"{BASE}/api/execution/cycles/{c['id']}/abort", timeout=15)
