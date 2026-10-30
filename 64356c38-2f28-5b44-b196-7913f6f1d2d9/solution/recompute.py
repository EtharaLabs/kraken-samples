# FORGE-CANARY-BEGIN
# FORGE-CANARY-SLOT-1: 0000000000000000000000000000000000000000000000000000000000000000
# FORGE-CANARY-SLOT-2: 0000000000000000000000000000000000000000000000000000000000000000
# FORGE-CANARY-SLOT-3: 0000000000000000000000000000000000000000000000000000000000000000
# FORGE-CANARY-END
"""Derive every generated file of this bundle from solution/grounding.yaml.

Outputs: tests/test_output.py (one Reward Kit criterion per compiled rubric
item), tests/judge.toml (judged items), tests/reward.toml,
tests/reward.compiled.toml, tests/diag_correctness.py, tests/diag_speedup.py,
tests/harness/config.json, tests/harness/tests.json, solution/solve.sh,
solution/TRUTH.md, solution/provenance.yaml and solution/policy.yaml. config.json
is written last because it records the digests of the other verifier files.
No model is ever called. Deterministic: no clock, network, locale or random
source. Discovery locations are re-derived from solution/reference.patch.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOL = ROOT / "solution"
TESTS = ROOT / "tests"
BANNER = "GENERATED SECTION. DO NOT HAND-EDIT."
ZERO = "0" * 64


def canary(marker: str) -> str:
    lines = [f"{marker} FORGE-CANARY-BEGIN"]
    lines += [f"{marker} FORGE-CANARY-SLOT-{i}: {ZERO}" for i in (1, 2, 3)]
    lines.append(f"{marker} FORGE-CANARY-END")
    return "\n".join(lines) + "\n"


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


CRITERION_HEAD = '''"""{banner}"""

import json
import statistics
from pathlib import Path

import rewardkit
from rewardkit import criterion

MEASURE = Path("/logs/verifier/measure.json")
FAMILIES = {families!r}
FAMILY_WEIGHTS = {family_weights!r}
TAU = {tau!r}
KAPPA = {kappa!r}


def _load():
    try:
        record = json.loads(MEASURE.read_text())
    except (OSError, ValueError) as exc:
        return None, f"G1:measurement-unreadable:{{type(exc).__name__}}"
    status = record.get("status") if isinstance(record, dict) else None
    if status != "ok":
        return None, "G1:measurement-error:" + ";".join(map(str, (record or {{}}).get("reasons", [])))[:400]
    return record, ""


def _gates(record):
    fired = sorted(k for k, v in record.get("red_lines", {{}}).items() if v)
    if fired:
        return "G2:red-line:" + ",".join(fired)
    if record.get("correctness", {{}}).get("passed") is not True:
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
    return {{family: _family_share(record, family) for family in FAMILIES}}
'''

TEST_OUTPUT_BODY = """

ITEMS = {items!r}


def _all_equal(group):
    return bool(group) and all(entry.get("equal") is True for entry in group.values())


RELATIONS = {{
    "check_programs": lambda r: _all_equal(r["checks"]["programs"]),
    "check_base_tests": lambda r: r["tests"]["collected"] > 0 and not r["tests"]["base_failures"],
    "check_api": lambda r: _all_equal(r["checks"]["api"]),
    "check_timed_digests": lambda r: _all_equal(r["checks"]["timed"]),
    "check_expert_tests": lambda r: not r["tests"]["expert_failures"],
    "check_library_only": lambda r: not r["tree"]["ignored"],
    "absent_rl1_protected": lambda r: not r["scan"]["rl1_protected"],
    "absent_rl1_integrity": lambda r: not r["scan"]["rl1_integrity"],
    "absent_rl2_api": lambda r: not r["scan"]["rl2_api"],
    "absent_rl2_leftovers": lambda r: not r["scan"]["rl2_leftovers"],
    "absent_rl3_scan": lambda r: not r["scan"]["rl3_scan"],
    "absent_rl3_identity": lambda r: not r["scan"]["rl3_identity"],
    "absent_craft_scan": lambda r: not r["scan"]["craft_scan"],
    "absent_rl4_literal": lambda r: not r["scan"]["rl4_literal"],
}}


@criterion
def rubric_item(workspace: Path, item_id: str, relation: str) -> dict:
    try:
        record, reason = _load()
        if record is None:
            return {{"score": 0.0, "reasoning": json.dumps({{"verdict": "reject", "gates": reason}})}}
        shares = _shares(record)
        credit = sum(FAMILY_WEIGHTS[family] * shares[family] for family in FAMILIES)
        if relation.startswith("sr_family_"):
            score = shares[relation.removeprefix("sr_family_")]
            detail = {{"sr": score}}
        else:
            holds = bool(RELATIONS[relation](record))
            score = credit if holds else 0.0
            detail = {{"holds": holds, "credit": credit}}
        detail["verdict"] = "accept" if score > 0.0 else "reject"
        detail["gates"] = _gates(record) or ("open" if credit > 0.0 else "G4:no-family-clears-tau")
        return {{"score": score, "reasoning": json.dumps(detail, sort_keys=True)}}
    except Exception as exc:  # criteria never raise; a broken record scores zero with a reason
        return {{"score": 0.0, "reasoning": json.dumps({{"verdict": "reject", "gates": f"criterion-error:{{type(exc).__name__}}"}})}}


for _item_id, _weight, _relation in ITEMS:
    rewardkit.rubric_item(_item_id, _relation, weight=_weight, name=_item_id)
"""

DIAG_CORRECTNESS_BODY = """

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
"""

DIAG_SPEEDUP_BODY = """

@criterion
def diag_speedup(workspace: Path) -> dict:
    try:
        record, reason = _load()
        if record is None:
            return {"score": 0.0, "reasoning": reason}
        worst = min(base / patch for family in FAMILIES for _, base, _, patch in _medians(record, family))
        return {"score": worst, "reasoning": "min-base-over-patch"}
    except Exception as exc:  # criteria never raise
        return {"score": 0.0, "reasoning": f"criterion-error:{type(exc).__name__}"}
"""

OBLIGATIONS = ("D1", "RL1", "RL2", "RL3", "RL4")
DIMENSIONS = ("outcome", "coverage", "constraints", "robustness", "process", "craft")
TARGETS = (
    "submission_diff",
    "test_log",
    "workload_output",
    "timing_record",
    "scan_record",
)
OUTCOME_CLASSES = ("VALUE", "EFFECT", "ABSENCE", "INVARIANT", "ORDERING", "DIVERGENCE")
ITEM_KEYS = {
    "id",
    "obligation",
    "dimension",
    "weight",
    "negate",
    "evaluation_target",
    "criterion",
    "judgment",
    "evidence",
    "mode",
}
COMPILATION_FLOOR = 0.70
JUDGED_FLOOR = 11


def validate_rubric(g: dict) -> tuple[list[dict], list[dict]]:
    items = g["rubric"]
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)), "duplicate rubric ids"
    for i in items:
        assert set(i) == ITEM_KEYS, f"{i['id']}: keys {sorted(set(i) ^ ITEM_KEYS)}"
        assert re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", i["id"]), i["id"]
        assert i["obligation"] in OBLIGATIONS and i["dimension"] in DIMENSIONS, i["id"]
        assert i["evaluation_target"] in TARGETS and i["weight"] in (1, 3, 5), i["id"]
        assert i["mode"] in ("compiled", "judged") and isinstance(i["negate"], bool), i[
            "id"
        ]
        assert i["judgment"]["type"] in OUTCOME_CLASSES, i["id"]
        assert ("relation" in i["judgment"]) == (i["mode"] == "compiled"), i["id"]
        assert ("residue" in i["judgment"]) == (i["mode"] == "judged"), i["id"]
    na = {(r["obligation"], r["dimension"]) for r in g["rubric_not_applicable"]}
    filled = {(i["obligation"], i["dimension"]) for i in items}
    for cell in ((o, d) for o in OBLIGATIONS for d in DIMENSIONS):
        assert (cell in filled) != (cell in na), (
            f"grid cell {cell}: item and not_applicable must be exclusive and one present"
        )
    compiled = [i for i in items if i["mode"] == "compiled"]
    judged = [i for i in items if i["mode"] == "judged"]
    total = sum(i["weight"] for i in items)
    assert sum(i["weight"] for i in compiled) / total >= COMPILATION_FLOOR, (
        "compilation floor"
    )
    assert len(judged) >= JUDGED_FLOOR, "judged item floor"
    assert any(i["negate"] for i in judged), "judged prohibitions"
    visible = g["visible_workload"]
    for fam, sizes in g["hidden_workloads"]["families"].items():
        assert visible["n"] not in sizes, (
            f"hidden size of {fam} equals the visible size"
        )
    return compiled, judged


def family_weights(g: dict) -> dict[str, float]:
    hw = g["hidden_workloads"]
    weights = {fam: float(w) for fam, w in hw["family_weights"].items()}
    assert tuple(weights) == tuple(hw["families"]), "family_weights must name every family in order"
    assert abs(sum(weights.values()) - 1.0) < 1e-12, "family weights must sum to one"
    return weights


def criteria_files(g: dict, compiled: list[dict]) -> None:
    head = CRITERION_HEAD.format(
        banner=BANNER,
        families=tuple(g["hidden_workloads"]["families"]),
        family_weights=family_weights(g),
        tau=float(g["timing"]["tau"]),
        kappa=float(g["timing"]["kappa"]),
    )
    items = tuple((i["id"], i["weight"], i["judgment"]["relation"]) for i in compiled)
    write(TESTS / "test_output.py", head + TEST_OUTPUT_BODY.format(items=items))
    write(TESTS / "diag_correctness.py", head + DIAG_CORRECTNESS_BODY)
    write(TESTS / "diag_speedup.py", head + DIAG_SPEEDUP_BODY)


def _toml_str(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def judge_toml(judged: list[dict], evidence: dict[str, str]) -> None:
    # Reward Kit accepts per-criterion files only in individual mode, so the batched judge reads
    # every evidence file through [judge] files; each item names its own target in annotations.
    files = ", ".join(_toml_str(evidence[t]) for t in TARGETS)
    out = [f"# {BANNER}", "", "[judge]", f"files = [{files}]", 'mode = "batched"', "",
           "[scoring]", 'aggregation = "weighted-mean"', ""]
    for i in judged:
        out += [
            "[[criterion]]",
            f"id = {_toml_str(i['id'])}",
            f"name = {_toml_str(i['id'])}",
            f"description = {_toml_str(i['criterion'])}",
            'type = "binary"',
            f"weight = {i['weight']}",
            f"negate = {'true' if i['negate'] else 'false'}",
            "",
            "[criterion.annotations]",
            'mode = "judged"',
            f"type = {_toml_str(i['judgment']['type'])}",
            f"obligation = {_toml_str(i['obligation'])}",
            f"dimension = {_toml_str(i['dimension'])}",
            f"evidence = {_toml_str(i['evaluation_target'])}",
            f"residue = {_toml_str(i['judgment']['residue'])}",
            "",
        ]
    write(TESTS / "judge.toml", "\n".join(out))


def reward_tomls(compiled: list[dict], judged: list[dict]) -> None:
    wc, wj = sum(i["weight"] for i in compiled), sum(i["weight"] for i in judged)
    scoring = [f"# {BANNER}", ""]
    for stem in ("test_output", "diag_correctness", "diag_speedup"):
        scoring += [f"[scoring.{stem}]", 'aggregation = "weighted-mean"', ""]

    def rewards(with_judge: bool) -> list[str]:
        judge = {"judge": 0} if with_judge else {}
        rows = [
            (
                "reward",
                {
                    "test_output": wc,
                    **({"judge": wj} if with_judge else {}),
                    "diag_correctness": 0,
                    "diag_speedup": 0,
                },
            ),
            (
                "correctness",
                {"test_output": 0, **judge, "diag_correctness": 1, "diag_speedup": 0},
            ),
            (
                "worst_case_speedup",
                {"test_output": 0, **judge, "diag_correctness": 0, "diag_speedup": 1},
            ),
        ]
        out = []
        for name, weights in rows:
            body = ", ".join(f"{k} = {float(v)!r}" for k, v in weights.items())
            out += [
                "[[reward]]",
                f'name = "{name}"',
                'aggregation = "weighted-mean"',
                f"weights = {{ {body} }}",
                "",
            ]
        return out

    write(TESTS / "reward.toml", "\n".join(scoring + rewards(True)))
    write(TESTS / "reward.compiled.toml", "\n".join(scoring + rewards(False)))


def config_json(g: dict) -> None:
    hw, tm, rt, vw = (
        g["hidden_workloads"],
        g["timing"],
        g["repo_tests"],
        g["visible_workload"],
    )
    tests = {
        "runner_uid": tm["runner_uid"],
        "pytest_timeout_sec": tm["pytest_timeout_sec"],
        "test_selection": rt["selection"],
        "test_ignore": rt["ignore"],
        "f2p_test": g["upstream"]["graded_test"],
    }
    write(
        TESTS / "harness" / "tests.json",
        json.dumps(tests, indent=1, sort_keys=True) + "\n",
    )
    digests = {
        item["dst"]: hashlib.sha256((ROOT / item["src"]).read_bytes()).hexdigest()
        for item in g["harness_files"]
    }
    config = {
        **tests,
        "families": hw["families"],
        "reps": hw["reps"],
        "program_seeds": hw["program_seeds"],
        "tau": float(tm["tau"]),
        "child_timeout_sec": tm["child_timeout_sec"],
        "visible": {"n": vw["n"], "seed": vw["seed"], "literals": vw["literals"]},
        "harness_sha256": digests,
    }
    write(
        TESTS / "harness" / "config.json",
        json.dumps(config, indent=1, sort_keys=True) + "\n",
    )


def policy_yaml(g: dict) -> None:
    record = {
        "schema": "trinity.policy/v1",
        "source": g["policy"]["source"],
        "channels": g["policy"]["channels"],
    }
    write(
        SOL / "policy.yaml",
        canary("#") + f"# {BANNER}\n" + yaml.safe_dump(record, sort_keys=False),
    )
SOLVE_HEAD = """#!/usr/bin/env bash
{canary}# {banner}
# Oracle ladder. Every live line is one self-contained command: solution/apply.py
# applies (+) or reverts (-) staged sub-patches on /app/pennylane with exact context.
# Each prefix of the lines is a real partial fix; the last line reverts the stages and
# applies solution/reference.patch, so the full oracle tree is base plus the upstream fix.
"""


def solve_sh(g: dict) -> str:
    lines = [SOLVE_HEAD.replace("{canary}", canary("#")).replace("{banner}", BANNER)]
    for step in g["oracle"]["ladder"]:
        lines.append(f"# {step['id']}: {step['effect']}\n")
        lines.append('python3 "$(dirname "$0")/apply.py" ' + " ".join(step["ops"]) + "\n")
    return "".join(lines)


def derive_discovery(g: dict) -> list[dict]:
    patch = (SOL / "reference.patch").read_text()
    files = re.findall(r"^\+\+\+ b/(.+)$", patch, re.M)
    removed = [
        l[1:].strip()
        for l in patch.splitlines()
        if l.startswith("-") and not l.startswith("---")
    ]
    rows = []
    for dv in g["discovery"][:4]:
        found = []
        for loc in dv["established_at"]:
            if loc["file"].startswith("pennylane/"):
                ok = loc["file"] in files or any(f.endswith(loc["file"]) for f in files)
                if "needle" in loc:
                    ok = ok and loc["needle"] in removed
            else:
                ok = (ROOT / loc["file"]).is_file()
            found.append((loc["file"], loc.get("symbol", ""), ok))
        rows.append({"id": dv["id"], "locations": found})
    return rows


def truth(g: dict, discovery: list[dict]) -> None:
    rl = {r["id"]: r["check"] for r in g["red_lines"]}
    ck = {c["id"]: c["check"] for c in g["checkers"]}
    lines = [
        canary("<!--").replace("\n", " -->\n"),
        f"# Ground truth: {g['task_name']}",
        "",
        BANNER,
        "",
        f"Upstream {g['upstream']['canonical_repo']} at base {g['upstream']['base_commit']}; reference fix "
        f"{g['upstream']['reference_fix_commit']} restricted to: "
        + ", ".join(g["upstream"]["reference_patch"]["files"])
        + ".",
        "",
        "## Golden trajectory",
        "",
    ]
    steps = [
        (
            "Run the visible workload and see tracing time grow faster than linearly in the gate count.",
            "baseline observed",
            [],
        ),
        (
            "Profile the capture path and locate the per-wrapper removal of the base operator's equation.",
            "DV1, DV2 established",
            [],
        ),
        (
            "Replace the per-removal list rebuild with a batched backward sweep per frame keyed by equation identity.",
            "DV3 applied in the library source",
            ["C6"],
        ),
        (
            "Keep every wrapper family on the fast path; the hidden families are scored separately.",
            "DV4 covered",
            ["C6"],
        ),
        (
            "Keep the single positional call and generator inputs working exactly as at base.",
            "API preserved",
            ["C2"],
        ),
        (
            "Keep every traced program identical to the base commit's, including nested frames and out-of-order consumption.",
            "behavior preserved",
            ["C1", "C3"],
        ),
        ("Keep the covering repository tests passing.", "tests green", ["C4", "C5"]),
        (
            "Deliver D1, the modified working tree at /app/pennylane, editing only the library package.",
            "D1 delivered",
            ["C7"],
        ),
    ]
    for i, (action, state, checks) in enumerate(steps, 1):
        lines.append(
            f"{i}. {action} State: {state}. Checkers: {', '.join(checks) or 'none'}."
        )
    lines += ["", "## Red lines", ""]
    lines += [f"- {k}: {v}. Checker: C7." for k, v in rl.items()]
    lines += ["", "## Checkers", ""] + [f"- {k}: {v}." for k, v in ck.items()]
    lines += ["", "## Rejected routes", ""]
    lines += [
        f"- {c['id']} {c['name']} ({c['kind']}): expected {c['expect']}; measured {c['measured']}."
        for c in g["controls"]
    ]
    lines += ["", "## Oracle ladder", "", g["oracle"]["rule"], ""]
    lines += [f"- {s['id']}: {s['effect']}." for s in g["oracle"]["ladder"]]
    lines += ["", "## Alternate correct solutions", ""]
    lines += [f"- {a['name']}: {a['approach']}" for a in g["alternates"]]
    lines += ["", "## Rubric", ""]
    lines += [
        f"- {i['id']}: {i['obligation']} x {i['dimension']}, weight {i['weight']}, negate "
        f"{str(i['negate']).lower()}, {i['mode']}, {i['judgment']['type']} over {i['evaluation_target']}. {i['criterion']}"
        for i in g["rubric"]
    ]
    lines += [""] + [
        f"- not applicable {r['obligation']} x {r['dimension']}: {r['reason']}." for r in g["rubric_not_applicable"]
    ]
    rk = g["reward_kit"]
    lines += ["", "## Gates", ""] + [f"- {x['id']}: {x['check']}." for x in rk["gates"]]
    lines += ["", rk["credit"], "", rk["compiled_item_rule"], "", rk["judged_item_rule"]]
    lines += ["", "## Discovery values", ""]
    for row in discovery:
        locs = "; ".join(
            f"{f} {s}".strip() + ("" if ok else " (not derivable)")
            for f, s, ok in row["locations"]
        )
        lines.append(f"- {row['id']}: {locs}.")
    lines += [
        "",
        "## Reward",
        "",
        g["reward"]["formula"],
        "",
        g["reward"]["no_op_rule"] + ".",
        "",
    ]
    write(SOL / "TRUTH.md", "\n".join(lines))


def provenance(g: dict) -> None:
    u = g["upstream"]
    record = {
        "schema": "trinity.provenance/v1",
        "generated": BANNER,
        "slot": g["slot"],
        "run_id": g["run_id"],
        "origin": "original",
        "provenance_date": "2026-10-26",
        "no_upstream_lift": True,
        "source_kind": "public_repository",
        "source": {
            "canonical_identity": u["canonical_repo"],
            "host_numeric_id": u["host_numeric_id"],
            "license": u["license"],
            "license_source": "host API spdx_id",
            "fork_ancestry_snapshot_digest": u["fork_ancestry_snapshot_digest"],
            "base_commit_sha": u["base_commit"],
            "base_commit_committed_at": u["base_commit_committed_at"],
            "task_generating_event": "performance pull request opened, pennylane pull request 10298, merged as "
            f"commit {u['reference_fix_commit']} on {u['merged_at']}",
            "task_generating_event_timestamp": u["event_timestamp"],
            "reference_fix_commit": u["reference_fix_commit"],
        },
        "attestations": {
            k: "attestation-unavailable"
            for k in (
                "ancestry_attestation_digest",
                "ancestry_attestation_signer",
                "event_attestation_digest",
                "event_attestation_signer",
            )
        },
        "screening": {
            "roots": "unresolved, FORGE_VIEW screening_roots null",
            "screening_measured_at": "unresolved",
            "screening_interval_days": "unresolved",
            "screening_expires_at": "unresolved",
        },
        "cap": "HOLD:PILOT_REQUIRED",
    }
    body = (
        canary("#")
        + f"# {BANNER}\n"
        + yaml.safe_dump(record, sort_keys=True, width=4096)
    )
    write(SOL / "provenance.yaml", body)


def main() -> None:
    g = yaml.safe_load((SOL / "grounding.yaml").read_text())
    compiled, judged = validate_rubric(g)
    discovery = derive_discovery(g)
    criteria_files(g, compiled)
    judge_toml(judged, g["reward_kit"]["evidence"])
    reward_tomls(compiled, judged)
    write(SOL / "solve.sh", solve_sh(g))
    (SOL / "solve.sh").chmod(0o755)
    truth(g, discovery)
    provenance(g)
    policy_yaml(g)
    config_json(g)


if __name__ == "__main__":
    main()
