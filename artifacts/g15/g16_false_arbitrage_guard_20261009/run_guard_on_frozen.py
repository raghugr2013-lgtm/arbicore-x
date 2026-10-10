#!/usr/bin/env python3
"""Run G1.6 guard on the frozen Oct 8 winners export (read-only source)."""
from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from false_arbitrage_guard import apply_guard, load_jsonl

ROOT = Path(__file__).resolve().parent
FROZEN = ROOT.parent / "core-20261008T2216Z" / "G1_5_EXPORT_20261008T2216Z" / "MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    t0 = time.time()
    assert FROZEN.is_file(), f"missing frozen export: {FROZEN}"
    sha = file_sha256(FROZEN)
    rows = load_jsonl(str(FROZEN), chain="base")
    before = {
        "source": str(FROZEN),
        "source_sha256": sha,
        "base_rows": len(rows),
        "classification_counts": dict(Counter(r.get("classification") for r in rows)),
        "sum_searcher_kept_net_usd_known": sum(
            float(r["searcher_kept_net_usd"])
            for r in rows
            if r.get("searcher_kept_net_usd") is not None
        ),
        "rows_with_net": sum(1 for r in rows if r.get("searcher_kept_net_usd") is not None),
    }
    out = apply_guard(rows, block_window=3, amount_tolerance=0.05)
    # after: classifications unchanged; additive flags only
    after_cls = Counter(r["original_classification"] for r in out["results"])
    flagged = [r for r in out["results"] if r["guard_flag"] != "NO_FLAG"]
    sample = sorted(
        flagged,
        key=lambda r: (0 if r["guard_flag"] == "BOTH_FLAGS" else 1, -(r["original_net_usd"] or 0)),
    )[:25]
    report = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(time.time() - t0, 3),
        "before": before,
        "after": {
            "flag_counts": out["flag_counts"],
            "mirror_link_count": out["mirror_link_count"],
            "unique_mirror_pairs": out["unique_mirror_pairs"],
            "original_classification_counts": dict(after_cls),
            "classification_unchanged": dict(after_cls) == before["classification_counts"],
            "flagged_rows": len(flagged),
        },
        "params": out["params"],
        "sample_flagged": sample,
        "notes": [
            "Frozen source file was not modified.",
            "guard_flag is additive; original classification preserved.",
            "Flags are investigation signals, not automatic non-arbitrage verdicts.",
        ],
    }
    (OUT / "g16_before_after.json").write_text(json.dumps(report, indent=2) + "\n")
    # compact links for audit (may be large)
    (OUT / "g16_mirror_links.json").write_text(
        json.dumps(out["mirror_links"], indent=2) + "\n"
    )
    # per-tx flags only
    slim = [
        {
            "tx_hash": r["tx_hash"],
            "guard_flag": r["guard_flag"],
            "original_classification": r["original_classification"],
            "original_net_usd": r["original_net_usd"],
            "inferred_bundle_net_usd": r["inferred_bundle_net_usd"],
            "mirror_links": r["mirror_links"],
            "repeated_pools": r["repeated_pools"],
        }
        for r in out["results"]
        if r["guard_flag"] != "NO_FLAG"
    ]
    (OUT / "g16_flagged_rows.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in slim)
    )
    md = []
    md.append("# G1.6 frozen-data before/after\n")
    md.append(f"- Generated: `{report['generated_utc']}`")
    md.append(f"- Source: `{FROZEN.name}` sha256 `{sha}`")
    md.append(f"- Base rows: **{before['base_rows']}**")
    md.append(f"- Original classification counts: `{before['classification_counts']}`")
    md.append(f"- Classification unchanged after guard: **{report['after']['classification_unchanged']}**")
    md.append(f"- Flag counts: `{out['flag_counts']}`")
    md.append(f"- Unique mirror pairs: **{out['unique_mirror_pairs']}** (raw link rows {out['mirror_link_count']})")
    md.append(f"- Flagged rows: **{len(flagged)}**")
    md.append("\n## Sample flagged (up to 25)\n")
    md.append("| tx | flag | orig class | orig NET | bundle NET | peers |")
    md.append("|---|---|---|---|---|---|")
    for r in sample:
        peers = ",".join(x[:10] + "…" for x in r["mirror_links"][:2])
        md.append(
            f"| `{r['tx_hash'][:18]}…` | {r['guard_flag']} | {r['original_classification']} | "
            f"{r['original_net_usd']} | {r['inferred_bundle_net_usd']} | {peers} |"
        )
    md.append("\n## Verdict inputs\n")
    md.append("- Verified evidence: frozen export rows + original classification/NET columns.")
    md.append("- Inferred linkage: cross-tx reverse pool swaps within ±3 blocks at ≤5% amount tolerance; repeated pool within a route.")
    (OUT / "G1_6_FROZEN_BEFORE_AFTER.md").write_text("\n".join(md) + "\n")
    print(json.dumps(report["after"] | {"base_rows": before["base_rows"], "source_sha256": sha[:16]}, indent=2))


if __name__ == "__main__":
    main()
