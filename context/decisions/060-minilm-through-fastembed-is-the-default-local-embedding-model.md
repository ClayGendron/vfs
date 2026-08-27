# 060. all-MiniLM-L6-v2 Through fastembed Is the Default Local Embedding Model

- **Status:** accepted 2026-08-27 — decided by Clay in session after
  the fastembed model benchmark: "okay minilm is my default model
  choice through fastembed."
- **Date:** 2026-08-27
- **Deciders:** Clay Gendron
- **Decided by:** human
- **Context source:**
  `context/research/studies/2026-08-27-fastembed-models/` (the survey,
  the dependency audit, and the benchmark on the vfs_native and scifact
  corpora; full numbers in its `results.json`).

## Context

vfs's embedding seam (specs 134/135) shipped with a ladder of local
providers: the hash floor (zero dependencies, no semantics), model2vec
potion (static semantics, `embed-local` extra), and adapters for hosted
APIs. The question was which *real* model vfs should name as its
default recommendation, and through which runtime.

The candidates were `sentence-transformers/all-MiniLM-L6-v2` through
sentence-transformers (torch, hundreds of MB to GBs), the same model
through fastembed (ONNX Runtime, ~100 MB, no torch, no transformers),
and the newer small models fastembed serves that beat MiniLM on MTEB
Retrieval by ~10 points (bge-small-en-v1.5, snowflake-arctic-embed-xs/s),
plus a hosted flagship (OpenAI text-embedding-3-large at 1024
dimensions) as the ceiling reference.

The benchmark reused the ranking harness — glean through the verb,
Convex 50/50 fusion with the BM25 lexical leg, nDCG@10 via ranx — and
found:

- **MiniLM posted the best fused quality on both corpora** (0.7998 on
  vfs_native vs the 0.7589 BM25 baseline; 0.6903 on scifact vs 0.6580)
  *and* was the fastest real transformer (~120 chunks/s on one CPU).
- **The MTEB lead of the newer small models did not survive.**
  fastembed serves bge only int8-quantized, which runs 27x slower than
  fp32 on Apple Silicon — unusable. The arctic models process
  512-token windows in fp32, embed 5–10x slower than MiniLM, and
  arctic-xs fused *below* MiniLM despite a stronger vector-only arm.
- **The hosted ceiling is close, not decisive, for the default's
  job**: OpenAI 3-large @1024 fused 0.7959/0.6934 at ~330 ms per query
  (API round trip) against MiniLM's ~40 ms local — though its scifact
  vector-only arm (0.7659) exposed that fixed 50/50 fusion weights can
  hurt a strong leg (spec 136's territory).

## Decision

1. **The default local embedding model is
   `sentence-transformers/all-MiniLM-L6-v2`, served through fastembed**
   (ONNX Runtime). A `FastEmbedEmbeddingProvider` joins
   `vfs.embedding` with MiniLM as its default model;
   `fastembed` joins the `embed-local` extra beside `model2vec`.
   sentence-transformers (torch) does not become a dependency at any
   tier — users who want it reach it through the LangChain adapter or
   the protocol.
2. **The zero-install defaults do not change.** `InMemoryStorage`
   keeps the hash provider; `DatabaseStorage` keeps no embedder.
   MiniLM is the documented one-line opt-in, never a silent swap: the
   embedding identity is stamped on the space, and a default that
   changed with the installed extras would re-identify existing spaces
   and force re-embeds.
3. **bge models are not offered through the provider** while fastembed
   serves them only int8-quantized (`qdrant/*-onnx-q`).

## Consequences

- **Easier:** one documented answer to "which model?" — the best
  measured fused quality vfs has, offline after one ~90 MB download,
  no torch, no API key; the provider owns the (empty) query prefix so
  prefix-sensitive models can join later without caller changes.
- **Harder:** fastembed brings numpy into the `embed-local` extra's
  environment (never into core imports — the provider loads it
  lazily, and the no-numpy import pin still holds); MiniLM truncates
  inputs at 256 tokens, so long chunks are represented by their heads.
- **Committed to:** the embed step must stay correct for providers far
  slower than MiniLM — the benchmark exposed that the 120 s per-call
  timeout over 2,048-input batches silently drops vectors for any
  embedder under ~17 chunks/s (study finding 3); the fix is owed
  before the provider lands.
