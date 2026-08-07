# 034. Chaining Filters Rows in Hand: `observations=` Never Reaches the Pattern-Search Seam

- **Status:** accepted 2026-08-06 — decided by Clay in session during
  the manual review of the 092/093 landing. Amends ADR 030 decision
  6.4 (the chaining surface's meaning is fixed as row filtering, which
  its wording — "glob over a prior result's rows" — already said) and
  ADR 031 decision 1 (the `observations=` carve-out is removed: the
  seam is now pattern-only *unconditionally*). ADR 031 decision 4
  (concurrent router-side probe for `paths=`) is reaffirmed unchanged.
- **Date:** 2026-08-06
- **Deciders:** Clay Gendron
- **Context source:** a teaching walkthrough of `reads.py`'s
  `if roots:` block surfaced that the landed implementation gives
  `observations=` rows-as-scope-roots semantics — the backend
  re-derives roots from chained rows, composes them into the pattern
  batch, and re-implements the find-operand rule storage-side — the
  one remaining place scope crosses the pattern-search seam as paths,
  and a duplicate owner of machinery ADR 031 assigned to the router's
  probe.

## The deciding argument

Chained rows are already in the caller's hand. A pattern applied to
rows in hand is a pure predicate — `fnmatch.filter(names, pattern)`,
`PurePath.match`, and the pipe shape (`find … | grep`) are the
uniform field precedent, and none of them re-touches the filesystem.
Searching *under* rows is a different operation, and the namespace
already owns a channel for it: `paths=`, with asserted roots and
unbounded root count (ADR 031 §7). Keeping both meanings on one
channel gave `observations=` storage dispatch, duplicated the
find-operand law at the seam, and made ADR 031's "the router never
sends scope roots to storage" true only with an asterisk.

The verb's *subject* decides whether storage is involved: glob's
subject is the path, always present on a row, so chained glob never
touches storage; grep's subject is content, so chained grep matches
in memory what it holds and fetches only what it lacks.

## Decisions

### 1. Chained glob is a pure in-memory filter

`glob(pattern, observations=rows)` keeps exactly the rows whose path
the compiled pattern matches — `compile_filter(pattern, ext)`, the
same authority every other glob surface uses. No storage call, no
root assertion, no dispatch. *(Annotation, 2026-08-07: spec 094's
`kind=` parameter refines "no storage call" to the general law this
ADR already stated for grep in decision 2 — a chained verb matches in
memory the facts it holds and fetches only the facts the call's
parameters make load-bearing and the rows lack. A `kind=` filter over
a row that carries no kind stats exactly the lacking rows, loudly;
without `kind=`, chained glob remains purely in-memory.)*
Consequences, chosen knowingly:

- **Rows serve as held.** Columns and staleness are the input's; the
  `populated` mask is unchanged. A vanished row still passes — the
  caller who wants fresh rows chains the filtered result into `stat`.
- **Input order is preserved** (the pipe precedent), duplicates
  included; `max_count` caps the filtered sequence.
- **No meta hiding.** Rows in hand are already liveness-resolved; a
  `/.vfs` row the caller legitimately fetched is never dropped by
  the filter.
- A closed router still refuses; element validation (must be
  `Observation`) is unchanged.

### 2. Chained grep matches content in memory, fetching only what it lacks

`grep(pattern, observations=rows)` is the same filter posture over
content:

- Path-structural gates (`globs`/`globs_not`/`ext`/`ext_not`) apply
  first, in memory, against row paths — same compiled authority, no
  meta rule (decision 1).
- A row with content in hand is matched in memory, as held.
- A row without content whose kind is a content kind (or unknown) is
  fetched through the router's own `read` over the grouped-dispatch
  machinery; a row that cannot be read classifies loudly through
  read's ladder (`not_found`, `wrong_kind`, …) beside the healthy
  rows' matches.
- A row whose known kind is not a content kind never matches and is
  skipped silently — a filter's non-match, not an error.
- The index tier is not involved, so the `unindexable_pattern`
  refusal gate (ADR 033) does not apply to chained grep; `allow_scan`
  is irrelevant on this path. Output modes, case modes, word/fixed
  flags, context, `invert_match`, and per-file `max_count` behave
  identically to the storage tiers — the match authority is one
  shared module.

### 3. `observations` leaves the pattern-search storage protocol

`SupportsPatternSearch.glob` and `.grep` lose the `observations`
parameter; the backend's roots derivation and the storage-side
find-operand machinery are deleted. Scope crosses the seam only as
pattern text, now with no exception. The conformance rows for chained
pattern search move from the storage contract to router-level tests.

### 4. The grep match authority becomes a shared module

`_compile_verifier`/`_verify` move from the database backend's
`grep.py` to a router-visible module (`vfs.pattern_matching.grep`,
beside the glob language at `vfs.pattern_matching.glob`), the glob
chokepoint's posture applied to content: storage tiers use it to
verify candidates, the router uses it to filter chained rows, and the
two surfaces cannot drift.

### 5. `paths=` is untouched

Scoped dispatch, composition, residuation, and the concurrent probe
stand exactly as ADR 031 landed them — check-first sequencing was
considered and declined: it adds a serial round-trip and changes no
result (a missing root's composed pattern matches nothing, and the
probe already yields the loud per-root error).

## Rejected alternatives

- **Rows as scope roots (the landed shape)** — storage dispatch for
  row algebra, a second owner of the find-operand law, and the
  standing exception to ADR 031's pattern-only seam. Subtree search
  over chained rows remains expressible: pass their paths to
  `paths=`.
- **Re-verifying matched rows against storage** — a batched re-stat
  would restore the existence assertion at the cost of a storage
  call on every chained filter; declined for filter purity. `stat`
  chaining is the explicit spelling of that intent.
- **Keeping `observations=` on the storage signatures as a dead
  parameter** — a contract that says more than the router ever sends
  is drift by construction.
