"""Decision 6: is the literal "from the same extraction that builds the grams" a necessary condition of a match?

A fresh SQLite store holds small files. For each pattern, vfs's own grep (the authority) is run, the extraction's
surviving literal segments per OR branch are read off code_grams' own fragment compiler and its branch dedupe, and the
server-side test decision 6 adds (`instr(content, :lit) > 0`, ORed over branches) is run on the same rows.
"""
from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import sys

from vfs import AsyncVirtualFileSystem, DatabaseStorage
from vfs.models import code_grams as cg

DB = sys.argv[1]
FILES = {
    "/a/lower.c": "void f(void) { p = kmalloc(8); }\n",
    "/a/upper.c": "#define KMALLOC 1\n",
    "/a/other.c": "hello world\n",
    "/a/nul.c": "x\x00 kmalloc(1)\n",
}
CASES = [
    ("[Kk]malloc", dict(case_mode="sensitive")),
    ("Kmalloc|kmalloc", dict(case_mode="sensitive")),
    ("Kmalloc|kmalloc", dict(case_mode="smart")),
    ("(?i)kmalloc", dict(case_mode="sensitive")),
    ("(?i:KMALLOC)", dict(case_mode="sensitive")),
    ("kmalloc", dict(case_mode="sensitive", invert_match=True)),
    ("kmalloc", dict(case_mode="sensitive")),
]


def extraction_literals(pattern: str) -> list[str]:
    """Each surviving OR branch's longest raw segment, after the fold dedupe _fragment_query applies."""
    fragments = cg._compile_seq(list(cg.sre_parse.parse(pattern).data))
    out, seen = [], set()
    for fragment in fragments:
        grams = set()
        for segment in fragment:
            if segment:
                grams |= cg._grams_from_run(cg._encode_run(segment))
        key = frozenset(grams)
        if key in seen:
            continue
        seen.add(key)
        out.append(max(fragment, key=len))
    return out


async def main() -> None:
    if os.path.exists(DB):
        os.remove(DB)
    fs = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}"))
    try:
        for path, body in FILES.items():
            r = await fs.write(path=path, content=body, parents=True)
            if not r.success:
                print("write refused", path, [e.message[:80] for e in r.errors])
        rb = await fs.storage_for("/").rebuild() if hasattr(fs, "storage_for") else None
        _ = rb
        raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        for pattern, kw in CASES:
            r = await fs.grep(pattern, paths=("/a",), output_mode="files", **kw)
            got = sorted(str(o.path) for o in r.observations)
            lits = extraction_literals(pattern)
            where = " OR ".join("instr(c.content, ?) > 0" for _ in lits)
            kept = sorted(
                p for (p,) in raw.execute(
                    "SELECT e.path FROM vfs_entries e JOIN vfs_content c ON c.entry_id = e.entry_id "
                    f"WHERE e.kind = 'file' AND ({where})", lits
                )
            )
            lost = sorted(set(got) - set(kept))
            print(f"{pattern!r} {kw}")
            print(f"   grep returns {got}  errors={[e.message[:50] for e in r.errors]}")
            print(f"   extraction literals {lits}; instr keeps {kept}")
            print(f"   ROWS LOST BY THE LITERAL TEST: {lost}")
        print("python re check: (?i)kmalloc vs KMALLOC ->", bool(re.search("(?i)kmalloc", "KMALLOC")))
        print("sqlite instr past a NUL:", raw.execute("select instr(?, 'kmalloc')", ("x\x00 kmalloc",)).fetchone())
    finally:
        await fs.close()


asyncio.run(main())
