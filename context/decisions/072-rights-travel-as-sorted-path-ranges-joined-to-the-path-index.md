# 072. Rights Travel as Sorted Path Ranges, Joined to the Path Index

- **Status:** accepted 2026-09-30 (Clay: "yes to all three, lets start
  with only this for now" — the range-join direction; the vector-leg
  count gate and path-ordered chunk numbers are ruled in and get their
  own ADRs). Amends ADR 071 rule 1 and ADR 067 rule 2's predicate form.
  Rules 1, 2, 4 and 5 amended 2026-10-01 from the five-engine study
  (Clay: "go with your recommendations", then "can we drop vector for
  right now?"); see *Validation*.
- **Date:** 2026-09-30
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay, 2026-09-30). Drafted by Claude from four
  research memos:
  `../research/2026-09-30-search-document-level-security-prior-art.md`,
  `../research/2026-09-30-path-acl-ranges-prior-art.md`,
  `../research/2026-09-30-authz-list-filtering-prior-art.md`,
  `../research/2026-09-30-filtered-vector-search-prior-art.md`,
  and the measurement that prompted them,
  `../research/studies/2026-09-29-partial-glean-latency/`.

## Context

ADR 067 compiles a caller's rights into a literal SQL predicate: one
arm per covering prefix, `path = :p OR path LIKE :p || '/%'`, minus
holes, plus owner arms. ADR 071 rule 1 splits a predicate too wide for
one statement into several OR-clauses and merges the results.

`glean` for a caller with partial access was measured on SQLite at
50,000 files. With 1 to 5 grants it cost about the same as the
whole-mount fast path. With 100 grants it cost about 440 ms, and with
500 grants about 2 s, even for a rare word. The profile put nearly all
of it in two SQL statements: the visible-corpus count and the vector
leg's distance query. Each one started from the chunk table and tested
every chunk against every arm. The cost was chunks × grants. The path
index was never used.

Four studies looked at how other systems avoid this:

- **No mature system tests every row against every grant.** SpiceDB
  walks outward from the grants with index lookups. Postgres row-level
  security guidance keeps the policy text fixed and puts the user's
  grants in data. Oso Cloud joins grant facts as rows. Only OPA inlines
  grants as an OR list, which is vfs's shape today.
- **Search engines keep the filter's cost flat** with a sorted index
  (Lucene's index-sorted range query is two binary searches) or a
  cached filter bitset (Elasticsearch and OpenSearch document-level
  security). None copies a folder's grant onto every file beneath it
  without paying a re-crawl on every change; the ones that stay fresh
  store a reference, which is what a vfs prefix grant already is.
- **A caller's covering prefixes never overlap,** so they are sorted
  byte ranges. Joined to the `path` index, each range is one index
  seek, and the cost follows the rows the caller can see.
- **Starting from entries, not chunks,** is the other half: find the
  visible entries through the path index first, then touch only their
  chunks.

Measured on vfs's own table shapes (50k to 100k rows):

| shape | 100 grants | 500 grants | 5,000 grants |
|---|---|---|---|
| SQLite, today's OR of `LIKE` arms (corpus count) | 458 ms | 1,874 ms | 10 s, or refused past SQLite's expression depth |
| SQLite, entries filtered first | 6.5 ms | 36 ms | — |
| SQLite, range join, ranges in one bound value | — | 6 ms | 5 ms |
| Postgres, today's arms | 15 ms | 148–185 ms | 290–322 ms |
| Postgres, range join via `unnest` | — | 21 ms | 28–72 ms |
| SQLite vector leg, admitted entries first | 9 ms (was 214) | 42 ms, one statement | — |

Two shapes were measured and rejected: a literal `CASE` tree (Postgres
JIT compilation turned 27 ms into 1.4 to 20 s) and temporary tables (a
fixed 3 to 10 ms, and a read that writes).

## Options considered

- **Keep OR'd arms, change `LIKE` to byte ranges.** Two to six times
  faster on Postgres. Still grows with the grant count, still fans past
  the budgets, and still hits SQLite's depth cap near a thousand arms.
- **Filter entries first, arms unchanged (a semi-join).** Removes the
  chunks × grants product on SQLite. The entries pass still grows with
  the grant count.
- **A range join with the ranges in one bound value.** The statement
  text is the same for every caller, one bind carries any number of
  ranges, and each range is one index seek. Needs a table function per
  dialect to unpack the value.
- **Copy grants onto rows (early binding by value).** Rejected: a grant
  on a folder would rewrite every row beneath it.
- **A per-caller visible-set cache.** Held in reserve: nothing yet keys
  it safely against writes, and the range join may make it unnecessary.

## Decision

1. **Rights compile to a sorted list of disjoint pieces of two kinds:**
   *exact paths*, matched as `path = p`, and *open ranges*, matched as
   `lo < path < hi` in bytewise order. A prefix `p` gives the exact
   path `p` and the open range `(p || '/', p || '0')`. They stay two
   pieces because bytes below `/` (such as `-`) sort between a prefix
   and its children: `/a-b` lies between `/a` and `/a/`. Holes are cut
   out of an arm's pieces, and where an inclusive bound is a lawful
   path it becomes an exact path beside the open range. No bound is
   ever a path plus a low byte: SQL Server pads the shorter string
   with spaces before comparing, so `p < p || '\x01'` is false there
   (found by this ADR's validation). The root is the exact path `/`
   plus the open range `('/', '0')`. The pieces are computed once per
   resolution and memoized on it, keyed by grant revision like the
   resolution itself.
2. **The pieces travel as one bound value per kind, unpacked by the
   engine, and join to the `path` index.** The unpacking spelling is a
   `DialectProfile` fact, because SQLAlchemy takes no position on it:
   `json_each` on SQLite, `unnest` of two arrays on Postgres,
   `OPENJSON` on SQL Server, `JSON_TABLE` on MariaDB. Oracle declares
   none (see rule 5). The statement text does not change with the
   caller's grants.
3. **Owner arms are their own branch.** "Rows this member owns, under
   the other members' ranges" joins through the `owner_id` index in a
   separate `UNION` branch. Mixed into the same OR, it blocks the range
   seeks.
4. **Chunk-side statements filter entries first, through a derived
   table:** the visible-corpus count joins the visible entries as
   `(SELECT ...) v` on `entry_id`, never `entry_id IN (SELECT ...)`
   and never by testing chunk rows against the rights. The `IN` form
   took 5 to 55 s on MariaDB and Oracle in the validation. The vector
   leg keeps ADR 071's clauses for now (Clay, 2026-10-01); it moves
   with the count-gate ADR, which must choose between an index walk
   that stops early and the visible set first.
5. **A dialect with no unpacking spelling keeps ADR 071's arms and
   fan unchanged:** Oracle, whose `JSON_TABLE` join measured no gain
   and lost at 500 grants, and every unknown dialect. The literal
   small-rights form first drafted here is not built: the validation
   found no consistent gain for it over the join, and one form per
   dialect keeps the code to two shapes.
6. **Unchanged:** `Rights.admits` in app code remains the authority on
   every row (ADR 071 rule 2); the grant model, groups, the meet, the
   owner floor, posture and road visibility (ADR 070) are untouched.
   Nothing is written on a read.

## Validation (2026-10-01)

Study `../research/studies/2026-10-01-range-join-engines/`: 41,421
entries and 121,200 chunks per engine, six callers (1 to 500 grants, an
open root with 50 holes, an owner arm), each answer checked against
`Rights.admits` over every row. Every shape returned exactly the right
rows on all five engines. Listing the visible entries, 100 grants
(ms):

| engine | arms (today) | range join |
|---|---|---|
| SQLite | 176 | 5 |
| Postgres | 10 | 4.6 |
| MariaDB | 206 | 11 |
| SQL Server | 1,299 | 15 |
| Oracle | 230 | 196 |

The visible chunk count through the derived table stayed between 5
and 52 ms on SQLite, Postgres, MariaDB and SQL Server from 1 to 500
grants. Oracle's join gained nothing and, at 500 grants, took 960 ms
against the arms' 721.

## Consequences

- A caller's read cost follows what it can see, not how many grants it
  holds. The measured shapes stay flat from 100 to 5,000 grants.
- The multi-clause fan and its app-side deduplication leave the common
  path on four engines; they remain for Oracle, unknown dialects and
  the vector leg. The visible set is one statement, so its count needs
  no merging.
- **Validated before code** (see *Validation*). SQL Server, feared the
  risk, gained most; Oracle is the open one, and a better Oracle
  spelling is a follow-up probe.
- Large rights make one large bound value (a JSON string or two
  arrays). Its size limits per driver must be checked; none is a
  designed cap.
- Follow-ups already ruled in (Clay, 2026-09-30), each in its own ADR:
  the vector leg's count gate (which now also moves the vector leg onto
  the visible set where that wins) on approximate-index dialects (which also
  fixes pgvector's measured 0.70 to 0.85 recall under a selective
  filter), and path-ordered chunk numbers per lexical epoch (which make
  the visible `df` and counts range arithmetic in the Rust kernel).
