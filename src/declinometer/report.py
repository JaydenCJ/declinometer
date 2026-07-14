"""Rendering: detections, rate tables, history, and diffs as text/JSON/Markdown.

All rendering is pure string building over the structured results — no
printing, no terminal detection, no color codes. The CLI decides where the
strings go; tests assert on them directly.
"""

from __future__ import annotations

import json
from typing import List, Optional, Sequence, Tuple

from .aggregate import RunSummary
from .detector import Detection, Thresholds, VERDICTS
from .diffing import RunDiff
from .store import RunEntry

__all__ = [
    "render_table",
    "render_detection",
    "render_rate_table",
    "render_history",
    "render_diff",
    "to_json",
]


def to_json(data: object) -> str:
    """Canonical JSON output: sorted keys, stable across runs."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """A plain, dependency-free, monospace-aligned table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip()]
    for row in rows:
        lines.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip())
    return "\n".join(lines)


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _pct(value: float) -> str:
    return f"{value:.1f}%"


def _pp(value: float) -> str:
    """Percentage-point delta with an explicit sign."""
    return f"{value:+.1f} pp"


def _n(count: int, noun: str) -> str:
    """Count + noun with correct pluralization ("1 word", "2 words")."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


# ----------------------------------------------------------------------- #
# scan                                                                     #
# ----------------------------------------------------------------------- #

def render_detection(
    det: Detection,
    thresholds: Optional[Thresholds] = None,
    explain: bool = False,
) -> str:
    """Human-readable verdict block for one output."""
    th = thresholds or Thresholds()
    lines = [
        f"verdict: {det.verdict}",
        f"refusal score: {det.refusal_score:.1f} (threshold {th.refusal_score:.1f})",
        f"hedge score: {det.hedge_score:.1f} "
        f"(density {det.hedge_density:.1f} per 100 words, "
        f"thresholds {th.hedge_score:.1f} / {th.hedge_density:.1f})",
        f"substance: {_n(det.word_count, 'word')}, "
        f"{_n(det.code_fences, 'code block')}, {_n(det.list_items, 'list item')}",
    ]
    if explain:
        if det.signals:
            lines.append("signals:")
            for hit in det.signals:
                boost = " (opening)" if hit.multiplier != 1.0 else ""
                lines.append(
                    f"  [{hit.category}] {hit.pattern_id} "
                    f"{hit.text!r} at {hit.start}-{hit.end} "
                    f"weight {hit.weight:g} x{hit.multiplier:g}{boost}"
                )
        else:
            lines.append("signals: none")
    return "\n".join(lines)


# ----------------------------------------------------------------------- #
# rate                                                                     #
# ----------------------------------------------------------------------- #

def _summary_row(summary: RunSummary) -> List[str]:
    return [
        str(summary.total),
        _pct(summary.rate("refusal")),
        _pct(summary.rate("partial")),
        _pct(summary.rate("hedged")),
        _pct(summary.rate("comply")),
    ]


def render_rate_table(
    groups: Sequence[Tuple[Tuple[str, ...], RunSummary]],
    by: Sequence[str],
    markdown: bool = False,
) -> str:
    """Rate table, one row per (model, prompt_version, ...) group."""
    headers = list(by) + ["outputs", "refusal", "partial", "hedged", "comply"]
    rows = [list(key) + _summary_row(summary) for key, summary in groups]
    if markdown:
        return _markdown_table(headers, rows)
    return render_table(headers, rows)


# ----------------------------------------------------------------------- #
# history                                                                  #
# ----------------------------------------------------------------------- #

def render_history(entries: Sequence[RunEntry], markdown: bool = False) -> str:
    """Chronological table of logged runs with declined-rate movement."""
    headers = [
        "label", "created", "model", "prompt", "outputs",
        "refusal", "partial", "hedged", "declined", "trend",
    ]
    rows: List[List[str]] = []
    prev: Optional[float] = None
    for entry in entries:
        s = entry.summary
        declined = s.declined_rate
        trend = "-" if prev is None else _pp(declined - prev)
        prev = declined
        rows.append([
            entry.label,
            entry.created_at[:10],
            s.model or "-",
            s.prompt_version or "-",
            str(s.total),
            _pct(s.rate("refusal")),
            _pct(s.rate("partial")),
            _pct(s.rate("hedged")),
            _pct(declined),
            trend,
        ])
    if markdown:
        return _markdown_table(headers, rows)
    return render_table(headers, rows)


# ----------------------------------------------------------------------- #
# diff                                                                     #
# ----------------------------------------------------------------------- #

def render_diff(diff: RunDiff, max_flips: int = 10) -> str:
    """The diff report the release gate prints."""
    lines = [f"declinometer diff: {diff.label_a} -> {diff.label_b}"]
    lines.append(f"  outputs   {diff.total_a} -> {diff.total_b}")
    for verdict in VERDICTS:
        ra, rb, delta = diff.rate_deltas[verdict]
        lines.append(
            f"  {verdict:<9} {_pct(ra)} -> {_pct(rb)}  ({_pp(delta)})"
        )

    moved = {c: v for c, v in diff.signal_deltas.items() if v[2] != 0}
    if moved:
        lines.append("signal shifts:")
        for cat, (ca, cb, delta) in sorted(
            moved.items(), key=lambda kv: (-abs(kv[1][2]), kv[0])
        ):
            lines.append(f"  {cat:<22} {ca} -> {cb}  ({delta:+d})")

    worsened = diff.worsened_flips
    improved = diff.improved_flips
    if worsened:
        shown = worsened[:max_flips]
        lines.append(f"flipped worse ({len(worsened)}):")
        for rid, va, vb in shown:
            lines.append(f"  {rid}: {va} -> {vb}")
        if len(worsened) > len(shown):
            lines.append(f"  ... and {len(worsened) - len(shown)} more")
    if improved:
        lines.append(f"flipped better ({len(improved)}): " +
                      ", ".join(rid for rid, _, _ in improved[:max_flips]))

    if diff.regressed:
        lines.append(
            f"verdict: REGRESSION (declined rate {_pp(diff.declined_delta)} "
            f"exceeds tolerance {diff.tolerance:g} pp)"
        )
    else:
        lines.append(
            f"verdict: OK (declined rate {_pp(diff.declined_delta)}, "
            f"tolerance {diff.tolerance:g} pp)"
        )
    return "\n".join(lines)
