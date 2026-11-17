"""Judge lineage guard and gate reader for tests/test.sh.

usage: judge_guard.py guard
       judge_guard.py gate <compiled reward.json> <compiled reward-details.json>
       judge_guard.py zero <compiled reward.json> <reward.json>
       judge_guard.py judged <reward-details.json>
       judge_guard.py diagnostic <compiled reward.json>

`guard` exits 3 and writes /logs/verifier/verifier-error.json when a judge variable is
missing, the declared lineage is excluded or not admitted, or the model route or family is
wrong; an admitted lineage is recorded in /logs/verifier/judge-lineage.json with its
same-lineage note. `gate` prints "open" when every gate holds, else "closed": the
measurement record carries no fired red line (G2), the compiled-only `correctness`
diagnostic is 1.0 (G1, G3, G4) and the compiled-only reward, which equals the speed credit
P when those hold, is above zero (G5). It also writes the per-item verdicts beside the
compiled record as verdicts.json. `zero` writes the reward record of a closed gate: reward
0.0, the compiled diagnostics unchanged. `judged` exits 3 with reason judge-unavailable
when any judged score carries an error. `diagnostic` (local /opt/kraken/compiled_only.sh) writes a
verifier-error.json naming the compiled credit, so the mode can never yield a score.
Installed at /opt/kraken, outside /tests, so Reward Kit never imports it.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Final, NoReturn

VERIFIER: Final = Path("/logs/verifier")
ERROR_PATH: Final = VERIFIER / "verifier-error.json"
LINEAGE_PATH: Final = VERIFIER / "judge-lineage.json"
MEASURE_PATH: Final = VERIFIER / "measure.json"
VARIABLES: Final = ("REWARDKIT_JUDGE", "OPENAI_API_KEY")
# The judge's lineage is the provider part of REWARDKIT_JUDGE: openai is admitted; Anthropic
# (the authoring lineage), Meta and any other provider are refused.
ADMITTED_LINEAGES: Final = ("openai",)
EXCLUDED_LINEAGES: Final = ("anthropic", "meta")
EXCLUDED_FAMILIES: Final = ("claude", "opus", "fable", "muse", "llama")
SAME_LINEAGE_NOTES: Final = {
    "openai": (
        "the judge gpt-6-astra and the client pilot solver GPT-6.1-sol are both OpenAI models; "
        "judgments of GPT-6.1-sol rollouts are same-lineage "
        "(contract coverage gap judge-same-lineage-as-pilot-solver)"
    ),
}
ROUTE: Final = "openai/"
CORRECTNESS: Final = "correctness"
DIAGNOSTIC_KEYS: Final = ("reward", CORRECTNESS, "worst_case_speedup")


FALLBACK_PATH = Path("/logs/verifier/judge-fallback.json")


def _fallback(reason: str, detail: str) -> None:
    FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FALLBACK_PATH.write_text(
        json.dumps({"judge_fallback": True, "reason": reason, "detail": detail}, sort_keys=True)
    )
    print(f"judge fallback: {reason}: {detail}", file=sys.stderr)
    raise SystemExit(3)


def _refuse(reason: str, detail: str) -> NoReturn:
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
        _fallback("judge-variable-missing", ",".join(missing))
    tokens = set(
        re.split(r"[^a-z0-9]+", os.environ["REWARDKIT_JUDGE"].strip().lower().split("/", 1)[0])
    ) - {""}
    excluded = sorted(tokens & set(EXCLUDED_LINEAGES))
    if excluded:
        _fallback("judge-lineage-excluded", ",".join(excluded))
    if not tokens or not tokens <= set(ADMITTED_LINEAGES):
        _fallback("judge-lineage-not-admitted", ",".join(sorted(tokens)) or "empty")
    model = os.environ["REWARDKIT_JUDGE"].strip().lower()
    if not model.startswith(ROUTE):
        _fallback(
            "judge-model-route-invalid",
            "REWARDKIT_JUDGE must be openai/<model>",
        )
    families = [f for f in EXCLUDED_FAMILIES if f in model]
    if families:
        _fallback("judge-model-family-excluded", ",".join(families))
    record = {
        "lineage": sorted(tokens),
        "same_lineage_notes": [
            SAME_LINEAGE_NOTES[t] for t in sorted(tokens) if t in SAME_LINEAGE_NOTES
        ],
    }
    LINEAGE_PATH.write_text(json.dumps(record, indent=1, sort_keys=True))


def _compiled(path: Path) -> dict[str, object]:
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def _criteria(node: object) -> list[dict[str, object]]:
    """The criteria of the first test_output component found in a reward-details tree."""
    match node:
        case {"name": "test_output", "detail": {"criteria": list(found)}}:
            return [c for c in found if isinstance(c, dict)]
        case dict():
            values = list(node.values())
        case list():
            values = node
        case _:
            return []
    for value in values:
        found = _criteria(value)
        if found:
            return found
    return []


def _red_lines() -> list[str]:
    """Every red line the measurement fired; unreadable counts as fired (fail closed)."""
    try:
        fired = json.loads(MEASURE_PATH.read_text())["red_lines"]
    except (OSError, ValueError, KeyError, TypeError):
        return ["measurement-unreadable"]
    if not isinstance(fired, dict):
        return ["red-lines-malformed"]
    return sorted(name for name, hits in fired.items() if hits)


def _float(record: dict[str, object], key: str) -> float:
    value = record.get(key)
    return float(value) if isinstance(value, (int, float)) else 0.0


def gate(path: Path, details: Path) -> None:
    record = _compiled(path)
    fired = _red_lines()
    open_ = (
        CORRECTNESS in record
        and _float(record, CORRECTNESS) == 1.0
        and _float(record, "reward") > 0.0
        and not fired
    )
    try:
        tree: object = json.loads(details.read_text())
    except (OSError, ValueError):
        tree = {}
    items: dict[str, dict[str, object]] = {}
    for entry in _criteria(tree):
        raw = entry.get("reasoning")
        try:
            reason = json.loads(raw) if isinstance(raw, str) else {}
        except ValueError:
            reason = {}
        value = entry.get("value")
        score = float(value) if isinstance(value, (int, float)) else 0.0
        # The item's own verdict comes from its criterion (test_output.py _own), decided
        # whatever the gates say; a diagnostic without one falls back to its score.
        own = reason.get("verdict") if isinstance(reason, dict) else None
        items[str(entry.get("name"))] = {
            "score": score,
            "verdict": own
            if isinstance(own, str) and own
            else ("accept" if score > 0.0 else "reject"),
            "detail": reason,
        }
    state = "open" if open_ else "closed"
    out = {"gate": state, "red_lines": fired, "compiled": record, "items": items}
    (path.parent / "verdicts.json").write_text(
        json.dumps(out, indent=1, sort_keys=True)
    )
    print(state)


def zero(path: Path, out: Path) -> None:
    record = _compiled(path)
    result = {key: _float(record, key) for key in DIAGNOSTIC_KEYS}
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
        _fallback("judge-unavailable", f"reward details unreadable: {type(exc).__name__}")
    errors = _errors(details)
    if errors:
        _fallback("judge-unavailable", "; ".join(errors)[:500])


def diagnostic(path: Path) -> NoReturn:
    record = _compiled(path)
    detail = {key: _float(record, key) for key in DIAGNOSTIC_KEYS}
    _refuse("compiled-only-diagnostic", json.dumps(detail, sort_keys=True))


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
        case ["diagnostic", path]:
            diagnostic(Path(path))
        case _:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
