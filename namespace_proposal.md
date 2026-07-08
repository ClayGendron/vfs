**VFS: A Virtual File System for Agentic Search over Enterprise Data**

**Status:** Draft proposal for review **Version:** 0.1 **Date:** 2026-07-08

------

**1. Summary**

VFS exposes enterprise data (initially any SQL database) as a virtual file system that AI agents can search natively. It bridges two worlds:

- **The file system**, because agents already know how to navigate, glob, and grep one. It is the universal, tool-free interface.
- **The property graph**, because relationships and lineage carry the semantic meaning that grounds agent understanding.

The bridge rests on a two-layer architecture:

1. **The store** — a flat, ID-addressed object layer where every node and edge lives under a permanent, stable identifier. All graph semantics attach here.
2. **The tree** — one or more human-legible namespace views, composed entirely of symlinks into the store. Names can change; IDs cannot; edges only ever speak ID.

Agents interact through four verbs: **glob** (structural search), **grep** (lexical search), **glean** (semantic search), and **graph** (relationship traversal).

This is deliberately not a novel architecture. It is the inode table, git's object store + working tree, and Linux's sysfs, applied to enterprise data. Adopters should recognize it in seconds.

------

**2. Motivation**

**2.1 The problem**

Agents are increasingly the primary consumers of enterprise data, but the interfaces available to them are poor fits:

- **Raw SQL** requires schema knowledge, connection management, and per-database dialect handling. It exposes structure but not meaning: a foreign key says nothing about *why* two rows relate.
- **Bespoke APIs / RAG pipelines** are per-source integration projects with no shared navigation model.
- **File systems** are the one interface every agent handles natively — every coding agent can `ls`, glob, and grep without new tooling — but real file systems have exactly one relationship (containment) and no semantics.

The insight: project the database *as* a file system, so agents get native navigation, while preserving the graph of typed relationships (foreign keys, lineage, ownership) that gives the data meaning.

**2.2 The core tension this design resolves**

A file system is a graph with one edge type — containment — constrained to a tree, where that single edge type also defines the namespace. A property graph is a multigraph: many edge types, edge properties, multiple overlapping hierarchies.

Naive attempts to merge them fail in predictable ways:

- If node identity is a path, renames and moves destroy identity and sever every edge.
- If edges are expressed between two full paths, non-containment edges (`works_for`, `depends_on`) have nowhere natural to live and cannot be globbed.
- If edge entries are named by their target's leaf name, distinct targets with identical leaf names collide (two `data.csv` files in different years).

Every one of these failure modes was encountered during design exploration. The architecture below is shaped specifically to eliminate them.

------

**3. Design principles**

1. **Paths are sentences, not addresses.** A path like `person/p-123/works_for/acme-co` reads as a subject–predicate–object statement. The edge type is a path segment, which makes it globbable.
2. **A node's directory is its adjacency list.** Every node is a directory containing a content file plus one subdirectory per outgoing edge type, each holding one entry per edge. This is the property-graph node record, serialized as a directory.
3. **Identity is never location-derived.** Source paths, display names, and namespace positions are *properties* of a node, stored as metadata. Identity flows through stable IDs end to end.
4. **Edges always target the store, never a view.** Recorded relationships reference permanent IDs. View paths are for humans and for agents *entering* the graph; anything persisted is persisted against store IDs.
5. **Containment is not privileged in the model.** The familiar directory tree is just one edge type (`contains`) rendered as a hierarchy by the default view. It is infrastructure in the store (addressing) and ordinary edge data in the tree.
6. **Stay virtual.** VFS is a lazy projection over the source database (FUSE-style or an MCP server presenting file semantics). Nothing is materialized at scale; `ls`, glob, and grep compile to queries against the source. The file system is the interface and address space — never the query engine.
7. **Self-describing.** The mount carries its own ontology under `/.vfs/vocab/`. An agent landing in an unfamiliar VFS mount can read its way to full schema comprehension before touching data.

------

**4. Architecture overview**

```
/                               ← the mount
├── .vfs/
│   ├── store/                  ← LAYER 1: flat, ID-addressed truth
│   │   ├── nodes/
│   │   │   └── <node-id>/
│   │   │       ├── _.md            ← content rendered for agents
│   │   │       ├── .meta.json      ← type, ids, source refs, sync info
│   │   │       └── <edge_type>/    ← one dir per outgoing edge type
│   │   │           ├── <target-id> → ../../<target-id>     (symlink = edge)
│   │   │           └── <target-id>.edge.json               (edge properties)
│   │   └── edges/              ← predicate-first index (see §5.4)
│   │       └── <edge_type>/
│   │           └── <subj-id>--<obj-id>/
│   └── vocab/                  ← the ontology layer
│       ├── nodes/<type>.md     ← what each node type is
│       └── edges/<type>.md     ← domain, range, inverse, semantics
├── data/                       ← LAYER 2: the tree (default namespace view)
│   └── 2026/
│       └── data.csv → /.vfs/store/nodes/f-8a2b1c
└── views/                      ← additional namespaces (by-project, by-owner…)
    └── by-project/apollo/inputs/revenue.csv → /.vfs/store/nodes/f-8a2b1c
```

**4.1 Layer 1: the store**

Flat, machine-shaped, deliberately boring. Every node lives at exactly one canonical path, `/.vfs/store/nodes/<id>`, where `<id>` is a permanent stable identifier (UUID assigned on first sight, or content-hash-derived where dedup is valuable; truncate hashes to ~12 hex chars in paths, keep the full hash in `.meta.json`).

Because the store is ID-addressed, ambiguity is impossible at this layer: two datasets that both happen to be named `data.csv` were never namable here by anything except their distinct IDs.

All graph semantics — edges, edge properties, metadata, lineage — attach at this layer and only this layer.

**4.2 Layer 2: the tree**

The familiar hierarchy (`/data/2026/data.csv`) is a **view**: a set of symlinks into the store, generated from `contains` edges with human-chosen labels. Key consequences, all free:

- **Renames and moves are view operations.** Relabeling a `contains` edge touches nothing in the store. Lineage survives reorganization — for enterprise data, arguably the entire point.
- **Hard-link semantics.** One store node may appear at many view paths (two `contains` edges), with no identity confusion.
- **Multiple coexisting namespaces.** Source-system layout, by-project, by-region, by-owner — each is a disposable set of containment edges. The store is authoritative; views are opinions.
- **Time travel is architecturally possible.** A view is edge data; "the namespace as of last quarter" is a filter on edge validity. Not in scope for v1, but not foreclosed.

The one-sentence mental model to teach adopters (git vocabulary, deliberately):

> **Nodes live in the store under permanent IDs; the tree is a symlink view that gives them human names. Names can change, IDs can't, and edges only ever speak ID.**

------

**5. Data model**

**5.1 Nodes**

Every node is a directory in the store containing:

| Entry          | Purpose                                                      |
| -------------- | ------------------------------------------------------------ |
| `_.md`         | The node's content, rendered for agents: YAML frontmatter (structured fields) + prose body. For a SQL row, this is the row rendered legibly — the target surface for **grep** and **glean**. |
| `.meta.json`   | System metadata: `type`, `id`, full content hash, `source` (database, table, primary key), `source_path` (original filesystem path, where applicable), sync timestamps. |
| `<edge_type>/` | One subdirectory per outgoing edge type (see §5.2).          |

**Every node is typed** (`type` in `.meta.json`, mirrored in frontmatter). Types are a small, flat set — `person`, `report`, `dataset`, `order`, … — declared in the vocab. Deep class hierarchies are explicitly discouraged: format/category distinctions (`mime: text/csv`) are properties, not subclasses. A category earns a class only when it repeatedly needs distinct constraints or edge types.

Rationale: typed nodes make queries direct (`all datasets` rather than proxy conditions like "things that appear as objects of `depends_on`"), give validation shapes an attachment point, and keep a growing heterogeneous graph legible. The cost is one field per node, known for free at sync time.

**5.2 Edges**

An edge is an entry inside its subject's edge-type directory:

```
/.vfs/store/nodes/rpt-42/depends_on/ds-9f3a12 → /.vfs/store/nodes/ds-9f3a12
```

Read left to right: *rpt-42 depends_on ds-9f3a12*. The edge's **location** is its address; the symlink's **target** is the object's canonical store path. An edge never needs to encode two full paths — it is an entry, and entries live in one place.

- **Entry names are target IDs**, guaranteeing uniqueness within the edge directory (this is what resolves the two-`data.csv` collision — see §6).
- **Edge properties** live in a sidecar: `<target-id>.edge.json` beside the symlink, carrying timestamps, provenance, confidence, and relationship-level labels (`role: "prior-year baseline"`). Sidecars make edges **greppable**: "all `derived_from` edges created by last Tuesday's ETL run" is a grep over `**/derived_from/*.edge.json`.
- **Inverses are materialized both ways** (the sysfs pattern): if `works_for` is declared with `inverse: employs` in the vocab, the object side automatically presents `employs/` entries. Since everything is virtual, this is just resolving the FK in the other direction.

Edge typing is structural — the predicate *is* the directory name; an untyped edge cannot exist. The design discipline is to mint as few edge types as possible: if two candidate predicates would never be queried differently, they should be one predicate.

**5.3 Path grammar**

After the store prefix, segments alternate **node / edge-type / node / edge-type / …**:

```
nodes/p-123/works_for/acme-co
nodes/rpt-42/depends_on/ds-9f3a12
```

This rhythm makes edge types globbable:

```
glob /.vfs/store/nodes/*/works_for/*      # every works_for edge
glob /.vfs/store/nodes/rpt-42/*/          # every edge type leaving rpt-42
```

Deep paths (`p-123/works_for/acme-co/headquartered_in/nyc`) are legible as traversal expressions; whether they resolve eagerly is an open question (§10).

**5.4 Predicate-first edge index**

Globbing `nodes/*/*/works_for/*` answers "all edges of type X" but is scan-shaped. `/.vfs/edges/` provides the alternate access path — the same edges indexed by predicate first:

```
/.vfs/store/edges/works_for/
    p-123--acme-co/
        subject → /.vfs/store/nodes/p-123
        object  → /.vfs/store/nodes/acme-co
        .edge.json
```

Edge-instance names are deterministic (`<subj>--<obj>`, content-addressed for edges, so re-syncing never duplicates), with a discriminator suffix only where the same pair can be multiply linked. Both this index and the subject-local entries are lazy views over the same source FKs; there is no synchronization problem.

**5.5 The vocab layer**

`/.vfs/vocab/` is the ontology — RDFS-lite, written for agents:

```
/.vfs/vocab/
    nodes/dataset.md      # frontmatter: fields, edge types; body: prose semantics
    edges/depends_on.md   # frontmatter: domain, range, inverse, cardinality; body: meaning
```

Each file is markdown with structured frontmatter (machine-parsable) and a prose body (agent-groundable — e.g., "`placed_order` means the customer initiated the order, not that it was billed to them"; the kind of meaning no SQL schema carries). Vocab files serve grep and glean like any other content.

For SQL sources, the vocab largely extracts itself (§7.1), then gets enriched by humans.

------

**6. Naming and disambiguation**

The rule that prevents the entire class of collision bugs: **the entry name inside an edge directory is a local alias for the edge, not the identity of the target.** Identity is the symlink's target. Names are rendering.

Three layers, all serving different consumers of `ls`:

1. **Identity layer (always):** entries named by target ID. Collision-proof by construction.
2. **Presentation layer (computed at readdir):** friendly names derived from the target — start with its display/leaf name; on collision *within this directory*, prepend distinguishing ancestry or append a short ID suffix (`data.csv--9f3a12`). Git's shortest-unique-prefix logic. Because VFS is virtual, these names are computed per-listing, never stored.
3. **Relationship layer (sidecar):** `label`/`role` in `.edge.json` — often the most meaningful name of all, because "which `data.csv`" is frequently edge information ("current-year data" vs. "prior-year baseline"), not node information.

**Implementation requirement:** `readlink`-equivalent resolution must be dirt cheap and batched. A single listing call on an edge directory should return entry names *and* resolved targets (and ideally target types + display names) in one round trip. Under this scheme, "what do these entries point to" is the most common operation in the system; if it costs a round trip per entry, the design fails in practice regardless of correctness.

------

**7. Virtualization over SQL**

**7.1 Schema mapping**

The graph vocabulary largely extracts itself from a relational schema:

| SQL construct  | VFS construct                                                |
| -------------- | ------------------------------------------------------------ |
| Table          | Node type                                                    |
| Row            | Node                                                         |
| Primary key    | Basis for stable ID (namespaced: `customer/…`)               |
| Foreign key    | Edge type (bare symlink)                                     |
| Junction table | Edge type **with properties** — a junction table is already a reified edge; its extra columns (`since`, `role`) map directly to `.edge.json` |
| Column         | Frontmatter field in `_.md`                                  |

The auto-extracted vocab is a starting point; the value-add is human enrichment of edge semantics in prose.

**7.2 Laziness requirements**

- Paths resolve on demand; nothing is materialized at scale. A 50M-row table is not 50M directories on disk.
- `ls` on a large collection returns paginated or query-shaped listings (`/nodes/order/?status=open/`, or sharded ID-prefix directories).
- **glob** compiles to `WHERE` clauses on structural fields; **grep** compiles to `LIKE`/full-text search over rendered content; **glean** runs over embeddings of `_.md` renderings (which is why rows render as prose-ish markdown — embeddings of legible text ground far better than embeddings of raw JSON); **graph** compiles to recursive/join queries against the source.
- `graph` must *never* be implemented as filesystem walking — multi-hop traversal via readdir is an N+1 disaster. The verb speaks in paths (`graph /nodes/rpt-42 --follow depends_on+ --reverse` → list of store paths) but executes as queries.

**7.3 The four verbs, mapped to the layout**

| Verb      | Plane      | Operates over                                                |
| --------- | ---------- | ------------------------------------------------------------ |
| **glob**  | structural | path patterns: types, edge-type segments, view trees         |
| **grep**  | lexical    | `_.md` content, `.edge.json` sidecars, vocab files           |
| **glean** | semantic   | embeddings of `_.md` (and vocab) renderings                  |
| **graph** | relational | edge topology; input/output are store paths, execution is source queries |

------

**8. Worked example**

A report depends on two datasets that share a leaf name:

**Store (truth):**

```
/.vfs/store/nodes/rpt-42/
    _.md
    .meta.json
    depends_on/
        ds-9f3a12 → /.vfs/store/nodes/ds-9f3a12
        ds-9f3a12.edge.json     # { "role": "current-year data" }
        ds-77d0e4 → /.vfs/store/nodes/ds-77d0e4
        ds-77d0e4.edge.json     # { "role": "prior-year baseline" }

/.vfs/store/nodes/ds-9f3a12/.meta.json   # source_path: "data/2026/data.csv"
/.vfs/store/nodes/ds-77d0e4/.meta.json   # source_path: "data/2025/data.csv"
```

**Tree (view):**

```
/data/2026/data.csv → /.vfs/store/nodes/ds-9f3a12
/data/2025/data.csv → /.vfs/store/nodes/ds-77d0e4
```

No ambiguity exists anywhere: the edges name IDs; the identical leaf names live only in the view, where their differing ancestry distinguishes them; and the *meaning* of each dependency rides the edge sidecar. Moving `data/2026/data.csv` to `archive/2026-revenue.csv` relabels one `contains` edge and severs nothing.

**Agent flow:** an agent that finds a file via the view (`glob /data/**/*.csv`) resolves it to a store ID in the same listing call (§6), then traverses (`graph`) or records edges against that ID. Tooling performs view→store resolution implicitly.

------

**9. Invariants (normative)**

1. Every node has exactly one canonical store path, ID-named, permanent.
2. Every node carries exactly one type, declared in the vocab.
3. Every persisted edge references store IDs on both ends. No edge may target a view path.
4. View trees consist only of symlinks (and directories of symlinks) into the store; views are regenerable from `contains` edges and carry no unique state.
5. Edge-directory entry names at the identity layer are target IDs; friendly names are computed, never stored.
6. Location-derived names (`source_path`, display names) appear only as properties, never as identifiers.
7. Deterministic edge-instance IDs (`<subj>--<obj>`) unless multi-edges between a pair are required, in which case UUIDs with the pairing recorded in the sidecar.
8. The vocab is part of the mount: no VFS instance ships without `/.vfs/vocab/` describing its node and edge types.

------

**10. Open questions for review**

1. **Listing protocol.** Exact shape of the batched `ls` that returns names + targets + types in one round trip (§6). This is where the UX is won or lost: agents live in the view for search but land in the store for traversal, and the transition must be seamless.
2. **Deep-path resolution.** Do multi-hop paths (`p-123/works_for/acme-co/headquartered_in/*`) resolve eagerly, or are they only accepted as `graph`-verb expressions?
3. `**graph**` **verb syntax.** Filters, hop limits, direction, `--reverse`, path-shaped vs. table-shaped output.
4. **Row→markdown rendering.** Field ordering, prose templates per node type, handling of wide/blob columns; this determines glean quality.
5. **Write path.** v1 read-only vs. allowing agents to *add* edges (annotations, discovered lineage) — and if so, where user-asserted edges live relative to source-derived edges.
6. **Large-collection listing UX.** Sharded prefixes vs. query-shaped virtual directories vs. pagination tokens; what do agents handle most naturally?
7. **Validation.** SHACL-style shapes per node type (closed-world checks: "every report has ≥1 `depends_on`") — in scope for v1?
8. **Name.** "VFS" collides with the kernel's virtual file system layer. Either a problem or free SEO; decide deliberately.

------

**11. Alternatives considered**

- **Path-as-identity (no store layer).** Rejected: renames sever edges; identical leaf names collide; the original motivating failure.
- **Edges between pairs of full paths.** Rejected: non-containment edges have no home in the namespace and cannot be globbed; resolved by paths-are-sentences (§5.2–5.3).
- **Materialized export instead of virtual projection.** Rejected at enterprise scale; creates a second silo and a sync problem. Virtual-only is a principle, not an optimization.
- **Property-graph database as the interface (Neo4j et al.).** Solves the graph side but abandons the thesis: agents would need bespoke query tooling instead of native file navigation.
- **Raw RDF/SPARQL surface.** The store is isomorphic to an RDF graph (nodes ↔ resources, edge types ↔ predicates, vocab ↔ RDFS, sidecars ↔ RDF-star annotations), and an RDF export is a natural future adapter — but SPARQL as the *primary* agent interface fails the native-navigation test.

**12. Prior art**

The design is a deliberate composite of proven systems: **inode tables** (flat ID store + name-mapping tree), **git** (content-addressed object store + working tree; shortest-unique-prefix naming), **sysfs/procfs** (object graph projected as directories + typed symlink relationships + attribute files), **REST** (`/customers/123/orders` — the node/edge-type/node path grammar), and **RDF/RDFS** (typed nodes and predicates, self-describing vocab, edge reification). Adoption strategy leans on this: developers are not learning a bridge between file systems and graphs; they are recognizing one they have used for twenty years.