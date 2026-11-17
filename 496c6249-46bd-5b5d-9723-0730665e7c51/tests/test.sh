#!/usr/bin/env bash
# Verifier entry point. Order: judge-variable and lineage guard, one
# serial measurement (the submission is rebuilt as a builder uid and every run of submission
# code is demoted to a restricted runner uid), the compiled criteria alone, and the judged
# criteria only when every gate held (G1 to G4, and a compiled speed credit above zero, G5).
# Reward = 0 when a gate fails, else 0.9 * C + 0.1 * J, as the weights of
# tests/reward.toml; C = 2/3 speed credit + 1/3 correctness, constraint and craft items at 1.0 each. With no judge
# configured (OPENAI_API_KEY unset) the reward is C alone. Reward Kit writes every reward byte, except the gate-closed
# record, which judge_guard.py derives from the compiled one; this script writes none.
# The compiled record and its per-item verdicts stay under /logs/verifier/compiled/.
#
# The compiled-only local diagnostic is a separate script, /opt/kraken/compiled_only.sh
# (tests/compiled_only.sh in the bundle); Harbor runs only this graded path.
set -uo pipefail

V=/logs/verifier
RK=/opt/rk/bin/rewardkit
GUARD="/opt/rk/bin/python /opt/kraken/judge_guard.py"
STAGE=/opt/kraken/rk-stage
export PYTHONDONTWRITEBYTECODE=1
# Fail closed: whatever path ends this script, a missing reward file becomes reward 0.0.
trap '[ -s "$V/reward.json" ] || echo "{\"reward\": 0.0}" > "$V/reward.json"; [ -s "$V/reward.txt" ] || /opt/rk/bin/python -c "import json,sys; print(float(json.load(open(sys.argv[1]))[\"reward\"]))" "$V/reward.json" > "$V/reward.txt" 2>/dev/null || echo 0.0 > "$V/reward.txt"' EXIT

mkdir -p "$V"
rm -rf "$V/reward.json" "$V/reward.txt" "$V/judge-fallback.json" "$V/reward-details.json" "$V/measure.json" "$V/verifier-error.json" \
  "$V/judge-lineage.json" "$V/evidence" "$V/compiled" "$V/ctrf.json"
chmod 0755 "$V"

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
[ -s "$V/measure.json" ] || verifier_error measurement-record-missing
# The CTRF report names each declared cheat check (/tests/cheat-checks.json), one per red line.
/opt/venv/bin/python /opt/kraken/harness/ctrf.py "$V/measure.json" "$V/ctrf.json" \
  || verifier_error ctrf-report-failed
# A harness file that disagrees with the bundle before any submission code ran is an
# image/bundle mismatch the agent cannot cause: a verifier error, never a red line.
if grep -q '"harness-integrity-mismatch-before-run"' "$V/measure.json"; then
  verifier_error harness-integrity-mismatch
fi

# Compiled criteria first, alone; their record stays under compiled/ for audit.
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp /tests/test_output.py /tests/diag_correctness.py /tests/diag_speedup.py "$STAGE/"
cp /opt/kraken/reward.compiled.toml "$STAGE/reward.toml"
"$RK" "$STAGE" --workspace /app/numpy --output "$V/compiled/reward.json" > "$V/rewardkit-compiled.log" 2>&1 \
  || verifier_error rewardkit-compiled-failed
[ -s "$V/compiled/reward.json" ] || verifier_error rewardkit-compiled-no-output
GATE="$($GUARD gate "$V/compiled/reward.json" "$V/compiled/reward-details.json")"
rm -rf "$STAGE"

if [ "$GATE" = open ]; then
  # Every gate held: the judged criteria run beside the compiled ones (reward.toml 90/10),
  # or, with no judge configured, the compiled record is the reward.
  if [ "$JUDGE" = off ]; then
    cp "$V/compiled/reward.json" "$V/reward.json"
    cp "$V/compiled/reward-details.json" "$V/reward-details.json" 2>/dev/null || true
  else
    if "$RK" /tests --workspace /app/numpy --output "$V/reward.json" > "$V/rewardkit.log" 2>&1 \
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
  # A gate failed (build, covering test, correctness, red line, or no class clears tau):
  # reward 0.0, no judge is called.
  $GUARD zero "$V/compiled/reward.json" "$V/reward.json" || verifier_error zero-record-failed
fi
[ -s "$V/reward.json" ] || verifier_error rewardkit-no-output
/opt/rk/bin/python -c 'import json,sys; print(float(json.load(open(sys.argv[1]))["reward"]))' \
  "$V/reward.json" > "$V/reward.txt" || verifier_error reward-txt-failed
cat "$V/reward.json"
exit 0
