# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- Deterministic four-verdict detector (`refusal` / `partial` / `hedged` /
  `comply`) built on a weighted pattern lexicon: 6 refusal-axis categories
  (hard refusals, policy references, apology contrasts, identity deflection,
  redirection, capability disclaimers) and 2 hedge-axis categories
  (uncertainty, deferral), with per-hit weights and a 1.5x opening-position
  multiplier.
- Length-preserving normalizer: character-wise case folding, typographic
  quote folding, and masking of code fences, inline code, double-quoted
  spans, and blockquotes — quoted refusals are mentioned, not spoken, and
  never counted. Signal spans always point at the original text.
- Substance analysis (code fences, list items, word count) that separates
  blank refusals from `partial` answers that still delivered content.
- Tunable `Thresholds` (refusal score, hedge score, hedge density, opening
  window, substance tests), exposed as CLI flags.
- JSONL record reader tolerant of field dialects (`output`/`text`/
  `completion`/`response`/`content`, or a pinned `--field`), with precise
  `file:line` errors.
- Run summaries with per-verdict counts and rates, per-category signal
  counts, per-id verdicts, and model/prompt_version inference; grouped
  aggregation for `rate --by`.
- Versioned history store: plain JSON with sorted keys and atomic writes,
  unique labels (`--force` to replace), designed to be committed to git.
- Regression diffs: rate deltas in percentage points, signal-category
  shifts, flipped case IDs ordered worst-first, and a declined-rate gate
  with `--tolerance`.
- `declinometer` CLI: `scan` (with `--explain`, `--json`,
  `--fail-on-declined`), `rate`, `log`, `history`, `diff` (exit 1 on
  regression); text, JSON, and Markdown output formats.
- Runnable example (`examples/version_watch.py`) with twelve-case fixture
  corpora for two prompt versions, plus `docs/detection.md` documenting
  every weight, threshold, and known limitation.
- 90 pytest tests and `scripts/smoke.sh`, all offline and deterministic.

### Notes

- The repository ships no CI workflow; verification is local — `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/declinometer/releases/tag/v0.1.0
