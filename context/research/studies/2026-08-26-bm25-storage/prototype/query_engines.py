"""Both options on the real engines: load Option A's rows (from the store)
and Option B's blocks (from the Rust build) into a ``bm25a_*``/``bm25b_*``
namespace on Postgres, MySQL, SQL Server, and Oracle; time the same 45
queries — A's in-engine SUM(weight) vs B's blob fetch + numpy scoring —
unscoped (S1), scoped by extension (S3), and scoped by a 500-entry
allow-list (S5); for B both client-side filtering (fetch the scope's chunk
ids, np.isin) and a semi-join (score all, probe the top candidates in
SQL). Load wall and bytes per table per engine are recorded. Drops the
namespace at the end unless ``--keep``.

    uv run --no-sync python query_engines.py [--engines pg,my,ms,or] [--reps 5]
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sqlite3
import statistics
import time

import numpy as np

from common import EPOCH_A, EPOCH_B, OPTION_B_RS, STORE, TOP_K, draw_queries, dump_json, kendall_tau, round_top, score_full_batched, timed

URLS = {
    "pg": dict(host="localhost", port=54320, user="vfs", password="vfs", database="vfs"),
    "my": dict(host="localhost", port=33061, user="vfs", password="vfs", database="vfs", charset="utf8mb4"),
    "ms": "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost,14330;UID=sa;PWD=vfsStr0ngPassw0rd;DATABASE=master;TrustServerCertificate=yes",
    "or": dict(user="vfs", password="vfs", dsn="localhost:15210/FREEPDB1"),
}
LOAD_BATCH = 20_000
SEMI_PAGE = 200


# ---------------------------------------------------------------------------
# Engine adapters (sync surface; Postgres wraps asyncpg in a private loop)
# ---------------------------------------------------------------------------


class Engine:
    name = ""
    term_type = ""
    blob_type = ""
    id16 = ""
    double = ""
    bigint = "BIGINT"
    limit_head = ""
    limit_tail = ""

    def run(self, sql: str) -> None: ...
    def fetch(self, sql: str) -> list[tuple]: ...
    def load(self, table: str, ncols: int, rows: list[tuple]) -> None: ...
    def table_bytes(self, table: str) -> int: ...
    def close(self) -> None: ...

    def term_lit(self, term: str) -> str:
        assert "'" not in term
        return "'" + term + "'"

    def id_lit(self, entry_id: bytes) -> str: ...

    def drop(self, table: str) -> None: ...

    def limit(self, sql: str) -> str:
        return sql.replace("SELECT ", f"SELECT {self.limit_head}", 1) + self.limit_tail


class Postgres(Engine):
    name = "postgres"
    term_type = 'VARCHAR(64) COLLATE "C"'
    blob_type = "BYTEA"
    id16 = "BYTEA"
    double = "DOUBLE PRECISION"
    limit_tail = f" LIMIT {TOP_K}"

    def __init__(self) -> None:
        import asyncpg

        self.loop = asyncio.new_event_loop()
        self.conn = self.loop.run_until_complete(asyncpg.connect(**URLS["pg"]))

    def run(self, sql: str) -> None:
        self.loop.run_until_complete(self.conn.execute(sql))

    def fetch(self, sql: str) -> list[tuple]:
        return [tuple(r) for r in self.loop.run_until_complete(self.conn.fetch(sql))]

    def load(self, table: str, ncols: int, rows: list[tuple]) -> None:
        self.loop.run_until_complete(self.conn.copy_records_to_table(table, records=rows))

    def table_bytes(self, table: str) -> int:
        return int(self.fetch(f"SELECT pg_total_relation_size('{table}')")[0][0])

    def id_lit(self, entry_id: bytes) -> str:
        return f"'\\x{entry_id.hex()}'::bytea"

    def drop(self, table: str) -> None:
        self.run(f"DROP TABLE IF EXISTS {table}")

    def close(self) -> None:
        self.loop.run_until_complete(self.conn.close())


class MySQL(Engine):
    name = "mysql"
    term_type = "VARBINARY(64)"
    blob_type = "VARBINARY(2000)"
    id16 = "BINARY(16)"
    double = "DOUBLE"
    limit_tail = f" LIMIT {TOP_K}"

    def __init__(self) -> None:
        import pymysql

        self.conn = pymysql.connect(**URLS["my"], autocommit=True)

    def run(self, sql: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(sql)

    def fetch(self, sql: str) -> list[tuple]:
        with self.conn.cursor() as cur:
            cur.execute(sql)
            return [tuple(r) for r in cur.fetchall()]

    def load(self, table: str, ncols: int, rows: list[tuple]) -> None:
        marks = ", ".join("%s" for _ in range(ncols))
        with self.conn.cursor() as cur:
            cur.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)

    def table_bytes(self, table: str) -> int:
        self.run(f"ANALYZE TABLE {table}")
        return int(self.fetch(f"SELECT data_length + index_length FROM information_schema.tables WHERE table_schema = 'vfs' AND table_name = '{table}'")[0][0])

    def term_lit(self, term: str) -> str:
        return "X'" + term.encode().hex() + "'"

    def id_lit(self, entry_id: bytes) -> str:
        return "X'" + entry_id.hex() + "'"

    def drop(self, table: str) -> None:
        self.run(f"DROP TABLE IF EXISTS {table}")

    def close(self) -> None:
        self.conn.close()


class MSSQL(Engine):
    name = "mssql"
    term_type = "VARCHAR(64) COLLATE Latin1_General_100_BIN2_UTF8"
    blob_type = "VARBINARY(2000)"
    id16 = "BINARY(16)"
    double = "FLOAT"
    limit_head = f"TOP {TOP_K} "

    def __init__(self) -> None:
        import pyodbc

        self.conn = pyodbc.connect(URLS["ms"], autocommit=True)

    def run(self, sql: str) -> None:
        self.conn.execute(sql)

    def fetch(self, sql: str) -> list[tuple]:
        return [tuple(r) for r in self.conn.execute(sql).fetchall()]

    def load(self, table: str, ncols: int, rows: list[tuple]) -> None:
        """BULK INSERT from a TSV copied into the container: pyodbc's
        fast_executemany measured ~100 k rows/min against the emulated
        server, which would have put Option A's 3.09 M rows past 30 min.
        Binary columns travel as hex text (bcp character mode)."""
        import os
        import subprocess
        import tempfile

        def cell(v):
            if v is None:
                return ""
            if isinstance(v, (bytes, bytearray)):
                return v.hex()
            return str(v)

        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-16") as fh:
            for r in rows:
                fh.write("\t".join(cell(v) for v in r) + "\n")
            local = fh.name
        os.chmod(local, 0o644)
        remote = f"/tmp/bulk_{table}.tsv"
        subprocess.run(["docker", "cp", local, f"vfs-test-mssql-1:{remote}"], check=True, capture_output=True)
        self.conn.execute(
            f"BULK INSERT {table} FROM '{remote}' WITH (DATAFILETYPE='widechar', FIELDTERMINATOR='\\t', ROWTERMINATOR='\\n', TABLOCK)"
        )
        os.unlink(local)

    def table_bytes(self, table: str) -> int:
        return int(self.fetch(f"SELECT SUM(used_page_count) * 8192 FROM sys.dm_db_partition_stats WHERE object_id = OBJECT_ID('{table}')")[0][0])

    def id_lit(self, entry_id: bytes) -> str:
        return "0x" + entry_id.hex()

    def drop(self, table: str) -> None:
        self.run(f"IF OBJECT_ID('{table}') IS NOT NULL DROP TABLE {table}")

    def close(self) -> None:
        self.conn.close()


class Oracle(Engine):
    name = "oracle"
    term_type = "VARCHAR2(64 CHAR)"
    blob_type = "RAW(2000)"
    id16 = "RAW(16)"
    double = "BINARY_DOUBLE"
    bigint = "NUMBER(19)"
    limit_tail = f" FETCH FIRST {TOP_K} ROWS ONLY"

    def __init__(self) -> None:
        import oracledb

        self.conn = oracledb.connect(**URLS["or"])
        self.conn.autocommit = True

    def run(self, sql: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(sql)

    def fetch(self, sql: str) -> list[tuple]:
        with self.conn.cursor() as cur:
            cur.execute(sql)
            return [tuple(r) for r in cur.fetchall()]

    def load(self, table: str, ncols: int, rows: list[tuple]) -> None:
        marks = ", ".join(f":{i + 1}" for i in range(ncols))
        with self.conn.cursor() as cur:
            cur.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)

    def table_bytes(self, table: str) -> int:
        t = table.upper()
        return int(
            self.fetch(
                f"SELECT SUM(bytes) FROM user_segments WHERE segment_name = '{t}' "
                f"OR segment_name IN (SELECT index_name FROM user_indexes WHERE table_name = '{t}')"
            )[0][0]
        )

    def id_lit(self, entry_id: bytes) -> str:
        return f"HEXTORAW('{entry_id.hex()}')"

    def drop(self, table: str) -> None:
        try:
            self.run(f"DROP TABLE {table} PURGE")
        except Exception:
            pass

    def close(self) -> None:
        self.conn.close()


ENGINES = {"pg": Postgres, "my": MySQL, "ms": MSSQL, "or": Oracle}


# ---------------------------------------------------------------------------
# Schema and load
# ---------------------------------------------------------------------------

TABLES = ["bm25a_terms", "bm25b_postings", "bm25b_docs", "bm25b_df", "bm25b_stats", "bm25b_entries"]


def ddl(e: Engine) -> list[str]:
    return [
        f"CREATE TABLE bm25a_terms (epoch INTEGER NOT NULL, term {e.term_type} NOT NULL, chunk_id {e.bigint} NOT NULL, tf INTEGER NOT NULL, weight {e.double} NOT NULL, PRIMARY KEY (epoch, term, chunk_id))",
        f"CREATE TABLE bm25b_postings (epoch INTEGER NOT NULL, term {e.term_type} NOT NULL, block_no INTEGER NOT NULL, doc_count INTEGER NOT NULL, max_tf INTEGER NOT NULL, min_dl INTEGER NOT NULL, doc_ids {e.blob_type} NOT NULL, tfs {e.blob_type} NOT NULL, dls {e.blob_type} NOT NULL, PRIMARY KEY (epoch, term, block_no))",
        f"CREATE TABLE bm25b_docs (epoch INTEGER NOT NULL, chunk_id {e.bigint} NOT NULL, entry_id {e.id16} NOT NULL, dl INTEGER NOT NULL, PRIMARY KEY (epoch, chunk_id))",
        "CREATE INDEX ix_bm25b_docs_entry ON bm25b_docs (epoch, entry_id)",
        f"CREATE TABLE bm25b_df (epoch INTEGER NOT NULL, term {e.term_type} NOT NULL, df INTEGER NOT NULL, idf {e.double} NOT NULL, PRIMARY KEY (epoch, term))",
        f"CREATE TABLE bm25b_stats (epoch INTEGER NOT NULL, n_docs INTEGER NOT NULL, avg_dl {e.double} NOT NULL, PRIMARY KEY (epoch))",
        f"CREATE TABLE bm25b_entries (entry_id {e.id16} NOT NULL, ext VARCHAR(32), deleted INTEGER NOT NULL, PRIMARY KEY (entry_id))",
        "CREATE INDEX ix_bm25b_entries_ext ON bm25b_entries (ext)",
    ]


def iter_batches(cursor, transform):
    while rows := cursor.fetchmany(LOAD_BATCH):
        yield [transform(r) for r in rows]


def load_all(e: Engine, store: sqlite3.Connection, optb: sqlite3.Connection) -> dict:
    for t in TABLES:
        e.drop(t)
    for stmt in ddl(e):
        e.run(stmt)
    term = (lambda t: t.encode()) if e.name == "mysql" else (lambda t: t)
    timings: dict = {}
    t0 = time.perf_counter()
    n = 0
    cur = store.execute(f"SELECT epoch, term, chunk_id, tf, weight FROM vfs_lex_terms WHERE epoch = {EPOCH_A}")
    for batch in iter_batches(cur, lambda r: (r[0], term(r[1]), r[2], r[3], r[4])):
        e.load("bm25a_terms", 5, batch)
        n += len(batch)
    timings["a_terms"] = {"rows": n, "wall_s": round(time.perf_counter() - t0, 2)}
    t0 = time.perf_counter()
    n = 0
    cur = optb.execute("SELECT epoch, term, block_no, doc_count, max_tf, min_dl, doc_ids, tfs, dls FROM lex_postings")
    for batch in iter_batches(cur, lambda r: (r[0], term(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8])):
        e.load("bm25b_postings", 9, batch)
        n += len(batch)
    timings["b_postings"] = {"rows": n, "wall_s": round(time.perf_counter() - t0, 2)}
    t0 = time.perf_counter()
    cur = optb.execute("SELECT epoch, chunk_id, entry_id, dl FROM lex_docs")
    for batch in iter_batches(cur, lambda r: (r[0], r[1], bytes(r[2]), r[3])):
        e.load("bm25b_docs", 4, batch)
    cur = optb.execute("SELECT epoch, term, df, idf FROM lex_df")
    for batch in iter_batches(cur, lambda r: (r[0], term(r[1]), r[2], r[3])):
        e.load("bm25b_df", 4, batch)
    e.load("bm25b_stats", 3, [tuple(optb.execute("SELECT epoch, n_docs, avg_dl FROM lex_stats").fetchone())])
    cur = store.execute("SELECT entry_id, ext, CASE WHEN deleted_at IS NULL THEN 0 ELSE 1 END FROM vfs WHERE chunked")
    for batch in iter_batches(cur, lambda r: (bytes(r[0]), r[1], r[2])):
        e.load("bm25b_entries", 3, batch)
    timings["shared_docs_df_stats_entries"] = {"wall_s": round(time.perf_counter() - t0, 2)}
    if e.name == "postgres":
        for t in TABLES:
            e.run(f"ANALYZE {t}")
    elif e.name == "oracle":
        for t in TABLES:
            e.run(f"BEGIN DBMS_STATS.GATHER_TABLE_STATS(USER, '{t.upper()}'); END;")
    elif e.name == "mssql":
        for t in TABLES:
            e.run(f"UPDATE STATISTICS {t}")
    timings["bytes"] = {t: e.table_bytes(t) for t in TABLES}
    return timings


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


def a_scores(e: Engine, terms: list[str]) -> str:
    lits = ", ".join(e.term_lit(t) for t in terms)
    return f"SELECT chunk_id, SUM(weight) AS score FROM bm25a_terms WHERE epoch = {EPOCH_A} AND term IN ({lits}) GROUP BY chunk_id"


def a_s1(e: Engine, terms: list[str]) -> str:
    return e.limit(f"SELECT chunk_id, score FROM ({a_scores(e, terms)}) s ORDER BY score DESC, chunk_id")


def a_s3(e: Engine, terms: list[str], ext: str) -> str:
    return e.limit(
        f"SELECT s.chunk_id, s.score FROM ({a_scores(e, terms)}) s "
        f"JOIN bm25b_docs d ON d.epoch = {EPOCH_B} AND d.chunk_id = s.chunk_id "
        f"JOIN bm25b_entries en ON en.entry_id = d.entry_id AND en.deleted = 0 AND en.ext = '{ext}' "
        "ORDER BY s.score DESC, s.chunk_id"
    )


def a_s5(e: Engine, terms: list[str], allow_lits: str) -> str:
    return e.limit(
        f"SELECT s.chunk_id, s.score FROM ({a_scores(e, terms)}) s "
        f"JOIN bm25b_docs d ON d.epoch = {EPOCH_B} AND d.chunk_id = s.chunk_id "
        f"WHERE d.entry_id IN ({allow_lits}) ORDER BY s.score DESC, s.chunk_id"
    )


def b_blocks(e: Engine, terms: list[str]) -> str:
    lits = ", ".join(e.term_lit(t) for t in terms)
    return f"SELECT term, block_no, doc_count, max_tf, min_dl, doc_ids, tfs, dls FROM bm25b_postings WHERE epoch = {EPOCH_B} AND term IN ({lits})"


def b_df(e: Engine, terms: list[str]) -> str:
    lits = ", ".join(e.term_lit(t) for t in terms)
    return f"SELECT term, idf FROM bm25b_df WHERE epoch = {EPOCH_B} AND term IN ({lits})"


def b_blocks_joined(e: Engine, terms: list[str]) -> str:
    """One round trip: the blocks with their term's idf joined in."""
    lits = ", ".join(e.term_lit(t) for t in terms)
    return (
        "SELECT p.term, p.block_no, p.doc_count, p.max_tf, p.min_dl, p.doc_ids, p.tfs, p.dls, d.idf "
        f"FROM bm25b_postings p JOIN bm25b_df d ON d.epoch = p.epoch AND d.term = p.term "
        f"WHERE p.epoch = {EPOCH_B} AND p.term IN ({lits})"
    )


def scope_ext_ids(ext: str) -> str:
    return f"SELECT d.chunk_id FROM bm25b_docs d JOIN bm25b_entries en ON en.entry_id = d.entry_id WHERE d.epoch = {EPOCH_B} AND en.deleted = 0 AND en.ext = '{ext}'"


def scope_allow_ids(allow_lits: str) -> str:
    return f"SELECT d.chunk_id FROM bm25b_docs d WHERE d.epoch = {EPOCH_B} AND d.entry_id IN ({allow_lits})"


def semi_probe(base_scope: str, chunk_ids: list[int]) -> str:
    ids = ", ".join(str(i) for i in chunk_ids)
    return f"{base_scope} AND d.chunk_id IN ({ids})"


# ---------------------------------------------------------------------------
# Option B evaluation shapes
# ---------------------------------------------------------------------------


def b_fetch(e: Engine, terms: list[str]):
    idfs = {(t.decode() if isinstance(t, (bytes, bytearray)) else t): float(i) for t, i in e.fetch(b_df(e, terms))}
    rows = e.fetch(b_blocks(e, terms))
    blocks = [((r[0].decode() if isinstance(r[0], (bytes, bytearray)) else r[0]), r[1], r[2], r[3], r[4], bytes(r[5]), bytes(r[6]), bytes(r[7])) for r in rows]
    return idfs, blocks


def b_fetch_joined(e: Engine, terms: list[str]):
    idfs: dict[str, float] = {}
    blocks = []
    for r in e.fetch(b_blocks_joined(e, terms)):
        term = r[0].decode() if isinstance(r[0], (bytes, bytearray)) else r[0]
        idfs[term] = float(r[8])
        blocks.append((term, r[1], r[2], r[3], r[4], bytes(r[5]), bytes(r[6]), bytes(r[7])))
    return idfs, blocks


def b_all_candidates(blocks, idfs, avg_dl):
    """Every candidate ordered by score desc, id asc (for the semi-join probe)."""
    top, _ = score_full_batched(blocks, idfs, avg_dl)
    return top


def b_semijoin(e: Engine, blocks, idfs, avg_dl, base_scope: str):
    from common import decode_varints_fast, tf_norm

    # Score everything, order all candidates, probe pages of ids until top-k survive.
    counts = np.fromiter((b[2] for b in blocks), dtype=np.int64, count=len(blocks))
    deltas = decode_varints_fast(b"".join(b[5] for b in blocks))
    run = np.cumsum(deltas)
    starts = np.cumsum(counts) - counts
    ids = run - np.repeat(run[starts] - deltas[starts], counts)
    tfs = decode_varints_fast(b"".join(b[6] for b in blocks))
    dls = decode_varints_fast(b"".join(b[7] for b in blocks))
    term_idf = np.repeat(np.fromiter((idfs[b[0]] for b in blocks), dtype=np.float64, count=len(blocks)), counts)
    scores = term_idf * tf_norm(tfs, dls, avg_dl)
    uniq, inverse = np.unique(ids, return_inverse=True)
    agg = np.bincount(inverse, weights=scores, minlength=uniq.size)
    order = np.lexsort((uniq, -agg))
    ranked_ids, ranked_scores = uniq[order], agg[order]
    survivors: list[tuple[int, float]] = []
    probes = 0
    for start in range(0, ranked_ids.size, SEMI_PAGE):
        page = ranked_ids[start : start + SEMI_PAGE]
        keep = {int(r[0]) for r in e.fetch(semi_probe(base_scope, [int(i) for i in page]))}
        probes += 1
        for cid, sc in zip(page, ranked_scores[start : start + SEMI_PAGE]):
            if int(cid) in keep:
                survivors.append((int(cid), float(sc)))
                if len(survivors) == TOP_K:
                    return survivors, probes
    return survivors, probes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def bench_engine(key: str, reps: int, queries, ext: str, allow_ids: list[bytes], keep: bool) -> dict:
    e = ENGINES[key]()
    store = sqlite3.connect(STORE)
    optb = sqlite3.connect(OPTION_B_RS)
    result: dict = {"engine": e.name}
    try:
        t0 = time.perf_counter()
        result["load"] = load_all(e, store, optb)
        result["load"]["total_wall_s"] = round(time.perf_counter() - t0, 2)
        print(e.name, "loaded", result["load"])
        avg_dl = float(e.fetch(f"SELECT avg_dl FROM bm25b_stats WHERE epoch = {EPOCH_B}")[0][0])
        allow_lits = ", ".join(e.id_lit(i) for i in allow_ids)
        ext_scope = scope_ext_ids(ext)
        allow_scope = scope_allow_ids(allow_lits)
        # Scope-set fetch cost on its own (query-independent; a client could cache it per epoch).
        result["scope_fetch"] = {}
        for label, sql in (("ext", ext_scope), ("allow", allow_scope)):
            ms, rows = timed(lambda: e.fetch(sql), reps)
            result["scope_fetch"][label] = {"ms": ms, "chunk_ids": len(rows)}
        per_query: list[dict] = []
        for arity, qs in queries.items():
            for terms in qs:
                q: dict = {"arity": arity, "terms": terms}
                # S1
                q["a_s1_ms"], rows = timed(lambda: e.fetch(a_s1(e, terms)), reps)
                a_top = round_top([(int(c), float(s)) for c, s in rows])
                q["b_s1_fetch_ms"], (idfs, blocks) = timed(lambda: b_fetch(e, terms), reps)
                q["b_s1_score_ms"], (b_top, ncand) = timed(lambda: score_full_batched(blocks, idfs, avg_dl), reps)
                q["b_s1_total_ms"] = q["b_s1_fetch_ms"] + q["b_s1_score_ms"]
                q["b_s1_fetch1_ms"], (idfs1, blocks1) = timed(lambda: b_fetch_joined(e, terms), reps)
                assert sorted(blocks1) == sorted(blocks) and idfs1 == idfs
                q["b_s1_total1_ms"] = q["b_s1_fetch1_ms"] + q["b_s1_score_ms"]
                q["blocks"], q["candidates"], q["blob_bytes"] = len(blocks), ncand, sum(len(b[5]) + len(b[6]) + len(b[7]) for b in blocks)
                q["agree_s1"] = a_top == round_top(b_top)
                q["tau_s1"] = kendall_tau([i for i, _ in a_top], [i for i, _ in b_top])
                # S3 ext
                q["a_s3_ms"], rows = timed(lambda: e.fetch(a_s3(e, terms, ext)), reps)
                a3 = round_top([(int(c), float(s)) for c, s in rows])

                def b3_client():
                    idfs, blocks = b_fetch(e, terms)
                    allow = np.fromiter((int(r[0]) for r in e.fetch(ext_scope)), dtype=np.int64)
                    return score_full_batched(blocks, idfs, avg_dl, allow=allow)[0]

                q["b_s3_client_ms"], b3c = timed(b3_client, reps)
                q["agree_s3_client"] = a3 == round_top(b3c)

                def b3_semi():
                    idfs, blocks = b_fetch(e, terms)
                    return b_semijoin(e, blocks, idfs, avg_dl, ext_scope)

                q["b_s3_semi_ms"], (b3s, probes) = timed(b3_semi, reps)
                q["b_s3_semi_probes"] = probes
                q["agree_s3_semi"] = a3 == round_top(b3s)
                # S5 allow-list
                q["a_s5_ms"], rows = timed(lambda: e.fetch(a_s5(e, terms, allow_lits)), reps)
                a5 = round_top([(int(c), float(s)) for c, s in rows])

                def b5_client():
                    idfs, blocks = b_fetch(e, terms)
                    allow = np.fromiter((int(r[0]) for r in e.fetch(allow_scope)), dtype=np.int64)
                    return score_full_batched(blocks, idfs, avg_dl, allow=allow)[0]

                q["b_s5_client_ms"], b5c = timed(b5_client, reps)
                q["agree_s5_client"] = a5 == round_top(b5c)

                def b5_semi():
                    idfs, blocks = b_fetch(e, terms)
                    return b_semijoin(e, blocks, idfs, avg_dl, allow_scope)

                q["b_s5_semi_ms"], (b5s, probes) = timed(b5_semi, reps)
                q["b_s5_semi_probes"] = probes
                q["agree_s5_semi"] = a5 == round_top(b5s)
                per_query.append(q)
            print(e.name, "arity", arity, "done")
        result["queries"] = per_query
        keys = [k for k in per_query[0] if k.endswith("_ms")]
        summary = {}
        for arity in (1, 3, 6):
            rows = [q for q in per_query if q["arity"] == arity]
            summary[arity] = {k: statistics.median(q[k] for q in rows) for k in keys}
            summary[arity]["agree"] = {k: sum(q[k] for q in rows) for k in per_query[0] if k.startswith("agree_")}
            summary[arity]["min_tau_s1"] = min(q["tau_s1"] for q in rows)
            summary[arity]["semi_probes_max"] = max(max(q["b_s3_semi_probes"], q["b_s5_semi_probes"]) for q in rows)
        result["summary"] = summary
    finally:
        if not keep:
            for t in TABLES:
                e.drop(t)
        e.close()
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="pg,my,ms,or")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    store = sqlite3.connect(STORE)
    queries = draw_queries(store, EPOCH_A)
    assert all(t.isascii() for qs in queries.values() for q in qs for t in q), "non-ASCII query term; literal inlining would need N'' care on MSSQL"
    ext = "c"
    rng = random.Random(7)
    chunked = [bytes(r[0]) for r in store.execute("SELECT entry_id FROM vfs WHERE chunked AND deleted_at IS NULL ORDER BY entry_id")]
    allow_ids = rng.sample(chunked, 500)
    for key in args.engines.split(","):
        result = bench_engine(key, args.reps, queries, ext, allow_ids, args.keep)
        out = dump_json(f"engine_{result['engine']}.json", {"reps": args.reps, "ext": ext, "allow_entries": len(allow_ids), **result})
        print(result["engine"], "summary", result.get("summary"), out)


if __name__ == "__main__":
    main()
