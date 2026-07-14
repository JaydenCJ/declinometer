"""The ``declinometer`` command-line interface.

Five subcommands mirror the workflow:

- ``scan``     classify one output (file or stdin) and explain the signals
- ``rate``     aggregate a JSONL dump into per-model/per-prompt rates
- ``log``      record a run into a history file under a label
- ``history``  show the logged trend
- ``diff``     compare two runs (labels in a history file, or two JSONL
               files) and exit 1 on regression — the release gate

Exit codes: 0 success, 1 gate failure (``diff`` regression, or ``scan
--fail-on-declined`` hitting a refusal/partial), 2 usage or data error.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from . import __version__
from .aggregate import scan_records, summarize, summarize_groups
from .detector import Thresholds, detect
from .diffing import diff_runs
from .records import RecordError, read_records
from .report import (
    render_detection,
    render_diff,
    render_history,
    render_rate_table,
    to_json,
)
from .store import HistoryStore, StoreError, make_entry

__all__ = ["main", "build_parser"]


class CliError(Exception):
    """A user-facing error; printed to stderr, exits 2."""


# ----------------------------------------------------------------------- #
# shared argument groups                                                   #
# ----------------------------------------------------------------------- #

def _add_threshold_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("detection thresholds")
    group.add_argument(
        "--refusal-threshold", type=float, default=None, metavar="SCORE",
        help="refusal-axis score at which an output counts as declined "
             "(default: 3.0)",
    )
    group.add_argument(
        "--hedge-threshold", type=float, default=None, metavar="SCORE",
        help="minimum hedge score for the hedged verdict (default: 2.0)",
    )
    group.add_argument(
        "--hedge-density", type=float, default=None, metavar="PER100W",
        help="minimum hedge score per 100 words for the hedged verdict "
             "(default: 1.5)",
    )


def _thresholds_from(args: argparse.Namespace) -> Thresholds:
    base = Thresholds()
    return Thresholds(
        refusal_score=(
            args.refusal_threshold
            if args.refusal_threshold is not None
            else base.refusal_score
        ),
        hedge_score=(
            args.hedge_threshold if args.hedge_threshold is not None else base.hedge_score
        ),
        hedge_density=(
            args.hedge_density if args.hedge_density is not None else base.hedge_density
        ),
    )


def _add_field_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--field", default=None, metavar="NAME",
        help="JSON field holding the output text (default: try "
             "output/text/completion/response/content)",
    )


def _read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise CliError(f"cannot read {path}: {exc.strerror}") from exc


def _load_records(path: str, field: Optional[str]):
    try:
        if path == "-":
            return read_records(sys.stdin, text_field=field)
        return read_records(path, text_field=field)
    except RecordError as exc:
        raise CliError(str(exc)) from exc
    except OSError as exc:
        raise CliError(f"cannot read {path}: {exc.strerror}") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------- #
# subcommands                                                              #
# ----------------------------------------------------------------------- #

def _cmd_scan(args: argparse.Namespace) -> int:
    text = _read_text(args.path)
    th = _thresholds_from(args)
    det = detect(text, th)
    if args.json:
        print(to_json(det.to_dict()))
    else:
        print(render_detection(det, th, explain=args.explain))
    if args.fail_on_declined and det.declined:
        return 1
    return 0


def _parse_by(raw: str) -> Tuple[str, ...]:
    names = tuple(name.strip() for name in raw.split(",") if name.strip())
    if not names:
        raise CliError("--by needs at least one of: model, prompt_version")
    for name in names:
        if name not in ("model", "prompt_version"):
            raise CliError(
                f"cannot group by {name!r} (choose from: model, prompt_version)"
            )
    return names


def _cmd_rate(args: argparse.Namespace) -> int:
    th = _thresholds_from(args)
    pairs = []
    for path in args.paths:
        pairs.extend(scan_records(_load_records(path, args.field), th))
    if not pairs:
        raise CliError("no records found")
    by = _parse_by(args.by)
    groups = summarize_groups(pairs, by=by)
    if args.format == "json":
        print(to_json({
            "groups": [
                {"key": dict(zip(by, key)), **summary.to_dict()}
                for key, summary in groups
            ]
        }))
    else:
        print(render_rate_table(groups, by, markdown=(args.format == "markdown")))
    return 0


def _cmd_log(args: argparse.Namespace) -> int:
    th = _thresholds_from(args)
    records = _load_records(args.path, args.field)
    if not records:
        raise CliError("no records found")
    summary = summarize(scan_records(records, th))
    entry = make_entry(
        summary,
        label=args.label,
        created_at=args.now or _utc_now(),
        model=args.model,
        prompt_version=args.prompt_version,
    )
    store = HistoryStore(args.db)
    try:
        store.add(entry, force=args.force)
    except StoreError as exc:
        raise CliError(str(exc)) from exc
    s = entry.summary
    outputs = "output" if s.total == 1 else "outputs"
    print(
        f"logged {entry.label!r}: {s.total} {outputs}, "
        f"refusal {s.rate('refusal'):.1f}%, partial {s.rate('partial'):.1f}%, "
        f"hedged {s.rate('hedged'):.1f}% -> {args.db}"
    )
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    try:
        entries = HistoryStore(args.db).runs()
    except StoreError as exc:
        raise CliError(str(exc)) from exc
    if not entries:
        raise CliError(f"no runs logged in {args.db}")
    if args.format == "json":
        print(to_json({"runs": [e.to_dict() for e in entries]}))
    else:
        print(render_history(entries, markdown=(args.format == "markdown")))
    return 0


def _summary_for_diff(ref: str, args: argparse.Namespace, store: Optional[HistoryStore]):
    if store is not None:
        try:
            return store.get(ref).summary
        except StoreError as exc:
            raise CliError(str(exc)) from exc
    th = _thresholds_from(args)
    records = _load_records(ref, args.field)
    if not records:
        raise CliError(f"no records found in {ref}")
    return summarize(scan_records(records, th))


def _cmd_diff(args: argparse.Namespace) -> int:
    store = HistoryStore(args.db) if args.db else None
    summary_a = _summary_for_diff(args.a, args, store)
    summary_b = _summary_for_diff(args.b, args, store)
    try:
        diff = diff_runs(
            summary_a, summary_b,
            label_a=args.a, label_b=args.b,
            tolerance=args.tolerance,
        )
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    if args.format == "json":
        print(to_json(diff.to_dict()))
    else:
        print(render_diff(diff))
    return 1 if diff.regressed else 0


# ----------------------------------------------------------------------- #
# parser                                                                   #
# ----------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="declinometer",
        description="Detect refusals and hedging in model outputs; "
                    "track refusal rates across prompt and model versions.",
    )
    parser.add_argument(
        "--version", action="version", version=f"declinometer {__version__}"
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    p_scan = sub.add_parser(
        "scan", help="classify one output from a file or stdin",
        description="Classify one output. Reads a plain-text file, or stdin "
                    "when PATH is '-' (the default).",
    )
    p_scan.add_argument("path", nargs="?", default="-", help="text file or '-' for stdin")
    p_scan.add_argument("--json", action="store_true", help="emit the full detection as JSON")
    p_scan.add_argument("--explain", action="store_true", help="list every matched signal with its span")
    p_scan.add_argument(
        "--fail-on-declined", action="store_true",
        help="exit 1 when the verdict is refusal or partial",
    )
    _add_threshold_args(p_scan)
    p_scan.set_defaults(func=_cmd_scan)

    p_rate = sub.add_parser(
        "rate", help="aggregate JSONL outputs into refusal/hedge rates",
        description="Scan JSONL files (one output object per line) and print "
                    "rates grouped by model and/or prompt_version.",
    )
    p_rate.add_argument("paths", nargs="+", metavar="JSONL", help="input files, '-' for stdin")
    p_rate.add_argument(
        "--by", default="model,prompt_version", metavar="KEYS",
        help="comma-separated grouping keys: model, prompt_version (default: both)",
    )
    p_rate.add_argument(
        "--format", choices=("text", "json", "markdown"), default="text",
        help="output format (default: text)",
    )
    _add_field_arg(p_rate)
    _add_threshold_args(p_rate)
    p_rate.set_defaults(func=_cmd_rate)

    p_log = sub.add_parser(
        "log", help="scan a JSONL file and record the run in a history file",
        description="Summarize a JSONL file and append the result to a "
                    "history file under a unique label.",
    )
    p_log.add_argument("path", metavar="JSONL", help="input file, '-' for stdin")
    p_log.add_argument("--db", required=True, metavar="FILE", help="history file (created if missing)")
    p_log.add_argument("--label", required=True, help="unique label for this run, e.g. 'prompt-v4'")
    p_log.add_argument("--model", default=None, help="override the model recorded for this run")
    p_log.add_argument("--prompt-version", default=None, help="override the prompt version recorded")
    p_log.add_argument(
        "--now", default=None, metavar="ISO8601",
        help="timestamp to record instead of the current UTC time",
    )
    p_log.add_argument("--force", action="store_true", help="replace an existing run with the same label")
    _add_field_arg(p_log)
    _add_threshold_args(p_log)
    p_log.set_defaults(func=_cmd_log)

    p_hist = sub.add_parser(
        "history", help="show the logged runs in a history file",
        description="Print every logged run in order with its rates and the "
                    "declined-rate trend between consecutive runs.",
    )
    p_hist.add_argument("--db", required=True, metavar="FILE", help="history file")
    p_hist.add_argument(
        "--format", choices=("text", "json", "markdown"), default="text",
        help="output format (default: text)",
    )
    p_hist.set_defaults(func=_cmd_history)

    p_diff = sub.add_parser(
        "diff", help="compare two runs; exit 1 on refusal-rate regression",
        description="Compare run A (baseline) with run B. With --db, A and B "
                    "are labels in the history file; otherwise they are JSONL "
                    "files scanned on the fly. Exits 1 when the declined rate "
                    "(refusal + partial) rises by more than --tolerance "
                    "percentage points.",
    )
    p_diff.add_argument("a", help="baseline: history label (with --db) or JSONL file")
    p_diff.add_argument("b", help="candidate: history label (with --db) or JSONL file")
    p_diff.add_argument("--db", default=None, metavar="FILE", help="history file holding the labels")
    p_diff.add_argument(
        "--tolerance", type=float, default=0.0, metavar="PP",
        help="allowed declined-rate increase in percentage points (default: 0)",
    )
    p_diff.add_argument(
        "--format", choices=("text", "json"), default="text",
        help="output format (default: text)",
    )
    _add_field_arg(p_diff)
    _add_threshold_args(p_diff)
    p_diff.set_defaults(func=_cmd_diff)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except CliError as exc:
        print(f"declinometer: error: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        # Downstream (e.g. `head`) closed the pipe: point stdout at devnull
        # so the interpreter's final flush cannot raise a second time.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
