"""Build scikit-learn trees into importable site directories with meson-python.

Image time (root, once):   build.py image <base-src> <expert-overlay>
  copies the pristine base source to /opt/harness/base-src, builds it into
  /opt/harness/base-site, lays the reference library files over a copy and builds
  /opt/harness/expert-site, then restores the base files so /opt/harness/work/graded
  is the base source with an up-to-date build directory (the warm tree).

Verify time: rebuild() compiles the overlaid warm tree as the builder uid, so only
the files the submission changed are recompiled, and installs it into a fresh site.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))

import runner  # noqa: E402

PY = "/opt/venv/bin/python"
ROOT = Path("/opt/harness")
GRADED = ROOT / "work" / "graded"
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


def image(base_src: Path, expert_overlay: Path) -> None:
    rels = sorted(
        p.relative_to(expert_overlay).as_posix()
        for p in expert_overlay.rglob("*")
        if p.is_file()
    )
    shutil.copytree(base_src, ROOT / "base-src", symlinks=True)
    shutil.copytree(base_src, GRADED, symlinks=True)
    _image_build(ROOT / "base-site")
    _copy_fresh(expert_overlay, rels)
    _image_build(ROOT / "expert-site")
    _copy_fresh(base_src, rels)
    _image_build(Path("/tmp/warm-site"))
    shutil.rmtree("/tmp/warm-site")


def rebuild(site: Path, uid: int, timeout: float) -> BuildResult:
    """Compile and install the overlaid warm tree as uid; any failure is a failed build."""
    site.parent.mkdir(parents=True, exist_ok=True)
    if site.exists():
        shutil.rmtree(site)
    subprocess.run(["chown", "-R", f"{uid}:{uid}", str(GRADED.parent)], check=True)
    guard = runner.PersistenceGuard(uid, skip=(str(GRADED.parent),))
    started = time.monotonic()
    res = runner.run_restricted(
        pip_argv(GRADED, site), guard=guard, pythonpath="", timeout=timeout
    )
    seconds = time.monotonic() - started
    ok = res.returncode == 0 and (site / "sklearn" / "__init__.py").is_file()
    log = res.stdout[-20000:] + "\n--- stderr ---\n" + res.stderr
    return BuildResult(ok, round(seconds, 1), log, res.leftovers)


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "image":
        raise SystemExit(__doc__)
    image(Path(sys.argv[2]), Path(sys.argv[3]))
