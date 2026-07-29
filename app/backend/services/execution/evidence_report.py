"""Final Evidence Report — bundles Fee Provenance + Fresh-Cycle Analytics +
Survivability + Fresh-Cycle Watch into a single READ-ONLY package and renders
Markdown for download.

This is the artifact that answers the core operator question:

    "How often does a real executable fresh-cycle opportunity actually occur?"

with evidence — alongside the assumption-level transparency of every fee that
enters the ROI math. No execution, no fund movement.
"""
from core.models import now_iso
from services.execution import fee_provenance, fresh_cycle_analytics, fresh_cycle_watch


def _fmt(v, suffix=""):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return f"{v}{suffix}"


def _fee_table_md(fees: list) -> str:
    out = [
        "| # | Fee | Value | Classification | Source | Refresh | Confidence | Grade |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, f in enumerate(fees, 1):
        out.append(
            "| {i} | {name} | `{val}` | {cls} | {src} | {refresh} | {conf} | **{rec}** |".format(
                i=i, name=f["name"], val=_fmt(f.get("current_value")),
                cls=f.get("classification", "—"),
                src=(f.get("source") or "—").replace("|", "/"),
                refresh=f.get("refresh_frequency", "—"),
                conf=f.get("confidence", "—"),
                rec=f.get("recommendation", "—"),
            )
        )
    return "\n".join(out)


def fee_provenance_md(pkg: dict) -> str:
    s = pkg.get("summary", {})
    rec = s.get("recommendation_counts", {})
    md = [
        "# Fee Provenance Report",
        f"_Generated: {pkg.get('generated_at')}_",
        "",
        "## Summary",
        f"- Total fees inspected: **{s.get('total_fees', 0)}**",
        f"- Live / measured fees: **{s.get('real_count', 0)}**",
        f"- Static / assumed fees: **{s.get('assumed_count', 0)}**",
        f"- Production Grade: **{rec.get('Production Grade', 0)}**, "
        f"Needs Verification: **{rec.get('Needs Verification', 0)}**, "
        f"Assumption Only: **{rec.get('Assumption Only', 0)}**",
        "",
        "## Trust Verdict",
        f"> {pkg.get('trust_verdict', '—')}",
        "",
        "## Fee Inventory",
        _fee_table_md(pkg.get("fees", [])),
        "",
        "### Consumers per fee",
    ]
    for f in pkg.get("fees", []):
        md.append(f"- **{f['name']}** → {', '.join(f.get('consumers', []) or ['—'])}")
        if f.get("note"):
            md.append(f"  - _{f['note']}_")
    md += ["", f"_{pkg.get('note', '')}_"]
    return "\n".join(md)


def fresh_cycle_md(pkg: dict, days: int) -> str:
    s = pkg.get("statistics", {})
    sv = pkg.get("survivability", {})
    ev = pkg.get("evidence", {})
    ans = ev.get("answer") or {}
    ow = pkg.get("observation_window") or ev.get("observation_window") or {}
    formal = ev.get("formal_recommendation") or {}
    tg = ow.get("target") or {}
    pg = ow.get("progress") or {}
    trig = ow.get("triggers") or {}
    md = [
        f"# Fresh-Cycle Opportunity Analytics ({days}d window)",
        f"_Generated: {now_iso()}_",
        "",
        "## Observation Window (data-collection mode)",
        f"- **Observation start:** `{ow.get('observation_start_time') or '—'}`",
        f"- **Last observation:** `{ow.get('last_observation_at') or '—'}`",
        f"- **Duration:** **{_fmt(ow.get('observation_duration_days'), 'd')}** "
        f"({_fmt(ow.get('observation_duration_seconds'), 's')})",
        f"- **Observation count:** **{_fmt(ow.get('observation_count'))}**",
        f"- **Target window:** any of → "
        f"({tg.get('days', '—')} days) OR ({tg.get('observations', '—'):,} observations) OR "
        f"(≥{tg.get('significant_go_windows', '—')} closed GO windows / ≥{tg.get('significant_pct_above_floor', '—')}% time above floor)"
        if tg else "- **Target window:** —",
        f"- **Progress:** {_fmt(pg.get('days_pct'), '%')} of days · "
        f"{_fmt(pg.get('observations_pct'), '%')} of observations · "
        f"{_fmt(pg.get('go_windows_pct'), '%')} of GO-window evidence",
        f"- **Triggers fired:** days={_fmt(trig.get('days'))}, observations={_fmt(trig.get('observations'))}, "
        f"statistically_significant={_fmt(trig.get('statistically_significant'))}",
        f"- **Ready for first formal review:** **{_fmt(ow.get('ready_for_first_formal_review'))}**"
        + (f" — {ow.get('review_trigger_satisfied')}" if ow.get("review_trigger_satisfied") else ""),
        "",
        "## Core Evidence Question",
        f"> **{ev.get('question', '—')}**",
        f"> **Verdict: `{ev.get('frequency_verdict', '—')}`**",
        f"> {ev.get('automation_recommendation', '—')}",
        "",
        "## Formal Recommendation (4-level)",
        f"- **Level:** **`{formal.get('level', '—')}`**",
        f"- **Rationale:** {formal.get('rationale', '—')}",
        f"- **Ready for formal review:** {_fmt(formal.get('ready_for_formal_review'))}",
        "",
        "## Statistics",
        f"- Observations: **{s.get('observations', 0)}**  "
        f"(span {s.get('observation_span_hours', 0)}h)",
        f"- % time ROI positive: **{_fmt(s.get('pct_time_roi_positive'), '%')}**",
        f"- % time ROI ≥ floor ({s.get('floor_pct', '—')}%): "
        f"**{_fmt(s.get('pct_time_roi_above_floor'), '%')}**",
        f"- % time GO: **{_fmt(s.get('pct_time_go'), '%')}**",
        f"- Average positive ROI: **{_fmt(s.get('avg_positive_roi_pct'), '%')}**",
        f"- Maximum ROI: **{_fmt(s.get('max_roi_pct'), '%')}**",
        f"- GO windows total: **{s.get('go_windows_total', 0)}**",
        f"- GO windows / day: **{_fmt(s.get('go_windows_per_day'))}**, "
        f"per week: **{_fmt(s.get('go_windows_per_week'))}**",
        f"- Longest GO window: **{_fmt(s.get('longest_go_window_s'), 's')}**, "
        f"avg: **{_fmt(s.get('avg_go_window_s'), 's')}**",
        f"- Avg max safe buy in GO windows: **${_fmt(s.get('avg_max_safe_buy_usd_in_go_windows'))}**",
        "",
        "## Survivability — GO windows",
    ]
    wins = sv.get("windows", []) or []
    if not wins:
        md.append("_No GO windows recorded in the sample window._")
    else:
        md += [
            "| Start | End | Duration (s) | Peak ROI % | Avg ROI % | Max Safe Buy $ | Venue | Samples | Status |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for w in wins[:50]:
            md.append(
                "| {s} | {e} | {d} | {p} | {a} | {sz} | {v} | {n} | {st} |".format(
                    s=w.get("start_time") or "—", e=w.get("end_time") or "—",
                    d=_fmt(w.get("duration_s")), p=_fmt(w.get("peak_roi_pct")),
                    a=_fmt(w.get("avg_roi_pct")), sz=_fmt(w.get("max_safe_buy_usd")),
                    v=(w.get("venue") or "—").upper(),
                    n=w.get("samples"), st=w.get("status", "—"),
                )
            )
    md += ["", "## Headline Answer"]
    for k, label in [
        ("observations", "Observations"),
        ("observation_span_hours", "Observation span (h)"),
        ("pct_time_fresh_roi_positive", "% time fresh ROI > 0"),
        ("pct_time_fresh_roi_above_floor", "% time fresh ROI ≥ floor"),
        ("pct_time_go", "% time GO"),
        ("avg_positive_roi_pct", "Avg positive ROI %"),
        ("max_roi_pct", "Max ROI %"),
        ("go_windows_total", "GO windows total"),
        ("go_windows_per_day", "GO windows / day"),
        ("go_windows_per_week", "GO windows / week"),
        ("avg_go_window_s", "Avg GO window (s)"),
        ("longest_go_window_s", "Longest GO window (s)"),
    ]:
        md.append(f"- **{label}:** {_fmt(ans.get(k))}")
    md += ["", f"_{ev.get('note', '')}_"]
    return "\n".join(md)


def watch_md(w: dict) -> str:
    md = [
        "# Fresh-Cycle Watch",
        f"_Generated: {w.get('generated_at')}_",
        "",
        f"**Credential state:** `{w.get('credential_state')}` — {w.get('credential_state_label')}",
        f"- Bot token set: **{_fmt(w.get('token_set'))}** ({w.get('token_mask') or '—'})",
        f"- Chat ID set: **{_fmt(w.get('chat_id_set'))}**",
        f"- Alerts enabled flag: **{_fmt(w.get('alerts_enabled'))}**",
        "",
        "## Alert kinds the watcher will fire when armed",
        "| Kind | Label | Trigger | Enabled |",
        "|---|---|---|---|",
    ]
    for k in w.get("alert_kinds", []):
        md.append(
            "| `{k}` | {l} | {t} | {e} |".format(
                k=k["key"], l=k["label"], t=k["trigger"], e=_fmt(k.get("enabled")),
            )
        )
    md += ["", f"_{w.get('note', '')}_"]
    return "\n".join(md)


async def build(days: int = 30) -> dict:
    fees = await fee_provenance.build()
    fresh = await fresh_cycle_analytics.analytics(days)
    watch = await fresh_cycle_watch.status()
    return {
        "phase": "Final Evidence Report (read-only)",
        "generated_at": now_iso(),
        "window_days": days,
        "fee_provenance": fees,
        "fresh_cycle": fresh,
        "fresh_cycle_watch": watch,
        "executive_summary": {
            "fees_real_count": fees.get("summary", {}).get("real_count"),
            "fees_assumed_count": fees.get("summary", {}).get("assumed_count"),
            "fresh_cycle_frequency_verdict": fresh.get("evidence", {}).get("frequency_verdict"),
            "fresh_cycle_recommendation": fresh.get("evidence", {}).get("automation_recommendation"),
            "watch_state": watch.get("credential_state"),
        },
        "note": "Bundle of all three read-only reports. No execution, no fund movement. E5 stays BLOCKED.",
    }


def to_markdown(pkg: dict) -> str:
    es = pkg.get("executive_summary", {})
    days = pkg.get("window_days", 30)
    md = [
        "# ArbiCore — Final Evidence Report",
        f"_Generated: {pkg.get('generated_at')}_",
        "",
        "**Scope:** Fee Provenance + Fresh-Cycle Opportunity Analytics + Survivability + "
        "Fresh-Cycle Watch. **READ-ONLY** — no execution, no wallets, no API keys, no fund movement. "
        "E5 stays BLOCKED.",
        "",
        "## Executive Summary",
        f"- Fees classified as real / measured: **{_fmt(es.get('fees_real_count'))}**",
        f"- Fees classified as static / assumed: **{_fmt(es.get('fees_assumed_count'))}**",
        f"- Fresh-cycle opportunity frequency verdict: **`{es.get('fresh_cycle_frequency_verdict', '—')}`**",
        f"- Watcher state: **`{es.get('watch_state', '—')}`**",
        "",
        f"> **Automation recommendation:** {es.get('fresh_cycle_recommendation', '—')}",
        "",
        "---",
        "",
        fee_provenance_md(pkg.get("fee_provenance", {})),
        "",
        "---",
        "",
        fresh_cycle_md(pkg.get("fresh_cycle", {}), days),
        "",
        "---",
        "",
        watch_md(pkg.get("fresh_cycle_watch", {})),
        "",
        "---",
        "",
        f"_{pkg.get('note', '')}_",
    ]
    return "\n".join(md)
