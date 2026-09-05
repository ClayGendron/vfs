# SQL Server membership reads — where `IN (...)` stops seeking, why the binds are `nvarchar`, and the form that fixes both

- **Status:** research memo — adopted by ADR 061 and implemented by spec 145 (2026-09-04)
- **Date:** 2026-09-04
- **Owner:** Clay Gendron
- **Method:** executed experiments against the live SQL Server 2025
  container (`docker/compose.test.yml`, RTM-CU8 17.0.4075.5, amd64
  under Rosetta — ratios and plan shapes are the evidence, absolute
  times are inflated): a seek→scan flip matrix over 20,000 / 200,000 /
  1,000,000-row entry tables × 8 list sizes × 7 bind-typing and key
  arms, all under `WITH (UPDLOCK)`; a code-page probe; a
  membership-forms matrix (chunked `IN`, `OPENJSON`, `VALUES`, TVP, temp
  table) at 2,067 / 10,000 / 20,000 keys with lock profiles; a TVP
  feasibility probe — all rerunnable from
  `studies/2026-09-04-mssql-membership-reads/`. A source trace through
  the installed SQLAlchemy 2.0.52, pyodbc 5.3.0 and aioodbc 0.5.0, cross-
  checked against the refreshed read-only `~/Git/Repos/sqlalchemy`
  clone (MIT, `origin/main` de83fa72d, 2026-09-04, clean). A census of
  the 45 `.in_(` sites in `src/vfs/storage/backends/database/`. Prior
  art from two parallel researchers: a web sweep of Microsoft's
  documentation and the SQL Server community (URLs in **Sources**),
  and a study of twelve refreshed, licence-checked read-only clones
  under `~/Git/Repos` — jackrabbit-oak (Apache-2.0, `origin/trunk`
  f26e243, 2026-09-04) and sqlalchemy (MIT, `origin/main` de83fa72d,
  2026-09-04) were the two with SQL Server-relevant code; opendal,
  filesystem_spec, pyfilesystem2, juicefs, seaweedfs, agentfs,
  libsqlfs, memori, letta and mem0 carry no SQL Server support
  (commits and licences in **Sources**). All clones were clean.
- **Question under evaluation:** on SQL Server, vfs's chunked
  membership reads (`path IN (...)`, `entry_id IN (...)`, 2,067
  elements per chunk) plan as a clustered index scan plus a giant
  filter instead of an index seek, and spec 144 just made the
  `mkedge` resolve a *locking* read — so the scan now escalates to a
  table-level exclusive lock per statement. Where is the flip, what
  drives it, why do the binds arrive as `nvarchar`, and which
  membership form should vfs adopt?

## Bottom line

1. **There is no fixed flip point — the optimizer costs seeks
   against one scan, and the answer moves with table size.** On
   20,000 rows the shipped form scans from 1,024 elements; on 200,000
   and 1,000,000 rows it seeks all the way to 2,067. Typed elements
   (no conversion) and the binary `entry_id` key flip *earlier* on
   small tables (256 at 20k, 1,280 at 200k, never at 1M) because their
   seeks are cheaper to run but a scan of a small table is cheaper
   still. Lowering `in_list_budget` cannot fix this: the scan appears
   exactly on the tables where it costs least, and every scan cell
   past ~1,000 elements is an optimizer `TimeOut` — it stopped
   searching, not chose.
2. **The scan's cost is the lock, not the time.** Under
   `WITH (UPDLOCK)` any scan takes an update lock on every row, and
   at 5,000 locks in one statement SQL Server escalates to a
   table-level `X` lock held to commit. Every scan cell in every
   matrix shows `OBJECT:X`; every seek cell shows two `KEY:U` per row
   and no escalation, even at 40,000 key locks in one transaction
   spread over 10–40 statements. The threshold is per statement, so
   the rule is: **a locking membership read must seek, and must lock
   fewer than ~2,500 rows per statement.**
3. **The binds are `nvarchar` because vfs asked for that, and for a
   good reason that still holds.** SQLAlchemy's pyodbc dialect *would*
   declare `String` binds as `SQL_VARCHAR` (the TypeDecorator is not
   in the way — measured), but `_engine_kwargs` passes
   `use_setinputsizes=False` on every `mssql` URL because a `varchar`
   bind is read in the *database's* code page: on `master`
   (CP-1252) it finds `café` and loses `日本語` and the emoji. Reproduced
   here: the stock engine returns 62 of 64 rows. A typed bind is
   lossless only on a database whose default collation is UTF-8
   (reproduced too: 64 of 64 on `vfs_utf8`). vfs cannot require that.
4. **The implicit conversion is an 8× tax on every seek, and a cliff
   for CJK.** With `nvarchar` binds the seek is the dynamic
   `Merge Interval → Index Seek` shape with a residual `Filter`:
   ~0.13 ms per element warm at 1M rows against ~0.016 ms typed. And
   **one CJK path in the list makes the seek's range swallow the
   table**: 63 ASCII paths plus `/n/日本語.py` took 200 ms on 20k rows,
   1.4 s on 200k, 6.8 s on 1M, and locked the whole table (`OBJECT:X`)
   at every size. Today a `mkdir`/`write`/`mkedge` batch naming one
   CJK path holds an exclusive table lock for its transaction.
   `FORCESEEK` does not help this form (46 s at 200k rows).
5. **Compile time is a third, separate cost.** A 2,067-element list
   compiles in 0.6–1.6 s (any typing; `TimeOut`), ~0.5 ms per element.
   Prepared plans are reused only for identical text, so every
   batch's remainder chunk compiles fresh. A form with one bind
   regardless of list length compiles once (5 ms) and never again.
6. **A `VALUES` derived table with the cast on the server is the
   form to adopt; `OPENJSON` ties on speed but carries a cardinality
   trap vfs would walk into.** Both forms are lossless (3 of 3
   canaries), typed (no conversion on the column), and resolve 2,067
   keys in 13–19 ms warm on 20k and 1M rows (vs 124 ms for the best
   shipped chunking and 4,060 ms for the shipped 2,067 chunk) and
   10,000 keys in 66–88 ms as five statements. `OPENJSON` compiles
   once (one bind, one text) where `VALUES` compiles per distinct
   length (~80 ms at 2,067 rows, 20× cheaper than the same `IN`
   list). But `OPENJSON` seeks *because* the optimizer estimates a
   constant 50 rows (7 in the `IN (SELECT ...)` spelling) whatever
   the array holds — harmless on a unique key (`path`, `entry_id`:
   one row per element, nothing downstream to misprice), and
   exactly the regression EF Core shipped (#32394) on non-unique
   columns, which vfs has (`parent_id` children listings, edges by
   `source_id`/`target_id`, `segments` and postings by term). A
   `VALUES` table has its true cardinality, so the optimizer's choice
   is honest on every column — which is also why it flipped to the
   hash scan on the 20k table and needs `FORCESEEK` on the locking
   reads (measured: with the hint, a seek at every size; 40,000 key
   locks in one transaction, no table lock). It is SQLAlchemy-native
   (`values()`), has no row cap as a derived table (a 2,067-row join
   was accepted; the 1,000 cap is `INSERT ... VALUES` only), and its
   2,100-bind cap coincides with the lock budget every locking read
   needs anyway (≤ 2,000 rows per statement so two key locks per row
   stay under the 5,000 trigger). Third: a table-valued parameter —
   it works from ad hoc SQL once pyodbc's `[type, schema, *rows]`
   convention is used and seeks (28 ms, lossless) because TVPs carry
   no statistics, but needs a `CREATE TYPE` per key type per table
   namespace and a driver-only parameter shape.

## The reads today — a census of the 45 sites

`grep -rn "\.in_(" src/vfs/storage/backends/database/` finds 45
sites. Classified by what the bind is and how big the list gets:

| class | sites | count |
|---|---|---|
| path (`BytewiseString`), chunk scale | `edges.py:396` (**locking**, mkedge resolve), `descent.py:62` (ancestor classify), `descent.py:128` (`rows_by_path` — every write/edit/read batch) | 3 |
| other string keys (`BytewiseString`), query-sized lists | `glean.py:427` term, `lexical.py:123` term, `pathterms.py:257` segment | 3 |
| small enum strings | `reads.py:285` ext, `reads.py:303` kind | 2 |
| plain `String(64)` (database-default collation, unindexed), chunk scale | `embed.py:197` content_hash | 1 |
| binary(16) keys (`ULIDKey`), chunk scale | `edges.py:121,124,340` (**locking**),`437`; `segments.py:125,131,209` (**locking**),`224`; `glean.py:653`; `writes.py:658,808,858,916`; `reads.py:352,498`; `topology.py:584,589,590,591,592,595,596,621`; `indexing.py:306,554` | 25 |
| row-value tuple (not rendered on mssql, `tuple_in=False`) | `indexing.py:654` | 1 |
| integer keys | `edges.py:356`; `embed.py:203`; `glean.py:386,441,496,576,757`; `grep.py:472,487,519` | 10 |

Three facts follow. The conversion tax and the CJK cliff touch only
the string-key classes (8 sites), and only the three `path` sites
reach chunk scale. The scan-and-escalate problem touches **every**
chunk-scale class, string or binary — the binary key flipped to a
hash scan at 256 elements on the 20k table. And the three locking
sites (`edges.py:340,396`, `segments.py:209`) are the ones spec 144
just made lock-sensitive; the 25 binary sites include the delete
cascades in `topology.py`, which take `X` row locks by nature and
escalate at the same threshold.

## Where the seek→scan flip is, and what drives it

Three things drive the plan, and they are separable. Say it plainly:
the flip is a **cost decision that moves with table size**; the
implicit conversion is a **separate tax that makes every seek slower
and one class of values catastrophic**; and the compile time of a long
list is a **third cost that neither of the first two explains**.

### The flip moves with table size (it is the optimizer's cost model)

Seek-or-scan by list size, plain `WITH (UPDLOCK)` reads, the vfs
engine as shipped, an all-ASCII list (`nvarchar-ascii` arm):

| rows | 64 | 256 | 512 | 768 | 1,024 | 1,280 | 1,536 | 2,067 |
|---|---|---|---|---|---|---|---|---|
| 20,000 | seek | seek | seek | seek | **scan** | scan | scan | scan |
| 200,000 | seek | seek | seek | seek | seek | seek | seek | seek |
| 1,000,000 | seek | seek | seek | seek | seek | seek | seek | seek |

The same with the conversion removed (the `cast` arm) and with the
binary key (`entry_id`, which never converts):

| rows | 64 | 256 | 512 | 768 | 1,024 | 1,280 | 1,536 | 2,067 |
|---|---|---|---|---|---|---|---|---|
| 20,000 | seek | **scan** | scan | scan | scan | scan | scan | scan |
| 200,000 | seek | seek | seek | seek | seek | **scan** | scan | scan |
| 1,000,000 | seek | seek | seek | seek | seek | seek | seek | seek |

So there is no fixed list-size threshold. A scan is chosen when the
optimizer's estimated cost of *N* seeks (each a Merge Interval seek
plus a clustered key lookup) exceeds one pass over the table. A small
table makes the scan cheap, so the flip comes early; at a million rows
the scan is never cheaper than 2,067 seeks. That is the opposite of
what a fixed budget assumes: **the tables where vfs scans today are
the small ones**, where the scan itself costs little — the damage on
them is not the scan's time but its lock (below).

Two details from the plans. Every scan cell above ~1,000 elements
carries `StatementOptmEarlyAbortReason="TimeOut"`: the optimizer ran
out of its search budget before it finished, so past that point the
plan is whatever it had, not the best it could find. And the scan
shape differs by typing: with the conversion present the scan is
`Clustered Index Scan → Filter` — the `Filter` evaluates the whole
`IN` list against every row, O(rows × list), which is why 2,067
elements on 20,000 rows took 4–6 s; with typed elements it is
`Hash Match(Clustered Index Scan, Constant Scan)`, O(rows + list),
20–30 ms on the same table.

### The implicit conversion is a tax on every seek, and a cliff for CJK

`ParameterDataType` in every default-arm plan is `nvarchar(...)`;
`path` is `varchar(1024) COLLATE Latin1_General_100_BIN2_UTF8`.
Data-type precedence converts the *column*, so the seek is the
dynamic `GetRangeThroughConvert` shape: `Constant Scan → Merge
Interval → Index Seek` with a residual `Filter`. It seeks, but at
several times the cost of a typed seek — warm times at 1,000,000
rows, per element, ASCII lists:

| form | 256 | 1,024 | 2,067 | per element |
|---|---|---|---|---|
| shipped nvarchar (converted) | 13 ms | 81 ms | 282 ms | ~0.13 ms |
| `cast` (typed, lossless) | 6 ms | 17 ms | 33 ms | ~0.016 ms |
| `entry_id` (binary) | 6 ms | 20 ms | 36 ms | ~0.017 ms |

About 8× per element — and it gets worse with the list because the
residual `Filter` costs list-length per candidate row.

The cliff: one CJK path in the list changes the plan's *range*. With
`/n/日本語.py` among 63 ASCII paths the "seek" locked the entire table
(`OBJECT:X`, a table-level exclusive lock through escalation) and took
200 ms on 20,000 rows, 1.4 s on 200,000, 6.8 s on 1,000,000 — linear in
table size, i.e. a full range scan with the `IN` filter applied to
every row. `/n/café.py` (Latin-1) and the emoji (a surrogate pair)
did not do this. The mechanism: the range computed for the converted
value swallows the table, then the residual filter costs O(rows ×
list). Consequence for `mkedge` today: a batch that names one CJK
endpoint locks the whole entry table exclusively, for the transaction's
lifetime, regardless of chunk size.

### Compile time is the third cost, and it is per statement text

`CompileTime` scales with list length: ~12 ms at 64, ~200 ms at 1,024,
600–1,600 ms at 2,067, on every arm (typed or not; `TimeOut` on most
2,067-element plans). A prepared plan is reused only for an identical
statement text, so a batch's full-size chunks share one compile per
table and length, but the *remainder* chunk of every batch has its own
length and compiles fresh — a 1,000-element remainder pays ~0.3 s
before it executes, every call. This cost is invisible in the warm
column and dominates the cold one; a form with one bind regardless of
list length (OPENJSON, below) compiles once, ever.

### What `FORCESEEK` does and does not buy

`FORCESEEK` on the shipped nvarchar form (`forceseek` arm) forces the
converted seek at every size — and the converted seek with canaries is
the slow, table-locking shape just described, so at 2,067 elements it
took 4.3 s (20k rows) and 46 s (200k). Useless alone. On the typed
`cast` form (`cast-forceseek`) it is exactly the tool it should be: a
seek at every size on every table, 32–39 ms warm for 2,067 elements,
4,134 `KEY:U` locks (two per row: the path index key and the clustered
key) and no escalation.

Full matrix (every cell, every arm) in the study README.

## Bind typing — why the binds arrive as nvarchar (source trace)

Read in the installed SQLAlchemy 2.0.52 (the one that runs) and
cross-checked against the refreshed clone at `origin/main` de83fa72d
(2.1 dev, 2026-09-04, MIT); line numbers are the installed copy's
unless marked.

1. **pyodbc's default for a Python `str` is `SQL_WVARCHAR`** — an
   `nvarchar` parameter — unless `cursor.setinputsizes()` says
   otherwise. This is what the plan's `ParameterDataType="nvarchar(24)"`
   reflects.
2. **SQLAlchemy's mssql+pyodbc dialect does know better.** It maps
   `String` to `_String_pyodbc`, whose `get_dbapi_type` returns
   `SQL_VARCHAR` (`dialects/mssql/pyodbc.py:525-530`; clone `:521`),
   and it defaults `use_setinputsizes=True` (`pyodbc.py:662-665`), which
   sets `bind_typing = SETINPUTSIZES` (`connectors/pyodbc.py:51-54`).
3. **The TypeDecorator is not the problem.** For an expanding
   `IN` parameter, `_get_set_input_sizes_lookup`
   (`sql/compiler.py:1989-2025`; clone `:2062`) calls
   `typ._unwrapped_dialect_impl(dialect).get_dbapi_type(dbapi)`;
   `_unwrapped_dialect_impl` (`sql/type_api.py:1880-1897`; clone
   `:1952`) sees `BytewiseString` is still a TypeDecorator after
   dialect adaptation and follows `load_dialect_impl` to the
   `String(1024, collation=...)` it returns for mssql, which adapts to
   `_String_pyodbc`. Measured: the lookup for the vfs `path IN (...)`
   statement returns `{path: 12}` — `12` is `pyodbc.SQL_VARCHAR`.
   `_prepare_set_input_sizes` (`engine/default.py:2073-2170`; clone
   `:2312`) then fans that one entry out to every expanded name
   (`if key in self._expanded_parameters`, `:2133`; clone `:2372`).
4. **vfs switches it off on purpose.** `_engine_kwargs` in
   `src/vfs/storage/backends/database/engine.py:529-546` passes
   `use_setinputsizes=False` for every `mssql` URL, so `bind_typing`
   stays `NONE`, `cursor.setinputsizes` is never called (measured: an
   aioodbc-level spy saw zero calls), and pyodbc's Unicode default
   wins. The reason, in the docstring and confirmed here: a
   `SQL_VARCHAR` bind is interpreted by the server in the *database's*
   default code page (CP-1252 on `master`), so any character outside
   it becomes `?` before the comparison — the "canaries" section
   below shows the stock engine finding only 1 of 3 non-ASCII paths.
5. **aioodbc changes nothing.** `dialects/mssql/aioodbc.py` subclasses
   `MSDialect_pyodbc`; aioodbc's cursor forwards `setinputsizes`
   straight to pyodbc in its worker thread (`aioodbc/cursor.py:148-162`).

So the binds are `nvarchar` because vfs chose lossless over typed, and
that choice is correct as far as it goes: the driver-side `varchar`
declaration cannot carry the column's UTF-8 collation, so it can
never be both typed and lossless on a database whose default
collation is not UTF-8.

### The experiment: what each bind typing finds, and what it costs

`codepage_probe.py`, 64-element lists on 20,000 rows, `WITH (UPDLOCK)`:

| database / bind | found | canaries | ms | plan | locks |
|---|---|---|---|---|---|
| `master` (CP-1252) / `varchar` — stock SQLAlchemy | 62 | 1 of 3 | 34 | seek, no filter | 124 KEY:U |
| `master` / `nvarchar` — vfs as shipped | 64 | 3 of 3 | 201 | seek + filter | **OBJECT:X** |
| `vfs_utf8` (UTF-8 default) / `varchar` — stock SQLAlchemy | 64 | 3 of 3 | 27 | seek, no filter | 128 KEY:U |
| `vfs_utf8` / `nvarchar` — vfs as shipped | 64 | 3 of 3 | 203 | seek + filter | **OBJECT:X** |

Read it twice. The lossy bind is fast and seeks cleanly; the lossless
bind is slow and locks the table (the list holds `日本語`). The database
collation, not the column collation, decides whether a `varchar` bind
is lossless. So "fix the bind typing" has exactly one lossless,
database-independent spelling: convert **on the server, after the
`nvarchar` value has arrived intact**, under the column's own
collation — `CAST(@p COLLATE Latin1_General_100_BIN2_UTF8 AS
varchar(1024))`. Measured (the `cast` arms): 3 of 3 canaries,
`convert=False` in the plan, `ParameterDataType` still `nvarchar`, and
the seek is the clean `Merge Interval → Index Seek` with no residual
`Filter`. There is no SQLAlchemy flag for this: `render_bind_cast`
only fires on `RENDER_CASTS` dialects (asyncpg, psycopg), so a
per-element cast on an expanding parameter would need a custom
construct — which is one reason the winning form below applies the
cast once, in a projection, instead of once per element.

## Alternative membership forms, measured

`forms_probe.py`: resolve K sorted paths (three of them the canaries,
except the `in-nvarchar` rows, which are all-ASCII because one CJK
element makes every shipped-form statement a table-range seek) to
`(path, entry_id)` inside one transaction under `WITH (UPDLOCK)`; time
the whole resolve; read the locks held before rollback. `stmts` is the
number of round trips. Warm = best of three runs.

**K = 2,067 (one vfs chunk today):**

| rows | form | stmts | cold ms | warm ms | compile ms | plan | locks | lossless |
|---|---|---|---|---|---|---|---|---|
| 20k | `in-nvarchar-2067` (shipped) | 1 | 5,549 | 4,060 | 1,452 | scan + Filter | **OBJECT:X** | (ASCII list) |
| 20k | `in-nvarchar-512` | 5 | 519 | 124 | 15 | seek + Filter | 4,134 KEY:U | (ASCII list) |
| 20k | `in-cast-512` | 5 | 149 | 53 | 7 | scan (hash) on the 512s | **OBJECT:X** | yes |
| 20k | `in-cast-2067` | 1 | 682 | 21 | 627 | scan (hash) | **OBJECT:X** | yes |
| 20k | `in-cast-fs-2067` (`FORCESEEK`) | 1 | 1,133 | 29 | 1,062 | seek | 4,134 KEY:U | yes |
| 20k | `openjson-2067` | 1 | 24 | **13** | 6 | seek (nested loops over the TVF) | 4,134 KEY:U | yes |
| 20k | `openjson-with` (`WITH (path varchar(1024))`) | 1 | 22 | 16 | 3 | seek | 4,130 KEY:U | **no** (1 of 3) |
| 20k | `values-2067` | 1 | 114 | 16 | 77 | scan (hash) | **OBJECT:X** | yes |
| 20k | `values-fs-2067` (`FORCESEEK`) | 1 | 121 | 13 | 84 | seek | 4,134 KEY:U | yes |
| 20k | `values-fs-1000` | 3 | 74 | 17 | 5 | seek | 4,134 KEY:U | yes |
| 20k | `temp-1000` (create, 3 inserts, join, drop) | 6 | 105 | 35 | 8 | scan (hash) | **OBJECT:X** + Sch-M | yes |
| 20k | `tvp` ad hoc `JOIN ? AS k` (`[type, schema, *rows]`) | 1 | — | 28 | 3 | seek (nested loops over the table variable, est 1) | 4,134 KEY:U | yes |
| 20k | `tvp` via `sp_executesql` READONLY / stored procedure | 1 | — | 27–31 | 2–3 | scan (hash), est 2,067 | **OBJECT:X** | yes |
| 1M | `in-nvarchar-2067` (shipped) | 1 | 1,930 | 267 | 1,615 | seek + Filter | 4,134 KEY:U | (ASCII list) |
| 1M | `in-nvarchar-512` | 5 | 538 | 126 | 16 | seek + Filter | 4,134 KEY:U | (ASCII list) |
| 1M | `in-cast-2067` | 1 | 699 | 30 | 631 | seek | 4,134 KEY:U | yes |
| 1M | `in-cast-fs-2067` | 1 | 1,403 | 30 | 1,337 | seek | 4,134 KEY:U | yes |
| 1M | `openjson-2067` | 1 | 22 | **16** | 5 | seek | 4,134 KEY:U | yes |
| 1M | `values-fs-2067` | 1 | 119 | 15 | 81 | seek | 4,134 KEY:U | yes |
| 1M | `temp-1000` | 6 | 86 | 31 | 6 | scan of `#k`, seek into the entry table | Sch-M + 4,134 KEY:U | yes |

**K = 10,000 (the ETL contract):**

| rows | form | stmts | cold ms | warm ms | plan | locks |
|---|---|---|---|---|---|---|
| 20k | `in-nvarchar-512` | 20 | 1,161 | 597 | seek + Filter | 20,000 KEY:U |
| 20k | `in-nvarchar-2067` (shipped) | 5 | 22,560 | — | scan + Filter | **OBJECT:X** |
| 20k | `in-cast-fs-2067` | 5 | 1,966 | 154 | seek | 20,000 KEY:U |
| 20k | `openjson-2067` | 5 | 75 | **72** | seek | 20,000 KEY:U |
| 20k | `openjson-10000` (one statement) | 1 | 61 | 56 | seek | **OBJECT:X** (escalated at 5,000) |
| 20k | `values-fs-2067` | 5 | 248 | 66 | seek | 20,000 KEY:U |
| 1M | `in-nvarchar-512` | 20 | 1,226 | 579 | seek + Filter | 20,000 KEY:U |
| 1M | `in-nvarchar-2067` (shipped) | 5 | 4,339 | 1,287 | seek + Filter | 20,000 KEY:U |
| 1M | `in-cast-fs-2067` | 5 | 2,464 | 103 | seek | 20,000 KEY:U |
| 1M | `openjson-2067` | 5 | 92 | **88** | seek | 20,000 KEY:U |
| 1M | `openjson-10000` (one statement) | 1 | 90 | 61 | seek | **OBJECT:X** |
| 1M | `values-fs-2067` | 5 | 258 | 71 | seek | 20,000 KEY:U |

What each form taught:

- **`OPENJSON` + cast projection.** The plan is `Sort → Table-valued
  function → Index Seek → Clustered Index Seek` with a fixed estimate
  (7.07 rows for the `IN (SELECT ...)` spelling, 50 for the `WITH`
  spelling) at every table size and list length. A low fixed estimate
  is normally a hazard; for a key lookup it is exactly right — nested
  loops of seeks is the plan we want, and no hint is needed to get it.
  One bind, so one compile ever (5 ms), and the statement text is the
  same for every chunk. The `WITH (path varchar(1024))` spelling is
  the code-page trap again: `WITH` converts with the database
  collation (1 of 3 canaries). The cast-in-projection spelling is
  lossless. Cost: `json.dumps` of the list client-side (10,000 paths
  is ~170 KB, sent as one `nvarchar(max)`).
- **`VALUES` + `FORCESEEK`.** SQLAlchemy renders `values()` natively
  and vfs already uses it for guarded updates. Without the hint the
  constant table's exact cardinality makes the optimizer pick the
  hash scan on small tables (20k: scan at 2,067 → `OBJECT:X`); with
  it, a clean seek everywhere. Compile is ~80 ms at 2,067 rows —
  20× cheaper than the same `IN` list, but still per statement text
  (the remainder chunk recompiles). Bound by the 2,100-parameter cap.
  Note: a 2,067-row `VALUES` *derived table* was accepted; the
  1,000-row cap bit `INSERT ... VALUES` (the temp-table form, error
  10738), not the join.
- **`IN` + per-element cast + `FORCESEEK`.** Seeks everywhere, 29–30
  ms warm, but 1.1–1.4 s compile at 2,067 — the `IN` list's parse and
  optimizer cost is per element regardless of typing. Usable, but
  strictly dominated.
- **Smaller `nvarchar` chunks.** At 512 the shipped form seeks on all
  three table sizes (ASCII lists), 124–126 ms per 2,067 keys, 580–600
  ms per 10,000 — 4× the round trips and ~7–9× the time of `OPENJSON`,
  and the CJK cliff remains at any chunk size. A mitigation, not a fix.
- **Temp table.** `CREATE TABLE #k` + paged `INSERT ... VALUES` (≤ 1,000
  rows each) + join + drop: real statistics, so the optimizer picks a
  hash or merge scan of the entry table because it *knows* there are
  2,067 keys — and that scan is the lock problem again (`OBJECT:X` at
  20k). Also two `Sch-M` locks per call and 6–23 statements. Not
  competitive.
- **Table-valued parameter.** pyodbc binds a TVP as a list of row
  tuples with the type name and schema prepended as two strings
  (`[typ, "dbo", (path,), ...]`); with that shape an ad hoc
  `JOIN ? AS k` works, 28 ms, lossless, and seeks — the table
  variable's estimate of 1 row drives nested-loops seeks with
  4,134 key locks and no escalation. Without the prefix, or through
  `sp_executesql` with a `READONLY` parameter or a stored procedure,
  it either fails ("Cannot find data type") or gets the exact row
  count (2,067) and scans under `OBJECT:X`. It needs a `CREATE TYPE`
  per key type per table namespace (owned by vfs DDL, dropped with
  the tables), a parameter shape no SQLAlchemy type can produce (so
  `exec_driver_sql` or a custom bind processor), and it is twice
  `OPENJSON`'s time. Viable, third.

## Lock escalation — what happens when 20,000 rows are locked in one transaction

`forms_probe.py --ks 20000` (the mkedge worst case: a 10,000-edge
batch locks up to 20,000 endpoint rows). Locks read from
`sys.dm_tran_locks` for the probe's SPID before rollback. The
`index_lock_promotion_*` counters of `sys.dm_db_index_operational_stats`
were unusable here: their deltas went negative whether read inside or
outside the transaction, and a direct check (three reads with nothing
between, then a full-table `WITH (UPDLOCK)` scan that visibly held
`OBJECT:X`) left them unchanged — so a table-level lock taken for a
scan is not counted as a "promotion" on this server, and the
20,000-key seek's table lock was not counted either. `OBJECT:X` in the
lock table is the signal that matters: a table-level exclusive lock
on the entry table, held to commit, whether the lock manager granted
it up front for the scan or escalated to it mid-statement.

| rows | form | stmts | warm ms | locks held at the end | escalated |
|---|---|---|---|---|---|
| 20k | `in-nvarchar-512` (ASCII) | 40 | 1,249 | 40,000 KEY:U + OBJECT:IX | no |
| 20k | `in-cast-fs-2067` | 10 | 350 | 40,000 KEY:U + OBJECT:IX | no |
| 20k | `openjson-2000` | 10 | 157 | 40,000 KEY:U + OBJECT:IX | no |
| 20k | `openjson-20000` (one statement) | 1 | 161 | **OBJECT:X** | **yes** |
| 20k | `values-fs-1000` | 20 | 183 | 40,000 KEY:U + OBJECT:IX | no |
| 20k | `temp-1000` | 23 | 192 | **OBJECT:X** + Sch-M | **yes** (scan) |
| 1M | `in-nvarchar-512` (ASCII) | 40 | 1,175 | 40,000 KEY:U + OBJECT:IX | no |
| 1M | `in-cast-fs-2067` | 10 | 208 | 40,000 KEY:U + OBJECT:IX | no |
| 1M | `openjson-2000` | 10 | 173 | 40,000 KEY:U + OBJECT:IX | no |
| 1M | `openjson-20000` (one statement) | 1 | 168 | **OBJECT:X** | **yes** |
| 1M | `values-fs-1000` | 20 | 180 | 40,000 KEY:U + OBJECT:IX | no |
| 1M | `temp-1000` | 23 | 187 | Sch-M + KEY:X (the `#k` rows); the join seeks here | no |

So the answer to "does the mkedge lock escalate?" is: **not when the
statement seeks and locks fewer than ~2,500 rows** (two key locks per
row — the `path` index key and the clustered key — stay under the
5,000-lock trigger), no matter how many such statements one
transaction issues (40,000 key locks in one transaction, zero
escalations). It escalates the moment one statement scans (any
`IN`-list flip; any temp-table join; today's CJK cliff) or seeks more
than ~2,500 rows (one 10,000- or 20,000-key `OPENJSON` statement). The
chunk size of a locking read is therefore a **lock budget** — a
declared per-dialect fact — and not a bind budget. `OPENJSON` has no
bind cap to hide behind, so the budget must be explicit.

## Prior art

### Microsoft's own documentation

- **The IN list is sugar for a chain of ORs, and the optimizer must
  cost each disjunct.** The `IN` reference says a list is equivalent
  to `col = a OR col = b ...` and warns that very large lists can
  exhaust resources and raise error 8623 (optimizer) or 8632
  (expression services); it recommends storing the values in a table
  instead. This is the documented root of the compile-time cost we
  measured (0.5–0.7 ms per element).
- **Long IN lists are a known plan-quality hazard, and the seek
  operator has a documented-by-the-community cap.** Hugo Kornelis's
  operator reference describes `Merge Interval` exactly as our plans
  show it: runtime values become intervals through `Constant Scan →
  Compute Scalar`, `Merge Interval` collapses overlaps, and a
  `Nested Loops` drives one `Index Seek` per interval. Paul White
  (answers.sqlperformance.com) adds two undocumented limits: at most
  15 residual predicates pushed into a seek and **at most 64 seek
  operations per seek operator** — beyond that a separate `Filter`
  appears, then the `Constant Scan + Nested Loops` shape; this is
  the residual `Filter` on every one of our converted-seek plans, and
  the reason 64 was the only list size at which the `cast` form
  seeked without a `Merge Interval` on the 20k table. An SQL
  Undercover measurement (2024) puts the literal-list flip near ~70
  values and shows both a literal list and a temp-table semi-join
  degrading to sort + merge join in the thousands; a million-value
  literal list fails outright. Microsoft's own 8623 troubleshooting
  post reports the error from a >10,000-entry `IN` and recommends a
  temp table. Paul White's dynamic-seek write-up explains the
  `Constant Scan → Merge Interval → Index Seek` shape we see up to the
  flip (Microsoft's operator reference documents `Merge Interval` as
  the operator that merges overlapping seek intervals): each element
  becomes a seek interval, the intervals are sorted and merged, and
  the seek runs once per interval. Past a cost
  threshold the optimizer prefers one scan with a residual `Filter`,
  and with a `TimeOut` early-abort it stops searching before it finds
  the seek plan at all (we see `StatementOptmEarlyAbortReason="TimeOut"`
  on every scan cell above ~1,000 elements).
- **Data-type precedence converts the column, not the parameter.**
  `nvarchar` outranks `varchar`, so an `nvarchar` parameter against a
  `varchar` column implicitly converts the column
  (`CONVERT_IMPLICIT` in every default-arm plan). On Windows
  collations the optimizer can still seek through the conversion
  (Jonathan Kehayias's write-up of `GetRangeThroughConvert`) — on the
  legacy `SQL_*` collations it cannot, and the same predicate scans
  unconditionally. vfs pins a Windows collation
  (`Latin1_General_100_BIN2_UTF8`), which is why the seek shape exists
  at all; the plain `String(64)` columns (`content_hash`) take the
  database default, `SQL_Latin1_General_CP1_CI_AS` on this server.
- **UTF-8 collations and code pages.** Microsoft's collation docs
  describe `_UTF8` collations (SQL Server 2019+) as `varchar` storing
  UTF-8, and the `CAST`/`CONVERT` docs state that `nvarchar → varchar`
  conversion uses the code page of the *target's collation*; a
  `varchar` parameter with no explicit collation takes the database
  default. That is exactly the lossy squeeze vfs's `_engine_kwargs`
  docstring describes and this study reproduces (a `varchar` bind
  finds `café` and loses `日本語` and the emoji on `master`; all three
  survive on a database created `COLLATE Latin1_General_100_BIN2_UTF8`).
- **OPENJSON, and its cardinality trap.** The `OPENJSON` reference documents both shapes: the
  default schema (`key`, `value`, `type` columns, `value` is
  `nvarchar(max)`) and the `WITH` schema, whose declared types are
  converted with the database default collation unless the column's
  collation is explicit. The plans captured here show the fixed
  estimate directly: `StatementEstRows` 50 for the `WITH` spelling
  and 7.07 for the `IN (SELECT ...)` spelling, regardless of the
  array's length — low enough that the optimizer picks nested-loops
  seeks, which is the behaviour we want for a key lookup and the
  reason we do not need `FORCESEEK` on that form. The trap is real
  and recorded in the field: EF Core 8 switched its `IN`-list
  translation to `OPENJSON` and issue dotnet/efcore#32394 reports
  millisecond queries turning into timeouts because the estimate is
  a constant 50 rows regardless of the array, which pushes the
  optimizer into nested-loops seeks on columns where each value
  matches many rows. `STRING_SPLIT` carries the same hard-coded 50
  (Aaron Bertrand's 2016 follow-up; Brent Ozar's 2020/2022 posts
  recommend splitting into a `#temp` table first, which gets
  statistics, and note table variables estimate 1 row). See the
  reconciliation in the recommendation.
- **STRING_SPLIT** is the other documented list idiom; it splits on
  a single character, so it is unsafe for paths (a path may contain
  any separator we could pick) and this study does not use it.
- **Table-valued parameters** require a user-defined table type
  (`CREATE TYPE ... AS TABLE`) and are declared `READONLY`; they are
  the documented way to send many rows in one round trip, and the
  same page states that "SQL Server does not maintain statistics on
  columns of table-valued parameters" — which is why the ad hoc TVP
  join here estimated 1 row and seeked while the `sp_executesql`
  spelling saw 2,067 and scanned. pyodbc's wiki documents passing one
  as a list of row tuples with the type name and schema prepended
  (a pyodbc 4.0.32 fix, issue #595); its examples are all
  stored-procedure calls, but the ad hoc `JOIN ?` form works with the
  same prefix (measured).
- **Table value constructors.** The reference is explicit: as a
  derived table "there is no limit to the number of rows"; the
  1,000-row cap (error 10738) applies to `INSERT ... VALUES` only —
  which is exactly what the probes saw (a 2,067-row `VALUES` join was
  accepted; the temp-table form's 2,000-row `INSERT` was refused).
  The binding cap on a `VALUES` join is therefore the 2,100
  parameters, not the row count.
- **Lock escalation.** The transaction-locking guide documents the
  threshold: escalation is attempted when a single statement holds
  at least **5,000 locks on one table or index** (and at 1,250-lock
  intervals thereafter), or when lock memory passes its limit;
  `ALTER TABLE ... SET (LOCK_ESCALATION = DISABLE|TABLE|AUTO)` and
  trace flags 1211/1224 change it; Microsoft's blocking-troubleshooting
  page adds that `ROWLOCK` does not prevent it and that batching and
  SARGable predicates do. Paul White's "Lock Escalation Threshold"
  series sharpens the trigger: part 1 shows the real condition is
  ≥ 5,000 HoBt locks held by *a single access method*, checked every
  1,250 locks, so escalation actually lands near 6,250; part 3 (with
  a db-berater post) covers `UPDLOCK`: the hint takes `IX` at table
  level and its `U` key locks count toward the threshold, so
  escalation under `UPDLOCK` yields a table-level **`X`** lock — the
  `OBJECT:X` in every escalated cell here. The threshold is **per
  statement / per access method** — locks accumulated over many
  statements in one transaction do not trigger it, which is exactly
  what the chunked-seek measurements show (40,000 `KEY:U` in one
  transaction, no table lock). `sys.dm_db_index_operational_stats`
  exposes `index_lock_promotion_attempt_count` and `_count`,
  cumulative per partition and reset when the metadata cache drops
  — a plausible reason the counters were unusable here.
- **2,100 parameters per statement** is the documented request cap
  (the "Maximum Capacity Specifications" page: parameters per
  user-defined function / stored procedure 2,100), which is where
  `insertmanyvalues_max_parameters = 2099` in SQLAlchemy's mssql
  dialect and vfs's `in_list_budget = 2_100` both come from.

### What the field does — jackrabbit-oak and SQLAlchemy

Read at f26e243 and de83fa72d respectively; described, never copied.

- **Oak's RDB document store batches with plain `IN` lists, at a
  fixed 2,048 keys per statement, on every engine.** `MAX_IN_CLAUSE
  = 2048` (`RDBJDBCTools.java:386-388`, overridable by system
  property, citing OAK-3843); reads and deletes partition their key
  sets by it and issue one `SELECT ... WHERE ID IN (...)` per
  partition (`RDBDocumentStoreJDBC.java:754-777`, `:137-160`). Oracle's
  1,000-element cap is handled *inside* the statement: the renderer
  splits one predicate into `(ID IN (?…1000) OR ID IN (?…1000) …)`
  (`RDBJDBCTools.java:330-380`, `:405-406`), so a 2,048-key statement
  stays one round trip; a single key renders as `ID = ?`. Bulk writes
  go 64 documents per transaction (`RDBDocumentStore.java:2191-2194`).
  No TVP, `OPENJSON`, temp table or `VALUES` join anywhere; the SQL
  Server entry (`RDBDocumentStoreDB.java:495-560`) overrides only DDL,
  `TOP`, a concat expression and a UTC-time query.
- **Oak sidesteps the `nvarchar`/collation problem by keying on
  bytes.** On SQL Server (and MySQL) the ID column is
  `varbinary(512)` (`RDBDocumentStoreDB.java:503-509`) — the Javadoc
  says it is for "databases that can not handle 512 character primary
  keys" (`RDBDocumentStore.java:132-134`) — and keys are bound with
  `setBytes` of the UTF-8 encoding (`RDBJDBCTools.java:410-416`), so no
  bind-type mismatch and no collation can touch key equality or
  order. Around it Oak is loud about collation: it requires text
  fields to collate by code point (`RDBDocumentStore.java:214-219`),
  reads `sys.databases.collation_name` at startup
  (`RDBCommonVendorSpecificCode.java:88-115`), warns on legacy `SQL_*`
  collations ("risk of performance degradation", OAK-8908,
  `RDBBlobStoreDB.java:82-89`), and runs a "broken DB collation?"
  range-query sanity check (`RDBDocumentStoreJDBC.java:466`). Its
  documented sample uses `sendStringParametersAsUnicode=true` — the
  JDBC equivalent of our `nvarchar` binds — which is tolerable there
  only because the keys are binary. vfs's `entry_id IN (...)` sites
  are already in Oak's position; its `path IN (...)` sites are the
  ones Oak's design deliberately does not have.
- **SQLAlchemy's only `IN` chunking is the ORM's selectin loader, at
  500** (`orm/strategies.py:2992`, `_chunksize = 500`), justified in
  the docs by Oracle's hard limit and "the size of the SQL string
  shouldn't be arbitrarily large"
  (`doc/build/orm/queryguide/relationships.rst:830-834`); Core's
  expanding `IN` never chunks (`sql/compiler.py:4228-4275`,
  `:2113-2275`, `:3508-3583`), and the SQL Server bind cap is modelled
  only for insertmanyvalues (`insertmanyvalues_max_parameters =
  2099`, `dialects/mssql/base.py:3159-3162`), not for `IN`. The stated
  reason string binds are typed at all is the seek: the 2.0 changelog
  (`doc/build/changelog/changelog_20.rst:8382-8392`) says
  `use_setinputsizes` defaults on "so that non-unicode string
  comparisons are bound by pyodbc to `pyodbc.SQL_VARCHAR` rather than
  `pyodbc.SQL_WVARCHAR`, allowing indexes against VARCHAR columns to
  take effect" — the exact tension this memo measures: SQLAlchemy
  chose the seek, vfs chose lossless, and neither default gives
  both on a non-UTF-8 database. Tuple-`IN` renders through `VALUES`
  only on SQLite (`tuple_in_values`, `dialects/sqlite/base.py:2188`).
  Nothing in SQLAlchemy uses TVPs, `OPENJSON` or temp tables.

### SQLAlchemy documentation and tracker

- The mssql+pyodbc dialect docs ("Setinputsizes Support") state
  that `use_setinputsizes=True` is the 2.0 default and that `String`
  binds are declared `SQL_VARCHAR`, `Unicode` binds `SQL_WVARCHAR`;
  the `do_setinputsizes` event is the documented hook to override
  per-type. The "expanding" bind-parameter docs describe the
  post-compile expansion vfs's `in_()` calls rely on. SQLAlchemy has
  no per-element render hook for pyodbc: `render_bind_cast` only
  fires on `RENDER_CASTS` dialects (asyncpg/psycopg), so a per-element
  `CAST(... COLLATE ...)` on an expanding parameter needs a custom
  construct, not a flag. Issue #8177 flipped `use_setinputsizes` to
  default-on for 2.0; discussion #8171 records why `SQL_WVARCHAR` had
  been the default ("in Python 3 all strings are Unicode") and
  introduces the `_String_pyodbc`/`_Unicode_pyodbc` split; discussion
  #10524 shows 1.3/1.4 users hitting `NVARCHAR` binds against
  `VARCHAR` columns with `cast(value, String(n))` as the workaround.
  No SQLAlchemy issue about expanding parameters missing
  setinputsizes typing was found — consistent with the trace above:
  they do not miss it. The pyodbc wiki says the same from the driver
  side ("Tips and Tricks by Database Platform": `nvarchar` parameters
  against `varchar` columns force index scans; fix with
  `setinputsizes([(pyodbc.SQL_VARCHAR, 255)])`) and documents that a
  Python 3 `str` is encoded UTF-16LE into `SQL_C_WCHAR` by default
  ("Unicode" page).

## Recommendation, ranked

Say the goal once more. A membership read on SQL Server must (a) find
every path, including non-Latin ones; (b) seek, on every table size,
at every list length, because a scan under `UPDLOCK` is a table lock;
(c) lock fewer than ~2,500 rows per statement; (d) not pay a fresh
half-second compile per chunk. Today's form fails (b) on small tables,
fails (b) and (c) for any list with a CJK path, and pays (d). Ranked
by measured cost, robustness across table sizes, and how much of vfs
each touches:

1. **Adopt a `VALUES`-derived-table membership form on mssql, behind
   one helper.** Add a dialect-owned `membership(column, values)` (in
   `dialects.py`, or a small `membership.py` beside it) that every
   `.in_(chunk)` site calls. On every engine but mssql it returns
   `column.in_(values)` unchanged. On mssql it returns
   `column.in_(select(<cast>(k.c.v)).select_from(values(...)))` — or
   the equivalent join — over SQLAlchemy's `values()` construct,
   where `<cast>` is chosen from the column's type:
   `CAST(v COLLATE Latin1_General_100_BIN2_UTF8 AS varchar(n))` for
   `BytewiseString` (the lossless, typed spelling measured here), the
   `_string` variant's collation for `ext`/`kind`, and no cast for
   `ULIDKey` (`varbinary` binds already match `binary(16)`) or
   integer keys. Declare it on the profile as a decision SQLAlchemy
   takes no position on (`membership: Literal["in_list", "values"]`,
   `"values"` on `MSSQL` only). **The locking reads add `FORCESEEK`**:
   `lock_rows` renders `WITH (UPDLOCK, FORCESEEK)` from a profile hint
   that names both — without it the constant table's honest
   cardinality produced the hash scan and the table lock on the 20k
   table. Non-locking reads take no hint: on a unique key the
   optimizer seeks wherever a seek is cheaper, and on the non-unique
   columns (`parent_id`, edge endpoints, segments, terms) an honest
   estimate is exactly what we want it to have. **Chunking stays**,
   and the mssql chunk becomes a declared *lock budget* of 2,000
   elements per statement (two key locks per row → 4,000, under the
   5,000 trigger with room for the fixed predicates), which is also
   under the 2,100-bind cap, so `membership_budget` keeps one number.
   Evidence: 13–17 ms per 2,067 keys warm on 20k and 1M rows
   (shipped: 4,060 ms and 267 ms; best shipped chunking: 124 ms);
   66–71 ms per 10,000 keys; 3 of 3 canaries; a seek at every size on
   the hinted locking reads; ~80 ms compile per distinct length;
   40,000 key locks in one transaction without a table lock.
   Touches: `dialects.py` (profile field, helper, budget, the
   two-hint `row_lock_hint`), the 38 chunk-scale `.in_(` sites routed
   through the helper (3 path, 25 binary, 10 integer — a mechanical
   edit; the 7 query-sized string/enum sites can follow or stay),
   and tests: a membership conformance test that includes the three
   canaries on every engine leg, and a plan-shape/lock test on the
   mssql leg.
2. **`OPENJSON` with the same server-side cast — for unique-key
   lookups only, if the per-length compile of `VALUES` shows up in
   production.** One `nvarchar(max)` bind, 5 ms compile once, the
   same 13–19 ms per 2,067 keys, and no hint needed because the
   optimizer estimates 50 rows (7 in the `IN (SELECT ...)` spelling)
   whatever the array holds. That constant is the reason to rank it
   second: on `path` and `entry_id` it cannot bite (one row per
   element, nothing downstream to misprice), but the helper would be
   shared by the non-unique memberships — `reads.py:498` (`parent_id`,
   children listing), `edges.py:121,124,437` and `topology.py:595,596`
   (`source_id`/`target_id`), `segments.py:125,131,224`
   (`segments.entry_id`), `indexing.py:306,554` (`chunks.entry_id`),
   `glean.py:427` and `grep.py:472,487` (postings by term / gram) —
   where a fixed 50-row guess is the EF Core #32394 regression
   waiting to happen (the optimizer seeks 50 times when a value
   matches thousands of rows). It would need a per-site opt-in
   ("this column is unique"), which is a second knob for a tie on
   speed. Keep it as the fallback, not the default.
3. **Interim mitigation only: lower the mssql `in_list_budget` to
   512.** Keeps the shipped form seeking on every table size for
   ASCII lists (124–126 ms per 2,067 keys, 4× the round trips), does
   nothing for the CJK cliff or the conversion tax, and still
   compiles per remainder. Worth doing today only if 1 or 2 cannot
   land before spec 144's lock ships; do not mistake it for the fix.
4. **Do not** enable `use_setinputsizes` (lossy on any non-UTF-8
   database), add `FORCESEEK` to the shipped `nvarchar` form (46 s at
   200k rows with one CJK path), use `OPENJSON ... WITH (path
   varchar(n))` (lossy, same code-page squeeze), adopt TVPs ahead of
   1 or 2 (a `CREATE TYPE` per key type per namespace and a
   driver-only bind shape, for 2× the time of `OPENJSON`), or set
   `LOCK_ESCALATION = DISABLE` on the entry table (the scan would then
   hold one `U` lock per row instead — the same blockage with more
   memory).
5. **A deployment note, not a design:** on a database created with a
   UTF-8 default collation, SQLAlchemy's stock `varchar` binds are
   lossless and seek cleanly (27 ms, 3 of 3). vfs could detect that
   (`DATABASEPROPERTYEX(DB_NAME(), 'Collation') LIKE '%UTF8'`) and turn
   `setinputsizes` back on there, but it would still flip to a scan on
   small tables and still pay the per-element compile, so it is an
   optimization on top of 1, never a substitute.

**One line:** on SQL Server, replace `col IN (@p1..@pN)` with a
`VALUES` derived table whose values are cast on the server into the
column's own collation, `FORCESEEK` on the locking reads, chunked at
2,000 elements as a lock budget — it is lossless, seeks where it
must, tells the optimizer the truth where it may choose, and never
escalates; `OPENJSON` ties on speed but lies about cardinality, and
every other option fails at least one of those tests.

## Sources

- The experiments: this session, 2026-09-04, against the
  `docker/compose.test.yml` SQL Server 2025 container (RTM-CU8,
  17.0.4075.5, Enterprise Developer, Ubuntu 24.04 image, amd64 under
  Rosetta; `master` collation `SQL_Latin1_General_CP1_CI_AS`, compat
  170; 10 vCPU, 2 GB), tree at `c3903d7` plus the spec 144 working
  copy; scripts and full tables in
  `studies/2026-09-04-mssql-membership-reads/`.
- SQLAlchemy 2.0.52 as installed (`.venv`), pyodbc 5.3.0, aioodbc
  0.5.0; the refreshed read-only clone `~/Git/Repos/sqlalchemy`
  (MIT, `origin/main` de83fa72d, 2026-09-04, clean) for the 2.1-dev
  line numbers cited beside the installed ones, the ORM selectin
  chunk, the changelog rationale and the mssql tests
  (`test/dialect/mssql/test_engine.py:658-800`).
- Reference clones, each refreshed to its upstream default branch
  and licence-checked 2026-09-04, all clean: jackrabbit-oak
  (Apache-2.0, `origin/trunk` f26e243, 2026-09-04) — the RDB document
  store files cited above; and, with no SQL Server support found by
  grep: opendal (Apache-2.0, `origin/main` 8fcab84, 2026-09-04),
  filesystem_spec (BSD-3-Clause, `origin/master` 13b0bce,
  2026-09-01), pyfilesystem2 (MIT, `origin/master` 77a8562,
  2025-05-17), juicefs (Apache-2.0, `origin/main` c9a67b2,
  2026-09-04), seaweedfs (Apache-2.0, `origin/master` ed9d588,
  2026-09-04), agentfs (licences under `licenses/`, `origin/main`
  0a014eb, 2026-06-03), libsqlfs (LGPL, `origin/master` 4d330a6,
  2019-07-10), memori (LICENSE present, `origin/main` 10d6501,
  2026-09-03), letta (Apache-2.0, `origin/main` 4511fa0bc,
  2026-08-23), mem0 (Apache-2.0, `origin/main` dae67f7, 2026-09-04).
- vfs: `src/vfs/storage/backends/database/engine.py` (`_engine_kwargs`),
  `src/vfs/models/rows.py` (`BytewiseString`, `_string`, `ULIDKey`),
  `src/vfs/storage/backends/database/dialects.py` (`MSSQL`,
  `membership_budget`, `lock_rows`), the `.in_(` census over
  `src/vfs/storage/backends/database/`.
- Microsoft documentation:
  `IN (Transact-SQL)` — https://learn.microsoft.com/en-us/sql/t-sql/language-elements/in-transact-sql
  (OR-equivalence; errors 8623/8632 on very long lists);
  `Table hints` — https://learn.microsoft.com/en-us/sql/t-sql/queries/hints-transact-sql-table
  (`FORCESEEK`, `UPDLOCK`);
  `Data type precedence` — https://learn.microsoft.com/en-us/sql/t-sql/data-types/data-type-precedence-transact-sql
  (`nvarchar` outranks `varchar`, so the column converts);
  `Collation and Unicode support` — https://learn.microsoft.com/en-us/sql/relational-databases/collations/collation-and-unicode-support
  (`_UTF8` collations; code pages);
  `CAST and CONVERT` — https://learn.microsoft.com/en-us/sql/t-sql/functions/cast-and-convert-transact-sql
  (`nvarchar` → `varchar` uses the collation's code page);
  `OPENJSON` — https://learn.microsoft.com/en-us/sql/t-sql/functions/openjson-transact-sql
  (default vs `WITH` schema; `value` is `nvarchar(max)`);
  `Use table-valued parameters` — https://learn.microsoft.com/en-us/sql/relational-databases/tables/use-table-valued-parameters-database-engine
  (user-defined table type, `READONLY`);
  `Table value constructor` — https://learn.microsoft.com/en-us/sql/t-sql/queries/table-value-constructor-transact-sql
  (the 1,000-row limit, error 10738);
  `Transaction locking and row versioning guide` — https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide
  (escalation at 5,000 locks per statement per table/index, `LOCK_ESCALATION` option);
  `sys.dm_db_index_operational_stats` — https://learn.microsoft.com/en-us/sql/relational-databases/system-dynamic-management-views/sys-dm-db-index-operational-stats-transact-sql
  (`index_lock_promotion_attempt_count`, `index_lock_promotion_count`);
  `Maximum capacity specifications` — https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server
  (2,100 parameters per statement).
- Microsoft, "Showplan logical and physical operators reference" —
  https://learn.microsoft.com/en-us/sql/relational-databases/showplan-logical-and-physical-operators-reference
  (`Merge Interval`, `Constant Scan`, `Filter`, the operators every
  plan here is made of).
- Hugo Kornelis, "Merge Interval" (SQL Server Execution Plan
  Reference) — https://sqlserverfast.com/epr/merge-interval/.
- Paul White, answer on the 64-seek / 15-residual limits of a seek
  operator — https://answers.sqlperformance.com/questions/851/
  (secondary source; the limits are undocumented by Microsoft).
- SQL Undercover, "Explicitly defining values in an IN clause vs
  putting them into a temp table and using a semi join" (2024-12-04) —
  https://sqlundercover.com/2024/12/04/explicitly-defining-values-in-an-in-clause-vs-putting-them-into-a-temp-table-and-use-a-semi-join/.
- Microsoft, "8623: The query processor ran out of internal resources"
  (archived blog) — https://learn.microsoft.com/en-us/archive/blogs/mdegre/8623-the-query-processor-ran-out-of-internal-resources-and-could-not-produce-a-query-plan.
- Microsoft, "Resolve blocking problems caused by lock escalation" —
  https://learn.microsoft.com/en-us/troubleshoot/sql/database-engine/performance/resolve-blocking-problems-caused-lock-escalation.
- Microsoft, `ALTER TABLE` (`SET (LOCK_ESCALATION = ...)`) —
  https://learn.microsoft.com/en-us/sql/t-sql/statements/alter-table-transact-sql.
- Paul White, "Lock Escalation Threshold" part 1 —
  https://sqlperformance.com/2022/09/sql-performance/lock-escalation-threshold-part-1
  and part 3 — https://sqlperformance.com/2022/10/sql-performance/lock-escalation-threshold-part-3;
  db-berater, "UPDLOCK and lock escalation" (2025-03) —
  https://www.db-berater.de/2025/03/updlock-and-lock-escalation/.
- dotnet/efcore issue #32394, the EF Core 8 `OPENJSON` regression —
  https://github.com/dotnet/efcore/issues/32394.
- Aaron Bertrand, "STRING_SPLIT() in SQL Server 2016: Follow-Up #1"
  (the hard-coded 50-row estimate) —
  https://sqlperformance.com/2016/04/sql-server-2016/string-split-follow-up-1;
  Brent Ozar, "How to Pass a List of Values Into a Stored Procedure"
  (2020) — https://www.brentozar.com/archive/2020/02/how-to-pass-a-list-of-values-into-a-stored-procedure/
  and "Should You Use SQL Server 2022's STRING_SPLIT?" (2022) —
  https://www.brentozar.com/archive/2022/12/should-you-use-sql-server-2022s-string_split/;
  "Statistics Matter on Temp Tables, Too" (2014) —
  https://www.brentozar.com/archive/2014/02/statistics-matter-on-temp-tables-too/.
- Microsoft, `STRING_SPLIT` — https://learn.microsoft.com/en-us/sql/t-sql/functions/string-split-transact-sql.
- Solomon Rutzky, "Native UTF-8 Support in SQL Server 2019: Savior,
  False Prophet, or Both?" — https://sqlquantumleap.com/2018/09/28/native-utf-8-support-in-sql-server-2019-savior-false-prophet-or-both/
  (collation precedence can silently lose data when UTF-8 and
  non-UTF-8 `varchar` mix).
- MSSQLTips, "Implicit Conversions in SQL affect query performance"
  (`PlanAffectingConvert`, the `plan_affecting_convert` XEvent) —
  https://www.mssqltips.com/sqlservertip/7732/implicit-conversions-in-sql-affect-query-performance/.
- SQLAlchemy tracker: issue #8177 — https://github.com/sqlalchemy/sqlalchemy/issues/8177;
  discussion #8171 — https://github.com/sqlalchemy/sqlalchemy/discussions/8171;
  discussion #10524 — https://github.com/sqlalchemy/sqlalchemy/discussions/10524;
  issues #5048 and #4198 (expanding-parameter internals) —
  https://github.com/sqlalchemy/sqlalchemy/issues/5048,
  https://github.com/sqlalchemy/sqlalchemy/issues/4198;
  operators reference (`IN` renders `__[POSTCOMPILE_...]`) —
  https://docs.sqlalchemy.org/en/20/core/operators.html.
- pyodbc wiki: "Unicode" — https://github.com/mkleehammer/pyodbc/wiki/Unicode;
  "Cursor" (`setinputsizes`) — https://github.com/mkleehammer/pyodbc/wiki/Cursor;
  "Tips and Tricks by Database Platform" —
  https://github.com/mkleehammer/Pyodbc/wiki/Tips-and-Tricks-by-Database-Platform;
  aioodbc — https://github.com/aio-libs/aioodbc (a thread wrapper around pyodbc).
- Jonathan Kehayias, "Implicit Conversions that cause Index Scans" —
  https://www.sqlskills.com/blogs/jonathan/implicit-conversions-that-cause-index-scans/
  (fetched 2026-09-04: on a `SQL_` collation the `varchar` → `nvarchar`
  conversion produces an index scan, on a Windows collation a seek is
  still used — the reason vfs's `Latin1_General_100_BIN2_UTF8` column
  seeks through the conversion at all).
- Paul White, "Dynamic Seeks and Hidden Implicit Conversions" (2012) —
  https://sqlkiwi.blogspot.com/2012/01/dynamic-seeks-and-hidden-implicit-conversions.html
  (the dynamic-seek operators are added after costing, at zero cost;
  `GetRangeThroughConvert` / `GetRangeWithMismatchedTypes`; hidden
  conversions damage cardinality estimates even when a seek survives).
- SQLAlchemy documentation: mssql dialect, "Setinputsizes Support" —
  https://docs.sqlalchemy.org/en/20/dialects/mssql.html#setinputsizes-support;
  `bindparam(expanding=True)` —
  https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.bindparam.
- pyodbc wiki, "Working with Table Valued Parameters (TVPs)" —
  https://github.com/mkleehammer/pyodbc/wiki/Working-with-Table-Valued-Parameters-(TVPs)
  (fetched 2026-09-04: a TVP is a list of row tuples; the type name
  and schema are prepended as two leading strings, a fix from
  pyodbc 4.0.32 / issue #595; every example is a stored-procedure call).
- Microsoft documentation pages above were fetched 2026-09-04 for
  the `IN` remarks (errors 8623/8632, "store the items in a table"),
  the lock-escalation thresholds (5,000 locks per statement per
  table/index, retries every 1,250 locks, `ALTER TABLE SET
  LOCK_ESCALATION`), and the table-value-constructor limits (no
  derived-table row limit; 1,000 rows for `INSERT ... VALUES`, error
  10738); the others are cited by their stable reference URLs.
