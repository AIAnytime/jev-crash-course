"""Calibration maths: does a stated confidence of 0.9 actually come true 90%
of the time?"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Bin:
    lo: float
    hi: float
    n: int
    mean_confidence: float
    accuracy: float


def reliability(pairs: list[tuple[float, bool]], n_bins: int = 10) -> list[Bin]:
    """pairs: (stated confidence, was the answer correct)."""
    bins: list[Bin] = []
    for i in range(n_bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        in_bin = [
            (c, ok) for c, ok in pairs
            if (lo <= c < hi) or (i == n_bins - 1 and c == 1.0)
        ]
        if not in_bin:
            bins.append(Bin(lo, hi, 0, 0.0, 0.0))
            continue
        bins.append(
            Bin(
                lo=lo, hi=hi, n=len(in_bin),
                mean_confidence=sum(c for c, _ in in_bin) / len(in_bin),
                accuracy=sum(1 for _, ok in in_bin if ok) / len(in_bin),
            )
        )
    return bins


def ece(pairs: list[tuple[float, bool]], n_bins: int = 10) -> float:
    """Expected Calibration Error -- mean |confidence - accuracy|, weighted by
    bin population. Lower is better; 0 is perfect."""
    if not pairs:
        return float("nan")
    total = len(pairs)
    return sum(
        b.n / total * abs(b.mean_confidence - b.accuracy)
        for b in reliability(pairs, n_bins) if b.n
    )


def brier(pairs: list[tuple[float, bool]]) -> float:
    """Brier score -- mean squared error of the probability itself."""
    if not pairs:
        return float("nan")
    return sum((c - (1.0 if ok else 0.0)) ** 2 for c, ok in pairs) / len(pairs)


def accuracy(pairs: list[tuple[float, bool]]) -> float:
    if not pairs:
        return float("nan")
    return sum(1 for _, ok in pairs if ok) / len(pairs)
