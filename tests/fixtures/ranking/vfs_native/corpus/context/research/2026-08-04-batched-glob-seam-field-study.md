# Batched glob seam: field study of wire shapes, root assertions, and SQL fan limits

- **Status:** final — supersedes §2 ("Dispatch shape") of
  `2026-07-31-glob-pattern-seam-routing.md`; every other section of
  that memo stands. Feeds spec 092.
- **Date:** 2026-08-04
- **Owner:** Clay Gendron
- **Method:** five research agents run in parallel during the ADR
  031 ratification session — four read-only studies of reference
  checkouts under `~/Git/Repos/` (zoekt+codesearch; ripgrep+BSD/V7
  find; fsspec+opendal+pyfilesystem2; sqlite+postgres+sqlalchemy)
  and one executed benchmark (sqlite 3.37.2, 200k rows, scripts
  preserved in session scratch, tables reproduced below). All
  citations are file:line into the checkouts at their 2026-08-04
  revisions.

## 1. Wire-shape precedent (zoekt, codesearch)

**"Shards receive predicate trees with routing upstream" —
confirmed, with a caveat.** zoekt's searcher seam is one method
taking one query AST (`api.go:910`); path constraints are ordinary
atoms in that tree (`query/query.go:396-403` Substring with
`FileName: true`; `:317-320` FileNameSet); shard pruning happens
upstream in `selectRepoSet` (`search/shards.go:690-700`) against
cached per-shard metadata. The caveat: routing predicates **stay in
the tree** and both tiers evaluate them — upstream pruning is an
optimization layered on top, not a replacement. zoekt is not
precedent for stripping scope information so the backend never sees
it; it is precedent for scope-as-predicate with routing as pruning.

**"No studied system turns N roots into N wire calls" — confirmed.**
No per-root or per-pattern fan-out exists in either codebase; fan-out
is over storage units (shards) carrying the identical query. Two
strengthening facts: (a) `typeRepoSearcher.eval`
(`search/eval.go:94-124`) resolves N repos and **rewrites them into
one set-valued atom in one call** — the batch-tuple shape in
production; (b) set-valued atoms (`RepoSet`, `FileNameSet`) exist
*specifically* because per-item wire encoding was too expensive, and
zoekt hand-wrote their codec for a 60% speedup
(`query/marshal.go:95-119`). codesearch collapses N roots at *index*
time (`index/merge.go:132-143`) — per-root queries do not exist as a
concept there.

Two postures worth carrying: zoekt has **no cardinality cap** on its
set atoms (sets larger than the shard count are tolerated,
`shards.go:462-466`), and it **fails open** when routing metadata is
unknown — include the shard and suppress the optimization, never
exclude (`shards.go:479-484`).

## 2. Multi-root traversal and operand assertions (ripgrep, find)

**One compiled matcher, N roots — confirmed** in ripgrep (one
`Override` built once, `hiargs.rs:1246-1267`; one walk seeded with
all roots, `hiargs.rs:885-929`; parallelism across directory
entries, never across roots, `walk.rs:1452-1535`), BSD find (one
plan, one `fts_open` over the whole operand array,
`main.c:133-148`), and V7 find.

**Upfront operand assertion has direct precedent.** ripgrep's
parallel walker stats every operand on the main thread before any
worker spawns (`walk.rs:1462-1497`); BSD find stats all roots inside
`fts_open` (`fts.c:148-157` — `FTS_NOSTAT` never applies to roots).
Both report every bad operand, keep searching good ones, and exit
nonzero. Sharpest detail: find's readdir-race forgiveness
(`-ignore_readdir_race`) explicitly applies only at `fts_level > 0`
(`find.c:195-197`) — *assert roots, tolerate races below* is encoded
in the source.

**The assert-by-searching hole exists in ripgrep too**: when a
short-circuit skips the walk (`--max-count=0`,
`hiargs.rs:532-540` → `main.rs:87`), operand errors silently vanish
— the same fused-assertion bug class as our subsumption gap. A
separate assertion phase is right by construction.

**Precedent conflict on the root row (must be recorded):** find runs
its expression over the root entry itself (`find.c:236`), which is
vfs's rule; **ripgrep exempts explicitly-named operands from `-g`
entirely** (`walk.rs:1149-1152` depth-0 skip;
`haystack.rs:131-139`; verified: `rg --files -g '*.py' README.md`
prints `README.md`). The differential battery's find and rg legs
disagree on this case — the rg leg needs it in the allowlist.

**A test we did not know we needed:** sharing one matcher across
roots caused real order-dependence bugs in ripgrep (per-root base
paths leaked into shared cached state; issues #3376/#3419/#3320,
fixed by moving `absolute_base` per-root, `dir.rs:92-112`); the fix
ships with tests running roots in both orders
(`tests/misc.rs:745-810`). Multi-root glob should pin root-order
independence.

## 3. Storage-layer batching, missing roots, capability degradation

**No studied storage layer batches existence checks as a protocol
call.** fsspec's batch shapes are concurrency-windowed fan-outs of
single-path coroutines (`asyn.py:204`), with per-path outcomes via
positional `return_exceptions` lists and per-method `on_error`
policies. The best per-path batch-result model is opendal's batch
delete: `succeeded`/`failed` vectors carrying the path beside each
error, with an enforced length-equality invariant
(`batch_delete.rs:49-56, 107-112`), and retryable-vs-permanent
triage per path (`:120-126`).

**The anti-pattern is in the field:** fsspec's multi-root
`expand_path` raises only when the *entire* batch is empty
(`asyn.py:928-929`) — 4 missing roots out of 5 are invisible. And in
all three libraries, the glob result alone cannot name which of N
roots was missing. This is the exact failure mode the probe exists
to close.

**Missing-base behavior splits by architecture:** fsspec and opendal
default to silent-empty (opendal normatively — prefix-based listing
"does not require the parent directory to exist",
`operator.rs:1741-1745`); pyfilesystem2, the POSIX-shaped one,
raises `ResourceNotFound`. vfs's find-operand law sits with the
POSIX branch, now carried by a probe instead of the scan.

**Capability-degraded existence checks — the probe-fallback
question:** opendal refuses to coerce "backend cannot stat" into
"path missing": `Unsupported` propagates through `exists` as its own
outcome (`operator.rs:509-516`) — the precedented result shape is
three-way (present / absent / undeterminable), never a two-way
collapse. The precedented fallback for a backend without cheap
point-reads is a **bounded list used as a weaker signal**
(`Operator::check`: limit-1 list, NotFound ⇒ OK,
`operator.rs:336-359`; fsspec HTTP `_isdir` via `ls`). And the
list/stat race tolerance to copy: a NotFound *during* concurrent
enrichment means "skip, keep going," not "fail"
(`complete.rs:189`).

**Seam confirmation:** nobody pushes a pattern across the storage
seam today — fsspec forwards only an optional literal-prefix *hint*
(`asyn.py:833-836`; correctness never depends on it), opendal's glob
RFC (`6209_glob_support.md`) keeps base and pattern separate with
client-side matching primary. The patterns-tuple seam goes further;
zoekt (§1) is the system that actually did it.

## 4. SQL engine limits and planner behavior for wide OR fans

Condensed fact table (full citations in the agent transcript;
load-bearing rows verified against source):

| Engine | Fact | Value | Bounds |
|---|---|---|---|
| sqlite | `SQLITE_MAX_EXPR_DEPTH` | 1000 (runtime-lowerable) | expression tree **height**; flat OR parses left-deep so height ≈ arms + per-arm depth (`parse.y:1349`, `expr.c:852-864`) |
| sqlite | `SQLITE_MAX_VARIABLE_NUMBER` | 32,766 (999 pre-3.32) | bind parameters |
| sqlite | `SQLITE_MAX_COMPOUND_SELECT` | 500 | UNION-ALL arms |
| sqlite | `SQLITE_MAX_LIKE_PATTERN_LENGTH` | 50,000 | one LIKE pattern |
| postgres | *(no expression-depth limit)* | — | OR chains flatten to one N-ary node (`gram.y:20377-20391`); only `max_stack_depth` (bytes, bounds nesting not width) |
| postgres | protocol parameters | 65,535 | binds per statement |
| mssql (via sqlalchemy) | parameter cap | 2,099 | binds (`mssql/base.py:3139-3142`) |
| oracle | 1,000-element IN list | unmodeled anywhere in sqlalchemy | our `DialectProfile` remains the owner |

**Measured on our exact statement shape:** 996 OR arms parse; **997
fail** (`Expression tree is too large`). Mitigation verified:
**balanced parenthesization** of the OR set reduces height to
log₂(N)+arm-depth — 5,000 balanced arms parse fine.

**Planner facts that shape the executor:**

- **OR optimization is all-or-nothing on both engines.** sqlite's
  case-3 analysis bails the moment one arm is non-indexable
  (`whereexpr.c:729`); postgres's `generate_bitmap_or_paths` drops
  the whole BitmapOr if any single arm matches no index
  (`indxpath.c:1735-1744`). One stray arm ⇒ full scan. Arms must be
  uniform prefix form.
- **The LIKE-prefix rewrite has collation preconditions.** sqlite:
  default LIKE is case-insensitive, so its generated range terms
  carry NOCASE and a plain BINARY path index cannot serve them —
  full scan until either `case_sensitive_like=ON` or a
  `COLLATE NOCASE` index exists (`whereexpr.c:1427`; measured both
  ways). postgres: prefix rewrite requires a `Const` pattern and
  either C locale or a `text_pattern_ops` index
  (`like_support.c:266-317`; `indices.sgml:1420-1450`).
- **Bound-parameter LIKE prefixes defeat statement caching** on
  sqlite: the statement is re-prepared whenever the parameter is
  rebound (`whereexpr.c:318-320`).
- **SQLAlchemy models essentially none of this** — its only
  statement-shaping budgets are INSERT-scoped
  (`insertmanyvalues_*`). Candidate `DialectProfile` fields this
  study justifies: expression-depth cap + whether OR chains
  accumulate depth; a general (non-INSERT) bind budget; the IN-list
  cap (already ours); compound-SELECT cap; the LIKE-prefix index
  requirement (a correctness-of-*plan* fact, not of results).

## 5. Executed benchmark (sqlite, 200k rows, 10k dirs)

Batched OR fan vs per-root queries, identical row sets verified,
medians of 3:

| K roots | per-root | fan C=50 | fan C=200 | fan C=500 |
|---|---|---|---|---|
| 100 (scan mode) | 1.09s | 0.59s | 0.58s | 0.58s |
| 1,000 (scan mode) | 10.78s | 5.86s | 5.70s | 5.53s |
| 10,000 (scan mode) | 109.1s | 59.0s | 57.4s | 55.3s |
| 100 (indexed) | 1.6ms | 1.0ms | 1.0ms | 1.0ms |
| 1,000 (indexed) | 17.2ms | 11.2ms | 11.7ms | 13.1ms |
| 10,000 (indexed) | 166.6ms | 111.8ms | 111.2ms | 111.0ms |

- **The fan wins at every K in both modes** (~1.8-2.0× scan-bound,
  ~1.4-1.5× indexed) and nearly all of the win is captured by C=50;
  widening past C≈200 buys 1-6%. Sweet spot **C≈200**, leaving
  headroom under every engine cap. Ceilings measured: fan fails at
  C=1000 (expression depth), UNION ALL at C=501 (compound cap).
- **The ext-conjunct cliff (design-changing):** `AND ext IN (…)`
  bolted onto the OR group **abandons MULTI-INDEX OR** — sqlite
  switches to the ext index and brute-forces all 200 LIKE arms
  against ~133k rows: 11.7ms → 4.14s, **~350×**. The OR optimization
  fires only when the whole WHERE is a pure OR of indexable terms.
  The call-level ext *fact* must therefore be **rendered inside each
  arm** (distribution is semantics-preserving:
  (A∨B)∧e ≡ (A∧e)∨(B∧e)) or applied client-side — never ANDed
  beside the fan.
- **The collation cliff dwarfs fan tuning:** default-LIKE scan mode
  vs indexed mode is 100-1000×; no chunk-width choice recovers it.
  Making the prefix rewrite fire (pragma, GLOB, or matching index
  collation) is worth more than every other knob combined.
- UNION ALL: equal to per-root in scan mode, fastest shape in
  indexed mode (~17% ahead at K=10k) — but capped at 500 arms and
  it duplicates overlapping rows; a candidate per-dialect rendering,
  not the default.
- Per-statement overhead on embedded sqlite is ~10µs, so the fan's
  win here is scan/setup amortization; on networked engines
  round-trip amortization should widen the gap, not narrow it.

## Consequences for spec 092

1. Chunk width defaults to ~200 arms/statement, budgeted by the
   tighter of: bind params, IN-list cap, **expression depth** (new
   budget; sqlite 1000 with left-deep accumulation), compound cap if
   a UNION rendering is ever used. Balanced parenthesization is the
   escape hatch if a wider chunk is ever wanted.
2. The WHERE must render as a **pure OR of uniform prefix-form
   arms**; all ext facts (caller-level and derived alike) render
   inside arms. The ADR's semantic split stands (caller ext is one
   call-level *fact*); its *rendering* is per-arm by distribution.
3. A `DialectProfile` gains the fields SQLAlchemy lacks (expression
   depth + accumulation shape, general bind budget, compound cap,
   LIKE-prefix index requirement).
4. The probe returns three-way per-root outcomes (present / absent /
   undeterminable) with the path carried beside each error;
   capability-missing is never coerced to absent; a bounded-list
   fallback is the precedented degraded mode; NotFound during the
   concurrent race means skip-and-continue.
5. The differential battery allowlists the find/rg divergence on
   explicitly-named operands (vfs follows find); acceptance adds a
   root-order-independence case.
6. Fail-open posture wherever routing consults cached facts: include
   and stop optimizing, never exclude.
