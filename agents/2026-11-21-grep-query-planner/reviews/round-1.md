# Round 1: adversarial review of the grep planner design

**Verdict: Not yet.** Decision 6 loses matching rows in two ways, both run. The rest of the design holds on rows, and the changes it needs are bounded: a branch rule that looks at the scope's size, a probe whose cost really is bounded by T, and a stated plan for patterns with no indexable literal.

The pinned code is `5dfdcc79`, and `$PIN` is the `src` of a checkout of that commit. Scripts are in `$R1 = agents/2026-11-21-grep-query-planner/reviews/scripts/round-1/`, and their saved output sits beside them as `*.out`. Every script runs from the repository root as `PYTHONPATH=$PIN uv run python $R1/<script> <db>`. `<db>` is the sandbox `linux.db`, except for r02, which builds its own store at `$R1/r02.db`. Every run used SQLite. No Postgres leg was run. Where a finding should hold on Postgres too, it says why.

Load was 2.7 to 13 during the session. Every timing below is marked *loaded*, and no finding rests on a timing. The findings rest on counts and row sets.

## Findings, high to low

### H1. Decision 6: the literal "from the same extraction that builds the grams" is not a necessary condition of a case-sensitive match

Script: `r02_literal_not_necessary.py`. It builds a fresh store with these files under `/a`:

- `lower.c` holds `kmalloc(8)`.
- `upper.c` holds `KMALLOC`.
- `other.c` holds `hello world`.

For each pattern, the script runs vfs's own grep, which is the authority on what matches. It then reads the surviving literal of each OR branch from `code_grams`' own `_compile_seq`, applying the same fold dedupe that `_fragment_query` applies. Last, it runs decision 6's `instr(content, :lit) > 0`, ORed over the branches. Observed:

```
'[Kk]malloc' {'case_mode': 'sensitive'}      grep returns ['/a/lower.c']; extraction literals ['Kmalloc']; ROWS LOST: ['/a/lower.c']
'Kmalloc|kmalloc' {'case_mode': 'sensitive'} grep returns ['/a/lower.c']; extraction literals ['Kmalloc']; ROWS LOST: ['/a/lower.c']
'Kmalloc|kmalloc' {'case_mode': 'smart'}     grep returns ['/a/lower.c']; extraction literals ['Kmalloc']; ROWS LOST: ['/a/lower.c']
'(?i)kmalloc' {'case_mode': 'sensitive'}     grep returns ['/a/lower.c', '/a/upper.c']; extraction literals ['kmalloc']; ROWS LOST: ['/a/upper.c']
'(?i:KMALLOC)' {'case_mode': 'sensitive'}    grep returns ['/a/lower.c', '/a/upper.c']; extraction literals ['KMALLOC']; ROWS LOST: ['/a/lower.c']
```

Three properties of the extraction cause this. Each one is sound for a folded index and unsound for a raw, case-sensitive substring test:

- `_class_members` dedupes a class's members after folding, so `[Kk]` keeps only `K`.
- `_fragment_query` dedupes OR branches by their folded gram set, so `Kmalloc|kmalloc` keeps one branch.
- The planner ignores inline flags on purpose ("Case flags need no tracking"), so `(?i)` and `(?i:...)` leave case-sensitive literals behind, even on a call whose `case_mode` is `sensitive`.

So "the call is case-sensitive" is not a property of the call's `case_mode`. The literal test needs its own extraction. That extraction must keep raw branches without the fold dedupe, and it must stand down under any case-insensitive scope in the pattern. Otherwise the literal test must fold on both engines. The same rows are lost on Postgres, because `strpos` is just as case-sensitive as `instr`, and the extraction is engine-independent Python.

### H2. Decision 6 as written applies under `invert_match`, and it drops exactly the rows an inverted grep returns

Script: `r02_literal_not_necessary.py`, same store. Observed:

```
'kmalloc' {'case_mode': 'sensitive', 'invert_match': True}  grep returns ['/a/other.c', '/a/upper.c']; extraction literals ['kmalloc']; instr keeps ['/a/lower.c']; ROWS LOST: ['/a/other.c', '/a/upper.c']
```

Decision 6 turns on when "the gram plan yields, for every OR branch, a literal" and the call is case-sensitive. It names the scan side's fetch explicitly. `invert_match` runs the scan side (`scan_all` in `grep.py`), and its gram plan still yields literals. A file that lacks the literal has no matching line, so every one of its lines is returned. Those are exactly the files the test removes. Decision 6 must exclude `invert_match` in so many words. This holds on both engines.

### M1. Decision 3: the probe's cost is bounded by the scope, not by T, whenever rows in the range fail its other terms

Script: `r03_probe_visits.py`. It uses read-only raw SQL and counts every row the access path hands to the WHERE clause. The count comes from a Python function placed before the residual terms. The plan in every case is `SEARCH vfs_entries USING INDEX ix_vfs_entries_path (path>? AND path<?)`. T = 1,024.

| root | rows in range | live probe: returned / visited | trash-side probe (`deleted_at IS NOT NULL`): returned / visited | partial view admitting 10 rows: returned / visited |
|---|---|---|---|---|
| /drivers/md | 301 | 296 / 301 | 0 / 301 | 10 / 301 |
| /drivers/gpu | 8,625 | 1,025 / 1,085 | 0 / 8,625 | 10 / 8,625 |
| /drivers | 39,794 | 1,025 / 1,070 | 0 / 39,794 | 10 / 39,794 |

The live probe behaves as R2 says. Two probes the decision also requires do not:

- **The trash side.** A grep under `/.vfs/trash/<root>` probes for tombstoned rows, and walks every live row in the range to find them.
- **A partial caller's view.** Decision 3 reads "live, visible" rows. At the reference deployment every call is judged against grants. A caller who sees 10 rows under a root of a million files makes the probe visit the million.

A live root that holds many tombstones costs the same way. The view was simulated with a function, because the sandbox has a single `everyone_level` of 5.

The fix that keeps the bound: the probe counts range rows on the path index alone, so T bounds what it visits, and the view and the tombstone side are judged on the n ≤ T rows it returns. On Postgres the same predicate is an index range scan with a filter, so the visits should match. That was not run.

### M2. Decisions 4 and 5: "U ≤ SCAN_TIER_BUDGET → range-scoped" takes the plan that grows with the corpus's candidates over the one that grows with the scope

Script: `r05_branch_rule.py`. It prototypes both ladder branches of decision 4 inside vfs's own grep:

- *ranged*: no allow-list, with the roots' range as pushdown on the candidate fetch.
- *allowed*: an allow-list built by range and met by the kernel.

The script disables `_ladder_defers` so both branches run the ladder, and it counts exactly the ids the candidate entry fetch resolves. Rows were identical in all 25 pairs. A selection:

| root (files) | pattern (U) | ranged: ids resolved | allowed: allow ids / ids resolved | loaded ms, ranged vs allowed |
|---|---|---|---|---|
| /drivers/atm (30) | -EINVAL (17,427) | 17,427 | 30 / 12 | 49.3 vs 31.0 |
| /drivers/md (296) | MODULE_LICENSE (17,330) | 17,330 | 296 / 66 | 51.5 vs 30.1 |
| /drivers/gpu/drm/amd/display/dc (1,033) | -EINVAL (17,427) | 17,427 | 1,033 / 0 | 48.1 vs 25.5 |
| /drivers/media (3,023) | -EINVAL (17,427) | 17,427 | 3,023 / 1,073 | 86.9 vs 69.7 |

The ranged branch resolves the corpus-wide candidate set. On a remote engine that is up to 25,000 bound ids shipped and 25,000 primary-key probes, to keep a dozen rows. The allowed branch resolves at most the scope, and the range allow-list costs about 0.34 µs an id (R2). The rule in decision 4 never looks at the scope's size. Decision 5 prices `F_ladder` as "a one-candidate answer", so it cannot see this term either. The probe has already learned that the scope exceeds T, and an exact range count is cheap. A rule that compares U with the scope's size, or one that always meets the range allow-list when the scope is under the budget, avoids the case. This rests on the counts. The timings are loaded (load 9 to 13) and only agree in direction.

### M3. Decision 4: there is no plan for a pattern with no indexable literal, and today's two paths disagree on it

Script: `r07_unindexable_and_stmt_cost.py`. Over `/mm/tests` (1 file):

```
'a':   database plan -> 0 rows [unindexable_pattern]; in-hand plan -> 1 rows []
'.':   database plan -> 0 rows [unindexable_pattern]; in-hand plan -> 1 rows []
'^$':  database plan -> 0 rows [unindexable_pattern]; in-hand plan -> 1 rows []
'x*':  database plan -> 0 rows [unindexable_pattern]; in-hand plan -> 1 rows []
```

The database path refuses these patterns without `allow_scan`. The in-hand path answers them. Decision 4 says every plan returns the same rows, and its three plans include no scan tier. The spec must choose one of two answers:

- In hand serves an unindexable pattern below T. A pattern's refusal then depends on the scope's size.
- The refusal gate runs before the probe.

Either way, the scan tier (`allow_scan`, `invert_match`) over a scope larger than T needs a named plan. The "What is checked" matrix lists "no indexable literal" but gives no expected answer for it.

### M4. Decisions 2 and 4 against "What is checked": the range allow-list is a new statement bounded by the scope, not by a declared budget

Script: `r08_probe_shape_and_allow_size.py`. Observed: `range allow-list for 7 roots: 1 statement, 78793 ids (84% of 93759 files)`. At the reference deployment the same share is about 8.4 million ids, materialised in Python and handed to the kernel. Decision 4's third bullet routes to this statement exactly when U exceeds 25,000. At ten million files, that is the normal case for any common pattern: 18% of Linux files hold `-EINVAL`.

The spec's check says every statement decisions 3, 4 or 6 add is bounded by T, `SCAN_TIER_BUDGET`, `CONTENT_BYTE_BUDGET` or the membership budget, "none is the corpus". This one is bounded by none of them. Today's segment allow-list has the same profile, and `pathterms.py` acknowledges it. The spec should acknowledge the same profile and name its direction, instead of claiming a bound it does not have.

### M5. Decision 3 against decision 2: the probe, as R2 measures it, omits the root's own row, so in hand would return nothing for a root that is a file

Script: `r08_probe_shape_and_allow_size.py`. Observed: `R2 probe rows for file root /include/linux/dcache.h: 0; vfs grep rows: 1`.

Decision 2 says a root scope takes its rows from the range "plus the root's own row". Decision 3 says the probe reads rows "by range", and R2's `e1_scope_probe.py` measured exactly that. If the probe is built from R2, in hand is chosen for every file root, because zero rows is at most T, and it returns nothing. The r04 parity run below included the root's row in its probe and matched. The spec should state the probe as range OR `path = :root`.

### L1. Decision 7: a weighted mean of statement latencies measures each statement's work, not the round trip

Script: `r07_unindexable_and_stmt_cost.py`. One call's statements span `/drivers/atm -EINVAL: 20 statements, min 0.480 ms, median 0.972, max 37.0 (77x)`. The corpus-wide `i_count` spans 0.341 to 38.6 ms (113x). The figures are loaded, but the spread is the point.

`c_stmt` is meant to be a per-statement fixed cost. Taken as the mean of observed latencies, it absorbs the 18,000-bind fetches and the content batches. That inflates the ladder's `s·c_stmt` more than in hand's, and so it moves T. It also makes the plan of an identical call depend on what other callers ran just before, through shared per-storage state. Rows are unaffected, as decision 7 says. A round trip can be measured on a statement that does no work.

### L2. Decision 8 / R5: the 4-gram column was simulated case-sensitively, while the stored index is one folded stream

Script: `r06_fold_4gram.py`, over nine of R5's patterns. A folded 4-gram rule nominated 26,415 candidates, against 25,820 for the raw rule R5 used. That is a cut of 44.1% instead of 45.3%. The gap is large on one row: for `TODO`, a folded 4-gram index nominates 3,515 against R5's 3,144, so its cut is 0.7% and not 11%. The decision's 35% is close to right in aggregate, but the per-pattern "4 to 16 times" needs the folded rule. The follow-up experiment decision 8 names should simulate folded grams.

### L3. Decision 3: overlapping roots double-count the probe

Script: `r08_probe_shape_and_allow_size.py`. The roots `/drivers`, `/drivers/md` and `/drivers/md/bcache` give per-root rows of 37,340, 296 and 31, which sum to 37,667, against 37,340 distinct rows. A per-chunk probe with `LIMIT T + 1` overstates n and B unless the roots are reduced to their maximal elements first. This costs time only.

### L4. Decision 2: "a scope given as roots, with no glob arm" never occurs at the storage seam

Script: `r01_trace_shape.py`. For `paths=("/drivers/atm",)`, grep_rows receives `globs=('/drivers/atm',)`, the root's literal on the entry-wide channel, and a scope whose arms are `('**',)`. With `globs=("*.c",)`, it receives `globs=()` and arms `('*.c',)`.

So the condition the planner tests is "arms are exactly `**`". Decision 1's "arm that admits a root itself" is a literal pattern on the entry-wide channel, which the seam cannot tell apart from a caller's literal glob. Path equality is exact for both, so this is harmless. The spec should still say it.

## Attacked and held

- **R1 reproduced exactly** (`r01_trace_shape.py`, `r04_plans.py`). The allow-list is 40,262 ids for `/drivers/atm`, 3,958 for `/include/linux/dcache.h`, and 2,462 for `/fs/open.c` with `/fs/read_write.c`. The cause is the root literal's arm, with segments `{drivers}` and a name fact.
- **Decision 1, prototyped** (`r04_plans.py`, mode `d1`: a fully literal allow-list arm resolves by `path = :pattern`). Every pair in the matrix returned the same rows as today, with line spans and match text: 8 scopes (1 to 1,033 files, a file root, two file roots, three roots, overlapping roots) times 9 patterns (rare, common, alternation, anchored, `\b`, case-insensitive, no match, over the budget). The allow-list fell from 40,262 to 39 for `/drivers/atm`, and from 3,958 to 1 for `dcache.h`. With decision 1 alone, the existing `_ladder_defers` already takes the allow-list as the candidate set for small scopes: U is `None` in those rows. It still spends 19 statements where in hand spends 5.
- **Plan parity** (`r04_plans.py`). The range-scoped ladder and in hand (probe with the root's row → `grep(observations=...)`) returned identical rows to today on every pair where U ≤ 25,000. The one DIFF was the range-only prototype at U = 37,102 (`^static int` over three roots), which truncated and lost `/kernel/kcsan`. Decision 4 routes that case to the allow-listed branch. The same truncation kept the `/drivers/atm` rows only because sandbox ids follow path order (`/drivers` sorts before `/kernel`). No element of the design depends on that order.
- **R2's live probe** visits about T rows (1,070 at T = 1,024 over `/drivers`), as claimed (`r03_probe_visits.py`).
- **The range's exactness on Postgres**: `models/rows.py` pins `path` to `COLLATE "C"` there, so `/` sorts before `0`. This was read, not run.
- **`instr` and NUL**: a body with a NUL is refused at write ("content contains null bytes"), so SQLite's NUL handling cannot hide a literal (`r02`).
- **In hand's statement count**: 5 statements in every pair, against 16 to 24 for the ladder plans (`r04`).

## Not attacked

- No Postgres leg was run.
- No real grants were built, so the view in M1 is simulated.
- The trash view was not run through vfs, because the sandbox is read-only and holds no tombstones. M1's trash-side probe is the raw SQL that view would issue.
- Decision 5's "within 20% of the best plan" was not tested, because no quiet window opened.
- The remote-latency projections of R7 were not re-run.
