"""Proves the canonical verifier runs end-to-end in a FRESH Python process and
emits the required structured RESULT lines for every stage — even offline
(RPC calls fail closed; the script must not crash and must print all stages)."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # app/backend
SCRIPT = os.path.join(HERE, "verify_readiness.py")


def test_verifier_exists_and_is_shipped_at_backend_root():
    assert os.path.isfile(SCRIPT)


def test_verifier_runs_in_fresh_process_and_reports_every_stage():
    env = dict(os.environ)
    # Fail-fast, offline RPC so the process is quick and deterministic.
    env["PROVIDER_RPC_URLS_BASE"] = "http://127.0.0.1:1,http://127.0.0.1:2"
    env["ARBICORE_RPC_MAX_RETRIES"] = "0"
    env["ARBICORE_RPC_BACKOFF_BASE_MS"] = "1"
    env.pop("BASE_BALANCER_V2_VAULT", None)
    env.pop("ARBICORE_EXECUTOR_ADDRESS_BASE", None)

    proc = subprocess.run(
        [sys.executable, SCRIPT], cwd=HERE, env=env,
        capture_output=True, text=True, timeout=120,
    )
    out = proc.stdout
    assert proc.returncode == 0, f"rc={proc.returncode}\nSTDERR:\n{proc.stderr}\nOUT:\n{out}"
    # Every stage must emit exactly-prefixed structured lines.
    for stage in ("RESULT P0 ", "RESULT P1 ", "RESULT P2 ", "RESULT P3 "):
        assert stage in out, f"missing '{stage}' in:\n{out}"
    assert "VERIFY_DONE" in out
    # No result()-signature / kwarg-collision regressions.
    assert "got multiple values" not in out
    assert "RESULT P1 " in out
    # Offline provisioning-gated stages must be explicitly BLOCKED, not silent.
    assert "RESULT P2 BLOCKED" in out
    assert "RESULT P3 BLOCKED" in out
    # Never leak secrets.
    assert "127.0.0.1:1" not in out and "127.0.0.1:2" not in out
