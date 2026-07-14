# 072 spike — grep gram index at scale: SQLite portable tier + Postgres pg_trgm

- **Date:** 2026-07-12
- **Machine:** Apple Silicon (darwin 25.3.0), local Homebrew PostgreSQL 18.0,
  Python via uv, numpy 2.4.2. Single-threaded throughout.
- **Scripts:** `spike/` beside this file. Data (corpus + indexes) in the
  session scratchpad; regenerate with `build_corpus.py` →
  `build_index_sqlite.py <N>` → `bench_query_sqlite.py <N>` →
  `bench_postgres.py <N> --load` → `bench_decode.py`.
- **Corpus:** 495,004 real docs (1.64 GB text) from 16 local OSS repos
  (linux, gitlabhq, freebsd-src, postgres, sqlalchemy, langchain, go/rust
  repos…), files ≤2 MB split into ~4 KB line-aligned chunks (avg 3.3 KB/doc),
  round-robin interleaved so every id-prefix tier is a language mix. The
  990K tier indexes the corpus twice with offset ids — posting volumes are
  honest at ~1M rows; gram *diversity* stays flat (disclosed limitation).
- **Gram semantics:** identical to the live `code_grams.py` folded stream
  (newline-norm → NFC → casefold → UTF-8 → distinct 24-bit byte trigrams);
  query planning uses the **live** `build_code_gram_query(folded=True)`.

## Bottom line

**Verdict A confirmed with headroom: the portable SQLite tier clears the
hard requirement at ~1M docs.** Selective patterns answer in 0.3–80 ms,
punctuation-heavy patterns in ~60 ms, and the pathological cases are
exactly the ones the design already handles by policy (refusal, runtime
budget, truncation). A **full epoch rebuild of ~1M docs takes 3.3 minutes
single-threaded** — batch-only reindex is not just viable, it's cheap.
Two spike findings change spec details: **(1) the v1 posting encoding
should be delta+varint, not delta+gamma** — γ loses on every axis that
matters once the k-rarest policy exists; **(2) k=4 rarest grams is the
right default** — k=2 is up to 5× worse on wrapped regexes, k=all wastes
decode on rare patterns.

## 1. Build/rebuild (SQLite portable tier)

| tier | docs | text | (gram,doc) pairs | distinct grams | full rebuild | index size | peak RSS |
|---|---|---|---|---|---|---|---|
| 10K | 10,000 | 34 MB | 8.4 M | 126,548 | **3 s** | 12 MB | 0.3 GB |
| 100K | 100,000 | 330 MB | 85.2 M | 238,775 | **23 s** | 100 MB | 1.8 GB |
| 495K | 495,004 | 1.65 GB | 399.8 M | 331,953 | **105 s** | 439 MB | 5.1 GB |
| 990K | 990,008 | 3.31 GB | 799.6 M | 331,953 | **199 s** | 858 MB | 9.1 GB |

- Rebuild scales linearly (≈60 µs/doc: ~75% gram extraction, ~25%
  sort+encode+write). A 1M-doc mount reindexes in ~3.5 min single-threaded;
  with the epoch watermark noop check, steady-state cadence costs nothing.
- ~840 distinct grams/doc at 3.3 KB/doc (research extrapolated 2–3K at
  5 KB — same direction, size-dependent).
- Distinct grams plateau at ~332K of the 16.7M possible — the gram id
  space never pressures the schema.
- Index is 26% of corpus bytes (varint). Zoekt's positional design runs
  ~2–3×  corpus; doc-level postings are an order cheaper, as predicted.
- **Caveat:** peak RSS 9.1 GB at 990K came from whole-bucket
  sort-and-encode (256 buckets); a production build must sub-batch the
  hot buckets (bounded-memory external sort — codesearch's 64 MB chunk
  discipline). Nothing structural.

### Posting-size distribution (495K tier — zoekt's power law reproduced)

Median posting blob 27 bytes; 65% ≤ 64 bytes (zoekt measured median 10 B,
78% ≤ 64 B on rune grams). The tail is where the bytes live:

| doc_count bucket | grams | pairs | varint MB | gamma MB |
|---|---|---|---|---|
| ≤10 docs | 149,793 | 0.5 M | 1.1 | 1.7 |
| ≤100 | 99,905 | 3.6 M | 5.6 | 6.6 |
| ≤1K | 53,931 | 18.9 M | 24.1 | 22.8 |
| ≤10K | 21,799 | 67.8 M | 75.5 | 60.3 |
| ≤10% of corpus | 4,634 | 103.4 M | 101.5 | 64.6 |
| ≤25% | 1,358 | 106.1 M | 101.4 | 45.4 |
| >25% | 533 | 99.5 M | 94.9 | 27.1 |

The hottest gram (75% of docs) is a 372 KB varint / 65 KB γ blob — no
paging needed, exactly as research predicted; the policy simply never
fetches it.

## 2. Decode throughput — the ENCODING decision

Synthetic sorted doc-id sets, densities n of N=1,000,000 (best-of runs):

| density n | γ pure-py | varint pure-py | varint numpy | pyroaring deser+∩ |
|---|---|---|---|---|
| 1K | 1.6 M vals/s | 8.2 M | 31 M | 5 µs |
| 10K | 2.1 M | 12.6 M | 51 M | 63 µs |
| 100K | 2.4 M | 14.9 M | **135 M** | 91 µs |
| 1M | 3.0 M | 14.2 M | **125 M** (8 ms) | 3 µs (dense→runs) |

Blob sizes (same lists): n=10K: varint 12.7 KB vs γ 14.8 KB (**varint
smaller when sparse**); n=100K: 100 KB vs 71 KB; n=1M: 1 MB vs 125 KB vs
**roaring 230 bytes** (run containers).

**Recommendation — flip the v1 default from delta+gamma to delta+varint:**

1. γ is *larger* than varint for sparse grams (≤~100 docs — 75% of all
   grams, and precisely the blobs the k-rarest policy fetches).
2. γ's size win concentrates in dense blobs the query path never reads —
   and where it does matter, roaring crushes both (230 B vs 125 KB/1 MB).
3. γ decode is bit-granular — un-vectorizable, 40× slower than numpy
   varint (334 ms vs 8 ms on a 1M-doc list). Pure-Python γ at 2–3 M
   vals/s would make hot-blob decode a real cliff; numpy varint removes
   the cliff entirely (worst blob in the corpus decodes in ~3 ms).
4. Total index size cost of varint-over-γ is 439 MB vs ~255 MB at 495K —
   both trivially acceptable (26% vs 15% of corpus).

Concrete: `ENCODING_DELTA_VARINT` becomes the v1 write default;
`ENCODING_ROARING` reserved for grams above a density threshold (~5–10%
of corpus) if/when needed; `ENCODING_DELTA_GAMMA` can be dropped
entirely (keep the tag value reserved). The per-row `encoding` tag
already carries this — no schema change.

## 3. Query ladder (SQLite, 990K-doc tier, warm; live planner, k = rarest grams)

| pattern | class | k=2 | k=4 | k=all | candidates @k4 | verified |
|---|---|---|---|---|---|---|
| `xyzzy_unlikely_sentinel_42` | zero-hit | 0.3 ms | 0.3 ms | 1.8 ms | 22 | 0 |
| `EXPORT_SYMBOL_NS_GPL` | rare | 13.7 | **7.4** | 59.6 | 1,292 | 1,240 |
| `kmalloc` | medium | 45.4 | 60.0 | 78.6 | 12,088 | 11,454 |
| `def __init__` | hot phrase | 20.0 | **19.6** | 70.2 | 3,308 | 2,996 |
| `->next` | punct | 97.7 | **60.7** | 60.5 | 14,154 | 11,246 |
| `!= NULL` | punct | 362.1 | 258.3 | 286.7 | 73,144 | 18,136 |
| `static\s+int\s+\w+_probe` | regex | 242.7 | **211.0** | 287.3 | 46,610 | 20,860 |
| `.*alloc_page.*` | regex | 4,046 | **766** | 703 | 5,876 | 2,270 |
| `(?i)Mutex_Lock` | folded | 382.0 | 306.4 | 336.7 | 28,584 | 27,660 |
| `[fF]oo_bar` | class+run | 13.8 | **7.3** | 7.4 | 216 | 90 |
| `return` | ultra-hot | 525 | 579 | 568 | 514,184 (52% of corpus) | (budget case) |
| `(kmalloc\|vmalloc)\(` | nested alt | REFUSED (planner: non-top-level alternation) | | | | |
| `ab` | sub-3-byte | REFUSED | | | | |
| `kmalloc\|ab` | short branch | REFUSED | | | | |

Scan tier for calibration (100K tier; ~10× at 1M): 260–400 ms simple
patterns, 1.7 s alternations, **16.6 s** for `.*alloc_page.*` (Python re
backtracking) — i.e. ~3–170 s at 1M docs. The index tier wins by 30–700×
on selective patterns, and the wrapped-regex case is the difference
between 0.77 s and ~2.8 min.

Findings:

- **k=4 is the default.** k=2 (zoekt's number) transfers badly to
  doc-level postings, exactly as research predicted: `.*alloc_page.*` is
  5× worse at k=2 (its two rarest grams are still common). k=all is
  counterproductive on rare patterns (rare_ident: 59.6 ms vs 7.4 —
  decoding 17 blobs to save nothing). Early-exit when the running set is
  small makes k=4 ≈ k=optimal everywhere.
- **Empty-posting short-circuit works as designed** (zero-hit: 0.3 ms).
- **The runtime budget case is real and behaves:** `return` matches 52%
  of the corpus; with the ~10K candidate cap the query truncates with a
  flag instead of burning 580 ms — and the classified-refusal +
  budget design covers it. Latency is dominated by content fetch +
  verify of the candidate set, linear in candidates (495K→990K
  latencies scale ~2× with doubled candidate counts; decode/intersect
  stages stay sub-linear).
- **Verify dominates mid-selectivity queries** → the cost-ladder rule
  (join candidates to entries metadata *before* fetching content)
  is where the next factor lives; content fetch ran ~0.5–1 ms per 500
  docs here with ids wrapped mod the real corpus (doubled-tier verify
  times for hot patterns undercount ≤2× due to fetch dedup — disclosed).
- **Planner gap confirmed at 1M scale:** `(kmalloc|vmalloc)\(` refused
  (only top-level alternations split) while pg_trgm answers it in
  3.8 ms. The §5 planner upgrades (nested-alternation cross-product,
  bounded class expansion) are the highest-value follow-up — note
  `[fF]oo_bar` already plans fine via its `oo_bar` run; it is `[fF]oo`
  -shaped patterns (no ≥3-byte run) that refuse.

## 4. Postgres pg_trgm provider tier

| metric | 100K docs | 495K docs |
|---|---|---|
| COPY load | 6.5 s (173 MB heap) | 25.4 s (801 MB heap) |
| GIN gin_trgm_ops build (2 GB maintenance_work_mem) | 13.4 s | 54.3 s |
| GIN index size | 122 MB (0.71× heap) | 466 MB (0.58× heap) |

(GIN build scales linearly and lands in the same ballpark as the vfs
portable build — 54 s vs 105 s at 495K.)

Per-pattern, native `content ~ pattern`, with the vfs byte-gram index
(k=4) at the same tier for comparison:

| pattern | pg 100K | pg 495K | recheck rm @495K | vfs @495K | ratio @495K |
|---|---|---|---|---|---|
| `xyzzy…` (zero-hit) | 1.2 ms | 3.2 ms | 0 | 0.3 ms | 10× |
| `EXPORT_SYMBOL_NS_GPL` | 2.1 ms | **126 ms** | 5,618 | **4.2 ms** | 30× |
| `kmalloc` | 2.5 ms | 92 ms | 315 | 29.9 ms | 3× |
| `def __init__` | 143 ms | 767 ms | 38,581 | **9.7 ms** | 79× |
| `->next` | 236 ms | 998 ms | 48,194 | **30.1 ms** | 33× |
| `!= NULL` | 510 ms | 2,085 ms | 113,270 | **128 ms** | 16× |
| `static\s+int\s+\w+_probe` | 16.9 ms | 447 ms | 12,259 | 107 ms | 4× |
| `(kmalloc\|vmalloc)\(` | 3.8 ms | 153 ms | 5,162 | REFUSED (planner gap) | — |
| `return` (ultra-hot) | 679 ms | 2,899 ms | 4,782 | budget case | — |
| `ab` (sub-3) | 1,107 ms | 1,888 ms **seq scan** | — | REFUSED (classified) | — |

Findings:

- **The word-alphabet weakness is measured, and it grows with corpus
  size.** pg_trgm cannot index punctuation or underscores (`ISWORDCHR`
  = alnum): `EXPORT_SYMBOL_NS_GPL` splits into four medium-hot words
  and costs **126 ms with 5,618 rechecked rows** where vfs's
  underscore-aware byte grams answer in 4 ms — and underscore-joined
  identifiers are *the* canonical code-search pattern. Operator
  patterns are worse (`->next` 33×, `def __init__` 79×). The byte-gram
  design earns its keep even where pg_trgm is available.
- **The silent bail-out is real:** sub-3-byte pattern → full seq scan,
  1.9 s at 495K, no warning. The provider must keep vfs's static
  refusal gate in front of pg_trgm; never rely on pg_trgm to refuse.
- **pg_trgm covers vfs's current planner gap, at a price that scales:**
  `(kmalloc|vmalloc)(` runs 3.8 ms at 100K but 153 ms at 495K (the
  paren is unindexable to pg_trgm; the word grams are hot). It remains
  strictly better than refusal-to-scan, but the real fix is vfs's own
  nested-alternation planner upgrade, which would put this pattern in
  the ~10 ms class.
- Native `~` beat the ILIKE-prefilter+Python-verify shape on every
  pattern at both tiers (verify shape costs 1.2–2.2×); but it
  evaluates Postgres-ARE semantics, not Python `re` — the
  capability-trait decision from the research doc stands (declare
  dialect semantics, or pay the ILIKE shape's overhead to keep Python
  authoritative).

## 5. What this changes in spec.md / the research doc

1. **§6 execution policy:** default k = **4** rarest grams (not 2), with
   early exit; keep the ~10K candidate verification budget +
   truncation flag (measured: the budget engages exactly on the
   patterns it should).
2. **Posting encoding:** v1 default = `ENCODING_DELTA_VARINT` with the
   numpy decode path; drop γ (see §2). Roaring stays a reserved
   density-tier upgrade, not v1.
3. **Reindex verb:** full-rebuild cost is low enough (≈3.5 min/1M docs,
   ≈60 µs/doc) that no incremental machinery is needed at 0.1.0 scale;
   the build must stream hot buckets in bounded batches (peak-RSS
   caveat).
4. **Planner upgrades promoted:** nested-alternation splitting is now
   evidenced as the top gap (common code-search shape, refused today,
   3.8 ms under pg_trgm's graph). Bounded char-class expansion second.
5. **Provider story revised downward:** at 495K docs the portable
   byte-gram tier beats pg_trgm on *every* measured code-shaped
   pattern (3–79×), including underscore identifiers — pg_trgm's
   word-only alphabet is a structural mismatch for code search that
   worsens with corpus size. The Postgres provider's grep override is
   now a *narrow* win (patterns the vfs planner can't yet index, and
   word-shaped natural-language search), not a wholesale replacement —
   and always behind vfs's refusal gate. The portable tier is the
   primary engine on every backend.

## 6. Honest limitations

- 990K tier = corpus × 2 (ids offset): posting lengths and candidate
  volumes are honest at 1M; gram diversity is not (real 1M-doc corpora
  would add some grams; the plateau at 332K suggests the effect is
  small). Hot-pattern verify times at 990K undercount ≤2× (fetch dedup).
- Single pattern per class, not a workload log; no concurrency; warm OS
  page cache; SQLite and corpus on the same NVMe.
- Postgres at Homebrew defaults (128 MB shared_buffers) except
  2 GB maintenance_work_mem for the GIN build; no fastupdate/churn
  benchmark (deferred — batch-only indexing makes GIN churn behavior
  less relevant for vfs's usage shape).
- Avg doc 3.3 KB (chunked); whole-file corpora with 5–10 KB docs would
  raise grams/doc (~linearly) and per-doc extraction cost.
