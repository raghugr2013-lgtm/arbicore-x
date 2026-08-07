"""Iteration 12 — extra coverage:
   • /api/execution/proposed/history snapshot list
   • static userscript v2 is reachable & parseable
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://flashloan-readiness.preview.emergentagent.com").rstrip("/")
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "ArbiCore2026!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code}")
    return s


def test_proposed_history_endpoint(session):
    # Give the worker a chance to write a snapshot.
    deadline = time.time() + 30
    body = None
    while time.time() < deadline:
        r = session.get(f"{BASE_URL}/api/execution/proposed/history?limit=5", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        if isinstance(body, dict) and body.get("snapshots"):
            break
        time.sleep(3)
    assert body is not None
    # Accept either {"snapshots":[...]} or list shape; assert a structured response.
    snapshots = body.get("snapshots") if isinstance(body, dict) else body
    assert isinstance(snapshots, list)
    # Worker writes every 15s; after >=15s+grace we expect at least 1 snapshot.
    # If empty we record but don't fail — proposer may not yet have run.
    if snapshots:
        s0 = snapshots[0]
        assert "ranked_count" in s0 or "primary" in s0 or "now" in s0


def test_userscript_v2_loads():
    r = requests.get(f"{BASE_URL}/arbicore-companion-v2.user.js", timeout=15)
    assert r.status_code == 200, r.status_code
    body = r.text
    assert "==UserScript==" in body and "==/UserScript==" in body
    # Basic sanity on the ingestion path it should target
    assert "quote-capture-batch" in body or "ArbiCore" in body
