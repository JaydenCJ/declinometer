#!/usr/bin/env python3
"""Runnable demo: track refusal rates across two prompt versions.

Scans the two JSONL fixtures next to this file (the same outputs, produced
by "prompt v1" and "prompt v2"), logs both runs into a history file inside
a directory of your choice, prints the trend, and diffs the runs the same
way `declinometer diff` would in a release gate.

Usage:

    python examples/version_watch.py [OUTPUT_DIR]

Fully offline and deterministic — no model, no network, fixed timestamps.
"""

from __future__ import annotations

import os
import sys

from declinometer import (
    HistoryStore,
    diff_runs,
    read_records,
    scan_records,
    summarize,
)
from declinometer.report import render_diff, render_history
from declinometer.store import make_entry

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
    os.makedirs(out_dir, exist_ok=True)
    db_path = os.path.join(out_dir, "history.json")
    if os.path.exists(db_path):
        os.unlink(db_path)  # idempotent re-runs

    # 1. Scan each prompt version's outputs and log them under a label.
    store = HistoryStore(db_path)
    summaries = {}
    for label, created in (("prompt-v1", "2026-07-01T09:00:00Z"),
                           ("prompt-v2", "2026-07-08T09:00:00Z")):
        version = label.split("-")[1]
        records = read_records(os.path.join(HERE, f"outputs_{version}.jsonl"))
        summary = summarize(scan_records(records))
        summaries[label] = summary
        store.add(make_entry(summary, label=label, created_at=created))
        print(f"[log] {label}: {summary.total} outputs, "
              f"refusal {summary.refusal_rate:.1f}%, "
              f"declined {summary.declined_rate:.1f}%")

    # 2. The trend table, straight from the history file on disk.
    print()
    print(render_history(HistoryStore(db_path).runs()))

    # 3. The release-gate diff: did prompt v2 regress?
    print()
    diff = diff_runs(summaries["prompt-v1"], summaries["prompt-v2"],
                     label_a="prompt-v1", label_b="prompt-v2")
    print(render_diff(diff))

    print()
    if not diff.regressed:
        print("expected a regression in the fixtures", file=sys.stderr)
        return 1
    if [rid for rid, _, _ in diff.worsened_flips] != [
        "case-04", "case-06", "case-10", "case-02", "case-08"
    ]:
        print("unexpected flip set", file=sys.stderr)
        return 1
    print("DEMO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
