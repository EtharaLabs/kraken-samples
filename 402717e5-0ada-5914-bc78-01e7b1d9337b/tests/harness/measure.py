"""Measure the submission once, serially, and write the measurement record.

Runs as root inside the separate verifier image. Every piece of submission code
(correctness instances, the in-process probe, the covering tests, the timed calls)
runs as the restricted uid through runner.py, in a fresh `python -I -B` process
whose working directory is a fresh tmpfs scratch outside every source tree. The
criteria under /tests only read the record and the evidence files written here.
"""

from __future__ import annotations

import json
import math
import secrets
import statistics
import sys
import time
import traceback
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))

import compare  # noqa: E402
import repotests  # noqa: E402
import runner  # noqa: E402
import treeops  # noqa: E402
import workloads  # noqa: E402

KRAKEN = Path("/opt/kraken")
WORK = KRAKEN / "work"
SUBMISSION = Path("/app/statsmodels")
OUT = Path("/logs/verifier/measure.json")
EVIDENCE = Path("/logs/verifier/evidence")
CHILD = str(HARNESS / "child.py")
PY = "/opt/venv/bin/python"
SCHEMA = "kraken.za.measure/v1"
EVIDENCE_CAP = 200_000
SR_FLOOR = 0.001
# Equality within twice the workload's own A/A band
NOISE_EQUAL_FACTOR = 2.0
MAX_ROUNDS = 3
SCAN_KEYS = ("RL1", "RL1_integrity", "RL2", "RL2_dynamic", "RL3", "RL4", "RL5", "RL5_dynamic", "RL6", "RL6_files")


def _snapshot(config: dict) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for rel in config["harness_sha256"]:
        path = Path("/") / rel
        out[rel] = treeops.sha256(path) if path.is_file() else None
    return out


def _child(
    guard, args: list[str], timeout: float
) -> tuple[dict | None, runner.RunResult]:
    res = runner.run_restricted(
        [PY, "-I", "-B", CHILD, *args], guard=guard, timeout=timeout
    )
    return (res.json_line() if res.returncode == 0 else None), res


def _write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    path.chmod(0o644)
    return path


class Measurement:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.scan: dict[str, list[str]] = {
            k: [] for k in SCAN_KEYS
        }
        self.errors: list[str] = []
        self.tree: dict = {}
        self.diff = ""
        self.instances: dict[str, dict] = {}
        self.probe: dict = {}
        self.tests: dict = {}
        self.test_log = ""
        self.timing: dict = {}
        self.rounds: list[dict] = []
        self.seeds: dict = {}
        self.correctness_failures: list[str] = []

    # -- tree ---------------------------------------------------------------
    def build(self) -> Path:
        treeops.lock_tree(SUBMISSION)
        patch = WORK / "patch"
        report = treeops.build_graded_tree(KRAKEN / "base", SUBMISSION, patch)
        repotests.install_pristine(patch, self.config)
        treeops.lock_tree(patch)
        self.tree = {
            "applied": list(report.applied),
            "protected": list(report.protected_edits),
            "compiled": list(report.compiled),
            "ignored": list(report.ignored),
        }
        self.diff = report.diff
        for key, hits in treeops.scan(
            report, tuple(self.config["visible"]["literals"])
        ).items():
            self.scan[key] += hits
        return patch

    def note_leftovers(self, label: str, res: runner.RunResult) -> None:
        if res.leftovers:
            self.scan["RL2_dynamic"].append(
                f"{label}: files persisted outside the run scratch: {list(res.leftovers)[:5]}"
            )

    # -- correctness --------------------------------------------------------
    def correctness(self, guard, trees: dict[str, Path], master: int) -> None:
        cfg = self.config
        specs = workloads.correctness_plan(master, cfg["visible"], cfg["plan"])
        rng = workloads._rng(master + 1)
        probe_base = {"intended": "probe", "trim": 0.15, "maxlag": None, "params": {}}
        probe = {
            "a": {
                **probe_base,
                "id": "pr-a",
                "kind": "random_walk",
                "nobs": int(rng.integers(300, 500)),
                "seed": int(rng.integers(1, 2**31 - 1)),
                "regression": "c",
                "autolag": None,
            },
            "b": {
                **probe_base,
                "id": "pr-b",
                "kind": "ar",
                "nobs": int(rng.integers(250, 450)),
                "seed": int(rng.integers(1, 2**31 - 1)),
                "regression": "ct",
                "autolag": "AIC",
            },
        }
        probe["a2"] = {
            **probe["a"],
            "id": "pr-a2",
            "seed": int(rng.integers(1, 2**31 - 1)),
        }
        all_specs = specs + [probe["a"], probe["b"], probe["a2"]]
        spec_file = _write_json(WORK / "specs.json", all_specs)
        probe_file = _write_json(WORK / "probe.json", probe)
        timeout = cfg["correctness_timeout_sec"]
        base, res = _child(
            guard, ["result", str(trees["base"]), str(spec_file), "profile"], timeout
        )
        if base is None:
            self.errors.append(f"base correctness run failed: {res.stderr[-600:]}")
            return
        orc, res = _child(
            guard, ["oracle", str(trees["base"]), str(spec_file)], timeout
        )
        if orc is None:
            self.errors.append(f"oracle run failed: {res.stderr[-600:]}")
            return
        sub, res = _child(
            guard, ["result", str(trees["patch"]), str(spec_file)], timeout
        )
        self.note_leftovers("correctness", res)
        base, orc = base["results"], orc["results"]
        if sub is None:
            self.correctness_failures.append(
                f"submission correctness run failed (exit {res.returncode}, timeout={res.timed_out}): {res.stderr[-400:]}"
            )
            sub = {"results": {}}
        sub = sub["results"]
        for spec in specs:
            sid = spec["id"]
            cls = compare.classify(spec, base[sid], orc[sid])
            got = sub.get(sid)
            reasons = (
                ["no outcome"]
                if got is None
                else compare.judge(cls, got, base[sid], orc[sid])
            )
            self.instances[sid] = {
                "spec": spec,
                "class": cls,
                "cond_max": orc[sid].get("cond_max"),
                "oracle_flags": orc[sid].get("flags"),
                "base": {k: v for k, v in base[sid].items() if k != "warnings"}
                | {"n_warnings": len(base[sid].get("warnings", []))},
                "oracle": {
                    k: orc[sid].get(k) for k in ("stat", "bpidx", "gap", "lags")
                },
                "submission": None
                if got is None
                else {
                    k: got.get(k)
                    for k in (
                        "ok",
                        "stat",
                        "pvalue",
                        "lags",
                        "bpidx",
                        "exc_type",
                        "exc_msg",
                    )
                },
                "errors": {}
                if got is None
                else compare.errors(got, base[sid], orc[sid]),
                "equal": not reasons,
                "reasons": reasons,
            }
            if reasons:
                self.correctness_failures.append(
                    f"{sid} ({cls}, {spec['kind']}): {'; '.join(reasons)[:300]}"
                )
        self._probe(guard, trees, probe_file, base)

    def _probe(self, guard, trees, probe_file: Path, base: dict) -> None:
        got, res = _child(
            guard,
            ["probe", str(trees["patch"]), str(probe_file)],
            self.config["correctness_timeout_sec"],
        )
        self.note_leftovers("probe", res)
        if got is None:
            self.correctness_failures.append(
                f"in-process probe failed (exit {res.returncode}): {res.stderr[-300:]}"
            )
            return
        refs = {
            "a": base["pr-a"],
            "b": base["pr-b"],
            "a2": base["pr-a2"],
            "b_again": base["pr-b"],
        }
        verdict = {k: compare.judge("well", got[k], refs[k], {}) for k in refs}
        self.probe = {"verdict": verdict}
        if verdict["a"] or verdict["b"]:
            self.correctness_failures.append(
                f"probe first calls differ from the base: {verdict['a'] + verdict['b']}"
            )
        elif verdict["a2"] or verdict["b_again"]:
            self.scan["RL2_dynamic"].append(
                "a later call in the same process returned a result that differs from a fresh process: "
                + "; ".join(verdict["a2"] + verdict["b_again"])[:300]
            )

    # -- covering tests -----------------------------------------------------
    def repo_tests(self, guard, patch: Path) -> None:
        outcome = repotests.run(
            guard, patch, self.config, timeout=self.config["pytest_timeout_sec"]
        )
        self.note_leftovers("covering tests", outcome.result)
        self.tests = {
            "collected": outcome.collected,
            "failures": outcome.failures[:200],
        }
        self.test_log = outcome.result.stdout[-EVIDENCE_CAP:]

    # -- timing -------------------------------------------------------------
    def timed(self, guard, trees: dict[str, Path], master: int, core: int) -> None:
        """Up to MAX_ROUNDS full interleaved measurements, each on fresh series.

        A round whose expert-against-expert band is below the limit is the one read;
        otherwise the whole measurement repeats. Every round's band is logged.
        """
        limit = self.config["noise_band_limit"]
        for index in range(MAX_ROUNDS):
            errors_before = len(self.errors)
            timing = self._timed_round(guard, trees, master, core, index)
            band = self.speedup(timing)["noise_band"]
            self.rounds.append({"round": index + 1, "noise_band": band, "timing": timing})
            print(f"timing round {index + 1}: noise band {band}", flush=True)
            self.timing = timing
            if len(self.errors) > errors_before or (band is not None and band < limit):
                return

    def _timed_round(
        self, guard, trees: dict[str, Path], master: int, core: int, index: int
    ) -> dict:
        cfg = self.config
        budget = cfg["per_call_budget_sec"]
        order = ["expert", "patch", "expert_aa"]
        dead: set[str] = set()
        timing: dict = {}
        pairs = cfg["timing_pairs"]
        for rep in range(pairs):
            rot = order[rep % 3 :] + order[: rep % 3]
            for timed_spec, warm in workloads.timed_specs(
                master, index * pairs + rep, cfg["timed_workloads"], cfg["visible"]
            ):
                wid = timed_spec["id"]
                slot = timing.setdefault(
                    wid, {"expert": [], "expert_aa": [], "patch": [], "seeds": [], "reps": []}
                )
                slot["seeds"].append(timed_spec["seed"])
                spec_file = _write_json(
                    WORK / f"timed-{wid}-{index}-{rep}.json", [timed_spec, warm]
                )
                results = {}
                for name in rot:
                    if name == "patch" and wid in dead:
                        continue
                    tree = trees["expert" if name == "expert_aa" else name]
                    out, res = _child(
                        guard,
                        ["timed", str(tree), str(spec_file), str(core)],
                        budget + cfg["child_overhead_sec"],
                    )
                    if name == "patch":
                        self.note_leftovers(f"timing {wid}", res)
                    if out is None or out["seconds"] > budget:
                        if name == "patch":
                            dead.add(wid)
                            slot["timeout"] = (
                                f"exit {res.returncode}, timeout={res.timed_out}, "
                                f"seconds={None if out is None else out['seconds']}: {res.stderr[-300:]}"
                            )
                        else:
                            self.errors.append(
                                f"{name} timed run {wid}:{index}:{rep} failed: {res.stderr[-400:]}"
                            )
                        continue
                    slot[name].append(out["seconds"])
                    results[name] = out
                slot["reps"].append(
                    {name: out["seconds"] for name, out in results.items()}
                )
                if "patch" in results:
                    self._timed_checks(wid, f"{index}:{rep}", results)
        return timing

    def _timed_checks(self, wid: str, rep: str, results: dict) -> None:
        p = results["patch"]
        ratio = p["cpu_seconds"] / p["seconds"] if p["seconds"] > 0 else 0.0
        if ratio > self.config["cpu_wall_limit"]:
            self.scan["RL5_dynamic"].append(
                f"timing {wid}:{rep}: cpu/wall {ratio:.3f} > {self.config['cpu_wall_limit']}"
            )
        if (
            p["threads_started"]
            or p["forks"]
            or (p["tasks_after"] > p["tasks_before"] >= 0)
        ):
            self.scan["RL5_dynamic"].append(
                f"timing {wid}:{rep}: threads started {p['threads_started']}, forks {p['forks']}, "
                f"tasks {p['tasks_before']} -> {p['tasks_after']} during the timed call"
            )
        e = results.get("expert") or results.get("expert_aa")
        if e is None:
            return
        got, ref = p["result"], e["result"]
        same = (
            got["lags"] == ref["lags"]
            and got["crit"] == ref["crit"]
            and compare._close(
                got["stat"], ref["stat"], compare.NEAR_RTOL, compare.NEAR_ATOL
            )
        )
        if not same:
            self.correctness_failures.append(
                f"timed workload {wid}:{rep}: result {got} differs from the reference {ref}"
            )

    def speedup(self, timing: dict | None = None) -> dict:
        """SR_i from paired timings, read against workload i's own A/A band.

        Each process pair times expert, expert_aa and patch on the same freshly generated
        series, so SR_i = exp(median_rep log(T_expert / T_patch)) and the noise band of
        workload i is median_rep |log(T_expert / T_expert_aa)|. An SR_i at or above
        exp(-2 x band_i) is inside the measured noise and counts as 1.0; every SR_i is floored
        at SR_FLOOR (a timed-out workload scores SR_FLOOR). The round's noise_band, which
        the 0.02 ceiling gates, is the median of the per-workload bands.
        """
        timing = self.timing if timing is None else timing
        measured, bands, equal_at = {}, {}, {}
        for wid, slot in timing.items():
            reps = slot.get("reps") or []
            aa = [
                abs(math.log(r["expert"] / r["expert_aa"]))
                for r in reps
                if r.get("expert") and r.get("expert_aa")
            ]
            bands[wid] = statistics.median(aa) if aa else None
            equal_at[wid] = (
                math.exp(-NOISE_EQUAL_FACTOR * bands[wid]) if bands[wid] is not None else math.inf
            )
            paired = [
                math.log(r["expert"] / r["patch"])
                for r in reps
                if r.get("expert") and r.get("patch")
            ]
            if slot.get("timeout") or not paired:
                measured[wid] = None
            else:
                measured[wid] = math.exp(statistics.median(paired))
        srs = {
            wid: SR_FLOOR
            if sr is None
            else 1.0
            if sr >= equal_at[wid]
            else max(sr, SR_FLOOR)
            for wid, sr in measured.items()
        }
        known = [b for b in bands.values() if b is not None]
        band = statistics.median(known) if known else None
        values = list(srs.values())
        harmonic = len(values) / sum(1 / v for v in values) if values else 0.0
        geomean = (
            math.exp(sum(math.log(v) for v in values) / len(values)) if values else 0.0
        )
        return {
            "sr": srs,
            "sr_measured": measured,
            "noise_bands": bands,
            "noise_equal_at": equal_at,
            "harmonic": harmonic,
            "geomean": geomean,
            "noise_band": band,
            "aa_log_ratios": known,
        }

    # -- record -------------------------------------------------------------
    def stage(self) -> str:
        if any(self.scan.values()):
            return "red_line"
        if not self.tree.get("applied"):
            return "unmodified"
        if self.tests.get("failures") or not self.tests.get("collected"):
            return "covering_tests"
        if self.correctness_failures or not self.instances:
            return "correctness"
        if any(slot.get("timeout") for slot in self.timing.values()):
            return "timeout"
        return "none"

    def record(self) -> dict:
        speed = self.speedup() if self.timing else None
        if speed is not None:
            speed["noise_bands"] = [r["noise_band"] for r in self.rounds]
        stage = self.stage()
        status = "error" if self.errors else "ok"
        band_limit = self.config["noise_band_limit"]
        if (
            status == "ok"
            and speed is not None
            and (speed["noise_band"] is None or speed["noise_band"] >= band_limit)
        ):
            status = "noise_floor"
        red_lines = {rl: [h for k, hits in self.scan.items() if k.split("_")[0] == rl for h in hits] for rl in ("RL1", "RL2", "RL3", "RL4", "RL5", "RL6")}
        return {
            "schema": SCHEMA,
            "status": status,
            "reasons": self.errors
            + (["noise_floor"] if status == "noise_floor" else []),
            "seeds": self.seeds,
            "tree": self.tree,
            "scan": self.scan,
            "red_lines": red_lines,
            "failure_stage": stage,
            "tests": self.tests,
            "correctness": {
                "passed": not self.correctness_failures
                and bool(self.instances)
                and not self.tests.get("failures")
                and bool(self.tests.get("collected")),
                "instances_passed": not self.correctness_failures
                and bool(self.instances),
                "failures": self.correctness_failures[:100],
                "classes": {
                    c: sum(1 for i in self.instances.values() if i["class"] == c)
                    for c in ("well", "near", "fallback")
                },
                "instances": {
                    sid: {"class": i["class"], "intended": i["spec"]["intended"], "equal": i["equal"]}
                    for sid, i in self.instances.items()
                },
                "probe_and_timed_failures": [
                    f for f in self.correctness_failures if f.startswith(("timed workload", "probe", "in-process"))
                ],
            },
            "timing": self.timing,
            "timing_rounds": [
                {"round": r["round"], "noise_band": r["noise_band"]} for r in self.rounds
            ],
            "speedup": speed,
        }

    def write_evidence(self) -> None:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        files = {
            "submission_diff.txt": "changed paths: "
            + json.dumps(self.tree, sort_keys=True)
            + "\n\n"
            + self.diff[:EVIDENCE_CAP],
            "test_log.txt": json.dumps(self.tests, indent=1, sort_keys=True)
            + "\n\n"
            + self.test_log,
            "workload_output.json": json.dumps(
                {"instances": self.instances, "probe": self.probe},
                indent=1,
                sort_keys=True,
            ),
            "timing_record.json": json.dumps(
                {
                    "timing": self.timing,
                    "rounds": self.rounds,
                    "speedup": self.speedup() if self.timing else None,
                },
                indent=1,
                sort_keys=True,
            ),
            "scan_record.json": json.dumps(self.scan, indent=1, sort_keys=True),
        }
        for name, text in files.items():
            (EVIDENCE / name).write_text(text)


def _core() -> int:
    import os

    return max(os.sched_getaffinity(0))


def measure(correctness_only: bool = False, pinned_seed: int | None = None) -> dict:
    config = json.loads((HARNESS / "config.json").read_text())
    before = _snapshot(config)
    mismatch = [
        f"/{rel}"
        for rel, digest in config["harness_sha256"].items()
        # files under /tests are left out here: an audit may edit them on purpose; any change
        # while submission code runs is still red line RL1
        if rel.startswith("opt/kraken/") and before.get(rel) != digest
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
    WORK.mkdir(parents=True, exist_ok=True)
    patch = m.build()
    master = pinned_seed if pinned_seed is not None else secrets.randbelow(2**31 - 2) + 1
    m.seeds = {"master": master}
    print(f"verify-time master seed {master}", flush=True)
    if not m.tree["applied"]:
        m.write_evidence()
        return m.record()
    guard = runner.PersistenceGuard(config["runner_uid"])
    trees = {"base": KRAKEN / "base", "expert": KRAKEN / "expert", "patch": patch}
    m.correctness(guard, trees, master)
    m.repo_tests(guard, patch)
    # --correctness-only is an author-side smoke mode (no timing); test.sh never passes it
    if m.stage() == "none" and not m.errors and not correctness_only:
        m.timed(guard, trees, master, _core())
    after = _snapshot(config)
    m.scan["RL1_integrity"] += [
        f"harness file /{rel} changed while the submission ran"
        for rel in config["harness_sha256"]
        if after.get(rel) != before.get(rel)
    ]
    m.write_evidence()
    return m.record()


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    try:
        args = sys.argv[1:]
        # author-side smoke flags; test.sh passes neither, so graded runs draw a fresh seed
        seed = int(args[args.index("--master-seed") + 1]) if "--master-seed" in args else None
        record = measure(correctness_only="--correctness-only" in args, pinned_seed=seed)
    except (
        Exception
    ):  # boundary: any harness crash becomes an error record with a reason
        record = {
            "schema": SCHEMA,
            "status": "error",
            "reasons": ["harness-exception", traceback.format_exc()[-2000:]],
        }
    record["elapsed_sec"] = round(time.time() - started, 1)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=1, sort_keys=True))
    tmp.replace(OUT)


if __name__ == "__main__":
    main()
