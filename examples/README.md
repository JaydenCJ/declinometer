# Examples

- `outputs_v1.jsonl` / `outputs_v2.jsonl` — the same twelve outputs as
  produced under "prompt v1" and "prompt v2" of a fictional assistant.
  v2 deliberately over-refuses: three cases flip to `refusal`, one to
  `partial`, one to `hedged`. Both files are plain JSON Lines with
  `id`, `model`, `prompt_version`, and `output` fields.
- `version_watch.py` — a runnable end-to-end demo of the library API:
  scans both fixtures, logs them into a history file, prints the trend
  table, and diffs the two runs. Prints `DEMO OK` on success.

Run the demo from the repository root (no install needed, zero runtime
dependencies):

```bash
PYTHONPATH=src python3 examples/version_watch.py /tmp/declinometer-demo
```

Or exercise the same fixtures through the CLI:

```bash
declinometer rate examples/outputs_v1.jsonl examples/outputs_v2.jsonl --by prompt_version
declinometer diff examples/outputs_v1.jsonl examples/outputs_v2.jsonl
```

`diff` exits with code 1 here — the fixtures contain a real regression.
