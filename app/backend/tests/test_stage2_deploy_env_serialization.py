"""STAGE 2 — deploy.env shell-safe serialization tests.

Guards the blocker where sourcing deploy.env executed a MONGO_MOUNTS value like
`volume:/x/_data->/data/configdb; volume:/y/_data->/data/db;` as shell (the `;`
split it into commands → "/data/configdb: No such file or directory"). The
env_kv serializer must make such values inert AND preserve them exactly.
"""
import subprocess
import textwrap

COMMON = "/app/deployment/upgrade/lib/common.sh"

MULTI_MOUNT = ("volume:/var/lib/docker/volumes/a/_data->/data/configdb; "
               "volume:/var/lib/docker/volumes/b/_data->/data/db; ")


def _source_and_get(serialized_line, key):
    """Write a serialized env line to a temp file, source it, echo the key."""
    script = textwrap.dedent(f"""
        source {COMMON}
        f="$(mktemp)"
        {serialized_line} > "$f"
        set -a; source "$f"; set +a
        printf '%s' "${{{key}}}"
        rm -f "$f"
    """)
    p = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    return p.stdout, p.stderr, p.returncode


def test_env_kv_multi_mount_is_sourced_inertly_and_preserved():
    out, err, rc = _source_and_get(
        f'env_kv MONGO_MOUNTS "{MULTI_MOUNT}"', "MONGO_MOUNTS")
    assert rc == 0, err
    # exact preservation (incl. semicolons, '->', paths, trailing space)
    assert out == MULTI_MOUNT, repr(out)
    # the path must NOT have been executed as a command
    assert "No such file or directory" not in err
    assert "/data/configdb" not in err


def test_env_kv_line_format_is_single_quoted():
    p = subprocess.run(
        ["bash", "-c", f'source {COMMON}; env_kv MONGO_MOUNTS "{MULTI_MOUNT}"'],
        capture_output=True, text=True)
    line = p.stdout.strip()
    assert line.startswith("MONGO_MOUNTS='")
    assert line.endswith("'")


def test_env_kv_preserves_embedded_single_quote():
    val = "path/with'quote->/data/db;"
    out, err, rc = _source_and_get(f"env_kv WEIRD \"{val}\"", "WEIRD")
    assert rc == 0, err
    assert out == val, repr(out)


def test_detect_env_uses_env_kv_not_raw_heredoc_for_deploy_env():
    txt = open("/app/deployment/upgrade/steps/00_detect_env.sh").read()
    # deploy.env must be built via env_kv (shell-safe), not a raw ${VAR} heredoc
    assert "env_kv MONGO_MOUNTS" in txt
    assert "MONGO_MOUNTS=${MONGO_MOUNTS}" not in txt
