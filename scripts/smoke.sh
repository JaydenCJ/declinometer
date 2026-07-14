#!/usr/bin/env bash
# Smoke test for declinometer: scan a single output, aggregate the example
# fixtures, log two runs into a history file, and verify that the diff gate
# exits non-zero on the regression the fixtures contain.
# Self-contained: pure stdlib, no network, idempotent (works from a clean tree).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# The package has zero runtime dependencies, so running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/declinometer-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. scan: a hard refusal from stdin gets the refusal verdict with evidence.
scan_out="$(printf "I'm sorry, but I can't help with that request. It goes against my guidelines." \
  | "$PYTHON" -m declinometer scan --explain)" || fail "scan exited non-zero"
echo "$scan_out" | sed 's/^/[scan] /'
echo "$scan_out" | grep -q "^verdict: refusal" || fail "scan did not report a refusal"
echo "$scan_out" | grep -q "cannot_verb" || fail "scan --explain missing the matched pattern"

# 2. scan: a plain answer complies, and --fail-on-declined gates a refusal.
printf 'The capital of France is Paris.' \
  | "$PYTHON" -m declinometer scan | grep -q "^verdict: comply" \
  || fail "plain answer should comply"
set +e
printf 'I must decline. I cannot help with that.' \
  | "$PYTHON" -m declinometer scan --fail-on-declined >/dev/null
gate_rc=$?
set -e
[ "$gate_rc" -eq 1 ] || fail "--fail-on-declined should exit 1 on a refusal, got $gate_rc"

# 3. rate: the example fixtures aggregate per prompt version.
rate_out="$("$PYTHON" -m declinometer rate \
  "$ROOT/examples/outputs_v1.jsonl" "$ROOT/examples/outputs_v2.jsonl" \
  --by prompt_version)" || fail "rate exited non-zero"
echo "$rate_out" | sed 's/^/[rate] /'
echo "$rate_out" | grep -E '^v1 +12 +8\.3%' >/dev/null || fail "rate wrong for v1"
echo "$rate_out" | grep -E '^v2 +12 +33\.3%' >/dev/null || fail "rate wrong for v2"

# 4. log: record both runs into a history file with fixed timestamps.
"$PYTHON" -m declinometer log "$ROOT/examples/outputs_v1.jsonl" \
  --db "$WORKDIR/history.json" --label prompt-v1 --now 2026-07-01T09:00:00Z >/dev/null \
  || fail "log prompt-v1 failed"
"$PYTHON" -m declinometer log "$ROOT/examples/outputs_v2.jsonl" \
  --db "$WORKDIR/history.json" --label prompt-v2 --now 2026-07-08T09:00:00Z >/dev/null \
  || fail "log prompt-v2 failed"
[ -f "$WORKDIR/history.json" ] || fail "history file missing"

# 5. history: the trend table shows the declined-rate jump.
hist_out="$("$PYTHON" -m declinometer history --db "$WORKDIR/history.json")"
echo "$hist_out" | sed 's/^/[history] /'
echo "$hist_out" | grep -q "prompt-v2" || fail "history missing prompt-v2"
echo "$hist_out" | grep -q "+33.3 pp" || fail "history missing the trend delta"

# 6. diff: the regression gate exits 1 and names the flipped cases.
set +e
diff_out="$("$PYTHON" -m declinometer diff prompt-v1 prompt-v2 --db "$WORKDIR/history.json")"
diff_rc=$?
set -e
echo "$diff_out" | sed 's/^/[diff] /'
[ "$diff_rc" -eq 1 ] || fail "diff on a regression should exit 1, got $diff_rc"
echo "$diff_out" | grep -q "verdict: REGRESSION" || fail "diff did not report the regression"
echo "$diff_out" | grep -q "case-04: comply -> refusal" || fail "diff did not name a flipped case"

# 7. diff within tolerance passes (exit 0).
"$PYTHON" -m declinometer diff prompt-v1 prompt-v2 \
  --db "$WORKDIR/history.json" --tolerance 50 >/dev/null \
  || fail "diff within tolerance should exit 0"

# 8. the runnable example agrees end to end.
demo_out="$("$PYTHON" "$ROOT/examples/version_watch.py" "$WORKDIR/demo")" \
  || fail "version_watch.py exited non-zero"
echo "$demo_out" | grep -q "DEMO OK" || fail "demo did not finish"

# 9. --version and --help agree with the package.
version_out="$("$PYTHON" -m declinometer --version)"
pkg_version="$("$PYTHON" -c 'import declinometer; print(declinometer.__version__)')"
[ "$version_out" = "declinometer $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"
"$PYTHON" -m declinometer --help | grep -q "diff" || fail "--help missing diff command"

echo "SMOKE OK"
