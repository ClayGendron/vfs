# turbopuffer — what (not) to borrow for VFS

> Date: 2026-06-03
> Scope: VFS storage/index/retrieval design — the trigram posting-list index
> (`src/vfs/postings.py`, `src/vfs/code_grams.py`), the staging→compile pipeline
> (`src/vfs/backends/database.py`), and the vector/lexical/hybrid search surface
> (`src/vfs/vector.py`, `src/vfs/embedding.py`, `src/vfs/bm25.py`,
> `src/vfs/query/`). VFS targets enterprises and single devs running search over
> a repo/database on one machine (SQLite/Postgres/MSSQL), not a distributed
> billion-vector cluster.
> Trigger: "research turbopuffer and its applicability to VFS — are there
> concepts we could bring over?" Companion to
> [`2026-04-20-pgvectorscale.md`](./2026-04-20-pgvectorscale.md) (the binary-quantization
> story shows up there too) and [`2026-04-20-postgres-native-bm25.md`](./2026-04-20-postgres-native-bm25.md).

## If only one sentence survives

turbopuffer's headline architecture (object storage as source of truth, stateless
compute, S3-as-consensus) **does not apply** to a single-machine SQL-backed system
that already has transactions — but VFS has *independently converged* on
turbopuffer's two best ideas (a WAL-style delta log + async LSM compaction), so
turbopuffer is best read as **validation of the current design plus a short list of
refinements**, of which exactly three are worth lifting: **binary-quantized
embeddings, an IVF/centroid vector index built on the existing posting-list codec,
and Reciprocal Rank Fusion for hybrid search.**

## Why we're here

VFS is a database-backed agentic search platform: mount heterogeneous sources behind
one Unix-style namespace and let an agent `search` / `grep` / `glob` / traverse across
them. The retrieval stack is hybrid — semantic (embeddings), lexical (BM25), and
pattern (trigram-gated grep) — over a single kinded `VFSEntry` table per mount.
turbopuffer is the current darling of object-storage-first vector search, so the
question is whether its architecture or its data structures buy VFS anything.

Short answer: the *architecture* solves a problem VFS deliberately doesn't have; a
few of the *data-structure choices* are directly portable. The rest of this memo
separates those two cleanly so we don't cargo-cult the parts that only make sense at
S3 scale.

## How turbopuffer actually works

Sourced predominantly from turbopuffer's own docs/blog (architecture, concepts,
guarantees, write, fts, hybrid, blog/turbopuffer, blog/ann-v3), claim-level
adversarially verified. Vendor-self-reported, so treat perf numbers as best-case.

- **Object storage is the single durable source of truth.** All durable state lives
  in S3/GCS via an LSM-tree engine. Compute nodes are **stateless** — any node can
  serve any namespace. There is **no separate consensus plane** (Raft/Paxos);
  ordering/consensus is offloaded to object-store atomicity (S3 compare-and-swap).
- **A namespace is "just a prefix"** on object storage, implicitly created on first
  insert. This is what makes per-tenant isolation cheap.
- **Three-tier cache hierarchy:** object storage → NVMe SSD (recently queried
  namespaces) → DRAM/CPU cache (frequently accessed). This is the whole performance
  story: cold p50 ≈ **874ms** vs warm p50 ≈ **14ms** for 1M docs, because each
  object-storage roundtrip is ~100ms and a cold query needs 3–4 of them. Caches are
  derived/non-durable, so they don't violate the stateless-node guarantee; routing
  uses *soft* (sticky-but-not-required) affinity.
- **Vector index = SPFresh**, a centroid/IVF-style ANN with incremental updates,
  chosen over graph indexes (HNSW/DiskANN) **specifically because clustering
  minimizes roundtrips and write-amplification against high-latency object storage**
  (centroid nav ≈ 2–4 roundtrips vs graph traversal ≈ 10–20). Targets >90–95%
  recall@10 including filtered queries. The portable maxim: *pick the index for your
  storage medium's access cost, not just in-memory recall.*
- **ANN v3 reframes vector search as bandwidth-bound, not compute-bound.** RaBitQ
  **binary quantization** gives 16–32× compression so that **<1%** of candidates
  need full-precision reranking — letting quantized index levels sit in DRAM/L3 while
  full-precision vectors stay on SSD.
- **Write path = per-namespace WAL inside the namespace's object-storage prefix.**
  1 WAL entry/sec; concurrent writes batched into the same entry; indexing is an
  **asynchronous LSM build off the write path**; **HTTP 429 backpressure** once
  unindexed data exceeds 2 GiB.
- **Full-text = BM25** with `k1` (1.2), `b` (0.75), and `k3` (8.0, query-term-freq
  saturation — rarely exposed elsewhere).
- **Hybrid search runs ANN and BM25 in parallel** (a `multi_query` endpoint, up to 16
  subqueries on one consistent snapshot) and **fuses client-side with Reciprocal Rank
  Fusion (RRF, k=60: `score += 1/(k+rank)`)** — not a unified server-side score. The
  server stays two independent rankers.
- **Consistency is strong-by-default (CP):** queries return latest data; >99.8%
  consistent; ~100ms staleness only during rare scaling/failover. Eventual mode is an
  opt-in that searches only the first ~128 MiB of unindexed data.
- *(Refuted during research:* the claim that writes go invisible past 128 MiB until
  reindexed — 1-2 vote, excluded.)*

## What does NOT transfer (and why)

| turbopuffer pillar | Why it's a non-fit for VFS |
| --- | --- |
| Object storage as source of truth | VFS's source of truth is a SQL DB. The whole bet exists to give S3 the durability+consistency a transactional DB already has. |
| Stateless compute, any-node-any-namespace | VFS is single-process / embedded (SQLite) or a DB connection (PG/MSSQL). No fleet to make stateless. |
| S3 compare-and-swap as consensus | A **SQL transaction** is VFS's consistency primitive. The write pipeline (`database.py`, phases 1–7) already runs index-before-persist in one txn. turbopuffer reinvents this on S3; VFS gets it for free. |
| Three-tier object→SSD→RAM cache; cold-start penalty | Local DB pages are already ~sub-ms. The 874ms→14ms problem is created by object storage; VFS never pays the 100ms roundtrip. |
| Namespace = object-storage prefix | VFS's mount + longest-prefix composition (and the `/.vfs/__meta__` namespace) is **richer** than a flat prefix. Nothing to gain. |

Do not chase object-storage-first, stateless compute, or S3-consensus. They answer
questions VFS has deliberately not asked.

## The convergence (turbopuffer validates the current design)

turbopuffer's write path — **WAL → async LSM indexing → backpressure** — is the same
shape VFS already implements, independently:

| turbopuffer | VFS equivalent |
| --- | --- |
| WAL (append-only, ordered) | `vfs_entries_grams_staging` — append-only delta log, monotonic `seq`, `action` ∈ {add,delete} (`models.py`) |
| Async LSM indexing off write path | The **compile phase** — latest-action-wins fold via `ROW_NUMBER() … ORDER BY seq DESC`, then `_fold_postings` (`database.py`) |
| 429 backpressure at 2 GiB unindexed | Compile triggered when staging exceeds **5M rows** |
| LSM sorted runs / posting compaction | delta+gamma posting lists + two-pointer `merge_postings()` (`postings.py`) |

The patterns turbopuffer markets as innovation are already in the tree. That's the
most reassuring outcome of this research, and it's why the refinements below land on
substrate we already have. See [`2026-05-26-bulk-insert-vs-orm-per-row.md`](./2026-05-26-bulk-insert-vs-orm-per-row.md)
and [`2026-06-02-reading-orm-rows-without-dirty-state.md`](./2026-06-02-reading-orm-rows-without-dirty-state.md)
for the bulk-DML/snapshot machinery the compile phase rides on.

## What to borrow — ranked by value

### 1. Binary-quantized embeddings (highest value, most portable)
turbopuffer treats vector search as **bandwidth-bound** and uses RaBitQ for 16–32×
compression with <1% full-precision reranking. VFS today stores embeddings as **JSON**
by default (`vector.py`, `models.py`); pgvector exists only on the Postgres backend.
JSON floats are the worst case for both storage and scan bandwidth.

A binary-quantized representation (1 bit/dim packed into a blob) + a small
full-precision rerank pass would:
- make semantic search **actually viable on the SQLite/embedded path**, where there
  is no ANN index and search is brute-force today;
- shrink the embedding column ~32×;
- slot in behind the existing `EmbeddingProvider` / `semantic_search` interface with
  no API change.

This overlaps the StatisticalBinaryQuantization note in
[`2026-04-20-pgvectorscale.md`](./2026-04-20-pgvectorscale.md) — but the SQLite win is
the part pgvectorscale can't give us, since pgvectorscale is Postgres-only.

### 2. An IVF/centroid vector index built on the existing posting-list codec
turbopuffer chose a centroid/IVF index over HNSW because it suits an LSM/posting-list
world. VFS already *has* that world: a compressed `gram_key → posting_list` inverted
index. An IVF index is structurally identical — `centroid_id → posting list of doc_ids
in that cluster`. We could:
- store centroids as entries,
- **reuse `encode_postings`/`decode_postings`/`merge_postings` verbatim** for cluster
  membership,
- reuse the staging→compile fold for incremental vector updates.

This gives approximate vector search on SQLite with near-zero new storage code, and it
composes with #1 for the rerank step. It's the most *elegant* fit: turbopuffer's
"index for your storage medium" reasoning points straight at infrastructure VFS
already shipped for grep. Relates to story 003 (Postgres native vector search) and
story 013 (database-agnostic trigram index).

### 3. Reciprocal Rank Fusion for hybrid search
turbopuffer fuses ANN + BM25 with client-side **RRF (k=60)** rather than a unified
server-side score, keeping the rankers independent. VFS has three independent rankers
(`semantic_search`, `lexical_search`/BM25, grep) and currently combines via **set
algebra + pagerank** on `VFSResult`. RRF is a tiny, well-validated addition — an
`rrf`/`fuse` operator in the query engine (`query/executor.py`, `query/parser.py`)
that merges ranked `VFSResult` lists by reciprocal rank. It's strictly more expressive
than set intersection for "best of semantic AND lexical," and it fits the pipeline
model: `search "x" | lexical "y" | rrf | top 15`. Directly relevant to story 022
(hybrid search across mounts).

### 4. A formal consistency knob (eventual vs strong reads) — medium
turbopuffer lets queries opt into eventual consistency (skip scanning unindexed data).
VFS grep already does the *strong* thing — it merges unflushed staging adds/deletes
into posting-list results so search is correct before compile. That's a real cost when
staging is large. An explicit `consistency="eventual"` fast path that **skips the
staging scan** under bounded staleness would mirror turbopuffer's knob. The strong
side is built; the eventual side is a documented opt-out, not new machinery. Ties into
story 030 (incremental chunk indexing) and story 031 (unified entry-creation
chokepoint).

### 5. Explicit, observable backpressure + tiered compaction — smaller
- Compile currently does a **full decode→merge→re-encode per touched gram**. At scale
  that's write-amplification-heavy; turbopuffer's LSM leveling/tiering is the textbook
  fix when posting recompaction becomes a bottleneck. Not urgent — keep in pocket.
- The 5M-row staging trigger is backpressure-by-compaction. turbopuffer makes
  backpressure **explicit and observable** (HTTP 429). For an agent-facing system,
  surfacing "index is N% behind" beats silently folding. Natural home: story 031.

### 6. BM25 `k3` — marginal
`bm25.py` has `k1=1.5`, `b=0.75`, `epsilon` but no `k3` (query-term-freq saturation).
Only matters for repeated terms in long queries. Low priority. See
[`2026-04-20-postgres-native-bm25.md`](./2026-04-20-postgres-native-bm25.md).

## Recommendation

Treat turbopuffer as a confirmation, not a redesign. The two best effort/payoff bets
are **#1 (binary-quantized embeddings on the SQLite path)** and **#3 (an RRF fusion
operator)** — both fit existing interfaces with no schema upheaval. **#2 (IVF on the
posting-list codec)** is the higher-ceiling, higher-effort play and the most
architecturally satisfying because it reuses what grep already built. Everything under
"what does not transfer" should stay un-borrowed: VFS's transactional, single-machine,
mount-composed model is a different and deliberate design point.

## Confidence / caveats

turbopuffer findings are ~80% vendor docs/blog (self-reported; perf numbers are
vendor-published), adversarially verified at the claim level (24/25 confirmed, 1
refuted). The headline scale numbers (100B vectors, 200ms p99) are at 92% recall,
unfiltered, ANN v3 opt-in beta — irrelevant to VFS's single-machine target and not
cited in any recommendation. Cross-vendor comparisons vs Pinecone/pgvector came from
non-neutral secondary sources and are excluded. The durable architectural contrast
(stateless compute + object-storage-as-truth + no consensus plane) is well
substantiated; the relative cost/QPS claims are not.

## Primary sources

- turbopuffer.com/docs/architecture, /docs/concepts, /docs/guarantees, /docs/write,
  /docs/fts, /docs/hybrid, /docs/query
- turbopuffer.com/blog/turbopuffer, /blog/ann-v3
- Founder interview: latent.space/p/turbopuffer
