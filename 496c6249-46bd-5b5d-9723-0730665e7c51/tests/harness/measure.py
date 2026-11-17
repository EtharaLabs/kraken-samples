"""Measure the submission once, serially, and write the measurement record.

Runs as root inside the separate verifier image. The submission is compiled as the
builder uid, and every piece of submission code that runs afterwards (correctness
and timing children, covering tests) runs as the restricted runner uid through
runner.py. The criteria under /tests only read the record and the evidence files.
"""

from __future__ import annotations

import json
import random
import secrets
import sys
import time
import traceback
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))

import build  # noqa: E402
import repotests  # noqa: E402
import runner  # noqa: E402
import treeops  # noqa: E402

KRAKEN = Path("/opt/kraken")
SUBMISSION = Path("/app/numpy")
SITES = {
    "base": KRAKEN / "base-site",
    "expert": KRAKEN / "expert-site",
    "patch": KRAKEN / "work" / "site",
}
OUT = Path("/logs/verifier/measure.json")
EVIDENCE = Path("/logs/verifier/evidence")
CHILD = str(HARNESS / "child.py")
SCHEMA = "kraken.numpy-isin.measure/v1"
EVIDENCE_CAP = 200_000
EXPERT = "expert"
ORDER = ("base", "base2", EXPERT, "patch")


def _snapshot(config: dict) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for rel in config["harness_sha256"]:
        path = Path("/") / rel
        out[rel] = treeops.sha256(path) if path.is_file() else None
    return out


def _seed(visible: int) -> int:
    while True:
        seed = secrets.randbelow(2**31)
        if seed != visible:
            return seed


class Measurement:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.scan: dict[str, list[str]] = {
            k: []
            for k in ("RL1", "RL1_INTEGRITY", "RL2", "RL3", "RL4", "RL5", "CRAFT", "LEFTOVERS")
        }
        self.tree: dict = {}
        self.build: dict = {}
        self.checks: dict[str, dict] = {"api": {}, "cases": {}, "timed": {}}
        self.tests: dict = {}
        self.timing: dict = {}
        self.errors: list[str] = []
        self.diff = ""
        self.logs: dict[str, str] = {}

    def child(
        self, guard: runner.PersistenceGuard, tree: str, args: list[str]
    ) -> tuple[dict | None, runner.RunResult]:
        site = SITES["base" if tree == "base2" else tree]
        res = runner.run_restricted(
            [
                repotests.PY,
                CHILD,
                str(site),
                *args,
            ],
            guard=guard,
            pythonpath=f"{site}:{HARNESS}",
            timeout=self.config["child_timeout_sec"],
        )
        if tree == "patch" and res.leftovers:
            self.scan["LEFTOVERS"].append(
                f"{' '.join(args[:2])}: files persisted outside the run scratch: {list(res.leftovers)[:5]}"
            )
        return (res.json_line() if res.returncode == 0 else None), res

    def overlay_and_build(self) -> bool:
        report = treeops.overlay(KRAKEN / "base-src", SUBMISSION, build.GRADED)
        self.tree = {
            "applied": list(report.applied),
            "ignored": list(report.ignored),
            "protected": list(report.protected_edits),
        }
        self.diff = report.diff
        for key, hits in treeops.scan(
            report, tuple(self.config["visible"]["literals"])
        ).items():
            self.scan[key] += hits
        result = build.rebuild(
            SITES["patch"], self.config["builder_uid"], self.config["build_timeout_sec"]
        )
        self.scan["LEFTOVERS"] += (
            [f"build left files outside its tree: {list(result.leftovers)[:5]}"]
            if result.leftovers
            else []
        )
        self.build = {"ok": result.ok, "seconds": result.seconds}
        self.logs["build_log.txt"] = result.log
        treeops.lock_tree(build.GRADED.parent)
        if result.ok:
            repotests.install_pristine(SITES["patch"], self.config)
        return result.ok

    def api(self, guard: runner.PersistenceGuard) -> None:
        got = {tree: self.child(guard, tree, ["api"])[0] for tree in ("base", "patch")}
        if got["base"] is None:
            self.errors.append("base-api-run-failed")
            return
        equal = (
            got["patch"] is not None and got["patch"]["digest"] == got["base"]["digest"]
        )
        self.checks["api"] = {
            "equal": equal,
            "base": got["base"]["detail"],
            "patch": (got["patch"] or {}).get("detail"),
        }
        if not equal:
            self.scan["RL5"].append(
                "a public set-routine signature, export list or StringDType attribute differs from base"
            )

    def correctness(self, guard: runner.PersistenceGuard) -> None:
        for _ in range(self.config["correctness_seeds"]):
            seed = _seed(self.config["visible"]["seed"])
            ref, ref_res = self.child(guard, "base", ["correct", str(seed)])
            got, res = self.child(guard, "patch", ["correct", str(seed)])
            if ref is None:
                self.errors.append(
                    f"base-correctness-run-failed:{seed}:{ref_res.stderr[-300:]}"
                )
                continue
            # An instance on which the base build itself raises has no defined result to keep,
            # so it is recorded and not graded; every other instance must match exactly.
            undefined = set(ref.get("raised", []))
            wrong = (
                []
                if got is None
                else [
                    i
                    for i, (a, b) in enumerate(
                        zip(ref["cases"], got["cases"], strict=True)
                    )
                    if a != b and i not in undefined
                ]
            )
            self.checks["cases"][str(seed)] = {
                "count": len(ref["cases"]),
                "graded": len(ref["cases"]) - len(undefined),
                "base_raises": sorted(undefined),
                "equal": got is not None and not wrong,
                "mismatched_cases": wrong[:50],
                "patch_failure": None
                if got is not None
                else f"exit {res.returncode}, timeout={res.timed_out}: {res.stderr[-300:]}",
            }

    def plan(self) -> list[tuple[str, int, int, int]]:
        rng = random.Random(secrets.randbits(64))
        cfg = self.config["timing"]
        out = []
        for name in cfg["classes"]:
            for lo, hi in cfg["left_slots"]:
                out.append(
                    (
                        name,
                        rng.randint(lo, hi),
                        rng.randint(*cfg["right_range"]),
                        _seed(self.config["visible"]["seed"]),
                    )
                )
        return out

    def timed(self, guard: runner.PersistenceGuard) -> None:
        plan = self.plan()
        digests: dict[str, dict[str, set[str]]] = {}
        for rep in range(self.config["timing"]["reps"]):
            rot = ORDER[rep % len(ORDER) :] + ORDER[: rep % len(ORDER)]
            for name, n_left, n_right, seed in plan:
                key = f"{name}:{n_left}x{n_right}"
                slot = self.timing.setdefault(name, {}).setdefault(
                    key, {"seed": seed, "n_left": n_left, "n_right": n_right}
                )
                for tree in rot:
                    out, res = self.child(
                        guard,
                        tree,
                        ["time", name, str(n_left), str(n_right), str(seed)],
                    )
                    if out is None:
                        reason = f"{tree} timing {key} failed (exit {res.returncode}, timeout={res.timed_out})"
                        if tree == "patch":
                            slot.setdefault("patch_failures", []).append(reason)
                        else:
                            self.errors.append(f"{reason}: {res.stderr[-300:]}")
                        continue
                    slot.setdefault(tree, []).append(out["seconds"])
                    digests.setdefault(key, {}).setdefault(tree, set()).add(
                        out["digest"]
                    )
        for key, seen in digests.items():
            ref = seen.get("base", set())
            if seen.get(EXPERT, set()) != ref or seen.get("base2", set()) != ref:
                self.errors.append(f"reference-output-mismatch:{key}")
            self.checks["timed"][key] = {
                "equal": len(ref) == 1 and seen.get("patch", set()) == ref
            }

    def calibrated_tau(self) -> tuple[float, float]:
        spread = 1.0
        for slots in self.timing.values():
            for slot in slots.values():
                if slot.get("base") and slot.get("base2"):
                    a, b = min(slot["base"]), min(slot["base2"])
                    spread = max(spread, a / b, b / a)
        return max(self.config["timing"]["tau_floor"], spread**2), spread

    def repo_tests(self, guard: runner.PersistenceGuard) -> None:
        outcome = repotests.run(guard, SITES["patch"], self.config)
        if outcome.result.leftovers:
            self.scan["LEFTOVERS"].append(
                f"covering tests: files persisted outside the run scratch: {list(outcome.result.leftovers)[:5]}"
            )
        self.tests = {
            "collected": outcome.collected,
            "failures": outcome.failures[:200],
        }
        self.logs["test_log.txt"] = outcome.result.stdout[-EVIDENCE_CAP:]

    def failures(self) -> list[str]:
        out = [] if self.build.get("ok") else ["build failed"]
        out += [
            f"case set {k}"
            for k, v in self.checks["cases"].items()
            if not v.get("equal")
        ]
        out += [
            f"timed {k}" for k, v in self.checks["timed"].items() if not v.get("equal")
        ]
        out += self.tests.get("failures", [])
        if self.build.get("ok") and not self.checks["cases"]:
            out.append("no correctness instance ran")
        return out

    def red_lines(self) -> dict[str, list[str]]:
        return {
            "RL1": self.scan["RL1"] + self.scan["RL1_INTEGRITY"],
            "RL2": self.scan["RL2"] + self.scan["LEFTOVERS"],
            "RL3": self.scan["RL3"],
            "RL4": self.scan["RL4"],
            "RL5": self.scan["RL5"],
        }

    def record(self) -> dict:
        tau, spread = self.calibrated_tau()
        failures = self.failures()
        return {
            "schema": SCHEMA,
            "status": "error" if self.errors else "ok",
            "reasons": self.errors,
            "tree": self.tree,
            "build": self.build,
            "scan": self.scan,
            "red_lines": self.red_lines(),
            "checks": self.checks,
            "tests": self.tests,
            "correctness": {"passed": not failures, "failures": failures[:100]},
            "tau": tau,
            "base_spread": spread,
            "opt_threshold": self.config["timing"]["opt_threshold"],
            "class_weights": self.config["timing"]["classes"],
            "timing": self.timing,
        }

    def write_evidence(self) -> None:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        files = {
            "submission_diff.txt": "changed paths: "
            + json.dumps(self.tree, sort_keys=True)
            + "\n\n"
            + self.diff[:EVIDENCE_CAP],
            "build_log.txt": self.logs.get("build_log.txt", "")[-EVIDENCE_CAP:],
            "test_log.txt": json.dumps(self.tests, indent=1, sort_keys=True)
            + "\n\n"
            + self.logs.get("test_log.txt", ""),
            "workload_output.json": json.dumps(
                self.checks, indent=1, sort_keys=True, default=str
            ),
            "timing_record.json": json.dumps(
                {"tau": self.calibrated_tau(), "timing": self.timing},
                indent=1,
                sort_keys=True,
            ),
            "scan_record.json": json.dumps(self.scan, indent=1, sort_keys=True),
        }
        for name, text in files.items():
            (EVIDENCE / name).write_text(text)


def measure() -> dict:
    config = json.loads((HARNESS / "config.json").read_text())
    before = _snapshot(config)
    mismatch = [
        f"/{rel} does not match the bundle"
        for rel, d in config["harness_sha256"].items()
        # /tests files are left out: an audit probe may edit them on purpose.
        if rel.startswith("opt/kraken/") and before.get(rel) != d
    ]
    if mismatch:
        return {
            "schema": SCHEMA,
            "status": "error",
            "reasons": ["harness-integrity-mismatch-before-run", *mismatch],
        }
    if not SUBMISSION.is_dir():
        return {
            "schema": SCHEMA,
            "status": "error",
            "reasons": ["submission-tree-missing"],
        }
    m = Measurement(config)
    if m.overlay_and_build():
        guard = runner.PersistenceGuard(config["runner_uid"])
        m.api(guard)
        m.correctness(guard)
        m.repo_tests(guard)
        gates_open = (
            not m.failures() and not any(m.red_lines().values()) and not m.errors
        )
        if gates_open or config["timing"]["always"]:
            m.timed(guard)
    after = _snapshot(config)
    m.scan["RL1_INTEGRITY"] += [
        f"harness file /{rel} changed while the submission ran"
        for rel in before
        if after.get(rel) != before[rel]
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
            "schema": SCHEMA,
            "status": "error",
            "reasons": ["harness-exception", traceback.format_exc()[-2000:]],
        }
    record["elapsed_sec"] = round(time.time() - started, 1)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=1, sort_keys=True, default=str))
    tmp.replace(OUT)


if __name__ == "__main__":
    main()
