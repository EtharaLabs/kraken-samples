"""Run submission code as a restricted uid in a fresh process, then check for leftovers.

Every run gets a new empty HOME and TMPDIR. After the run, every process of the
restricted uid is killed, the scratch directory is removed, and any file the uid
still owns anywhere else on the image (or in /dev/shm) is a persistence attempt.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SCRATCH_ROOT = Path("/opt/kraken/scratch")
SCAN_ROOTS = ("/", "/dev/shm")
SKIP = ("/proc", "/sys", "/dev/pts", str(SCRATCH_ROOT))


@dataclass(frozen=True, slots=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    leftovers: tuple[str, ...] = field(default=())
    collected: dict[str, str] = field(default_factory=dict)

    def json_line(self) -> dict | None:
        for line in reversed(self.stdout.strip().splitlines()):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
        return None


def _kill_uid(uid: int) -> None:
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text()
        except OSError:
            continue
        for line in status.splitlines():
            if line.startswith("Uid:") and int(line.split()[1]) == uid:
                try:
                    os.kill(int(entry.name), signal.SIGKILL)
                except OSError:
                    pass


class PersistenceGuard:
    """Snapshot of every place the restricted uid can write, taken once before any run.

    A file can only appear in a directory the uid may write to, and an existing
    file can only change if the uid may write to it, so these two sets bound
    every cross-process channel through the filesystem.
    """

    def __init__(self, uid: int) -> None:
        self.uid = uid
        self.dirs: list[str] = []
        self.files: dict[str, tuple[int, int]] = {}
        for root in SCAN_ROOTS:
            dev = os.stat(root).st_dev
            for dirpath, dirnames, filenames in os.walk(root):
                if dirpath != "/" and dirpath.startswith(SKIP):
                    dirnames[:] = []
                    continue
                dirnames[:] = [d for d in dirnames if self._same_dev(os.path.join(dirpath, d), dev)]
                if self._writable(dirpath):
                    self.dirs.append(dirpath)
                for name in filenames:
                    path = os.path.join(dirpath, name)
                    if self._writable(path):
                        st = os.lstat(path)
                        self.files[path] = (st.st_size, st.st_mtime_ns)

    @staticmethod
    def _same_dev(path: str, dev: int) -> bool:
        try:
            return os.lstat(path).st_dev == dev and not path.startswith(SKIP)
        except OSError:
            return False

    def _writable(self, path: str) -> bool:
        try:
            st = os.lstat(path)
        except OSError:
            return False
        if st.st_uid == self.uid:
            return bool(st.st_mode & 0o200)
        if st.st_gid == self.uid:
            return bool(st.st_mode & 0o020)
        return bool(st.st_mode & 0o002)

    def leftovers(self) -> list[str]:
        found: list[str] = []
        for d in self.dirs:
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for name in names:
                path = os.path.join(d, name)
                try:
                    st = os.lstat(path)
                except OSError:
                    continue
                if st.st_uid == self.uid:
                    found.append(path)
        for path, before in self.files.items():
            try:
                st = os.lstat(path)
            except OSError:
                found.append(path)
                continue
            if (st.st_size, st.st_mtime_ns) != before:
                found.append(path)
        return sorted(set(found))


def _purge(paths: list[str]) -> None:
    for path in paths:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.unlink(path)
            except OSError:
                pass


def run_restricted(
    argv: list[str],
    *,
    guard: PersistenceGuard,
    pythonpath: str,
    cwd: str,
    timeout: float,
    collect: tuple[str, ...] = (),
) -> RunResult:
    uid = guard.uid
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(dir=SCRATCH_ROOT))
    home, tmp = scratch / "home", scratch / "tmp"
    for d in (scratch, home, tmp):
        d.mkdir(exist_ok=True)
        os.chown(d, uid, uid)
    env = {
        "PATH": "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "PYTHONPATH": pythonpath,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "JAX_PLATFORMS": "cpu",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "XLA_FLAGS": "--xla_cpu_multi_thread_eigen=false",
        "LANG": "C.UTF-8",
    }
    argv = [a.replace("{scratch}", str(scratch)) for a in argv]
    timed_out = False
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            user=uid,
            group=uid,
            extra_groups=[],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        returncode, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -9
        stdout = (
            exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        )
        stderr = (
            exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        )
    _kill_uid(uid)
    collected = {}
    for rel in collect:
        path = scratch / rel
        if path.is_file() and not path.is_symlink():
            collected[rel] = path.read_text(errors="replace")
    shutil.rmtree(scratch, ignore_errors=True)
    leftovers = guard.leftovers()
    _purge([p for p in leftovers if p not in guard.files])
    return RunResult(returncode, stdout, stderr[-4000:], timed_out, tuple(leftovers), collected)
