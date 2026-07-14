"""Turning per-output detections into run-level summaries.

A :class:`RunSummary` is the unit declinometer tracks over time: verdict
counts and rates, which signal categories fired how often, and the verdict
of every individual output (so a diff can name the exact cases that
flipped). Summaries serialize to plain dictionaries with sorted, stable
keys — they live in the history file and must diff cleanly in git.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .detector import Detection, Thresholds, VERDICTS, detect
from .records import Record

__all__ = ["RunSummary", "summarize", "summarize_groups", "scan_records"]


@dataclass(frozen=True)
class RunSummary:
    """Aggregated verdicts for one batch of outputs."""

    total: int
    counts: Dict[str, int]
    signal_counts: Dict[str, int]
    verdicts: Dict[str, str]  # record id -> verdict
    model: Optional[str] = None
    prompt_version: Optional[str] = None

    def rate(self, verdict: str) -> float:
        """Percentage (0-100) of outputs with *verdict*."""
        if self.total == 0:
            return 0.0
        return self.counts.get(verdict, 0) * 100.0 / self.total

    @property
    def refusal_rate(self) -> float:
        return self.rate("refusal")

    @property
    def declined_rate(self) -> float:
        """refusal + partial — the rate a product team alarms on."""
        return self.rate("refusal") + self.rate("partial")

    def rates(self) -> Dict[str, float]:
        return {v: round(self.rate(v), 4) for v in VERDICTS}

    def ids_with(self, verdict: str) -> List[str]:
        return sorted(rid for rid, v in self.verdicts.items() if v == verdict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "total": self.total,
            "counts": {v: self.counts.get(v, 0) for v in VERDICTS},
            "rates": self.rates(),
            "signal_counts": dict(sorted(self.signal_counts.items())),
            "verdicts": dict(sorted(self.verdicts.items())),
            "model": self.model,
            "prompt_version": self.prompt_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "RunSummary":
        counts = {str(k): int(v) for k, v in dict(data.get("counts", {})).items()}
        return cls(
            total=int(data.get("total", 0)),
            counts=counts,
            signal_counts={
                str(k): int(v) for k, v in dict(data.get("signal_counts", {})).items()
            },
            verdicts={str(k): str(v) for k, v in dict(data.get("verdicts", {})).items()},
            model=data.get("model") if isinstance(data.get("model"), str) else None,
            prompt_version=(
                data.get("prompt_version")
                if isinstance(data.get("prompt_version"), str)
                else None
            ),
        )


def scan_records(
    records: Iterable[Record],
    thresholds: Optional[Thresholds] = None,
) -> List[Tuple[Record, Detection]]:
    """Detect every record, keeping the pairing for reports and summaries."""
    th = thresholds or Thresholds()
    return [(rec, detect(rec.text, th)) for rec in records]


def summarize(
    pairs: Iterable[Tuple[Record, Detection]],
    model: Optional[str] = None,
    prompt_version: Optional[str] = None,
) -> RunSummary:
    """Fold (record, detection) pairs into one :class:`RunSummary`.

    When *model* / *prompt_version* are not given explicitly, they are
    inferred if every record agrees on a single value — a mixed batch
    stays ``None`` rather than lying.
    """
    counts: Dict[str, int] = {v: 0 for v in VERDICTS}
    signal_counts: Dict[str, int] = {}
    verdicts: Dict[str, str] = {}
    models = set()
    prompt_versions = set()
    total = 0

    for rec, det in pairs:
        total += 1
        counts[det.verdict] = counts.get(det.verdict, 0) + 1
        verdicts[rec.id] = det.verdict
        models.add(rec.model)
        prompt_versions.add(rec.prompt_version)
        for hit in det.signals:
            signal_counts[hit.category] = signal_counts.get(hit.category, 0) + 1

    if model is None and len(models) == 1:
        model = next(iter(models))
    if prompt_version is None and len(prompt_versions) == 1:
        prompt_version = next(iter(prompt_versions))

    return RunSummary(
        total=total,
        counts=counts,
        signal_counts=signal_counts,
        verdicts=verdicts,
        model=model,
        prompt_version=prompt_version,
    )


def summarize_groups(
    pairs: Iterable[Tuple[Record, Detection]],
    by: Tuple[str, ...] = ("model", "prompt_version"),
) -> List[Tuple[Tuple[str, ...], RunSummary]]:
    """Group pairs by record metadata and summarize each group.

    *by* may contain ``"model"`` and/or ``"prompt_version"``. Missing
    metadata renders as ``"-"`` so groups stay printable and sortable.
    Groups come back sorted by key for stable output.
    """
    valid = {"model", "prompt_version"}
    for name in by:
        if name not in valid:
            raise ValueError(f"cannot group by {name!r} (choose from {sorted(valid)})")

    buckets: Dict[Tuple[str, ...], List[Tuple[Record, Detection]]] = {}
    for rec, det in pairs:
        key = tuple(
            (rec.model if name == "model" else rec.prompt_version) or "-" for name in by
        )
        buckets.setdefault(key, []).append((rec, det))

    return [(key, summarize(buckets[key])) for key in sorted(buckets)]
