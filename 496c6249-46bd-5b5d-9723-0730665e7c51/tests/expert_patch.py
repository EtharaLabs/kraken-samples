"""Apply tests/expert-c2.patch to the reference source tree in the verifier image (exact context, no fuzz).

The reference is the upstream fix 7643e77e extended with an authored C hash path for StringDType
membership; the image fetch stage copies the upstream files and this script
adds the extension. usage: expert_patch.py <tree> <patch>
"""

import re
import sys
from pathlib import Path

HUNK = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def main(tree: Path, patch: Path) -> None:
    for chunk in re.split(r"^diff --git ", patch.read_text(), flags=re.MULTILINE)[1:]:
        rel = re.search(r"^\+\+\+ b/(.+)$", chunk, re.MULTILINE).group(1)
        path = tree / rel
        src = path.read_text().split("\n")
        out, pos = [], 0
        for hunk in re.split(r"^(?=@@ )", chunk, flags=re.MULTILINE)[1:]:
            old_start = int(HUNK.match(hunk).group(1))
            body = hunk.split("\n")[1:]
            if body and body[-1] == "":
                body = body[:-1]
            before = [line[1:] for line in body if line[:1] in (" ", "-")]
            after = [line[1:] for line in body if line[:1] in (" ", "+")]
            start = old_start - 1
            if src[start : start + len(before)] != before:
                sys.exit(f"expert-c2.patch: hunk does not match {rel} at line {start + 1}")
            out += src[pos:start] + after
            pos = start + len(before)
        path.write_text("\n".join(out + src[pos:]))
        print(f"extended {rel}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
