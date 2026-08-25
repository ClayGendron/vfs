# Review campaign — the 2026-08-18 → 2026-08-25 landing (25 commits)

- **Date:** 2026-08-25
- **Scope:** commit set `bd0b14a..86a42a7` — every commit landed on and
  after 2026-08-18: the glob/grep remediation arc at its tip (specs
  107–116), the Rust chunking engine (spec 117), matcher offload
  (spec 118), the fan-out/admission refactors (`ec02bc9`, `342ce5a`),
  and the CI/docs landings. Judged at the tip (HEAD = `86a42a7`,
  clean tree); commit messages treated as reviewed contracts.
- **Method:** the five-lens review workflow (ownership, contract,
  scale, test, adversarial — all on live engines), one independent
  skeptic per finding, one synthesis pass. 26 agents total: 5
  reviewers, 20 adjudications, 1 synthesis. All four engine legs were
  live throughout; the contract lens re-ran every leg at exactly the
  claimed counts (Postgres 210, MySQL 211, MSSQL 212, Oracle 209).
- **Funnel:** 20 raw findings → 3 refuted in adjudication → 17
  verified, merging to **3 major, 6 minor (one pre-existing/out of
  range), 8 design questions**. Zero critical. Two severities
  corrected in verification: the generation re-dirty lock finding
  *raised* minor → major; the EOF-discard mutant lowered major →
  minor. No finding reached this memo unverified.
- **Decision pass:** Clay, 2026-08-25, same session — recorded per
  finding below and summarized in §5. Six specs born: 120–125.

## 1. Major findings

### F1 — reindex holds the event loop for the whole chunk parse

`indexing.py` `chunk_dirty` calls `Chunk.split_batch` synchronously
inside the coroutine. The native call detaches the GIL — which frees
*threads*, not the *loop* — so every caller sharing the host's loop
stalls for the whole batch parse plus the inline chunk-row assembly.
ADR 048 and spec 117 promise "the reindex verb's event-loop occupancy
for chunking goes to approximately zero"; the promise traces to an
inference the same commit set's own ADR 049 measurement contradicts
(a 1,535 ms tick gap on a GIL-detaching seam was spec 118's entire
justification). The offload shape that fixes it was built one module
over and never applied here.

**Executed:** 2,000 files → 2,250 ms worst loop gap during
`reindex()` at a 10 ms heartbeat; 3,000 files → 3,156 ms, of which
2.52 s is `split_batch` alone; extrapolated to the landed linux gate
(~24 s chunk wall), reindex freezes the loop ~24 s. Loop-blocking is
pre-existing (the base split inline too); the *promise* is the set's.

**Verified lead attached:** occupancy is systemic, not chunk-only —
the posting/gram `build_epoch` also runs inline (369 ms gap observed
in the same probe).

**Decision:** offload the **whole reindex verb's CPU-bound stages**
through the backend-owned executor spec 118 built — chunk pass and
`build_epoch` alike — closing the lead in the same landing. → spec
**120**.

### F2 — generation re-dirty UPDATE write-locks the entry table on MySQL

The unconditional first statement of every `chunk_dirty`
(`UPDATE entry SET chunked=false WHERE chunked AND (chunk_generation
IS NULL OR != gen)`) has no supporting index, and the dialect profile
pins MySQL/MariaDB at REPEATABLE READ for write ops — under which an
unindexed UPDATE takes next-key locks on **every scanned row**, held
for the whole reindex transaction, even when it matches zero rows.

**Executed (live MySQL, 20k entries):** the zero-match statement
alone in an open RR transaction blocked a rival single-row UPDATE
3,009 ms to lock-wait timeout (errno 1205 — a *retryable* code, so
saturation becomes a retry storm); end-to-end with a counterfactual
arm, concurrent write throughput during reindex drops ~3× (9 vs 29
writes). The originally filed rationale (scan cost) was the weak
half — Postgres pays 63 ms at 500k rows.

**Decision:** a LIMIT-1 existence probe before the UPDATE (the
`_pending_probe` shape) — a consistent read takes no InnoDB locks and
the steady-state no-op skips the UPDATE entirely. An index on
`chunk_generation` alone was considered and declined: `IS NULL OR !=`
is not a selective range, so RR would still lock broadly. → spec
**121**.

### F3 — grep racing or following `close()` escapes as a raw RuntimeError

`EngineHost.close()` shuts the lazily-minted verify executor down but
never clears it, so any grep after — including greps **in flight**
when close lands — raises `RuntimeError: cannot schedule new futures
after shutdown`, which `_execute` does not classify, crossing the
storage seam raw against the backend's own law. Every sibling verb
keeps serving after close via transparent re-pooling; grep itself
serves after close *if no grep ever ran before* (fresh pool minted) —
the same call is fatal or fine on hidden pool state. Introduced by
spec 118 slice A; no such mode existed at the base.

**Executed:** 100 % reproduction, 4/4 runs, sqlite and live Postgres,
from the top public API (24 in-flight `fs.grep` + `fs.close()` → 24
raw RuntimeErrors; the identical glob shape → 24 clean Results).

**Adjacent unverified leads:** close does not actually stop the
storage (a write after `close()` still *mutates*); and a grep after a
close that never minted the pool mints a fresh executor nothing will
ever shut down.

**Decision:** grep **serves like its siblings** — across and after
close, re-minting the pool (or falling back to inline verify), with
in-flight calls coming back classified, plus a verb-level after-close
conformance row. The broader "should a closed backend refuse
everything" question is *deliberately left open* and recorded, not
ruled. → spec **122**.

## 2. Minor findings

- **F4 — STATUS end-state count stale:** STATUS.md records 2,641 at
  two sites; the clean tip runs 2,646 passed / 866 skipped
  (collection engine-invariant at 3,512 items — not environment
  drift). Provenance: slice A's 2,631 + 10, taken one commit before
  `76af78d` added 5. *Lead:* the surrounding engine-leg counts may
  share the stale provenance. → spec **125**.
- **F5 — offload residency cap overstated:** `VerifyOffload`'s
  docstring caps abandoned-worker residency at ≤32 MiB, but the
  batcher's declared singleton exemption lawfully sends one oversized
  body over it (executed: a 40 MiB body rides alone — spied batch
  width 41,942,023 bytes). The code is right; the prose understates
  an accepted risk in `offload.py` and ADR 049. → spec **125**.
- **F6 — `_line_slices` docstring claims disproved identity:** it
  states boundary placement alone makes `^`/`$`/`\b` judge
  identically to an unsliced scan — the exact claim the spec 112 fix
  disproved (executed: `$` matches at slice-end offsets 112/224 on a
  40-line body with no empty lines when the callers' guard is
  absent). Identity holds only because both callers discard
  zero-width matches at non-final slice ends — a caller obligation
  the docstring never names. No runtime defect. → spec **125**.
- **F7 — EOF discard guard unpinned (surviving mutant):** deleting
  `and stop < len(text)` from both whole-text loops survives the
  entire suite (2,646 native, 2,633 pure) while pure-engine
  `grep("$")` on `"abc"` returns 0 instead of 1 and end-to-end
  `fs.grep("$")` silently drops every file without a trailing
  newline. The qualifier is declared law; only the *opposite*
  (over-serving) direction has a proven killer. Downgraded from
  major: shipped code correct, pure engine only, narrow pattern
  class. *Lead:* the ledger carries no row for this guard in either
  direction. → spec **124**.
- **F8 — grep mask law unpinned (surviving mutant):** widening only
  the hoisted projection (not the mask) survives all 2,646 tests
  while a valued `size_bytes` reaches callers and the wire outside
  the populated mask. The conformance mask law loops over
  stat/read/ls/glob but not grep, and passes no `columns=`. Ledger
  row M3's wording admits both readings — the same intent-ambiguity
  failure mode M5 recorded. → spec **124**.
- **F9 — malformed-notebook reindex wedge (pre-existing, out of
  range):** `split_notebook` promises malformed notebooks fall back
  to the recursive splitter but guards only the cells extraction: a
  valid .ipynb with non-string `kernelspec.language` raises raw
  `AttributeError` and wedges every `reindex()` until the file is
  deleted (executed end-to-end; grep still serves via the scan
  overlay; reindex recovers after deletion). Byte-identical at the
  base — flagged for triage, not charged to this set; the set added a
  second unguarded call site. **Decision:** fix it anyway — a
  user-writable file wedging reindex is worth fixing regardless of
  provenance. → spec **123**.

## 3. Design questions and their rulings

All eight were verified — the factual substrate of each is real; none
is a reachable defect. Decisions: Clay, 2026-08-25.

- **Q1 — whole-text scan skeleton duplicated** (`_count_whole` /
  `_hits_whole`, byte-identical 8-line skeleton; the silent
  one-copy-fix risk was refuted — each copy has 2–4 killing tests —
  and the item was parked 2026-08-18 behind the byte-cap-slicing
  trigger). **Ruled: unify now** — the phantom guard became a second
  shared law in the parked bodies, which is weight enough. Taker's
  caveats: `_hits_whole` consumes `found.end()`; a generator's
  `StopIteration.value` verdict is unobservable under early `cap`
  break. → spec **125**.
- **Q2 — Chunk's extension routing spelled twice** (`split` and
  `split_batch`; delegation executed and verified behavior-identical
  across seven routes; `chunk.py`'s "single door" line now factually
  stale — `Chunk.split` has zero production callers). **Ruled: take
  the delegation and the doc fix.** → spec **125**.
- **Q3 — content-kind membership ride has no owner** (four
  spellings, one unsorted, charge remembered separately twice; the
  filed nondeterminism/cache-churn consequence was **refuted** on all
  five dialect compilers and four live engines — `in_()` expands
  out-of-band, compiled text byte-identical, cache key
  order-independent). **Ruled: a `KindMembership` owner lands**
  beside `ExtMembership`. → spec **125**.
- **Q4 — "any content ≥ GRAM_SIZE yields at least one chunk" false
  on the structure path** (over-budget whitespace-only body → 0
  chunks native / 2 pure; pre-existing, pinned, generation-stamped,
  consequence-free). **Ruled: editorial qualification only.** → spec
  **125**.
- **Q5 — "candidate budget" truncation appended twice at the storage
  seam** (real, reproduced; invisible through the facade —
  `Result.merge` dedupes; ratified as campaign open question 23).
  **Ruled: guard now**, closing OQ 23 — minding the load-bearing
  `truncations == ["candidate budget"]` equality. → spec **125**.
- **Q6 — `_route_fanout`'s "never peeked" clause over-scopes** (exact
  for the function that owns it; `_glob_dispatches` reads
  `kind`/`columns`, both documented and pinned). **Ruled: scope the
  clause.** → spec **125**.
- **Q7 — `chunk_spans` fallback causes mis-enumerated** (the Python
  seam omits the >u32/4 GiB body fallback the Rust seam declares, and
  its "parse failure" arm is unreachable at tree-sitter 0.26 —
  executed: a 4 GiB+ body silently takes the character splitter,
  correct posture under the no-designed-caps rule). **Ruled: one
  shared wording across the three sites.** → spec **125**.
- **Q8 — `chunk_dirty` whole-corpus residency undisclosed** (the
  filed arithmetic was refuted by staged tracemalloc on two engines
  and three corpus shapes: the batch encode adds ~0.4× transient and
  never raises the call's peak — the measured 6.1×-content peak is
  the pre-existing chunk-insert executemany; but `build_epoch`,
  pathterms, and segments all disclose their profiles and this pass
  doesn't, while the generation law adds fresh whole-corpus-dirty
  triggers). **Ruled: land the disclosure AND a byte budget** for the
  split batch, symmetric with `_EXTRACT_BATCH_BYTES`, accepting it
  does not move the measured peak. → spec **120**.

## 4. Refutations, leads, and unreached surface

**Refuted in adjudication (3):** the surrogate-content escape
(unreachable past the write gate), the cross-engine chunk-shape
coincidence (explained by the generation stamp), and the
completed-flag divergence (lawful). Each refutation is executed
evidence, recorded in the run transcripts.

> **Correction (2026-08-25, spec 127's landing):** the first
> refutation was wrong. The write gate refuses only *direct*
> surrogate strs; a pure-ASCII notebook whose JSON carries a
> `\ud800` escape passes the gate, and `json.loads` manufactures
> the lone surrogate inside `split_notebook` — the next review
> round reproduced the wedge end-to-end (its F4). Fixed by
> spec 127: unstorable characters are scrubbed to U+FFFD at the
> splitter. The other two refutations stand.

**Unverified leads (for a future pass — none verified):**

- Reindex-vs-writer lock scope beyond F2: the counterfactual arm
  still showed 1.5–3 s write stalls; `repair_segment_drift`'s
  `with_for_update()` re-read is the likely holder, pre-dating the
  range.
- Close does not stop the storage: post-close writes serve and
  mutate; whether a closed backend should refuse is undecided
  contract (recorded as an open question by spec 122).
- The executor minted by a post-close grep is never shut down
  (thread leak) — spec 122's territory.
- Trash-path .ipynb exclusion from the chunk pass — law or
  dirty-flag accident?
- `fs.glob(kind="dir")` (invalid kind value) returns empty success
  rather than a typed-invalid refusal.
- `_assemble_spans` decodes per-span with `errors="replace"` — a
  mid-codepoint engine boundary would silently yield U+FFFD; only
  whole-node boundaries are pinned.
- `chunk.rs`'s `set_language(...).ok()?` arm is likely unreachable
  with compile-time-pinned crates — dead, uncovered branch.
- STATUS.md's engine-leg counts around the stale suite count (F4).
- Wall-expired grep never reports the unconsulted overlay (carried
  forward from the campaign memo, still true at tip, unreproduced).

**Surface no lens reached (the review's honest gaps):** none of the
range's performance/timing claims were re-measured (the 52 s/54 s
linux gate, bench ladder walls, the 6.6× projection, the 273 ms
residual, the 9.0 MB wheel — taken on trust throughout); the
93,760-file linux-corpus gate was not replayed; spec 114's concurrent
two-process-per-engine shape was not re-executed (single legs only);
the 3.11–3.14 matrix ran nowhere (3.13 only); `publish.yml` was read,
never executed; MySQL was exercised for conformance counts and F2's
lock probes but not the scale-width shapes; `Cargo.lock`/`uv.lock`
were not audited beyond the tree-sitter removal.

**Checked and clean (highlights):** the two-read overlay protocol on
both docstring sites; the full bind-accounting contract with live
budgets confirmed by introspection (MSSQL 2,099 params, Oracle 1,000
IN); every new IN-list rides `chunked()`; all three offload laws
against their ledger rows; both chunk provenance laws including the
column-to-column SET on all three flip arms; schema 5→6
refuse-on-mismatch; all 18 mutant-ledger rows replayed in an isolated
worktree (17 killed at recorded scope, C1 designed-inert as its row
states, M5's recorded killer drift confirmed); the 342ce5a admission
refactor rated exemplary by the ownership lens; native.py verified a
true leaf; tree-sitter fully gone from pyproject/uv.lock.

## 5. Decision-pass summary — the spec set

| Spec | Born from | One line |
| --- | --- | --- |
| 120 | F1 + its systemic lead + Q8 | reindex leaves the event loop — whole-verb offload, split-batch byte budget, residency disclosure |
| 121 | F2 | LIMIT-1 existence probe before the generation re-dirty UPDATE |
| 122 | F3 + executor-leak lead | grep serves across and after close like its siblings; classified in-flight failures; after-close conformance row |
| 123 | F9 | malformed-notebook metadata guards — the fallback promise kept |
| 124 | F7 + F8 + ledger leads | pins for the two surviving mutants; M3 anchor tightened; the missing ledger row |
| 125 | Q1–Q7, Q5, F4–F6 | consolidations (skeleton, chunk delegation, KindMembership, truncation guard) and prose trues |
