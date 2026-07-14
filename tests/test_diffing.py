"""Run diffs: deltas, flip detection and ordering, the regression gate."""

import pytest

from declinometer import Record, diff_runs, scan_records, summarize

from conftest import HARD_REFUSAL, HEDGED_ANSWER, PARTIAL_ANSWER, POLITE_ANSWER


def summary_of(texts_by_id):
    records = [Record(id=k, text=v) for k, v in texts_by_id.items()]
    return summarize(scan_records(records))


BASELINE = summary_of({
    "a": POLITE_ANSWER, "b": POLITE_ANSWER, "c": POLITE_ANSWER, "d": HARD_REFUSAL,
})
WORSE = summary_of({
    "a": HARD_REFUSAL, "b": PARTIAL_ANSWER, "c": HEDGED_ANSWER, "d": HARD_REFUSAL,
})


def test_rate_deltas_in_percentage_points():
    diff = diff_runs(BASELINE, WORSE)
    ra, rb, delta = diff.rate_deltas["refusal"]
    assert (ra, rb, delta) == (25.0, 50.0, 25.0)
    assert diff.declined_delta == 50.0  # declined went 25% -> 75%


def test_regression_gate_respects_tolerance():
    assert diff_runs(BASELINE, WORSE, tolerance=0.0).regressed
    assert diff_runs(BASELINE, WORSE, tolerance=49.9).regressed
    assert not diff_runs(BASELINE, WORSE, tolerance=50.0).regressed
    # improvement never regresses
    assert not diff_runs(WORSE, BASELINE).regressed
    # a negative tolerance is a config bug, not a stricter gate
    with pytest.raises(ValueError, match="tolerance"):
        diff_runs(BASELINE, WORSE, tolerance=-1.0)


def test_flips_ordered_worst_first_and_split_by_direction():
    diff = diff_runs(BASELINE, WORSE)
    assert diff.flips == [
        ("a", "comply", "refusal"),   # +3 severity first
        ("b", "comply", "partial"),   # +2
        ("c", "comply", "hedged"),    # +1
    ]
    assert diff.worsened_flips == diff.flips
    # the overall list is worst-first, so the biggest improvement sorts last
    back = diff_runs(WORSE, BASELINE)
    assert back.improved_flips == [
        ("c", "hedged", "comply"),
        ("b", "partial", "comply"),
        ("a", "refusal", "comply"),
    ]


def test_disjoint_corpora_diff_has_rates_but_no_flips():
    other = summary_of({"x": HARD_REFUSAL, "y": HARD_REFUSAL})
    diff = diff_runs(BASELINE, other)
    assert diff.flips == []
    assert diff.rate_deltas["refusal"][2] == 75.0
    assert diff.regressed


def test_signal_deltas_cover_categories_from_both_runs():
    diff = diff_runs(BASELINE, WORSE)
    assert diff.signal_deltas["hard_refusal"][2] > 0
    a_only = summary_of({"a": HEDGED_ANSWER})
    b_only = summary_of({"a": POLITE_ANSWER})
    d2 = diff_runs(a_only, b_only)
    assert "uncertainty" in d2.signal_deltas  # category present only in run A


def test_diff_to_dict_is_json_ready():
    data = diff_runs(BASELINE, WORSE, label_a="v1", label_b="v2").to_dict()
    assert data["a"] == "v1" and data["b"] == "v2"
    assert data["regressed"] is True
    assert data["rates"]["refusal"]["delta"] == 25.0
    assert {"id", "a", "b"} == set(data["flips"][0])
