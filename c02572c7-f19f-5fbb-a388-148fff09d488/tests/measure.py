#!/usr/bin/env python3
"""Extract workload timings and compute a dense Harbor reward.

Reward formula: SWE-fficiency Speedup Ratio (SR)
  He et al., "SWE-fficiency: Can Language Models Optimize Real-World
  Repositories?" arXiv:2511.06090 §2.3.

    Speedup_LM   = baseline_mean / optimized_mean
    Speedup_gold = target_speedup (from corpus)
    SR           = Speedup_LM / Speedup_gold
    SR           = max(SR, SR_MIN)                       # SR_MIN = 0.001

Empty-patch / failed-patch / failed-tests behavior (per paper):
    SR = max(1 / Speedup_gold, SR_MIN)   # clamp to no-op baseline
The no-op baseline represents "LM did nothing successful" → Speedup_LM = 1.

Three modes:
  --extract <path>       Print the last mean value found in a workload log.
  --noop-reward          Emit the no-op clamp without running a workload.
                         Required: --target-speedup, --instance-id,
                                   --reward-path, --result-path.
                         Optional: --status (default: "noop_clamp").
  <grading args>         Compare baseline vs optimized, write reward + result.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MEAN_RE = re.compile(r"Mean:\s*([0-9]+\.?[0-9]*(?:[eE][-+]?[0-9]+)?)")

SR_MIN = 0.001  # SWE-fficiency §2.3 per-instance floor


def extract_mean(log_path: str) -> float | None:
    text = Path(log_path).read_text(errors="replace")
    matches = MEAN_RE.findall(text)
    if not matches:
        return None
    return float(matches[-1])


def clamp_noop(target_speedup: float) -> float:
    """Reward when the LM effectively did nothing (or broke things)."""
    return max(1.0 / target_speedup, SR_MIN)


def write_noop(target: float, instance_id: str | None, status: str,
               reward_path: str, result_path: str) -> int:
    reward = clamp_noop(target)
    result = {
        "instance_id": instance_id,
        "target_speedup": target,
        "status": status,
        "sr_min": SR_MIN,
        "reward_formula": (
            "SR = max(1/target_speedup, SR_MIN) [no-op clamp; "
            "SWE-fficiency arXiv:2511.06090 §2.3]"
        ),
        "reward": reward,
    }
    Path(reward_path).write_text(f"{reward:.9g}")
    Path(result_path).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", help="Print the last Mean: value from a log file")
    parser.add_argument("--noop-reward", action="store_true",
                        help="Emit no-op clamp SR = max(1/target, SR_MIN)")
    parser.add_argument("--status", type=str, default="noop_clamp",
                        help="Status label to record with a noop-reward call")
    parser.add_argument("--baseline", type=str)
    parser.add_argument("--optimized", type=str)
    parser.add_argument("--target-speedup", type=float)
    parser.add_argument("--test-status", type=int)
    parser.add_argument("--instance-id", type=str)
    parser.add_argument("--reward-path", type=str)
    parser.add_argument("--result-path", type=str)
    args = parser.parse_args()

    if args.extract:
        mean = extract_mean(args.extract)
        print("" if mean is None else f"{mean:.9g}")
        return 0

    if args.noop_reward:
        for k in ("target_speedup", "reward_path", "result_path"):
            if getattr(args, k) is None:
                print(f"--noop-reward requires --{k.replace('_', '-')}", file=sys.stderr)
                return 2
        return write_noop(
            args.target_speedup, args.instance_id, args.status,
            args.reward_path, args.result_path,
        )

    required = [
        args.baseline,
        args.optimized,
        args.target_speedup,
        args.test_status,
        args.reward_path,
        args.result_path,
    ]
    if any(v is None for v in required):
        print("Missing grading arguments", file=sys.stderr)
        return 2

    def to_float(value: str) -> float | None:
        value = (value or "").strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    baseline = to_float(args.baseline)
    optimized = to_float(args.optimized)
    target = args.target_speedup

    result: dict = {
        "instance_id": args.instance_id,
        "target_speedup": target,
        "baseline_mean_sec": baseline,
        "optimized_mean_sec": optimized,
        "test_status": args.test_status,
        "sr_min": SR_MIN,
        "reward_formula": "SR = measured_speedup / target_speedup (SWE-fficiency arXiv:2511.06090)",
    }

    if baseline is None or optimized is None:
        result["status"] = "workload_failed"
        reward = SR_MIN
    elif optimized <= 0:
        result["status"] = "invalid_timing"
        reward = SR_MIN
    else:
        measured = baseline / optimized
        result["measured_speedup"] = measured
        if args.test_status != 0:
            result["status"] = "tests_failed"
            reward = clamp_noop(target)
        else:
            sr = measured / target
            reward = max(sr, SR_MIN)
            if measured >= target:
                result["status"] = "passed"
            else:
                result["status"] = "insufficient_speedup"
            result["sr_raw"] = sr

    result["reward"] = reward
    Path(args.reward_path).write_text(f"{reward:.9g}")
    Path(args.result_path).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
