"""Folder grants as predicates: OR'd LIKE arms against ranges, joins and id ranges.

A partial caller's rights compile to one arm per granted folder. Today
each arm is ``path = p OR path LIKE 'p/%'`` and the arms are OR'd, so a
statement that scans N chunk rows tests up to N x arms conditions. This
script times the same two counts under other encodings of the same
rights:

- ``entries``: ``SELECT count(*) FROM entries WHERE <rights>``
- ``corpus``: ``_visible_corpus``'s shape, ``count(*), sum(dl)`` over the
  lexical doc rows joined to their entry, filtered by the rights

Forms (every form must return the same numbers; the script asserts it):

- ``a_like``    OR of ``path = p OR path LIKE 'p/%'`` (today)
- ``b_range``   OR of ``path = p OR (path >= 'p/' AND path < 'p0')``
- ``*_semi``    (corpus) the arms inside ``d.entry_id IN (SELECT e.id ...)``
- ``c_values``  the prefixes as a VALUES list, joined by byte range
- ``c_temp``    the prefixes in a temp table, joined by byte range
- ``c_unnest``  (Postgres) the prefixes as two array binds, ``unnest``-ed
- ``d_or``      OR of ``pre BETWEEN lo AND hi`` on a preorder number
- ``d_values``  the preorder ranges as a VALUES list, joined
- ``e_or``      doc rows numbered in preorder: OR of ``doc_no BETWEEN``,
                no join to entries at all
- ``e_values``  the doc-number ranges as a VALUES list, joined
- ``g_sums``    the same count from an in-memory prefix-sum array (no SQL)

Also timed: the visible-chunk filter (``_visible_chunks``'s job) as a
chunked ``IN`` join plus an app-side admit, against a bisect over doc
ranges; and the maintenance cost of each encoding under a move.

    uv run --no-sync python bench.py --engine sqlite
    uv run --no-sync python bench.py --engine postgres --url postgresql://vfs:vfs@localhost:54320/vfs

Study code only: nothing here is imported by vfs, and it imports no vfs code.
"""

from __future__ import annotations

import argparse
import asyncio
import bisect
import os
import random
import sqlite3
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import asyncpg

HERE = os.path.dirname(os.path.abspath(__file__))
EPOCH = 1
IN_CHUNK = 30_000
SEMI_GROUP = 200
SCORE = "((d.dl * 7919 + d.chunk_id * 104729) % 100003)"


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------


@dataclass
class Corpus:
    entries: list[tuple[int, str, int, int]]  # id, path, pre, pend
    docs: list[tuple[int, int, int, int]]  # chunk_id, entry_id, dl, doc_no
    folders: list[str]
    pre: dict[str, int] = field(default_factory=dict)
    pend: dict[str, int] = field(default_factory=dict)
    doc_pre: list[int] = field(default_factory=list)  # doc_no -> entry preorder
    cum_dl: list[int] = field(default_factory=list)  # prefix sums of dl by doc_no


def build_corpus(tops: int, folders: int, files: int, chunks: int, seed: int = 930) -> Corpus:
    rng = random.Random(seed)
    paths: list[str] = []
    folder_paths: list[str] = []
    for t in range(tops):
        top = f"/t{t:02d}"
        paths.append(top)
        for f in range(folders):
            folder = f"{top}/f{f:03d}"
            folder_paths.append(folder)
            paths.append(folder)
            if f % 10 == 0:
                # A sibling whose name extends the folder's: sorts between p and p/ bytewise.
                paths.append(f"{folder}.md")
            paths.extend(f"{folder}/doc{n:03d}.md" for n in range(files))
    # Preorder: segment-wise order, so a subtree is contiguous including its root.
    ordered = sorted(paths, key=lambda p: tuple(s.encode() for s in p.split("/")))
    pre = {p: i for i, p in enumerate(ordered)}
    pend: dict[str, int] = {}
    stack: list[str] = []
    for p in ordered:
        while stack and not p.startswith(stack[-1] + "/"):
            pend[stack.pop()] = pre[p] - 1
        stack.append(p)
    for p in stack:
        pend[p] = len(ordered) - 1
    ids = list(range(1, len(paths) + 1))
    rng.shuffle(ids)
    entry_id = dict(zip(paths, ids, strict=True))
    entries = [(entry_id[p], p, pre[p], pend[p]) for p in paths]
    files_only = [p for p in ordered if p.endswith(".md")]
    doc_keys = [(pre[p], k, p) for p in files_only for k in range(chunks)]
    chunk_ids = list(range(1, len(doc_keys) + 1))
    rng.shuffle(chunk_ids)
    docs = []
    doc_pre = []
    cum = [0]
    for doc_no, ((p_pre, _k, p), cid) in enumerate(zip(doc_keys, chunk_ids, strict=True)):
        dl = rng.randint(80, 240)
        docs.append((cid, entry_id[p], dl, doc_no))
        doc_pre.append(p_pre)
        cum.append(cum[-1] + dl)
    return Corpus(entries, docs, folder_paths, pre, pend, doc_pre, cum)


def prefix_sets(c: Corpus) -> dict[str, list[str]]:
    def spread(n: int) -> list[str]:
        step = max(1, len(c.folders) // n)
        return c.folders[::step][:n]

    return {
        "10 spread": spread(10),
        "100 spread": spread(100),
        "500 spread": spread(500),
        "100 adjacent": c.folders[:100],
    }


@dataclass
class Rights:
    prefixes: list[str]
    pre_ranges: list[tuple[int, int]]
    doc_ranges: list[tuple[int, int]]  # coalesced, sorted, disjoint


def compile_rights(c: Corpus, prefixes: list[str]) -> Rights:
    pre_ranges = sorted((c.pre[p], c.pend[p]) for p in prefixes)
    doc_ranges: list[tuple[int, int]] = []
    for lo, hi in pre_ranges:
        a = bisect.bisect_left(c.doc_pre, lo)
        b = bisect.bisect_right(c.doc_pre, hi) - 1
        if a > b:
            continue
        if doc_ranges and doc_ranges[-1][1] + 1 >= a:
            doc_ranges[-1] = (doc_ranges[-1][0], b)
        else:
            doc_ranges.append((a, b))
    return Rights(sorted(prefixes), pre_ranges, doc_ranges)


# ---------------------------------------------------------------------------
# SQL building
# ---------------------------------------------------------------------------


class Binds:
    def __init__(self, engine: str) -> None:
        self.engine = engine
        self.values: list[Any] = []

    def __call__(self, value: Any, cast: str = "") -> str:
        self.values.append(value)
        if self.engine == "sqlite":
            return "?"
        return f"${len(self.values)}{cast}"


def escape_like(p: str) -> str:
    return p.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def predicate(form: str, r: Rights, b: Binds, e: str = "e", d: str = "d") -> tuple[str, str]:
    """(extra FROM/JOIN text, WHERE text) for *form*."""
    txt = "::text" if b.engine == "postgres" else ""
    if form == "none":
        return "", "1=1"
    if form.endswith("_semi"):
        return predicate(form.removesuffix("_semi"), r, b, e, d)
    if form == "a_like":
        arms = [f"({e}.path = {b(p)} OR {e}.path LIKE {b(escape_like(p) + '/%')} ESCAPE '\\')" for p in r.prefixes]
        return "", "(" + " OR ".join(arms) + ")"
    if form == "b_range":
        arms = [f"({e}.path = {b(p)} OR ({e}.path >= {b(p + '/')} AND {e}.path < {b(p + '0')}))" for p in r.prefixes]
        return "", "(" + " OR ".join(arms) + ")"
    if form == "c_values":
        rows = ", ".join(f"({b(p, txt)}, {b(p + '0', txt)})" for p in r.prefixes)
        return f"WITH g(p, hi) AS (VALUES {rows})|g", _residual(e)
    if form == "c_temp":
        return "g_tmp AS g", _residual(e)
    if form == "c_unnest":
        lo = b(r.prefixes, "::text[]")
        hi = b([p + "0" for p in r.prefixes], "::text[]")
        return f"unnest({lo}, {hi}) AS g(p, hi)", _residual(e)
    if form == "d_or":
        arms = [f"{e}.pre BETWEEN {b(lo)} AND {b(hi)}" for lo, hi in r.pre_ranges]
        return "", "(" + " OR ".join(arms) + ")"
    if form == "d_values":
        cast = "::int" if b.engine == "postgres" else ""
        rows = ", ".join(f"({b(lo, cast)}, {b(hi, cast)})" for lo, hi in r.pre_ranges)
        return f"WITH g(lo, hi) AS (VALUES {rows})|g", f"{e}.pre BETWEEN g.lo AND g.hi"
    if form == "d_unnest":
        lo = b([x for x, _ in r.pre_ranges], "::int[]")
        hi = b([y for _, y in r.pre_ranges], "::int[]")
        return f"unnest({lo}, {hi}) AS g(lo, hi)", f"{e}.pre BETWEEN g.lo AND g.hi"
    if form == "e_or":
        arms = [f"{d}.doc_no BETWEEN {b(lo)} AND {b(hi)}" for lo, hi in r.doc_ranges]
        return "", "(" + " OR ".join(arms) + ")"
    if form == "e_values":
        cast = "::int" if b.engine == "postgres" else ""
        rows = ", ".join(f"({b(lo, cast)}, {b(hi, cast)})" for lo, hi in r.doc_ranges)
        return f"WITH g(lo, hi) AS (VALUES {rows})|g", f"{d}.doc_no BETWEEN g.lo AND g.hi"
    if form == "e_unnest":
        lo = b([x for x, _ in r.doc_ranges], "::int[]")
        hi = b([y for _, y in r.doc_ranges], "::int[]")
        return f"unnest({lo}, {hi}) AS g(lo, hi)", f"{d}.doc_no BETWEEN g.lo AND g.hi"
    raise ValueError(form)


def _residual(e: str) -> str:
    # One byte range [p, p0) per prefix; the residual drops siblings like 'p.md' that sort inside it.
    return f"{e}.path >= g.p AND {e}.path < g.hi AND ({e}.path = g.p OR substr({e}.path, length(g.p) + 1, 1) = '/')"


def query(kind: str, form: str, r: Rights, engine: str, t: str) -> tuple[str, list[Any]]:
    b = Binds(engine)
    frm, where = predicate(form, r, b)
    cte = ""
    if "|" in frm:
        cte, frm = frm.split("|")
        cte += " "
    if kind == "entries":
        if form.startswith("e_") or form.endswith("_semi"):
            raise ValueError("doc-range and semi-join forms only answer the corpus count")
        src = f"{frm} JOIN {t}_entries e ON {where}" if frm else f"{t}_entries e"
        tail = "" if frm else f" WHERE {where}"
        return f"{cte}SELECT count(*) FROM {src}{tail}", b.values
    head, order = "count(*), coalesce(sum(d.dl), 0)", ""
    if kind == "topk":
        # A per-row computed score ordered and limited: the vector leg's shape without the vector.
        head, order = "d.chunk_id", f" ORDER BY {SCORE}, d.chunk_id LIMIT 10"
    if form.endswith("_semi"):
        # Arms fan into groups of SEMI_GROUP (SQLite's 1,000-deep expression cap), UNION-ed inside the IN.
        b = Binds(engine)
        parts = []
        for start in range(0, len(r.prefixes), SEMI_GROUP):
            sub = Rights(r.prefixes[start : start + SEMI_GROUP], [], [])
            parts.append(f"SELECT e.id FROM {t}_entries e WHERE {predicate(form, sub, b)[1]}")
        inner = " UNION ".join(parts)
        return (f"SELECT {head} FROM {t}_docs d WHERE d.epoch = {EPOCH} AND d.entry_id IN ({inner}){order}"), b.values
    if form.startswith("e_"):
        src = f"{frm} JOIN {t}_docs2 d ON d.epoch = {EPOCH} AND {where}" if frm else f"{t}_docs2 d"
        tail = "" if frm else f" WHERE d.epoch = {EPOCH} AND {where}"
        return f"{cte}SELECT {head} FROM {src}{tail}{order}", b.values
    if frm:
        src = f"{frm} JOIN {t}_entries e ON {where} JOIN {t}_docs d ON d.epoch = {EPOCH} AND d.entry_id = e.id"
        tail = ""
    else:
        src = f"{t}_docs d JOIN {t}_entries e ON e.id = d.entry_id"
        tail = f" WHERE d.epoch = {EPOCH} AND {where}"
    return f"{cte}SELECT {head} FROM {src}{tail}{order}", b.values


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------


class SqliteDb:
    engine = "sqlite"

    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path, isolation_level=None)
        # vfs pins this on every SQLite connection; it is what lets a LIKE prefix use the path index.
        self.conn.execute("PRAGMA case_sensitive_like = ON")

    async def exec(self, sql: str, args: list[Any] | None = None) -> None:
        self.conn.execute(sql, args or [])

    async def many(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        self.conn.execute("BEGIN")
        self.conn.executemany(sql, rows)
        self.conn.execute("COMMIT")

    async def fetch(self, sql: str, args: list[Any]) -> list[tuple[Any, ...]]:
        return self.conn.execute(sql, args).fetchall()

    async def plan(self, sql: str, args: list[Any]) -> str:
        rows = self.conn.execute("EXPLAIN QUERY PLAN " + sql, args).fetchall()
        return "\n".join(f"{'  ' * _depth(rows, r)}{r[3]}" for r in rows)

    async def begin(self) -> None:
        self.conn.execute("BEGIN")

    async def rollback(self) -> None:
        self.conn.rollback()

    async def close(self) -> None:
        self.conn.close()


def _depth(rows: list[Any], row: Any) -> int:
    parents = {r[0]: r[1] for r in rows}
    depth, cur = 0, row[1]
    while cur in parents:
        depth, cur = depth + 1, parents[cur]
    return depth


class PgDb:
    engine = "postgres"

    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn
        self.tx: Any = None

    async def exec(self, sql: str, args: list[Any] | None = None) -> None:
        await self.conn.execute(sql, *(args or []))

    async def many(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        n = sql.count("?")
        await self.conn.executemany(_numbered(sql, n), rows)

    async def fetch(self, sql: str, args: list[Any]) -> list[tuple[Any, ...]]:
        return [tuple(r) for r in await self.conn.fetch(sql, *args)]

    async def plan(self, sql: str, args: list[Any]) -> str:
        rows = await self.conn.fetch("EXPLAIN (ANALYZE, BUFFERS) " + sql, *args)
        return "\n".join(r[0] for r in rows)

    async def begin(self) -> None:
        self.tx = self.conn.transaction()
        await self.tx.start()

    async def rollback(self) -> None:
        await self.tx.rollback()

    async def close(self) -> None:
        await self.conn.close()


def _numbered(sql: str, n: int) -> str:
    for i in range(1, n + 1):
        sql = sql.replace("?", f"${i}", 1)
    return sql


async def load(db: Any, c: Corpus, t: str) -> None:
    coll = ' COLLATE "C"' if db.engine == "postgres" else ""
    big = "bigint" if db.engine == "postgres" else "INTEGER"
    rowid = " WITHOUT ROWID" if db.engine == "sqlite" else ""
    await db.exec(
        f"CREATE TABLE {t}_entries (id {big} PRIMARY KEY, path text{coll} NOT NULL, owner_id text, "
        "pre integer NOT NULL, pend integer NOT NULL)"
    )
    await db.exec(
        f"CREATE TABLE {t}_docs (epoch integer, chunk_id {big}, entry_id {big} NOT NULL, "
        f"dl integer NOT NULL, PRIMARY KEY (epoch, chunk_id)){rowid}"
    )
    await db.exec(
        f"CREATE TABLE {t}_docs2 (epoch integer, doc_no integer, chunk_id {big} NOT NULL, "
        f"dl integer NOT NULL, PRIMARY KEY (epoch, doc_no)){rowid}"
    )
    rng = random.Random(7)
    await db.many(
        f"INSERT INTO {t}_entries VALUES (?, ?, ?, ?, ?)",
        [(i, p, f"u{rng.randrange(50)}", pr, pe) for i, p, pr, pe in c.entries],
    )
    await db.many(f"INSERT INTO {t}_docs VALUES (?, ?, ?, ?)", [(EPOCH, cid, eid, dl) for cid, eid, dl, _ in c.docs])
    await db.many(f"INSERT INTO {t}_docs2 VALUES (?, ?, ?, ?)", [(EPOCH, dn, cid, dl) for cid, _, dl, dn in c.docs])
    await db.exec(f"CREATE UNIQUE INDEX {t}_ix_path ON {t}_entries (path)")
    await db.exec(f"CREATE INDEX {t}_ix_pre ON {t}_entries (pre)")
    await db.exec(f"CREATE INDEX {t}_ix_owner ON {t}_entries (owner_id)")
    await db.exec(f"CREATE INDEX {t}_ix_docs_entry ON {t}_docs (epoch, entry_id)")
    if db.engine == "postgres":
        await db.exec(f"VACUUM ANALYZE {t}_entries")
        await db.exec(f"VACUUM ANALYZE {t}_docs")
        await db.exec(f"VACUUM ANALYZE {t}_docs2")
    else:
        await db.exec("ANALYZE")


async def fill_temp(db: Any, r: Rights) -> None:
    if db.engine == "sqlite":
        db.conn.execute("CREATE TEMP TABLE IF NOT EXISTS g_tmp (p text PRIMARY KEY, hi text NOT NULL)")
        db.conn.execute("DELETE FROM g_tmp")
        db.conn.executemany("INSERT INTO g_tmp VALUES (?, ?)", [(p, p + "0") for p in r.prefixes])
    else:
        await db.exec('CREATE TEMP TABLE IF NOT EXISTS g_tmp (p text COLLATE "C" PRIMARY KEY, hi text COLLATE "C")')
        await db.exec("TRUNCATE g_tmp")
        await db.conn.copy_records_to_table("g_tmp", records=[(p, p + "0") for p in r.prefixes])
        await db.exec("ANALYZE g_tmp")


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


async def timed(fn: Any, reps: int) -> tuple[float, Any]:
    out = await fn()
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter()
        out = await fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return statistics.median(samples), out


def forms_for(engine: str) -> list[str]:
    base = ["none", "a_like", "b_range", "c_values", "c_temp", "d_or", "d_values", "e_or", "e_values"]
    if engine == "postgres":
        base += ["c_unnest", "d_unnest", "e_unnest"]
    return base


def truth(c: Corpus, r: Rights) -> tuple[int, int, int]:
    def under(path: str) -> bool:
        i = bisect.bisect_right(r.prefixes, path) - 1
        while i >= 0:
            p = r.prefixes[i]
            if path == p or path.startswith(p + "/"):
                return True
            if not path.startswith(p):
                return False
            i -= 1
        return False

    admitted = {eid for eid, path, _, _ in c.entries if under(path)}
    docs = [dl for _, eid, dl, _ in c.docs if eid in admitted]
    return len(admitted), len(docs), sum(docs)


def top10(c: Corpus, r: Rights) -> list[int]:
    los = [lo for lo, _ in r.doc_ranges]
    his = [hi for _, hi in r.doc_ranges]

    def visible(dn: int) -> bool:
        i = bisect.bisect_right(los, dn) - 1
        return i >= 0 and dn <= his[i]

    rows = [((dl * 7919 + cid * 104729) % 100003, cid) for cid, _, dl, dn in c.docs if visible(dn)]
    return [cid for _, cid in sorted(rows)[:10]]


def g_sums(c: Corpus, r: Rights) -> tuple[int, int]:
    n = sum(hi - lo + 1 for lo, hi in r.doc_ranges)
    s = sum(c.cum_dl[hi + 1] - c.cum_dl[lo] for lo, hi in r.doc_ranges)
    return n, s


async def run(engine: str, url: str | None, tops: int, folders: int, files: int, chunks: int, reps: int) -> None:
    c = build_corpus(tops, folders, files, chunks)
    t = f"acl_{uuid4().hex[:8]}"
    tmpdir = tempfile.mkdtemp(prefix="acl-ranges-")
    db: Any = SqliteDb(f"{tmpdir}/db.sqlite") if engine == "sqlite" else PgDb(await asyncpg.connect(url))
    label = f"{engine}-{len(c.entries)}"
    out: list[str] = []
    plans: list[str] = []
    try:
        t0 = time.perf_counter()
        await load(db, c, t)
        version = sqlite3.sqlite_version if engine == "sqlite" else (await db.fetch("SELECT version()", []))[0][0]
        head = (
            f"## {engine} — {len(c.entries):,} entry rows, {len(c.docs):,} doc rows "
            f"({tops} tops x {folders} folders x {files} files x {chunks} chunks), load {time.perf_counter() - t0:.0f}s, "
            f"median of {reps} warm runs, ms\n\n{version}\n"
        )
        print(head, flush=True)
        out.append(head)
        sets = prefix_sets(c)
        forms = forms_for(engine)
        for kind in ("entries", "corpus", "topk"):
            kforms = [f for f in forms if not (kind == "entries" and f.startswith("e_"))]
            if kind == "topk":
                kforms = ["none", "a_like", "b_range", "a_like_semi", "b_range_semi", "c_values", "e_values"]
            if kind == "corpus":
                kforms[3:3] = ["a_like_semi", "b_range_semi"]
                kforms.append("g_sums")
            header = f"\n### {kind}\n\n| form | " + " | ".join(sets) + " |\n|---|" + "---|" * len(sets)
            print(header, flush=True)
            out.append(header)
            rows: dict[str, list[str]] = {f: [] for f in kforms}
            for name, prefixes in sets.items():
                r = compile_rights(c, prefixes)
                n_ent, n_doc, s_doc = truth(c, r)
                for form in kforms:
                    if form == "g_sums":
                        t1 = time.perf_counter()
                        for _ in range(100):
                            got = g_sums(c, r)
                        ms = (time.perf_counter() - t1) * 10
                        assert got == (n_doc, s_doc), (form, name, got)
                        rows[form].append(f"{ms:.3f}")
                        continue
                    if form == "none":
                        sql, args = query(kind, form, r, engine, t)
                        ms, _ = await timed(lambda sql=sql, args=args: db.fetch(sql, args), reps)
                        rows[form].append(f"{ms:.1f}")
                        continue
                    if form == "c_temp":
                        sql, args = query(kind, form, r, engine, t)

                        async def fn(sql: str = sql, args: list[Any] = args, r: Rights = r) -> Any:
                            await fill_temp(db, r)
                            return await db.fetch(sql, args)
                    else:
                        sql, args = query(kind, form, r, engine, t)

                        async def fn(sql: str = sql, args: list[Any] = args) -> Any:
                            return await db.fetch(sql, args)

                    ms, got = await timed(fn, reps)
                    if kind == "topk":
                        assert [int(x[0]) for x in got] == top10(c, r), (kind, form, name, got)
                    else:
                        want = (n_ent,) if kind == "entries" else (n_doc, s_doc)
                        assert tuple(int(x) for x in got[0]) == want, (kind, form, name, got, want)
                    rows[form].append(f"{ms:.1f}")
                    if name == "100 spread":
                        plan = await db.plan(sql, args)
                        plans.append(f"### {kind} · {form} · {name}\n\n```\n{_clip(plan)}\n```\n")
            for form in kforms:
                line = f"| {form} | " + " | ".join(rows[form]) + " |"
                print(line, flush=True)
                out.append(line)
        out.append(await visible_chunks(db, c, t, sets, reps))
        out.append(await moves(db, c, t, reps))
        print(out[-2] + out[-1], flush=True)
    finally:
        if engine == "postgres":
            for suffix in ("docs2", "docs", "entries"):
                await db.exec(f"DROP TABLE IF EXISTS {t}_{suffix}")
            await db.exec("DROP TABLE IF EXISTS g_tmp")
        await db.close()
    with open(os.path.join(HERE, "runs", f"{label}.md"), "w") as f:
        f.write("\n".join(out) + "\n")
    with open(os.path.join(HERE, "runs", f"{label}-plans.md"), "w") as f:
        f.write(f"# Plans — {label}, the 100-spread rights\n\n" + "\n".join(plans))
    print(f"-> runs/{label}.md", flush=True)


def _clip(plan: str) -> str:
    return "\n".join(line if len(line) <= 220 else line[:220] + " …" for line in plan.splitlines())


async def visible_chunks(db: Any, c: Corpus, t: str, sets: dict[str, list[str]], reps: int) -> str:
    """_visible_chunks' job: which of a candidate chunk set the rights admit."""
    rng = random.Random(11)
    by_chunk = {cid: dn for cid, _, _, dn in c.docs}
    candidates = sorted(rng.sample([cid for cid, *_ in c.docs], len(c.docs) // 2))
    lines = [
        f"\n### visible chunks — {len(candidates):,} candidate chunk ids (half the corpus), ms\n",
        "| form | " + " | ".join(sets) + " |",
        "|---|" + "---|" * len(sets),
    ]
    today, ranged = [], []
    for prefixes in sets.values():
        r = compile_rights(c, prefixes)
        plist = r.prefixes

        def admits(path: str, plist: list[str] = plist) -> bool:
            i = bisect.bisect_right(plist, path) - 1
            while i >= 0:
                p = plist[i]
                if path == p or path.startswith(p + "/"):
                    return True
                if not path.startswith(p):
                    return False
                i -= 1
            return False

        async def current(admits: Any = admits) -> set[int]:
            seen: set[int] = set()
            for start in range(0, len(candidates), IN_CHUNK):
                ids = candidates[start : start + IN_CHUNK]
                b = Binds(db.engine)
                marks = ", ".join(b(i) for i in ids)
                sql = (
                    f"SELECT d.chunk_id, e.path FROM {t}_docs d JOIN {t}_entries e ON e.id = d.entry_id "
                    f"WHERE d.epoch = {EPOCH} AND d.chunk_id IN ({marks})"
                )
                seen.update(cid for cid, path in await db.fetch(sql, b.values) if admits(path))
            return seen

        los = [lo for lo, _ in r.doc_ranges]
        his = [hi for _, hi in r.doc_ranges]

        async def by_range(los: list[int] = los, his: list[int] = his) -> set[int]:
            seen: set[int] = set()
            for cid in candidates:
                dn = by_chunk[cid]
                i = bisect.bisect_right(los, dn) - 1
                if i >= 0 and dn <= his[i]:
                    seen.add(cid)
            return seen

        ms1, a = await timed(current, reps)
        ms2, b2 = await timed(by_range, reps)
        assert a == b2, "range filter disagrees"
        today.append(f"{ms1:.1f}")
        ranged.append(f"{ms2:.1f}")
    lines.append("| chunked IN join + app admit (today) | " + " | ".join(today) + " |")
    lines.append("| bisect over doc ranges, pure Python | " + " | ".join(ranged) + " |")
    return "\n".join(lines) + "\n"


async def moves(db: Any, c: Corpus, t: str, reps: int) -> str:
    """What a subtree move costs each encoding, rolled back after each run."""
    folder = c.folders[0]
    top = folder.rsplit("/", 1)[0]
    n_folder = c.pend[folder] - c.pre[folder] + 1
    n_top = c.pend[top] - c.pre[top] + 1
    total = len(c.entries)
    b = "?" if db.engine == "sqlite" else "$"

    def ph(i: int) -> str:
        return "?" if b == "?" else f"${i}"

    def path_rewrite(old: str, new: str) -> tuple[str, list[Any]]:
        sql = (
            f"UPDATE {t}_entries SET path = {ph(1)} || substr(path, {ph(2)}) "
            f"WHERE path = {ph(3)} OR (path >= {ph(4)} AND path < {ph(5)})"
        )
        return sql, [new, len(old) + 1, old, old + "/", old + "0"]

    def pre_shift(lo: int, hi: int, dest: int) -> tuple[str, list[Any]]:
        # Move preorder block [lo, hi] to sit after position dest (> hi): the block and everything between shift.
        k = hi - lo + 1
        sql = (
            f"UPDATE {t}_entries SET pre = CASE WHEN pre BETWEEN {ph(1)} AND {ph(2)} THEN pre + {ph(3)} "
            f"ELSE pre - {ph(4)} END WHERE pre BETWEEN {ph(5)} AND {ph(6)}"
        )
        return sql, [lo, hi, dest - hi, k, lo, dest]

    def insert_shift(at: int) -> tuple[str, list[Any]]:
        return f"UPDATE {t}_entries SET pre = pre + 1 WHERE pre >= {ph(1)}", [at]

    cases = [
        ("rename a folder in place — path rewrite", *path_rewrite(folder, folder + "x"), n_folder),
        ("rename a top folder in place — path rewrite", *path_rewrite(top, top + "x"), n_top),
        (
            "move a folder to the far end — dense preorder shift",
            *pre_shift(c.pre[folder], c.pend[folder], total - 1),
            total - c.pre[folder],
        ),
        (
            "move a folder next door — dense preorder shift",
            *pre_shift(c.pre[folder], c.pend[folder], c.pend[folder] + n_folder),
            2 * n_folder,
        ),
        ("insert one row at the front — dense preorder shift", *insert_shift(1), total - 1),
    ]
    lines = [
        f"\n### maintenance — one statement each, rolled back, ms (entry table {total:,} rows)\n",
        "| operation | rows touched | ms |",
        "|---|---|---|",
    ]
    for name, sql, args, touched in cases:
        samples = []
        for _ in range(reps):
            await db.begin()
            t0 = time.perf_counter()
            await db.exec(sql, args)
            samples.append((time.perf_counter() - t0) * 1000)
            await db.rollback()
        lines.append(f"| {name} | {touched:,} | {statistics.median(samples):.1f} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["sqlite", "postgres"])
    ap.add_argument("--url", default="postgresql://vfs:vfs@localhost:54320/vfs")
    ap.add_argument("--tops", type=int, default=10)
    ap.add_argument("--folders", type=int, default=200)
    ap.add_argument("--files", type=int, default=50)
    ap.add_argument("--chunks", type=int, default=1)
    ap.add_argument("--reps", type=int, default=5)
    a = ap.parse_args()
    asyncio.run(run(a.engine, a.url, a.tops, a.folders, a.files, a.chunks, a.reps))
