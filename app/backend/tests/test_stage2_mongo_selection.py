"""STAGE 2 — deterministic Mongo-container selection preflight test.

Guards the exact production layout that broke 00_detect_env.sh: multiple Mongo
containers on one host. The pure bash selector `choose_mongo_container`
(deployment/upgrade/lib/common.sh) must deterministically pick the authoritative
ArbiCore Mongo without relying on "exactly one Mongo container", honour an
explicit override, and fail clearly only when genuinely ambiguous. Docker-free.
"""
import subprocess
import textwrap

COMMON = "/app/deployment/upgrade/lib/common.sh"

# The exact multi-Mongo layout reported on the VPS.
VPS_CANDIDATES = "arbicore-x-mongo\nfactory-mongo\nforeman-cert-mongo\nforeman-mongo"


def _choose(candidates, explicit="", default="arbicore-x-mongo"):
    """Source common.sh and invoke the pure selector; return (rc, chosen)."""
    script = textwrap.dedent(f"""
        source {COMMON}
        set +e
        out="$(choose_mongo_container "$1" "$2" "$3")"
        rc=$?
        printf '%s|%s' "$rc" "$out"
    """)
    p = subprocess.run(["bash", "-c", script, "_", candidates, explicit, default],
                       capture_output=True, text=True)
    rc_str, _, chosen = p.stdout.partition("|")
    return int(rc_str), chosen.strip()


def test_multi_mongo_picks_authoritative_default():
    rc, chosen = _choose(VPS_CANDIDATES)  # no explicit → default among candidates
    assert rc == 0
    assert chosen == "arbicore-x-mongo"


def test_explicit_override_wins_when_present():
    rc, chosen = _choose(VPS_CANDIDATES, explicit="factory-mongo")
    assert rc == 0
    assert chosen == "factory-mongo"


def test_explicit_override_not_present_is_error():
    rc, chosen = _choose(VPS_CANDIDATES, explicit="does-not-exist")
    assert rc == 2
    assert chosen == ""


def test_single_candidate_is_used():
    rc, chosen = _choose("only-mongo", default="arbicore-x-mongo")
    assert rc == 0
    assert chosen == "only-mongo"


def test_ambiguous_without_default_match_errors():
    rc, chosen = _choose("factory-mongo\nforeman-mongo", default="arbicore-x-mongo")
    assert rc == 3
    assert chosen == ""


def test_common_sh_defines_selector_and_validator():
    txt = open(COMMON).read()
    assert "choose_mongo_container()" in txt
    assert "validate_mongo_container()" in txt
    assert 'ARBICORE_DEFAULT_MONGO' in txt
