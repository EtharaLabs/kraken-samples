# Verifier copy of environment/build/graft.py; the two differ only by this line.
"""Make a statsmodels source tree importable in place.

usage: graft.py <installed-package-dir> <source-tree>

Copies every file of the installed (built) statsmodels package that the source
tree lacks, which is the compiled extension modules and the generated
_version.py, to the same relative path in the source tree. Files that exist in
both are left as the source tree has them.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main(installed: Path, tree: Path) -> None:
    pkg = tree / "statsmodels"
    copied = 0
    for path in sorted(installed.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(installed)
        target = pkg / rel
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    print(f"grafted {copied} built files into {pkg}")
    if not copied:
        raise SystemExit("nothing grafted: the build produced no extension modules")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
