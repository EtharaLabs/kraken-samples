import json
from pathlib import Path

from rewardkit import criterion

MEASURE = Path("/logs/verifier/measure.json")
STATUS = "status"
CLASSES = {'plain': 0.16666666666666666, 'none': 0.16666666666666666, 'nan': 0.16666666666666666, 'str_na': 0.16666666666666666, 'object': 0.16666666666666666, 'mixed': 0.16666666666666666}

def _load():
    try:
        record = json.loads(MEASURE.read_text())
    except (OSError, ValueError) as exc:
        return None, f"G1:measurement-unreadable:{type(exc).__name__}"
    if not isinstance(record, dict) or record.get(STATUS) != "ok":
        reasons = record.get("reasons", []) if isinstance(record, dict) else []
        return None, "G1:measurement-error:" + ";".join(map(str, reasons))[:400]
    return record, ""

def _gates(record):
    fired = sorted(k for k, v in record.get("red_lines", {}).items() if v)
    if fired:
        return "G2:red-line:" + ",".join(fired)
    if record.get("build", {}).get("ok") is not True:
        return "G3:build-failed"
    if record.get("correctness", {}).get("passed") is not True:
        return "G4:correctness-failed"
    return ""

def _class_share(slots, tau, opt):
    """(share, s, r) of one class: s is the worst-case submission speedup over its hidden sizes,
    r the reference speedup at that same size in the same run; share = min(1, (s / r) / opt) once
    s clears tau, else 0. A failed patch run anywhere in the class makes it 0."""
    rows = []
    for slot in slots.values():
        if slot.get("patch_failures") or not all(slot.get(k) for k in ("base", "expert", "patch")):
            return 0.0, 0.0, 0.0
        base, ref, patch = (min(slot[k]) for k in ("base", "expert", "patch"))
        rows.append((base / patch, base / ref))
    if not rows:
        return 0.0, 0.0, 0.0
    s, r = min(rows)
    return (0.0 if s < tau else min(1.0, s / r / opt)), s, r

def _shares(record):
    timing = record.get("timing", {})
    return {name: _class_share(timing.get(name, {}), record["tau"], record["opt_threshold"]) for name in CLASSES}

@criterion
def diag_correctness(workspace: Path) -> dict:
    try:
        record, reason = _load()
        if record is None:
            return {"score": 0.0, "reasoning": reason}
        if record.get("build", {}).get("ok") is not True:
            return {"score": 0.0, "reasoning": "G3:build-failed"}
        if record.get("correctness", {}).get("passed") is not True:
            return {"score": 0.0, "reasoning": "G4:correctness-failed"}
        return {"score": 1.0, "reasoning": "build-and-behavior-hold"}
    except Exception as exc:  # criteria never raise
        return {"score": 0.0, "reasoning": f"criterion-error:{type(exc).__name__}"}
