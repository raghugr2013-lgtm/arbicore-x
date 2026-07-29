"""TimeWindowClusterDetector — ±5min co-occurrence cluster strategy.

PARTIAL HARVEST of `archive/backend/intel/clusters.py` per
LEGACY_ARCHIVE_IMPORT_ASSESSMENT §2.2.2 (only the time-window strategy;
the persistent K-hop funding-source detector is covered by Phase C Wave 4
``EntityClusterDetector``).

Pure-compute, async-friendly, side-effect-free. Returns a list of cluster
dicts the LaunchArbitrageScanner (D-4.5) feeds into Wave-4 EntityResolver
for entity reconciliation.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from typing import Dict, Iterable, List


def _cluster_id(*parts: str) -> str:
    h = hashlib.md5(":".join(parts).encode()).hexdigest()[:14]
    return f"cluster-{h}"


class TimeWindowClusterDetector:
    """Wallets that buy the same token within ±window form a transient cluster."""

    def __init__(self, *,
                 window_seconds: int = 300,
                 min_cluster_size: int = 3) -> None:
        self.window_seconds = window_seconds
        self.min_cluster_size = min_cluster_size

    def detect(self, activity: Iterable[Dict]) -> List[Dict]:
        """``activity`` items require: wallet, token_id, timestamp, action.
        Only ``action == "buy"`` events contribute.
        """
        by_token: Dict[str, List[Dict]] = defaultdict(list)
        for a in activity:
            if a.get("action") != "buy":
                continue
            tid = a.get("token_id")
            if not tid:
                continue
            by_token[tid].append(a)

        now = int(time.time())
        out: List[Dict] = []
        for tid, events in by_token.items():
            events.sort(key=lambda e: e["timestamp"])
            i = 0
            n = len(events)
            while i < n:
                j = i
                window_start = events[i]["timestamp"]
                window_wallets = set()
                while (j < n
                       and events[j]["timestamp"] - window_start
                       <= self.window_seconds):
                    window_wallets.add(events[j]["wallet"])
                    j += 1
                if len(window_wallets) >= self.min_cluster_size:
                    wallet_list = sorted(window_wallets)
                    cid = _cluster_id("tw", tid, str(window_start))
                    out.append({
                        "id": cid,
                        "type": "time_window",
                        "wallets": wallet_list,
                        "tokens_touched": [tid],
                        "first_co_event": window_start,
                        "last_co_event": events[j - 1]["timestamp"],
                        "cohesion_score": min(
                            100, 30 + len(wallet_list) * 8
                        ),
                        "label": None,
                        "computed_at": now,
                    })
                i = j if j > i else i + 1
        return out

    def membership_index(self, clusters: List[Dict]) -> Dict[str, str]:
        """Return ``{wallet -> cluster_id}`` (latest cluster wins per wallet)."""
        out: Dict[str, str] = {}
        for c in clusters:
            for w in c.get("wallets", []):
                out[w] = c["id"]
        return out
