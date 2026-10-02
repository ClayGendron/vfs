"""Spec 058's performance gate: the shipped resolver and compiler against S1's literal form.

S1 (``../2026-09-05-permissions-predicate-at-scale/``) measured the read
predicate as hand-written SQL. This script loads S1's exact corpus into
S1's lean entry table, then builds the same caller's predicate with the
code vfs ships: ``vfs.storage.grants.resolve`` for the rights and
``vfs.storage.backends.database.rights.visibility_clauses`` for the SQL.
It times two shapes S1 timed, each against S1's ``literal_like``:

- the grep pass: files in a size band, filtered by the predicate;
- the ranked join-back: 1,000 candidate ids, chunked by the membership
  budget, filtered by the predicate.

The gate (spec 058, acceptance): the shipped form stays within 1.5x of
the literal form. A group-shaped caller (rights through memberships) is
timed beside it for the record; S1 has no literal form for it.

    VFS_TEST_POSTGRES_URL=... uv run --no-sync python gate.py --engine postgres --files 75000 --reps 5

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import statistics
import sys
import time
from typing import Any

from sqlalchemy import and_, or_, select

HERE = os.path.dirname(os.path.abspath(__file__))
S1 = os.path.join(HERE, "..", "2026-09-05-permissions-predicate-at-scale")
sys.path.insert(0, S1)

import corpus as C  # noqa: E402
from common import Bench  # noqa: E402
from probe import GREP_LO, GREP_HI, filters, joinback, p_literal, select as s1_select  # noqa: E402

from vfs.storage.backends.database.dialects import chunked  # noqa: E402
from vfs.storage.backends.database.rights import visibility_clauses  # noqa: E402
from vfs.storage.grants import GrantRow, resolve  # noqa: E402

LEVEL = {"read": "read", "write": "read_write", "admin": "read_write"}
GATE = 1.5


def rows_for(corpus: C.Corpus, table: list[tuple[str, str, str]], ids: set[str]) -> list[GrantRow]:
    """The caller's rows in the shipped shape, under a private root (no everyone arm)."""
    rows = [GrantRow(p, pf, LEVEL[lvl]) for p, pf, lvl in table if p in ids]
    return [GrantRow("*", "/", "none"), *rows]


async def time_core(b: Bench, statements: list[Any], reps: int) -> tuple[float, int]:
    """Median ms over *reps* warm runs of *statements* as one logical query; rows of the first run."""
    assert b.conn is not None
    samples: list[float] = []
    rows = 0
    for r in range(reps + 1):
        t0 = time.perf_counter()
        seen: set[int] = set()
        for stmt in statements:
            seen.update(row[0] for row in (await b.conn.execute(stmt)).fetchall())
        dt = (time.perf_counter() - t0) * 1000
        await b.conn.rollback()
        if r == 0:
            rows = len(seen)
            continue
        samples.append(dt)
    return statistics.median(samples), rows


async def run(engine: str, n_files: int, reps: int) -> None:
    corpus = C.build(n_files)
    rng = random.Random(7)
    owners = corpus.owner_rows
    grants_per: dict[str, int] = {}
    for p, _, _ in corpus.grant_flat:
        grants_per[p] = grants_per.get(p, 0) + 1
    typ = sorted(p for p, k in owners.items() if 100 <= k <= 400 and grants_per.get(p, 0) >= 8)[0]
    file_ids = [e[0] for e in corpus.entries if e[3] == "file"]
    candidates = sorted(rng.sample(file_ids, 1000))
    report: list[str] = []

    async with Bench(engine, S1) as b:
        print(f"[{engine}] loading {len(corpus.entries):,} rows ...", flush=True)
        await b.load(corpus, [])
        entry = b.t["entry"]
        grep_filter = and_(
            entry.c.kind == "file", entry.c.size_bytes.between(GREP_LO, GREP_HI), entry.c.deleted_at.is_(None)
        )

        # The flat caller: S1's typical principal, its own rows plus the everyone rows expanded.
        flat = resolve({typ: frozenset()}, rows_for(corpus, corpus.grant_flat, {typ}), "read")
        # The group caller: the same principal through S1's groups form.
        groups = frozenset(corpus.groups_of[typ])
        grouped = resolve({typ: groups}, rows_for(corpus, corpus.grant_g, {typ, *groups}), "read")

        literal = p_literal(b, corpus, typ, "like")
        tpl, fp = filters(b, corpus, rng)["grep"]
        lit_grep = await b.timeit(s1_select(b, tpl.format(e="e"), literal), {**fp, **literal.params}, reps)
        stmts, _ = joinback(b, candidates, literal, "in")
        lit_back = await b.timeit(stmts, reps=reps)
        report.append(f"literal_like: grep {lit_grep.median_ms:.1f} ms ({lit_grep.rows} rows), "
                      f"join-back {lit_back.median_ms:.1f} ms ({lit_back.rows} rows), {literal.binds} binds")

        for label, rights in (("shipped flat", flat), ("shipped groups", grouped)):
            clauses = visibility_clauses(entry, rights, b.profile, b.parameter_budget)
            assert clauses is not None and clauses, label
            grep = [select(entry.c.id).where(grep_filter, clause.predicate) for clause in clauses]
            spend = max(clause.binds for clause in clauses)
            chunk = max(1, min(b.membership_budget, b.parameter_budget - 32 - spend))
            back = [
                select(entry.c.id).where(entry.c.id.in_(list(part)), clause.predicate)
                for clause in clauses
                for part in chunked(candidates, chunk)
            ]
            g_ms, g_rows = await time_core(b, grep, reps)
            j_ms, j_rows = await time_core(b, back, reps)
            arms = len(rights.arms) + sum(len(a.prefixes) for a in rights.owner_arms)
            line = (f"{label}: grep {g_ms:.1f} ms ({g_rows} rows), join-back {j_ms:.1f} ms ({j_rows} rows), "
                    f"{len(clauses)} clause(s), {arms} arms")
            if label == "shipped flat":
                assert g_rows == lit_grep.rows and j_rows == lit_back.rows, "the shipped form must admit what S1's does"
                ratio_g, ratio_j = g_ms / lit_grep.median_ms, j_ms / lit_back.median_ms
                verdict = "PASS" if max(ratio_g, ratio_j) <= GATE else "FAIL"
                line += f" — ratio grep {ratio_g:.2f}x, join-back {ratio_j:.2f}x vs literal: {verdict} (gate {GATE}x)"
            report.append(line)
            print(f"[{engine}] {line}", flush=True)

    os.makedirs(os.path.join(HERE, "runs"), exist_ok=True)
    out = os.path.join(HERE, "runs", f"{engine}-{len(corpus.entries)}.md")
    with open(out, "w") as f:
        f.write(f"## {engine} — {len(corpus.entries):,} entry rows, median of {reps} warm runs\n\n")
        f.write("\n".join(f"- {line}" for line in report) + "\n")
    print(f"[{engine}] → {out}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["sqlite", "postgres", "mssql", "oracle", "mariadb"])
    ap.add_argument("--files", type=int, default=75_000)
    ap.add_argument("--reps", type=int, default=5)
    a = ap.parse_args()
    asyncio.run(run(a.engine, a.files, a.reps))
