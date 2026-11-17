"""Measure the submission once, serially, and write the measurement record.

Runs as root inside the separate verifier image. Every piece of submission code
(the timed workloads and the repository tests) runs as a restricted uid in a fresh
process through runner.py. score.py only reads the record this script writes.
"""

from __future__ import annotations

import json
import math
import secrets
import shutil
import statistics
import sys
import time
import traceback
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))

import equiv  # noqa: E402
import repotests  # noqa: E402
import runner  # noqa: E402
import treeops  # noqa: E402

ROOT = Path("/opt/harness")
SUBMISSION = Path("/app/cirq")
OUT = Path("/logs/verifier/measure.json")
EVIDENCE = Path("/logs/verifier/evidence")
CHILD = str(HARNESS / "child.py")
PY = "/opt/venv/bin/python"
EVIDENCE_CAP = 200_000
TREES = ("base", "expert", "patch")


def _integrity() -> dict[str, str | None]:
    pinned = json.loads((ROOT / "integrity.json").read_text())
    return {
        rel: (treeops.sha256(Path(rel)) if Path(rel).is_file() else None)
        for rel in pinned
    }


def _seed(visible: int) -> int:
    while True:
        seed = secrets.randbelow(2**31)
        if seed != visible:
            return seed


class Measurement:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.scan: dict[str, list[str]] = {"RL1": [], "RL2": [], "RL3": [], "RL4": []}
        self.families: dict[str, dict] = {}
        self.tests: dict = {}
        self.errors: list[str] = []
        self.diff = ""
        self.test_log = ""
        self.tree: dict = {}

    def note_leftovers(self, label: str, res: runner.RunResult) -> None:
        if res.leftovers:
            self.scan["RL2"].append(
                f"{label}: files persisted outside the run scratch: {list(res.leftovers)[:5]}"
            )

    def build(self) -> Path:
        treeops.lock_tree(SUBMISSION)
        graded = ROOT / "work" / "graded"
        report = treeops.build_graded_tree(ROOT / "base", SUBMISSION, graded)
        for rel in self.config["covering_tests"]:
            shutil.copyfile(ROOT / "overlay" / rel, graded / rel)
        treeops.lock_tree(graded)
        self.tree = {
            "applied": list(report.applied),
            "ignored": list(report.ignored),
            "protected": list(report.protected_edits),
        }
        self.diff = report.diff
        hits = treeops.scan(report, tuple(self.config["visible"]["literals"]))
        for key, found in hits.items():
            self.scan[key] += found
        return graded

    def _child(self, guard, tree: Path, family: str, seed: int, cases: int):
        res = runner.run_restricted(
            [PY, CHILD, str(tree), family, str(seed), str(cases)],
            guard=guard,
            pythonpath=str(HARNESS),
            cwd=str(tree),
            timeout=self.config["child_timeout_sec"],
        )
        return (res.json_line() if res.returncode == 0 else None), res

    def family(self, guard, trees: dict[str, Path], family: str) -> None:
        cfg = self.config
        n_cases = cfg["families"][family]["cases"]
        seed = _seed(cfg["visible"]["seed"])
        slot: dict = {
            "seed": seed,
            "cases": [{} for _ in range(n_cases)],
            "patch_failures": [],
        }
        base_out: list[dict] = []
        base_inputs: list[str] = []
        for rep in range(cfg["reps"]):
            order = TREES[rep % 3 :] + TREES[: rep % 3]
            for name in order:
                out, res = self._child(guard, trees[name], family, seed, n_cases)
                if name == "patch":
                    self.note_leftovers(f"timing {family}", res)
                if out is None or len(out.get("records", [])) != n_cases:
                    reason = (
                        f"{name} run {family} rep {rep} failed (exit {res.returncode}, "
                        f"timeout={res.timed_out}): {res.stderr[-400:]}"
                    )
                    if name == "patch":
                        slot["patch_failures"].append(reason)
                    else:
                        self.errors.append(reason)
                    continue
                for i, rec in enumerate(out["records"]):
                    case = slot["cases"][i]
                    case["kind"] = rec["kind"]
                    case.setdefault(name, []).append(rec["seconds"])
                    if name == "base" and rep == 0:
                        base_out.append(rec["output"])
                        base_inputs.append(rec["input"])
                        continue
                    if not base_inputs:
                        continue
                    diff = None
                    if rec["input"] != base_inputs[i]:
                        diff = "input circuit differs from the base build"
                    else:
                        diff = equiv.output_diff(base_out[i], rec["output"])
                    if name == "base" and diff:
                        self.errors.append(
                            f"base output not deterministic: {family}#{i}: {diff}"
                        )
                    elif name == "expert" and diff:
                        case["expert_departs"] = diff
                    elif name == "patch" and diff and "patch_diff" not in case:
                        case["patch_diff"] = diff
                del out
        base_out.clear()
        # Noise band: the largest spread of the base tree's own repeated timings.
        spreads = [
            math.log(max(c["base"]) / min(c["base"]))
            for c in slot["cases"]
            if len(c.get("base", [])) > 1
        ]
        observed = max(spreads, default=0.0)
        slot["observed_base_spread"] = round(observed, 4)
        slot["noise_band"] = round(
            min(cfg["noise_cap"], max(cfg["noise_floor"], observed)), 4
        )
        for case in slot["cases"]:
            for name in TREES:
                if case.get(name):
                    case[f"{name}_median"] = statistics.median(case[name])
        self.families[family] = slot

    def repo_tests(self, guard, graded: Path) -> None:
        outcome = repotests.run(
            guard, graded, self.config, timeout=self.config["pytest_timeout_sec"]
        )
        self.note_leftovers("repository tests", outcome.result)
        self.tests = {
            "collected": outcome.collected,
            "failures": outcome.failures[:200],
        }
        self.test_log = outcome.result.stdout[-EVIDENCE_CAP:]

    def record(self) -> dict:
        return {
            "schema": "cirq8197.measure/v1",
            "status": "error" if self.errors else "ok",
            "reasons": self.errors,
            "tree": self.tree,
            "scan": self.scan,
            "red_lines": {k: v for k, v in self.scan.items() if v},
            "families": self.families,
            "tests": self.tests,
        }

    def write_evidence(self) -> None:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        timing = {
            fam: {
                "seed": slot["seed"],
                "noise_band": slot["noise_band"],
                "cases": [
                    {k: v for k, v in c.items() if k.endswith("_median") or k == "kind"}
                    for c in slot["cases"]
                ],
            }
            for fam, slot in self.families.items()
        }
        equivalence = {
            fam: {
                "patch_failures": slot["patch_failures"],
                "cases": [
                    {
                        "kind": c.get("kind"),
                        "equivalent": "patch_diff" not in c,
                        "reason": c.get("patch_diff"),
                    }
                    for c in slot["cases"]
                ],
            }
            for fam, slot in self.families.items()
        }
        files = {
            "submission_diff.txt": "changed paths: "
            + json.dumps(self.tree, sort_keys=True)
            + "\n\n"
            + self.diff[:EVIDENCE_CAP],
            "test_log.txt": json.dumps(self.tests, indent=1, sort_keys=True)
            + "\n\n"
            + self.test_log,
            "workload_output.json": json.dumps(equivalence, indent=1, sort_keys=True),
            "timing_record.json": json.dumps(timing, indent=1, sort_keys=True),
            "scan_record.json": json.dumps(self.scan, indent=1, sort_keys=True),
        }
        for name, text in files.items():
            (EVIDENCE / name).write_text(text)


def measure() -> dict:
    config = json.loads((HARNESS / "config.json").read_text())
    before = _integrity()
    pinned = json.loads((ROOT / "integrity.json").read_text())
    if before != pinned:
        return {
            "schema": "cirq8197.measure/v1",
            "status": "error",
            "reasons": ["harness-integrity-mismatch-before-run"],
        }
    if not (SUBMISSION / "cirq-core" / "cirq").is_dir():
        return {
            "schema": "cirq8197.measure/v1",
            "status": "error",
            "reasons": ["submission-tree-missing"],
        }
    m = Measurement(config)
    graded = m.build()
    guard = runner.PersistenceGuard(config["runner_uid"])
    trees = {"base": ROOT / "base", "expert": ROOT / "expert", "patch": graded}
    for family in config["families"]:
        m.family(guard, trees, family)
    m.repo_tests(guard, graded)
    after = _integrity()
    m.scan["RL1"] += [
        f"harness file {rel} changed while the submission ran"
        for rel in pinned
        if after.get(rel) != pinned[rel]
    ]
    m.write_evidence()
    return m.record()


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    try:
        record = measure()
    except (
        Exception
    ):  # boundary: any harness crash becomes a zero-scoring record with a reason
        record = {
            "schema": "cirq8197.measure/v1",
            "status": "error",
            "reasons": ["harness-exception", traceback.format_exc()[-2000:]],
        }
    record["elapsed_sec"] = round(time.time() - started, 1)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=1, sort_keys=True))
    tmp.replace(OUT)


if __name__ == "__main__":
    main()
