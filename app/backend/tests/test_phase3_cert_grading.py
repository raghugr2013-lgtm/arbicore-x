"""Phase-3 — Shadow Certification grading honesty + infra-only readiness gating.

Regression for the false "executable_rate=0.0000 ≥ 0.1" pass reason on a zero-
volume (infrastructure-only) run, plus the fix that an infrastructure-only PASS
never satisfies the LIMITED_LIVE SHADOW_VALIDATION mandatory gate.

Deterministic; no Mongo, no network. Grades runs via ShadowCertificationEngine
._grade_run and drives the readiness gate with a tiny fake shadow repo.
"""
import asyncio

from arbicore.certification.engine import ShadowCertificationEngine
from arbicore.certification.models import (
    ShadowCertificationRun, ShadowCertificationCycle)
from arbicore.certification.thresholds import (
    CertificationThresholds, CertificationStatus, CycleStatus)
from arbicore.control.readiness import ExecutionReadinessEngine, GREEN, YELLOW


def _engine(th=None):
    return ShadowCertificationEngine(cert_repo=None, evidence_repo=None,
                                     thresholds=th or CertificationThresholds())


def _cycle(i, *, processed, executable, status=CycleStatus.PASS):
    return ShadowCertificationCycle(
        cycle_id=f"c{i}", cycle_index=i, started_at="t", completed_at="t",
        duration_ms=1.0, opportunities_seen=processed,
        opportunities_processed=processed, executable_count=executable,
        stage_p95_ms={"discovery": 1.0}, infra_health={"mongo_ok": True, "runner_ok": True},
        runner_exceptions=0, cycle_status=status.value,
        flags=(["low_volume"] if processed == 0 else []))


def _run(th, cycles, *, start_markers=None):
    run = ShadowCertificationRun.start(thresholds=th)
    for c in cycles:
        run = run.with_cycle(c)
    if start_markers is not None:
        run = ShadowCertificationRun(
            run_id=run.run_id, started_at=run.started_at, completed_at=None,
            status=run.status, target_cycles=run.target_cycles,
            thresholds=run.thresholds, cycles=list(run.cycles),
            summary={"start_markers": start_markers})
    return run


def _no_false_ge(pass_reasons):
    """No pass reason may claim 'X ≥ Y' unless float(X) >= float(Y)."""
    import re
    for r in pass_reasons:
        m = re.search(r"=\s*([0-9.]+)\s*≥\s*([0-9.]+)", r)
        if m:
            assert float(m.group(1)) >= float(m.group(2)), f"false claim: {r}"


# ── infrastructure-only (p=0) ──
def test_infra_only_zero_volume_is_distinct_status_no_false_claim():
    th = CertificationThresholds()  # target_cycles=20
    eng = _engine(th)
    run = _run(th, [_cycle(i, processed=0, executable=0) for i in range(20)])
    status, summary, pass_r, warn_r, fail_r = eng._grade_run(run)
    assert status == CertificationStatus.PASS_INFRASTRUCTURE_ONLY
    assert summary["infrastructure_only"] is True
    assert summary["executable_rate_evaluated"] is False
    # the historical bug: must NOT assert executable_rate ≥ threshold
    assert not any("≥" in r and "executable_rate=" in r for r in pass_r)
    assert any("not evaluated" in r for r in pass_r)
    _no_false_ge(pass_r)


def test_infra_only_preserves_start_markers_through_grading():
    th = CertificationThresholds()
    eng = _engine(th)
    run = _run(th, [_cycle(i, processed=0, executable=0) for i in range(20)],
               start_markers={"infrastructure_only": True, "readiness_at_start": {}})
    _, summary, _, _, _ = eng._grade_run(run)
    assert summary.get("start_markers", {}).get("infrastructure_only") is True


# ── evaluable runs (p>0) ──
def test_below_warn_threshold_fails():
    th = CertificationThresholds()
    eng = _engine(th)
    # processed all in one cycle; exec_rate 0.02 < warn 0.05
    cycles = [_cycle(0, processed=100, executable=2)] + \
             [_cycle(i, processed=0, executable=0) for i in range(1, 20)]
    status, _, _, _, fail_r = eng._grade_run(_run(th, cycles))
    assert status == CertificationStatus.FAIL
    assert any("warn threshold" in r for r in fail_r)


def test_warning_range_is_warning():
    th = CertificationThresholds()
    eng = _engine(th)
    # exec_rate 0.07 → between warn(0.05) and pass(0.10)
    cycles = [_cycle(0, processed=100, executable=7)] + \
             [_cycle(i, processed=0, executable=0) for i in range(1, 20)]
    status, _, _, warn_r, _ = eng._grade_run(_run(th, cycles))
    assert status == CertificationStatus.WARNING
    assert any("pass threshold" in r for r in warn_r)


def test_threshold_met_is_pass_with_true_claim():
    th = CertificationThresholds()
    eng = _engine(th)
    # exec_rate 0.20 ≥ pass 0.10
    cycles = [_cycle(0, processed=100, executable=20)] + \
             [_cycle(i, processed=0, executable=0) for i in range(1, 20)]
    status, summary, pass_r, _, _ = eng._grade_run(_run(th, cycles))
    assert status == CertificationStatus.PASS
    assert summary["executable_rate_evaluated"] is True
    assert any("executable_rate=0.2000 ≥ 0.1" in r for r in pass_r)
    _no_false_ge(pass_r)


# ── readiness gate: infra-only PASS must NOT satisfy SHADOW_VALIDATION ──
class _FakeRun:
    def __init__(self, status, summary):
        self.status = status
        self.summary = summary
        self.cycles = [object()] * 20
        self.target_cycles = 20


class _FakeShadowRepo:
    def __init__(self, latest):
        self._latest = latest
    async def current_running(self):
        return None
    async def list_recent(self, limit=1):
        return [self._latest] if self._latest else []


def _shadow_check(latest_run):
    eng = ExecutionReadinessEngine(shadow_cert_repo=_FakeShadowRepo(latest_run))
    return asyncio.get_event_loop().run_until_complete(eng._shadow_validation())


def test_infra_only_pass_does_not_green_shadow_validation():
    r = _FakeRun("PASS_INFRASTRUCTURE_ONLY", {"infrastructure_only": True})
    chk = _shadow_check(r)
    assert chk["status"] == YELLOW
    assert any("INFRASTRUCTURE-ONLY" in w for w in chk["warnings"])


def test_infra_only_via_start_markers_does_not_green():
    r = _FakeRun("PASS", {"start_markers": {"infrastructure_only": True}})
    chk = _shadow_check(r)
    assert chk["status"] == YELLOW


def test_real_executable_pass_greens_shadow_validation():
    r = _FakeRun("PASS", {"infrastructure_only": False, "executable_rate": 0.2})
    chk = _shadow_check(r)
    assert chk["status"] == GREEN


def test_limited_live_stays_red_on_infra_only_pass():
    """Even with an infra-only shadow PASS, LIMITED_LIVE must remain RED / non-activatable."""
    eng = ExecutionReadinessEngine(
        shadow_cert_repo=_FakeShadowRepo(
            _FakeRun("PASS_INFRASTRUCTURE_ONLY", {"infrastructure_only": True})))
    report = asyncio.get_event_loop().run_until_complete(eng.evaluate())
    ll = report["modes"]["LIMITED_LIVE"]
    assert ll["status"] == "RED" and ll["can_activate"] is False
    fa = report["modes"]["FULL_AUTOMATION"]
    assert fa["status"] == "RED" and fa["can_activate"] is False


def test_infra_only_pass_not_paper_validation_and_no_auto_confirm():
    """Infra-only shadow certification is not paper evidence and enables nothing.
    PAPER_VALIDATION is driven by paper evidence bundles, not shadow status."""
    eng = ExecutionReadinessEngine(
        shadow_cert_repo=_FakeShadowRepo(
            _FakeRun("PASS_INFRASTRUCTURE_ONLY", {"infrastructure_only": True})),
        paper_evidence_repo=None)  # no paper evidence
    report = asyncio.get_event_loop().run_until_complete(eng.evaluate())
    paper = next(c for c in report["components"] if c["name"] == "PAPER_VALIDATION")
    assert paper["status"] != GREEN            # infra-only shadow ≠ paper evidence
    # and no live-capable mode is auto-activatable
    assert report["modes"]["LIMITED_LIVE"]["can_activate"] is False
