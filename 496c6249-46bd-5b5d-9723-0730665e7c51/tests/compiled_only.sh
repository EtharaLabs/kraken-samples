#!/usr/bin/env bash
# Local compiled-only diagnostic, installed at /opt/kraken/compiled_only.sh (outside /tests);
# Harbor never runs it. It needs no judge variables: one serial measurement and the compiled
# criteria alone, exactly as /tests/test.sh runs them, then the run ends as a verifier error
# (reason compiled-only-diagnostic) that names the compiled credit. It never writes a reward.
set -uo pipefail

V=/logs/verifier
RK=/opt/rk/bin/rewardkit
GUARD="/opt/rk/bin/python /opt/kraken/judge_guard.py"
STAGE=/opt/kraken/rk-stage
export PYTHONDONTWRITEBYTECODE=1

mkdir -p "$V"
rm -rf "$V/reward.json" "$V/reward-details.json" "$V/measure.json" "$V/verifier-error.json" \
  "$V/judge-lineage.json" "$V/evidence" "$V/compiled" "$V/ctrf.json"
chmod 0755 "$V"

verifier_error() {
  rm -f "$V/reward.json"
  [ -s "$V/verifier-error.json" ] || printf '{"verifier_error": true, "reason": "%s"}\n' "$1" > "$V/verifier-error.json"
  echo "verifier error: $1" >&2
  exit 3
}

/opt/venv/bin/python /opt/kraken/harness/measure.py > "$V/measure.stdout" 2> "$V/measure.stderr"
[ -s "$V/measure.json" ] || verifier_error measurement-record-missing
/opt/venv/bin/python /opt/kraken/harness/ctrf.py "$V/measure.json" "$V/ctrf.json" \
  || verifier_error ctrf-report-failed
if grep -q '"harness-integrity-mismatch-before-run"' "$V/measure.json"; then
  verifier_error harness-integrity-mismatch
fi

rm -rf "$STAGE" && mkdir -p "$STAGE"
cp /tests/test_output.py /tests/diag_correctness.py /tests/diag_speedup.py "$STAGE/"
cp /opt/kraken/reward.compiled.toml "$STAGE/reward.toml"
"$RK" "$STAGE" --workspace /app/numpy --output "$V/compiled/reward.json" > "$V/rewardkit-compiled.log" 2>&1 \
  || verifier_error rewardkit-compiled-failed
[ -s "$V/compiled/reward.json" ] || verifier_error rewardkit-compiled-no-output
GATE="$($GUARD gate "$V/compiled/reward.json" "$V/compiled/reward-details.json")"
rm -rf "$STAGE"

cat "$V/compiled/reward.json"
echo "gate: $GATE" >&2
$GUARD diagnostic "$V/compiled/reward.json"
verifier_error compiled-only-diagnostic
