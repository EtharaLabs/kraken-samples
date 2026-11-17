"""Repository tests covering the edited code, run from the verifier's pristine copies.

The graded tree gets the pristine test files of statsmodels/tsa/tests that cover
stattools and lagselect: the base commit's files with the tests the upstream fix
added. The pass set is recorded at image build time on the base tree with the same
command (`repotests.py baseline`); it is every test that passes on both the base
tree and the reference tree. A submission passes when every test of the pass set
still passes. Added tests that fail on the base tree name the reference's private
helpers and are recorded as excluded, never required.

usage at build time: repotests.py baseline <base-tree> <expert-tree> <out.json> <tests.json>
"""

from __future__ import annotations

import json
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))

import runner  # noqa: E402

PY = "/opt/venv/bin/python"
BASELINE = Path("/opt/kraken/base-pass.json")
PRISTINE = Path("/opt/kraken/pristine-tests")
PASSED, FAILED, SKIPPED = "passed", "failed", "skipped"


@dataclass(frozen=True, slots=True)
class TestOutcome:
    result: runner.RunResult
    outcomes: dict[str, str]
    collected: int
    failures: list[str]


def install_pristine(tree: Path, config: dict) -> None:
    for rel in config["test_files"]:
        shutil.copyfile(PRISTINE / Path(rel).name, tree / rel)


def _argv(tree: Path, config: dict) -> list[str]:
    # The repository's pytest configuration is kept (its filterwarnings turn several
    # warnings into errors); only its addopts are replaced, because they name a plugin
    # (pytest-randomly) that neither image installs.
    return [
        PY, "-I", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--import-mode=prepend",
        "-c", str(tree / "pyproject.toml"), "-o", "addopts=--strict-markers",
        f"--rootdir={tree}", "--junitxml={scratch}/tmp/junit.xml",
        *[str(tree / rel) for rel in config["test_files"]],
    ]


def _parse(xml_text: str) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for case in ET.fromstring(xml_text).iter("testcase"):
        key = f"{case.get('classname')}::{case.get('name')}"
        tags = {child.tag for child in case}
        if tags & {"failure", "error"}:
            outcomes[key] = FAILED
        elif SKIPPED in tags:
            outcomes[key] = SKIPPED
        else:
            outcomes[key] = PASSED
    return outcomes


def _execute(
    guard, tree: Path, config: dict, timeout: float
) -> tuple[runner.RunResult, dict[str, str]]:
    res = runner.run_restricted(
        _argv(tree, config), guard=guard, timeout=timeout, collect=("tmp/junit.xml",)
    )
    xml_text = res.collected.get("tmp/junit.xml")
    if xml_text is None:
        return res, {}
    try:
        return res, _parse(xml_text)
    except ET.ParseError:
        return res, {}


def run(guard, tree: Path, config: dict, timeout: float) -> TestOutcome:
    res, outcomes = _execute(guard, tree, config, timeout)
    if not outcomes:
        return TestOutcome(
            res,
            {},
            0,
            [
                f"covering tests produced no report (exit {res.returncode}, timeout={res.timed_out})"
            ],
        )
    baseline = json.loads(BASELINE.read_text())
    failures = [
        f"covering test fails: {key}"
        for key in baseline["required"]
        if outcomes.get(key) != PASSED
    ]
    return TestOutcome(res, outcomes, len(outcomes), failures)


def baseline(base: Path, expert: Path, out: Path, config: dict) -> None:
    guard = runner.PersistenceGuard(config["runner_uid"])
    record = {}
    for name, tree in (("base", base), ("expert", expert)):
        work = Path(f"/opt/kraken/work/baseline-{name}")
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(tree, work, symlinks=True)
        install_pristine(work, config)
        res, outcomes = _execute(guard, work, config, config["pytest_timeout_sec"])
        shutil.rmtree(work)
        if not outcomes:
            raise SystemExit(
                f"baseline run on {name} produced no report: {res.stderr[-3000:]}"
            )
        record[name] = outcomes
    base_pass = {k for k, v in record["base"].items() if v == PASSED}
    expert_pass = {k for k, v in record["expert"].items() if v == PASSED}
    lost = sorted(base_pass - expert_pass)
    if lost:
        raise SystemExit(f"the reference tree fails tests the base passes: {lost[:10]}")
    summary = {
        "required": sorted(base_pass & expert_pass),
        "excluded_fail_on_base": sorted(
            k for k, v in record["base"].items() if v == FAILED
        ),
        "skipped_on_base": sorted(k for k, v in record["base"].items() if v == SKIPPED),
        "collected": len(record["base"]),
    }
    out.write_text(json.dumps(summary, indent=1))
    print(
        json.dumps(
            {k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}
        )
    )


if __name__ == "__main__":
    if len(sys.argv) != 6 or sys.argv[1] != "baseline":
        raise SystemExit(__doc__)
    baseline(
        Path(sys.argv[2]),
        Path(sys.argv[3]),
        Path(sys.argv[4]),
        json.loads(Path(sys.argv[5]).read_text()),
    )
