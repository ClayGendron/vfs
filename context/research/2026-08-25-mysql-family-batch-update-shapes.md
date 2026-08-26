# MySQL-family batch UPDATE shapes — spec 080's research questions, answered live

- **Date:** 2026-08-25
- **Method:** executed experiments against MySQL 8.4.10 and MariaDB
  11.4.13 in Docker (`docker/compose.test.yml`; the `mariadb` profile
  was added for this study), on the real vfs schema minted in a fresh
  namespace per run. Scripts and every run's JSON under
  `studies/2026-08-25-set-based-topology-statements/`
  (`mysql_update_shapes.py`, `results/mysql-shapes-*.json`). Driver
  facts cited from the installed pymysql 2.2.8 / aiomysql 0.3.2 and the
  sibling `sqlalchemy` checkout.
- **Feeds:** spec 080 (design waits on this memo); spec 102's MySQL
  spelling (the companion memo,
  `2026-08-25-set-based-scattered-delete.md`).

## The finding under study, re-confirmed at the source

`pymysql.cursors.Cursor.executemany` matches the statement against
`RE_INSERT_VALUES`; on a match it packs rows into one multi-row
INSERT/REPLACE, otherwise it is literally
`self.rowcount = sum(self.execute(query, arg) for arg in args)` — one
round trip per row. `aiomysql.cursors.Cursor.executemany` is the same
regex and the same loop. An UPDATE never matches, so the guarded
aggregate arm and the unguarded absorb executemany both cost one
driver round trip per staged row on this family.

## Q1 — rowcount semantics: FOUND_ROWS, always on under SQLAlchemy

- SQLAlchemy's mysql dialects OR `CLIENT.FOUND_ROWS` into the client
  flags at connect (`dialects/mysql/mysqldb.py:242–261`;
  `aiomysql.py:240` returns `CLIENT.FOUND_ROWS`). Measured:
  `dialect._found_rows_client_flag()` is `2` on both members.
- Executed on both members with a matched-but-unchanged UPDATE
  (`SET version = version` on one row):

  | connection | rowcount |
  |---|---|
  | SQLAlchemy session (flag set by the dialect) | **1** (matched) |
  | raw aiomysql, default `client_flag=0` | **0** (affected) |
  | raw aiomysql, `client_flag=CLIENT.FOUND_ROWS` | **1** (matched) |

- **The semantic the set-based arm needs is *matched*:** "every guard
  matched" is a row-matched question, and FOUND_ROWS is exactly that.
  Today matched == affected anyway because the guard always writes
  `version + 1`, but the dependency is now explicit: the arm counts
  matched rows, SQLAlchemy sets the flag, and a pin should assert one of
  the two — cheapest is a conformance row on the family legs asserting
  that a matched-unchanged UPDATE reports rowcount 1 (the raw-driver
  probe above is the negative control that proves the row has teeth).

## Q2 — the statement shape: a UNION ALL derived table in a multi-table UPDATE

Three shapes were built with SQLAlchemy Core and timed over the same
corpus, each in its own transaction, each verifying afterwards that
every row's version rose by exactly one:

| shape | binds/row | 1k MySQL | 1k MariaDB | 10k MySQL | 10k MariaDB |
|---|---|---|---|---|---|
| per-row executemany (today) | 5 | 0.355 s | 0.349 s | 4.054 s | 4.719 s |
| **UNION ALL derived-table join** | 3 | 0.131 s | 0.085 s | **1.068 s** | **1.162 s** |
| CASE-keyed guard over an IN list | 3 | 0.044 s | 0.043 s | 1.195 s | 1.093 s |

Both set-based shapes ran as **one statement per 10,900 rows** (the
member profiles' `parameter_budget // 3`), so 10k rows was one round
trip against the loop's 10,000. Rowcount summed to N in every run.

**The join shape SQLAlchemy renders** (from `update(entry).where(entry.c.entry_id == v.c.v_id, entry.c.version == v.c.v_base, entry.c.path == v.c.v_path).values(...)` with `v = union_all(select(literal…)…).subquery("v")`):

```sql
UPDATE t, (SELECT %s AS v_id, %s AS v_base, %s AS v_path
           UNION ALL SELECT %s AS v_id, %s AS v_base, %s AS v_path …) AS v
SET t.version = (v.v_base + %s), t.updated_at = %s
WHERE t.entry_id = v.v_id AND t.version = v.v_base AND t.path = v.v_path
```

The mysql compiler renders the extra FROM as the family's native
multi-table `UPDATE t, v` (`update_tables_clause`;
`render_table_with_column_in_update_from = True` in
`dialects/mysql/base.py`); no `UPDATE … FROM` and no dialect-specific
construct is needed. Identical text on both members.

**Why the UNION ALL and not a VALUES table:** MySQL 8 spells a table
value constructor as `VALUES ROW(…)`, which SQLAlchemy's `values()`
does not render for the mysql dialect; MariaDB accepts bare
`VALUES (…)` but with its own column-naming rules. One family shape
was the requirement (spec 080 Q4), and the UNION ALL derived table is
the one both members execute unchanged. (The VALUES forms were not
executed — recorded as the reason for the choice, not as a measurement.)

**Why the join shape over the CASE shape:** at 10k they are within
noise of each other, but the CASE shape as timed guards on `version`
only. Spec 079's address proof needs `path = path-at-snapshot` in the
guard too, which in the CASE spelling is a second CASE expression (5
binds/row, two 10k-arm CASEs for the optimizer to evaluate per row);
the join carries the path tuple natively at 3 binds/row. The join is
also the shape spec 102's reparent uses, so one spelling serves both.

**Bind width for chunking:** 3 binds per row for the guarded material
update as timed here (id, base version, path); the real arm adds the
clobber columns, so the width is `3 + len(_CLOBBER_COLUMNS)` and the
chunk is `statement_budget(...)` off the compiled construction, exactly
as the VALUES arm does today — no new budget constant.

## Q3 — attribution on mismatch: savepoint rollback, per-row redrive, exact blame

Executed on both members at 1,000 rows with one row's version bumped
behind the batch's back:

- the UNION ALL join reported aggregate rowcount **999** of 1,000;
- `begin_nested()` → rollback left every other row's version untouched
  (verified by re-reading all 1,000 — `True` on both members);
- the per-row redrive over the same 1,000 rows reported rowcount 0 for
  exactly `/d00050/f000500.txt`, the row that was bumped.

So the existing `_guarded_by_aggregate` flow transfers unchanged: one
set-based statement per chunk under a savepoint, `rowcount == N` proves
the chunk, a miss rolls the savepoint back and hands the chunk to
`_guarded_by_rowcount`. Under REPEATABLE READ the family's declared
`guard_miss="redrive"` still applies to the classification step — this
study only proves the mechanics of the fallback, which the redrive-mode
dialect short-circuits anyway.

## Q4 — both members, real engines

- Dialect resolution: `mysql+aiomysql://` → `dialect.name == "mysql"`,
  profile `mysql`; `mariadb+aiomysql://` → `dialect.name == "mariadb"`,
  `is_mariadb=True`, profile `mariadb`. The README's "rides the same
  policy under its own dialect name" is true and the study exercised it.
- The `mysql`-marked conformance leg run against MariaDB 11.4 through
  the `mariadb+aiomysql://` URL: **211 passed, 4 skipped** — identical
  to the MySQL 8.4 leg the same session.
- Every number in this memo was produced on both members.

## Recommendation for spec 080's design

1. Add a mysql-family rung to `_update_materials`' ladder ahead of the
   executemany aggregate: the UNION ALL derived-table multi-table
   UPDATE, guarded on `(entry_id, version, path)`, chunked by
   `statement_budget`, verified by aggregate rowcount == N under a
   savepoint; on mismatch, the existing per-row floor. The unguarded
   absorb arm takes the same join without the version predicate.
2. Select the rung by capability, not name: "the dialect renders a
   multi-table UPDATE and lacks `update_returning_multifrom`" is the
   honest predicate (Postgres/MSSQL keep the VALUES+RETURNING arm;
   Oracle keeps array DML, which is already one round trip per chunk).
3. Pin FOUND_ROWS with a family-leg conformance row (matched-unchanged
   UPDATE reports 1) rather than a runtime assert — the flag is set by
   SQLAlchemy, not by vfs, and the row fails the day that changes.
4. Correct plan.md 079's "one executemany regardless of N" to name the
   per-family shapes: VALUES join (Postgres/MSSQL), UNION ALL join
   (mysql family), array DML (Oracle), per-row rowcount (SQLite).
5. Expected effect at the 10k ETL contract: ~4× on the guarded overwrite
   batch's UPDATE phase on both members, and the REPEATABLE READ lock
   window shrinks with it.
