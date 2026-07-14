# 072 research — grep at scale: the trigram index tier, from source

- **Date:** 2026-07-12
- **Method:** four parallel researchers over local checkouts of
  `codesearch` (Russ Cox, 64-bit version), `zoekt`
  (sourcegraph/zoekt @ 071adfde), and `postgres` (`contrib/pg_trgm`),
  each grounded in `spec.md` §6 and the live vfs planner/schema
  (`code_grams.py`, `rows.py`). Every claim below is cited to source;
  extrapolations are flagged.
- **Positions under evaluation** (supersede the earlier research.md §2
  "grams deferred whole" conclusion):
  1. Grep must scale to millions of documents — the gram index is a
     core 0.1.0 deliverable, not a deferred tier.
  2. Index-required grep is **on by default**: patterns that cannot
     benefit from the index are refused with a classified error;
     devs can opt out per call.
  3. The staging/fold/compact pipeline is dropped. No `auto_index` on
     writes — indexing is a batch process at intervals.

## Bottom line

All three positions survive review, and the third gets *stronger*:
batch-only reindex with epoch-scoped posting rows makes the posting
store immutable-per-epoch, which is the only model either reference
engine ever shipped (zoekt: immutable shards, delta path fenced as a
self-described "HACK"; codesearch: write-once index, merge offline).
The refusal predicate already exists in the live planner (`GramAny`),
and vfs's `posting_list.doc_count` strictly dominates zoekt's
frequency proxy. Two corrections to absorb: (a) zoekt's
2-rarest-gram intersection is only sound for *positional* postings —
vfs's doc-level postings need rarest-first intersection of ~2–8 grams
with early exit; (b) the review found a **confirmed false-negative
bug** in `code_grams.py` (per-codepoint NFC normalization) that must
be fixed before the index tier ships (§5). The Postgres provider can
ride `pg_trgm` GIN natively, dropping the portable tier's scale bar
to SQLite-class deployments — where the blob-posting design is
plausible at 1M docs subject to one spike-measurable cliff
(pure-Python γ-decode throughput).

## 1. The refusal predicate — static, and it already exists

Both engines detect "unindexable" identically and neither refuses —
they scan. codesearch's condition is `RegexpQuery(re).Op == QAll`
(simplification guarantees `QAll` never hides inside a live AND,
`index/regexp.go:52-113`); zoekt's is `regexpToMatchTreeRecursive`
returning `bruteForceMatchTree` (`index/eval.go:616-693`). vfs's
planner computes the same condition as `GramAny`
(`code_grams.py:341-412`): it already collapses
OR-with-unconstrained-branch, gramless runs, empty patterns, and
sub-3-byte fixed strings.

**The gate vfs should ship:**

1. `re.compile(pattern, flags)` first — failure classifies as
   *invalid pattern*, never as unindexable (the planner returns
   `GramAny` on sre errors, which would misreport broken regexes).
2. `build_code_gram_query(pattern, folded=True)` — **folded
   unconditionally, for every case mode** (see §5.2).
3. Refuse iff `q.is_any()` → classified kind (e.g.
   `unindexable_pattern`), message naming the cause ("no literal run
   of ≥3 bytes survives folding") and the opt-out parameter.
4. Per-call opt-out (`allow_scan=True`) skips step 3 and runs the
   scan/verify tier.

Edge cases, resolved consistently with both engines: empty pattern,
anchor-only (`^$`, `\b`) → refuse. `.*foo.*` → indexable (min-0
wrappers drop out; verified against the live planner). `foo|ab` →
refuse — an alternation with one sub-3-byte branch is unindexable in
both engines (codesearch `regexp_test.go:60`, zoekt
`eval.go:678-682`). `(?i)Foo` → indexable under always-folded
planning.

**Do not build a "weakly indexable" refusal tier.** Neither engine
refuses on weak narrowing; the precedented mitigation is
execution-side (§2). The static gate is pattern-shape only;
selectivity is a runtime budget, enforced with caps and a
truncation/late-refusal signal, not a plan-time prediction.

Pattern-class taxonomy (for docs and tests): *fully indexable* —
case-sensitive literal ≥3 bytes, concatenations/alternations of such
literals; *partially indexable* — literals embedded among `.`/`.*`/
classes/min-0 quantifiers, case-insensitive literals, alternations
where every branch carries a ≥3-byte literal; *unindexable* — no
required literal reaches 3 bytes, match-all subexpression swallowing
the pattern, alternation with an unindexable branch, over-broad OR
cross-products.

## 2. Execution policy — the four pieces, amended for doc-level postings

The four-piece minimal query path is confirmed with evidence, plus
one amendment and one correction.

**The correction: zoekt's "intersect only the 2 rarest grams" does
not transfer.** Zoekt's postings are *positional* (varint deltas of
rune offsets, one entry per occurrence, `shard_builder.go:238-247`),
so two grams plus an exact rune-distance constraint
(`distanceHitIterator`, `hititer.go:39-113`) are highly selective.
vfs's postings are doc-level (codesearch-shaped). The right model is
codesearch's intersection order, upgraded with zoekt's frequency
awareness:

- Sort required grams ascending by `doc_count`; any gram with no
  posting row → return empty immediately (zoekt's `freq==0`
  short-circuit, `indexdata.go:446-455`).
- Intersect rarest-first with early exit: stop when the running
  candidate set is ≤ ~1,000 docs or two consecutive grams shrink it
  by <10% (judgment values — spike-tunable).
- Cap grams fetched at ~8; skip outright any gram with `doc_count`
  above ~25% of corpus (the blob costs more than the narrowing it
  buys).
- **Authoritative Python `re` verification of every candidate,
  unconditionally** (zoekt `matchtree.go:810-845, 958-988`;
  codesearch re-greps candidate files).

**The amendment — staged evaluation (zoekt's cost ladder,
`matchtree.go:53-60`, `eval.go:276-289`):** apply path/metadata
predicates to the candidate doc set *before* fetching content for
regex verification. In SQL terms: join candidates to `entries` with
the path/soft-delete/scope predicates first, then fetch content for
the survivors only. This join is also the deletion filter (§3).

**Frequency proxy:** zoekt's "frequency" is literally the posting
blob's byte size (`indexdata.go:437`) — it has no count. vfs stores
both `doc_count` and `byte_size` per posting row and strictly
dominates: use `doc_count` for selectivity policy, `byte_size` for
I/O budgeting.

**Runtime budgets** (neither engine refuses; both cap output work —
zoekt `ShardMaxMatchCount=100_000`, `TotalMaxMatchCount=1_000_000`,
`MaxWallTime`, `api.go:976-1032`): cap docs fetched+verified per
query at ~10,000 with an explicit truncation flag on the Result; cap
total posting bytes fetched (a few MB); honor a wall-time deadline.
These are extrapolated values, not copied constants — the spike
calibrates them.

**Posting encoding:** no chunking/paging — neither engine pages
posting lists. Worst-case doc-level blob at 1M docs is ~125–200 KB
(γ-coded; arithmetic in §4) — fine as a single SQL blob. The policy
refuses to *fetch* hot-gram blobs rather than paging them.
codesearch's format is the direct precedent for
`ENCODING_DELTA_GAMMA` (γ-coded doc-id deltas, `read.go:31-45`);
the per-row `encoding` tag is the escape hatch to flip hot grams to
roaring bitmaps if the spike says Python γ-decode can't keep up.

## 3. Freshness — batch-only reindex, epoch-scoped, dirty overlay

**Batch-only is strongly supported.** Zoekt's shipped model is
wholesale per-repo rebuild; the delta path is an allowlisted
experiment fenced by six hard-error fallbacks whose own comments call
the compaction story a "HACK... while we create a better compaction
strategy" (`gitindex/index.go:876-883`). codesearch never implemented
incremental update at all (`write.go:33-36`). Dropping staging/fold
also removes the one genuinely novel (unprecedented) piece of the old
design: neither reference engine ever mutates a posting in place.
**Consequence: the `gram_staging` table and fold machinery leave the
schema entirely.**

**Epoch stamp = three-part fingerprint, not a timestamp** (zoekt's
`IndexState`, `builder.go:396-447`):

1. index format version — mismatch → drop-and-rebuild, never migrate
   (zoekt has no migration path anywhere; `toc.go:31-69`,
   `read.go:268-285`);
2. hash of index-affecting options (gram config, folding, size caps —
   zoekt's `HashOptions`, `builder.go:127-157`);
3. content watermark: **max entry revision at build time**. This is
   also the dirty-overlay predicate for free
   (`WHERE revision > index_epoch_revision`) — and a second
   independent reason the §5 revision stamp must ship in Pass A.

**Atomic publication is cleaner in SQL than in zoekt:** build posting
rows under `epoch = N+1` (invisible — readers filter on the current
epoch), flip the current-epoch pointer row in one transaction, then
delete old-epoch rows (a separate, slower reclamation step — zoekt
runs vacuum/merge on 8h/24h loops, decoupled from publication).
Zoekt needs rename choreography plus crash-cleanup sweepers to
approximate what a transaction gives vfs outright
(`builder.go:262-264, 777-802`).

**Deletions between rebuilds need no tombstone table.** Zoekt leaves
stale postings on disk and masks them per-candidate at eval
(`eval.go:222-238`). vfs's analogue is the §2 join back to live
non-deleted `entries` before verification — required anyway because
trigram hits are candidates, not answers. The entries table *is* the
tombstone.

**Dirty overlay — architecturally attested, implementation
unverified locally.** Zoekt's API is explicitly shaped for it
(`MinimalRepoListEntry.Branches` exists so "Sourcegraphs query
planner [can decide] if it can use zoekt or go via an unindexed code
path", `api.go:863-878`), but the union itself lives in the
sourcegraph monorepo (not on disk). Two requirements the zoekt shape
implies:

1. Both sides must exclude each other's territory — index results
   filtered to entries *not* in the dirty set, scan results only
   over the dirty set — or modified entries double-hit.
2. The dirty set needs a size cap with a visible response (forced
   reindex trigger or surfaced degradation) — an ever-growing dirty
   set silently degrades grep to scan-tier.

**Cadence ≠ rebuild.** Sourcegraph's loop checks every minute
(jittered) but rebuilds only on fingerprint mismatch, with linear
failure backoff (×10min, cap 120min) and stale-first priority. vfs's
reindex verb must be idempotent-cheap when the watermark says nothing
changed. For 0.1.0: an explicit reindex verb + the epoch fingerprint;
scheduling is the caller's problem.

## 4. Scale — portable tier plausible at 1M docs; Postgres rides pg_trgm

### Portable tier (SQLite-class)

Arithmetic (assumptions flagged; spike measures them): ~5 KB/doc
average → 1M docs ≈ 5 GB corpus; ~2–3K distinct grams/doc →
~2.5×10⁹ (gram, doc) pairs; γ-coded posting volume ≈ **2.5–4 GB
total** across ~1–5M posting rows (24-bit byte-gram space caps at
16.7M; zoekt's measured reality is 282K distinct trigrams per 100 MB
shard, power-law distributed — median posting list 10 bytes, 78%
under 64 bytes, `shard_builder.go:113-118`). Hot-gram blob worst
case ~125 KB. Both engines independently chose 20,000 distinct
trigrams/doc as the "probably not text" rejection threshold — adopt
it.

**The real cliff is decode throughput, not blob size.** codesearch
decodes *every* required gram's full posting list (`read.go:561-606`)
— viable in Go over mmap, not in pure Python. Mitigations, in order:
k-rarest intersection (§2) so hot blobs are never fetched; then, if
the spike says γ-decode still can't keep up, flip hot grams to
`ENCODING_ROARING` with a C-backed roaring library. Doc-id-range
chunking is worth *reserving* in the format but not building.
Rebuild memory is a non-issue if the build streams gram-by-gram
(codesearch's external-sort discipline: 64 MB chunks,
`write.go:67`); never materialize all pairs at once.

### Postgres provider (`pg_trgm`)

`gin_trgm_ops` accelerates `LIKE`/`ILIKE`/`~`/`~*`;
`trgm_regexp.c` compiles a regex into a trigram AND/OR *graph*
evaluated per GIN entry — genuine index-accelerated regex. Every
strategy sets `recheck=true`, so it is structurally a
candidate-filter + authoritative-verify design, same as vfs. Its
index is always case-folded (compile-time `IGNORECASE`,
`trgm.h:19-25`) — the same single-folded-stream decision vfs made.

Gotchas, in bite order:

1. **Silent full-scan degeneration** — on bail-out pg_trgm sets
   `GIN_SEARCH_MODE_ALL` with no error or warning. Exact bail-outs:
   color classes >256 chars (so `.`, `\w`, negated classes
   contribute nothing); graph explosion (>128 states / >1024 arcs →
   only the regex *prefix* constrains the index); no unavoidable
   trigram → NULL; >256 trigrams after pruning
   (`trgm_regexp.c:221-225, 591-603, 941-953`). The provider keeps
   vfs's own static refusal gate in front so worst case is
   refused-or-slow-correct, never surprising.
2. **Word-character-only trigram alphabet** (`ISWORDCHR` =
   alphanumeric, `trgm.h:50`): underscores, `->`, `::`, `!=` never
   appear in any indexed trigram; `foo_bar` indexes as two
   independent words. pg_trgm is *less selective than vfs's byte-gram
   planner on exactly the patterns code search cares about* — this is
   why `code_grams.py` exists, and the recheck ratio on
   operator-dense patterns is a spike measurement.
3. **Regex dialect**: Postgres ARE ≠ Python `re`. Two safe shapes:
   (a) declare provider grep as Postgres-regex semantics via a
   capability trait; (b) keep Python authoritative — use vfs's own
   planner to extract required runs, issue
   `content ILIKE '%<run>%'` conjunctions (accelerated by the same
   GIN index), Python-verify. (b) is provably a superset filter and
   is the recommended default.
4. **Maintenance**: GIN build wants `maintenance_work_mem`; on
   write-heavy mounts set `fastupdate=off` or tune
   `gin_pending_list_limit` (pending-list flush stalls, and
   unflushed pending pages are scanned linearly by every query).
5. **Provisioning under spec §8**: `pg_trgm.control` is
   `trusted=true`, so `CREATE EXTENSION IF NOT EXISTS pg_trgm` is
   legitimate first-touch DDL for a database-owner role; otherwise
   declared-external with a capability gate that omits accelerated
   grep. Never sniff catalogs.

**Verdict B: yes** — the provider override drops the portable tier's
scale requirement to SQLite-class deployments, which per Verdict A it
can clear.

## 5. Defects found in live vfs code (blocking or near-blocking for the index tier)

1. **Confirmed false-negative bug — per-codepoint NFC in
   `code_grams.py`.** `_emit_literal` NFC-normalizes each codepoint
   alone while the index stream is whole-string NFC. Empirically
   verified: NFD-stored content (`cafe` + U+0301) matches the
   authoritative `re.search`, but the pattern's required grams are
   absent from the index — the file is silently dropped from
   candidates, violating the module's own never-false-negatives
   contract. Fix: NFC-normalize each joined run (or the whole pattern
   before `sre_parse.parse`), not per-codepoint. **Must land before
   the index tier ships.**
2. **Raw (non-folded) planning is unsound against a folded-only
   index.** Verified: raw-mode grams for `Foo` do not exist in a
   folded stream → silent false negatives. Grep must plan
   `folded=True` for every case mode (fold the pattern for candidate
   lookup; verify case-sensitively). Guard or remove the raw query
   path. One edge worth a test: folding can shorten a pattern below
   3 bytes (`ẞ` → `ss`), flipping indexable → refused.
3. **Over-conservative anchor handling.** The planner flushes literal
   runs at zero-width nodes (`^`, `$`, `\b`); codesearch treats them
   as adjacency-transparent (`ab\bc` still yields `"abc"`,
   `regexp_test.go:79`). Sound but loses grams; treating `AT` as a
   no-op is a safe improvement.
4. **No small-char-class expansion.** `[fF]oo` → `GramAny` → refused,
   while `(?i)foo` indexes — an asymmetry users will hit. Bounded
   class expansion (codesearch caps at 100 runes; vfs could cap at
   ~4) is the single highest-value planner upgrade for shrinking the
   refusal set.
5. Minor: seam grams across min≥1 repeats (`a+hello` misses `"ahe"`;
   codesearch bridges it) — sound, weaker, low priority. Smart-case
   detection in the memory backend uses `.lower()` while the index
   folds with `.casefold()` — no unsoundness found, but unify when
   grep is wired to grams.

## 6. Consolidated design for spec §6 (replaces the open question)

- **Grep ships with the gram index, write+read together, as a core
  pass** — not deferred to a trailing Pass C. The scan/verify
  machinery is built as permanent code (it is the verification layer
  and the opt-out/overlay engine), but scan-over-everything is never
  the default public behavior.
- **Static refusal gate**: compile → plan folded → refuse on
  `GramAny` with a classified kind and per-call `allow_scan` opt-out
  (§1). No weak-selectivity refusal tier; runtime budgets instead
  (§2).
- **Execution**: rarest-first doc_count-ordered intersection, ~2–8
  grams, early exit, empty-posting short-circuit, metadata-join
  before content fetch, unconditional Python `re` verify,
  capped + truncation-flagged output (§2).
- **Index lifecycle**: batch reindex verb; epoch-scoped posting rows;
  three-part fingerprint (format version, options hash, max-revision
  watermark); one-transaction epoch flip; decoupled old-epoch
  reclamation; drop-and-rebuild on any format/options mismatch;
  dirty overlay (index over ≤ watermark ∪ scan over > watermark,
  mutually exclusive) with a capped dirty set (§3). `gram_staging`
  and the fold pipeline are deleted from the schema.
- **Capability surface**: grep's tier (gram vs scan) and its
  eventual-consistency window are declared traits; the refusal
  behavior and opt-out are part of the documented contract.
- **Ripples**: revision stamp is doubly mandatory in Pass A (§3
  watermark); the `code_grams.py` NFC bug and folded-only wiring
  guard are prerequisites; conformance harness gains pattern-class
  taxonomy tests (§1) and the fold-shortening edge (§5.2).

## 7. What only the spike can answer

> **Answered 2026-07-12** — see `spike-results.md`. Headlines: portable
> tier clears 1M docs (selective grep 0.3–80 ms; full rebuild 3.3 min);
> v1 encoding flips to delta+varint (γ dropped); k=4 rarest default;
> pg_trgm loses to the byte-gram tier 3–79× on code-shaped patterns at
> 495K docs, so the provider override is narrow, not wholesale.

On a real code corpus (few large OSS repos flattened), varying
N ∈ {10K, 100K, 1M} docs and doc-size distribution:

**Portable (SQLite):** measured distinct-grams/doc and gram-frequency
distribution for 24-bit byte grams (the 2–3K/doc figure is
extrapolated from rune-gram engines; punctuation-rich code differs);
pure-Python γ-decode throughput vs `pyroaring` vs numpy-vectorized
varint (**this single number decides whether `ENCODING_ROARING` is
v1 or deferred**); query latency vs k (grams intersected,
k ∈ {1,2,3,4,all}) × pattern class {rare identifier, hot identifier,
punctuation-heavy, sub-3-byte}; candidate false-positive counts
feeding Python verify; full epoch rebuild wall-clock and peak memory
at each N; SQLite blob overflow-page read cost vs `page_size`.

**Postgres provider:** GIN index size/build time at 1M docs; recheck
ratio per pattern class (especially punctuation-dense); frequency of
regex bail-out (`GIN_SEARCH_MODE_ALL`) over a realistic pattern log;
`fastupdate` on/off × churn rate → p99 latencies; `~ pattern`
end-to-end vs ILIKE-conjunction + Python verify.

**Flagged as estimates, not source-derived:** avg doc size (5 KB),
per-doc gram dedup ratio, corpus-wide distinct-gram count, Python
γ-decode throughput, GIN size ratio. Everything else above is cited.
