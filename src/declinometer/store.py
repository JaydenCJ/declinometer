"""The history file: an append-mostly JSON store of logged runs.

One JSON document, sorted keys, atomic writes — designed to be committed
next to the prompts it measures, so `git log history.json` *is* the
refusal-rate audit trail. Schema:

.. code-block:: json

    {
      "format": 1,
      "runs": [ { "label": "...", "created_at": "...", ...summary } ]
    }

Labels are unique; re-logging a label needs an explicit ``force`` because
silently overwriting a tracked measurement is how audit trails die.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional

from .aggregate import RunSummary

__all__ = ["StoreError", "RunEntry", "HistoryStore", "FORMAT_VERSION"]

FORMAT_VERSION = 1


class StoreError(ValueError):
    """The history file is missing, malformed, or the operation is invalid."""


@dataclass(frozen=True)
class RunEntry:
    """One logged run: a labelled, timestamped RunSummary."""

    label: str
    created_at: str
    summary: RunSummary

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {"label": self.label, "created_at": self.created_at}
        data.update(self.summary.to_dict())
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "RunEntry":
        label = data.get("label")
        created_at = data.get("created_at")
        if not isinstance(label, str) or not label:
            raise StoreError("run entry missing 'label'")
        if not isinstance(created_at, str):
            raise StoreError(f"run {label!r} missing 'created_at'")
        return cls(label=label, created_at=created_at, summary=RunSummary.from_dict(data))


class HistoryStore:
    """Load, query, and atomically rewrite one history file."""

    def __init__(self, path: str):
        self.path = path
        self._runs: List[RunEntry] = []
        self._loaded = False

    # -- loading ---------------------------------------------------------

    def load(self) -> "HistoryStore":
        """Read the file if it exists; a missing file is an empty store."""
        self._runs = []
        self._loaded = True
        if not os.path.exists(self.path):
            return self
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise StoreError(f"{self.path}: not valid JSON: {exc.msg}") from exc
        if not isinstance(data, dict) or "runs" not in data:
            raise StoreError(f"{self.path}: not a declinometer history file")
        fmt = data.get("format")
        if fmt != FORMAT_VERSION:
            raise StoreError(
                f"{self.path}: unsupported format {fmt!r} (this build reads {FORMAT_VERSION})"
            )
        runs = data["runs"]
        if not isinstance(runs, list):
            raise StoreError(f"{self.path}: 'runs' must be a list")
        self._runs = [RunEntry.from_dict(entry) for entry in runs]
        return self

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # -- queries ---------------------------------------------------------

    def runs(self) -> List[RunEntry]:
        self._ensure_loaded()
        return list(self._runs)

    def labels(self) -> List[str]:
        return [run.label for run in self.runs()]

    def get(self, label: str) -> RunEntry:
        self._ensure_loaded()
        for run in self._runs:
            if run.label == label:
                return run
        known = ", ".join(self.labels()) or "(none)"
        raise StoreError(f"no run labelled {label!r} in {self.path} (known: {known})")

    # -- mutation --------------------------------------------------------

    def add(self, entry: RunEntry, force: bool = False) -> None:
        """Append a run; replacing an existing label requires *force*."""
        self._ensure_loaded()
        existing = [i for i, run in enumerate(self._runs) if run.label == entry.label]
        if existing and not force:
            raise StoreError(
                f"run {entry.label!r} already exists in {self.path} "
                "(use --force to replace it)"
            )
        for i in reversed(existing):
            del self._runs[i]
        self._runs.append(entry)
        self._write()

    def _write(self) -> None:
        """Atomic write: temp file in the same directory, then rename."""
        payload = {
            "format": FORMAT_VERSION,
            "runs": [run.to_dict() for run in self._runs],
        }
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        fd, tmp_path = tempfile.mkstemp(prefix=".declinometer-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp_path, self.path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise


def make_entry(
    summary: RunSummary,
    label: str,
    created_at: str,
    model: Optional[str] = None,
    prompt_version: Optional[str] = None,
) -> RunEntry:
    """Build a RunEntry, letting explicit metadata override the inferred."""
    if model is not None or prompt_version is not None:
        summary = RunSummary(
            total=summary.total,
            counts=summary.counts,
            signal_counts=summary.signal_counts,
            verdicts=summary.verdicts,
            model=model if model is not None else summary.model,
            prompt_version=(
                prompt_version if prompt_version is not None else summary.prompt_version
            ),
        )
    return RunEntry(label=label, created_at=created_at, summary=summary)
