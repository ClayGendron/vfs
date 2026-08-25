# Review campaign — the 2026-08-25 remediation-round landing (7 commits)

- **Date:** 2026-08-25
- **Scope:** commit set `86a42a7..0b4fb4c` — the chunking-arc
  landing-review round itself: the review memo (`f522b19`) and the
  six specs it bred, landed as 121 (`4d4111f`), 122 (`7e728b5`), 123
  (`de9dc90`), 124 (`ac97b2e`), 125 (`1de26a5`), 120 (`0b4fb4c`).
  Judged at the tip (`0b4fb4c`, clean tree); commit messages treated
  as reviewed contracts.
- **Method:** the five-lens review workflow (ownership, contract,
  scale, test, adversarial — all four engine legs live throughout),
  one independent skeptic per finding, one synthesis pass. 25 agents:
  5 reviewers, 19 adjudications, 1 synthesis. Executed evidence
  standard held end to end — no finding below is unverified.
- **Funnel:** 19 raw findings (ownership 5, scale 4, contract 4,
  adversarial 3, test 3) → 2 refuted in adjudication → 17 verified,
  merging (four lenses converged on F1; two on F7) to **4 major, 5
  minor, 4 design questions**. Zero critical. Two severities
  corrected in verification: both notebook wedges lowered critical →
  major (deliberately pathological triggers, on the calibration the
  prior memo set with its own F9).
- **Decision pass:** Clay, 2026-08-25, same session. F1's fix shape
  and F7's posture were ruled **conditional on prior-art
  verification**, delivered the same session as
  `2026-08-25-close-lifecycle-and-shutdown-race-prior-art.md` — both
  verdicts support the rulings recorded below. Four specs born:
  126–129.

## 1. Major findings

### F1 — `EngineHost.close()` is one-shot: connections re-established after the first close are never released

Four lenses converged (scale, adversarial, ownership, contract),
each with an independent live-Postgres reproduction. `close()` gates
`self._ready = False` and `await self._engine.dispose()` behind
`if self._closed: return`, and `_closed` latches on first close
forever. The round's own spec 122 made close → verb → close a
first-class, conformance-pinned sequence and hoisted the *pool*
shutdown above the gate — while the engine dispose stayed below it.
So the second close shuts the pool and strands every re-minted DB
connection. Second leg, same root: `_closed = True` lands *before*
the dispose await, so a close cancelled mid-dispose (exactly what
`base.py`'s `wait_for` timeout produces) latches closed with the
engine live, silently defeating the retry `base.py` promises.

**Executed (live Postgres, pids cross-checked in
`pg_stat_activity`):** close #1 disposes; the pinned post-close grep
mints pid 3481; closes #2 and #3 never close it — the leak survives
dropping every reference plus `gc.collect()`, reclaimed only by a
manual `engine.dispose()`. Cancelled-close path: 4 of 5 pooled
connections stranded unrecoverably. Reproduced from the public
surface three ways (`DatabaseStorage` direct, `VFS.unbind()`/rebind,
cancelled close). Bounded at pool_size per host; a multi-tenant
process cycling hosts accumulates stranded sessions against
`max_connections`. No document declares the latch: every relevant
contract reads close as "release what is held."

**Verified lead attached:** the `_ready = False` drop is also behind
the gate — harmless only while nothing below the gate runs, i.e. it
stops being harmless the moment the gate falls.

**Decision (prior-art-verified):** drop `_closed` entirely — every
close tears down whatever is held, idempotent by cheapness, no state
set before teardown completes. The prior-art memo's verdict was
unambiguous: SQLAlchemy itself has no dispose latch (dispose is a
repeatable pool-flush with documented connect-after-dispose), and no
surveyed system pairs a one-shot close latch with revival-on-use —
every latch's real job is refusal, which vfs deliberately does not
have. → spec **126**.

### F2 — surviving mutant: "queued work is never cancelled" at close is unpinned

Restoring the exact pre-spec-122 spelling
`shutdown(wait=False, cancel_futures=True)` — the behavior whose
removal the close docstring and commit `7e728b5` declare as law —
survives the entire suite: 2,661 passed, zero failures
(runtime-mutation plugin, repo untouched). The divergence is real
and reachable: with the single-worker pool occupied and a grep's
verify batch queued at close, tip serves `success=True`; the mutant
raises raw `CancelledError` across the public storage seam. Queued-
at-close is ordinary load since spec 120 put reindex hops on the
same pool. The close fix's other three legs carry ledger rows
(P8/P9/P10); this fourth leg has none.

**Decision:** land the queued-batch-served-across-close pin and a
ledger row for the cancel-futures direction, beside F1's fix in the
close spec. → spec **126**.

### F3 — deep-nested `.ipynb` JSON raises `RecursionError` and permanently wedges `reindex()`

`RecursionError` subclasses `RuntimeError`, so it escapes the
`except (ValueError, KeyError, TypeError)` guarding `json.loads` in
`split_notebook`. A writable ~10 KB `.ipynb` body of
`"["*10000 + "]"*10000` (bisected threshold: depth 9,999 on CPython
3.13) writes successfully, then **every** `reindex()` raises raw
`RecursionError` for the whole store until the file is deleted.
Reproduced end-to-end on both engines, identical under
`VFS_PURE_PYTHON=1`. Violates spec 123's law 1 ("no shape the JSON
parse admits raises") and the backend seam law. The narrow catch is
pre-existing at the base, but `de9dc90` edited this exact try/except
and re-declared the promise around it; the prior round's decision
pass already ruled the class in regardless of provenance. Severity
corrected critical → major in verification (deliberately constructed
trigger).

**Decision:** widen the exception floor at the splitter. → spec
**127**.

### F4 — lone-surrogate JSON escape in a pure-ASCII `.ipynb` raises `UnicodeEncodeError` and wedges `reindex()`

A 79-byte pure-ASCII body
`{"cells": [{"cell_type": "markdown", "source": "\ud800 ..."}]}`
passes the Entry write gate — the gate refuses only *direct*
surrogate strs, and this surrogate is manufactured by `json.loads`
downstream — then the unguarded `content.encode("utf-8")` in
`split_code_batch` raises raw `UnicodeEncodeError` out of the
splitter. Same wedge shape as F3; reproduced on memory and live
Postgres, both engines. Directly violates the docstring `de9dc90`
added, and **falsifies the prior memo's own §4 refutation** ("the
surrogate-content escape is unreachable past the write gate").
Critical for the fix: the recursive fallback is itself
surrogate-hostile (`normalize_content` raises the same way), so
routing to the fallback cannot close the class. Severity corrected
critical → major (same calibration as F3).

**Decision:** degrade at the splitter — an explicit surrogate policy
at the splitter's encode sites, so any admitted shape chunks instead
of raising; fallback-path included. → spec **127**.

## 2. Minor findings

- **F5 — `offload.py` counts three laws over four bullets:**
  `7e728b5` added the fourth bullet (pool-follows-close) and left
  the count; `1de26a5` — the round's own prose-trues pass — edited
  two lines above it without noticing. One line. → spec **129**.
- **F6 — an existing race test silently lost its `_audit`:**
  `4d4111f`'s appended MySQL race test absorbed the trailing
  `await _audit(storage)` from
  `test_a_second_reindex_refuses_while_one_runs` (same-indentation
  editing accident; AST-verified base 1/0 → tip 0/2). The restored
  audit passes on live MySQL, so nothing was masked — the defect is
  an undeclared weakening of an engine-leg pin. → spec **129**.
- **F7 — the close-window inline bound is verb-sized, not
  batch-sized:** prose in `offload.py`, spec 122's record, and
  `7e728b5` bound the close window at "one on-loop batch," but a
  verb that captured the pool before close serves *all* its
  remaining hops inline — and spec 120's whole-verb chunk hop makes
  the exposure verb-sized. **Executed:** a reindex racing close at
  20,000 files ran `_assess_and_split` 1.56 s on the event loop
  (1,714 ms worst gap, vs ~242 ms offloaded) while correctly
  reporting success; a raced grep over a >32 MiB corpus ran both
  verify batches on `MainThread`. Behavior is correct throughout
  (classified Results, zero raw escapes); the defect is prose plus
  an untested reindex-racing-close path. **Decision
  (prior-art-verified):** prose + pin — restate the bound per racing
  verb everywhere it is claimed and add the reindex-racing-close
  row; the survey found drain-on-captured-resource universal, per-hop
  migration unprecedented, and any bound the closer's to impose. The
  zombie-pool alternative is recorded as an open question, not
  ruled. → spec **129**.
- **F8 — ledger row P13 overclaims:** `truncations` is provably
  empty at grep's index-side cut (probe-assert never fired across
  2,661 tests plus a live-Postgres leg), so the guard spec 125 added
  there is constant-true and deleting it *alone* survives P13's full
  declared scope (90 passed) — "either guard deleted … killed"
  invites a false survived-regression report from a literal
  replayer. The scan-side and both-deleted directions kill as
  recorded; the code shape itself was cleared as deliberate
  defensive symmetry. **Decision:** keep the guard (spec 125's
  ruling stands), re-word the row to the proven both-appends
  mutation with a C1-style designed-inert note for the index-side
  direction. → spec **129**.
- **F9 — the 32 MiB split-batch byte budget can be deleted or
  voided unnoticed:** the sub-batch pins referee result-equality
  only. Executed: (a) replacing `_split_batches` with one whole-set
  call survives every test — only the 100 % coverage gate objects,
  via the now-dead helper; (b) `_SPLIT_BATCH_BYTES = 1 << 60`
  survives tests *and* the coverage gate, because the pin
  monkeypatches the constant and never observes the declared value.
  Spec 120 §2's byte-bound promise is unrefereed (losing it costs a
  ~0.4× transient, not the peak — hence minor). **Decision:** a
  consumption-spy pin under a small budget plus a declared-value
  referee, landed with the batcher consolidation. → spec **128**.

## 3. Design questions and their rulings

All four arrived as minor defects and were downgraded in
verification on the falsifiability standard — no wrong output
exists, and where a shape was chosen it was chosen deliberately.
Decisions: Clay, 2026-08-25.

- **Q1 — the byte-bounded singleton-exempt batcher has three
  spellings:** `_split_batches` is a verbatim copy of grep's
  `_content_batches`, and `build_epoch`'s inline extract batcher is
  a third spelling with a *post-add* flush (bound = budget + one
  body; the filed "~132 MiB" consequence was refuted by the
  `MAX_INDEXABLE_BYTES` filter — measured overshoot ≤ one ≤2 MiB
  indexable body). **Ruled: one owner lands** — a `byte_chunked()`
  helper beside `chunked()`, all three sites consuming it, the flush
  discipline ruled in the spec. → spec **128**.
- **Q2 — a `_Truncations` owner for the at-most-once law?** Six
  repeated `if <literal> not in truncations` guards plus an upgrade
  dance; per-site guards were spec 125's deliberate ruling three
  days ago, every path is at-most-once by construction, and
  `Result.merge` dedupes at the facade. **Ruled: deferred** —
  reversing a same-round ruling without new evidence is churn;
  recorded as an open question with a growth tripwire.
- **Q3 — a shared `_presence_probe` owner for the LIMIT-1 shape?**
  Spec 121's inline probe duplicates `_pending_probe`'s shape
  without its "never a bare SELECT EXISTS" rationale (rule confirmed
  real on live MSSQL: error 42000). Two call sites is thin ground
  for a wrapper; regressions fail loudly on the MSSQL leg. **Ruled:
  deferred** — recorded as an open question carrying the
  Docker-free-legality-pin argument.
- **Q4 — the offload residency law is unscoped now that reindex
  rides the hop:** indexing's two 32 MiB budgets meter characters by
  a *declared* ASCII-dominant proxy, so an abandoned reindex
  worker's batch can hold 96–128 MiB of folded bytes on CJK/emoji
  corpora (measured 3.00×/4.00×), while `offload.py`'s abandonment
  bullet states the bound in grep's byte-exact terms only. **Ruled:
  scope the prose** — qualifier where reindex is covered, folded
  into the trues pass. → spec **129**.

## 4. Refutations, leads, and unreached surface

**Refuted in adjudication (2):** a claimed regression window in the
spec 121 probe (the "pre-probe bare UPDATE would have caught a rival
flip in the same run" premise is false — both shapes issue their
generation statement first in `chunk_dirty`'s own writer
transaction, so no differential window exists); and a claimed stale
suite-count at two STATUS sites (the mismatch is real but both
sites are scoped to the 103/117/118 mining record — correctly
historical, and "correcting" them would inject an error). Both
refutations are executed evidence in the run transcripts.

**Unverified leads (for a future pass — none verified):**

- `call_offloaded`'s inline fallback catches only submit-time
  `RuntimeError`; a future cancelled *after* a successful submit has
  no fallback by construction — the asymmetry to watch if the
  queued-cancel posture is ever revisited.
- The chunking module may hold more escapes in F3/F4's class —
  worth a sweep of `split_code`'s tree-sitter path and
  `split_with_line_ranges` for raises outside their declared tuples
  (spec 127 takes the sweep).
- `_POSTING_BATCH_BYTES` / `_EXTRACT_BATCH_BYTES` may share F9's
  existence-vs-equality gap (spec 128 investigates).
- The facade's `Result.merge` dedupe — P13's only non-local
  safety net — may itself be unpinned.
- `TestStatementLegality` holds exactly one compile-level
  legality row; other hand-built statements (e.g.
  `_values_flip_stmt`) rely on the live legs alone.
- The loop-responsiveness pin has ~2× margin against its sleeps —
  acceptable, possible CI flake to watch.
- `OFFLOAD_WORKERS`' comment still describes only the grep
  measurement, though the pool now serves reindex too.
- A raced reindex keeps executing DDL-free writes after `close()`
  and commits them — the already-recorded post-close-writes open
  question, now with a reindex-specific edge.
- `build_epoch`/`chunk_dirty` could select `entry.c.size_bytes` and
  meter true UTF-8 bytes for free if byte-exact metering is ever
  wanted.
- The chunk_dirty/build_epoch docstrings' "the loop keeps serving"
  carries the same unstated close-window exception as F7's prose
  sites (spec 129 sweeps them together).

**Surface no lens reached (the review's honest gaps):** full MSSQL
and Oracle leg re-runs at tip — both engines were exercised live
(targeted new rows; the 10,500-entry Oracle scale probe under the
1,000-element IN cap; serves-after-close rows), but the claimed
213/210 totals rest on the commit messages; the recorded linux-gate
and probe-corpus timings (51 s reindex, 50 ms/36 ms gaps) were not
re-measured; `cargo test`; the coverage percentage; a
reindex-racing-close pin (F7 names it; spec 129 lands it).

**Checked and clean (highlights):** all 26 mutant-ledger rows
replayed in an isolated worktree — every row killed at recorded
scope except C1 (designed-inert by its own text) and P13's
index-side sub-direction (F8); spec 120's hop shapes, budgets,
disclosures, and suite counts re-measured to exact match; spec
121's probe pins with the race row live on MySQL (the real
lock-wait timeout kills P6 on-engine); spec 122's 24-greps repro
re-executed 24/24 served, after-close and mask rows green on all
four live engines; 3,539 hostile notebook shapes (inside the
declared tuple, spec 123 holds — F3/F4 sit outside it); 16,000
differential checks per engine on the unified `_whole_matches`
driver (no overcount; count/hits/bytes agree); close-storms (12
rounds of 16 greps + 3 write/reindex + racing close) with zero raw
escapes; reindex-offload occupancy re-measured 16 ms native / 19 ms
pure worst gap at 2,000 files; the full Postgres leg re-run at
exactly the claimed 211; `call_offloaded` verified the single hop
home (no stray `run_in_executor`/`submit` in `src/`);
`kind_membership` verified the single SQL spelling; the
`_whole_matches` unification verified behavior-preserving against
both pre-images; 10,000-file write/reindex/grep on live Postgres
with full recall.

## 5. Decision-pass summary — the spec set

| Spec | Born from | One line |
| --- | --- | --- |
| 126 | F1 + its `_ready` lead + F2 | close disposes every close — the latch falls; the queued-work-served pin and ledger row |
| 127 | F3 + F4 + the sweep lead | the splitter's exception floor — no admitted shape raises; surrogate policy at the encode sites |
| 128 | F9 + Q1 + the budget-gap lead | one `byte_chunked()` owner for the three batcher spellings; the budgets get referees |
| 129 | F5–F8 + Q4 | prose trues (close window said out loud, residency scoping, law count), the audit restore, P13 re-worded, the reindex-racing-close pin |

Deferred to `open-questions.md`: Q2 (`_Truncations` owner), Q3
(`_presence_probe` owner), and the zombie-pool close-window
alternative surfaced by the prior-art memo.
