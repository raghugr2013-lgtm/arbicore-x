"""STAGE 2 — T2 Base searcher (SHADOW) runtime config wiring (static + functional).

Guards the VPS blocker where the canonical deployment env omitted the T2 runtime
wiring, so the backend container booted without:
  * ARBICORE_T2_SEARCHER_ENABLED
  * ARBICORE_WSS_URL_BASE  (primary Base WSS var consumed by the T2 runtime)

Proves:
  1. 00_detect_env.sh reproducibly wires ARBICORE_T2_SEARCHER_ENABLED (default true)
     and injects an operator-supplied Base WSS without erasing existing config.
  2. common.sh assert_t2_config_or_die() fails CLOSED when T2 is enabled but the
     Base WSS (ARBICORE_WSS_URL_BASE / fallback ARBICORE_RPC_WSS_BASE) is missing.
  3. 01_preflight.sh invokes that gate.
The primary WSS var name is asserted directly against the T2 source of truth.
"""
import re
import subprocess

REPO = "/app"
COMMON = f"{REPO}/deployment/upgrade/lib/common.sh"
DETECT_ENV = f"{REPO}/deployment/upgrade/steps/00_detect_env.sh"
PREFLIGHT = f"{REPO}/deployment/upgrade/steps/01_preflight.sh"
LIVE_BASE = f"{REPO}/app/backend/arbicore/searcher/live_base.py"
RUNTIME = f"{REPO}/app/backend/arbicore/searcher/runtime.py"


def _read(p):
    with open(p) as f:
        return f.read()


# ── The variable names T2 actually consumes (source of truth) ──────────────
def test_t2_consumes_wss_url_base_primary_rpc_wss_fallback():
    txt = _read(LIVE_BASE)
    # primary-first, fallback-second — exact precedence the runtime uses
    assert ('os.environ.get("ARBICORE_WSS_URL_BASE") or '
            'os.environ.get("ARBICORE_RPC_WSS_BASE")') in txt
    assert 'ARBICORE_T2_SEARCHER_ENABLED' in _read(RUNTIME)


# ── 00_detect_env.sh wiring (reproducible, non-erasing) ────────────────────
def test_detect_env_wires_t2_flag_default_true_idempotently():
    txt = _read(DETECT_ENV)
    assert 'T2_FLAG="${ARBICORE_T2_SEARCHER_ENABLED:-true}"' in txt
    assert re.search(
        r"grep -q '\^ARBICORE_T2_SEARCHER_ENABLED=' \"\$BACKEND_ENV\" \\\s*\n\s*"
        r'\|\| echo "ARBICORE_T2_SEARCHER_ENABLED=\$\{T2_FLAG\}"', txt), \
        "T2 flag must be written idempotently (only if absent) — never overwrite OLD"


def test_detect_env_injects_wss_without_erasing_existing():
    txt = _read(DETECT_ENV)
    # WSS injected only when absent AND operator provided it (never fabricated)
    assert 'ARBICORE_WSS_URL_BASE=${ARBICORE_WSS_URL_BASE}' in txt
    assert 'ARBICORE_RPC_WSS_BASE=${ARBICORE_RPC_WSS_BASE}' in txt
    assert '! grep -q \'^ARBICORE_WSS_URL_BASE=\' "$BACKEND_ENV"' in txt
    # the OLD-var inherit regex already covers ARBICORE_* so an existing WSS is preserved
    assert "APP_PREFIX_RE='^(ARBICORE|MONGO|DB|JWT|VAULT|FEATURE)_'" in txt


def test_preflight_invokes_t2_gate():
    assert 'assert_t2_config_or_die "${ROOT_DIR}/backend/.env"' in _read(PREFLIGHT)


# ── Functional: exercise the REAL common.sh gate ───────────────────────────
def _run_gate(env_lines):
    """Source common.sh and call assert_t2_config_or_die against a temp env
    file built from env_lines. Returns the subprocess CompletedProcess."""
    import tempfile
    import os
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
        f.write("\n".join(env_lines) + "\n")
        envf = f.name
    try:
        script = f'source {COMMON}\nassert_t2_config_or_die "{envf}"\necho GATE_OK\n'
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    finally:
        os.unlink(envf)


def test_gate_passes_when_t2_enabled_with_wss_and_rpc():
    r = _run_gate([
        "ARBICORE_T2_SEARCHER_ENABLED=true",
        "ARBICORE_WSS_URL_BASE=wss://base-mainnet.example/v2/KEY",
        "ARBICORE_RPC_URL_BASE=https://base-mainnet.example/v2/KEY",
    ])
    assert r.returncode == 0 and "GATE_OK" in r.stdout, r.stderr


def test_gate_passes_with_rpc_wss_fallback():
    r = _run_gate([
        "ARBICORE_T2_SEARCHER_ENABLED=on",
        "ARBICORE_RPC_WSS_BASE=wss://base-mainnet.example/ws",
        "ARBICORE_RPC_URL_BASE=https://base-mainnet.example/rpc",
    ])
    assert r.returncode == 0 and "GATE_OK" in r.stdout, r.stderr


def test_gate_fails_closed_when_t2_enabled_but_wss_missing():
    r = _run_gate([
        "ARBICORE_T2_SEARCHER_ENABLED=true",
        "ARBICORE_RPC_URL_BASE=https://base-mainnet.example/rpc",
    ])
    assert r.returncode != 0, "gate must FAIL when T2 on but WSS missing"
    assert "no Base WSS configured" in (r.stdout + r.stderr)
    assert "GATE_OK" not in r.stdout


def test_gate_fails_closed_when_t2_enabled_but_rpc_missing():
    r = _run_gate([
        "ARBICORE_T2_SEARCHER_ENABLED=true",
        "ARBICORE_WSS_URL_BASE=wss://base-mainnet.example/ws",
    ])
    assert r.returncode != 0
    assert "no Base RPC" in (r.stdout + r.stderr)


def test_gate_noop_when_t2_disabled():
    for flag in ("false", "off", "0", ""):
        r = _run_gate([f"ARBICORE_T2_SEARCHER_ENABLED={flag}"])
        assert r.returncode == 0 and "GATE_OK" in r.stdout, (flag, r.stderr)
    # flag entirely absent → also a no-op (does not require WSS)
    r = _run_gate(["SOME_OTHER=1"])
    assert r.returncode == 0 and "GATE_OK" in r.stdout, r.stderr
