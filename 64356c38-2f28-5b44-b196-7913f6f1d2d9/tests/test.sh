#!/usr/bin/env bash
# Verifier entry point. Order: judge-variable guard, one serial measurement
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
rm -rf "$V/reward.json" "$V/reward-details.json" "$V/measure.json" "$V/verifier-error.json" "$V/evidence" "$V/compiled"
chmod 0755 "$V"

verifier_error() {
  rm -f "$V/reward.json"
  [ -s "$V/verifier-error.json" ] || printf '{"verifier_error": true, "reason": "%s"}\n' "$1" > "$V/verifier-error.json"
  echo "verifier error: $1" >&2
  exit 3
}

$GUARD guard || verifier_error judge-guard-refused

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
  # Every gate held: the judged criteria run beside the compiled ones.
  "$RK" /tests --workspace /app/pennylane --output "$V/reward.json" > "$V/rewardkit.log" 2>&1 \
    || verifier_error judge-unavailable
  $GUARD judged "$V/reward-details.json" || verifier_error judge-unavailable
else
  # A gate failed (red line, correctness, or no family clears tau): reward 0.0, no judge.
  $GUARD zero "$V/compiled/reward.json" "$V/reward.json" || verifier_error zero-record-failed
fi
[ -s "$V/reward.json" ] || verifier_error rewardkit-no-output
cat "$V/reward.json"
exit 0
