"""Covering repository tests: the StringDType and set-routine test modules.

The verifier always runs its own pristine copies of the test files (from the base
build) against the build under test. The base build's pass set is recorded at image
build time with the same command (`repotests.py baseline`); a submission passes
when every test the base passes still passes.

usage at build time: repotests.py baseline <config.json>
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
BASE_SITE = Path("/opt/kraken/base-site")
BASELINE = Path("/opt/kraken/base-pass.json")
BASELINE_MODE = "baseline"
PASSED, FAILED, SKIPPED = "passed", "failed", "skipped"


@dataclass(frozen=True, slots=True)
class TestOutcome:
    result: runner.RunResult
    collected: int
    failures: list[str]


def install_pristine(site: Path, config: dict) -> None:
    """Replace the test files of site with the base build's copies."""
    for rel in config["pristine_test_paths"]:
        src, dst = BASE_SITE / rel, site / rel
        if dst.is_dir():
            shutil.rmtree(dst)
        elif dst.exists():
            dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copyfile(src, dst)


def _argv(site: Path, config: dict) -> list[str]:
    return [
        PY,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
        f"--rootdir={site}",
        "--junitxml={scratch}/tmp/junit.xml",
        *[str(site / rel) for rel in config["test_selection"]],
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


def execute(
    guard: runner.PersistenceGuard, site: Path, config: dict
) -> tuple[runner.RunResult, dict[str, str]]:
    res = runner.run_restricted(
        _argv(site, config),
        guard=guard,
        pythonpath=str(site),
        timeout=config["pytest_timeout_sec"],
        collect=("tmp/junit.xml",),
    )
    xml_text = res.collected.get("tmp/junit.xml")
    if xml_text is None:
        return res, {}
    try:
        return res, _parse(xml_text)
    except ET.ParseError:
        return res, {}


def run(guard: runner.PersistenceGuard, site: Path, config: dict) -> TestOutcome:
    res, outcomes = execute(guard, site, config)
    if not outcomes:
        return TestOutcome(
            res,
            0,
            [
                f"covering tests produced no report (exit {res.returncode}, timeout={res.timed_out})"
            ],
        )
    baseline = json.loads(BASELINE.read_text())
    failures = [
        f"test no longer passes: {key}"
        for key in baseline["passed"]
        if outcomes.get(key) != PASSED
    ]
    return TestOutcome(res, len(outcomes), failures)


def baseline(config: dict) -> None:
    guard = runner.PersistenceGuard(config["runner_uid"])
    res, outcomes = execute(guard, BASE_SITE, config)
    if not outcomes:
        raise SystemExit(f"baseline run produced no report: {res.stderr[-2000:]}")
    record = {
        "passed": sorted(k for k, v in outcomes.items() if v == PASSED),
        "failed_on_base": sorted(k for k, v in outcomes.items() if v == FAILED),
        "collected": len(outcomes),
    }
    BASELINE.write_text(json.dumps(record, indent=1))
    print(
        json.dumps(
            {k: (len(v) if isinstance(v, list) else v) for k, v in record.items()}
        )
    )


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != BASELINE_MODE:
        raise SystemExit(__doc__)
    baseline(json.loads(Path(sys.argv[2]).read_text()))
