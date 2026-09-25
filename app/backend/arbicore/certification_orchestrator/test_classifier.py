"""Deterministic test-result classifier.

Consumes raw test outcomes (test node-id -> passed/failed) + the committed
certification manifest, and classifies each FAILURE into one of the manifest
categories. A failure NOT covered by the manifest defaults to GENUINE_FAILURE
(fail-closed: an unexpected red is treated as real, never hand-waved).

The engine uses ``genuine_failures`` (from ``summarize``) as the ONLY count that
can turn G1 red — env-gated / stale / unavailable / deprecated outcomes are
surfaced transparently but do not masquerade as passes, nor block on infra we
intentionally don't run here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

_MANIFEST_PATH = Path(__file__).with_name("certification_manifest.json")

# Categories that are NOT genuine system defects.
_NON_GENUINE = {"STALE_EXPECTATION", "ENV_GATED", "UNAVAILABLE_DEPENDENCY", "DEPRECATED_PATH"}


def load_manifest(path: Path = None) -> Dict[str, Any]:
    p = Path(os.environ.get("ARBICORE_CERT_MANIFEST_PATH") or path or _MANIFEST_PATH)
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {"schema": "arbicore.certification_manifest/1.0", "tests": {}}


def _match(node_id: str, manifest_tests: Dict[str, Any]) -> Dict[str, Any]:
    if node_id in manifest_tests:
        return manifest_tests[node_id]
    # File-level fallback: 'tests/x.py::test_y' -> 'tests/x.py'
    file_part = node_id.split("::", 1)[0]
    if file_part in manifest_tests:
        return manifest_tests[file_part]
    return {}


def classify_failures(failed_node_ids: List[str], manifest: Dict[str, Any] = None) -> Dict[str, Any]:
    manifest = manifest or load_manifest()
    tests = manifest.get("tests", {})
    classified: List[Dict[str, str]] = []
    for nid in failed_node_ids:
        entry = _match(nid, tests)
        category = entry.get("category", "GENUINE_FAILURE")
        classified.append({
            "test": nid,
            "category": category,
            "reason": entry.get("reason", "not in manifest — defaulted to GENUINE_FAILURE (fail-closed)"),
            "recommended_disposition": entry.get("recommended_disposition", "investigate"),
            "genuine": category not in _NON_GENUINE,
        })
    return {
        "classified": classified,
        "counts": _counts(classified),
        "genuine_failures": sum(1 for c in classified if c["genuine"]),
    }


def _counts(classified: List[Dict[str, str]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in classified:
        out[c["category"]] = out.get(c["category"], 0) + 1
    return out


def summarize(*, passed: int, failed_node_ids: List[str],
              manifest: Dict[str, Any] = None) -> Dict[str, Any]:
    """Produce the ``tests`` evidence namespace for the gate engine."""
    cls = classify_failures(failed_node_ids, manifest)
    return {
        "passed": passed,
        "failed_total": len(failed_node_ids),
        "genuine_failures": cls["genuine_failures"],
        "category_counts": cls["counts"],
        "classified": cls["classified"],
    }


__all__ = ["load_manifest", "classify_failures", "summarize"]
