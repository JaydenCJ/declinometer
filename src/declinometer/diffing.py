"""Comparing two runs: rate deltas, signal shifts, and the flipped cases.

The diff is where declinometer earns its keep — "the refusal rate went from
2.1% to 7.4% between prompt v3 and v4, driven by policy_reference cues, and
here are the nine case IDs that flipped" is an actionable bug report;
"users say the bot got worse" is not.

A diff *regresses* when the declined rate (refusal + partial) rises by more
than ``tolerance`` percentage points. The CLI turns a regression into exit
code 1, so a `declinometer diff` slots straight into a release gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .aggregate import RunSummary
from .detector import VERDICTS

__all__ = ["RunDiff", "diff_runs"]

#: Ranking used to describe a flip's direction. Higher is worse.
_SEVERITY = {"comply": 0, "hedged": 1, "partial": 2, "refusal": 3}


@dataclass(frozen=True)
class RunDiff:
    """Everything that changed between run *a* (baseline) and run *b*."""

    label_a: str
    label_b: str
    total_a: int
    total_b: int
    #: verdict -> (rate_a, rate_b, delta_in_percentage_points)
    rate_deltas: Dict[str, Tuple[float, float, float]]
    #: category -> (count_a, count_b, delta)
    signal_deltas: Dict[str, Tuple[int, int, int]]
    #: ids present in both runs whose verdict changed, with both verdicts,
    #: sorted worst-flips-first then by id.
    flips: List[Tuple[str, str, str]] = field(default_factory=list)
    #: declined-rate movement in percentage points (positive = worse).
    declined_delta: float = 0.0
    tolerance: float = 0.0

    @property
    def regressed(self) -> bool:
        return self.declined_delta > self.tolerance

    @property
    def worsened_flips(self) -> List[Tuple[str, str, str]]:
        return [
            (rid, va, vb)
            for rid, va, vb in self.flips
            if _SEVERITY[vb] > _SEVERITY[va]
        ]

    @property
    def improved_flips(self) -> List[Tuple[str, str, str]]:
        return [
            (rid, va, vb)
            for rid, va, vb in self.flips
            if _SEVERITY[vb] < _SEVERITY[va]
        ]

    def to_dict(self) -> Dict[str, object]:
        return {
            "a": self.label_a,
            "b": self.label_b,
            "total_a": self.total_a,
            "total_b": self.total_b,
            "rates": {
                v: {"a": round(ra, 4), "b": round(rb, 4), "delta": round(d, 4)}
                for v, (ra, rb, d) in self.rate_deltas.items()
            },
            "signals": {
                c: {"a": ca, "b": cb, "delta": d}
                for c, (ca, cb, d) in self.signal_deltas.items()
            },
            "flips": [
                {"id": rid, "a": va, "b": vb} for rid, va, vb in self.flips
            ],
            "declined_delta": round(self.declined_delta, 4),
            "tolerance": self.tolerance,
            "regressed": self.regressed,
        }


def diff_runs(
    a: RunSummary,
    b: RunSummary,
    label_a: str = "a",
    label_b: str = "b",
    tolerance: float = 0.0,
) -> RunDiff:
    """Compute the structured diff between two summaries.

    Flips are only computed over ids present in both runs — a diff between
    disjoint corpora still yields honest rate deltas, just no flip list.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")

    rate_deltas: Dict[str, Tuple[float, float, float]] = {}
    for verdict in VERDICTS:
        ra, rb = a.rate(verdict), b.rate(verdict)
        rate_deltas[verdict] = (ra, rb, rb - ra)

    categories = sorted(set(a.signal_counts) | set(b.signal_counts))
    signal_deltas: Dict[str, Tuple[int, int, int]] = {}
    for cat in categories:
        ca = a.signal_counts.get(cat, 0)
        cb = b.signal_counts.get(cat, 0)
        signal_deltas[cat] = (ca, cb, cb - ca)

    shared = set(a.verdicts) & set(b.verdicts)
    flips = [
        (rid, a.verdicts[rid], b.verdicts[rid])
        for rid in shared
        if a.verdicts[rid] != b.verdicts[rid]
    ]
    # Worst flips first (largest severity increase), then stable by id.
    flips.sort(key=lambda f: (-(_SEVERITY[f[2]] - _SEVERITY[f[1]]), f[0]))

    return RunDiff(
        label_a=label_a,
        label_b=label_b,
        total_a=a.total,
        total_b=b.total,
        rate_deltas=rate_deltas,
        signal_deltas=signal_deltas,
        flips=flips,
        declined_delta=b.declined_rate - a.declined_rate,
        tolerance=tolerance,
    )
