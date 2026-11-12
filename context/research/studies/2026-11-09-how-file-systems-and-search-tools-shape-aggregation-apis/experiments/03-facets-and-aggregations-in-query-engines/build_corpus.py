"""Build a SQLite table of the vfs src/ tree: path, ext, size, lines."""
import os
import sqlite3
import sys

root = sys.argv[1]
db = sys.argv[2]
if os.path.exists(db):
    os.remove(db)
conn = sqlite3.connect(db)
conn.execute("create table files (path text primary key, dir text, ext text, size integer, lines integer)")
rows = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d != "__pycache__"]
    for name in filenames:
        full = os.path.join(dirpath, name)
        rel = os.path.relpath(full, root)
        ext = os.path.splitext(name)[1].lstrip(".") or None
        size = os.path.getsize(full)
        try:
            with open(full, "rb") as fh:
                lines = sum(1 for _ in fh)
        except OSError:
            lines = None
        rows.append((rel, os.path.dirname(rel) or ".", ext, size, lines))
conn.executemany("insert into files values (?,?,?,?,?)", rows)
conn.commit()
print(len(rows), "rows")
