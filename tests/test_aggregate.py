"""Run summaries: counts, rates, metadata inference, and grouping."""

import pytest

from declinometer import Record, scan_records, summarize, summarize_groups
from declinometer.aggregate import RunSummary

from conftest import HARD_REFUSAL, HEDGED_ANSWER, PARTIAL_ANSWER, POLITE_ANSWER


def pairs_for(texts, model="m", prompt_version="v1"):
    records = [
        Record(id=f"r{i}", text=t, model=model, prompt_version=prompt_version)
        for i, t in enumerate(texts)
    ]
    return scan_records(records)


def test_summarize_counts_and_rates():
    s = summarize(pairs_for([HARD_REFUSAL, POLITE_ANSWER, HEDGED_ANSWER, PARTIAL_ANSWER]))
    assert s.total == 4
    assert s.counts == {"refusal": 1, "partial": 1, "hedged": 1, "comply": 1}
    assert s.rate("refusal") == 25.0
    assert s.refusal_rate == 25.0
    assert s.declined_rate == 50.0  # refusal + partial
    empty = summarize([])
    assert empty.total == 0 and empty.rate("refusal") == 0.0


def test_summarize_records_per_id_verdicts():
    s = summarize(pairs_for([HARD_REFUSAL, POLITE_ANSWER]))
    assert s.verdicts == {"r0": "refusal", "r1": "comply"}
    assert s.ids_with("refusal") == ["r0"]


def test_summarize_infers_uniform_metadata_but_not_mixed():
    uniform = summarize(pairs_for([POLITE_ANSWER, POLITE_ANSWER]))
    assert uniform.model == "m" and uniform.prompt_version == "v1"

    mixed = summarize(
        pairs_for([POLITE_ANSWER], model="m1") + pairs_for([POLITE_ANSWER], model="m2")
    )
    assert mixed.model is None  # a mixed batch must not lie


def test_summarize_signal_counts_by_category():
    s = summarize(pairs_for([HARD_REFUSAL]))
    assert s.signal_counts.get("hard_refusal", 0) >= 1
    assert s.signal_counts.get("policy_reference", 0) >= 1


def test_summary_dict_round_trip():
    s = summarize(pairs_for([HARD_REFUSAL, POLITE_ANSWER, HEDGED_ANSWER]))
    restored = RunSummary.from_dict(s.to_dict())
    assert restored.total == s.total
    assert restored.counts == s.counts
    assert restored.verdicts == s.verdicts
    assert restored.rates() == s.rates()
    assert restored.model == s.model


def test_summarize_groups_by_model_and_prompt_version():
    pairs = (
        pairs_for([HARD_REFUSAL], model="m1", prompt_version="v1")
        + pairs_for([POLITE_ANSWER, POLITE_ANSWER], model="m1", prompt_version="v2")
        + pairs_for([POLITE_ANSWER], model="m2", prompt_version="v1")
    )
    groups = summarize_groups(pairs, by=("model", "prompt_version"))
    keys = [key for key, _ in groups]
    assert keys == [("m1", "v1"), ("m1", "v2"), ("m2", "v1")]  # sorted, stable
    assert groups[0][1].refusal_rate == 100.0
    assert groups[1][1].total == 2


def test_summarize_groups_missing_metadata_renders_dash():
    pairs = scan_records([Record(id="x", text=POLITE_ANSWER)])
    ((key, _),) = summarize_groups(pairs, by=("model",))
    assert key == ("-",)


def test_summarize_groups_rejects_unknown_key():
    with pytest.raises(ValueError, match="cannot group by"):
        summarize_groups([], by=("temperature",))
