"""Build numpy trees into importable site directories with meson-python.

Image time (root, once):   build.py image <base-src> <expert-src>
  builds the pristine base into /opt/kraken/base-site, the base plus the upstream
  library change into /opt/kraken/expert-site, and leaves /opt/kraken/work/graded as
  the base source with a build directory built from it (the warm tree).

Verify time: rebuild() compiles the overlaid warm tree as the builder uid, so only
the files the submission changed are recompiled, and installs it into a fresh site.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))

import runner  # noqa: E402

PY = "/opt/venv/bin/python"
KRAKEN = Path("/opt/kraken")
GRADED = KRAKEN / "work" / "graded"
BUILD_DIR = GRADED / "build"


@dataclass(frozen=True, slots=True)
class BuildResult:
    ok: bool
    seconds: float
    log: str
    leftovers: tuple[str, ...]


def pip_argv(tree: Path, site: Path) -> list[str]:
    return [
        PY,
        "-m",
        "pip",
        "install",
        "--no-build-isolation",
        "--no-deps",
        "--no-index",
        "--no-cache-dir",
        "--disable-pip-version-check",
        "--target",
        str(site),
        str(tree),
        f"-Cbuild-dir={BUILD_DIR}",
        # Four compile jobs: one job per visible CPU runs a many-core builder out of memory.
        "-Ccompile-args=-j4",
    ]


def _image_build(site: Path) -> None:
    env = {**runner.BASE_ENV, "HOME": "/root", "TMPDIR": "/tmp"}
    subprocess.run(pip_argv(GRADED, site), env=env, cwd="/", check=True)


def _copy_fresh(src_root: Path, rels: list[str]) -> None:
    """Copy files into the warm tree with a new mtime so ninja recompiles them."""
    for rel in rels:
        target = GRADED / rel
        shutil.copyfile(src_root / rel, target)
        os.utime(target)


def image(base_src: Path, expert_src: Path) -> None:
    rels = sorted(p.relative_to(expert_src).as_posix() for p in expert_src.rglob("*") if p.is_file())
    shutil.copytree(base_src, KRAKEN / "base-src", symlinks=True)
    shutil.copytree(base_src, GRADED, symlinks=True)
    _image_build(KRAKEN / "base-site")
    _copy_fresh(expert_src, rels)
    _image_build(KRAKEN / "expert-site")
    _copy_fresh(base_src, rels)
    _image_build(Path("/tmp/warm-site"))
    shutil.rmtree("/tmp/warm-site")


def rebuild(site: Path, uid: int, timeout: float) -> BuildResult:
    """Compile and install the overlaid warm tree as uid; any failure is a failed build."""
    for path in (GRADED.parent, site.parent):
        path.mkdir(parents=True, exist_ok=True)
    if site.exists():
        shutil.rmtree(site)
    subprocess.run(["chown", "-R", f"{uid}:{uid}", str(GRADED.parent)], check=True)
    guard = runner.PersistenceGuard(uid, skip=(str(GRADED.parent),))
    import time

    started = time.monotonic()
    res = runner.run_restricted(
        pip_argv(GRADED, site), guard=guard, pythonpath="", timeout=timeout
    )
    seconds = time.monotonic() - started
    ok = res.returncode == 0 and (site / "numpy" / "__init__.py").is_file()
    log = res.stdout[-20000:] + "\n--- stderr ---\n" + res.stderr
    return BuildResult(ok, round(seconds, 1), log, res.leftovers)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "image":
        raise SystemExit(__doc__)
    image(Path(sys.argv[2]), Path(sys.argv[3]))
