#!/bin/bash
# Harbor verifier for SWE-Perf-style performance-optimization tasks.
# Grades via /tests/measure.py using the SWE-fficiency SR formula
# (arXiv:2511.06090 §2.3). Failure paths route through measure.py so
# every trial writes a dense, paper-faithful reward.
set -o pipefail

LOGS_DIR="/logs/verifier"
mkdir -p "$LOGS_DIR"

source /opt/miniconda3/etc/profile.d/conda.sh
conda activate testbed
cd /testbed

TARGET_SPEEDUP=1.02
INSTANCE_ID="networkx__networkx-7971"

# Paper-faithful no-op clamp: SR = max(1/target, SR_MIN).
# Used for empty/failed agent patches (LM produced nothing usable).
emit_noop() {
    local status="$1"
    python /tests/measure.py --noop-reward \
        --target-speedup "$TARGET_SPEEDUP" \
        --instance-id "$INSTANCE_ID" \
        --status "$status" \
        --reward-path "$LOGS_DIR/reward.txt" \
        --result-path "$LOGS_DIR/result.json"
}

# Task infra failure (test_patch won't apply, workload crashes).
# Writes SR_MIN=0.001 directly. Not the agent's fault.
emit_infra_fail() {
    local status="$1"
    echo "0.001" > "$LOGS_DIR/reward.txt"
    printf '{"status": "%s", "reward": 0.001, "instance_id": "%s"}\n' \
        "$status" "$INSTANCE_ID" > "$LOGS_DIR/result.json"
}

# No test_patch for this instance (covering tests exist at base_commit).

# 1) Snapshot the agent's changes as a patch we can re-apply after reset.
git add -A
git diff --no-color --cached harbor-base > "$LOGS_DIR/agent_patch.diff" || true
PATCH_SIZE=$(wc -c < "$LOGS_DIR/agent_patch.diff")
echo "Agent patch size: $PATCH_SIZE bytes"

if [ "$PATCH_SIZE" -eq 0 ]; then
    emit_noop "empty_patch"
    exit 0
fi

# 2) Baseline: reset, [apply test_patch,] rebuild, time.
git reset --hard harbor-base
git clean -fdx -e .venv -e "*.egg-info"
# (no test_patch to apply)
pip install -e . > "$LOGS_DIR/rebuild_base.log" 2>&1 || true
python /tests/workload.py > "$LOGS_DIR/baseline.out" 2>&1 || true
BASELINE_MEAN=$(python /tests/measure.py --extract "$LOGS_DIR/baseline.out")
echo "Baseline mean: $BASELINE_MEAN"

# 3) Optimized: reset, apply agent patch, [apply test_patch,] rebuild.
git reset --hard harbor-base
git clean -fdx -e .venv -e "*.egg-info"
if ! git apply --verbose "$LOGS_DIR/agent_patch.diff" \
    && ! git apply --verbose --ignore-space-change "$LOGS_DIR/agent_patch.diff"; then
    emit_noop "agent_patch_failed"
    exit 0
fi
# (no test_patch to apply)
pip install -e . > "$LOGS_DIR/rebuild_agent.log" 2>&1 || true

# 4) Correctness gate: covering tests must pass on the patched code.
set +e
pytest networkx/algorithms/components/tests/test_connected.py networkx/algorithms/components/tests/test_weakly_connected.py 2>&1 | tee "$LOGS_DIR/test_output.txt"
TEST_STATUS=${PIPESTATUS[0]}
set -e
echo "Test exit status: $TEST_STATUS"

# 5) Optimized timing.
python /tests/workload.py > "$LOGS_DIR/optimized.out" 2>&1 || true
OPTIMIZED_MEAN=$(python /tests/measure.py --extract "$LOGS_DIR/optimized.out")
echo "Optimized mean: $OPTIMIZED_MEAN"

# 6) Grade via SWE-fficiency SR formula.
python /tests/measure.py \
    --baseline "$BASELINE_MEAN" \
    --optimized "$OPTIMIZED_MEAN" \
    --target-speedup "$TARGET_SPEEDUP" \
    --test-status "$TEST_STATUS" \
    --instance-id "$INSTANCE_ID" \
    --reward-path "$LOGS_DIR/reward.txt" \
    --result-path "$LOGS_DIR/result.json"

exit 0
