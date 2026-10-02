"""How the shape of a permission filter sets its cost as grants grow.

A standalone SQLite experiment on vfs's own table shapes (entries, lex_docs,
chunks), no vfs import. It times the two statements that dominate a partial
caller's glean — the visible-corpus count and the brute-force vector leg —
under four filter shapes:

- ``like``: today's arms, ``path = :p OR path LIKE :p/%`` per grant, OR'd.
- ``range``: the same arms as byte ranges, ``path = :p OR (path > :p/ AND path < :p0)``.
- ``join``: the grants as rows of a temp table of ``[lo, hi)`` byte ranges,
  joined to the entries — one statement shape whatever the grant count.
- ``ordinal``: an epoch table numbering chunks in path order with a running
  length sum; a caller's ``N`` and ``sum(dl)`` are two index seeks per range.

    uv run --no-sync python filter_shapes.py --folders 100 --files 50

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import statistics
import struct
import time

import sqlite_vec

DIM = 64
TOPS = 10
REPEATS = 5


def build(folders: int, files: int, seed: int = 30) -> sqlite3.Connection:
    rng = random.Random(seed)
    db = sqlite3.connect(":memory:")
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.execute("PRAGMA case_sensitive_like = ON")
    db.executescript(
        """
        CREATE TABLE entry (id INTEGER PRIMARY KEY, entry_id TEXT NOT NULL UNIQUE, path TEXT NOT NULL UNIQUE,
                            owner_id TEXT, kind TEXT NOT NULL, deleted_at TEXT);
        CREATE INDEX ix_owner ON entry(owner_id);
        CREATE TABLE lex_docs (epoch INTEGER, chunk_id INTEGER, entry_id TEXT NOT NULL, dl INTEGER NOT NULL,
                               PRIMARY KEY (epoch, chunk_id));
        CREATE INDEX ix_docs_entry ON lex_docs(epoch, entry_id);
        CREATE TABLE chunks (id INTEGER PRIMARY KEY, entry_id TEXT NOT NULL, embedding BLOB);
        CREATE INDEX ix_chunks_entry ON chunks(entry_id);
        CREATE TABLE lex_order (epoch INTEGER, path TEXT, chunk_id INTEGER, ord INTEGER, cum_dl INTEGER,
                                PRIMARY KEY (epoch, path, chunk_id));
        """
    )
    paths = [f"/t{t:02d}/f{f:03d}/doc{n:03d}.md" for t in range(TOPS) for f in range(folders) for n in range(files)]
    order = list(range(len(paths)))
    rng.shuffle(order)  # write order is not path order, as in a live mount
    dirs = [f"/t{t:02d}" for t in range(TOPS)] + [f"/t{t:02d}/f{f:03d}" for t in range(TOPS) for f in range(folders)]
    rows = [(f"d{i}", p, "owner", "directory") for i, p in enumerate(dirs)]
    rows += [(f"e{i}", paths[i], "owner", "file") for i in order]
    db.executemany("INSERT INTO entry(entry_id, path, owner_id, kind) VALUES (?,?,?,?)", rows)
    docs, chunks = [], []
    for chunk_id, i in enumerate(order, start=1):
        docs.append((1, chunk_id, f"e{i}", rng.randint(80, 220)))
        vec = [rng.gauss(0, 1) for _ in range(DIM)]
        chunks.append((chunk_id, f"e{i}", struct.pack(f"{DIM}f", *vec)))
    db.executemany("INSERT INTO lex_docs VALUES (?,?,?,?)", docs)
    db.executemany("INSERT INTO chunks VALUES (?,?,?)", chunks)
    # the epoch build scans in path order and writes ordinals with a running length sum
    ordered = db.execute(
        "SELECT e.path, d.chunk_id, d.dl FROM lex_docs d JOIN entry e ON e.entry_id = d.entry_id "
        "WHERE d.epoch = 1 ORDER BY e.path, d.chunk_id"
    ).fetchall()
    cum, out = 0, []
    for ord_, (path, chunk_id, dl) in enumerate(ordered):
        out.append((1, path, chunk_id, ord_, cum))
        cum += dl
    out.append((1, "\U0010ffff", 0, len(ordered), cum))  # sentinel past every path
    db.executemany("INSERT INTO lex_order VALUES (?,?,?,?,?)", out)
    db.execute("ANALYZE")
    return db


def callers(folders: int, files: int) -> dict[str, list[str]]:
    every_folder = [f"/t{t:02d}/f{f:03d}" for t in range(TOPS) for f in range(folders)]
    every_file = [
        f"/t{t:02d}/f{f:03d}/doc{n:03d}.md" for t in range(TOPS) for f in range(folders) for n in range(files)
    ]
    return {
        "1 grant (10%)": ["/t03"],
        "5 grants (0.5%)": every_folder[3:5000:200][:5],
        "100 grants (10%)": every_folder[::10],
        "500 grants (50%)": every_folder[::2],
        "5000 file grants (10%)": every_file[::10],
    }


def ranges(prefixes: list[str]) -> list[tuple[str, str]]:
    """Each prefix as two half-open byte ranges: the row itself and everything beneath it.

    ``[p, p + U+0001)`` is exactly ``{p}``: vfs paths never hold a control character.
    """
    out = []
    for p in sorted(set(prefixes)):
        out.append((p, p + "\x01"))
        out.append((p + "/", p + "0"))
    return out


def like_arms(prefixes: list[str]) -> tuple[str, list[str]]:
    sql = " OR ".join("(e.path = ? OR e.path LIKE ? ESCAPE '\\')" for _ in prefixes)
    binds = [b for p in prefixes for b in (p, p + "/%")]
    return f"({sql})", binds


def range_arms(prefixes: list[str]) -> tuple[str, list[str]]:
    sql = " OR ".join("(e.path = ? OR (e.path > ? AND e.path < ?))" for _ in prefixes)
    binds = [b for p in prefixes for b in (p, p + "/", p + "0")]
    return f"({sql})", binds


ARMS_PER_STATEMENT = 400


def corpus_by_arms(db: sqlite3.Connection, prefixes: list[str], shape) -> tuple[int, int]:
    if len(prefixes) <= ARMS_PER_STATEMENT:
        where, binds = shape(prefixes)
        return db.execute(
            "SELECT count(*), coalesce(sum(d.dl),0) FROM lex_docs d JOIN entry e ON e.entry_id = d.entry_id "
            f"WHERE d.epoch = 1 AND {where}",
            binds,
        ).fetchone()
    seen: dict[int, int] = {}
    for i in range(0, len(prefixes), ARMS_PER_STATEMENT):
        where, binds = shape(prefixes[i : i + ARMS_PER_STATEMENT])
        for chunk_id, dl in db.execute(
            "SELECT d.chunk_id, d.dl FROM lex_docs d JOIN entry e ON e.entry_id = d.entry_id "
            f"WHERE d.epoch = 1 AND {where}",
            binds,
        ):
            seen[chunk_id] = dl
    return len(seen), sum(seen.values())


def load_ranges(db: sqlite3.Connection, prefixes: list[str]) -> None:
    db.execute("DROP TABLE IF EXISTS temp.vis")
    db.execute("CREATE TEMP TABLE vis (lo TEXT NOT NULL, hi TEXT NOT NULL)")
    db.executemany("INSERT INTO temp.vis VALUES (?,?)", ranges(prefixes))


def corpus_by_join(db: sqlite3.Connection, prefixes: list[str]) -> tuple[int, int]:
    load_ranges(db, prefixes)
    return db.execute(
        "SELECT count(*), coalesce(sum(d.dl),0) FROM temp.vis r "
        "JOIN entry e ON e.path >= r.lo AND e.path < r.hi "
        "JOIN lex_docs d ON d.epoch = 1 AND d.entry_id = e.entry_id"
    ).fetchone()


def corpus_by_ordinal(db: sqlite3.Connection, prefixes: list[str]) -> tuple[int, int]:
    load_ranges(db, prefixes)
    seek = "(SELECT {col} FROM lex_order o WHERE o.epoch = 1 AND o.path >= r.{end} ORDER BY o.path, o.chunk_id LIMIT 1)"
    return db.execute(
        "SELECT sum(" + seek.format(col="ord", end="hi") + " - " + seek.format(col="ord", end="lo") + "), "
        "sum(" + seek.format(col="cum_dl", end="hi") + " - " + seek.format(col="cum_dl", end="lo") + ") "
        "FROM temp.vis r"
    ).fetchone()


QUERY = struct.pack(f"{DIM}f", *[random.Random(7).gauss(0, 1) for _ in range(DIM)])


def vector_by_arms(db: sqlite3.Connection, prefixes: list[str], shape) -> list[int]:
    found = []
    for i in range(0, len(prefixes), ARMS_PER_STATEMENT):
        where, binds = shape(prefixes[i : i + ARMS_PER_STATEMENT])
        found += db.execute(
            "SELECT c.id, vec_distance_cosine(c.embedding, ?) AS dist FROM chunks c "
            f"JOIN entry e ON e.entry_id = c.entry_id WHERE e.deleted_at IS NULL AND {where} "
            "ORDER BY dist, c.id LIMIT 10",
            [QUERY, *binds],
        ).fetchall()
    return [cid for cid, _ in sorted(found, key=lambda r: (r[1], r[0]))[:10]]


def vector_by_join(db: sqlite3.Connection, prefixes: list[str]) -> list[int]:
    load_ranges(db, prefixes)
    rows = db.execute(
        "SELECT c.id, vec_distance_cosine(c.embedding, ?) AS dist FROM temp.vis r "
        "JOIN entry e ON e.path >= r.lo AND e.path < r.hi "
        "JOIN chunks c ON c.entry_id = e.entry_id WHERE e.deleted_at IS NULL ORDER BY dist, c.id LIMIT 10",
        [QUERY],
    ).fetchall()
    return [cid for cid, _ in rows]


def vector_whole(db: sqlite3.Connection, _prefixes: list[str]) -> list[int]:
    rows = db.execute(
        "SELECT c.id, vec_distance_cosine(c.embedding, ?) AS dist FROM chunks c "
        "JOIN entry e ON e.entry_id = c.entry_id WHERE e.deleted_at IS NULL ORDER BY dist, c.id LIMIT 10",
        [QUERY],
    ).fetchall()
    return [cid for cid, _ in rows]


def timed(fn, *args) -> tuple[float, object]:
    fn(*args)  # warm
    samples, out = [], None
    for _ in range(REPEATS):
        start = time.perf_counter()
        out = fn(*args)
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples), out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folders", type=int, default=100)
    parser.add_argument("--files", type=int, default=50)
    args = parser.parse_args()
    db = build(args.folders, args.files)
    n = db.execute("SELECT count(*) FROM lex_docs").fetchone()[0]
    print(f"## sqlite {sqlite3.sqlite_version} — {n:,} chunks, dim {DIM}, median of {REPEATS} warm runs\n")
    whole, _ = timed(vector_whole, db, [])
    print(f"whole-mount vector leg (no filter): {whole:.1f} ms\n")
    print(
        "| caller | corpus: like | corpus: range | corpus: join | corpus: ordinal | vector: like | vector: range | vector: join |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for label, prefixes in callers(args.folders, args.files).items():
        c_like, a = timed(corpus_by_arms, db, prefixes, like_arms)
        c_range, b = timed(corpus_by_arms, db, prefixes, range_arms)
        c_join, c = timed(corpus_by_join, db, prefixes)
        c_ord, d = timed(corpus_by_ordinal, db, prefixes)
        assert tuple(a) == tuple(b) == tuple(c) == tuple(d), (label, a, b, c, d)
        v_like, x = timed(vector_by_arms, db, prefixes, like_arms)
        v_range, y = timed(vector_by_arms, db, prefixes, range_arms)
        v_join, z = timed(vector_by_join, db, prefixes)
        assert x == y == z, (label, x, y, z)
        print(
            f"| {label} ({a[0]:,} visible) | {c_like:.1f} | {c_range:.1f} | {c_join:.1f} | {c_ord:.2f} "
            f"| {v_like:.1f} | {v_range:.1f} | {v_join:.1f} |"
        )
    print("\nPlans (100 grants):")
    prefixes = callers(args.folders, args.files)["100 grants (10%)"]
    for name, shape in (("like", like_arms), ("range", range_arms)):
        where, binds = shape(prefixes)
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT count(*) FROM lex_docs d JOIN entry e ON e.entry_id = d.entry_id "
            f"WHERE d.epoch = 1 AND {where}",
            binds,
        ).fetchall()
        print(f"- {name}: " + "; ".join(row[3] for row in plan[:4]))
    load_ranges(db, prefixes)
    plan = db.execute(
        "EXPLAIN QUERY PLAN SELECT count(*) FROM temp.vis r JOIN entry e ON e.path >= r.lo AND e.path < r.hi "
        "JOIN lex_docs d ON d.epoch = 1 AND d.entry_id = e.entry_id"
    ).fetchall()
    print("- join: " + "; ".join(row[3] for row in plan))


if __name__ == "__main__":
    main()
