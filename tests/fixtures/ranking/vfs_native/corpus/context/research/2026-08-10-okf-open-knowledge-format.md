# OKF (Open Knowledge Format): the spec, what Google actually shipped, and where it meets vfs

- **Status**: research memo (commits us to nothing; feeds a possible ADR on
  knowledge-bundle ingestion/serving and on frontmatter-as-query-surface)
- **Date**: 2026-08-10
- **Owner**: Clay Gendron
- **Question**: Google Cloud announced the Open Knowledge Format (June
  2026) — a vendor-neutral markdown-plus-frontmatter convention for giving
  AI agents curated organizational knowledge. What is it exactly, what did
  they actually build, and how could the idea integrate with vfs?
- **Evidence gathered**: cloned `GoogleCloudPlatform/knowledge-catalog`
  read-only to `~/Git/Repos/knowledge-catalog` (license checked
  immediately: Apache-2.0). Read `okf/SPEC.md` (v0.2, 1,003 lines) in
  full. Three parallel line-level surveys: the reference implementation
  (`okf/src/reference_agent/`, ~1,450 lines Python + tests), the
  samples/toolbox ecosystem (`samples/`, `toolbox/mdcode`,
  `toolbox/enrichment`, the checked-in bundles), and the vfs live tree
  (`src/vfs/`, `tests/`, standards, ADRs, open questions). Announcement
  blog consulted for positioning. Citations are repo-relative to the
  checkout; vfs code is cited from `src/vfs/`.

---

## 1. The format in one page

An OKF **bundle** is a directory tree of UTF-8 markdown files with YAML
frontmatter — nothing else. No schema registry, no central authority, no
required tooling; distribution is a git repo, a tarball, or a
subdirectory (`okf/SPEC.md` §3). Each non-reserved `.md` file is a
**concept**: one unit of knowledge (a table, an API, a metric, a
playbook). The concept's ID is its bundle-relative path minus `.md`.

Frontmatter has exactly one required key — `type`, a free-form string
(`BigQuery Table`, `Metric`, `Playbook`) with no central registry
(§4.1). Recommended: `title`, `description`, `resource` (canonical URI of
the underlying asset), `tags`. Everything else is passthrough; consumers
MUST NOT reject unknown keys, unknown types, broken links, or missing
optional families (§11 — the conformance posture is aggressively
permissive, tolerant-reader by construction).

On top of that floor, v0.2 adds four optional frontmatter families aimed
at corpora that are *continuously written by agents* (§1):

- **Provenance** (§5.1): `sources` — a list of `{id, resource, title}`
  entries with objective per-source credibility signals (`author`,
  `usage_count`, `last_modified`, framed by a `usage_window`). No stored
  credibility *score* — scores are subjective and go stale; consumers
  infer trust from signals. Per-claim attribution uses markdown footnotes
  whose labels join to `sources[].id` (keyed, not positional, because
  agents reorder lists).
- **Trust** (§5.2–5.3): `generated: {by, at}` (who wrote it) is kept
  distinct from `verified: [{by, at}]` (who confirmed it). Actors follow a
  convention: `<producer>/<version>` for agents, `human:<id>`,
  `process:<id>` (§7). Consumers *derive* a trust tier — unverified /
  machine-confirmed / human-reviewed — from the `human:` prefix; tiers are
  advisory, never access control.
- **Lifecycle** (§5.4–5.5): `status: draft|stable|deprecated` (absent ⇒
  stable) and `stale_after: YYYY-MM-DD` (absolute date, not a TTL, so
  staleness is a plain date comparison).
- **Attested computations** (§10): a concept type carrying a sanctioned
  computation (SQL/dbt/Python) plus `runtime`, typed `parameters`, an
  `executor` (returns a receipt), and an `attester` (deterministic,
  no-LLM code that inspects the receipt and returns a verdict). The agent
  may bind parameter values but never author the computation; attestation
  makes "did the sanctioned thing run" a mechanical comparison. The
  receipt/verdict wire formats and attester ABI are explicitly deferred
  (§12).

Structure beyond frontmatter: **`index.md`** per directory (reserved,
frontmatter-free) lists contents for *progressive disclosure* — see what
exists before opening documents (§8). **`log.md`** (reserved) is a
date-grouped, newest-first change history (§9). **Markdown links between
concepts are the knowledge graph**: untyped directed edges, relationship
kind conveyed by surrounding prose; consumers MUST tolerate dangling
links as "not-yet-written knowledge" (§6.1).

## 2. Positioning

The pitch is **format-not-platform**: the knowledge agents need (schemas,
metric definitions, runbooks, join paths) is scattered across catalogs
with proprietary APIs, wikis, and heads; OKF proposes plain files as the
interchange so any producer (human, agent, catalog exporter) can write it
and any consumer (LLM context loader, search index, graph viewer, static
file server) can read it. Google's Knowledge Catalog (formerly Dataplex)
ingests and serves OKF; the spec itself is published vendor-neutral on
GitHub with contributions invited. It is young (v0.1 → v0.2 within weeks
of announcement), Google-stewarded in practice, and the ecosystem beyond
Google is currently aspirational.

## 3. What Google actually shipped (implementation reality)

The repo's own framing is honest: the *format* is the contribution; the
code is proof-of-concept ends (`okf/README.md`). What exists:

- **A producer**: `reference-agent` (`okf/src/reference_agent/`), a
  Google-ADK LLM pipeline. A `Source` ABC (`sources/base.py`) feeds
  concept refs; the only concrete source is BigQuery
  (`sources/bigquery.py` — notable: date-sharded tables collapse into one
  family concept, 3,000 GA4 shards → one document). For each concept a
  fresh LLM session reads raw metadata via tools and writes one document
  via `write_concept_doc`; a second web-crawl pass augments docs from
  allowed sites; then `index.md` files are regenerated wholesale,
  deepest-first, with LLM-synthesized directory descriptions
  (`bundle/index.py`).
- **A consumer**: a static single-file HTML graph viewer
  (`viewer/generator.py`) — Cytoscape graph of concepts and link edges
  with trust/staleness badges. No backend.
- **A bridge**: `toolbox/mdcode` ("metadata as code", `kcmd`) syncs
  directories bidirectionally with Dataplex; its demo
  (`toolbox/mdcode/demo/okf/`) round-trips an OKF bundle through a custom
  Dataplex aspect type — the only place OKF frontmatter becomes
  *indexable* in a service.
- **The document model is deliberately untyped**:
  `OKFDocument = {frontmatter: dict, body: str}`
  (`bundle/document.py`) — no pydantic schema, `type` is the only
  validated key, unknown keys pass through by construction. The only
  typed accessors are three pure functions implementing the spec's
  derivations: `normalize_verified`, `trust_tier`, `is_stale`.

What does **not** exist anywhere in the repo: a server. No HTTP serving,
no MCP server for bundles, no bundle load/walk/validate library API, no
conformance validator, no `log.md` producer or consumer, no Attested
Computation runtime (one hand-written example attester sits in a bundle,
uninvoked by any code). The two file-KB MCP servers that do exist
(`samples/enrichment/src/tools/fileskb/`, `toolbox/enrichment`'s
`md-fileset`) are generic `list`/`read`/`search` over a directory —
**not OKF-aware**: they parse no frontmatter and understand no index.

## 4. Spec vs practice — the gaps

The delta between the spec's ambitions and the shipped artifacts is
itself a finding, because the gaps mark where a serious implementation
could actually contribute:

| Spec | Practice |
|---|---|
| Trust family: `verified`, trust tiers (§5.2–5.3) | Consumer-side functions exist and are tested; **no producer ever writes `verified`** — all 44 machine-generated concepts across three bundles are tier "unverified" |
| `stale_after`, `status` (§5.4–5.5) | Only in the one hand-authored showcase bundle (`okf/bundles/acme_retail/`) |
| Attested Computations (§10, 78 lines) | Spec-only; runtime, receipts, attester ABI all deferred; no code path touches the fields |
| `log.md` (§9) | Zero producers or consumers; one hand-written instance |
| `okf_version` declaration (§12) | Never written or read |
| Bundle-absolute `/` links *recommended* (§6.1) | Producer prompts **forbid** leading-`/` links (they break GitHub rendering); the viewer's edge extractor skips absolute links while its navigation handles *only* absolute links — the two link forms are in live contradiction |
| `tags` as a YAML list (§4.1) | One bundle emits a bare comma string (YAML scalar), another a real list; nothing normalizes — a real interop bug |
| Conformance (§11: every concept has `type`) | The `samples/enrichment` pipeline emits frontmatter with no `type` at all — Google's own adjacent sample is non-conformant |

Two structural observations follow. First, **producer/consumer
asymmetry**: three production paths, one OKF-aware consumption path (the
static viewer). Second, the format's most differentiated claims (trust,
freshness, attestation) are exactly the parts nothing populates or
enforces yet.

## 5. Transferable engineering patterns (worth borrowing regardless of OKF)

- **The augmentation guard** (`tools/bundle_tools.py:139-183`): during
  the web pass, a write that would *shrink* an existing doc's `# Schema`
  field set or `sources` list is refused with an error naming the missing
  fields and stating exactly which calls to re-issue. The invariant
  "ground truth from structured metadata may be augmented, never replaced
  by scraped prose" is enforced in the tool, not the prompt.
- **Errors as data with embedded remediation**: LLM-facing tools never
  raise; they return `{"error": <how to recover>}` and the prompt adds "a
  rejected write did not happen — fix it and retry." Guard violations
  become self-healing loops. (Rhymes with our envelope's
  classified-error posture; the remediation-text discipline is the part
  worth noting.)
- **Reachability-gated crawling** (`tools/web_tools.py`): a URL is
  fetchable only if a previously fetched page surfaced it (or it is a
  seed). Hallucinated URLs are structurally unfetchable — the crawl graph
  is a capability set. Budgets (page count, depth, hosts, path prefixes)
  are all enforced tool-side; budget is consumed even on failed fetches
  to kill retry loops.
- **Provenance as a tool guarantee**: `generated: {by, at}` is
  auto-stamped by the write tool with the actor convention; the model
  cannot forget or forge it.
- **Prompt-vs-tool enforcement gap as a lesson**: the producer's quality
  bar is ~270 lines of prompt instructions, of which exactly two rules
  are machine-enforced. Everything we choose to guarantee should sit on
  the tool side of that line.

## 6. The ecosystem gap: OKF has no serving story

OKF's own material demonstrates four consumption models — raw files in
git, generic file-KB MCP tools, a static HTML viewer, and push-into-
Dataplex — and not one of them can answer a query the format itself makes
expressible: *"all stable, human-reviewed `Metric` concepts tagged
`finance` that aren't stale."* The frontmatter families are queryable in
principle and unqueried in practice; the link graph is traversable in
principle and only visualized in practice. A consumer wanting any of
this must walk every file. The bridge into Dataplex exists precisely
because the files alone can't serve these questions — and it costs you
the vendor neutrality that was the point.

That missing layer — a queryable, permission-aware, agent-first serving
surface over a directory of knowledge files — is a nearly exact
description of vfs's mission ("the substrate AI agents stand on when
they need to read, write, search, and reason over a real organisation's
knowledge" — `context/standards/mission.md`). OKF supplies a portable
interchange format and a growing corpus shape; vfs supplies everything
OKF lacks: storage, search, graph, permissions, and (planned) the
one-tool MCP surface. The integration question is not "adopt OKF as our
model" but "be the best place an OKF bundle can live."

## 7. Where OKF meets vfs, seam by seam

The vfs survey confirmed the fit is mostly *existing* seams, not new
machinery. In rough order of increasing design work:

### 7.1 A bundle is already a valid vfs write

An OKF bundle is a directory tree of small text files — the native input
shape of the batch write door (`VirtualFileSystem.write(entries=[...])`,
`src/vfs/base.py`; 10,000+-entry batches are the declared contract, and
`parents=True` mints ancestors). Once written, everything already works:
glob/grep over concepts, tree-sitter markdown chunking
(`src/vfs/models/chunking.py` — heading-aware chunks fall out of the
generic walker; the standing precedent from the retired
markdown-chunking spec is *no bespoke markdown pipeline*), versioning,
trash, permissions. `index.md` and `log.md` are ordinary rows needing no
new primitive. Ingesting OKF requires **zero schema change** at this
tier — a `mount`-a-bundle demo is essentially free today.

The existing template for "a validated format value object that renders
frontmatter text and projects to plain `Entry` rows" is
`src/vfs/skills.py` (`Skill.to_entries()` — the only YAML-frontmatter
code in the tree, `pyyaml` already a dependency, angle-bracket injection
guard included). An `okf.py` sibling module — bundle model, conformance
check (§11 is short), `to_entries()` — would follow that precedent
exactly. Note the direction gap: `skills.py` *renders* frontmatter but
nothing in the tree *parses* it; ingestion needs the parse side.

### 7.2 Frontmatter as a query surface — the real design work

The gap §6 identifies is metadata query, and here vfs has a genuine hole
to fill deliberately: `Entry` has no structured-metadata carrier (only
`external_id` and `mime_type`), no tags, no key/value store
(`src/vfs/models/rows.py`). Two chartered routes exist, and the choice
is the heart of a future ADR:

- **Entry-keyed sidecar table** (the ADR 016 shape — the pattern
  `content`/`versions`/`chunks`/`edges` already use, and the shape the
  multimodal open question independently proposes for derived text). A
  `<t>_meta_kv` or typed frontmatter table keyed to `(entry,
  content_hash)`, populated at ingestion, reached through query
  parameters rather than paths.
- **Widening the entries row** with facet columns — precedented by `ext`
  (low-cardinality facet + index, `ix_<t>_ext_kind`), but every column
  moves through the `ENTRY_ROW_ONLY_COLUMNS`/drift-test machinery and
  bumps `SCHEMA_FORMAT_VERSION` (ADR 020).

The query-side precedent is fresh: `glob(kind=...)` (spec 094) shows the
full path a fact filter travels — declared in `params.py`, rendered
inside each SQL OR-arm, and honoring ADR 034's fetch-to-populate law for
chained calls. A `type=` / `tags=` / `status=` filter channel on
glob/grep would follow that identical route, giving exactly the query
OKF cannot serve: `glob("/kb/**", type="Metric", tags=["finance"])`.

Whether frontmatter extraction is OKF-specific or a general "structured
head-matter" facility (YAML frontmatter is also how skills, MDX, Hugo,
Obsidian, and our own memos work) is a genuine fork.
[NEEDS CLARIFICATION: is frontmatter-as-facets a general vfs capability
with OKF as one profile, or an OKF-specific ingestion feature? And which
storage shape — sidecar table vs entry columns?]

### 7.3 Links as edges

OKF's knowledge graph is untyped directed markdown links (§6.1) — a
near-perfect match for the existing `edges` table (`source_id`,
`target_id`, `edge_type`, indexed both directions) and the `Edge` model.
The pieces line up with current doctrine cleanly:

- **`mkedge` is the single unbuilt hinge**: the one classified stub in
  `DatabaseStorage` (`storage/backends/database/backend.py:419`),
  subtracted from `capabilities()`. ADR 018 already pins its shape
  (batch, touch/upsert, `"fs"` reserved).
- **Link extraction is ingestion-side, not namespace-layer**: the
  roadmap explicitly excludes edge inference from the namespace layer —
  "edges are written explicitly through `mkedge`; inference is a
  separate pipeline." An OKF ingester that parses body links and calls
  `mkedge(edge_type="link")` sits precisely on the sanctioned side of
  that line, as a caller.
- Dangling links (§6.1 says tolerate them) need a stance: OKF permits a
  link to a concept that doesn't exist yet, while `Edge` endpoints
  resolve to entries. Options: skip-and-warn at ingestion (the viewer's
  behavior), or defer edge minting until the target appears.
- The `graph` verb + `SupportsGraph` protocol exist router-side with no
  backend; OKF bundles would be a concrete, well-shaped first corpus for
  traversal ("what cites this concept" is the viewer's backlinks panel,
  server-side).

### 7.4 Progressive disclosure — vfs already is the mechanism

OKF's `index.md` convention exists because a bare file tree gives an
agent no cheap "what's here" step. vfs's read family *is* that ladder:
`ls` (parent-id equality) → `tree(max_depth=)` → `stat` → `read`, with
`columns=` narrowing throughout. If descriptions become queryable facets
(§7.2), an `ls` projection can return title/description per child —
`index.md` synthesized at read time, which §8 of the spec explicitly
blesses ("consumers MAY synthesize one on the fly"). We can also simply
serve the checked-in `index.md` files as ordinary rows. The one binding
limitation is the known cursor gap (no read-family pagination; open
question deferred to the MCP pass) — large-bundle browsing over MCP will
want it.

### 7.5 Trust and lifecycle as derived, never stored

OKF's stance — record objective signals, derive verdicts at read time
(`trust_tier`, `is_stale` as pure functions) — matches vfs's grain: these
belong as projection/filter vocabulary (`results/projection.py` function
vocabulary, or chain-time filters under ADR 034), not as stored columns
that go stale. If frontmatter lands as queryable facets, trust tiers
come free as a derived filter.

### 7.6 vfs as OKF *producer*

The export direction is cheap and strategically interesting: any vfs
subtree could render *out* as an OKF bundle. vfs already records what
OKF only conventions: the `versions` table is a real, queryable `log.md`
(OKF's log has zero producers — we'd have the first honest one);
`created_by`/owner map to the actor convention; `generated.at` is
`updated_at`. Export = walk subtree, emit/verify frontmatter, generate
`index.md` per directory, derive `log.md` from version history. That
makes vfs a two-way citizen of the interchange rather than a sink.

### 7.7 Attested computations — a far rhyme, not a near-term target

OKF §10's executor/attester split (agent binds parameters, never authors
the computation; deterministic code checks the receipt) rhymes with the
hermetic-runtime direction (`research/2026-07-24-hermetic-runtime-and-
wasm-cli.md`): vfs's `run` verb executing sanctioned entries inside a
sandbox is structurally an executor, and a receipt-checking attester is
exactly the kind of deterministic consumer-side code the wasm direction
contemplates. But the spec itself defers the entire runtime protocol,
and nothing in the reference repo executes anything. Watch, don't build.

## 8. Strategic read

- **The fit is asymmetric in our favor.** OKF standardizes the corpus
  shape and deliberately refuses to standardize storage, serving, or
  query (§1 non-goals). Everything it refuses is what vfs builds. "vfs
  serves OKF bundles" is a positioning statement that costs little and
  aligns with the one-tool MCP mission; "vfs adopts OKF internally" is
  not on the table and doesn't need to be.
- **The format is young and partially fictional.** v0.2 is weeks old;
  trust/attestation are unpopulated by any producer; known interop bugs
  (tags scalar/list, link-form contradiction) sit unfixed in Google's own
  bundles. Integrate at the floor (files + `type` + links + index), stay
  loose above it, and treat the trust families as derived-read features
  we can enable when corpora actually carry them.
- **Order of attack that respects the seams**: (1) a zero-schema
  ingestion demo — write a real bundle (the GA4 one is checked in) into
  a mount, glob/grep it, publish the story; (2) the frontmatter-facets
  ADR (§7.2 fork — the only real design decision); (3) `mkedge` +
  link-extraction at ingestion, which OKF motivates concretely and ADR
  018 already pins; (4) export/round-trip; (5) trust-tier projections.
  Each step is independently useful without the next.
- **What not to do**: no bespoke markdown pipeline (spec-029 precedent
  stands — chunking already handles headings); no Attested Computation
  runtime (spec defers it; nothing consumes it); no OKF-specific object
  kind (`ObjectKind` stays `{file, directory}` per ADR 015 — an OKF
  concept is a file, identified by frontmatter or path convention, both
  chartered routes).

## 9. Open questions raised

- The §7.2 fork: general frontmatter-facets capability vs OKF-specific
  ingestion; sidecar table vs entry columns; and whether `tags`/`type`
  join the glob/grep filter channels. → pointer filed in
  `open-questions.md`.
- Dangling-link policy for ingestion-time edge minting (§7.3).
- Whether bundle ingestion is a library helper (the `skills.py` shape),
  a CLI/dev-plane verb, or a mount-type concern — undecided and not
  urgent until (1) in §8 is attempted.
