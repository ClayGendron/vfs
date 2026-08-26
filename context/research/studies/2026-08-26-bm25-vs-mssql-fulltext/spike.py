"""Query-time spike: vfs's owned BM25 tables vs SQL Server Full-Text Search.

Loads a seeded sample of the linux checkout into real vfs tables on an
FTS-enabled SQL Server (``Dockerfile`` beside this script), reindexes so
the ``lex_*`` tables exist, builds a full-text index over
``chunks.content``, then times the two lexical legs across the query
shapes glean will issue — unscoped top-K, joined to entries for
liveness and path, scoped by extension, by directory segment, by an
entry-id allow-list, aggregated to entries (MaxP), and everything at
once — and records each statement's plan operators so a planner that
abandons the ``(epoch, term, chunk_id)`` seek shows up as a finding,
not a slow median.

    uv run python spike.py --files 2000 --seed 7 --out results/

Measurement runs on a plain pyodbc connection so the numbers are the
engine's, not the async driver stack's. Requires the container from the
Dockerfile on port 14331 and ODBC Driver 18.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import statistics
import time
from pathlib import Path as FsPath

import pyodbc

from vfs.models import Entry
from vfs.models.lexical import tokenize
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

LINUX = FsPath.home() / "Git/Repos/linux"
EXTS = {".c", ".h", ".py", ".rst", ".txt", ".md", ".S", ".sh", ".yaml", ".json"}
HOST, PORT, PASSWORD, DB = "localhost", 14331, "vfsStr0ngPassw0rd", "vfs_spike"
ODBC = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={HOST},{PORT};UID=sa;PWD={PASSWORD};"
    "TrustServerCertificate=yes;DATABASE="
)
URL = f"mssql+aioodbc://sa:{PASSWORD}@{HOST}:{PORT}/{DB}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
TABLE = "vfs"
RUNS = 7
TOP = 10


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------


def sample_files(n: int, seed: int) -> list[FsPath]:
    files = sorted(p for p in LINUX.rglob("*") if p.is_file() and p.suffix in EXTS and ".git" not in p.parts)
    return random.Random(seed).sample(files, min(n, len(files)))


async def load(files: list[FsPath]) -> None:
    storage = DatabaseStorage(url=URL, table_name=TABLE)
    batch: list[Entry] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "\x00" in text or not text:
            continue
        batch.append(Entry(path=Path("/" + path.relative_to(LINUX).as_posix()), content=text))
        if len(batch) == 500:
            assert (await storage.write(entries=batch, parents=True)).success
            batch = []
    if batch:
        assert (await storage.write(entries=batch, parents=True)).success
    t0 = time.perf_counter()
    assert (await storage.reindex()).success
    print(f"reindex (grams + lexical) {time.perf_counter() - t0:.1f}s")
    await storage.close()


def ensure_database() -> None:
    con = pyodbc.connect(ODBC + "master", autocommit=True)
    exists = con.execute("SELECT 1 FROM sys.databases WHERE name = ?", DB).fetchone()
    if exists:
        con.execute(f"ALTER DATABASE {DB} SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        con.execute(f"DROP DATABASE {DB}")
    con.execute(f"CREATE DATABASE {DB}")
    con.close()


def build_fulltext(con: pyodbc.Connection) -> float:
    pk = con.execute(
        "SELECT i.name FROM sys.indexes i JOIN sys.tables t ON t.object_id = i.object_id "
        f"WHERE t.name = '{TABLE}_chunks' AND i.is_primary_key = 1"
    ).fetchone()[0]
    con.execute("CREATE FULLTEXT CATALOG vfs_ft AS DEFAULT")
    t0 = time.perf_counter()
    con.execute(
        f"CREATE FULLTEXT INDEX ON {TABLE}_chunks (content LANGUAGE 1033) KEY INDEX {pk} "
        "ON vfs_ft WITH CHANGE_TRACKING OFF, NO POPULATION"
    )
    con.execute(f"ALTER FULLTEXT INDEX ON {TABLE}_chunks START FULL POPULATION")
    while True:
        status = con.execute("SELECT FULLTEXTCATALOGPROPERTY('vfs_ft', 'PopulateStatus')").fetchone()[0]
        if status == 0:
            break
        time.sleep(1)
    return time.perf_counter() - t0


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def pick_queries(con: pyodbc.Connection, epoch: int, seed: int) -> dict[str, list[list[str]]]:
    """Terms by df band, as the lexical study drew them: mid, rare, common."""
    n_docs = con.execute(f"SELECT n_docs FROM {TABLE}_lex_stats WHERE epoch = ?", epoch).fetchone()[0]
    rows = con.execute(
        f"SELECT term, df FROM {TABLE}_lex_df WHERE epoch = ? AND LEN(term) BETWEEN 4 AND 20 "
        "AND term NOT LIKE '%[^a-z0-9_]%'",
        epoch,
    ).fetchall()
    rng = random.Random(seed)
    mid = [t for t, df in rows if 0.002 * n_docs <= df <= 0.02 * n_docs]
    rare = [t for t, df in rows if 3 <= df < 0.002 * n_docs]
    common = [t for t, df in rows if df > 0.2 * n_docs]
    print(f"vocab bands: mid {len(mid)}, rare {len(rare)}, common {len(common)} of {n_docs} chunks")
    one = [[rng.choice(mid)] for _ in range(15)]
    three = [[*rng.sample(mid, 2), rng.choice(common)] for _ in range(15)]
    six = [[rng.choice(rare), *rng.sample(mid, 4), rng.choice(common)] for _ in range(15)]
    return {"1-term": one, "3-term": three, "6-term": six}


def contains_expr(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"' for t in terms)


def shapes(epoch: int, ext_value: str, segment: str, allow_ids: list[bytes]) -> dict[str, dict[str, str]]:
    """Each shape: the owned-table statement and the FTS statement, with {terms}/{ft} slots."""
    lt, ld, e, c, seg = f"{TABLE}_lex_terms", f"{TABLE}_lex_docs", TABLE, f"{TABLE}_chunks", f"{TABLE}_segments"
    ours_scores = f"SELECT chunk_id, SUM(weight) AS score FROM {lt} WHERE epoch = {epoch} AND term IN ({{terms}}) GROUP BY chunk_id"
    fts_scores = f"SELECT [KEY] AS chunk_id, RANK AS score FROM CONTAINSTABLE({c}, content, '{{ft}}')"
    allow = ", ".join("0x" + b.hex() for b in allow_ids)
    return {
        "S1 unscoped top-K": {
            "ours": f"SELECT TOP {TOP} chunk_id, score FROM ({ours_scores}) s ORDER BY score DESC, chunk_id",
            "fts": f"SELECT TOP {TOP} chunk_id, score FROM ({fts_scores}) s ORDER BY score DESC, chunk_id",
        },
        "S2 joined to entries (liveness + path)": {
            "ours": (
                f"SELECT TOP {TOP} e.path, s.score FROM ({ours_scores}) s "
                f"JOIN {ld} d ON d.epoch = {epoch} AND d.chunk_id = s.chunk_id "
                f"JOIN {e} e ON e.entry_id = d.entry_id AND e.deleted_at IS NULL "
                "ORDER BY s.score DESC, s.chunk_id"
            ),
            "fts": (
                f"SELECT TOP {TOP} e.path, s.score FROM ({fts_scores}) s "
                f"JOIN {c} ch ON ch.id = s.chunk_id JOIN {e} e ON e.entry_id = ch.entry_id AND e.deleted_at IS NULL "
                "ORDER BY s.score DESC, s.chunk_id"
            ),
        },
        "S3 scoped by extension": {
            "ours": (
                f"SELECT TOP {TOP} e.path, s.score FROM ({ours_scores}) s "
                f"JOIN {ld} d ON d.epoch = {epoch} AND d.chunk_id = s.chunk_id "
                f"JOIN {e} e ON e.entry_id = d.entry_id AND e.deleted_at IS NULL AND e.ext = '{ext_value}' "
                "ORDER BY s.score DESC, s.chunk_id"
            ),
            "fts": (
                f"SELECT TOP {TOP} e.path, s.score FROM ({fts_scores}) s "
                f"JOIN {c} ch ON ch.id = s.chunk_id "
                f"JOIN {e} e ON e.entry_id = ch.entry_id AND e.deleted_at IS NULL AND e.ext = '{ext_value}' "
                "ORDER BY s.score DESC, s.chunk_id"
            ),
        },
        "S4 scoped by directory segment": {
            "ours": (
                f"SELECT TOP {TOP} e.path, s.score FROM ({ours_scores}) s "
                f"JOIN {ld} d ON d.epoch = {epoch} AND d.chunk_id = s.chunk_id "
                f"JOIN {e} e ON e.entry_id = d.entry_id AND e.deleted_at IS NULL "
                f"WHERE EXISTS (SELECT 1 FROM {seg} g WHERE g.entry_id = e.entry_id AND g.segment = '{segment}') "
                "ORDER BY s.score DESC, s.chunk_id"
            ),
            "fts": (
                f"SELECT TOP {TOP} e.path, s.score FROM ({fts_scores}) s "
                f"JOIN {c} ch ON ch.id = s.chunk_id JOIN {e} e ON e.entry_id = ch.entry_id AND e.deleted_at IS NULL "
                f"WHERE EXISTS (SELECT 1 FROM {seg} g WHERE g.entry_id = e.entry_id AND g.segment = '{segment}') "
                "ORDER BY s.score DESC, s.chunk_id"
            ),
        },
        "S5 scoped by an id allow-list (500 ids)": {
            "ours": (
                f"SELECT TOP {TOP} d.entry_id, s.score FROM ({ours_scores}) s "
                f"JOIN {ld} d ON d.epoch = {epoch} AND d.chunk_id = s.chunk_id "
                f"WHERE d.entry_id IN ({allow}) ORDER BY s.score DESC, s.chunk_id"
            ),
            "fts": (
                f"SELECT TOP {TOP} ch.entry_id, s.score FROM ({fts_scores}) s "
                f"JOIN {c} ch ON ch.id = s.chunk_id WHERE ch.entry_id IN ({allow}) ORDER BY s.score DESC, s.chunk_id"
            ),
        },
        "S6 MaxP to entries": {
            "ours": (
                f"SELECT TOP {TOP} d.entry_id, MAX(s.score) AS best FROM ({ours_scores}) s "
                f"JOIN {ld} d ON d.epoch = {epoch} AND d.chunk_id = s.chunk_id "
                "GROUP BY d.entry_id ORDER BY best DESC, d.entry_id"
            ),
            "fts": (
                f"SELECT TOP {TOP} ch.entry_id, MAX(s.score) AS best FROM ({fts_scores}) s "
                f"JOIN {c} ch ON ch.id = s.chunk_id GROUP BY ch.entry_id ORDER BY best DESC, ch.entry_id"
            ),
        },
        "S7 ext + segment + MaxP": {
            "ours": (
                f"SELECT TOP {TOP} e.path, MAX(s.score) AS best FROM ({ours_scores}) s "
                f"JOIN {ld} d ON d.epoch = {epoch} AND d.chunk_id = s.chunk_id "
                f"JOIN {e} e ON e.entry_id = d.entry_id AND e.deleted_at IS NULL AND e.ext = '{ext_value}' "
                f"WHERE EXISTS (SELECT 1 FROM {seg} g WHERE g.entry_id = e.entry_id AND g.segment = '{segment}') "
                "GROUP BY e.path ORDER BY best DESC, e.path"
            ),
            "fts": (
                f"SELECT TOP {TOP} e.path, MAX(s.score) AS best FROM ({fts_scores}) s "
                f"JOIN {c} ch ON ch.id = s.chunk_id "
                f"JOIN {e} e ON e.entry_id = ch.entry_id AND e.deleted_at IS NULL AND e.ext = '{ext_value}' "
                f"WHERE EXISTS (SELECT 1 FROM {seg} g WHERE g.entry_id = e.entry_id AND g.segment = '{segment}') "
                "GROUP BY e.path ORDER BY best DESC, e.path"
            ),
        },
    }


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def fill(template: str, terms: list[str]) -> str:
    quoted = ", ".join("'" + t.replace("'", "''") + "'" for t in terms)
    return template.replace("{terms}", quoted).replace("{ft}", contains_expr(terms).replace("'", "''"))


def timed(con: pyodbc.Connection, sql: str) -> tuple[float, list[tuple]]:
    cur = con.cursor()
    t0 = time.perf_counter()
    rows = cur.execute(sql).fetchall()
    elapsed = (time.perf_counter() - t0) * 1000
    cur.close()
    return elapsed, [tuple(r) for r in rows]


def plan_operators(con: pyodbc.Connection, sql: str) -> list[str]:
    """Estimated plan's physical operators, in plan order (SHOWPLAN_TEXT)."""
    cur = con.cursor()
    cur.execute("SET SHOWPLAN_TEXT ON")
    cur.close()
    cur = con.cursor()
    cur.execute(sql)
    lines: list[str] = []
    while True:
        try:
            lines.extend(str(r[0]) for r in cur.fetchall())
        except pyodbc.ProgrammingError:
            pass
        if not cur.nextset():
            break
    cur.close()
    cur = con.cursor()
    cur.execute("SET SHOWPLAN_TEXT OFF")
    cur.close()
    ops: list[str] = []
    for line in lines:
        m = re.search(r"\|--([A-Za-z ]+?)\(", line)
        if m:
            op = m.group(1).strip()
            obj = re.search(r"OBJECT:\(\[[^\]]*\]\.\[dbo\]\.\[([^\]]+)\]", line)
            idx = re.search(r"\.\[([^\]]+)\]\)(?:, SEEK| )", line)
            ops.append(op + (f"[{obj.group(1)}]" if obj else ""))
    return ops


def key_of(row: tuple) -> object:
    return row[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="results")
    ap.add_argument("--skip-load", action="store_true", help="reuse the loaded database")
    args = ap.parse_args()
    out = FsPath(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if not args.skip_load:
        ensure_database()
        files = sample_files(args.files, args.seed)
        t0 = time.perf_counter()
        asyncio.run(load(files))
        print(f"loaded {len(files)} files in {time.perf_counter() - t0:.1f}s")
    con = pyodbc.connect(ODBC + DB, autocommit=True)
    if not args.skip_load:
        ft_seconds = build_fulltext(con)
        print(f"full-text population {ft_seconds:.1f}s")
    else:
        ft_seconds = None

    epoch = con.execute(f"SELECT current_gram_epoch FROM {TABLE}_meta").fetchone()[0]
    counts = {
        "chunks": con.execute(f"SELECT COUNT(*) FROM {TABLE}_chunks").fetchone()[0],
        "term_rows": con.execute(f"SELECT COUNT(*) FROM {TABLE}_lex_terms WHERE epoch = ?", epoch).fetchone()[0],
        "vocab": con.execute(f"SELECT COUNT(*) FROM {TABLE}_lex_df WHERE epoch = ?", epoch).fetchone()[0],
    }
    sizes = {
        r[0]: r[1]
        for r in con.execute(
            "SELECT t.name, SUM(a.total_pages) * 8 FROM sys.tables t JOIN sys.indexes i ON t.object_id = i.object_id "
            "JOIN sys.partitions p ON i.object_id = p.object_id AND i.index_id = p.index_id "
            "JOIN sys.allocation_units a ON p.partition_id = a.container_id GROUP BY t.name"
        ).fetchall()
    }
    ft_kb = con.execute("SELECT FULLTEXTCATALOGPROPERTY('vfs_ft', 'IndexSize')").fetchone()[0] * 1024
    print("counts", counts, "sizes KB", {k: v for k, v in sizes.items() if "lex" in k or "chunks" in k}, "ft KB", ft_kb)

    ext_value = con.execute(
        f"SELECT TOP 1 ext FROM {TABLE} WHERE kind = 'file' GROUP BY ext ORDER BY COUNT(*) DESC"
    ).fetchone()[0]
    segment = con.execute(
        f"SELECT TOP 1 segment FROM {TABLE}_segments GROUP BY segment ORDER BY COUNT(*) DESC"
    ).fetchone()[0]
    segment = segment.decode() if isinstance(segment, (bytes, bytearray)) else segment
    ids = [r[0] for r in con.execute(f"SELECT entry_id FROM {TABLE} WHERE kind = 'file'").fetchall()]
    allow_ids = random.Random(args.seed).sample(ids, min(500, len(ids)))
    print(f"scope: ext={ext_value!r} segment={segment!r} allow-list={len(allow_ids)}")

    queries = pick_queries(con, epoch, args.seed)
    all_shapes = shapes(epoch, ext_value, segment, allow_ids)
    results: dict[str, dict[str, dict[str, object]]] = {}
    for shape, stmts in all_shapes.items():
        results[shape] = {}
        for arity, qs in queries.items():
            ours_ms, fts_ms, overlaps = [], [], []
            for terms in qs:
                o_sql, f_sql = fill(stmts["ours"], terms), fill(stmts["fts"], terms)
                o_times, f_times = [], []
                o_rows = f_rows = []
                for _ in range(RUNS):
                    t, o_rows = timed(con, o_sql)
                    o_times.append(t)
                    t, f_rows = timed(con, f_sql)
                    f_times.append(t)
                ours_ms.append(statistics.median(o_times))
                fts_ms.append(statistics.median(f_times))
                o_keys, f_keys = {key_of(r) for r in o_rows}, {key_of(r) for r in f_rows}
                overlaps.append(len(o_keys & f_keys) / max(1, len(o_keys | f_keys)))
            probe = fill(stmts["ours"], qs[0]), fill(stmts["fts"], qs[0])
            results[shape][arity] = {
                "ours_ms_median": statistics.median(ours_ms),
                "ours_ms_p90": sorted(ours_ms)[int(0.9 * (len(ours_ms) - 1))],
                "fts_ms_median": statistics.median(fts_ms),
                "fts_ms_p90": sorted(fts_ms)[int(0.9 * (len(fts_ms) - 1))],
                "top10_jaccard_median": statistics.median(overlaps),
                "ours_plan": plan_operators(con, probe[0]),
                "fts_plan": plan_operators(con, probe[1]),
            }
            r = results[shape][arity]
            print(
                f"{shape:42} {arity:7} ours {r['ours_ms_median']:7.2f} ms  fts {r['fts_ms_median']:7.2f} ms  "
                f"jaccard {r['top10_jaccard_median']:.2f}"
            )
    con.close()
    payload = {
        "files": args.files,
        "seed": args.seed,
        "counts": counts,
        "sizes_kb": sizes,
        "fulltext_index_bytes": ft_kb,
        "fulltext_population_s": ft_seconds,
        "scope": {"ext": ext_value, "segment": segment, "allow_ids": len(allow_ids)},
        "queries": queries,
        "results": results,
    }
    (out / f"spike-{args.files}.json").write_text(json.dumps(payload, indent=1, default=str))
    print("wrote", out / f"spike-{args.files}.json")


main()
