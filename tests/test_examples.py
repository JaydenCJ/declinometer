"""The shipped example fixtures must keep telling the story the README tells."""

import os
import subprocess
import sys

from declinometer import diff_runs, read_records, scan_records, summarize

from conftest import EXAMPLES_DIR, REPO_ROOT


def test_example_fixtures_encode_a_real_regression():
    v1 = summarize(scan_records(read_records(os.path.join(EXAMPLES_DIR, "outputs_v1.jsonl"))))
    v2 = summarize(scan_records(read_records(os.path.join(EXAMPLES_DIR, "outputs_v2.jsonl"))))
    assert v1.total == v2.total == 12
    assert v1.counts == {"refusal": 1, "partial": 0, "hedged": 1, "comply": 10}
    assert v2.counts == {"refusal": 4, "partial": 1, "hedged": 2, "comply": 5}
    diff = diff_runs(v1, v2)
    assert diff.regressed
    assert [rid for rid, _, _ in diff.worsened_flips] == [
        "case-04", "case-06", "case-10", "case-02", "case-08",
    ]


def test_version_watch_demo_prints_demo_ok(tmp_path):
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO_ROOT, "src"))
    proc = subprocess.run(
        [sys.executable, os.path.join(EXAMPLES_DIR, "version_watch.py"), str(tmp_path)],
        capture_output=True, text=True, env=env, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "DEMO OK" in proc.stdout
    assert "verdict: REGRESSION" in proc.stdout
    assert (tmp_path / "history.json").exists()
