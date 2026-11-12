"""Does the Bloom filter depend on the planner statistics vfs now gathers?

Copies the clean store, drops the ``sqlite_stat1`` rows (what ``ANALYZE``
wrote), reopens, and explains and times the shipped page statement
again; then runs ``ANALYZE`` on the copy and repeats, so the two plans
sit side by side. Usage: uv run python check_stat1_sqlite.py <base db> <scratch copy path> <out text>
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

from explain_sqlite import STATEMENTS, Native, plan_and_opcodes


def measure(native: Native, db_path: str, label: str, lines: list[str]) -> None:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    stat_rows = conn.execute("SELECT count(*) FROM sqlite_stat1").fetchone()[0]
    explained = plan_and_opcodes(conn, STATEMENTS["shipped_join"])
    conn.close()
    db = native.open(db_path)
    native.run_page(db, STATEMENTS["shipped_join"], 0, 256)
    runs = [native.run_page(db, STATEMENTS["shipped_join"], 231481, 256) for _ in range(3)]
    native.lib.sqlite3_close(db)
    median = sorted(runs, key=lambda r: r["wall_ms"])[1]
    lines.append(f"== {label}: sqlite_stat1 rows={stat_rows}")
    lines.extend(f"  {p}" for p in explained["plan"])
    lines.append(
        f"  page: rows={median['rows']} wall_ms={median['wall_ms']} vm_step={median['vm_step']} "
        f"filter_miss={median['filter_miss']} filter_hit={median['filter_hit']}"
    )


def main() -> None:
    base, copy, out_text = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(copy + suffix):
            os.remove(copy + suffix)
    shutil.copyfile(base, copy)
    native = Native()
    lines: list[str] = [f"python sqlite {sqlite3.sqlite_version}; ctypes {native.version}"]
    measure(native, copy, "as shipped (ANALYZE run by vfs)", lines)
    conn = sqlite3.connect(copy)
    conn.execute("DELETE FROM sqlite_stat1")
    conn.commit()
    conn.close()
    measure(native, copy, "sqlite_stat1 emptied", lines)
    conn = sqlite3.connect(copy)
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()
    measure(native, copy, "ANALYZE run again", lines)
    out_text.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
