import json
from pathlib import Path

import rewardkit
from rewardkit import criterion

MEASURE = Path("/logs/verifier/measure.json")
FAILURE_STAGES = {'none': 0, 'red_line': 1, 'unmodified': 2, 'covering_tests': 3, 'correctness': 4, 'timeout': 5}

def _load():
    try:
        record = json.loads(MEASURE.read_text())
    except (OSError, ValueError) as exc:
        return None, f"measurement-unreadable:{type(exc).__name__}"
    if not isinstance(record, dict) or record.get("status") != "ok":
        return None, "measurement-not-ok"
    return record, ""

def _class_equal(record, key, value):
    group = [i for i in record["correctness"]["instances"].values() if i[key] == value]
    return all(i["equal"] for i in group)

RELATIONS = {
    "credit": lambda r: r.get("speedup") is not None,
    "class_well": lambda r: bool(r["correctness"]["instances"]) and _class_equal(r, "class", "well"),
    "class_near": lambda r: bool(r["correctness"]["instances"]) and _class_equal(r, "class", "near"),
    "class_fallback": lambda r: bool(r["correctness"]["instances"]) and _class_equal(r, "class", "fallback"),
    "narrow": lambda r: bool(r["correctness"]["instances"]) and _class_equal(r, "intended", "narrow"),
    "covering_tests": lambda r: r["tests"].get("collected", 0) > 0 and not r["tests"].get("failures"),
    "modified": lambda r: bool(r["tree"]["applied"]),
    "timed_and_probe": lambda r: not r["correctness"]["probe_and_timed_failures"],
}
for _key in ('RL1', 'RL1_integrity', 'RL2', 'RL2_dynamic', 'RL3', 'RL4', 'RL5', 'RL5_dynamic', 'RL6', 'RL6_files'):
    RELATIONS["absent_" + _key] = (lambda k: lambda r: not r["scan"][k])(_key)

def _holds(record):
    return {name: bool(fn(record)) for name, fn in RELATIONS.items()}

def _credit(record):
    speed = record.get("speedup")
    return 0.0 if speed is None else min(1.0, max(0.0, float(speed["harmonic"])))

@criterion
def diag_noise(workspace: Path) -> dict:
    """The expert-against-expert median absolute log ratio of the timed workloads."""
    try:
        record, reason = _load()
        if record is None or record.get("speedup") is None:
            return {"score": 0.0, "reasoning": reason or "not timed"}
        return {"score": float(record["speedup"]["noise_band"]), "reasoning": "aa-median-abs-log-ratio"}
    except Exception as exc:  # criteria never raise
        return {"score": 0.0, "reasoning": f"criterion-error:{type(exc).__name__}"}
