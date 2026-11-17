"""Repository tests of a built site: the linear_model test package.

The tests always come from the base source: the graded tree never takes test
changes, so the site under test carries the base commit's test files. The base
build's pass set is recorded at image build time with the same command
(`repotests.py baseline`). A submission passes when every test the base build
passes still passes and every test in the covering files passes.

usage at build time: repotests.py baseline <site> <out.json> <config.json>
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))

import runner  # noqa: E402

PY = "/opt/venv/bin/python"
BASELINE = Path("/opt/harness/base-pass.json")
PASSED, FAILED, SKIPPED = "passed", "failed", "skipped"


@dataclass(frozen=True, slots=True)
class TestOutcome:
    result: runner.RunResult
    outcomes: dict[str, str]
    collected: int
    failures: list[str]


def _argv(site: Path, config: dict) -> list[str]:
    return [
        PY,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        f"--rootdir={site}",
        "--junitxml={scratch}/tmp/junit.xml",
        *config["test_selection"],
    ]


def _parse(xml_text: str) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for case in ET.fromstring(xml_text).iter("testcase"):
        key = f"{case.get('classname')}::{case.get('name')}"
        tags = {child.tag for child in case}
        if tags & {"failure", "error"}:
            outcomes[key] = FAILED
        elif SKIPPED in tags:
            outcomes.setdefault(key, SKIPPED)
        elif outcomes.get(key) != FAILED:
            outcomes[key] = PASSED
    return outcomes


def covering(key: str, config: dict) -> bool:
    """Whether a junit key `<dotted module>[.<Class>]::<name>` is in a covering file."""
    module = key.split("::", 1)[0]
    for rel in config["covering_tests"]:
        dotted = rel.removesuffix(".py").replace("/", ".")
        if module == dotted or module.startswith(dotted + "."):
            return True
    return False


def _execute(
    guard: runner.PersistenceGuard, site: Path, config: dict, timeout: float
) -> tuple[runner.RunResult, dict[str, str]]:
    res = runner.run_restricted(
        _argv(site, config),
        guard=guard,
        pythonpath=str(site),
        cwd=str(site),
        timeout=timeout,
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
    res, outcomes = _execute(guard, site, config, config["pytest_timeout_sec"])
    if not outcomes:
        return TestOutcome(
            res,
            {},
            0,
            [
                f"repository tests produced no report (exit {res.returncode}, timeout={res.timed_out})"
            ],
        )
    baseline = json.loads(BASELINE.read_text())
    failures = [
        f"test no longer passes: {key}"
        for key in baseline["passed"]
        if outcomes.get(key) != PASSED
    ]
    cover = [key for key in outcomes if covering(key, config)]
    if len(cover) < baseline["covering_count"]:
        failures.append(
            f"covering files collected {len(cover)} of {baseline['covering_count']} tests"
        )
    failures += [
        f"covering test fails: {key}"
        for key in cover
        if outcomes[key] not in (PASSED, SKIPPED)
        or (outcomes[key] == SKIPPED and key not in baseline["covering_skipped"])
    ]
    return TestOutcome(res, outcomes, len(outcomes), failures)


def baseline(site: Path, out: Path, config: dict) -> None:
    guard = runner.PersistenceGuard(config["runner_uid"])
    res, outcomes = _execute(guard, site, config, config["pytest_timeout_sec"])
    if not outcomes:
        raise SystemExit(f"baseline run produced no report: {res.stderr[-2000:]}")
    record = {
        "passed": sorted(k for k, v in outcomes.items() if v == PASSED),
        "failed_on_base": sorted(k for k, v in outcomes.items() if v == FAILED),
        "covering_skipped": sorted(
            k for k, v in outcomes.items() if v == SKIPPED and covering(k, config)
        ),
        "covering_count": sum(1 for k in outcomes if covering(k, config)),
        "collected": len(outcomes),
    }
    out.write_text(json.dumps(record, indent=1))
    print(
        json.dumps(
            {k: (len(v) if isinstance(v, list) else v) for k, v in record.items()}
        )
    )


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "baseline":
        raise SystemExit(__doc__)
    baseline(
        Path(sys.argv[2]), Path(sys.argv[3]), json.loads(Path(sys.argv[4]).read_text())
    )
