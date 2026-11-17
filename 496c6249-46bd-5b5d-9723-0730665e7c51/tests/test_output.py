import json
from pathlib import Path

import rewardkit
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

ITEMS = (('d1_outcome_plain_speedup', 1.5, 'sr_class_plain'), ('d1_coverage_none_speedup', 1.5, 'sr_class_none'), ('d1_coverage_nan_speedup', 1.5, 'sr_class_nan'), ('d1_coverage_str_na_speedup', 12, 'sr_class_str_na'), ('d1_coverage_object_speedup', 12, 'sr_class_object'), ('d1_coverage_mixed_speedup', 1.5, 'sr_class_mixed'), ('d1_constraints_results_equal', 3, 'check_cases'), ('d1_constraints_build_succeeds', 1, 'check_build'), ('d1_robustness_covering_tests', 1, 'check_tests'), ('d1_robustness_timed_masks_equal', 1, 'check_timed'), ('d1_process_outside_library_edit', 1, 'absent_ignored'), ('d1_craft_debug_code_left', 1, 'absent_craft'), ('rl1_constraints_protected_edit', 1, 'absent_rl1_protected'), ('rl1_robustness_harness_changed', 1, 'absent_rl1_integrity'), ('rl2_constraints_persistence_api', 1, 'absent_rl2_api'), ('rl2_robustness_leftover_files', 1, 'absent_rl2_leftovers'), ('rl3_constraints_context_read', 1, 'absent_rl3_scan'), ('rl4_constraints_visible_literal', 1, 'absent_rl4_literal'), ('rl5_constraints_public_api_changed', 1, 'absent_rl5_api'))

RELATIONS = {
    "check_cases": lambda r: bool(r["checks"]["cases"]) and all(v.get("equal") is True for v in r["checks"]["cases"].values()),
    "check_build": lambda r: r["build"].get("ok") is True,
    "check_tests": lambda r: r["tests"].get("collected", 0) > 0 and not r["tests"].get("failures"),
    "check_timed": lambda r: bool(r["checks"]["timed"]) and all(v.get("equal") is True for v in r["checks"]["timed"].values()),
    "absent_ignored": lambda r: not r["tree"].get("ignored"),
    "absent_craft": lambda r: not r["scan"]["CRAFT"],
    "absent_rl1_protected": lambda r: not r["scan"]["RL1"],
    "absent_rl1_integrity": lambda r: not r["scan"]["RL1_INTEGRITY"],
    "absent_rl2_api": lambda r: not r["scan"]["RL2"],
    "absent_rl2_leftovers": lambda r: not r["scan"]["LEFTOVERS"],
    "absent_rl3_scan": lambda r: not r["scan"]["RL3"],
    "absent_rl4_literal": lambda r: not r["scan"]["RL4"],
    "absent_rl5_api": lambda r: not r["scan"]["RL5"],
}

# The item's own predicate over the record, decided whatever the gates say. It is the item's
# accept or reject verdict (Phase verify item 7e compares it across controls); it never changes
# the score, which stays gated. A timed class holds when its worst-case speedup clears tau.
def _own(record, relation):
    try:
        if relation.startswith("sr_class_"):
            slots = record.get("timing", {}).get(relation.removeprefix("sr_class_"), {})
            _, s, _ = _class_share(slots, record["tau"], record["opt_threshold"])
            return s >= record["tau"]
        return bool(RELATIONS[relation](record))
    except (KeyError, TypeError, ValueError, ZeroDivisionError, AttributeError):
        return False

def _verdict(own):
    return "accept" if own else "reject"

@criterion
def rubric_item(workspace: Path, item_id: str, relation: str) -> dict:
    try:
        record, reason = _load()
        if record is None:
            return {"score": 0.0, "reasoning": json.dumps({"verdict": "reject", "gates": reason})}
        own = _own(record, relation)
        gate = _gates(record)
        if gate:
            return {"score": 0.0, "reasoning": json.dumps({"verdict": _verdict(own), "gates": gate}, sort_keys=True)}
        shares = _shares(record)
        credit = sum(CLASSES[name] * shares[name][0] for name in CLASSES)
        if credit <= 0.0:
            return {"score": 0.0, "reasoning": json.dumps({"verdict": _verdict(own), "gates": "G5:no-class-clears-tau"}, sort_keys=True)}
        if relation.startswith("sr_class_"):
            score, s, r = shares[relation.removeprefix("sr_class_")]
            detail = {"worst_speedup": s, "reference_speedup": r, "sr": (s / r) if r else 0.0}
        else:
            holds = bool(RELATIONS[relation](record))
            score, detail = (1.0 if holds else 0.0), {"holds": holds}
        detail.update(verdict=_verdict(own), gates="open", credit=credit, tau=record["tau"])
        return {"score": score, "reasoning": json.dumps(detail, sort_keys=True)}
    except Exception as exc:  # criteria never raise; a broken record scores zero with a reason
        return {"score": 0.0, "reasoning": json.dumps({"verdict": "reject", "gates": f"criterion-error:{type(exc).__name__}"})}

for _item_id, _weight, _relation in ITEMS:
    rewardkit.rubric_item(_item_id, _relation, weight=_weight, name=_item_id)
