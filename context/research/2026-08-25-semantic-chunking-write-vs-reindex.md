# Semantic chunking — write-time or reindex-time?

- **Date:** 2026-08-25
- **Provenance:** commissioned by Clay to ready the chunking fork
  spec 103 left open (recorded in `../open-questions.md`, "Semantic
  chunking is 84% of the reindex wall"). The question as posed: should
  `Chunk.split` run on the write path or stay on the reindex path?
  Clay's prior: reindex — repeated edits to one file should not pay
  the chunk tax per edit, and write-path time is felt by the user
  while reindex time is not — unless measurement showed the write-path
  tax to be trivial. Two investigations, run 2026-08-25: executed
  benchmarks on the installed tree (Apple Silicon laptop, Python
  3.13, in-memory backend = `DatabaseStorage` on sqlite; scripts
  lived in the session scratchpad, ephemeral; this memo carries the
  operative numbers), and a prior-art study of nine systems in the
  reference checkouts (jackrabbit-oak, zoekt, codesearch, graphrag,
  LightRAG, cognee, letta, mem0, sqlite FTS5, plus postgres GIN).
- **Headline:** the measurements close the fork in the direction of
  Clay's prior, decisively. Inline chunking would be an ~8 % tax on a
  small single-file agent write — but it **doubles** edit latency on a
  mid-size file (+106 %), and on the ETL contract it is **10–12× the
  entire write pipeline** (a 10,000-file batch: 1.9 s to write,
  22.8 s to chunk). The work also cannot be shed to a thread: the
  language pack's `Parser` is a thread-pinned pyo3 class, and calling
  the cached parser from another thread **panics** — a
  `PanicException` (a `BaseException`) that escapes `split_code`'s
  `except Exception` fallback. Prior art is near-unanimous: expensive
  derived-data construction stays off the durable write path unless
  commit-time semantics demand it, and the one system that shipped a
  fully-synchronous mode (Oak's NRT `sync`) documents that you should
  not use it. Chunking stays on the reindex side; the patterns worth
  adopting there are budgeted work, skip-if-unchanged, and an
  observable staleness window.

## 1. The current shape (verified in the tree)

Writes stamp `chunked: False` on the touched entry
(`storage/backends/database/writes.py`); `reindex()` — an explicitly
invoked verb under a single-runner heartbeat lease — runs
`chunk_dirty` as its Phase A (`storage/backends/database/indexing.py`),
which re-splits every dirty live content entry via `Chunk.split` and
flips `chunked`/`indexable` guarded on the version the content was
read at. So chunking is already reindex-time; the fork is whether to
*move* it to the write path, not whether to keep it there.

## 2. Per-file cost distribution (executed)

`Chunk.split` timed per file — the exact call `chunk_dirty` makes —
over a seeded 4,000-file sample of the linux checkout (the spec 103
corpus) and the whole vfs `src/` tree. Parsers warm.

| corpus | n | mean | median | p90 | p99 | max |
|---|---|---|---|---|---|---|
| linux sample | 4,000 | 2.13 ms | 0.61 ms | 4.62 ms | 21.2 ms | 403.9 ms |
| vfs `src/` | 49 | 2.04 ms | 1.20 ms | 3.90 ms | 21.2 ms | 21.2 ms |

By size bucket (linux): `<4KB` mean 0.21 ms; `4–32KB` 1.73 ms;
`32–128KB` 7.81 ms; `≥128KB` mean **46.4 ms**, max 403.9 ms.
Throughput is flat at ~8 MB/s regardless of grammar mix.

Scaled to the full corpus: 76,032 eligible files × 2.13 ms = **162 s**,
which reproduces spec 103's measured 161 s within 1 % — the sample is
representative and the wall is fully explained by per-file cost, not
by any batch effect.

Parser first-touch is a non-factor: importing
`tree_sitter_language_pack` costs 28 ms once per process; per grammar,
load ≤ 66 ms (go; most < 1 ms) and first parse ≤ 29 ms.

## 3. What inline chunking would cost each audience (executed)

Measured through the public API (`VirtualFileSystem` on the in-memory
backend), with the chunk cost of the identical content measured
beside it:

- **Agent single-file writes** (200 files < 8 KB): write mean
  4.2 ms; chunking those files costs 0.33 ms/file — an **~8 % tax**.
  Trivial in the common case, but the tail is not: one ≥128 KB write
  would hold the event loop 46–404 ms mid-write, unsheddable (see §4).
- **Agent edit churn** (50 sequential edits to a 26 KB `.c` file):
  edit mean 3.20 ms; re-splitting the file costs 3.38 ms — a
  **+106 % tax on every edit**. This is Clay's repeated-tax intuition
  made exact: inline placement doubles edit latency, and N edits
  between reindexes pay N re-splits where the reindex path pays one.
- **ETL batch writes**: 1,000 files (15.9 MB) write in 0.20 s, chunk
  in 2.12 s (**+1,048 %**); 10,000 files (203.5 MB) write in 1.92 s,
  chunk in 22.78 s (**+1,188 %**). Inline chunking would turn the
  supported 10k-batch contract from ~2 s into ~25 s of blocking call
  time — and on real engines the window a write transaction stays
  open matters as much as the elapsed time.

Note the write baseline here is sqlite-in-memory, the fastest engine
vfs will ever sit on; on networked Postgres/MSSQL the *relative* tax
shrinks but the *absolute* chunk cost — and the event-loop occupancy —
is identical.

## 4. The thread door is closed (executed)

Running `Chunk.split` under a `ThreadPoolExecutor` panics:
`_native::Parser is unsendable, but sent to another thread`
(pyo3 assertion). Two facts compound:

- `chunking._PARSERS` is a module-level cache, so a parser created on
  the loop thread is reused from any later caller thread — and the
  pack's `Parser` is a thread-pinned (`unsendable`) pyo3 class.
- The panic surfaces as `pyo3_runtime.PanicException`, which derives
  from `BaseException` — it sails *through* `split_code`'s
  `except Exception` wholesale-fallback and kills the caller.

So inline placement could not even shed its tail to a worker thread —
the 404 ms worst case would sit on the event loop inside a write, for
every concurrent caller to feel. (This also stands as a latent hazard
note independent of the fork: any future code that threads a split —
e.g. an `asyncio.to_thread` convenience — will panic, not degrade.
Per-thread parser construction would avoid the panic but not the GIL:
spec 103's session measured 1.0× scaling on 8 threads. Process pools
remain the only parallelism, a posture question already recorded in
`../open-questions.md`.)

## 5. Prior art: nine systems, one consensus

Full citations gathered in-session from the reference checkouts;
condensed here.

- **jackrabbit-oak** — the closest problem shape, and the sharpest
  answer. Sync-vs-async is a per-index property: cheap property and
  reference indexes update in the commit; *every* fulltext/Lucene
  index (the tokenize-and-analyze family — exactly a tree-sitter
  parse+split) rides a periodic async lane with checkpoint diffs
  (`oak-doc/.../query/indexing.md`). Binary text extraction is pulled
  off the critical path explicitly because it "slows down the
  indexing rate considerably" (`pre-extract-text.md`). Staleness is
  managed, not ignored: observable lag (IndexStats time series), a
  30-minute failing-index timeout, and an NRT mode that keeps a
  small local delta index queries union in. Decisive detail: Oak
  *shipped* a fully-synchronous NRT variant and its own docs steer
  you off it — "the 'nrt' mode performs better, so using that is
  preferable" (`indexing.md`). The inline experiment has been run.
- **zoekt / codesearch** — index construction is offline batch with
  no write-path hook at all; staleness is one poll interval, and
  dirty detection is a fingerprint comparison
  (`zoekt/index/builder.go` `IncrementalSkipIndexing`), not writer
  bookkeeping.
- **graphrag / LightRAG / cognee** — no RAG pipeline chunks or embeds
  inside the durable write. graphrag is a batch CLI with an LLM cache
  for idempotent re-runs; LightRAG's `ainsert` enqueues (status row +
  content-hash dedupe) and returns a `track_id`, with a single drain
  worker and a `request_pending` coalescing bit
  (`lightrag/lightrag.py`); cognee splits the API in two —
  `add()` ingests cheap, `cognify()` is where the user pays.
- **letta / mem0** — letta uploads set
  `processing_status=PARSING` and background the pipeline, run
  chunking via `asyncio.to_thread`, and log any chunking call over
  0.5 s as a slow op (`file_processor.py`). mem0 is the field's one
  true inline system — `Memory.add()` blocks on extraction and
  embedding — and its rationale is the one case where inline is
  forced: an agent memory that isn't searchable on the *next turn* is
  broken. Its own escape hatch (`infer=False`) drops the expensive
  stage rather than deferring it.
- **sqlite FTS5 / postgres GIN fastupdate** — the "amortized inline"
  family: the write does the cheap indispensable part into a buffer
  (FTS5's pending-terms hash, GIN's pending list) that queries
  *union with the main structure*, so results are never stale — and
  only the reorganization (merging) is deferred, budgeted
  (`automerge` pages), resumable, and crisis-bounded
  (`crisismerge=16`). This strategy is strictly better where it
  applies — but it requires a cheap approximation of the derived
  datum that queries can union against, and a semantic chunk has
  none: there is no half-parse.

**Consensus:** expensive derived-data work goes on the write path only
when commit-time semantics demand it (a uniqueness veto, mem0's
next-turn read). Chunk rows gate nothing at commit and serve only the
not-yet-built embedding pipeline; nothing reads them microseconds
after a write. The field's answer for that shape is deferred, with the
window made observable and bounded.

## 6. What this leaves for the decision

The write-vs-reindex fork itself is closed by evidence: **chunking
stays off the write path.** The costs land asymmetrically on exactly
the two audiences the production posture names — doubled edit latency
for agents, a 12× batch penalty for ETL — the tail is unsheddable
in-process, and the field's one same-shape system deprecated its own
inline mode.

What remains is spec 103's *residual* sub-fork — where on the deferred
side the split runs (inside the reindex verb's wall, on its own
schedule, process-pooled, or in Rust) — and prior art marks the
patterns worth weighing when that is decided:

- **Dirty flag + status-query recovery** — already vfs's shape
  (`chunked=False`, re-derived by scan); LightRAG and letta confirm
  it over in-memory queues for crash recovery.
- **Skip-if-unchanged** — `chunk_dirty` re-splits every dirty entry
  even when content is byte-identical (an overwrite with the same
  body, a restore). zoekt/cognee/LightRAG all fingerprint-skip; the
  `content_hash` column is already on the entry and on each chunk row.
- **Budgeted work per tick + a crisis bound** — FTS5's shape, if
  chunking moves to its own cadence: a per-invocation page/file
  budget with a staleness backstop, rather than all-dirty-every-run.
- **Instrument the tail** — letta's >0.5 s slow-chunk warning; the
  46–404 ms ≥128 KB bucket is the population it would surface.
- **Single-worker coalescing** — the reindex lease already provides
  it; keep it wherever the split lands.
