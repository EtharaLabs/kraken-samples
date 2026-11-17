"""Judge binding guard for tests/test.sh.

usage: judge_guard.py guard
       judge_guard.py judged <reward-details.json>

`guard` exits 3 with a machine-readable reason in /logs/verifier/judge-fallback.json
when REWARDKIT_JUDGE or OPENAI_API_KEY is missing, or the judge is not an OpenAI model
(route openai/, no Anthropic, Meta or Claude family: the tasks were authored with Claude).
`judged` exits 3 with reason judge-unavailable when any judged score carries an
error. On either exit test.sh falls back to the compiled-only reward.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REASON_PATH = Path("/logs/verifier/judge-fallback.json")
VARIABLES = ("REWARDKIT_JUDGE", "OPENAI_API_KEY")
EXCLUDED_FAMILIES = ("claude", "opus", "sonnet", "haiku", "llama")
ROUTE = "openai/"


def _refuse(reason: str, detail: str) -> None:
    REASON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REASON_PATH.write_text(
        json.dumps(
            {"judge_fallback": True, "reason": reason, "detail": detail}, sort_keys=True
        )
    )
    print(f"judge fallback: {reason}: {detail}", file=sys.stderr)
    raise SystemExit(3)


def guard() -> None:
    missing = [name for name in VARIABLES if not os.environ.get(name, "").strip()]
    if missing:
        _refuse("judge-variable-missing", ",".join(missing))
    model = os.environ["REWARDKIT_JUDGE"].strip().lower()
    if not model.startswith(ROUTE):
        _refuse(
            "judge-model-route-invalid",
            "REWARDKIT_JUDGE must be openai/<model>",
        )
    families = [f for f in EXCLUDED_FAMILIES if f in model]
    if families:
        _refuse("judge-model-family-excluded", ",".join(families))


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
        case ["judged", path]:
            judged(Path(path))
        case _:
            raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
