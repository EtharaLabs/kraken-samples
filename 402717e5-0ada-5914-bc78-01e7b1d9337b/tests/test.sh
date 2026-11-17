#!/usr/bin/env bash
# Verifier entry point. One serial measurement (all submission code demoted to a restricted
# uid in fresh python -I processes), then the compiled criteria through Reward Kit, then,
# only when OPENAI_API_KEY is set and no failure stage fired, the 8 judged criteria of
# tests/judge.toml through Reward Kit. reward = 0.70 x compiled + 0.30 x judged with a judge,
# compiled alone without one or when the judge call fails, and 0 on any red line, covering-test
# failure, correctness failure or unmodified tree. The timing repeats up to three full
# interleaved rounds; when every round's expert-against-expert A/A band exceeds its limit the
# verifier stops with the reason noise_floor. Every path leaves reward.json and reward.txt.
set -uo pipefail

V=/logs/verifier
RK=/opt/rk/bin/rewardkit
STAGE=/opt/kraken/rk-stage
GUARD="/opt/rk/bin/python /opt/kraken/judge_guard.py"

mkdir -p "$V"
rm -rf "$V/reward.json" "$V/reward.json.tmp" "$V/reward-details.json" "$V/measure.json" "$V/verifier-error.json" "$V/evidence" \
  "$V/compiled" "$V/judged" "$V/judge-fallback.json" "$V/reward.txt" "$V/ctrf.json"
chmod 0755 "$V"
# Fail closed: whatever path ends this script, a missing reward file becomes reward 0.0.
trap '[ -s "$V/reward.json" ] || echo "{\"reward\": 0.0}" > "$V/reward.json"; [ -s "$V/reward.txt" ] || echo 0.0 > "$V/reward.txt"' EXIT

verifier_error() {
  rm -f "$V/reward.json" "$V/reward.json.tmp" "$V/reward.txt"
  [ -s "$V/verifier-error.json" ] || printf '{"verifier_error": true, "reason": "%s"}\n' "$1" > "$V/verifier-error.json"
  echo "verifier error: $1" >&2
  exit 3
}

/opt/venv/bin/python -I -B /opt/kraken/harness/measure.py > "$V/measure.stdout" 2> "$V/measure.stderr"
[ -s "$V/measure.json" ] || verifier_error measurement-missing
# A CTRF report naming each cheat check of
# tests/cheat-checks.json (red lines RL1-RL6), passed when the scan found no hit.
/opt/venv/bin/python -I -c 'import json,sys; m=json.load(open(sys.argv[1])); ids=json.load(open(sys.argv[2]))["ids"]; rl=m.get("red_lines") or {}; tests=[{"name": i, "status": "failed" if rl.get(i) else "passed", "duration": 0} for i in ids]; f=sum(t["status"] == "failed" for t in tests); json.dump({"results": {"tool": {"name": "kraken-za-10602-verifier"}, "summary": {"tests": len(tests), "passed": len(tests) - f, "failed": f, "pending": 0, "skipped": 0, "other": 0, "start": 0, "stop": 0}, "tests": tests}}, open(sys.argv[3], "w"))' \
  "$V/measure.json" /tests/cheat-checks.json "$V/ctrf.json" || verifier_error ctrf-write-failed
status="$(/opt/venv/bin/python -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("status"))' "$V/measure.json")"
case "$status" in
  ok) ;;
  noise_floor)
    /opt/venv/bin/python -I -c 'import json,sys; r=json.load(open(sys.argv[1])); s=r.get("speedup") or {}; json.dump({"verifier_error": True, "reason": "noise_floor", "noise_band": s.get("noise_band"), "noise_bands": s.get("noise_bands")}, open(sys.argv[2], "w"))' "$V/measure.json" "$V/verifier-error.json"
    verifier_error noise_floor ;;
  *) verifier_error "measurement-$status" ;;
esac

rm -rf "$STAGE" && mkdir -p "$STAGE"
cp /tests/test_output.py /tests/diag_correctness.py /tests/diag_speedup.py /tests/diag_noise.py \
  /tests/diag_stage.py /tests/reward.toml "$STAGE/"
"$RK" "$STAGE" --workspace /app/statsmodels --output "$V/compiled/reward.json" > "$V/rewardkit.log" 2>&1 \
  || verifier_error rewardkit-failed
[ -s "$V/compiled/reward.json" ] || verifier_error rewardkit-no-output
# The judged criteria run only with a key and only when no failure stage fired; a wrong, failed
# or unmodified submission scores 0 and is never sent to the judge.
FAIL="$(/opt/venv/bin/python -I -c 'import json,sys; print(int(float(json.load(open(sys.argv[1])).get("failure_stage", 1))))' "$V/compiled/reward.json")" \
  || verifier_error compiled-record-unreadable
J=""
if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "judge: OPENAI_API_KEY not set; scoring compiled criteria only" >&2
elif [ "$FAIL" != 0 ]; then
  echo "judge: not consulted (failure stage $FAIL)" >&2
elif ! $GUARD guard; then
  echo "judge: not an OpenAI judge; scoring compiled criteria only" >&2
else
  rm -rf "$STAGE" && mkdir -p "$STAGE" "$V/judged"
  cp /tests/judge.toml "$STAGE/judge.toml"
  if "$RK" "$STAGE" --workspace /app/statsmodels --output "$V/judged/reward.json" > "$V/judged/rewardkit.log" 2>&1 \
       && [ -s "$V/judged/reward.json" ] && $GUARD judged "$V/judged/reward-details.json"; then
    J="$(/opt/venv/bin/python -I -c 'import json,sys; print(float(json.load(open(sys.argv[1]))["reward"]))' "$V/judged/reward.json")" || J=""
  fi
  if [ -z "$J" ]; then
    [ -s "$V/judge-fallback.json" ] \
      || echo '{"judge_fallback": true, "reason": "judge-unavailable"}' > "$V/judge-fallback.json"
    echo "JUDGE UNAVAILABLE (${REWARDKIT_JUDGE:-}): scoring compiled criteria only" >&2
  fi
fi
/opt/venv/bin/python -I -c 'import json,sys; c=json.load(open(sys.argv[1])); C=float(c["reward"]); J=sys.argv[3]; r={"reward": (0.0 if float(c["failure_stage"]) else (min(1.0, max(0.0, 0.70 * C + 0.30 * float(J))) if J else C)), "compiled_score": C, **({"judged_score": float(J)} if J else {}), **{k: c[k] for k in ("correctness", "geomean_speedup_ratio", "noise_band", "failure_stage")}}; open(sys.argv[2] + ".tmp", "w").write(json.dumps(r, sort_keys=True) + "\n")' \
  "$V/compiled/reward.json" "$V/reward.json" "$J" && mv "$V/reward.json.tmp" "$V/reward.json" \
  || verifier_error reward-write-failed
/opt/venv/bin/python -I -c 'import json,sys; print(float(json.load(open(sys.argv[1]))["reward"]))' \
  "$V/reward.json" > "$V/reward.txt" || verifier_error reward-txt-failed
cat "$V/reward.json"
exit 0
