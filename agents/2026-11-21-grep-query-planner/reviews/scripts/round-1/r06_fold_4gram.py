"""Decision 8 / R5: the 4-gram column was simulated case-sensitively; the stored index is one folded stream.

For each pattern the corpus-wide ladder candidates are recorded (the kernel wrapped, as e3 does), their bodies read
read-only, and four filters counted: R5's raw 4-gram rule (e3's `quadgrams` over raw text), the same rule over the
folded stream a folded 4-gram index would hold, the raw literal (R5's column), and the folded literal (the ceiling
of any folded n-gram index).
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys

import vfs.storage.backends.database.grep as g
from vfs import AsyncVirtualFileSystem, DatabaseStorage
from vfs.models.code_grams import fold_content

DB = sys.argv[1]
PATTERNS = [("TODO", ["TODO"]), ("struct page \\*", ["struct page *"]), ("^struct inode \\{", ["struct inode {"]),
            ("alloc_page", ["alloc_page"]), ("pr_debug", ["pr_debug"]), ("copy_from_user", ["copy_from_user"]),
            ("dentry_lru_isolate", ["dentry_lru_isolate"]), ("EXPORT_SYMBOL_GPL", ["EXPORT_SYMBOL_GPL"]),
            ("MODULE_LICENSE", ["MODULE_LICENSE"])]  # fmt: skip
rec: dict = {}
real = g.extension


class Rec:
    def __init__(self, r):
        self._r = r

    def __getattr__(self, n):
        return getattr(self._r, n)

    def candidate_ids(self, fed, allow, cap):
        ids, count = self._r.candidate_ids(fed, allow, cap)
        rec["ids"], rec["U"] = list(ids), count
        return ids, count


g.extension = lambda: Rec(real())


def quad(text: str) -> set[str]:
    return {text[i : i + 4] for i in range(len(text) - 3)} or {text}


async def main() -> None:
    fs = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}"))
    raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    tot = [0] * 5
    try:
        print("| pattern | candidates fetched | raw 4-gram (R5) | folded 4-gram | raw literal | folded literal |")
        for pattern, lits in PATTERNS:
            rec.clear()
            await fs.grep(pattern, output_mode="files")
            ids = rec["ids"]
            r4 = f4 = rl = fl = 0
            for start in range(0, len(ids), 30000):
                chunk = ids[start : start + 30000]
                q = ("SELECT c.content FROM vfs_content c JOIN vfs_entries e ON e.entry_id = c.entry_id "
                     f"WHERE e.id IN ({','.join('?' * len(chunk))})")
                for (body,) in raw.execute(q, chunk):
                    folded = fold_content(body)
                    r4 += any(all(x in body for x in quad(lit)) for lit in lits)
                    f4 += any(all(x in folded for x in quad(fold_content(lit))) for lit in lits)
                    rl += any(lit in body for lit in lits)
                    fl += any(fold_content(lit) in folded for lit in lits)
            for i, v in enumerate((len(ids), r4, f4, rl, fl)):
                tot[i] += v
            print(f"| `{pattern}` | {len(ids)} | {r4} | {f4} | {rl} | {fl} |", flush=True)
        print(f"| total | {tot[0]} | {tot[1]} | {tot[2]} | {tot[3]} | {tot[4]} |")
        print(f"cut vs candidates: raw 4-gram {1 - tot[1] / tot[0]:.1%}, folded 4-gram {1 - tot[2] / tot[0]:.1%}")
    finally:
        raw.close()
        await fs.close()


asyncio.run(main())
