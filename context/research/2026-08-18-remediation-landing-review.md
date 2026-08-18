# Remediation-landing review — findings report on the specs 107–111 arc

- **Date:** 2026-08-18 (both runs the same day the arc landed)
- **Provenance:** synthesized output of two review workflows over the
  commit range `2d4d2f4..14e8df5` — the five landing commits of the
  glob/grep remediation campaign (spec 107 `a3de8d7`, spec 109
  `666c4c5`, spec 108 `5318fd7`, spec 110 `981a198`, spec 111
  `14e8df5`), reviewed at the clean tip.
  - **Run 1** (`wf_b03ca583-355`, 25 agents): five review lenses
    (ownership, contract, scale, test, adversarial) on Fable, one
    independent Opus skeptic per finding at high effort, one
    synthesis agent. All four Docker engine legs live for the whole
    run; findings cite executed repros. Funnel: 19 raw findings → 18
    survived verification → 1 merged (two lenses found the same
    defect) → **3 major, 6 minor, 8 downgraded to design questions.
    None unverified; no lens failed.**
  - **Run 2** (`wf_60acb112-d05`, 9 agents): one Fable skeptic per
    unverified lead run 1's verifiers noticed in passing, each
    required to land on a conclusion with executed evidence; the two
    leads needing temporary mutants ran sequentially under the
    safe-restore discipline, tree verified clean after. No live
    engines (nothing in the nine needed one; engine-dependent
    remainders are labeled). Outcome: **4 confirmed (1 major — a
    severity-raising corollary of run 1's finding 1 — and 3 minor),
    3 refuted with evidence, 2 elevated to design questions.**
  Repro scripts were written to the session scratchpad (ephemeral);
  findings name their scripts, and this memo carries the operative
  evidence.
- **Headline:** the campaign's storage-side work (specs 107, 108,
  111) held up under live-engine attack — spec 107's race protocol
  reproduced clean on MSSQL and Oracle, spec 108's arithmetic served
  hostile widths on all four engines including the Oracle IN-list
  floor and the re-created 07002 boundary, spec 111's row-fact gate
  matched the compiled authority over 66,000 hostile-name checks.
  The only behavioral defects in the arc are in spec 110's
  pure-engine slicing (findings 1–2), and the arc's batch-shaped new
  behaviors landed without tests that can see their width (findings
  3, L2, L3).
- **Feeds:** specs 112–115 (born 2026-08-18 from this memo, one per
  defect class): 112 pure-scan slice integrity (findings 1, 2, 7 and
  lead L1), 113 width and mask pins (findings 3, 8, 9 and leads L2,
  L3), 114 engine-leg harness reentrancy (lead L4), 115 bind
  accounting and docstring trues (findings 4, 5, 6 and lead Q1).
  The 10 design questions await a decision pass; none require action
  to keep the tree correct.

---

## Major

### 1. Budgeted pure-engine scan fabricates `^$` matches at slice boundaries — and displaces genuine hits under a cap

`src/vfs/pattern_matching/grep.py` — `_count_whole`, `_hits_whole` —
contract_review + adversarial_review independently (fabrication),
lead pass (displacement) — **CONFIRMED, major**

**What is wrong.** The deadline-sliced whole-text scan passes each
slice's end as `endpos`: `finditer(text, begin, stop)`. CPython's
`re` treats `endpos` as end-of-string, so a MULTILINE `$` matches at
every 16-line slice boundary; the zero-width phantom is then
attributed — via `text.rfind("\n", 0, found.start()) + 1` — to the
*following non-empty line*. Divergent pattern class: anything that
can match empty at a line start but not elsewhere on the line (`^$`,
`^ *$`, `^[ \t]*$`, `x*$`, `a?$` — ordinary blank-line greps).
`completed=True` throughout: not a lawful-subset truncation, invented
hits. The lead pass then proved the corollary: **under a cap the
phantom consumes the cap slot and displaces the genuine match** —
files mode always passes `cap=1`, so a files-mode grep can return the
fabricated hit *instead of* the real one. (The reviewer's suspected
mechanism — same-line dedup suppression — was proven output-invisible
across a 20,000-trial fuzz; the cap is the real suppression path.)

**Why it matters.** Storage grep always passes a float budget, so
every storage grep on the pure engine takes the sliced path. Silent
false positives and (capped) false negatives with `success=True` and
zero errors, breaking the arc's own written contracts: the
`_line_slices` docstring's "judge identically to an unsliced scan",
spec 110's laws 2–3, and commit `981a198`'s body verbatim. Blast
radius: the `VFS_PURE_PYTHON=1` / extension-less configuration, which
spec 110 declares first-class; default wheels ship the Rust engine
and answer correctly.

**Evidence (executed).** Unit: 17 non-empty lines, `^$` — unbounded
hits empty, bounded hits `[(17, 17, 17, 'x')]`, `completed=True`.
Public surface: `VirtualFileSystem.grep("^$", allow_scan=True)` over
a 40-line file with zero empty lines returns matches on lines 17 and
33 under the pure engine (memory, sqlite, and live Postgres — the
defect is engine-independent, it lives in the matcher), zero under
Rust. Displacement: `^$` with a non-matching line directly after the
slice boundary and the only genuine empty line two lines later,
`cap=1` — unbudgeted returns the genuine `(19, 19, '')`; budgeted
(generous budget, no expiry) returns the fabricated
`(17, 17, 'not-empty')` and loses the genuine hit. Fuzz: 1,285 of
20,000 uncapped trials fabricated extras; zero lost genuine hits
uncapped, zero under-counts in count mode (the phantom substitutes
1-for-1 on genuinely matching lines).

**Fix direction.** Don't let a slice boundary present as
end-of-string: iterate from `begin` against the full text and stop
once a match starts at or past `stop` (or discard zero-width matches
ending exactly at `stop` when `stop < len(text)`). The same-line
dedup needs no change (proven harmless alone). Then the missing pin:
a *budgeted* cross-engine parity sweep — every cross-engine assertion
in `test_matcher_parity.py` ran `budget=None`, which is exactly why
this shipped — plus the cap-displacement row.

### 2. Pure-engine wall budget has an exponential residual; single-slice bodies are never clock-checked

`src/vfs/pattern_matching/grep.py` — slice-grain deadline checks,
`_SLICE_LINES = 16` — scale_review — **CONFIRMED, major**

**What is wrong.** The deadline is consulted only *between* 16-line
slices, and the uninterruptible unit — one slice of `re`
backtracking — is exponential in line content, not the small constant
the "residual floor … 273 ms" phrasing implies. The `and begin` guard
additionally exempts one-slice bodies from any clock check at all.

**Why it matters.** Spec 110's own motivating shape is literally
unimproved: `(a+)+bcd` against a 31-byte file under a declared 1.0 s
wall budget ran **75.1 s** synchronously inside the coroutine with
zero errors, while spec 110 law 1 says "a deadline is honored within
a body". The results are exact (the scan finished), so this is a
wall breach, not data loss — and the run-2 cap-plus-deadline probe
(refuted lead R3 below) established that flipping `completed` on a
finished body would be the wrong repair: the flag means data
completeness, and the storage caller already records any breach that
could cost data via its own per-batch deadline check. What is missing
is a bound on the residual's magnitude and an honest record.

**Evidence.** Measured doubling per two characters of line length:
20→26-char lines cost 0.07 → 0.28 → 1.15 → 4.67 s each under a
0.05 s budget, all `completed=True` (single slice); a 16-line slice
of 24-char lines cost 19.3 s under a 0.2 s budget (the 16×
multiplier as derived). The landed pin uses 18-char lines against a
2.0 s ceiling — two orders of magnitude of headroom before it would
trip. Rust control: 5 ms.

**Fix direction.** Honest record first (the docstring must name the
exponential magnitude and the single-slice exemption, not just the
mechanism), the ReDoS pin re-shaped to lines near the measured wall,
and the residual-bounding mechanism recorded as a fork (finer-grain
interruption, a complexity gate, or offload — the same territory as
the event-loop occupancy fork already in `open-questions.md`).

### 3. Delete's cross-target posting-delta accumulation has no killing test at any batch width

`src/vfs/storage/backends/database/topology.py` — accumulate/flush —
test_review — **CONFIRMED, major**

**What is wrong.** The shipped code is correct, but a mutant that
flushes only the *last* accumulated delta survives the entire suite —
2,558 sqlite tests and the 187-test live Postgres leg including the
cascade battery — while silently corrupting the postings mirror on
any multi-target delete (stale postings feed `allow_list_ids` →
missed grep/glob hits). Every mirror-refereed delete row is
single-target; the multi-target rows assert only Result shape and
never read `tables.segments`. Spec 111's own law names the mirror
battery as the referee, and the declared referee cannot see the one
dimension the commit introduced.

**Evidence.** Two-target delete under the mutant:
`delete.success=True`, mirror audit fails — the trashed row keeps
pre-delete segments and never gains trash-side ones. A counting
plugin recorded 114 real `delete_rows` flushes during the suite run,
5 actually truncated by the mutant; nothing failed.

**Fix direction.** One multi-target mirror row (two files under
distinct roots, one call, `_assert_mirror`), ideally in the
conformance helper so all four engine legs referee it.

---

## Minor

### 4. Bind-spend accounting has four homes; one hand count overcharges — in the safe direction

`src/vfs/storage/backends/database/grep.py` — ownership_review —
**DOWNGRADED major→minor.** The filed harm (reintroducing the 07002
undercount class) was refuted: `base_binds = len(CONTENT_KINDS) + 1`
charges 4 where every dialect executes 3 — the `encoded` flag renders
as an inline literal on all six compilers checked and all four live
engines, so the overcount can never overdraw (MSSQL lands 33 under
cap at the maximum chunk). The other three counting sites
(`_channel_facts` increments, `_CHANNEL_ARM_BINDS = 3`,
`_static_binds`) are exact on every dialect. What remains: an
inaccurate inline comment (the flag costs no bind) and a four-site
counting convention where spec 108 §1 wrote "one bind-counting
mechanism, not two" — narrative drift for the mining pass to
reconcile.

### 5. Grep's module docstring misstates the overlay-verdict routing and read cadence

`src/vfs/storage/backends/database/grep.py` — contract_review —
**CONFIRMED.** Executed probe: on a non-empty preamble verdict the
full index tier still runs before the scan tier, and the combined
read is issued exactly **once**, not the docstring's "twice per gated
call". Spec 107 words it correctly ("routes the call onto today's
scan *path*"); the docstrings compressed it wrongly. Maintainer-model
drift only.

### 6. The 273 ms residual floor is claimed "recorded in the docstring" — no docstring carries it

`src/vfs/pattern_matching/grep.py` — contract_review — **CONFIRMED.**
`grep -rn "273"` over `src/`, `tests/`, `crates/` finds nothing; the
figure lives only in spec 110's status and `open-questions.md`. A
checkable false statement in the record; folds into finding 2's
docstring work.

### 7. The anchor half of the sliced-scan equivalence law is unpinned

`src/vfs/pattern_matching/grep.py` — test_review — **DOWNGRADED
major→minor** (the filed "a mid-line slicer mutant passes every
suite" was refuted: it dies in CI's pure leg, 4 conformance
failures). What survives: a slicer whose boundaries land one
character *into* the next line passes the whole pure-leg suite
(2,559 tests) while changing budgeted counts (`^line`: 40 → 38). The
"boundaries never cut mid-line" half is pinned indirectly; the
"`^`/`$`/`\b` judge identically" half is not. The same budgeted
parity row finding 1 needs closes both.

### 8. The rescued-scan path's post-scan epoch recheck is unpinned

`src/vfs/storage/backends/database/grep.py` — test_review —
**CONFIRMED.** A `skip_verified = True` mutant survives all 2,558
sqlite tests and the Postgres race leg (whose rival is a `write`,
which never moves the epoch pointer). Not equivalent: on live SQL
Server (per-statement snapshots), a rival `reindex()` between the
authoritative read and the scan makes the mutant silently drop a row
with `success=True` where baseline redrives and serves both. Fix: a
`current_epoch` counting spy on the rescued-path test.

### 9. Glob's narrow-`columns=` mask promise has no test; grep's sibling strip is equally unpinned

`src/vfs/storage/backends/database/reads.py` (glob, run 1) and
`.../grep.py` (grep, lead L3, run 2) — test_review — **both
CONFIRMED.** Mask-widening mutants — glob's `_observe` fed the
queried mask; grep's hoisted `projected`/`row_mask` block widened by
the ride — survive the full suite (glob: 429 executions; grep: 2,558
tests), because every test passing a real `columns=` selection uses
subset asserts (`<=`), which a wider mask satisfies, and no glob test
passes `columns=` at all. Values never leak (pydantic drops unknown
keys); mask vocabulary does — phantom `name`/`ext`/`size_bytes`
tokens in `populated` on the wire. Fix: one exact-equality mask row
per verb; grep's strip is a single hoisted site serving both
fetchers, so one row pins both paths.

---

## Lead-pass confirmations (run 2)

- **L1 — cap displacement** (major): merged into finding 1 above.
- **L2 — move/restore mirror width** (minor, CONFIRMED): the delete
  finding's sibling. A mutant running `move_postings` on only the
  last pair of a batch survives the full suite — including the
  mirror battery (drives move/restore exclusively single-pair) and a
  20-pair move test (asserts observations only). Multi-pair move and
  multi-target restore are supported contract shapes; the per-pair
  code is correct and intentional per spec 111. One multi-pair
  mirror row (or widening the seeded verb sequence to batch
  sometimes) closes it.
- **L3 — grep mask-strip** (minor, CONFIRMED): folded into finding 9
  above.
- **L4 — engine-leg harness reentrancy** (minor, CONFIRMED): both
  fixture families — `test_races.py::_server_storage` *and*
  `test_conformance.py::_server_storage`, the only consumers of
  `VFS_TEST_<ENGINE>_URL` — unconditionally `drop_all` the fixed
  `table_name="vfs"` metadata at setup; no fixture uses per-run
  names. Demonstrated deterministically on a shared sqlite file
  database: run B's setup makes run A's in-flight writes fail with
  "no such table: vfs" (the sqlite analogue of the Postgres
  "relation vfs does not exist" a run-1 verifier hit live). CI is
  safe (serialized per-engine jobs); failures are loud spurious
  reds, never silent passes — hence minor. Fix shape: mint a per-run
  table name in both fixtures, passed to `build_vfs_tables` and
  every `DatabaseStorage` — which also isolates advisory locks for
  free, since `advisory_key` derives from `table_name`. Two traps
  the fix must carry: the three raw-SQL content audits hardcode
  `FROM vfs_content`, and the rival storage instances in
  `test_races.py` must receive the minted name.

## Lead-pass refutations (run 2 — recorded so they are not re-raised)

- **R1 — deadline-cadence phase consistency**: instrumented all four
  scan paths across ten body sizes (1–64 lines, with and without
  trailing newlines) — deadline checks land at byte-identical
  line positions (`[16]`, `[16, 32]`, …) on every path. The three
  syntactic spellings are provably the same phase: first check after
  16 lines of work, then every 16.
- **R2 — the pyo3 2³² probe**: the spec's numbers are true (re-probed
  against the installed native engine: the `u32` context channels
  overflow at exactly 2³², `cap: Option<u64>` at 2⁶⁴ — matching
  `python.rs`'s declared types), and the operative invariant *is*
  durably pinned: `test_the_ceiling_itself_is_served_on_the_live_engine`
  crosses the native seam with `INT_CEILING` un-clamped and
  demonstrably fails on any future narrowing (verified with an
  emulated u16 mutant). The raw overflow points are unreachable
  through the public API and not load-bearing; no artifact is owed.
- **R3 — cap-plus-deadline `completed=True`**: literally true
  per-body, and the correct answer. A cap-truncated body's payload is
  byte-identical to the unbudgeted scan's (cap-reached is contractual
  completion); a cap break on a non-last body with the wall breached
  still reports incomplete via the next body's entry check; the
  storage caller re-checks the deadline before every subsequent
  batch, so any breach that could cost data is recorded. Flipping the
  flag would emit false truncation warnings on complete results.

## Design questions (awaiting a decision pass)

From run 1 (all verified accurate-but-inert; recorded verbatim in the
run's report):

1. Channel fan budget derived independently at two sites — result-
   neutral, but `arm_budget`'s third argument is a per-arm *bind*
   cost while one consumer caps a *statement count*; the two share a
   number, not a unit, and `pathterms.py` cannot trace the figure.
2. The skip-the-first-check deadline-cadence convention spelled three
   ways (two byte-identical duplicates among them) — equivalent
   today (see R1); spec 110's own byte-cap-slicing follow-up cannot
   be expressed by the line-counting strides.
3. The `{"name", "ext"}` row-gate ride literal repeated at three call
   sites — a forgotten ride fails loud, not wrong; a constant would
   belong in `reads.py`. Related: `reads.glob_rows` splats a
   positional three-tuple into `passes_row_filters`, where a
   parameter reorder would silently mis-gate; grep destructures to
   named locals.
4. `StaleSnapshot` raised identically at two sites in `grep_rows` —
   house-style confirmation; the sites guard different windows.
5. `ContentMatcher` protocol is silent on partial per-body results —
   each engine declares its own law at its implementation; one
   Protocol sentence would fix the vocabulary for a third engine.
6. The budgeted split path pays unbudgeted linear pre-work (decode +
   eager line split, ~2.4× residency) before its first deadline
   consult — ~7% overrun at 512 MiB against the 10 s default; a lazy
   line iterator alone would not fix it (`_as_text` is a second
   linear pre-pass on both paths).
7. Ladder-defer comparator strictness at the exact crossover tie
   (`allow_size=80`) is unpinned — observationally inert; spec 109's
   standing-mutation-harness question is the natural home.
8. The rarest-first ordering pin reads SQLAlchemy's private
   `_where_criteria` — stable through 2.1.0b3 (the predicted breakage
   does not reproduce); public `Select.whereclause` is available.

From run 2:

- **Q1 — `_static_binds` compiles on the default dialect** while the
  executed statement compiles on the live one. Verified
  count-identical for every reachable input (the two liveness terms)
  across all six profiles × five bundled dialects, and for six
  plausible future predicate shapes; divergence would need a dialect
  overriding bind *cardinality*, which none does. Hazard direction if
  it ever diverged: undercount → `per_chunk` inflation → the ORA-01795
  class. Options: pin the invariant (a dialect-count parity test +
  one docstring line) or thread the live dialect through.
- **Q2 — partial-count marking**: a wall-expired body's partial count
  lands in `score` per-row indistinguishable from an exact one
  (measured 48.0 where exact is 200.0), marked only by the
  result-level truncation warning — consistent with every other
  truncation channel's result-level convention, and no contract
  promises per-row exactness. Options: status quo; drop the
  interrupted row (exact-or-absent parity with the Rust engine — the
  warning already says rows may be missing); a per-row partiality
  field.

## What no lens reached (unreviewed surface)

The commit bodies' benchmark claims (ladders, hydration/delete wins)
were accepted as recorded, not re-measured against the original
harnesses (delete was independently re-timed at 10k on two engines);
spec 109's mutation ledger was spot-re-executed, not re-run whole;
MySQL is the least-exercised leg (race pins ran, the demotion race
was argued from its REPEATABLE READ pin, not raced; the 10k delete
and hostile-width probes ran on Postgres/sqlite and MSSQL/Oracle
respectively); Rust core internals beyond the pyo3 seam (unchanged in
range); the full `scripts/ci.sh` matrix (single legs and targeted
selections ran instead); pathterms' 1M-entry memory profile (accepted
as the docstring's declared suboptimality).
