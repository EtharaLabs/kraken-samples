#!/usr/bin/env bash
# Verifier entry point. Order: judge guard (OpenAI key and model), one serial measurement
# (submission code demoted to a restricted uid), the compiled criteria, and the
# judged criteria only when every gate held. Each compiled item scores its own
# relation; the gates act on the reward: when any gate fails, the reward is 0.0
# and no judge is called. The compiled record and its per-item verdicts stay
# under /logs/verifier/compiled/.
set -uo pipefail

V=/logs/verifier
RK=/opt/rk/bin/rewardkit
GUARD="/opt/rk/bin/python /opt/kraken/judge_guard.py"
STAGE=/opt/kraken/rk-stage

mkdir -p "$V"
rm -rf "$V/reward.json" "$V/reward.txt" "$V/judge-fallback.json" "$V/reward-details.json" "$V/measure.json" "$V/verifier-error.json" "$V/evidence" "$V/compiled"
chmod 0755 "$V"
# Fail closed: whatever path ends this script, a missing reward file becomes reward 0.0.
trap '[ -s "$V/reward.json" ] || echo "{\"reward\": 0.0}" > "$V/reward.json"; [ -s "$V/reward.txt" ] || /opt/rk/bin/python -c "import json,sys; print(float(json.load(open(sys.argv[1]))[\"reward\"]))" "$V/reward.json" > "$V/reward.txt" 2>/dev/null || echo 0.0 > "$V/reward.txt"' EXIT

verifier_error() {
  rm -f "$V/reward.json" "$V/reward.txt"
  [ -s "$V/verifier-error.json" ] || printf '{"verifier_error": true, "reason": "%s"}\n' "$1" > "$V/verifier-error.json"
  echo "verifier error: $1" >&2
  exit 3
}

# Judge is optional. With OPENAI_API_KEY unset (a host that provides no judge, such as a
# Smoldata Oracle sandbox), the reward is the compiled score alone and nothing is called
# over the network. A refused binding (not an OpenAI judge) also keeps the compiled reward.
JUDGE=on
if [ -z "${OPENAI_API_KEY:-}" ]; then
  JUDGE=off
  echo "judge: OPENAI_API_KEY not set; scoring compiled criteria only" >&2
elif ! $GUARD guard; then
  JUDGE=off
  echo "judge: not an OpenAI judge; scoring compiled criteria only" >&2
fi

/opt/venv/bin/python /opt/kraken/harness/measure.py > "$V/measure.stdout" 2> "$V/measure.stderr"
# A harness file that already disagrees with the bundle before any submission code ran is an
# image/bundle mismatch the agent cannot cause: a verifier error, never a red line.
if grep -q '"harness-integrity-mismatch-before-run"' "$V/measure.json" 2>/dev/null; then
  verifier_error harness-integrity-mismatch
fi

rm -rf "$STAGE" && mkdir -p "$STAGE"
cp /tests/test_output.py /tests/diag_correctness.py /tests/diag_speedup.py "$STAGE/"
cp /opt/kraken/reward.compiled.toml "$STAGE/reward.toml"
# Compiled criteria first; their record stays under compiled/ for audit.
"$RK" "$STAGE" --workspace /app/pennylane --output "$V/compiled/reward.json" > "$V/rewardkit-compiled.log" 2>&1 \
  || verifier_error rewardkit-compiled-failed
[ -s "$V/compiled/reward.json" ] || verifier_error rewardkit-compiled-no-output

if [ "$($GUARD gate "$V/compiled/reward.json" "$V/compiled/reward-details.json")" = "open" ]; then
  # Every gate held: the judged criteria run beside the compiled ones, or, with no judge
  # configured, the compiled record is the reward.
  if [ "$JUDGE" = off ]; then
    cp "$V/compiled/reward.json" "$V/reward.json"
    cp "$V/compiled/reward-details.json" "$V/reward-details.json" 2>/dev/null || true
  else
  if "$RK" /tests --workspace /app/pennylane --output "$V/reward.json" > "$V/rewardkit.log" 2>&1 \
       && [ -s "$V/reward.json" ] && $GUARD judged "$V/reward-details.json"; then
    :
  else
    # The judge failed: keep the compiled reward; the trial still scores.
    cp "$V/compiled/reward.json" "$V/reward.json"
    cp "$V/compiled/reward-details.json" "$V/reward-details.json" 2>/dev/null || true
    [ -s "$V/judge-fallback.json" ] \
      || echo '{"judge_fallback": true, "reason": "judge-unavailable"}' > "$V/judge-fallback.json"
    echo "JUDGE UNAVAILABLE (${REWARDKIT_JUDGE:-}): scoring compiled criteria only" >&2
  fi
  fi
else
  # A gate failed (red line, correctness, or no family clears tau): reward 0.0, no judge.
  $GUARD zero "$V/compiled/reward.json" "$V/reward.json" || verifier_error zero-record-failed
fi
[ -s "$V/reward.json" ] || verifier_error rewardkit-no-output
/opt/rk/bin/python -c 'import json,sys; print(float(json.load(open(sys.argv[1]))["reward"]))' \
  "$V/reward.json" > "$V/reward.txt" || verifier_error reward-txt-failed
cat "$V/reward.json"
exit 0
