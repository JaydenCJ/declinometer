"""Rendering: alignment, markdown shape, and the wording gates rely on."""

from declinometer import Record, detect, diff_runs, scan_records, summarize
from declinometer.report import (
    render_detection,
    render_diff,
    render_history,
    render_rate_table,
    render_table,
    to_json,
)
from declinometer.aggregate import summarize_groups
from declinometer.store import make_entry

from conftest import HARD_REFUSAL, POLITE_ANSWER


def test_render_table_alignment_and_canonical_json():
    out = render_table(["k", "value"], [["long-key", "1"], ["x", "22"]])
    lines = out.splitlines()
    assert lines[0].startswith("k")
    assert all(line == line.rstrip() for line in lines)
    assert lines[1].index("1") == lines[0].index("value")
    # canonical JSON: sorted keys, stable across runs
    assert to_json({"b": 1, "a": 2}) == '{\n  "a": 2,\n  "b": 1\n}'


def test_render_detection_explains_signals_with_spans():
    det = detect(HARD_REFUSAL)
    out = render_detection(det, explain=True)
    assert out.startswith("verdict: refusal")
    assert "[hard_refusal] cannot_verb" in out
    assert "(opening)" in out
    plain = render_detection(det)
    assert "cannot_verb" not in plain  # signals only appear with --explain


def test_render_rate_table_markdown_has_header_separator():
    pairs = scan_records([Record(id="a", text=POLITE_ANSWER, model="m", prompt_version="v1")])
    groups = summarize_groups(pairs, by=("model",))
    md = render_rate_table(groups, ["model"], markdown=True)
    lines = md.splitlines()
    assert lines[0].startswith("| model |")
    assert set(lines[1]) <= {"|", "-"}


def test_render_history_shows_trend_between_consecutive_runs():
    s1 = summarize(scan_records([Record(id="a", text=POLITE_ANSWER)]))
    s2 = summarize(scan_records([Record(id="a", text=HARD_REFUSAL)]))
    entries = [
        make_entry(s1, label="v1", created_at="2026-07-01T09:00:00Z"),
        make_entry(s2, label="v2", created_at="2026-07-08T09:00:00Z"),
    ]
    out = render_history(entries)
    assert "2026-07-01" in out
    v2_line = next(line for line in out.splitlines() if line.startswith("v2"))
    assert "+100.0 pp" in v2_line


def test_render_diff_verdict_lines():
    s_ok = summarize(scan_records([Record(id="a", text=POLITE_ANSWER)]))
    s_bad = summarize(scan_records([Record(id="a", text=HARD_REFUSAL)]))
    regressed = render_diff(diff_runs(s_ok, s_bad, label_a="v1", label_b="v2"))
    assert "declinometer diff: v1 -> v2" in regressed
    assert "verdict: REGRESSION" in regressed
    assert "a: comply -> refusal" in regressed
    fine = render_diff(diff_runs(s_bad, s_ok))
    assert "verdict: OK" in fine


def test_render_diff_truncates_long_flip_lists():
    s_ok = summarize(scan_records([Record(id=f"r{i:02d}", text=POLITE_ANSWER) for i in range(12)]))
    s_bad = summarize(scan_records([Record(id=f"r{i:02d}", text=HARD_REFUSAL) for i in range(12)]))
    out = render_diff(diff_runs(s_ok, s_bad), max_flips=10)
    assert "flipped worse (12):" in out
    assert "... and 2 more" in out

