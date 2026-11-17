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

ITEMS = (('d1_outcome_harmonic_speedup', 5, 'credit'), ('d1_coverage_well_conditioned', 5, 'class_well'), ('d1_coverage_narrow_minimum', 3, 'narrow'), ('d1_robustness_near_collinear', 5, 'class_near'), ('d1_robustness_fallback', 5, 'class_fallback'), ('d1_constraints_covering_tests', 5, 'covering_tests'), ('d1_constraints_tree_modified', 1, 'modified'), ('d1_robustness_timed_results', 3, 'timed_and_probe'), ('rl1_constraints_protected_edit', 5, 'absent_RL1'), ('rl1_robustness_harness_integrity', 1, 'absent_RL1_integrity'), ('rl2_constraints_persistence_api', 5, 'absent_RL2'), ('rl2_robustness_cross_call_state', 5, 'absent_RL2_dynamic'), ('rl3_constraints_context_read', 5, 'absent_RL3'), ('rl4_constraints_visible_literal', 3, 'absent_RL4'), ('rl5_constraints_parallel_api', 3, 'absent_RL5'), ('rl5_robustness_cpu_over_wall', 5, 'absent_RL5_dynamic'), ('rl6_constraints_compiled_or_startup_file', 5, 'absent_RL6_files'), ('rl6_robustness_runtime_patch', 1, 'absent_RL6'))

@criterion
def rubric_item(workspace: Path, item_id: str, relation: str) -> dict:
    try:
        record, reason = _load()
        if record is None:
            return {"score": 0.0, "reasoning": json.dumps({"verdict": "reject", "gate": reason})}
        holds = _holds(record)
        gate_open = all(holds[rel] for _, _, rel in ITEMS)
        credit = _credit(record) if gate_open else 0.0
        detail = {"holds": holds[relation], "gate_open": gate_open, "credit": credit,
                  "failure_stage": record.get("failure_stage")}
        detail["verdict"] = "accept" if credit > 0.0 else "reject"
        return {"score": credit, "reasoning": json.dumps(detail, sort_keys=True)}
    except Exception as exc:  # criteria never raise; a broken record scores zero with a reason
        return {"score": 0.0, "reasoning": json.dumps({"verdict": "reject", "gate": f"criterion-error:{type(exc).__name__}"})}

for _item_id, _weight, _relation in ITEMS:
    rewardkit.rubric_item(_item_id, _relation, weight=_weight, name=_item_id)
