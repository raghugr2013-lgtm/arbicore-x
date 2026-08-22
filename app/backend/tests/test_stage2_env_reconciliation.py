"""STAGE 2 — MONGO_URL host reconciliation + writable state-dir preflight tests.

Guards:
  * the generated MONGO_URL host is swapped to the SELECTED authoritative Mongo
    container (fixes 'selected arbicore-x-mongo but URL points at factory-mongo')
    while preserving scheme/credentials/port/path/query;
  * BACKUP_DIR/LOG_DIR default to a user-writable location (not root-only /opt),
    so the intended deploy user can run the procedure without permission errors.
Docker-free / deterministic.
"""
import subprocess
import textwrap

COMMON = "/app/deployment/upgrade/lib/common.sh"


def _call(func_and_args):
    script = textwrap.dedent(f"""
        source {COMMON}
        set +e
        {func_and_args}
    """)
    p = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return p.stdout.strip(), p.stderr.strip(), p.returncode


def test_rewrite_host_preserves_credentials_and_query():
    out, _, rc = _call(
        'rewrite_mongo_host '
        '"mongodb://user:pass@factory-mongo:27017/?authSource=admin" '
        '"arbicore-x-mongo"')
    assert rc == 0
    assert out == "mongodb://user:pass@arbicore-x-mongo:27017/?authSource=admin"


def test_rewrite_host_no_creds_no_query():
    out, _, _ = _call('rewrite_mongo_host "mongodb://factory-mongo:27017" "arbicore-x-mongo"')
    assert out == "mongodb://arbicore-x-mongo:27017"


def test_rewrite_host_with_path_db():
    out, _, _ = _call(
        'rewrite_mongo_host "mongodb://u:p@factory-mongo:27017/arbicore_x?authSource=admin" '
        '"arbicore-x-mongo"')
    assert out == "mongodb://u:p@arbicore-x-mongo:27017/arbicore_x?authSource=admin"


def test_mongo_url_host_extraction():
    out, _, _ = _call('mongo_url_host "mongodb://user:pass@factory-mongo:27017/?authSource=admin"')
    assert out == "factory-mongo"
    out2, _, _ = _call('mongo_url_host "mongodb://arbicore-x-mongo:27017"')
    assert out2 == "arbicore-x-mongo"


def test_reconciled_url_host_matches_selected_container():
    # simulate the 00_detect_env reconciliation branch
    out, _, _ = _call(
        'MONGO_CONTAINER=arbicore-x-mongo; '
        'OLD="mongodb://user:pass@factory-mongo:27017/?authSource=admin"; '
        'NEW="$(rewrite_mongo_host "$OLD" "$MONGO_CONTAINER")"; '
        'printf "%s" "$(mongo_url_host "$NEW")"')
    assert out == "arbicore-x-mongo"


def test_state_dirs_default_user_writable_not_opt():
    # BACKUP_DIR/LOG_DIR must default under the repo (ROOT_DIR/.state), not /opt.
    out, _, _ = _call('printf "%s|%s|%s" "$ROOT_DIR" "$BACKUP_DIR" "$LOG_DIR"')
    root, backup, logs = out.split("|")
    assert not backup.startswith("/opt/arbicore-x"), backup
    assert not logs.startswith("/opt/arbicore-x"), logs
    assert backup.startswith(root), (root, backup)
    assert logs.startswith(root), (root, logs)


def test_state_dirs_respect_explicit_override():
    script = textwrap.dedent(f"""
        source {COMMON}
        printf '%s|%s' "$BACKUP_DIR" "$LOG_DIR"
    """)
    p = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin",
             "BACKUP_DIR": "/opt/arbicore-x/backups",
             "LOG_DIR": "/opt/arbicore-x/logs"},
    )
    assert p.stdout.strip() == "/opt/arbicore-x/backups|/opt/arbicore-x/logs", p.stdout
