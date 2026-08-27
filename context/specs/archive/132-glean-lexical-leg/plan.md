# 132 — plan

## Approach

`glean.py` beside `grep.py`, in grep's shape: one session, SELECTs
only, the backend's `_execute` owns the transaction and the
`StaleSnapshot` redrive. The verb is the harness driver's two rounds
(`tests/ranking/driver.py`, spec 131) made a product path, plus what a
verb needs and a driver does not — scope, the freshness overlay,
liveness, the records, the envelope, the mask.

### Slice 0 — the per-query selection kernel (landed first)

`competing_blocks` (one call per term) became `select_blocks` (one
call per query): the summaries of every overflowing term, the round-one
candidates and their scores cross the seam once as packed bytes and
are viewed in place (`align_to`, copy fallback) on the Rust side; the
kernel orders terms by descending maximum and computes each term's
`rest` itself. Protocol 6 → 7. Measured on the full linux store, the
six-term shape spec 142 landed at 0.43 ms: **0.144 ms** (the memo's
0.15 ms target). The fidelity referee and the harness driver use it.

### Scope: subtree roots, resolved to chunk ids, two rungs

The router hands `glean` its scope as entry-local `Path`s (the plain
fan-out branch — `paths=tuple(rels)`), not glob text: a directory names
its subtree, a file itself. Piped `observations` arrive as rows and
reduce to the same thing (`targets_of`). So the scope predicate is
`OR(subtree_filter(root))` over the roots — the escaped path-prefix
range on the unique path index — with the content-kind gate, `encoded`
and liveness beside it. (The spec's "the globs grep takes" reads as the
router's pattern-text composition, which glean does not get; the
protocol types `paths: tuple[Path, ...]`.)

The ladder has two rungs and one declared constant:

- **Rung A — filter, then fetch.** `SELECT entry_id FROM entry WHERE
  scope AND encoded AND live LIMIT SCOPE_ID_BUDGET + 1`. When it does
  not overflow, the ids map to chunk ids through `lex_docs (epoch,
  entry_id)` in membership chunks, and the scorer takes them as
  `candidates`. Exact, and the id count is bounded by construction.
- **Rung B — fetch, then filter.** When the scope overflows the budget
  it is wide: score unscoped at the fusion K, then probe the top
  chunks' entries with the scope predicate (the same row fetch that
  supplies the entry facts). If fewer than `limit` entries survive,
  one deeper probe at `PROBE_DEEPEN × K`; still short → a `truncated`
  warning naming the scope probe. Never a third statement.

`SCOPE_ID_BUDGET = 5_000` entries (well under the "tens of thousands"
the spec forbids fetching per query), `FUSION_K = 1_000` chunks
(ADR 055's fusion K), `PROBE_DEEPEN = 4`. The constants are refereed:
a scope one over the budget takes rung B, one under takes rung A, and
both answer identically on a fixture where the truth is known.

`user_id` is accepted and not applied — every read on this backend
ignores it today and row-level grants are spec 058's; the spec's
mention in pin 2 is deferred there rather than half-built here.

### Freshness overlay: query-time blocks through the same scorer

The `NOT encoded` content-kind rows in scope (grep's scan partition),
in path order, capped at `OVERLAY_BUDGET = 500` entries (the memo
measured ~1.8 ms per entry pure Python; the Rust tokenizer is ~10×
that), bodies fetched in one content read. Each body is tokenized by
the engine and counted for the query terms off the loop
(`call_offloaded`), then **encoded as blocks** — doc ids the entries'
surrogate ids, exact `dl`, the query terms' `tf` — and handed to
`score_blocks` with the epoch's idfs and `avg_dl`. Same formula, same
accumulation order, same rounding as the index side, by construction.
An overlay entry answers as a whole document: one `Match` spanning its
lines, no chunk text (previews are spec 133's). The two-read protocol
of ADR 044 applies verbatim: the pointer read is advisory, a non-empty
overlay verdict settles it, an empty one is re-read after the fetch
and doubles as the epoch recheck; a moved pointer raises
`StaleSnapshot`.

### Entries out

MaxP: `max` over an entry's chunk scores; the top-K (`TOP_CHUNKS = 3`)
chunk rows ride as `Match(start=line_start, end=line_end, match=None,
content=chunk text, score=chunk score)`. Scores are **min-max
normalised over the candidate union** (index and overlay entries
together; one entry → 1.0), rounded to `SCORE_DECIMALS = 9`, ordered
`score DESC, path ASC` — spec 131's laws, so the ordered top-10 pins
carry over. The mask carries `path, kind, version` (the identity law)
plus the projected entry fields, `score`, and `matches`.

Term statistics ride the envelope as the extra field `lexical_stats`
(`n_docs`, `avg_dl`, per term `df`/`idf`) — `Result` is
`extra="allow"`; the router (spec 137) reads it.

### Records

`invalid` for a query with no post-fold term; `truncated` (warning)
for the overlay budget (`data={"scanned", "unconsulted"}`), the scope
probe, and the entry limit when the chunk window was full and the
entries still ran short; every warning carries structured `data`, never
a parsed message.

### Surface

`DatabaseStorage.glean` matching `SupportsGlean` exactly (so
`storage_ops` grows `glean`, `InMemoryStorage` inherits it); traits
`glean_signals="lexical"`, `glean_staleness="overlay"` — both keys
added to `TraitKey`/`TRAIT_VALUES`; ctor `glean_wall_seconds`.
Helpers shared with grep move to one owner: `pointer_with_overlay` →
`indexing.py`, `content_for_entries` → `reads.py`.

### Tests

`tests/storage/database/test_glean.py` (rungs, overlay, records, the
protocol under the seam), conformance rows (`scoped`, `piped`,
dirty-set, trashed rows excluded, entries-not-chunks, identity mask,
traits) and the harness arm `glean` in `tests/ranking` — its nDCG@10
must equal BM25's on every corpus (it *is* the baseline; any gap is a
bug) — with the engine-leg pin rows pointed at `glean`.

## Trade-offs

- Rung B can under-fill a wide scope whose matches lie elsewhere; two
  probes then a loud record is the bound the spec asks for, not exact
  recall at any cost.
- The overlay scores whole entries, not chunks; its rows carry no
  chunk text until spec 133 builds previews. Recorded, not hidden.
- Min-max over the union makes scores comparable across mounts at the
  cost of meaning nothing absolute — ADR 052's contract.
