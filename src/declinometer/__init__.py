"""declinometer — deterministic refusal & hedging detection for LLM outputs.

Public API surface, re-exported for library use:

- :func:`detect` / :class:`Detection` / :class:`Thresholds` — classify one
  output into ``refusal`` / ``partial`` / ``hedged`` / ``comply``.
- :func:`read_records` / :class:`Record` — load JSONL output dumps.
- :func:`scan_records` / :func:`summarize` / :class:`RunSummary` — batch
  scanning and run-level rates.
- :class:`HistoryStore` / :class:`RunEntry` — the versioned history file.
- :func:`diff_runs` / :class:`RunDiff` — regression diffs between runs.

Everything is standard library only, offline, and deterministic: the same
text always produces the same verdict.
"""

from .aggregate import RunSummary, scan_records, summarize, summarize_groups
from .detector import Detection, SignalHit, Thresholds, VERDICTS, detect
from .diffing import RunDiff, diff_runs
from .records import Record, RecordError, read_records
from .store import HistoryStore, RunEntry, StoreError

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "VERDICTS",
    "detect",
    "Detection",
    "SignalHit",
    "Thresholds",
    "Record",
    "RecordError",
    "read_records",
    "scan_records",
    "summarize",
    "summarize_groups",
    "RunSummary",
    "HistoryStore",
    "RunEntry",
    "StoreError",
    "diff_runs",
    "RunDiff",
]
