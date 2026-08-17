# 040. Path Terms in Candidate Nomination: Segment Postings, Write-Path Maintenance, and the Allow-List Seam

- **Status:** accepted 2026-08-17 — the record of the path-indexing
  research arc's decision set, resolved by Clay in session on the
  fork evidence. Implemented by spec 104 (drafted the same day).
  ADR 031's pattern-only glob seam and ADR 033's nomination/verify
  split are untouched; this ADR adds a second posting family beside
  the content grams and moves glob predicates from post-nomination
  filtering into nomination itself.
- **Date:** 2026-08-17
- **Deciders:** Clay Gendron
- **Context source:** the path-indexing prior-art memo
  (`../research/2026-08-17-path-indexing-prior-art.md`) and its
  studies directory (field study of zoekt, codesearch, ripgrep's
  globset/ignore, pg_trgm, plus public design writing on GitHub
  Blackbird, plocate, Lucene's path-hierarchy tokenizer, and
  filtered vector search; term-shape and maintenance measurements
  on the 93,760-file linux store; a 10,519-call mining pass over
  real agent search usage).

## The deciding argument

Glob predicates today apply after candidate nomination *and after
truncation*: a scoped query on a wide pattern pays the full
25,000-candidate fetch and can silently lose recall (the budget is
consumed by out-of-scope candidates the glob then discards). The
field study showed path predicates belong in nomination — Blackbird
ships path ngrams beside content ngrams, zoekt a filename corpus in
the same doc-id space, pg_trgm per-segment trigrams — always under
the same superset-then-recheck contract vfs already enforces.

Two facts picked the shape. The workload: 99.4% of 10,519 observed
agent searches are scoped, and directory scope + extension is ~86%
of all glob use — served entirely by directory-segment terms plus
the already-stored `ext` and `name` columns. The coherence
constraint (raised by Clay): every in-memory design in the field is
single-writer, while vfs is stateless calls over a shared
multi-writer database — and vfs renames deliberately leave no dirty
signal (the move's descendant rewrite "bumps no versions and takes
no guard"), so any epoch-cycled path structure goes silently stale
on rename: a false-negative hole. Path facts belong to the same
consistency domain as the `path` column itself, which is already
maintained transactionally.

## Decisions

1. **The path term is the directory segment, stored as a posting
   table in the entry-id space.** One row per (segment name,
   entry id), where segments are the entry's ancestor directory
   names — 3.8 rows per file and a 3,087-term vocabulary at linux
   scale. Extension and basename predicates are *not* new terms:
   the stored `ext` and `name` columns serve them as pushable SQL
   predicates. Rejected: path trigrams (10× the postings, 35× the
   rename cascade, to nominate the 8%-of-usage stem-wildcard class
   that degrades acceptably); ancestor-prefix terms (same cost at
   rest, 4× on renames, and no single-statement cascade — the term
   text embeds the path); an in-memory path corpus (single-writer
   prior art, per-process memory, and a designed scale cap).

2. **Postings are maintained synchronously, in the write and
   topology transactions.** Entry creation inserts them beside the
   entry rows; moves derive a postings delta from the descendant
   rewrite list they already compute (the pure-rename fast path is
   one scoped `UPDATE`); copy, trash, restore, and hard delete ride
   their existing statements. Measured: ~174 ms on a 10,000-file
   batch, ~0.6 ms on a single-file write, ~50 ms for a
   37,768-descendant rename. The invariant is mechanical: postings
   mirror the `path` column at every commit boundary. Rejected:
   epoch-cycled postings (rename staleness = forbidden false
   negatives, and no overlay signal exists to repair them). The
   flag-repaired variant (a `path_encoded`-style flag demoted by
   the move's descendant UPDATE, with a path-overlay query arm) is
   recorded as correct and lower-surface — but it converts a
   bounded rename-time cost into per-query degradation over an
   unbounded window (reindex is batch-only by decision, and agents
   search immediately after renaming), so it was not chosen.
   **Reindex additionally rebuilds — wholesale in effect, guarded
   delta in application** (Clay, 2026-08-17: reindex must also
   rebuild the postings so drift cannot accumulate). A reindex
   phase converges the table to exactly the recomputed segments of
   every live path — the same end state as a drop-and-rebuild — but
   applied in budget-chunked transactions whose changes are guarded
   by the path each delta was computed from; a guard miss skips the
   row, because a concurrent writer's synchronous maintenance is
   the truth. A literal drop-and-rebuild was rejected for the
   steady state: without epochs (which this table deliberately
   lacks) it either blocks every writer for the duration or reverts
   concurrent writers' postings from its stale snapshot. Found
   drift is reported loudly — it is a maintenance bug being
   surfaced, not silently absorbed. A true drop-and-rebuild remains
   the posture for format changes, as with the gram table.

3. **Nomination treats segment postings as peers of content grams.**
   The planner compiles admission globs to segment terms; their
   sorted entry-id postings enter the rarest-first intersection
   beside gram postings (measured intersection cost: 61–133 µs at
   any width), and the candidate budget counts *scoped* candidates
   — restoring recall for scoped-wide queries. Exclusion globs
   never prune nomination (excluding by a superset would
   under-nominate); they remain authority-side. Globs yielding no
   segment terms contribute `ext`/`name` predicates to the entry
   fetch; a glob yielding neither degrades to today's
   fetch-and-filter. The compiled glob remains the sole match
   authority over every survivor — nomination is a superset,
   always.

4. **The allow-list is a seam beside the planners, not inside
   grep.** One storage-layer module compiles the glob channels into
   segment terms plus column predicates and yields entry-id sets;
   grep nomination, the glob verb's prefilter, and the future glean
   pre-filter consume the same seam (pre-filtering with an id
   allow-list is the industry answer for selective filters in
   vector search). ADR 031 holds: scoping still arrives as pattern
   text on the glob channels; the allow-list is an internal
   artifact derived from them, never a new channel across the seam.

## Consequences

- Scoped queries stop paying for the corpus: nomination starts from
  the rarest posting of either kind (a scoped-wide query like
  `copyright` under `ext4` starts from 80 ids instead of 58,000),
  and truncation can no longer silently drop in-scope rows.
- The per-candidate hot loop sheds its measured overhead (~121 ms
  of `Path` construction per saturated call, ~92 ms per name-arm
  glob) by matching path strings and pushing `ext`/`name` into SQL.
- Writes and topology carry a new bounded cost, measured trivial at
  both audience profiles, and a new invariant to test: segment
  postings mirror the path column after every verb.
- The bench gate grows a scoped-query battery (the usage-mined
  shapes) with rg compared in its positional-path form — the
  hardest fair comparison — and a recall column: row counts must
  match rg's, not just beat its wall time.
- Stem wildcards (`*_test.c`) stay un-nominated by design; they ride
  column predicates or fetch-and-filter. If future usage data shows
  the class growing, path trigrams remain the recorded escalation,
  costed in the memo.
