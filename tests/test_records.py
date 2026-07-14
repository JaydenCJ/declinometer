"""JSONL loading: field detection, metadata, and precise error locations."""

import pytest

from declinometer import Record, RecordError, read_records
from declinometer.records import iter_records

from conftest import make_record


def test_reads_records_with_metadata(jsonl_file):
    path = jsonl_file([make_record("a", "hello", model="m1", prompt_version="p2")])
    (rec,) = read_records(path)
    assert rec == Record(id="a", text="hello", model="m1", prompt_version="p2", line_no=1)


def test_text_field_fallback_order():
    # 'output' wins over 'text' when both are present; each alias works alone.
    recs = list(iter_records([
        '{"output": "from-output", "text": "shadowed"}',
        '{"text": "from-text"}',
        '{"completion": "from-completion"}',
        '{"response": "from-response"}',
        '{"content": "from-content"}',
    ]))
    assert [r.text for r in recs] == [
        "from-output", "from-text", "from-completion", "from-response", "from-content",
    ]


def test_pinned_text_field_ignores_aliases():
    with pytest.raises(RecordError, match="no text field"):
        list(iter_records(['{"output": "x"}'], text_field="answer"))
    (rec,) = iter_records(['{"answer": "y", "output": "x"}'], text_field="answer")
    assert rec.text == "y"


def test_bare_json_strings_and_blank_lines():
    recs = list(iter_records(['"just text"', "", "   ", '"more"']))
    assert [(r.id, r.text) for r in recs] == [("line-1", "just text"), ("line-4", "more")]


def test_invalid_json_reports_source_and_line(jsonl_file, tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"output": "ok"}\n{broken\n', encoding="utf-8")
    with pytest.raises(RecordError) as exc:
        read_records(str(path))
    assert exc.value.line_no == 2
    assert str(path) in str(exc.value)


def test_wrong_shapes_are_errors():
    with pytest.raises(RecordError, match="expected an object or string"):
        list(iter_records(["[1, 2, 3]"]))
    with pytest.raises(RecordError, match="no text field"):
        list(iter_records(['{"output": 42}']))  # non-string text


def test_missing_id_falls_back_to_line_number_and_numeric_ids_stringify():
    recs = list(iter_records([
        '{"output": "a"}',
        '{"id": 7, "output": "b"}',
        '{"case_id": "c-9", "output": "c"}',
    ]))
    assert [r.id for r in recs] == ["line-1", "7", "c-9"]

