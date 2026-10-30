"""Repository tests covering the edited code.

The pass set of the base commit is recorded at image build time with the same
command (`repotests.py baseline`). A submission passes when every test the base
commit passes still passes and every test in the expert's added test file passes.

usage at build time: repotests.py baseline <tree> <out.json> <config.json>
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
BASELINE = Path("/opt/kraken/base-pass.json")


@dataclass(frozen=True, slots=True)
class TestOutcome:
    result: runner.RunResult
    outcomes: dict[str, str]
    collected: int
    failures: list[str]


PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"
BASELINE_MODE = "baseline"

def _argv(config: dict) -> list[str]:
    return [
        PY,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "no:randomly",
        *[f"--ignore={p}" for p in config["test_ignore"]],
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
            outcomes[key] = SKIPPED
        else:
            outcomes[key] = PASSED
    return outcomes


def in_f2p_file(key: str, f2p_test: str) -> bool:
    """Whether a junit key `<module path>[.<Class>]::<name>` belongs to the expert's test file.

    pytest reports the module path relative to its rootdir, so the dotted path of
    `tests/core/operator/x.py` may appear as `core.operator.x`; every suffix of at
    least two components is accepted.
    """
    module = key.split("::", 1)[0]
    parts = f2p_test.removesuffix(".py").split("/")
    suffixes = [".".join(parts[i:]) for i in range(len(parts) - 1)]
    return any(module == s or module.startswith(s + ".") for s in suffixes)


def _execute(
    guard: runner.PersistenceGuard, tree: Path, config: dict, timeout: float
) -> tuple[runner.RunResult, dict[str, str]]:
    res = runner.run_restricted(
        _argv(config),
        guard=guard,
        pythonpath=str(tree),
        cwd=str(tree),
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


def run(
    guard: runner.PersistenceGuard, tree: Path, config: dict, timeout: float
) -> TestOutcome:
    res, outcomes = _execute(guard, tree, config, timeout)
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
    f2p = [key for key in outcomes if in_f2p_file(key, config["f2p_test"])]
    if len(f2p) < baseline["f2p_count"]:
        failures.append(
            f"expert test file collected {len(f2p)} of {baseline['f2p_count']} tests"
        )
    failures += [
        f"covering test fails: {key}" for key in f2p if outcomes[key] != PASSED
    ]
    return TestOutcome(res, outcomes, len(outcomes), failures)


def baseline(tree: Path, out: Path, config: dict) -> None:
    guard = runner.PersistenceGuard(config["runner_uid"])
    res, outcomes = _execute(guard, tree, config, config["pytest_timeout_sec"])
    if not outcomes:
        raise SystemExit(f"baseline run produced no report: {res.stderr[-2000:]}")
    f2p = config["f2p_test"]
    record = {
        "passed": sorted(k for k, v in outcomes.items() if v == PASSED and not in_f2p_file(k, f2p)),
        "failed_on_base": sorted(k for k, v in outcomes.items() if v == FAILED),
        "f2p_count": sum(1 for k in outcomes if in_f2p_file(k, f2p)),
        "collected": len(outcomes),
    }
    out.write_text(json.dumps(record, indent=1))
    print(
        json.dumps(
            {k: (len(v) if isinstance(v, list) else v) for k, v in record.items()}
        )
    )


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != BASELINE_MODE:
        raise SystemExit(__doc__)
    baseline(
        Path(sys.argv[2]), Path(sys.argv[3]), json.loads(Path(sys.argv[4]).read_text())
    )
