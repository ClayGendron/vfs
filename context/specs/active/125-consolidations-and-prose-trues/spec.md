# 125 — The round's consolidations and prose trues

- **Status: draft, 2026-08-25.**
- **Born from** the chunking-arc landing review
  (`../../../research/2026-08-25-chunking-arc-landing-review.md`):
  design questions Q1 (skeleton unification — ruled *unify now*,
  un-parking the 2026-08-18 item), Q2 (Chunk delegation), Q3
  (KindMembership owner), Q5 (truncation dedupe — closes campaign
  open question 23), Q4/Q6/Q7 (prose scoping), and findings F4–F6
  (record decay). All ruled in the 2026-08-25 decision pass.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** verified-inert consolidations plus record truing. **No
  behavior change anywhere**: every consolidation was verified
  behavior-identical during the review; the gate is the full suite,
  both grep ladders byte-identical, and the touched pins.
- **Depends on:** spec 124 (its new EOF/mask pins referee the
  skeleton unification — land 124 first), spec 116 (the previous
  hygiene pass this continues), ADR 045 (bind-accounting vocabulary
  KindMembership joins).
- **Relates to:** spec 120 (touches `chunk_dirty` — coordinate the
  chunk-doc edits), the campaign memo's open question 23 (closed by
  §4 here).

## Intent

Six verified-but-inert consolidations and seven record corrections,
each individually small, landing as one hygiene pass in the spec 116
tradition. Nothing here is a defect; everything here was verified
real (and several filed *consequences* were refuted — the refutations
bound the shape below).

Laws that bind the slices:

1. **No behavior change.** Byte-identical grep ladders, identical
   suite results, identical compiled SQL on all five bundled dialect
   compilers.
2. **Prose is trued to the code, never the reverse** — except where
   the decision pass explicitly ruled a code consolidation.
3. **A record correction states what is, not what nearly was**: no
   hedging language in the corrected docstrings.

## Shape

**Consolidations:**

- **§1 The whole-text scan skeleton unifies.** The 8-line skeleton
  (slice loop, deadline consult, zero-width discard guard,
  rfind/dedup recovery) is byte-identical across
  `_count_whole`/`_hits_whole`; two shared laws now live in the twin
  copies. Unify into one driver. Taker's caveats from verification:
  `_hits_whole` also consumes `found.end()`, and a generator's
  `StopIteration.value` verdict is unobservable under an early `cap`
  break — shape the driver so both consumers keep their exact
  semantics. Refereed by spec 124's new EOF rows plus the existing
  2–4 killers per copy.
- **§2 `Chunk.split` delegates to `split_batch`.** The three-way
  extension routing is spelled once: `split` becomes
  `split_batch([...])[0]`, `_split_content` and the redundant
  notebook-extension guard go. Verified behavior-identical across
  all seven routes during the review. The `chunk.py` module
  docstring's "single door" line is trued: `split_batch` is the
  production splitter; `split` is the single-item convenience.
- **§3 `KindMembership` owns the content-kind ride.** The membership
  is spelled four times (one unsorted) with its bind charge
  remembered separately twice; a small owner beside `ExtMembership`
  in `reads.py` carries predicate and price together, all four sites
  consuming it. The refuted consequences bound the shape: this is
  *not* a determinism or cache fix (compiled text was proven
  byte-identical on all five compilers regardless of order) — it is
  ownership only, and the spec claims nothing more.
- **§4 The truncation dedupe guard.** The two "candidate budget"
  appends in the storage grep are guarded like the wall-time
  appends, so the storage seam emits the record at most once —
  minding the load-bearing `truncations == ["candidate budget"]`
  equality in the same module. Facade behavior is already correct
  (merge dedupes); this trues the seam and closes campaign open
  question 23.

**Prose trues (each site says what the verification proved):**

- **§5** `_line_slices`: scope the identity claim — boundary
  placement guarantees no match is *split* and begin-side context is
  real; zero-width end-of-slice matches are the **callers'**
  obligation to discard (the guard both callers carry). Name the
  obligation.
- **§6** `VerifyOffload`: abandoned-worker residency is "bounded by
  the content-byte budget *or one body, whichever is larger*"
  (singleton exemption), and the budget is a module constant, not
  the caller's. Mirror the correction in ADR 049 as an amendment
  note.
- **§7** `chunk_spans` (Python seam): one shared fallback wording
  across native.py, the Rust seam doc, and the chunking seam —
  "unknown grammar, language load failure, a body over 4 GiB, or the
  pure engine" — replacing the unreachable "parse failure" arm.
- **§8** Chunking module docstring: qualify "any content ≥ GRAM_SIZE
  yields at least one chunk" for the structure path (an over-budget
  whitespace-only body yields none by design; consequence-free and
  pinned).
- **§9** `_route_fanout`: scope the "never peeked" clause to the
  function that owns it, naming `_glob_dispatches`' two documented
  reads.
- **§10** STATUS.md: 2,641 → 2,646 at both sites, and re-measure the
  surrounding engine-leg counts while there (the review's lead:
  they may share the stale provenance).

## Slices

- **A. Consolidations** (§1–§4) — refereed by the full suite and
  byte-identical ladders.
- **B. Prose trues** (§5–§10) — docs only; the gate is factual
  accuracy against the review's executed evidence.

## Open questions

- None. Every item here carries a ruling from the 2026-08-25
  decision pass; the questions the pass left open live in the memo
  and `open-questions.md`, not in this spec.
