"""Reward arithmetic for tests/test.sh. Reads only the measurement record.

usage: score.py compiled            -> writes /logs/verifier/compiled.json, prints open|closed|error
       score.py final [judged.json] -> writes /logs/verifier/reward.json and reward.txt

Family speed score S_f for f in F1, F2, F3: over that family's hidden cases, the
median of clamp(ln(T_base / T_sub) / ln(T_base / T_ref), 0, 1), where T is the median
of the repeated timings of the case, each in a fresh process. A speedup over base
below the calibrated noise band counts as no speedup (0), and a submission within the
noise band of the reference counts as the reference (1). S_f is 0 when any case of f
is not equivalent to the base output or the submission's run fails.
Judged score J: the weighted mean of the judged items of tests/judge.toml, 0 for an
empty diff.
With no judge configured: reward = (0.25 S_F1 + 0.40 S_F2 + 0.20 S_F3) / 0.85.
With a judge configured: reward = 0.25 S_F1 + 0.40 S_F2 + 0.20 S_F3 + 0.15 J.
A red line or a failed covering test sets the reward to 0. No term multiplies J by
any speed score.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

V = Path("/logs/verifier")
MEASURE = V / "measure.json"
COMPILED = V / "compiled.json"
CONFIG = Path("/opt/harness/bin/config.json")


def case_score(case: dict, band: float) -> float | None:
    """None when the case cannot discriminate (reference within twice the band of base)."""
    tb, tr, ts = (
        case.get("base_median"),
        case.get("expert_median"),
        case.get("patch_median"),
    )
    if not tb or not tr or "expert_departs" in case:
        return None
    ref_gain = math.log(tb / tr)
    if ref_gain <= 2 * band:
        return None
    if not ts:
        return 0.0
    if math.log(ts / tr) <= band:
        return 1.0
    gain = math.log(tb / ts)
    if gain <= band:
        return 0.0
    return min(1.0, max(0.0, gain / ref_gain))


def family_score(slot: dict) -> tuple[float | None, dict]:
    band = slot["noise_band"]
    detail: dict = {"noise_band": band, "seed": slot["seed"]}
    scores = [case_score(c, band) for c in slot["cases"]]
    detail["case_scores"] = [None if s is None else round(s, 4) for s in scores]
    informative = [s for s in scores if s is not None]
    if not informative:
        detail["error"] = "no discriminating case"
        return None, detail
    if slot.get("patch_failures"):
        detail["zero"] = "submission run failed"
        return 0.0, detail
    bad = [
        i
        for i, c in enumerate(slot["cases"])
        if "patch_diff" in c or not c.get("patch")
    ]
    if bad:
        detail["zero"] = f"cases not equivalent to base: {bad}"
        return 0.0, detail
    return statistics.median(informative), detail


def compiled() -> str:
    config = json.loads(CONFIG.read_text())
    out: dict = {"gate": "error", "reasons": []}
    try:
        record = json.loads(MEASURE.read_text())
    except (OSError, ValueError) as exc:
        out["reasons"].append(f"measurement unreadable: {type(exc).__name__}")
        COMPILED.write_text(json.dumps(out, indent=1))
        return "error"
    if record.get("status") != "ok":
        out["reasons"] += [str(r)[:600] for r in record.get("reasons", [])]
        COMPILED.write_text(json.dumps(out, indent=1))
        return "error"
    families, details = {}, {}
    for fam, meta in config["families"].items():
        score, detail = family_score(record["families"][fam])
        details[fam] = detail
        if score is None:
            out["reasons"].append(f"{fam}: {detail['error']}")
        families[fam] = score
    out["families"] = {
        k: (None if v is None else round(v, 4)) for k, v in families.items()
    }
    out["detail"] = details
    if out["reasons"]:
        COMPILED.write_text(json.dumps(out, indent=1))
        return "error"
    speed = sum(config["families"][f]["weight"] * families[f] for f in families)
    out["speed_part"] = round(speed, 6)
    out["compiled_reward"] = round(speed / (1.0 - config["judge_weight"]), 6)
    out["empty_diff"] = not record["tree"].get("applied")
    closed = []
    if record.get("red_lines"):
        closed.append("red line: " + ",".join(sorted(record["red_lines"])))
    tests = record.get("tests", {})
    if not tests.get("collected") or tests.get("failures"):
        closed.append("covering tests failed")
    out["gate"] = "closed" if closed else "open"
    out["reasons"] = closed
    COMPILED.write_text(json.dumps(out, indent=1, sort_keys=True))
    return out["gate"]


def final(judged: Path | None) -> None:
    config = json.loads(CONFIG.read_text())
    record = json.loads(COMPILED.read_text())
    if record.get("gate") != "open":
        reward, how = 0.0, "gate closed"
    elif judged is None:
        reward, how = record["compiled_reward"], "compiled only (no judge)"
    else:
        j = (
            0.0
            if record.get("empty_diff")
            else float(json.loads(judged.read_text())["reward"])
        )
        reward, how = (
            record["speed_part"] + config["judge_weight"] * j,
            f"compiled plus judge J={j}",
        )
    reward = round(min(1.0, max(0.0, reward)), 6)
    (V / "reward.txt").write_text(f"{reward}\n")
    (V / "reward.json").write_text(json.dumps({"reward": reward}))
    print(f"reward={reward} ({how})")


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["compiled"]:
            print(compiled())
        case ["final"]:
            final(None)
        case ["final", path]:
            final(Path(path))
        case _:
            raise SystemExit(__doc__)
