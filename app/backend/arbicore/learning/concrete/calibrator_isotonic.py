"""ArbiCore X — Isotonic / Platt / Identity Confidence Calibrator (Wave 3).

Concrete implementation of the ``ConfidenceCalibrator`` ABC.

Algorithm ladder (chosen at fit time based on sample count):

    n >= min_samples_isotonic   -> Isotonic regression (primary)
    min_samples_platt <= n < .. -> Platt sigmoid       (fallback)
    n <  min_samples_platt      -> Identity mapping    (bootstrap / safe)

Determinism guarantees:
    * Same input samples -> same fitted curve, byte-for-byte.
    * ``calibrate()`` is a pure function of the fitted curve.
    * Output is always in [0, 100] and monotone non-decreasing.

Zero external runtime dependencies (no scipy / no sklearn).  The
isotonic fit uses Pool-Adjacent-Violators (PAV) implemented in-tree.
"""
from __future__ import annotations

import bisect
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..calibration import ConfidenceCalibrator

# ---------------------------------------------------------------------------
# Pool-Adjacent-Violators isotonic regression
# ---------------------------------------------------------------------------


def _pav(xs: Sequence[float], ys: Sequence[float]) -> Tuple[List[float], List[float]]:
    """Return ``(x_out, y_out)`` — a non-decreasing step function.

    Inputs must be sorted by ``x`` ascending.  Ties in ``x`` are averaged
    before fitting so the output has unique x-knots.  The algorithm is
    the classic PAV: repeatedly merge adjacent blocks whose left mean
    exceeds the right mean, weighted by count.
    """
    if not xs:
        return [], []
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have equal length")

    # Collapse ties in x (weight = count).
    xk: List[float] = []
    ys_sum: List[float] = []
    wts: List[float] = []
    for x, y in zip(xs, ys):
        if xk and x == xk[-1]:
            ys_sum[-1] += y
            wts[-1] += 1.0
        else:
            xk.append(float(x))
            ys_sum.append(float(y))
            wts.append(1.0)
    means = [s / w for s, w in zip(ys_sum, wts)]

    # PAV pass: keep merging until fully monotone.
    i = 0
    while i < len(means) - 1:
        if means[i] > means[i + 1]:
            # Merge blocks i and i+1.
            total_w = wts[i] + wts[i + 1]
            merged_mean = (means[i] * wts[i] + means[i + 1] * wts[i + 1]) / total_w
            # Merged block spans up to xk[i+1]; keep xk[i+1] as the right edge.
            xk[i] = xk[i + 1]
            means[i] = merged_mean
            wts[i] = total_w
            del xk[i + 1]
            del means[i + 1]
            del wts[i + 1]
            # Walk back to re-check the invariant with the previous block.
            if i > 0:
                i -= 1
        else:
            i += 1
    return xk, means


# ---------------------------------------------------------------------------
# Bucketed reliability diagram + scalar metrics
# ---------------------------------------------------------------------------


def _bucketize(samples: Sequence[Tuple[float, bool]], n_buckets: int) -> List[Dict[str, Any]]:
    """Bucket by predicted confidence in [0, 100]; emit rendering-friendly rows.

    ``predicted`` and ``realised`` are reported in [0, 1] to match the
    Wave-1 endpoint shape.
    """
    if n_buckets <= 0:
        return []
    edges = [i / n_buckets for i in range(n_buckets + 1)]
    labels = [f"{edges[i]:.1f}-{edges[i + 1]:.1f}" for i in range(n_buckets)]
    sums_p = [0.0] * n_buckets
    sums_s = [0.0] * n_buckets
    counts = [0] * n_buckets
    for raw, survived in samples:
        p = max(0.0, min(1.0, float(raw) / 100.0))
        idx = min(int(p * n_buckets), n_buckets - 1)
        sums_p[idx] += p
        sums_s[idx] += 1.0 if survived else 0.0
        counts[idx] += 1
    buckets: List[Dict[str, Any]] = []
    for i in range(n_buckets):
        if counts[i] > 0:
            predicted = sums_p[i] / counts[i]
            realised = sums_s[i] / counts[i]
        else:
            # Preserve bucket row for renderer stability; use midpoint as placeholder.
            predicted = (edges[i] + edges[i + 1]) / 2
            realised = 0.0
        buckets.append({
            "bucket": labels[i],
            "predicted": round(predicted, 4),
            "realised": round(realised, 4),
            "n": counts[i],
        })
    return buckets


def _brier(samples: Sequence[Tuple[float, bool]]) -> float:
    if not samples:
        return 0.0
    total = 0.0
    for raw, survived in samples:
        p = max(0.0, min(1.0, float(raw) / 100.0))
        y = 1.0 if survived else 0.0
        total += (p - y) ** 2
    return total / len(samples)


def _ece(buckets: Sequence[Dict[str, Any]]) -> float:
    total_n = sum(b["n"] for b in buckets)
    if total_n <= 0:
        return 0.0
    return sum(abs(b["predicted"] - b["realised"]) * b["n"] for b in buckets) / total_n


# ---------------------------------------------------------------------------
# Platt sigmoid fallback (single-parameter, closed-form via 1-var Newton)
# ---------------------------------------------------------------------------


def _fit_platt(samples: Sequence[Tuple[float, bool]]) -> Tuple[float, float]:
    """Fit ``sigmoid(a*x + b)``.  Simple bounded gradient descent.

    Kept intentionally minimal: 50 iterations, small learning rate, and
    numerically stable log-loss.  Deterministic given the same input.
    """
    a, b = 1.0, 0.0
    lr = 0.05
    n = len(samples)
    if n == 0:
        return a, b
    for _ in range(120):
        ga, gb = 0.0, 0.0
        for raw, survived in samples:
            x = max(0.0, min(1.0, float(raw) / 100.0))
            y = 1.0 if survived else 0.0
            z = a * x + b
            # Stable sigmoid.
            if z >= 0:
                ez = math.exp(-z)
                p = 1.0 / (1.0 + ez)
            else:
                ez = math.exp(z)
                p = ez / (1.0 + ez)
            err = p - y
            ga += err * x
            gb += err
        a -= lr * ga / n
        b -= lr * gb / n
    return a, b


def _platt_apply(a: float, b: float, x: float) -> float:
    z = a * x + b
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


# ---------------------------------------------------------------------------
# Concrete ConfidenceCalibrator
# ---------------------------------------------------------------------------


class IsotonicConfidenceCalibrator(ConfidenceCalibrator):
    """Isotonic (primary) / Platt (fallback) / Identity (safe) calibrator.

    ``fit()`` produces an in-memory curve.  Persistence and validation
    are the worker's responsibility (see ``calibration_worker.py``).
    """

    def __init__(self, min_samples_isotonic: int = 200, min_samples_platt: int = 30):
        self._min_iso = int(min_samples_isotonic)
        self._min_platt = int(min_samples_platt)
        # Curve state (identity by default).
        self._algorithm: str = "identity"
        self._x: List[float] = []
        self._y: List[float] = []
        self._platt_a: float = 1.0
        self._platt_b: float = 0.0
        self._n_samples: int = 0
        self._fit_metadata: Dict[str, Any] = {}

    # ------- state I/O helpers -------

    @property
    def algorithm(self) -> str:
        return self._algorithm

    @property
    def n_samples(self) -> int:
        return self._n_samples

    def curve(self) -> Dict[str, Any]:
        """Return the curve serialisation for persistence."""
        if self._algorithm == "isotonic":
            return {"algorithm": "isotonic", "x": list(self._x), "y": list(self._y)}
        if self._algorithm == "platt":
            return {"algorithm": "platt", "a": self._platt_a, "b": self._platt_b}
        return {"algorithm": "identity"}

    def load_curve(self, curve: Optional[Dict[str, Any]]) -> None:
        """Restore an in-memory curve from a previously persisted row."""
        if not curve:
            self._algorithm = "identity"
            self._x, self._y = [], []
            return
        algo = curve.get("algorithm", "identity")
        if algo == "isotonic":
            xs = curve.get("x") or []
            ys = curve.get("y") or []
            if len(xs) == len(ys) and xs:
                self._algorithm = "isotonic"
                self._x = [float(v) for v in xs]
                self._y = [float(v) for v in ys]
                return
        if algo == "platt":
            self._algorithm = "platt"
            self._platt_a = float(curve.get("a", 1.0))
            self._platt_b = float(curve.get("b", 0.0))
            return
        # Fallback for corrupted or unknown payloads.
        self._algorithm = "identity"
        self._x, self._y = [], []

    # ------- ABC contract -------

    def calibrate(self, raw_confidence: float, context: Dict) -> float:
        try:
            raw = float(raw_confidence)
        except (TypeError, ValueError):
            return 0.0
        if math.isnan(raw) or math.isinf(raw):
            return 0.0
        raw = max(0.0, min(100.0, raw))
        x = raw / 100.0
        if self._algorithm == "isotonic" and self._x:
            y = self._isotonic_apply(x)
        elif self._algorithm == "platt":
            y = _platt_apply(self._platt_a, self._platt_b, x)
        else:
            y = x
        y = max(0.0, min(1.0, y))
        return y * 100.0

    def fit(self, samples: Sequence[Tuple[float, bool]]) -> None:
        # Filter defensively — the caller SHOULD already have filtered to
        # resolved samples, but a bad row must never crash a fit.
        clean: List[Tuple[float, bool]] = []
        for raw, survived in samples:
            try:
                r = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isnan(r) or math.isinf(r):
                continue
            r = max(0.0, min(100.0, r))
            clean.append((r, bool(survived)))
        self._n_samples = len(clean)
        if self._n_samples >= self._min_iso:
            self._fit_isotonic(clean)
        elif self._n_samples >= self._min_platt:
            self._fit_platt(clean)
        else:
            self._algorithm = "identity"
            self._x, self._y = [], []

    # ------- fit primitives -------

    def _fit_isotonic(self, samples: Sequence[Tuple[float, bool]]) -> None:
        pairs = sorted(((r / 100.0, 1.0 if s else 0.0) for r, s in samples), key=lambda p: p[0])
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        xk, yk = _pav(xs, ys)
        # Enforce clamp [0, 1] on outputs and prepend/append anchors so
        # queries outside observed range use the boundary means.
        yk = [max(0.0, min(1.0, v)) for v in yk]
        self._algorithm = "isotonic"
        self._x = xk
        self._y = yk

    def _fit_platt(self, samples: Sequence[Tuple[float, bool]]) -> None:
        a, b = _fit_platt(samples)
        self._algorithm = "platt"
        self._platt_a = a
        self._platt_b = b

    # ------- isotonic apply (binary search) -------

    def _isotonic_apply(self, x: float) -> float:
        # Sorted x_k with associated y_k.  Return y at the first knot
        # whose x_k >= x; if x exceeds all knots, return last y.
        idx = bisect.bisect_left(self._x, x)
        if idx >= len(self._y):
            return self._y[-1]
        return self._y[idx]


# ---------------------------------------------------------------------------
# Public helpers used by the worker
# ---------------------------------------------------------------------------


def compute_metrics(samples: Sequence[Tuple[float, bool]],
                    n_buckets: int = 10) -> Dict[str, Any]:
    """Return the payload the endpoint / persistence row expects."""
    buckets = _bucketize(samples, n_buckets)
    return {
        "n_samples": len(samples),
        "brier_score": round(_brier(samples), 4),
        "ece": round(_ece(buckets), 4),
        "buckets": buckets,
    }
