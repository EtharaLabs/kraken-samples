"""Judge lineage guard and gate reader for tests/test.sh.

usage: judge_guard.py guard
       judge_guard.py gate <compiled reward.json> <compiled reward-details.json>
       judge_guard.py zero <compiled reward.json> <reward.json>
       judge_guard.py judged <reward-details.json>

`guard` exits 3 and writes /logs/verifier/verifier-error.json when a judge
variable is missing, the declared lineage is excluded, or the model group names
an excluded family. `gate` prints "open" when every gate holds, else "closed":
no red line fired in the measurement record (G2), the compiled-only `correctness`
diagnostic is 1.0 exactly when G1 and G3 hold, and
the compiled-only reward is above zero exactly when G4 holds (no compiled item
scores above zero while every family share is zero). It also writes the per-item
verdicts beside the compiled record as verdicts.json. `zero` writes the reward
record of a failed gate: reward 0.0, the compiled diagnostics unchanged.
`judged` exits 3 with reason judge-unavailable when any judged score carries an
error. Installed outside /tests so Reward Kit never imports it.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ERROR_PATH = Path("/logs/verifier/verifier-error.json")
VARIABLES = (
    "REWARDKIT_JUDGE",
    "KRAKEN_JUDGE_LINEAGE",
    "LITELLM_PROXY_API_BASE",
    "LITELLM_PROXY_API_KEY",
)
# Contract revision 8 (2026-10-28) admits OpenAI GPT judges; Anthropic (authoring) and Meta stay excluded.
EXCLUDED_LINEAGES = frozenset({"anthropic", "meta"})
EXCLUDED_FAMILIES = ("claude", "opus", "fable", "muse")
ROUTE = "litellm_proxy/"


def _refuse(reason: str, detail: str) -> None:
    ERROR_PATH.parent.mkdir(parents=True, exist_ok=True)
    ERROR_PATH.write_text(
        json.dumps(
            {"verifier_error": True, "reason": reason, "detail": detail}, sort_keys=True
        )
    )
    print(f"verifier error: {reason}: {detail}", file=sys.stderr)
    raise SystemExit(3)


def guard() -> None:
    missing = [name for name in VARIABLES if not os.environ.get(name, "").strip()]
    if missing:
        _refuse("judge-variable-missing", ",".join(missing))
    lineage_tokens = set(
        re.split(r"[^a-z0-9]+", os.environ["KRAKEN_JUDGE_LINEAGE"].lower())
    ) - {""}
    if lineage_tokens & EXCLUDED_LINEAGES:
        _refuse(
            "judge-lineage-excluded",
            ",".join(sorted(lineage_tokens & EXCLUDED_LINEAGES)),
        )
    model = os.environ["REWARDKIT_JUDGE"].strip().lower()
    if not model.startswith(ROUTE):
        _refuse(
            "judge-model-route-invalid",
            "REWARDKIT_JUDGE must be litellm_proxy/<model group>",
        )
    families = [f for f in EXCLUDED_FAMILIES if f in model]
    if families:
        _refuse("judge-model-family-excluded", ",".join(families))


def _compiled(path: Path) -> dict | None:
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def _criteria(node: object) -> list[dict]:
    """The criteria of the first test_output component found in a reward-details tree."""
    match node:
        case {"name": "test_output", "detail": {"criteria": list(found)}}:
            return [c for c in found if isinstance(c, dict)]
        case dict():
            values = node.values()
        case list():
            values = node
        case _:
            return []
    for value in values:
        found = _criteria(value)
        if found:
            return found
    return []


MEASURE_PATH = Path("/logs/verifier/measure.json")


def _red_lines() -> list[str]:
    """Every red line the measurement fired; unreadable counts as fired (fail closed).

    The correctness diagnostic reports behavior only, so the gate reads the red lines from the
    measurement record itself rather than through it."""
    try:
        record = json.loads(MEASURE_PATH.read_text())
        fired = record["red_lines"]
    except (OSError, ValueError, KeyError, TypeError):
        return ["measurement-unreadable"]
    if not isinstance(fired, dict):
        return ["red-lines-malformed"]
    return sorted(name for name, hits in fired.items() if hits)


def gate(path: Path, details: Path) -> None:
    record = _compiled(path) or {}
    try:
        correctness = float(record["correctness"])
        state = (
            "open"
            if correctness == 1.0
            and float(record["reward"]) > 0.0
            and not _red_lines()
            else "closed"
        )
    except (KeyError, TypeError, ValueError):
        state = "closed"
    try:
        tree = json.loads(details.read_text())
    except (OSError, ValueError):
        tree = {}
    items = {}
    for entry in _criteria(tree):
        try:
            reason = json.loads(entry.get("reasoning") or "{}")
        except ValueError:
            reason = {}
        items[str(entry.get("name"))] = {
            "score": entry.get("value"),
            "verdict": "accept" if (entry.get("value") or 0.0) > 0.0 else "reject",
            "holds": reason.get("holds"),
            "gates": reason.get("gates"),
        }
    out = {"gate": state, "compiled_reward": record.get("reward"), "items": items}
    (path.parent / "verdicts.json").write_text(json.dumps(out, indent=1, sort_keys=True))
    print(state)


def zero(path: Path, out: Path) -> None:
    record = _compiled(path) or {}
    keys = ("reward", "correctness", "worst_case_speedup")
    result = {key: float(record.get(key, 0.0)) for key in keys}
    result["reward"] = 0.0
    out.write_text(json.dumps(result, indent=2))


def _errors(node: object) -> list[str]:
    match node:
        case dict():
            found = [str(node["error"])] if node.get("error") else []
            return found + [e for value in node.values() for e in _errors(value)]
        case list():
            return [e for value in node for e in _errors(value)]
        case _:
            return []


def judged(path: Path) -> None:
    try:
        details = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        _refuse("judge-unavailable", f"reward details unreadable: {type(exc).__name__}")
    errors = _errors(details)
    if errors:
        _refuse("judge-unavailable", "; ".join(errors)[:500])


def main(argv: list[str]) -> None:
    match argv:
        case ["guard"]:
            guard()
        case ["gate", path, details]:
            gate(Path(path), Path(details))
        case ["zero", path, out]:
            zero(Path(path), Path(out))
        case ["judged", path]:
            judged(Path(path))
        case _:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
