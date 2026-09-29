"""Exact errno for each operation under each mode of the ancestor directory P.

Same tree as ``repro.sh``: ``P/alpha/file.txt`` is the file the caller may
use, ``P/beta`` is a sibling. The script chmods its own directory, so the
owner bits decide. Run with ``uv run python errno_matrix.py``.
"""

from __future__ import annotations

import errno
import glob
import os
import platform
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODES = {
    0o700: "rwx (control)",
    0o100: "--x search only",
    0o400: "r-- list only",
    0o000: "--- nothing",
}


def outcome(op: Callable[[], object]) -> str:
    """Return ``ok: <value>`` or the errno name the call raised."""
    try:
        value = op()
    except OSError as exc:
        return errno.errorcode.get(exc.errno or 0, str(exc.errno))
    return f"ok: {value}"


def scandir_kinds(path: Path) -> list[str]:
    """Names plus the kind read from the directory entry, without stat."""
    with os.scandir(path) as entries:
        return sorted(f"{e.name}:{'dir' if e.is_dir(follow_symlinks=False) else 'file'}" for e in entries)


def main() -> None:
    base = Path(os.environ.get("SCRATCH", HERE / ".scratch"))
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="tv.", dir=base))
    p = root / "P"
    (p / "alpha").mkdir(parents=True)
    (p / "beta").mkdir()
    (p / "alpha" / "file.txt").write_text("alpha data")
    ops: dict[str, Callable[[], object]] = {
        "listdir(P)": lambda: sorted(os.listdir(p)),
        "scandir(P) kinds": lambda: scandir_kinds(p),
        "stat(P)": lambda: "mode=" + oct(p.stat().st_mode & 0o777),
        "stat(P/beta) exists": lambda: bool(os.stat(p / "beta")),
        "stat(P/nope) missing": lambda: bool(os.stat(p / "nope")),
        "open(P/alpha/file.txt)": lambda: (p / "alpha" / "file.txt").read_text(),
        "listdir(P/alpha)": lambda: os.listdir(p / "alpha"),
        "glob(P/*)": lambda: sorted(Path(g).name for g in glob.glob(str(p / "*"))),
        "makedirs(P/alpha/x/y)": lambda: os.makedirs(p / "alpha" / "x" / "y", exist_ok=True),
        "mkdir(P/gamma)": lambda: os.mkdir(p / "gamma"),
    }
    print(f"# {platform.system()} {platform.release()}, Python {sys.version.split()[0]}, uid={os.getuid()}")
    try:
        for mode, label in MODES.items():
            print(f"\n## P mode {oct(mode)} ({label})")
            os.chmod(p, mode)
            for name, op in ops.items():
                print(f"  {name:<26} {outcome(op)}")
            os.chmod(p, 0o700)
            shutil.rmtree(p / "alpha" / "x", ignore_errors=True)
            shutil.rmtree(p / "gamma", ignore_errors=True)
    finally:
        os.chmod(p, 0o700)
        shutil.rmtree(root)
        if not any(base.iterdir()):
            base.rmdir()


if __name__ == "__main__":
    main()
