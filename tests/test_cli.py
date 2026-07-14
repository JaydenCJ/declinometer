"""End-to-end CLI behavior through main(): exit codes, output, error paths."""

import json

import pytest

from declinometer import __version__
from declinometer.cli import main

from conftest import HARD_REFUSAL, PARTIAL_ANSWER, POLITE_ANSWER, make_record


def run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# -- scan ---------------------------------------------------------------


def test_scan_file_reports_verdict_and_honors_thresholds(tmp_path, capsys):
    path = tmp_path / "out.txt"
    path.write_text(HARD_REFUSAL, encoding="utf-8")
    code, out, _ = run(capsys, "scan", str(path))
    assert code == 0
    assert out.startswith("verdict: refusal")

    soft = tmp_path / "soft.txt"
    soft.write_text("As an AI, here is the plan.", encoding="utf-8")
    _, out, _ = run(capsys, "scan", str(soft))
    assert out.startswith("verdict: comply")
    _, out, _ = run(capsys, "scan", str(soft), "--refusal-threshold", "1.0")
    assert out.startswith("verdict: refusal")


def test_scan_stdin_json_and_explain(tmp_path, capsys, monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(HARD_REFUSAL))
    code, out, _ = run(capsys, "scan", "--json")
    assert code == 0
    data = json.loads(out)
    assert data["verdict"] == "refusal"
    assert any(s["pattern_id"] == "cannot_verb" for s in data["signals"])


def test_scan_fail_on_declined_gates_partial_too(tmp_path, capsys):
    path = tmp_path / "out.txt"
    path.write_text(PARTIAL_ANSWER, encoding="utf-8")
    assert run(capsys, "scan", str(path))[0] == 0
    assert run(capsys, "scan", str(path), "--fail-on-declined")[0] == 1


def test_scan_missing_file_exits_2(capsys):
    code, _, err = run(capsys, "scan", "/nonexistent/output.txt")
    assert code == 2
    assert "declinometer: error:" in err


# -- rate ---------------------------------------------------------------


def test_rate_groups_by_prompt_version(jsonl_file, capsys):
    path = jsonl_file([
        make_record("a", POLITE_ANSWER, prompt_version="v1"),
        make_record("b", HARD_REFUSAL, prompt_version="v2"),
        make_record("c", POLITE_ANSWER, prompt_version="v2"),
    ])
    code, out, _ = run(capsys, "rate", path, "--by", "prompt_version")
    assert code == 0
    lines = out.splitlines()
    assert lines[0].split()[:2] == ["prompt_version", "outputs"]
    v2 = next(line for line in lines if line.startswith("v2"))
    assert "50.0%" in v2


def test_rate_json_format(jsonl_file, capsys):
    path = jsonl_file([make_record("a", HARD_REFUSAL)])
    code, out, _ = run(capsys, "rate", path, "--format", "json")
    assert code == 0
    data = json.loads(out)
    assert data["groups"][0]["key"] == {"model": "demo-model", "prompt_version": "v1"}
    assert data["groups"][0]["counts"]["refusal"] == 1


def test_rate_error_paths_exit_2_with_context(jsonl_file, tmp_path, capsys):
    ok = jsonl_file([make_record("a", POLITE_ANSWER)])
    code, _, err = run(capsys, "rate", ok, "--by", "temperature")
    assert code == 2
    assert "temperature" in err

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"output": "fine"}\nnot json\n', encoding="utf-8")
    code, _, err = run(capsys, "rate", str(bad))
    assert code == 2
    assert ":2:" in err  # names the offending line


# -- log / history --------------------------------------------------------


def test_log_then_history_round_trip(jsonl_file, tmp_path, capsys):
    db = str(tmp_path / "history.json")
    v1 = jsonl_file([make_record("a", POLITE_ANSWER)], "v1.jsonl")
    v2 = jsonl_file([make_record("a", HARD_REFUSAL)], "v2.jsonl")

    code, out, _ = run(capsys, "log", v1, "--db", db, "--label", "v1",
                       "--now", "2026-07-01T00:00:00Z")
    assert code == 0 and "logged 'v1'" in out
    code, _, _ = run(capsys, "log", v2, "--db", db, "--label", "v2",
                     "--now", "2026-07-08T00:00:00Z")
    assert code == 0

    code, out, _ = run(capsys, "history", "--db", db)
    assert code == 0
    assert "+100.0 pp" in out

    # duplicate label refused without --force, accepted with it
    code, _, err = run(capsys, "log", v1, "--db", db, "--label", "v1",
                       "--now", "2026-07-09T00:00:00Z")
    assert code == 2 and "already exists" in err
    code, _, _ = run(capsys, "log", v1, "--db", db, "--label", "v1", "--force",
                     "--now", "2026-07-09T00:00:00Z")
    assert code == 0

    # an empty/missing db is an explicit error, not an empty table
    code, _, err = run(capsys, "history", "--db", str(tmp_path / "none.json"))
    assert code == 2 and "no runs logged" in err


# -- diff -----------------------------------------------------------------


def test_diff_jsonl_files_exit_1_on_regression(jsonl_file, capsys):
    v1 = jsonl_file([make_record("a", POLITE_ANSWER), make_record("b", POLITE_ANSWER)], "v1.jsonl")
    v2 = jsonl_file([make_record("a", HARD_REFUSAL), make_record("b", POLITE_ANSWER)], "v2.jsonl")
    code, out, _ = run(capsys, "diff", v1, v2)
    assert code == 1
    assert "verdict: REGRESSION" in out
    assert "a: comply -> refusal" in out

    # within tolerance the same diff passes
    code, out, _ = run(capsys, "diff", v1, v2, "--tolerance", "60")
    assert code == 0
    assert "verdict: OK" in out


def test_diff_by_labels_from_history(jsonl_file, tmp_path, capsys):
    db = str(tmp_path / "history.json")
    v1 = jsonl_file([make_record("a", POLITE_ANSWER)], "v1.jsonl")
    v2 = jsonl_file([make_record("a", HARD_REFUSAL)], "v2.jsonl")
    run(capsys, "log", v1, "--db", db, "--label", "v1", "--now", "2026-07-01T00:00:00Z")
    run(capsys, "log", v2, "--db", db, "--label", "v2", "--now", "2026-07-08T00:00:00Z")

    code, out, _ = run(capsys, "diff", "v1", "v2", "--db", db, "--format", "json")
    assert code == 1
    data = json.loads(out)
    assert data["regressed"] is True
    assert data["flips"] == [{"id": "a", "a": "comply", "b": "refusal"}]

    code, _, err = run(capsys, "diff", "v1", "missing", "--db", db)
    assert code == 2
    assert "missing" in err


# -- misc -----------------------------------------------------------------


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"declinometer {__version__}"


def test_no_command_prints_help_and_exits_2(capsys):
    code = main([])
    out = capsys.readouterr().out
    assert code == 2
    assert "scan" in out and "diff" in out
