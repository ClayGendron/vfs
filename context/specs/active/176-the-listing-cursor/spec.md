# 176 — The listing cursor on `ls`, `tree` and `glob`: a path key on `Result`, keyset pages that read around tombstones, and one merge rule for every fan-out

- **Status:** draft — cut 2026-10-24 from ADR 087 (proposed the same
  day) and the two memos it stands on. Not started. Three open
  `[NEEDS CLARIFICATION]` markers (§1.1, §1.2, §1.4).
- **Date:** 2026-10-24
- **Owner:** Clay Gendron
- **Kind:** feature, in three slices. Slice A: the envelope field
  `Result.next_after`, the arguments `after=` and `limit=` on `ls`,
  `tree` and `glob`, the merge rule (`vfs/results/paging.py`), the key
  rebase (`vfs/paths.py`), and the router plumbing, served for every
  backend by a derived page in the router. Slice B: native keyset
  pages in `DatabaseStorage`, two index changes on `vfs_entries`, the
  `listing_cursor` trait, and the conformance family on every engine
  leg. Slice C: a stored `depth` column so a `tree` with `max_depth`
  pages in bounded work too. Schema format version 23 becomes 24
  (slice B) and 25 (slice C).
- **Depends on:** ADR 087 (pins 1, 3, 5, 12, 14, 15); ADR 010 (the
  envelope; amended below); ADR 033 §3 (the cursor deferral this spec
  closes); ADR 074 (a tombstone keeps its `(parent_id, name)`); ADRs
  067 and 072 (rights judged inside the statement). Nothing unlanded.
  Consumed by specs 167 (the `ls`, `tree`, `find` programs), 169 §b4
  and 172 (the WASI listing), 171 (the MCP tools) and 180 (the
  bounded `sweep` reuses the key and the merge rule).
- **Decisions it implements:** ADR 087 pin 3 (the cursor half: `ls`,
  `tree` and `glob` take `after=` and `limit=`, keyset on
  `(parent_id, name)`); pin 12 (the resumption key is a field of
  `Result`, carried as the lean); pin 14 (the access-path rows for
  three verbs); pin 15 (the axis table, §2.2); the ADR 033 amendment
  (the cursor deferred to "the MCP pass" lands here).
- **Research it stands on:**
  `../../../research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md`
  §2.6 and §5 step 4;
  `../../../research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md`
  §2, §4.2 (the `ls` row), §5 and §8 Q3; the studies
  `studies/2026-10-24-ostep-principles-for-vfs/04-locality-and-log-structure-ffs-lfs-ssd.md`
  (P3, P9 and the 900-of-1,000 probe `experiments/s04/lfs_probe.py`),
  `02-files-and-directories-the-api.md` (principle 4),
  `06-distribution-nfs-afs.md` (the nouns table: READDIR with cookie),
  and `studies/2026-10-23-filesystem-shaped-api/05-vfs-surface-audit.md`
  §4b with `experiments/s05/ls_10k.py`, and
  `06-sql-metadata-engines-seaweedfs-juicefs.md` §3 (keyset listings
  on the last name); the MCP memo
  `../../../research/2026-08-10-mcp-2026-07-28-stateless-revision.md`
  §8.2 (SEP-2567's cursor etiquette). Two probes ran for this spec
  (EXECUTED, appendix A).

## Intent

After this spec an agent can list a directory of 10,000 files one page
at a time. It asks `ls("/big", limit=1000)`. It gets 1,000 rows and a
key, `next_after`, which is the path of the last row. It passes the key
back as `after=` and gets the next 1,000. When the key comes back
empty, the listing is done. `tree` and `glob` work the same way, across
every mount, with no row repeated and no row lost.

Each page costs a fixed number of statements and reads a bounded
number of rows, even in a directory where most rows are deleted. Today
a deleted row stays in the listing's index range until `sweep` runs,
so a listing reads 1,000 rows to return 100 (EXECUTED, study 04). After
this spec the index skips deleted rows, so a page of 10 reads 11.

## Terms

Each term is used in one sense throughout.

| Term | Meaning |
|---|---|
| keyset page | A page that starts strictly after a key value in a sorted order, never at a numeric offset. The engine seeks to the key in an index and reads forward. |
| key | The resumption key: the path of the last row on a page. The caller passes it back as `after=`. |
| `next_after` | The field on `Result` that carries the key. `None` means the listing is exhausted. |
| `limit` | The most rows one page may hold. A page size, not a cap: the next page continues. |
| tombstone | A deleted row. It keeps its path and its `(parent_id, name)` with `deleted_at` set (ADR 074), until `sweep` purges it. |
| rows visited | Rows the engine's index range hands to its row filter for one statement. What an index design bounds. |
| rows fetched | Rows a statement returns to Python. |
| rows emitted | Rows that land on the page, after every filter in Python (rights, the compiled glob). |
| fill | Fetching more rows in the same storage call when Python filters dropped some, until the page has `limit + 1` emitted rows or the range ends (§2.3). |
| frontier | When several sorted streams (mounts, statement chunks) are merged into one page, the smallest key any unfinished stream reached. No merged row may pass it (§3.2). |

## 1. The contract at the surface

### 1.1 The arguments: `after=` and `limit=`

`ls`, `tree` and `glob` gain two keyword arguments on the router
(`base.py` `ls` line 928, `tree` line 941, `glob` line 1257), on
`Session` (`session.py` lines 104, 115, 253) and in `PARAMS`
(`params.py` lines 152, 158, 243):

```python
ParamSpec("after", "path", doc="resume after this row's path; the previous page's next_after"),
ParamSpec("limit", "int", minimum=1, maximum=INT_CEILING, doc="most rows on one page; None lists everything"),
```

- `after=None` starts at the beginning. `limit=None` returns every
  row after `after`, as today.
- `after` is gated like any path (`resolve_path`, read side). A
  relative or malformed key is `vfs.invalid` before any storage call.
- New shape rules in `RULES` (`params.py` line 403), each refusing
  `vfs.invalid` with zero storage calls:
  - `ls`: `(("after", "limit"), ("observations",))`, both forbidden
    together. A cursor pages one directory (§3.4).
  - `glob`: `(("after", "limit"), ("max_count",))`, both forbidden
    together. `max_count` stays a prefix cut in merge order with no
    key; `limit` is a page in path order with a key. Retiring glob's
    `max_count` in favour of `limit` is left to spec 181.
- **The default page.** The lean: the kernel has no default page.
  `limit=None` lists everything, so no existing caller (ETL, the
  conformance battery, chained Python) can lose rows by ignoring a key
  it never asked for. ADR 033 called a bare row cap "a silent-loss
  trap"; a default page with a key is not silent, but code that never
  reads `next_after` would still drop rows. The fronts page instead:
  the MCP tools pass `limit=LISTING_PAGE` when the call names none
  (spec 171 rebase note), the shell programs page at `ROWS_PER_CHUNK`
  (spec 167 rebase note), and the WASI listing drains pages (specs 169
  and 172 rebase notes). `LISTING_PAGE: Final = 1_000` lives in
  `vfs/ops.py` beside `GRAPH_LIMIT_DEFAULT`.
  `[NEEDS CLARIFICATION: the default page — none at the kernel with every front paging (lean), or a kernel default of LISTING_PAGE on ls, tree and glob with the more-line (§1.4) on every truncated listing; the second bounds the Python surface too but changes what an ETL ls returns]`

### 1.2 The key is the last row's path (lean)

The key is a plain `Path`: the full path of the last row on the page,
in the caller's namespace. ADR 087 pin 3 wrote `after=<name>`; this
spec widens it to a path, for five reasons:

1. **One key for three verbs.** `ls` pages siblings, `tree` and `glob`
   page whole subtrees. A bare name cannot say where a subtree page
   stopped. A path can, and for siblings path order equals name order,
   so `ls` still seeks on `(parent_id, name)` (§2.1).
2. **It rebases like every other path.** A page from a mount at `/m`
   carries keys under `/m`, and the existing rebase seam
   (`with_mount`, `without_mount`) moves them, exactly as it moves
   rows (§1.4, §3.1).
3. **It never expires.** A keyset key is a position, not a handle.
   The row it names may be deleted or moved between pages and the
   next page still starts at the right place. SEP-2567's etiquette
   asks for an expiry error; a path key never needs one.
4. **It grants nothing.** Every page passes the gate afresh under the
   caller's authority (ADR 087 pin 6). A forged key is only a
   different starting position, which `after=` already accepts. So
   "possession is not authorization" holds by construction.
5. **It survives every wire.** It is a JSON string in
   `structuredContent`, a shell word (`shlex.quote` round-trips it), a
   WASI string, and readable in a transcript.

The one risk of a readable key is that it names a row. §2.3 closes
that: **a key is always the path of a row on the page**, so it names
only what the caller was already shown.

`[NEEDS CLARIFICATION: the key's shape — the last row's plain path (lean), or a server-sealed opaque token per SEP-2567's etiquette (the 2026-08-10 MCP memo §8.2); a sealed token could carry a scanned-but-hidden position and drop the fill rule of §2.3, but it needs a server secret, a cipher vfs does not depend on, an expiry kind, and it is unusable as a CLI flag]`

A key must belong to the listing it resumes, or the call refuses
`vfs.invalid` with detail "the key is not in this listing":

| Verb | The key must be | Checked by |
|---|---|---|
| `ls(path)` | a child of the target's stored address (`address_of(rel).stored`, which strips the trash head); any path at all when the target is the trash head `/.vfs/trash` itself, whose rows answer at their own paths at every depth | the router |
| `tree(path)` | strictly beneath the target's stored address | the router |
| `glob` | any path | none: path order is global |

The router checks after `local_after` (§3.1), in the target mount's
coordinates, with `address_of` from `vfs/paths.py`, which is pure. So
a foreign key costs no storage call. A key that rebases outside the
target's mount (`start` or `past`) cannot be in the listing and is
refused the same way.

### 1.3 What a page promises

- **Order.** With `after` or `limit` given, rows come in path order:
  byte order of UTF-8, which equals Python's code-point order and the
  binary collation every engine's `path` and `name` columns are
  pinned to (`rows.py` `BytewiseString`, line 191; Oracle rests on
  `NLS_SORT=BINARY`, as that docstring already says). Without either,
  each verb keeps today's order.
- **Size.** A page holds at most `limit` rows. One exception: a `tree`
  page under a partial view may also carry the bare road directories
  that lead to its rows (§2.4). A page may be short, even empty, and
  still carry a key; this happens only when the router drops rows a
  deeper mount shadows (§3.3). Callers loop on the key, never on the
  page length.
- **The key.** `next_after` is set if and only if more rows may follow.
  The storage call fetches `limit + 1` emitted rows to know (the
  SeaweedFS pattern, study 06 §3), so a listing of exactly `N × limit`
  rows ends on its `N`th page, never on an empty extra page.
- **Rivals.** Each page is its own read transaction, so a listing
  across pages is not one snapshot. The guarantee is POSIX
  `readdir`'s: a row present for the whole iteration and not renamed
  appears exactly once; a row created, deleted or renamed during it may
  or may not appear; a row renamed forward past the key may appear
  under both paths. No row appears twice under one path.
- **Rights.** Every page is gated fresh (ADR 084 pin 2). A grant
  revoked between pages narrows the next page; no page carries a
  right.

### 1.4 Where the key lives: `Result.next_after` (lean)

`Result` (`results/envelope.py` line 316) gains one declared field:

```python
next_after: Path | None = None
```

ADR 087 pin 12 carries this as a lean. Declared, not an extra: the
envelope is open (`extra="allow"`), but an extra would be dropped by
`merge` and rebased by nobody.

`[NEEDS CLARIFICATION: pin 12 — the key as a field of Result (lean, carried here: the MCP wire needs it in structuredContent, and Oak's hasMore is a field), or a separate return such as a (Result, key) pair, which breaks the one-result-type rule of ADR 010 and every chained call]`

**The wire shape.** `to_payload()` (line 723) emits it when set:

```json
{"success": true, "ops": ["ls"], "observations": [...], "errors": [], "next_after": "/big/f00999.txt"}
```

With the default `exclude_none=True` an exhausted listing has no
`next_after` key at all; with `exclude_none=False` it is `null`.
`from_payload` restores it as a `Path`; a malformed value quarantines
as an envelope-field warning under the existing lenient rule. A peer
that predates the field carries it through as an extra, because the
model is open.

**What each operation does to the key.** One rule per family:

| Operation | `next_after` | Why |
|---|---|---|
| `filter`, `sort`, `top`, `kinds`, `_demoted`, `model_copy`, `_with_skips` | kept | the page shrank or reordered by the caller's choice; the listing's position is unchanged |
| `a \| b`, `a & b`, `a - b`, `Result.merge`, `Result.merge_branches` | `None` | two listings have no one position; the router merges pages with `frontier_page` instead (§3.2) |
| `with_mount(m)` | rebased like a row path | the key is a path in the reader's namespace |
| `without_mount(m)` | stripped like a row path | the inbound half |

`_with_observations` (line 616) must therefore pass `next_after`
through, and `with_mount` (line 662) and `without_mount` (line 704)
must rebase it. If the rebased key would exceed `MAX_PATH_LENGTH`, the
row it names was already dropped as `vfs.unaddressable`; the key
becomes `None` and the same warning gains `data["vfs.overflow"]
["next_after"] = <local key>`, so the listing ends loudly, never
silently. This needs a local path within a mount prefix of 1,024
bytes and is not expected in practice.

**The text.** `render_result` (`results/render.py` line 42) appends
one block after the body and before the errors when the key is set:

```text
more: after=/big/f00999.txt
```

This is the loud note. An agent reading the text sees that the
listing continues and what to pass. The line never appears when
`next_after` is `None`.

## 2. Storage: the keyset statements (`reads.py`)

### 2.1 `ls`: one directory, keyset on `(parent_id, name)`

Today `ls_rows` (line 189) fetches each target with its ancestors in
one point fetch (`_mappings_by_path`, line 793), screens it, then
`_children_by_parent` (line 844) lists every child of every directory
target with chunked `parent_id IN (...)` selects ordered by
`(parent_id, name)` (line 881), with no limit.

With `after` or `limit`, `ls_rows` takes a single target (the router
already refused a batch) and lists through a new
`_children_page`:

```python
stmt = (
    select(*_entry_columns(entry, wanted))
    .where(
        entry.c.parent_id == parent_id,
        *liveness_filters(entry, profile, include_meta=include_meta, trashed=trashed),
        *([entry.c.name > after_name] if after_name is not None else []),
    )
    .order_by(entry.c.name)
    .limit(batch)
)
```

- `after_name` is the last segment of the local key, which the
  router has already checked is a child of the target (§1.2). Comparing
  `name` rather than `path` lets one index serve the equality, the
  bound and the order.
- `batch` is `limit + 1` on the first statement of a page (§2.3 says
  when there is a second).
- Bind parameters per statement: the parent id, the name bound, the
  two meta-exclusion literals when `include_meta` is false, and the
  limit. Five at most, constant in the directory's size, so no
  chunking applies.
- A file target lists itself as today: one row, no key.
- **The trash head** `ls /.vfs/trash` lists the tombstoned roots in
  path order (`_trash_roots`, line 940). Its page adds `path > :key`
  and `LIMIT`. It visits every tombstoned row in its path range, roots
  and their descendants alike; `sweep` bounds that set, and spec 180's
  garbage gauge measures it. This is the one listing the new indexes
  do not bound, and the docstring says so.
- **The meta root** `ls /.vfs` merges the synthesized `trash` row into
  name order (`_with_trash_view`, line 960). Under a cursor the
  synthesized row obeys the key like a stored one: it is emitted only
  if its path is after the key, and it may itself be the key.

### 2.2 Tombstones: the liveness term moves into the index

**The problem, EXECUTED** (appendix A, SQLite, the statements of
§2.1 and §2.4 run against a database vfs built). With today's
indexes, the `(parent_id, name)` unique index holds tombstones beside
live rows, and the `deleted_at IS NULL` test runs per row after the
index lookup:

| Directory | Page | Rows visited per page, today | With the new indexes |
|---|---|---|---|
| `/d`: 1,000 children, the first 900 deleted | `ls(limit=10)`, 10 pages | 911 on page 1, then 11 | 11 on every page (10 on the last) |
| `/s`: 1,000 children, 9 of every 10 deleted | `ls(limit=10)`, 10 pages | 101, then 110 | 11 |
| `/s` as a subtree | `tree(limit=10)`, 10 pages | 101, then 110 | 11 |
| `/big`: 10,000 live children | `ls(limit=1000)`, 10 pages | 1,001 | 1,001 |

Every page returned the right rows in both columns: 10 pages, no row
repeated, none lost. Only the work differs.

**The change.** Two index changes on `vfs_entries` (`rows.py` around
line 482), and `SCHEMA_FORMAT_VERSION` (line 139) goes from 23 to 24:

```python
Index("ix_vfs_entries_parent_live_name", "parent_id", "deleted_at", "name"),
Index("ix_vfs_entries_deleted_at", "deleted_at", "path"),  # widened from (deleted_at)
```

- The first serves `ls` pages: `parent_id = :p AND deleted_at IS NULL
  AND name > :after ORDER BY name LIMIT n`. SQLite plans `IS NULL` as
  an equality on the index's second column (`deleted_at=?`, EXECUTED).
  Postgres, SQL Server, MariaDB and Oracle each document `IS NULL` as
  usable in a composite B-tree whose leading column is bound
  (INFERRED); task 9 measures it on each. The unique `(parent_id, name)` constraint
  stays: it arbitrates concurrent creates across live and tombstoned
  rows (ADR 074), which the new index cannot.
- The second widens an index that already exists. Its leading column
  still serves the sweep's age seek and the trash view's tombstoned
  seek. The added `path` serves `tree` pages and the live side of
  `glob`: `deleted_at IS NULL AND path > :after AND path < :upper
  ORDER BY path`. SQLite plans it as `deleted_at=? AND path>? AND
  path<?` (EXECUTED).
- Key widths stay inside every engine's key budget: the existing
  `ix_vfs_entries_everyone_path (everyone_level, path)` (line 489) is
  the precedent for a composite that ends in `path`.
- **Write cost.** Every row insert maintains one more index entry, and
  a delete or restore moves the row in both indexes, as it already
  moves it in `(deleted_at)`. No statement is added: the 10,000-row
  write stays 38 statements (criterion 13; EXECUTED at HEAD `ba77449`
  by re-running study 05's `ls_10k.py`, which counted 40 before the
  create-clears-no-body fix of `4459271`). The engine's own index
  maintenance is what the real legs report.

**The decision on the standing axes** (ADR 087 pin 15). Four ways to
keep a page's visited rows bounded:

| Axis | (a) composite indexes (chosen) | (b) count on the sweep schedule | (c) scan a fixed budget of raw rows, filter in Python | (d) partial index `WHERE deleted_at IS NULL` |
|---|---|---|---|---|
| Agent latency (statements per page) | 1 | 1 | 1, but many short or empty pages | 1 |
| ETL throughput | one more index entry per insert | none | none | one more index entry per live insert |
| Boundedness | `limit + 1` live rows, whatever the garbage | none: 911 rows for 10 until a deployment runs `sweep` | per page yes; pages per listing grow with garbage | `limit + 1` |
| Correctness under rivals | unchanged | unchanged | unchanged | unchanged |
| The atomic unit | unchanged | unchanged | unchanged | unchanged |
| Dialect reach | all five engines | all five | all five | Postgres, SQLite and SQL Server only; Oracle and MariaDB have no partial index |
| Protection | unchanged | unchanged | unchanged | unchanged |
| Overhead above the engine | none | none | Python filters dead rows | none |

(b) leaves the bound to a deployment's habits. (c) moves the garbage
from rows to round trips. (d) fails dialect reach. So (a).

**What the real-engine legs must measure** (slice B, task 9). SQLite
is EXECUTED above. Postgres, MariaDB, SQL Server and Oracle must each
show, on the fixtures of criteria 5 and 6, that the planner picks the
composite index for the `ls` page and the widened index for the `tree`
page, and that rows visited per page stay at `limit + 1`. Each engine
has a counter (§5). If a planner prefers the unique index, the fix is
an index pin as a `DialectProfile` fact, as `ranges.py` already does
for its range join; that is a decision SQLAlchemy takes no position
on, so the profile field is justified.

### 2.3 The fill rule: a key is always an emitted row

Python drops some fetched rows: a row the caller may not name under a
partial view (`view.shows`, `rights.py` line 509), and a `glob`
candidate the compiled pattern rejects. If the key could be the last
*fetched* row, a key could name a hidden row. That leaks a name. So:

**Rule.** A page is the first `limit` emitted rows after the key. The
key is the `limit`-th emitted row, set only when a `(limit + 1)`-th
emitted row exists. To find them, the storage call fetches in batches
from the last fetched row (an internal position, never returned):

1. The first batch is `limit + 1` rows.
2. While fewer than `limit + 1` rows are emitted and the range is not
   exhausted, fetch the next batch at twice the last batch's size, up
   to `LISTING_FILL_CEILING`, then in steps of that size.
3. Stop at `limit + 1` emitted rows or the end of the range.

`LISTING_FILL_CEILING: Final = 10_000` (`reads.py`), the same order as
grep's candidate budget (ADR 033 §3): no fill statement fetches more
rows than one verify pass already does. It bounds one statement's
working set. It is not a cap: the page keeps filling.

**The cost.** With no Python-side drop (the system actor; `ls` and
`tree`, whose tombstones the index already skips), the first batch
fills the page: one statement. Otherwise a page costs at most
`1 + ⌈log2(F / (limit + 1))⌉` statements while `F ≤ LISTING_FILL_CEILING`,
where `F` is the rows fetched to fill it, plus `⌈F / LISTING_FILL_CEILING⌉`
beyond that. Across a whole listing the rows fetched are at most about
twice what one unpaged call fetches, plus the one gap per page that
the next page fetches again. Under a view, `_children_by_parent`'s
road lookup (`view.road`) runs once per batch that holds a hidden
directory, as it runs once per call today.

### 2.4 `tree`: keyset on `path`

`tree_rows` (line 235) selects every live descendant ordered by
`path` (line 272) with an optional slash-count depth term. With
`after` or `limit` it adds a half-open range and a limit:

```python
lower = local_key if local_key is not None else address.stored
upper = None if address.stored == ROOT else address.stored + "0"
stmt = (
    select(*_entry_columns(entry, wanted))
    .where(
        descendant_filter(entry, address.stored, profile),
        entry.c.path > lower,
        *([entry.c.path < upper] if upper is not None else []),
        *liveness_filters(entry, profile, include_meta=address.meta, trashed=address.trashed),
    )
    .order_by(entry.c.path)
    .limit(batch)
)
```

- `[root + "/", root + "0")` is everything beneath `root`, because `0`
  is the byte after `/`. The rights code already uses this bound
  (`grants.py` line 25, `ranges.py` line 387). The explicit bounds make
  the range sargable on every engine without relying on each engine's
  `LIKE` prefix rule; the `LIKE` stays as the correctness term.
- **Under a view** the statement goes through `view.narrow` as today,
  so the fetched rows are already the ones the caller may name. When
  `narrow` yields one statement per clause, each clause statement is a
  stream and the clause pages merge by the frontier rule (§3.2), the
  same rule the router uses for mounts.
- **Road rows.** A hidden ancestor of an emitted row shows as a bare
  name (`_ancestors_below`, line 776). Under a cursor an ancestor `A`
  is emitted on a page only if the key does not lie inside `A`'s
  subtree (`not key.startswith(A + "/")`); otherwise an earlier page
  already showed it. This is a pure check, no query. One edge: a
  sibling whose name sorts between `A` and `A/` (such as `A.txt`, since
  `.` is below `/` in byte order) can make `A` arrive one page late,
  sorted before the key. It is emitted exactly once. Road rows do not
  count toward `limit` and are never the key; a page carries at most
  one per level of depth per emitted row, deduplicated.
- **The trash view.** A `tree` under `/.vfs/trash` flips the liveness
  term to `deleted_at IS NOT NULL`. That side is a range of tombstone
  times, not one value, so the widened index cannot also give path
  order: the page visits the tombstones in its path range, the trash
  head's profile (§2.1), bounded by `sweep`.
- **`max_depth` today.** The depth term is a residual filter on a
  computed slash count, so rows deeper than the bound are visited and
  dropped. EXECUTED: `tree("/n", max_depth=1)` over 10 directories of
  100 files, `limit=5`, visited 506 and 605 rows for 5 rows a page,
  with either index set. Slice B ships this profile and says so in the
  docstring; slice C bounds it (§2.5).

### 2.5 `tree` with `max_depth`: a stored depth (slice C)

- **The column.** `Column("depth", SmallInteger, nullable=False)` on
  `vfs_entries`: the number of `/` in the stored path (`0` for the
  root). It is a cache of `path`, like `path` is a cache of the
  `(parent_id, name)` chain (ADR 004), and it is written wherever
  `path` is written: `writes.py` `_entry_values` (line 1194),
  `topology.py` `_execute_move` (line 281, the moved root),
  `_apply_rewrites` (line 355, every descendant: one more bound
  parameter `b_depth` beside `b_path`), and `_execute_copy` (line
  405). A drift test pins `depth == path.count("/")` on every row the
  conformance battery writes.
- **The index.** `Index("ix_vfs_entries_live_depth_path", "deleted_at",
  "depth", "path")`. `SCHEMA_FORMAT_VERSION` 24 becomes 25.
- **The page.** A tree page under `max_depth = d` from a root at depth
  `r` is one statement: a `UNION ALL` of `d` branches, branch `k`
  being `deleted_at IS NULL AND depth = r + k AND path > :lower AND
  path < :upper ORDER BY path LIMIT :batch`, each a derived table so
  every engine accepts its own `ORDER BY` and limit (SQLAlchemy renders
  `TOP` on SQL Server and `FETCH FIRST` on Oracle). Each branch is a
  stream; the branches merge by the frontier rule. Rows visited per
  page: at most `d × (limit + 1)`.
- **Bind budget.** Each branch carries six bind parameters: the
  depth, the two path bounds, the limit, and the two meta-exclusion
  literals. The branches chunk with `chunked(levels, arm_budget(profile,
  parameter_budget, 6))` (`dialects.py` lines 666, 683), so a large
  `max_depth` becomes several statements per page, never one statement
  past SQL Server's ~2,100 parameters. The chunks are streams too.
- **Without `max_depth`** the slice B statement on
  `(deleted_at, path)` stays: one range, `limit + 1` rows.

### 2.6 `glob`: the key inside every arm

`glob_rows` (line 301) builds one self-contained OR-arm per pattern
(`pattern_arm`, line 500), chunks the arms by `arm_budget`, runs the
chunks in one snapshot, merges and sorts the candidates in Python
(`_pattern_candidates`, line 822), verifies each against the compiled
pattern, and applies `max_count` last.

With `after` or `limit`:

- **The key rides inside each arm**, as `path > :after`, never beside
  the fan. `_pattern_candidates`' docstring pins why: "nothing rides
  beside the fan", because a term beside an OR of arms demotes the
  plan. `ARM_FIXED_BINDS` (line 298) goes from 7 to 8, and
  `arm_budget` recomputes the chunk size, so 10,000 patterns still
  chunk under Oracle's and SQL Server's budgets.
- **Each chunk statement** gains `ORDER BY path LIMIT :batch` and is a
  stream. The chunk streams merge by the frontier rule, then the
  compiled pattern and the view filter run, and the fill rule (§2.3)
  fetches more when they drop rows.
- **The profile, stated honestly.** The `LIKE` prefilter over-admits
  (`*` becomes `%`, which crosses `/`), and a pattern with no literal
  prefix (`**/*.py`) has no path range at all. So the rows visited for
  a `glob` page are the candidates in the page's path range, not
  `limit + 1`. A sparse pattern over a large corpus visits many
  non-matching rows per page, as one unpaged call does today. Across
  a whole listing each candidate is visited about once. The docstring
  says so. The named future direction is one `UNION ALL` branch per
  arm with its own limit, the §2.5 shape, which bounds a prefixed arm
  at `limit + 1`; it waits for a measured need.

### 2.7 The seam: signatures, the trait, and the derived page

- **Signatures** (`protocol.py`): `SupportsRead.ls` (line 139) and
  `tree` (line 148), and `SupportsPatternSearch.glob` (line 263), gain
  `after: Path | None = None, limit: int | None = None`. `DatabaseStorage`
  passes them to `ls_rows`, `tree_rows` and `glob_rows` (`backend.py`
  lines 351, 373, 458). The storage receives local paths only.
- **The trait.** `TraitKey` (line 72) gains `"listing_cursor"` with
  values `frozenset({"keyset"})`. `DatabaseStorage.traits()` (line 288)
  declares it from slice B on.
- **The derived page.** A backend that does not declare
  `listing_cursor` never receives `after` or `limit`. The router calls
  it as today, sorts its rows by path, drops rows at or before the
  key, keeps `limit`, and sets the key from the `(limit + 1)`-th row.
  This is ADR 087 pin 2's rule for a backend without an index: a
  slower kernel answer, not the cursor leaving the kernel. Its pages
  are correct and cost what the backend's whole listing costs. Slice A
  serves every backend this way, `DatabaseStorage` included, so slice A
  lands green before any SQL changes.

## 3. The router: one merge rule for every fan-out

### 3.1 The key in each mount's coordinates (`paths.py`)

The caller's key is a path in the router's namespace. Each storage
works in its own. A new pure function beside `Path.with_mount` (line
294):

```python
class LocalAfter(NamedTuple):
    state: Literal["start", "key", "past"]
    key: Path | None

def local_after(after: Path | None, mount: Path) -> LocalAfter: ...
```

| The key relative to bind path `B` | `state` | What the router does |
|---|---|---|
| `None`, or below every path under `B` (`after < B + "/"` and not under `B`) | `start` | dispatch with no key |
| under `B` (`after` starts with `B + "/"`) | `key`, `after` without `B` | dispatch with the local key |
| `B` itself | `start` | `B`'s own row lives in the parent mount; everything in `B` follows it |
| above every path under `B` (`after >= B + "0"`) | `past` | do not dispatch; that mount is exhausted |

The root mount `/` is the identity: every key is `key`. The function
is pure and total; a property test checks it against a brute-force
oracle over random paths.

### 3.2 The frontier merge (`vfs/results/paging.py`)

A new leaf module holds the one rule that turns several sorted
streams into one page. Storage uses it for statement chunks and
`narrow` clauses; the router uses it for mounts.

```python
def frontier_page(
    rows: Sequence[T],
    stream_keys: Iterable[str | None],
    limit: int | None,
    path_of: Callable[[T], str],
) -> tuple[list[T], str | None]: ...
```

In plain words:

1. Each stream returned its rows in path order and its own key. A
   stream with a key has more rows; a stream with `None` is finished.
2. The **frontier** `F` is the smallest key among unfinished streams.
   Every stream has returned every row it holds up to its own key, so
   every row at or before `F` is in hand, from every stream.
3. Keep the merged rows at or before `F` (all of them if no stream is
   unfinished), in path order.
4. If more than `limit` remain, the page is the first `limit` and the
   key is the last of those. Otherwise the page is all of them, and the
   key is `F` (or `None` if every stream finished).

Why nothing is lost: a row after the page's key was not emitted, and
the next page starts after that key in every stream. Why nothing
repeats: every emitted row is at or before the key, and the next page
starts strictly after it. Rows from different streams at the same path
fuse first, by the existing `Result.merge` rule (left wins by mask),
because that is where a bind-path row and its mounted root meet.

The waste is bounded: a page discards at most `(streams − 1) × limit`
fetched rows, which the next page fetches again.

A seeded random test (stdlib `random`, no new dependency) checks the
rule against an oracle that lists everything and slices: 1,000 random
cases of 1 to 8 streams, random limits, random interleavings, each
drained to the end, asserting the drained rows equal the oracle's.

### 3.3 Each verb's route

- **`ls`.** A single-path `ls` always lands on one mount. A mount
  point beneath the listed directory shows as its stored directory row
  in the parent mount (`_shadow_filter` docstring, line 3111). So `ls`
  needs no merge: `_route_single` (line 1709) rebases the key with
  `local_after`, checks it belongs to the listing (§1.2; `start` and
  `past` never do), and dispatches once. `tree` runs the same check
  before `_tree_region`.
- **`tree`.** `_tree_region` (line 1960) dispatches the owning mount
  and every mount beneath the root. Each dispatch gets
  `local_after(after, binding.path)` and `limit`; a `past` mount is not
  dispatched (spied in criterion 9). The results merge as today
  (`Result.merge_branches`, the zero-progress rule for errors), then
  `frontier_page` re-pages the rows over the branch keys.
- **`glob`.** `_route_fanout` (line 2041) builds the branches in
  `_glob_dispatches` (line 2197). Each branch gets the rebased key and
  `limit`; `past` branches are skipped. `_merge_fanout` (line 2461)
  keeps its pinning rule for errors; `frontier_page` re-pages the rows.
  `_cap_rows` (line 3198) is skipped on a paged call, because
  `max_count` is refused beside `limit`. Root-probe rows (named scope
  roots served by `_root_probe`) are a stream with no key: they obey
  `> after` and the frontier like any row.
- **The shadow filter.** `_shadow_filter` drops rows a deeper mount
  owns. It runs on each branch after the storage page, so a branch may
  come back short with its key intact. That key may name a dropped
  row. This leaks nothing: the storage emitted that row under the
  caller's rights in that storage; the shadow rule is routing, not
  secrecy. It is the one case that makes a short page with a key (§1.3).
- **Errors and skips** keep their rules. A dead mount among live ones
  demotes to a warning (`merge_branches`). Its rows are absent, and
  its key is treated as finished, so the listing does not stall on it.
  The warning says the listing is partial.

### 3.4 A batch `ls` takes no cursor

`ls(observations=[...])` lists many directories in one call, grouped
by mount (`_dispatch_grouped_observations`, line 1750). A cursor over
it would need one position per directory, or one statement per
directory per page: with a 10,000-directory batch that is 10,000
statements a page, which no budget permits. The batch is the
in-process chaining shape, and its size is the caller's own input. So
the gate refuses `after`/`limit` beside `observations` (§1.1). A
caller who needs bounded pages lists each directory with `path=`. The
`ls_rows` docstring states the batch's profile: every child of every
named directory, in one call.

## 4. The access path, per page (ADR 087 pin 14)

Counts per page, never clocks. "Today" is one unpaged call over the
same 10,000-row directory (EXECUTED, `counts_today.py`, appendix A).

| Verb | Statements, system actor | Statements, named principal, warm | Rows visited per page | Body bytes |
|---|---|---|---|---|
| `ls` today (one call) | 3: `BEGIN`, point fetch, children | 5: plus the two rights revalidations | every child, tombstones included | 0 |
| `ls` page | 3 | 5, plus fill statements (§2.3) | `limit + 1` live children (slice B) | 0 |
| `tree` today (one call) | 3 | 5 (one is the `WITH` of `narrow`) | every descendant | 0 |
| `tree` page | 3 | 5, plus fill | `limit + 1`; with `max_depth = d`, `d × (limit + 1)` from slice C | 0 |
| `glob` today (one call) | 2 | 4 | every candidate the prefilter admits | 0 |
| `glob` page | 2, plus one per probe-owning mount | 4, plus fill | the candidates in the page's path range (§2.6) | 0 |

The anonymous column is measured and pinned by the access-path test
of task 6; the studies have no count for it yet.

## 5. Counting rows visited on each engine

Criteria 5 to 7 assert rows visited per page. Each engine exposes a
different counter, so `tests/support/rows_visited.py` captures the
page statement through `before_cursor_execute` and asks the engine:

| Engine | Counter | Kind |
|---|---|---|
| SQLite | `EXPLAIN QUERY PLAN` must name the index with `deleted_at=?` as an index constraint; then rows in that constrained range up to the last fetched row are counted with `count(*)` | plan-derived (no per-statement counter in the bundled build: `sqlite_stmt` and scan status are not compiled in, EXECUTED) |
| Postgres | `EXPLAIN (ANALYZE, FORMAT JSON)`: the scan node's actual rows plus "Rows Removed by Filter" | engine-counted |
| MariaDB | `Handler_read_key` plus `Handler_read_next` deltas from `SHOW SESSION STATUS` around the statement | engine-counted |
| SQL Server | `SET STATISTICS XML ON`: `ActualRowsRead` on the seek operator | engine-counted |
| Oracle | the `gather_plan_statistics` hint and `DBMS_XPLAN.DISPLAY_CURSOR(format => 'ALLSTATS LAST')`: A-Rows of the index range scan; if the test user cannot read the `V$` views, the plan's access predicates must include `DELETED_AT` | engine-counted, or plan-derived where privileges stop it; the leg task records which |

## Scope

In: §1 to §5. The router, `Session`, `PARAMS` and `RULES`; the
envelope field, its wire shape, its algebra and its rendered line;
`paging.py` and `local_after`; the storage keyset statements, the fill
rule, the two index changes, the `depth` column and its index; the
trait and the derived page; the conformance family; the rows-visited
counters; the real-engine legs; `docs/reference/api.md`,
`docs/reference/session.md` and `docs/how-to/add-a-backend.md` (the
trait and the two arguments).

Out: the fronts' own use of the cursor (specs 167, 169, 171, 172; see
the rebase notes); `sweep(limit=)` (spec 180, which reuses this
spec's key and merge rule); a cursor on `grep`, `glean` or `graph`
(ranked and match-shaped results, a separate question ADR 033 left
open); cross-page snapshots; a per-arm `glob` union (§2.6, named, not
built); retiring glob's `max_count` (spec 181).

## Acceptance criteria

Counts and states, never clocks. Each names its slice. "Every engine
leg" means SQLite file, memory, Postgres, MariaDB, SQL Server and
Oracle.

1. **(A)** `Result.next_after` is a declared `Path | None`.
   `to_payload()` omits it when `None` and carries it as a string when
   set; `Result.from_payload(json.loads(json.dumps(r.to_payload())))
   .next_after == r.next_after` for keys with spaces, quotes and
   non-ASCII segments. A payload from a peer without the field
   round-trips with `next_after is None`.
2. **(A)** `filter`, `sort`, `top`, `kinds` and `model_copy` keep the
   key; `|`, `&`, `-`, `Result.merge` and `Result.merge_branches`
   yield `None`. `with_mount("/m")` turns `/a/b` into `/m/a/b`, and
   `without_mount("/m")` turns it back. An overflowing rebase yields
   `None` and the `vfs.unaddressable` warning carries the local key.
3. **(A)** `to_str()` of a page with a key ends its body with exactly
   `more: after=<key>` before any errors block; a result without a key
   has no such line.
4. **(A)** Each refuses `vfs.invalid` with zero storage calls (spied):
   `ls(observations=[…], limit=10)`; `glob("*", max_count=5,
   limit=5)`; `limit=0`; `after="relative/key"`; `ls("/d",
   after="/e/x")` (not a child); `tree("/d", after="/e/x")` (not
   beneath).
5. **(B, every engine leg)** A directory of 10,000 files written in one
   batch. `ls("/big", limit=1000)` drained from `after=None`: exactly
   10 calls; calls 1 to 9 carry `next_after`, call 10 does not; the
   union of rows equals the 10,000 written paths; no path repeats;
   rows are in path order. Statements per page: 3 as the system actor
   and 5 as a named principal with a `read` grant and a warm cache,
   counted per page. Rows visited per page at most 1,001 (§5).
6. **(B, every engine leg)** 1,000 children; delete the first 900 in
   one call; then, in a second directory, delete 9 of every 10.
   `ls(limit=10)` on each drains in exactly 10 calls, 100 rows, no
   repeat, no loss, and rows visited per page at most 11. The SQLite
   leg reproduces appendix A (today's 911 on page 1 becomes 11).
7. **(B, every engine leg)** `tree("/big", limit=1000)` drains in 10
   calls with the same counts as criterion 5, and `tree` over the
   second directory of criterion 6 visits at most 11 rows a page.
   **(C)** `tree("/n", max_depth=1, limit=5)` over 10 directories of
   100 files visits at most 6 rows a page (appendix A: 506 and 605
   today); `max_depth=2` visits at most `2 × 6`.
8. **(B)** `glob("/big/*.txt", limit=1000)` drains in 10 calls, 10,000
   rows in path order, 2 statements a page as the system actor. A glob
   of 10,000 literal patterns with `limit=100` stays within every
   chunk's bind budget on the Oracle and SQL Server legs: chunk selects
   per page equal `⌈10,000 / arm_budget(profile, budget, 8)⌉`
   (counted), and no statement exceeds the dialect's parameter
   budget.
9. **(A)** Two mounts, `/` and `/m`, each holding 1,500 matching files.
   `glob("**/*.txt", limit=1000)` drains in exactly 3 calls, 3,000
   rows, global path order, no repeat, no loss. A page whose key lies
   beyond every path under `/m` dispatches nothing to `/m` (spied: 0
   calls). `tree("/", limit=1000)` over the same layout drains with the
   same properties. A mount that fails mid-listing demotes to a warning
   and the listing still ends.
10. **(B)** As a named principal allowed to name 1 of every 100 files
    in a 10,000-file directory: `ls(limit=10)` drains in exactly 10
    calls, 100 rows. Every `next_after` is the path of a row on its own
    page (no hidden name ever appears in a key). Children selects per
    page are at most 7, never one per row (§2.3, counted).
11. **(A)** A test backend that does not declare `listing_cursor`
    receives no `after` or `limit` keyword (spied), and its drained
    pages equal the native pages of the same rows.
12. **(B)** Rivals between pages: a file created before the key during
    a drain does not appear; one created after it does; a file present
    throughout appears exactly once; a file deleted after its page was
    served stays served and causes no repeat.
13. **(B)** The schema holds `ix_vfs_entries_parent_live_name` and the
    widened `ix_vfs_entries_deleted_at`; `SCHEMA_FORMAT_VERSION` is 24
    (25 after slice C). `write(entries=10_000, parents=True)` still
    issues 38 statements (counted; appendix A). The SQLite
    plan of the `ls` page names `ix_vfs_entries_parent_live_name` with
    `deleted_at=?` (pinned). **(C)** every row the conformance battery
    writes, moves or copies has `depth == path.count("/")`.
14. **(A)** The seeded frontier test of §3.2 and the `local_after`
    property test pass.
15. **(A)** `Session.ls`, `Session.tree` and `Session.glob` accept
    `after` and `limit`, and the signature drift test passes against
    `PARAMS`.
16. **(all)** `scripts/ci.sh` is green at 100% coverage after every
    task. The four server engine legs are green before slice B and
    slice C land.

## Rebase notes for specs 167, 169, 171 and 172

- **167 (the shell).** The `ls`, `tree` (and `ls -R`) and `find`/`glob`
  programs page at `limit=ROWS_PER_CHUNK` and emit each page as one
  chunk, so a 10,000-file `ls | wc -l` is 10 chunks by construction
  (167 criterion 7) and memory is bounded per stage, not only per seam
  (167 §5 says "a verb returns a whole `Result` and the producer slices
  it"; that sentence changes for these three). `ROWS_PER_CHUNK` and
  `LISTING_PAGE` are the same constant. Two vfs-only flags join the
  §4.1 table: `ls --limit N P` → `ls(P, limit=N)` and `ls --after K P`
  → `ls(P, after=K)`, the same on `tree` and `glob`; with `--limit`,
  the program prints one page and, when a key comes back, one stderr
  line `ls: more: --after <key>`, shell-quoted. `glob` drains up to
  `FANOUT_BUDGET` by pages instead of `max_count=FANOUT_BUDGET + 1`.
  The `cli` `Result` carries the last stage's `next_after`, so
  `to_payload` round-trips it (this spec's criterion 1 covers the
  field; 167 adds the program test).
- **169 §b4 (the WASI host).** `O_DIRECTORY` materializes the listing
  by draining `ls` pages of `LISTING_PAGE`: a 10,000-child directory is
  10 `ls` calls at open (counted), not one 10,000-row call. The
  `fd_readdir` cookie stays an index into the materialized list. A lazy
  form (one page per `fd_readdir`, the fd holding the key) is the named
  future direction.
- **171 (the MCP adapter).** (1) The `ls`, `tree` and `glob` tool
  schemas gain `after` (string) and `limit` (integer, minimum 1) from
  `PARAMS`, with no adapter code. (2) When a call names no `limit`,
  the adapter passes `limit=LISTING_PAGE` (subject to §1.1's marker).
  (3) `structuredContent` carries `next_after`. When the text cap
  elides rows of a paged result, the adapter sets `next_after` to the
  last shown row's path: the rows are in path order, so resuming there
  serves exactly the elided rows. The `vfs.elided` warning stays. (4)
  §2.4's paging hint for `ls`, `tree` and `glob` names `after=<last
  shown path>` instead of the `cli` `sed -n` form. (5) The three tool
  descriptions say, in one sentence each: pass `next_after` back as
  `after`; a key never expires; every page is checked against your
  rights. (6) A key in tool input is gated like a path and needs no
  binding to a principal (§1.2 reason 4), so SEP-2567's possession
  check is satisfied without state.
- **172 (the WASI Python runtime).** The guest door's `vfs.ls`,
  `vfs.tree` and `vfs.glob` take `after` and `limit` and pass them
  through. The mount provider's `list` (the 2026-10-23 WASI memo §2)
  drains pages of `LISTING_PAGE` until `next_after` is `None`, so
  `os.listdir` on 10,000 children issues 10 `ls` calls (counted).

Spec 180 (history and the bounded `sweep`) takes this spec's shape:
`sweep(limit=)` returns `Result.next_after`, accepts `after=`, and
merges per-mount pages with `frontier_page`.

## ADR amendments this spec needs

- **ADR 087 pin 3:** the key is the last row's path (`after=<path>`),
  not a bare name. `ls` seeks on `(parent_id, name)` using the key's
  last segment; `tree` and `glob` seek on `path`. A batch `ls`
  (`observations=`) takes no cursor. The kernel has no default page;
  the fronts page (lean, §1.1).
- **ADR 087 pin 12:** carried as the lean: the field is
  `Result.next_after`; set algebra and `merge` drop it, enrichment
  keeps it, rebase moves it.
- **ADR 087 pin 14:** the `ls`, `tree` and `glob` rows of the
  access-path table are §4's.
- **ADR 010:** `Result` gains `next_after` with the rules of §1.4.
- **ADR 033 §3 and its deferral:** closed. The read-family cursor is
  a plain path key, not SEP-2567's opaque handle, because a keyset
  position needs no state, never expires and grants nothing (§1.2).
  `grep`, `glean` and `graph` stay without a cursor.
- **ADR 074:** two listing indexes lead with or include `deleted_at`,
  so a tombstone in a listing's key range costs no read work on a
  page; the trash head's listing is the stated exception (§2.1).
- **ADR 004** (the path cache): `depth` joins `path` as a regenerable
  cache column, written at the same sites (§2.5).
- `open-questions.md`, "MCP 2026-07-28: long-batch execution model":
  the read-family cursor half is owned by spec 176.

## Landing notes

(Filled in on landing, per slice.)

## Appendix A. The probes (EXECUTED)

Three runs, all on 2026-10-24 at HEAD `ba77449`, from the repo root
under `uv run`. The two new scripts lived in the session scratchpad.
Counts only; nothing is timed.

**`cursor_probe.py`.** A SQLite file database built through vfs as the
system actor: `/big` with 10,000 files in one batch; `/d` with 1,000
files, the first 900 then deleted in one call; `/s` with 1,000 files,
9 of every 10 deleted; `/n` with 10 directories of 100 files. The
database was then opened with stdlib `sqlite3` and
`PRAGMA case_sensitive_like = ON` (as vfs sets it). The page
statements of §2.1 and §2.4 ran with every index-usable predicate in
plain SQL and every other test in one registered SQL function, the
only residual term, which counts each row the index range hands over.
That count is "rows visited". Each listing was drained page by page
with the key rule of §1.3. Then the index changes of §2.2 were applied
and the same drains ran again. Output:

```text
live children via fs.ls: {'/big': 10000, '/d': 100, '/s': 100}
rows in each (parent_id, name) range, live and tombstoned: {'/big': 10000, '/d': 1000, '/s': 1000}
--- today's indexes ---
ls /big limit=1000: pages=10 statements_per_page=1 rows=10000 distinct=10000 in_order=True returned_per_page=[1000 x 10] visited_per_page=[1001, 1001, 1001, 1001, 1001, 1001, 1001, 1001, 1001, 1000]
  plan, first page: SEARCH vfs_entries USING INDEX sqlite_autoindex_vfs_entries_1 (parent_id=?)
  plan, later pages: SEARCH vfs_entries USING INDEX sqlite_autoindex_vfs_entries_1 (parent_id=? AND name>?)
  union equals the 10,000 written: True
ls /d (first 900 of 1,000 deleted) limit=10: pages=10 rows=100 distinct=100 in_order=True visited_per_page=[911, 11, 11, 11, 11, 11, 11, 11, 11, 10]
ls /s (9 of every 10 deleted) limit=10: pages=10 rows=100 distinct=100 in_order=True visited_per_page=[101, 110, 110, 110, 110, 110, 110, 110, 110, 109]
tree /s limit=10: pages=10 rows=100 distinct=100 in_order=True visited_per_page=[101, 110, 110, 110, 110, 110, 110, 110, 110, 109]
  plan: SEARCH vfs_entries USING INDEX ix_vfs_entries_path (path>? AND path<?)
tree /big limit=1000: pages=10 rows=10000 distinct=10000 in_order=True visited_per_page=[1001 x 9, 1000]
tree /n max_depth=1 (10 dirs x 100 files) limit=5: pages=2 rows=10 visited_per_page=[506, 605]
--- with (parent_id, deleted_at, name) added and (deleted_at) widened to (deleted_at, path) ---
ls /big limit=1000: pages=10 rows=10000 distinct=10000 in_order=True visited_per_page=[1001 x 9, 1000]
  plan, later pages: SEARCH vfs_entries USING INDEX ix_probe_parent_live_name (parent_id=? AND deleted_at=? AND name>?)
  union equals the 10,000 written: True
ls /d (first 900 of 1,000 deleted) limit=10: pages=10 rows=100 distinct=100 in_order=True visited_per_page=[11, 11, 11, 11, 11, 11, 11, 11, 11, 10]
ls /s (9 of every 10 deleted) limit=10: pages=10 rows=100 distinct=100 in_order=True visited_per_page=[11, 11, 11, 11, 11, 11, 11, 11, 11, 10]
tree /s limit=10: pages=10 rows=100 distinct=100 in_order=True visited_per_page=[11, 11, 11, 11, 11, 11, 11, 11, 11, 10]
  plan: SEARCH vfs_entries USING INDEX ix_probe_deleted_path (deleted_at=? AND path>? AND path<?)
tree /big limit=1000: pages=10 rows=10000 distinct=10000 in_order=True visited_per_page=[1001 x 9, 1000]
tree /n max_depth=1 (10 dirs x 100 files) limit=5: pages=2 rows=10 visited_per_page=[506, 605]
```

(Repeated per-page lists are shortened as `[1001 x 9, 1000]`; the
statement count per page was 1 in every drain.)

How to read it:

- Every drain is correct on both index sets: 10 pages, no repeat, no
  loss, path order. The keyset alone is enough for correctness.
- Tombstones cost read work today: 911 rows for a page of 10 when the
  first 900 are deleted, and 110 for 10 when they are interleaved.
  With the liveness term in the index the cost is `limit + 1`.
- Depth is the one bound neither index set gives: 506 and 605 rows
  for pages of 5. Slice C's `depth` column is for this.

Limits: SQLite only; the real engines are task 9. Rows visited are
counted by a function SQLite calls per delivered row, not by the
engine's own counter, which the bundled build lacks.

**The 10,000-row write.** Study 05's `ls_10k.py`, re-run unchanged at
`ba77449`: `write(entries=10000, parents=True)` issued 38 statements
(`BEGIN` 1, `INSERT` 14, `SAVEPOINT` 10, `RELEASE` 10, `SELECT` 2,
`UPDATE` 1); the study's 40 included two `DELETE`s that `4459271`
removed. The `ls` lines were unchanged.

**`counts_today.py`.** `InMemoryStorage`, 10,000 files under `/big`, a
`read` grant to `alice` on `/big` under a `none` root posture;
statements per call after one warm call:

```text
system ls /big          rows=10000 statements=3 {'BEGIN': 1, 'SELECT': 2}
system tree /big        rows=10000 statements=3 {'BEGIN': 1, 'SELECT': 2}
system glob /big/*.txt  rows=10000 statements=2 {'BEGIN': 1, 'SELECT': 1}
alice  ls /big          rows=10000 statements=5 {'BEGIN': 1, 'SELECT': 4}
alice  tree /big        rows=10000 statements=5 {'BEGIN': 1, 'SELECT': 3, 'WITH': 1}
alice  glob /big/*.txt  rows=10000 statements=4 {'BEGIN': 1, 'SELECT': 3}
```

## In one line

`ls`, `tree` and `glob` take `after=` and `limit=` and return the last
row's path as `Result.next_after`; pages seek on indexes that skip
deleted rows, so each page costs a fixed number of statements and
about `limit` rows read, and one frontier rule merges pages across
mounts with nothing repeated and nothing lost.
