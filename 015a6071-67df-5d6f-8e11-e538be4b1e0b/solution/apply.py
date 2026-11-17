"""Strict unified-diff applier for the oracle (exact context, no fuzz).

usage: apply.py OP [OP ...]   with OP = +PATCH (apply) or -PATCH (revert)

PATCH is relative to this file's directory; the working tree is /app/cirq.
The sandbox has no git or patch binary. Operations run left to right and every
hunk must match exactly, so a revert only succeeds on the tree its patch made. A file
the patch creates (`--- /dev/null`) must not exist before it is applied, and its revert
removes it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TREE = Path("/app/cirq")
HERE = Path(__file__).resolve().parent
HUNK = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")

def _hunks(chunk: str) -> list[tuple[int, int, list[str]]]:
    out = []
    for hunk in re.split(r"^(?=@@ )", chunk, flags=re.M)[1:]:
        old_start, new_start = (int(x) for x in HUNK.match(hunk).groups())
        body = hunk.split("\n")[1:]
        if body and body[-1] == "":
            body = body[:-1]
        out.append((old_start, new_start, body))
    return out

def apply(patch: Path, *, revert: bool) -> None:
    text = patch.read_text()
    for chunk in re.split(r"^diff --git ", text, flags=re.M)[1:]:
        rel = re.search(r"^\+\+\+ b/(.+)$", chunk, re.M).group(1)
        path = TREE / rel
        created = re.search(r"^--- /dev/null$", chunk, re.M) is not None
        if (revert or not created) and not path.is_file():
            sys.exit(f"{patch.name}: {rel} is missing")
        if created and not revert:
            if path.exists():
                sys.exit(f"{patch.name}: {rel} already exists")
            path.parent.mkdir(parents=True, exist_ok=True)
            src = [""]
        else:
            src = path.read_text().split("\n")
        out, pos = [], 0
        drop, keep = ("+", "-") if revert else ("-", "+")
        for old_start, new_start, body in _hunks(chunk):
            start = max((new_start if revert else old_start) - 1, 0)
            before = [line[1:] for line in body if line[:1] in (" ", drop)]
            after = [line[1:] for line in body if line[:1] in (" ", keep)]
            if src[start : start + len(before)] != before:
                sys.exit(f"{patch.name}: hunk does not match {rel} at line {start + 1}")
            out += src[pos:start] + after
            pos = start + len(before)
        if created and revert:
            if out + src[pos:] != [""]:
                sys.exit(f"{patch.name}: {rel} differs from the file the patch created")
            path.unlink()
        else:
            path.write_text("\n".join(out + src[pos:]))
        print(f"{'reverted' if revert else 'patched'} {rel} ({patch.name})")

def main(ops: list[str]) -> None:
    if not ops or any(op[:1] not in "+-" for op in ops):
        raise SystemExit(__doc__)
    for op in ops:
        apply(HERE / op[1:], revert=op[0] == "-")

if __name__ == "__main__":
    main(sys.argv[1:])
