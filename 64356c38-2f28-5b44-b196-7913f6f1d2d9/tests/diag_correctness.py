"""GENERATED SECTION. DO NOT HAND-EDIT."""

import json
import statistics
from pathlib import Path

import rewardkit
from rewardkit import criterion

MEASURE = Path("/logs/verifier/measure.json")
FAMILIES = ('cnot', 'ctrl', 'adj', 'adjctrl', 'prod')
FAMILY_WEIGHTS = {'cnot': 0.125, 'ctrl': 0.125, 'adj': 0.125, 'adjctrl': 0.125, 'prod': 0.5}
TAU = 1.25
KAPPA = 1.2


def _load():
    try:
        record = json.loads(MEASURE.read_text())
    except (OSError, ValueError) as exc:
        return None, f"G1:measurement-unreadable:{type(exc).__name__}"
    status = record.get("status") if isinstance(record, dict) else None
    if status != "ok":
        return None, "G1:measurement-error:" + ";".join(map(str, (record or {}).get("reasons", [])))[:400]
    return record, ""


def _gates(record):
    fired = sorted(k for k, v in record.get("red_lines", {}).items() if v)
    if fired:
        return "G2:red-line:" + ",".join(fired)
    if record.get("correctness", {}).get("passed") is not True:
        return "G3:correctness-failed"
    return ""


def _medians(record, family):
    out = []
    for size, slot in sorted(record["timing"][family].items(), key=lambda kv: int(kv[0])):
        out.append((int(size), min(slot["base"]), min(slot["expert"]),
                    min(slot["patch"])))
    if not out:
        raise KeyError(family)
    return out


def _family_share(record, family):
    worst = None
    for _, slot in sorted(record["timing"][family].items(), key=lambda kv: int(kv[0])):
        if slot.get("patch_failures") or not slot.get("patch"):
            return 0.0
        base, expert, patch = (min(slot[k]) for k in ("base", "expert", "patch"))
        if base / patch < TAU:
            return 0.0
        worst = expert / patch if worst is None else min(worst, expert / patch)
    if worst is None:
        return 0.0
    return 1.0 if worst * KAPPA >= 1.0 else min(1.0, max(0.0, worst))


def _shares(record):
    return {family: _family_share(record, family) for family in FAMILIES}


@criterion
def diag_correctness(workspace: Path) -> dict:
    try:
        record, reason = _load()
        if record is None:
            return {"score": 0.0, "reasoning": reason}
        # Behavior only: red lines are reported by the reward gate and the scan record, not here,
        # so a correct tree that trips a red line still reads correctness 1.0.
        if record.get("correctness", {}).get("passed") is not True:
            return {"score": 0.0, "reasoning": "G3:correctness-failed"}
        return {"score": 1.0, "reasoning": "G1-G3-behavior-hold"}
    except Exception as exc:  # criteria never raise
        return {"score": 0.0, "reasoning": f"criterion-error:{type(exc).__name__}"}
