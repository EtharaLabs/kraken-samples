#!/usr/bin/env bash
# Verifier entry point: one serial measurement (submission code demoted to a restricted
# uid in fresh processes), the compiled score, and the judged items only when a judge is
# configured (OPENAI_API_KEY set). No network is used unless a judge is configured.
#
# Reward formula (identical in task.toml, instruction.md and tests/score.py):
#   Family speed score S_f for f in F1, F2, F3: over that family's hidden cases, the median
#   of clamp(ln(T_base / T_sub) / ln(T_base / T_ref), 0, 1), where T is the median of the
#   repeated timings of the case, each in a fresh process. A speedup over base below the
#   calibrated noise band counts as no speedup (0), and a submission within the noise band
#   of the reference counts as the reference (1). S_f is 0 when any case of f is not
#   equivalent to the base output or the submission's run fails.
#   Judged score J: the weighted mean of the judged items of tests/judge.toml, 0 for an
#   empty diff.
#   With no judge configured: reward = (0.25 S_F1 + 0.40 S_F2 + 0.20 S_F3) / 0.85.
#   With a judge configured:  reward = 0.25 S_F1 + 0.40 S_F2 + 0.20 S_F3 + 0.15 J.
#   A red line or a failed covering test sets the reward to 0. No term multiplies J by any
#   speed score.
set -uo pipefail

V=/logs/verifier
H=/opt/harness
PY=/opt/venv/bin/python
RKPY=/opt/rk/bin/python
STAGE=$H/judge-stage

mkdir -p "$V"
rm -rf "$V/reward.json" "$V/reward.txt" "$V/measure.json" "$V/compiled.json" "$V/evidence" \
  "$V/judged" "$V/judge-fallback.json" "$V/verifier-error.json"
chmod 0755 "$V"
# Fail closed: whatever path ends this script, a missing reward file becomes reward 0.0.
trap '[ -s "$V/reward.json" ] || { echo "{\"reward\": 0.0}" > "$V/reward.json"; echo 0.0 > "$V/reward.txt"; }' EXIT

verifier_error() {
  rm -f "$V/reward.json" "$V/reward.txt"
  printf '{"verifier_error": true, "reason": "%s"}\n' "$1" > "$V/verifier-error.json"
  echo "verifier error: $1" >&2
  exit 3
}

# The judge is optional. With OPENAI_API_KEY unset the reward is the compiled score
# alone and nothing is called over the network.
JUDGE=on
if [ -z "${OPENAI_API_KEY:-}" ]; then
  JUDGE=off
  echo "judge: OPENAI_API_KEY not set; scoring compiled criteria only" >&2
elif ! $RKPY $H/judge_guard.py guard; then
  JUDGE=off
  echo "judge: not an OpenAI judge or no key; scoring compiled criteria only" >&2
fi

$PY $H/bin/measure.py > "$V/measure.stdout" 2> "$V/measure.stderr"
if grep -q '"harness-integrity-mismatch-before-run"' "$V/measure.json" 2>/dev/null; then
  verifier_error harness-integrity-mismatch
fi

GATE=$($PY $H/score.py compiled)
case "$GATE" in
  open|closed) ;;
  *) verifier_error "measurement-error" ;;
esac

if [ "$GATE" = open ] && [ "$JUDGE" = on ] && grep -q '"empty_diff": true' "$V/compiled.json"; then
  # An empty diff is never sent to the judge: J = 0.
  $PY $H/score.py final "$V/judged/not-consulted.json" || verifier_error score-final-failed
elif [ "$GATE" = open ] && [ "$JUDGE" = on ]; then
  rm -rf "$STAGE" && mkdir -p "$STAGE" "$V/judged"
  cp /tests/judge.toml "$STAGE/judge.toml"
  if /opt/rk/bin/rewardkit "$STAGE" --workspace /app/cirq --output "$V/judged/reward.json" \
       > "$V/judged/rewardkit.log" 2>&1 \
     && [ -s "$V/judged/reward.json" ] \
     && $RKPY $H/judge_guard.py judged "$V/judged/reward-details.json"; then
    $PY $H/score.py final "$V/judged/reward.json" || verifier_error score-final-failed
  else
    [ -s "$V/judge-fallback.json" ] \
      || echo '{"judge_fallback": true, "reason": "judge-unavailable"}' > "$V/judge-fallback.json"
    echo "JUDGE UNAVAILABLE (${REWARDKIT_JUDGE:-}): scoring compiled criteria only" >&2
    $PY $H/score.py final || verifier_error score-final-failed
  fi
else
  $PY $H/score.py final || verifier_error score-final-failed
fi
cat "$V/reward.json"
exit 0
