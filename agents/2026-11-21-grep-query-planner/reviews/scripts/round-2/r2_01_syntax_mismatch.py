"""Decision 7, and every plan's parity: Python's parser and the matcher's regex crate read some admitted patterns
differently.

For each pattern: whether the language gate admits it, what the Rust matcher (the authority) does on a small body,
what e5's prototype extraction requires, and what the gram planner (also sre-based) requires. Then a property test of
e5 against the Rust matcher, with a generator that emits regex-crate syntax the gate admits. Then the same patterns on
the sandbox: the database grep (index side) against in hand over the same scope.
"""
from __future__ import annotations

import asyncio
import importlib.util
import random
import sqlite3
import sys

from vfs import AsyncVirtualFileSystem, DatabaseStorage
from vfs.models import Observation
from vfs.models.code_grams import build_code_gram_query
from vfs.pattern_matching import PatternError, compile_verifier

spec = importlib.util.spec_from_file_location("e5", sys.argv[2])
e5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e5)
DB = sys.argv[1]

CASES = [("\\<i_count", "x = inode->i_count;"), ("\\b{start}i_count", "x = inode->i_count;"),
         ("i_count\\>", "x = inode->i_count;"), ("[[:alpha:]]_count", "x = inode->i_count;"),
         ("x[a[bc]]y", "xby"), ("[a-c&&b]x", "bx"), ("\\<(?i)KMALLOC", "kmalloc(1)")]  # fmt: skip


def rust_hits(pattern: str, body: str, insensitive: bool = False) -> int:
    v = compile_verifier(pattern, fixed_strings=False, word_regexp=False,
                         case_mode="insensitive" if insensitive else "sensitive")
    return v.count_lines([body], cap=None, invert=False, budget=None)[0][0]


def main_static() -> None:
    for pattern, body in CASES:
        try:
            hits = rust_hits(pattern, body)
            gate = "admitted"
        except PatternError as exc:
            print(f"{pattern!r}: refused ({exc})")
            continue
        try:
            lits = e5.required_literals(pattern, insensitive=False)
        except Exception as exc:  # noqa: BLE001
            lits = f"error {exc}"
        plan = build_code_gram_query(pattern)
        lost = hits and lits and not any(lit in body for lit in lits)
        print(f"{pattern!r:24} gate={gate} rust hits on {body!r}: {hits}; e5 literals={lits}; "
              f"gram plan any={plan.is_any()}; e5 RULES OUT A MATCH: {bool(lost)}")


ATOMS = ["a", "b", "<", ">", "\\<", "\\>", "\\b{start}", "\\b{end}", "[[:alpha:]]", "[a[b]]", "[a-c&&b]",
         "[ab--b]", "x", "\\b"]  # fmt: skip


def property_test(cases: int) -> None:
    rng = random.Random(7)
    checked = violations = admitted = 0
    shown = 0
    for _ in range(cases):
        pattern = "".join(rng.choice(ATOMS) for _ in range(rng.randint(2, 5)))
        try:
            v = compile_verifier(pattern, fixed_strings=False, word_regexp=False, case_mode="sensitive")
            lits = e5.required_literals(pattern, insensitive=False)
        except (PatternError, Exception):  # noqa: BLE001
            continue
        admitted += 1
        if lits is None:
            continue
        bodies = ["".join(rng.choice("ab x<>[]:-&{}startend") for _ in range(rng.randint(0, 16))) for _ in range(30)]
        counts = v.count_lines(bodies, cap=None, invert=False, budget=None)[0]
        for body, count in zip(bodies, counts, strict=True):
            checked += 1
            if count and not any(lit in body for lit in lits):
                violations += 1
                if shown < 6:
                    shown += 1
                    print(f"  VIOLATION pattern={pattern!r} literals={sorted(lits)} body={body!r}")
    print(f"property test vs the Rust matcher: {admitted} admitted patterns, {checked} bodies, {violations} violations")


async def sandbox() -> None:
    fs = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}"))
    raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        root = sys.argv[3] if len(sys.argv) > 3 else "/fs/ext4"
        paths = [p for (p,) in raw.execute("select path from vfs_entries where kind='file' and path > ? and path < ?",
                                           (root + "/", root + "0"))]
        for pattern in ("i_count", "\\<i_count", "\\b{start}i_count", "i_count\\>", "[[:alpha:]]_count",
                        "\\<kmalloc"):
            db = await fs.grep(pattern, paths=(root,), output_mode="files")
            hand = await fs.grep(pattern, observations=[Observation(path=p, kind="file") for p in paths],
                                 output_mode="files")
            a, b = {str(o.path) for o in db.observations}, {str(o.path) for o in hand.observations}
            print(f"{root} ({len(paths)} files) {pattern!r:22} database grep: {len(a):3} rows; in hand: {len(b):3} rows; "
                  f"rows the database grep misses: {len(b - a)} {[e.kind for e in db.errors]}")
    finally:
        raw.close()
        await fs.close()


if len(sys.argv) <= 3:
    main_static()
    property_test(20_000)
asyncio.run(sandbox())
