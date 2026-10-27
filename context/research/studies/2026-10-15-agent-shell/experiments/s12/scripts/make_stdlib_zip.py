"""Build python314.zip: the pure-Python stdlib (and any extra package trees) as sources or sourceless .pyc.

STORED, not deflated: the WASI interpreter has no zlib, and zipimport needs zlib to inflate (the first floor run died on
exactly that). --deflate exists only to measure the size difference.

    .venv-build/bin/python scripts/make_stdlib_zip.py --lib <Python-3.14.8/Lib> [--extra <dir-holding-numpy>] [--pyc <build-python>] out.zip
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SKIP_DIRS = {"__pycache__", "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3", "pydoc_data", "venv", "site-packages", "_pyrepl"}
SKIP_SUFFIXES = {".pyi", ".pxd", ".pyx", ".h", ".c", ".cpp", ".typed"}


def walk(root: Path, prefix: str, skip_tests: bool, skip_extra: frozenset = frozenset()):
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        dirnames[:] = sorted(d for d in dirnames if (d not in SKIP_DIRS or (not skip_tests and d in {"test", "tests"})) and not (rel == Path(".") and d in skip_extra))
        for f in sorted(filenames):
            p = Path(dirpath) / f
            if p.suffix in SKIP_SUFFIXES or f.endswith(".so"):
                continue
            yield p, str(Path(prefix) / rel / f) if prefix else str(rel / f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", required=True)
    ap.add_argument("--extra", action="append", default=[], help="directory whose children (e.g. numpy/) go to the zip root")
    ap.add_argument("--pyc", default=None, help="compile .py to sourceless .pyc with this interpreter (must be 3.14)")
    ap.add_argument("--keep-tests", action="store_true")
    ap.add_argument("--deflate", action="store_true")
    ap.add_argument("--skip", action="append", default=[], help="top-level stdlib package to leave out (e.g. ctypes, replaced by a stand-in)")
    ap.add_argument("out")
    a = ap.parse_args()
    entries = list(walk(Path(a.lib), "", not a.keep_tests, frozenset(a.skip)))
    for extra in a.extra:
        entries += list(walk(Path(extra), "", not a.keep_tests))
    n_py = n_other = 0
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED if a.deflate else zipfile.ZIP_STORED, compresslevel=9) as z:
        if a.pyc:
            with tempfile.TemporaryDirectory() as td:
                for src, name in entries:
                    if src.suffix == ".py":
                        dest = Path(td) / (name + "c")
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        subprocess.run([a.pyc, "-c", f"import py_compile; py_compile.compile({str(src)!r}, cfile={str(dest)!r}, dfile={name!r}, doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)"], check=True)
                        z.write(dest, name + "c"); n_py += 1
                    else:
                        z.write(src, name); n_other += 1
        else:
            for src, name in entries:
                z.write(src, name)
                n_py += src.suffix == ".py"; n_other += src.suffix != ".py"
    print(f"{a.out}: {n_py} python files ({'pyc' if a.pyc else 'py'}), {n_other} other files, {Path(a.out).stat().st_size} bytes, {'deflated' if a.deflate else 'stored'}")


if __name__ == "__main__":
    main()
