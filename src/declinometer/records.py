"""JSONL record reading: one model output per line, tolerant of dialects.

declinometer does not run models; it consumes what a harness or gateway
already logs. The lowest common denominator across eval harnesses is JSON
Lines, one object per output, but nobody agrees on the field name for the
text — so :func:`iter_records` accepts the usual suspects (``output``,
``text``, ``completion``, ``response``, ``content``) unless the caller
pins one with ``text_field``. Bare JSON strings are accepted too, which
makes tiny hand-written fixtures pleasant.

Errors carry the file path and 1-based line number, because a bad line 4812
in a 5000-line dump is undebuggable otherwise.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Union

__all__ = ["Record", "RecordError", "TEXT_FIELDS", "iter_records", "read_records"]

#: Field names tried, in order, when no ``text_field`` is pinned.
TEXT_FIELDS = ("output", "text", "completion", "response", "content")

#: Metadata fields lifted from each record when present.
_ID_FIELDS = ("id", "case_id", "example_id", "name")


class RecordError(ValueError):
    """A line that could not be turned into a Record, with its location."""

    def __init__(self, source: str, line_no: int, reason: str):
        self.source = source
        self.line_no = line_no
        self.reason = reason
        super().__init__(f"{source}:{line_no}: {reason}")


@dataclass(frozen=True)
class Record:
    """One model output plus the metadata declinometer tracks."""

    id: str
    text: str
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    line_no: int = 0


def _extract_text(obj: dict, text_field: Optional[str]) -> Optional[str]:
    if text_field is not None:
        value = obj.get(text_field)
        return value if isinstance(value, str) else None
    for name in TEXT_FIELDS:
        value = obj.get(name)
        if isinstance(value, str):
            return value
    return None


def _extract_id(obj: dict, line_no: int) -> str:
    for name in _ID_FIELDS:
        value = obj.get(name)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value)
    return f"line-{line_no}"


def _as_optional_str(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def iter_records(
    lines: Iterable[str],
    source: str = "<stdin>",
    text_field: Optional[str] = None,
) -> Iterator[Record]:
    """Yield :class:`Record` objects from an iterable of JSONL lines.

    Blank lines are skipped. Anything else that fails to parse, or parses
    but has no usable text field, raises :class:`RecordError` immediately —
    a silently dropped record would corrupt the rate it feeds.
    """
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RecordError(source, line_no, f"invalid JSON: {exc.msg}") from exc

        if isinstance(obj, str):
            yield Record(id=f"line-{line_no}", text=obj, line_no=line_no)
            continue
        if not isinstance(obj, dict):
            raise RecordError(
                source, line_no, f"expected an object or string, got {type(obj).__name__}"
            )

        text = _extract_text(obj, text_field)
        if text is None:
            wanted = text_field or "/".join(TEXT_FIELDS)
            raise RecordError(source, line_no, f"no text field (looked for: {wanted})")

        yield Record(
            id=_extract_id(obj, line_no),
            text=text,
            model=_as_optional_str(obj.get("model")),
            prompt_version=_as_optional_str(obj.get("prompt_version")),
            line_no=line_no,
        )


def read_records(
    path_or_file: Union[str, io.TextIOBase],
    text_field: Optional[str] = None,
) -> List[Record]:
    """Read a whole JSONL file (path or open text handle) into a list."""
    if isinstance(path_or_file, str):
        with open(path_or_file, "r", encoding="utf-8") as fh:
            return list(iter_records(fh, source=path_or_file, text_field=text_field))
    source = getattr(path_or_file, "name", "<stream>")
    return list(iter_records(path_or_file, source=source, text_field=text_field))
