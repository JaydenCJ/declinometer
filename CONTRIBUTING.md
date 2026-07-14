# Contributing to declinometer

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Getting started

You need Python 3.9 or newer; everything else is standard library.

```bash
git clone https://github.com/JaydenCJ/declinometer
cd declinometer
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
bash scripts/smoke.sh
```

`scripts/smoke.sh` drives the real CLI end to end — scan, rate, log,
history, and the diff regression gate against the shipped fixtures — and
must print `SMOKE OK`.

## Before you open a pull request

1. Format touched files consistently with the surrounding code (PEP 8,
   4-space indents; `black`-compatible style is welcome).
2. Lint if you have a linter handy (`ruff check src tests` passes clean).
3. `pytest` — the whole suite must pass, offline, in seconds.
4. `bash scripts/smoke.sh` — must print `SMOKE OK`.
5. Add tests for behavior changes; keep logic in pure, unit-testable
   modules and out of `cli.py`.

## Ground rules

- **No new runtime dependencies.** `dependencies = []` is the flagship
  claim; test-only tools belong in the `dev` extra, with justification.
- **Determinism is the product.** No randomness, no wall-clock coupling,
  no network calls, no telemetry — a verdict must be reproducible forever.
- **Every lexicon pattern needs receipts.** A new pattern requires a
  canonical recall phrase in `tests/test_lexicon.py` (the coverage test
  enforces this) and, if it risks false positives, a lookalike case too.
- **History-file format changes need a version bump.** Anything that
  changes the meaning of a field must bump `FORMAT_VERSION` in `store.py`
  and be called out in the changelog.
- Code comments and doc comments are written in English. Keep the three
  READMEs aligned line-for-line; English is the authoritative version.

## Reporting bugs

Please include `declinometer --version`, the full command line, and — for
misclassifications — the exact output text plus `scan --explain`'s signal
list. That listing usually identifies the pattern to fix by name.

## Security

Please do not report security issues in public issues. Use GitHub's
private vulnerability reporting on this repository instead.
