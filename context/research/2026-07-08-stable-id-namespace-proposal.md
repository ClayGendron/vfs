# Stable-ID Namespace: Evaluation and Adopted Direction

- **Date:** 2026-07-08
- **Source:** synthesis of `namespace_proposal.md` (draft v0.1, evaluated and dropped same day — this document supersedes it) plus a three-track evaluation: feasibility/refactor against the live codebase, database performance analysis, and prior-art review against plan9, linux (sysfs/kernfs), unix-history-repo, and libfuse
- **Status:** proposal — direction agreed in discussion, not yet decomposed into stories. The spec series at the end is the intended cut; story 059 (the ADR) is where this becomes binding.

## 1. Origin and verdict

The original proposal ("VFS: A Virtual File System for Agentic Search over Enterprise Data") argued for a two-layer architecture: a flat, ID-addressed **store** where every node lives under a permanent identifier and all graph semantics attach, and one or more **tree views** — symlink namespaces into the store — where names are rendering, not identity. Edges live as directory entries whose path reads as a sentence (`nodes/rpt-42/depends_on/ds-9f`), and agents interact through four verbs: glob, grep, glean, graph.

Evaluated greenfield, the verdict:

- **The core correction is right and fixes a live defect.** Identity must not be location-derived. Today's edge encoding is exactly the proposal's rejected alternative: path-pair identity via `/__meta__/edges/out/<type>/<full-target-path>` (`src/vfs/paths.py:616-629`) with `source_path`/`target_path` columns (`src/vfs/rows.py:154-155`). A rename must rewrite every edge row (`src/vfs/columns.py:91` `_move_edges`) or lineage severs — the proposal's motivating failure mode, live in this codebase.
- **~70% of the proposal maps onto machinery already built** under different names: the four verbs are the current op vocabulary with real engines behind them (glob→sargable LIKE via `patterns.py`, grep→trigram/BM25, glean→embeddings, graph→`GraphProvider`), and the 057 result envelope already solves the proposal's "batched listing protocol" open question.
- **The proposal's chosen mechanism — POSIX symlinks — cannot meet its own success criterion.** Its §6 requires names *and* resolved targets in one round trip ("if it costs a round trip per entry, the design fails in practice"). POSIX `readdir` returns names only; FUSE readdirplus and NFSv3 READDIRPLUS batch attributes but **not symlink targets**. 9P directory reads (full stat per entry) and MCP-style structured listings satisfy it natively. The requirement is a protocol property, not a filesystem property. Consequence: **the MCP surface is primary; FUSE, if ever built, is a degraded adapter.**
- **"Stay virtual" is contradicted by two of the four verbs.** Glean requires full-corpus embedding materialization plus source-sync; grep at scale requires an inverted index — this repo is itself the proof, having replaced LIKE-grep with materialized trigram posting tables (`rows.py:177-206`). Honest reframing: *the namespace is virtual; derived indexes (IDs, grams, embeddings) are materialized; content is never duplicated.*
- **The pure pathless storage design inverts the rename/glob trade the wrong way.** Renames become O(1), but glob and ls — the hottest agent operations — go from one indexed LIKE/equality to recursive containment traversal. The adopted hybrid (§3 below) keeps proposal semantics at the model level and current performance at the storage level.

## 2. Prior-art corrections worth keeping

From the reference-repo review (`plan9/sys/doc/names.ms`, `plan9/sys/man/5/{read,stat}`, `linux/Documentation/filesystems/sysfs.rst`, `linux/drivers/base/core.c`, `linux/Documentation/admin-guide/cgroup-v2.rst`, `unix-history-repo/usr/sys/h/ino.h`, `libfuse/include/fuse_lowlevel.h`):

- **The inode analogy holds but is an extension, not an application**: Unix never exposes the inode table as a namespace; the proposal deliberately does (precedent: `/proc/<pid>/`). Permanent never-reused IDs also fix a real inode defect (number recycling, which NFS patched with generation numbers).
- **The strongest precedent went uncited: Linux device links.** `drivers/base/core.c` reifies each supplier↔consumer relationship as a directory named `supplier--consumer` under `/sys/class/devlink/`, containing `supplier` and `consumer` symlinks, with inverses materialized in both device directories. That is a shipping, near-isomorphic implementation of the edge model — down to the `--` pair separator. The **edge-is-a-directory shape** (properties inside, not sidecar files beside symlinks) is adopted here; it also fixes the sidecar glob-pollution bug where `glob nodes/*/depends_on/*` would match `.edge.json` files as false edge hits.
- **Plan 9 shows the right mechanism for views: bind, not symlinks.** Plan 9 has no symlinks; union/bind mounts deliver multiple namespaces and even time-travel as mount-table operations. Since VFS is fully virtual, views are server-synthesized grafts — no dangling links, no SYMLOOP.
- **The git analogy was the proposal's weakest claim.** Git identity *is* content; our nodes are mutable rows under permanent IDs. The store is inode/qid-shaped — permanent identity (`qid.path`) with separately-versioned content (`qid.vers` ↔ revision) — not OID-shaped. Content-hash IDs would sever edges on every row update.
- **cgroup v1→v2 is the cautionary tale for multiple namespaces**: parallel hierarchies drift; v2 retreated to one unified tree. One default view is normative; additional views are advisory and disposable.

## 3. The adopted model

One sentence: **an entry is a record with a permanent ID; "file" is one of its renderings.** The view renders the content facet at a human name; the store renders the whole record at its ID. Names can change, IDs can't, and edges only ever speak ID.

Three load-bearing decisions distinguish this from the original proposal:

1. **Path survives as a regenerable index, not identity.** The `path` column (and its unique index) stays, demoted to a cache over containment. Glob compiles to the same sargable LIKE as today; batch path→ID translation is one `WHERE path IN (…)` round trip. The invariant that keeps it honest: *nothing references path* — edges, postings, and permissions speak `id`; dropping and rebuilding the column from `parent_id` + `name` loses zero information. This is the pure design plus its dcache, persisted — a real filesystem keeps rename O(1) because it must serve arbitrary programs; we keep glob O(log n) because agents glob a thousand times per rename. (Every system that refused to store paths grew a materialized path index anyway: locate, Spotlight, Everything.)
2. **Two-key identity.** Internal `id` (bigint, exists today at `rows.py:124`) remains the join key — 16-byte edge rows, posting-list `doc_id`, narrow indexes. Public `node_id` (ULID, kind-prefixed like `ds_01J9…`) is the name: globally unique across mounts (each mount has its own table and its own `id=42`), mintable client-side (no `RETURNING` dependency — the gram-staging two-phase workaround at `rows.py:63-75` is the scar this heals), permanent across dump/restore/migration, non-enumerable, and time-ordered so batch inserts append to the index's right edge instead of splattering the B-tree.
3. **Edges move to their own narrow table, ID-keyed.** `(source_id, edge_type, target_id, props JSON, external_id)` with forward `(source_id, edge_type)` and reverse `(target_id, edge_type)` composite indexes. `_move_edges` is deleted; a rename touches zero edge rows. This bends 056's "one table" (the funnel survives intact) because edge rows were paying for ~20 empty wide-row columns.

### 3.1 Schema delta

```
entries  (one row per NODE: file | directory | chunk | version — kind='edge' gone)
  + node_id    CHAR(26) UNIQUE      public stable ID (ULID) → /.vfs/store/nodes/<node_id>
  + node_type  VARCHAR(64)          semantic type from vocab (dataset, person, report)
  + parent_id  BIGINT               int FK to parent; replaces string parent_dir as the ls key
  - source_path, target_path, edge_type, edge_weight, edge_distance
  (path, name, kind, content, content_hash, embedding, revision, external_id … unchanged)

edges    (one row per EDGE)
  id BIGINT PK · source_id BIGINT · edge_type VARCHAR(64) · target_id BIGINT
  props JSON ("the sidecar": role, confidence, provenance)
  external_id VARCHAR ("<subj>--<obj>", deterministic → idempotent re-sync)
  UNIQUE (source_id, edge_type, target_id) · INDEX fwd (source_id, edge_type) · INDEX rev (target_id, edge_type)

links    (DEFERRED — additional namespaces; nothing above depends on it)
  view · path · node_id · UNIQUE(view, path)
```

Containment is an ordinary edge in the model and a special case in storage: held as `parent_id` + the path cache (one insert per file, not two; ls stays an indexed int equality), rendered virtually as `contains/` / `contained_by/` so the namespace stays uniform. The one thing the column encoding forbids — multi-parent `contains` within a single view — is by design; extra namespaces come from `links`.

### 3.2 Identity rules

- **Path hit on write → same node, new revision.** Overwrite keeps `node_id`; content changes, identity persists, edges stay valid. (Minting a new ID per write would rebuild path-as-identity with extra steps.)
- **Path miss → new node, fresh ULID**, minted client-side ("assigned on first sight").
- **Delete then recreate at the same path → new node.** The old ULID is retired forever; it was a different object that reused a name.
- **Source-synced rows key on `external_id`, not path** — "have I seen this source row" survives the row moving to a different view path between syncs.
- Concurrent creates are arbitrated by the unique index on `path` (upsert on Postgres/SQLite, catch-and-retry on MSSQL); the pre-check is an optimization, not the guarantee.

### 3.3 Hot-path costs (the numbers that motivated the hybrid)

| Operation | Cost under this design |
| --- | --- |
| Write 1,000 files | ~3 statements: one `WHERE path IN (…)` translation (chunk at ~1,000 params for MSSQL), one `executemany` update (hits), one `executemany` insert (misses, ULIDs pre-minted). Edge/gram batches insert int triples with no read-back. Constant in N. |
| `glob /data/**/*.csv` | Identical to today: one sargable `LIKE` on the path index (`patterns.py` unchanged). |
| `ls` | `parent_id = ?` — int equality, marginally cheaper than today's string `parent_dir`. |
| Edge listing (batched "readdir+readlink") | One statement: `edges ⋈ entries` on the fwd index returning target `node_id`, name, kind, node_type, path, props. Satisfies the one-round-trip requirement outright. |
| Rename dir, 10k descendants | O(subtree) path-cache rewrite in-transaction (same as today) **minus** all edge rewrites (today's extra cost). Zero edge rows change. |
| Resolve `/.vfs/store/nodes/<id>` | Unique-index probe — cheaper than a path lookup. |

Known risks carried forward: the in-memory rustworkx graph (full edge-set load on TTL, `graph/rustworkx.py:242-247`) will not stretch to enterprise scale — bounded recursive CTEs over the edges table replace it (spec 067); collision-aware computed display names conflict with paginated listings and must be deterministic-and-stable or display-only.

## 4. How edges live in the namespace

One edge row, four addresses — every surface is a different `WHERE` clause over the same table; there is nothing to synchronize.

```
/.vfs/store/nodes/rpt-42/                 ← the entry row rendered as a record
    _.md                                  ← content facet (frontmatter + body; grep/glean target)
    .meta.json                            ← system facet (node_id, external_id, hash, revision, source refs)
    contains/                             ← rendered from parent_id (the column-backed edge type)
    depends_on/                           ← WHERE source_id=42 AND edge_type='depends_on'  (fwd index)
        ds_01J9…9F3A12/                   ← ONE EDGE: a directory (devlink shape), not symlink+sidecar
            target → /.vfs/store/nodes/ds_01J9…9F3A12
            props.json                    ← {"role": "current-year data"}

/.vfs/store/nodes/ds_01J9…9F3A12/
    depended_on_by/rpt_…/                 ← same rows via rev index; inverse name from vocab,
                                            reserved `_in/<type>/` fallback when undeclared

/.vfs/store/edges/depends_on/             ← predicate-first: WHERE edge_type='depends_on'
    rpt_…--ds_…/                          ← name = edges.external_id (deterministic re-sync)
        source → …/nodes/rpt_…   target → …/nodes/ds_…   props.json

/data/2026/data.csv/__meta__/edges/…      ← view-side lens: path-index probe → id → same adjacency
```

Grammar rules: after the store prefix, segments alternate node / edge-type / node; edge types are reserved to `[a-z][a-z0-9_]*`, and non-edge entries begin `_.` or `.` so facets and edge directories can never collide. `kind` describes what a node *is*, not how a surface renders it — the same node is a file at its view path and a record at its store path (precedent: `/proc/<pid>/`, Plan 9's `/net/tcp/<n>/`). The facet files are column projections of one row and cannot disagree with each other.

**Multi-hop paths do not resolve.** `nodes/a/works_for/b/employs/a/…` is legible as a sentence but eager resolution is traversal-by-readdir (the N+1 the proposal itself forbids) and a symlink-loop factory on any POSIX surface. One hop is a path; more than one hop is the `graph` verb, which takes path-shaped input and executes as bounded recursive queries. The namespace is the address book; `graph` is the traversal engine.

## 5. Proposed spec series

Each spec changes one layer, ships with the layer above unchanged, and leaves the tree green. Dependency spine: 059 → 060 → 061 → rest; 062/063 parallel after 061; 064 → 065 → 066 is the rendering chain.

1. **`059-identity-model-decision`** — ADR-plus-spec making the pivot binding: identity moves from path to permanent client-minted node ID; path demoted to regenerable index; edges reference IDs only; MCP surface primary. Records rejected alternatives with reasons (path-as-identity — the live rename/sever defect; exposed bigint — per-mount scope, no client minting, renumbering on restore; pure pathless storage — glob and result-rendering costs; content-hash IDs — sever on update). States the three identity rules. Supersedes the path-pair edge encoding descending from story 011. No code.
2. **`060-stable-node-id`** — Adds `node_id` (ULID, unique, indexed), minted client-side, immutable; kind-prefix convention; tightens `external_id` as the re-sync key. Scope ends at schema, drift test, insert path, and exposure on the domain model and Candidates. Nothing consumes the ID yet; behavior byte-identical.
3. **`061-id-keyed-edges`** — The rewrite spec. Edges move to the narrow ID-keyed table; `mkedge`/`rmedge`/listing rewire through it; entry table drops the five edge columns; `kind='edge'` leaves the enum; `_move_edges` deleted. Acceptance: rename a subtree with lineage, zero edge rows change. Existing `__meta__/edges` surface keeps working on ID joins; no new rendering.
4. **`062-path-as-cache`** — Adds `parent_id`; establishes the nothing-references-path invariant; ships and tests the rebuild routine (regenerate the column, prove byte-equality); specifies rename as in-transaction O(subtree) cache rewrite and per-engine concurrent-create arbitration. Glob/ls proven unchanged by the existing suite.
5. **`063-batch-identity-resolution`** — The batched write/read flow: one `IN`-translation per batch, split into update-keeping-id vs insert-minting-id, `external_id` path for synced rows; fixes the gram-staging two-phase workaround. Acceptance is a statement-count test: 1,000-entry write in a constant number of statements. No public API change.
6. **`064-store-namespace`** — `paths.py` learns `/.vfs/store/nodes/<node_id>` (unique-probe resolution), facet addresses `_.md`/`.meta.json` as column projections, reserved edge-type grammar, record-vs-file rendering semantics. Read-only, single-hop; multi-hop normatively refused here.
7. **`065-edge-namespace-surfaces`** — The four renderings over 061's table and 064's grammar: subject-local devlink-shaped adjacency, derived inverses with `_in/` fallback, predicate-first `/.vfs/store/edges/`, view-side `__meta__/edges/` lens. Each surface specified as a SELECT with its serving index named; the suite proves all four agree after arbitrary mutations. Excludes traversal and authoring policy.
8. **`066-vocab-layer`** — `node_type` column plus `/.vfs/vocab/` (one markdown file per node/edge type: frontmatter domain/range/inverse/cardinality, prose semantics), rendered via the `skills.py` reserved-namespace pattern. Declared inverses upgrade 065's fallback names; `contains` documented as the column-backed special case. No validation/SHACL, no SQL auto-extraction.
9. **`067-graph-traversal-sql`** — Bounded-depth recursive CTE traversal replaces load-everything rustworkx for the graph verb (direction, edge-type filter, hop limit, store-path output); declares which analytics (centrality-style) legitimately keep the in-memory engine. Acceptance on a corpus larger than memory-comfortable with index-served plans.

## 6. Explicitly out of scope (future epics, own decision points)

- **Multi-namespace views** — the `links` table; nothing in the series depends on it.
- **SQL-source virtualization** — schema mapper, FK→edge extractor, row→markdown renderer, verb→source-SQL compiler. The largest new build in the original proposal and the one subsystem this codebase has none of (`DatabaseFileSystem` is a store-of-record, not a projection); orthogonal to this storage pivot and new work under any architecture.
- **Agent-authored edge policy** — provenance distinction from source-derived edges (proposal's open question 5) and its interaction with 058's permission grants. Note for 058: one node reachable via many paths means visibility must ultimately resolve per-ID at the store layer, not per-path.
- **Any FUSE surface** — the batched-listing analysis makes MCP primary; a FUSE adapter would ship with documented degradations.
- **Vocab validation (SHACL-style shapes) and time-travel views** — architecturally unforeclosed, deliberately unscheduled.

## 7. Open questions

- Public exposure of the internal bigint: never, or permitted in debug surfaces only? (Leaning never — one public name.)
- Display-name policy in listings: computed friendly names must be deterministic and stable-once-minted, or display-only with IDs accepted everywhere. [NEEDS CLARIFICATION: pick before 065 — pagination interacts with collision detection.]
- ULID library vs ~10-line stdlib UUIDv7; kind-prefix registry (who mints `ds_`/`rpt_` prefixes — vocab?).
- Whether `contains` rendered under the store (`contains/` listing on large directories) needs its own pagination shape distinct from ls.
