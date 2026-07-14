"""History store: atomic persistence, label uniqueness, format guards."""

import json

import pytest

from declinometer import HistoryStore, Record, StoreError, scan_records, summarize
from declinometer.store import make_entry

from conftest import HARD_REFUSAL, POLITE_ANSWER


def entry_for(texts, label, created_at="2026-07-01T00:00:00Z"):
    records = [Record(id=f"r{i}", text=t) for i, t in enumerate(texts)]
    return make_entry(summarize(scan_records(records)), label=label, created_at=created_at)


def test_add_then_reload_round_trips(tmp_path):
    db = str(tmp_path / "history.json")
    entry = entry_for([HARD_REFUSAL, POLITE_ANSWER], "v1")
    HistoryStore(db).add(entry)

    reloaded = HistoryStore(db).get("v1")
    assert reloaded.label == "v1"
    assert reloaded.created_at == "2026-07-01T00:00:00Z"
    assert reloaded.summary.total == 2
    assert reloaded.summary.refusal_rate == 50.0


def test_missing_file_is_an_empty_store(tmp_path):
    store = HistoryStore(str(tmp_path / "nope.json"))
    assert store.runs() == []
    assert store.labels() == []


def test_duplicate_label_requires_force_and_unknown_label_errors(tmp_path):
    db = str(tmp_path / "history.json")
    store = HistoryStore(db)
    store.add(entry_for([POLITE_ANSWER], "v1"))
    with pytest.raises(StoreError, match="already exists"):
        store.add(entry_for([HARD_REFUSAL], "v1"))

    # force replaces in place; the store still has exactly one 'v1'
    store.add(entry_for([HARD_REFUSAL], "v1"), force=True)
    runs = HistoryStore(db).runs()
    assert [r.label for r in runs] == ["v1"]
    assert runs[0].summary.refusal_rate == 100.0

    # asking for an unknown label names the labels that do exist
    with pytest.raises(StoreError, match=r"no run labelled 'v9'.*v1"):
        store.get("v9")


def test_file_on_disk_is_stable_sorted_json(tmp_path):
    db = tmp_path / "history.json"
    HistoryStore(str(db)).add(entry_for([POLITE_ANSWER], "v1"))
    raw = db.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["format"] == 1
    assert raw == json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_rejects_foreign_and_unsupported_files(tmp_path):
    not_ours = tmp_path / "other.json"
    not_ours.write_text('{"hello": "world"}', encoding="utf-8")
    with pytest.raises(StoreError, match="not a declinometer history file"):
        HistoryStore(str(not_ours)).load()

    future = tmp_path / "future.json"
    future.write_text('{"format": 99, "runs": []}', encoding="utf-8")
    with pytest.raises(StoreError, match="unsupported format"):
        HistoryStore(str(future)).load()

    broken = tmp_path / "broken.json"
    broken.write_text("{nope", encoding="utf-8")
    with pytest.raises(StoreError, match="not valid JSON"):
        HistoryStore(str(broken)).load()


def test_make_entry_metadata_overrides(tmp_path):
    summary = summarize(scan_records([Record(id="a", text=POLITE_ANSWER, model="auto")]))
    entry = make_entry(summary, label="x", created_at="2026-07-02T00:00:00Z",
                       model="forced", prompt_version="p9")
    assert entry.summary.model == "forced"
    assert entry.summary.prompt_version == "p9"
    assert entry.summary.total == summary.total
