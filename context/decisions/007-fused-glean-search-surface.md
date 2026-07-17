# 007. Ranked Search Is One Fused `glean` Verb — the Caller Never Picks a Strategy

- **Status:** accepted
- **Date:** 2026-07-16 (decided 2026-07-03 with story 036, commit
  185f73b; this record promotes it out of the archived story)
- **Deciders:** Clay Gendron
- **Decided by:** human

## Context

Story 036 built the full sixteen-verb router surface, and had to settle
what the ranked-search verbs look like. The old surface exposed four:
`semantic_search`, `vector_search`, `lexical_search`, and BM25 — each a
retrieval strategy the caller had to choose. The primary caller is an
LLM agent over MCP: every strategy it can pick is a decision it can get
wrong, and the strategies are not distinct *questions* — they are
interchangeable means to the same question ("what's relevant to this
text?").

The obvious prior art cut the other way. LightRAG's single query
surface, `aquery(query, param)`, exposes `param.mode ∈ {naive, local,
global, hybrid, mix}` — the caller selects the retrieval strategy per
call — and the 2026-04-20 research memo
(`context/research/2026-04-20-graphify-and-lightrag.md` §"Explicit
Namespaced Verbs + `mode` Only on Retrieval Verbs") initially
recommended borrowing exactly that `QueryParam`-with-`mode` pattern for
VFS's search verbs.

## Options considered

- **Per-strategy verbs** (status quo) — four verbs, four capabilities,
  four things an agent must understand; cross-mount fan-out multiplies
  the confusion (which mounts support which strategy?).
- **One search verb with a `mode` selector** (the LightRAG template,
  recommended by the memo, rejected) — collapses the verb count but
  keeps the strategy decision on the caller; every mode has a distinct
  cost/recall profile the caller must learn, and LightRAG's own
  `aquery_llm` mode dispatcher is the memo's Anti-Pattern §2 (an
  if/elif chain that grows per mode).
- **One fused verb, no selector** (chosen) — Google-style search: text
  in, one fused ranked list out. Strategy choice and fusion live behind
  the backend seam.

## Decision

The ranked-search surface is a single verb: **`glean(query, *,
limit=10, ...)`** — live at `src/vfs/base.py:1067`. The caller never
selects a retrieval strategy. Backends index by whatever signals they
have (vector, lexical, graph) and fuse the rankings however they see
fit — reciprocal rank fusion in the reference design — all backend-
tunable and invisible in the public signature; the router passes
`query` and `limit` through opaquely. Results report
`function="glean"`: fusion means there is no single producing method to
name, and the sub-signal mix is deliberately opaque.

Two boundary pins complete the shape:

- **The asymmetry with `graph` is deliberate.** `graph(method, ...)`
  (`src/vfs/base.py:1103`) *does* expose a selector, validated against
  `GRAPH_METHODS` (`src/vfs/ops.py:82` — predecessors, successors,
  ancestors, descendants, neighborhood, meeting_subgraph,
  min_meeting_subgraph) before any dispatch. Traversal methods are
  semantically distinct questions — "ancestors of X" and "neighborhood
  of X" are different asks, not interchangeable strategies for one ask
  — so the selector carries caller intent rather than implementation
  choice. That is the rule: a parameter may select *what to answer*,
  never *how to answer it*.
- **Centrality was dropped entirely.** No centrality methods in
  `GRAPH_METHODS`, no ranked-search or centrality vocabulary in the
  projection layer; analytics are index-time data feeding glean's
  graph signal, not queries (`base.py:1118`).

`glean` is its own capability family — `SupportsGlean`
(`src/vfs/storage/protocol.py:182`), split from `SupportsPatternSearch`
because ranked search rides on retrieval indexes a backend may lack
even when it can glob/grep — so partial backends stay honest under the
derived-capabilities rule of ADR 001.

## Consequences

- **Easier:** an agent learns one search verb with two obvious
  parameters; cross-mount fan-out merges one fused list per capable
  terminal and skips incapable ones silently; backends can change,
  weight, or add ranking signals without any public-surface change;
  capability discovery is one bit (`glean` or not).
- **Harder:** power users cannot force a strategy (a lexical-only
  intent must go through `grep`, which remains the exact-match verb);
  cross-mount scores are only loosely comparable — each backend ranks
  by its own scorer, and re-fusing at the router is a recorded
  road-not-taken (`limit` trims the merge by score with that caveat,
  `base.py:1082-1085`); ranking quality debugging moves behind the
  backend seam where the caller cannot see the signal mix.
- **Committed to:** the surface is pinned ahead of its first
  implementation — no live backend implements `SupportsGlean` yet
  (neither `memory.py` nor the database backend); when one lands, it
  must fuse internally rather than grow a mode parameter, and any
  future "give me just vector results" need is a new capability
  discussion, not a `glean` flag.

Decided and executed in story 036
(`context/specs/archive/036-router-verb-surface/spec.md`, "Decided
semantics" §2–3). Rejected alternative documented in
`context/research/2026-04-20-graphify-and-lightrag.md`.
