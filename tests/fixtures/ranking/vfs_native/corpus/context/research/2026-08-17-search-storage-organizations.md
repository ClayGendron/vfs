# Storage-side organizations for fast search: the field, priced on our corpus

- **Status**: research memo — design input for choosing the next
  storage structure(s) after spec 104. The question was deliberately
  wider than SQL column indexes: *any* storage-side organization that
  makes searches faster (posting families, positional data, chunk
  keying, physical layout, caches, sidecar metadata). Every candidate
  was both located in the field and priced on the real linux store;
  four are recommended, five are ruled out with measurements.
- **Date**: 2026-08-17
- **Owner**: Clay Gendron
- **Question**: With the scoped-grep work landed (10 of 12 scoped
  rows faster than rg, fetch bytes now the dominant cost of every
  heavy row), what storage-side organizations — beyond column
  indexes — would make vfs search faster still, what do they cost,
  and in what order should they be considered?
- **Evidence gathered**: (a) a source-level field study of zoekt,
  codesearch, SQLite FTS5, PostgreSQL GIN/pg_trgm, livegrep, roaring
  bitmaps, Lucene/ES caching, and chunked-storage systems
  (`studies/2026-08-17-search-storage-organizations/FIELD.md` +
  per-system cited notes); (b) seven executed feasibility
  experiments on the 2026-08-16 linux store, 93,760 files, replaying
  the live nomination pipeline (`ARITH.md` + raw JSON + scripts,
  same directory). Cites and describes only — every line of vfs
  code stays ours.

---

## 1. The cost structure this research prices against

After the spec-104 arc and the perf landing (`1b36b4a`), heavy grep
rows are **fetch-byte bound**: `mutex_lock` scoped to
`drivers/gpu/drm/**` fetches 93.8 MB of bodies for 2,506 matching
lines; unscoped `copyright -i` fetches 419.9 MB truncated at 25,000
candidates. Verify is ~7.6 ms for 94 MB (rayon Rust core); assembly
and the per-call floor are ~ms-scale. The competitor's remaining
edge is structural: ripgrep reads only the bytes it needs via
parallel mmap; vfs ships every candidate's whole body out of SQL.
Codesearch — whose design vfs currently mirrors — declined
positional postings under a page-cache-warm cost model that does not
hold when bodies live behind SQL round trips. No planner precision
fixes this: zero false positives still transfers every true
candidate's full content.

## 2. The big lever: sub-document (chunk) nomination and fetch

**Field**: verifying at sub-document granularity is mainstream, not
exotic — Elasticsearch chunk postings carry (start, end) offsets,
Lucene stored fields chunk at ~16 KB with per-block lengths,
seaweedfs's read path is exactly "resolve chunks overlapping a
range, clip, fetch". The unanimous shape: chunks keyed by
**entry + ordinal with offset columns** (never content hash — that
is dedup's key and it destroys offset arithmetic), fixed boundaries
at retrieval scale (16–64 KB), and one load-bearing correctness
rule: **boundary-straddling grams must be covered at index time**
(emitted to a neighbor or via overlap) — a straddled trigram missing
from postings is an unrecoverable false negative.

**Arithmetic** (store already holds `vfs_chunks`: 726,817
entry-keyed rows with line ranges and content):

| row | bytes today | match-holding chunks only | reduction |
| --- | --- | --- | --- |
| mutex_lock @ drivers/gpu/drm/** | 93.8 MB | 3.3 MB | **28.8×** |
| kzalloc @ drivers/net/** | 64.7 MB | 5.6 MB | **11.5×** |
| EXPORT_SYMBOL_GPL @ drivers/** | 111.6 MB | 13.4 MB | **8.4×** |
| copyright -i unscoped (truncated) | 419.9 MB | 39.3 MB | **10.7×** |

Realistic chunk-gram nomination lands ≈ at this ideal bound —
chunk-level false positives measured negligible. Fetch time for the
chunk set: 64.2 ms cold / 2.5 ms warm vs 168.8 / 17.4 ms for full
bodies. **Cost**: (gram, chunk) postings are 2.42× (gram, file)
pairs; encoded blob bytes 2.38× (141.5 MB → ~337 MB projected).
The measured boundary-straddle hole (0.01–0.47% of match-holding
chunks under naive chunk-local grams) confirms the field's rule as
mandatory, not theoretical.

**Prototype (executed after the arithmetic — `chunk-prototype/`
under the study dir): the byte bound did NOT convert into an
end-to-end win on local SQLite.** A real chunk-granularity posting
family was built on a clone (Rust engine, same codec, 11.7 s;
measured cost **2.73×** blob bytes — the 2.38× sample projection
underestimated) and driven by a paired harness (identical pipeline,
chunk vs file posting source, exact-recall checked). The fetch-byte
cut delivered (6.6× across the suite) but warm wall time is a net
**loss** — geomean 0.78× — and cold results are mixed (mutex_lock@drm
1.49×, copyright-at-equal-work 1.37×, but kzalloc 0.85×, kfree
0.91×). Root cause: warm SQLite serves bytes at page-cache speed
(~17 ms per 94 MB), so saved bytes buy little, while cold cost is
**row-shaped, not byte-shaped** — 3,175 scattered 2 KB chunk rows
cost what 1,437 full bodies cost. The 2 KB semantic chunks multiply
candidate rows 2.2–2.8×, and that multiplier eats the byte win.

Facts the prototype settled regardless: **zero** bench-pattern grams
contain a newline (pinned over all 37 patterns); purely chunk-local
emission lost **zero matching lines** on every row (a line dies only
if the occurrence itself is split — never observed; 18 file-only
grams exist corpus-wide, all unreachable by line-scoped patterns —
a production design should still emit a 2-byte boundary tail);
the feared rare-pattern regression inverted (randomize_kstack_offset
is chunking's best win, 1.60× cold); the posting-cost side never
hurt (≤472 KB read per row); chunk-unbounded `copyright -i` serves
**full recall** (88,861 lines, 779 ms) where file mode truncates
(40,926 lines) — the recall story is real even where the speed story
is not. One hazard for any future spec: the candidate budget must be
**entry-denominated** — at 25,000 *chunks*, one row returned 0 of
601 lines (truncation before the name gate).

**Verdict: parked — does not clear its bar on SQLite.** The
deployment whose cost model matches the lever's premise (row-shaped
fetch over a *network*, where bytes-on-the-wire are the real
currency) is untested; re-open with a networked-engine measurement.
If re-opened: 16–64 KB fixed retrieval chunks (not the 2 KB semantic
chunks — cuts the row multiplier ~10×), entry-denominated budgets,
interval bounds on entry rows, boundary-tail emission.

## 3. Recommended beside it

- **Bytes-through content path** (independently re-confirmed): the
  seam's UTF-8 re-encode is 4.9 ms of the 7.6 ms verify on 94 MB,
  and the earlier fetch study measured `CAST(content AS BLOB)` at
  ~25% off fetch+encode combined. Chunk fetch shrinks the bytes;
  bytes-through stops re-encoding the ones that remain. The
  line-offset sidecar died in its place (§5) — the Rust core never
  scans lines wholesale.
- **Segmented posting blobs + GIN overlay discipline** (additive,
  at-scale): GIN stores posting data as independent 128–384 B
  segments with skip metadata precisely so intersection can skip
  without full decode; FTS5's analog is absolute-restart pages plus
  `first/last`-doc columns — SQL-native skip metadata vfs can put
  in ordinary columns beside posting-chunk rows. GIN's fastupdate
  pending list is our scan-tier overlay independently derived, with
  hardening rules worth adopting verbatim as discipline (overlay
  scanned first — ordering is load-bearing; idempotent
  publish-then-unlink merge; size-capped backstop that yields to a
  rival merger). None of this changes query semantics; it bounds
  decode work as corpora grow past in-memory posting intersection.
- **Epoch-keyed caching — recorded for the networked-engine
  future, marginal today**: the field point is strong (Lucene/ES
  caching rests entirely on segment immutability; our epoch pointer
  gives the same invariant corpus-wide, a perfect invalidation
  key), but the measured demand is thin — exact-repeat rate in
  10,929 re-mined agent searches is 8.2% overall and **6.3% on the
  expensive shapes**, and on sqlite the mmap/page-cache landing
  already serves the content-locality need. The
  `(epoch, doc) → content` LRU becomes the interesting piece when a
  networked engine (Postgres et al.) puts real latency behind every
  body fetch — that is the deployment where this graduates.

## 4. A hypothesis this research killed before it was built

**The case-folded gram family is already shipped.** The gram index
is a single folded stream and the planner is case-blind:
`copyright` sensitive and `-i` compile to the *identical* 7-gram
plan reading the same 237 KB of postings. The imagined "-i tax"
does not exist — `copyright -i`'s 712 ms is candidate mass, which
is §2's problem. (A raw, unfolded index would have needed 8× the
lookups; folding also shrinks the index — pairs at 89.9%, vocab at
71.2% of raw.) This entered the research as a promising candidate
and would have been a wasted spec.

## 5. Ruled out, with the numbers that ruled them

- **Positional postings (zoekt-style exact offsets)**: 7.70
  positions per posting measured; delta-varint ≈ +2.03 GB on a
  141.5 MB index — **15.3×**, bigger than the 1.22 GB content it
  indexes. Chunk granularity (§2) buys the same fetch reduction at
  2.38×. Zoekt's two-blob distance merge dies with it (needs exact
  offsets). FTS5's documented tiers corroborate: positions cost
  5.5× vs docid-only.
- **Content clustering by path**: the store is already **1.05×
  from optimal** — build inserts in path order; four fetch
  orderings differ < 7% cold. Nothing to win here on sqlite;
  revisit only with networked-engine evidence.
- **Content-addressed dedup**: 0.61% duplicate files / 0.27%
  duplicate bytes corpus-wide; zero duplicate candidates in the
  scoped bench rows. Dead at this corpus's shape.
- **Line-offset sidecar**: whole-corpus verify is 7.6 ms; the Rust
  core resolves lines lazily already. Win ceiling ≪ 5 ms.
- **Suffix arrays (livegrep)**: RAM-resident monolithic permutation,
  unbatchable random probes — irreconcilable with epoch-swapped SQL
  rows. **Roaring bitmaps**: density floor (papers' own ~0.1%) sits
  above our rare-gram tail where delta-varint is equal or smaller;
  headline speedups are vs RLE bitmaps, not sorted varint lists.
  **FTS5's LSM merge / GIN posting trees**: concurrency machinery
  the epoch rebuild-and-swap already obviates — FTS5's delete
  path is the best argument *for* our wholesale swap.

## 6. Recommended order (for the decide stage)

Revised after the chunk prototype's end-to-end measurement (§2):

1. **Bytes-through content path** — now the top open lever on
   SQLite: ~25% off fetch+encode (two independent measurements)
   plus the 4.9 ms verify-side encode; a contained seam change
   (dialect-gated BLOB cast, bytes-capable verify, decode-on-hit).
2. **The overlay-probe composite index**
   (`2026-08-17-overlay-probe-cost.md`) — the cheapest measured
   win, ~1.3 ms off every call.
3. **Segmented posting blobs with skip-metadata columns + GIN
   overlay discipline** — additive hardening; sized for corpora
   beyond linux-scale.
4. **Chunk-granularity nomination — parked with conditions**
   (§2): refuted end-to-end on local SQLite by the prototype;
   re-open only with a networked-engine measurement, and then with
   16–64 KB retrieval chunks, entry-denominated budgets, and
   boundary-tail emission. Its one standing merit today is recall
   (`copyright -i` full-recall at 779 ms vs file-mode truncation) —
   if truncation-free saturated queries become a requirement, this
   is the recorded design.
5. **Epoch-keyed caches** — parked with the same networked-engine
   trigger.

All five are independent; nothing here blocks anything else.
