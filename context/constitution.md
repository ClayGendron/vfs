# VFS Constitution

The policies that, if broken, stop VFS from being VFS.

## Preamble — How to read this document

Each principle below is a policy. Policies use RFC 2119 keywords: **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, **MAY**. A **MUST** is load-bearing for the project's identity and cannot be waived inside the codebase. A **SHOULD** may be deviated from only by a written decision in `context/decisions/` that names the principle, the deviation, and the expected expiry.

**Order of precedence.** When two articles apply to the same decision and conflict, the later article yields to the earlier one. Article 1 is the last to bend. This order is deliberate: primitive integrity is the most expensive thing to restore once broken; operational discipline (Article 5) is the easiest to tighten incrementally.

## Article 1 — Primitives

VFS has four first-class primitives. Every feature in the system either manipulates one of them or composes them. Nothing else is first-class.

**Everything is a file** means everything first-class in VFS must be addressable inside one canonical namespace. Files are not a special case; they are the governing metaphor for how the whole system is named, routed, and observed.

### 1.1 Namespace

A **Namespace** is the one rooted tree that contains every first-class object VFS exposes. It is the public world model of the system.

Everything first-class in VFS MUST be addressable within this namespace by an absolute, normalized path. There are no parallel public naming systems, no backend-specific URL grammars, and no hidden identifiers that callers must learn in order to use the filesystem correctly.

Paths are the addressing form of the namespace, not a separate primitive. A path MUST identify one location in one terminal filesystem after mount resolution. Namespace rules are load-bearing: mounts compose subtrees into the same world, they do not create side worlds.

### 1.2 Entry

An **Entry** is one row describing one observation of an object in the namespace. It is not the object — it is what an operation returned about it, at the moment it returned. (`src/vfs/results.py:87`.)

An Entry is fully described by:

- `path` — absolute, normalized, canonical identity. MUST be unique within its terminal filesystem.
- `kind` — closed enum: `file | directory | chunk | version | edge | tool | api` (`src/vfs/paths.py:30`). A path's kind MUST be derivable from the path and namespace conventions, never from a hidden field.
- `revision` — the coherence stamp for this Entry (see §1.4). MUST be populated on every Entry.
- Zero or more populated fields (`content`, `lines`, `size_bytes`, `score`, `in_degree`, `out_degree`, `updated_at`).

**A null field means "not populated by this call," never "absent on the object."** A consumer MUST NOT infer the truth of an attribute from a null. Entry is frozen; enrichment returns a new Entry.

New object kinds extend the enum; they MUST NOT live outside it.

### 1.3 Mount

A **Mount** is a named attachment of one `VirtualFileSystem` inside another at a single-segment path (`/data`, never `/data/archive`; enforced at `src/vfs/base.py:86`). Resolution is longest-prefix: the terminal filesystem for a path is found by walking the mount chain and rebasing at each step (`src/vfs/base.py:140–167`).

A Mount **composes** namespaces; it does not create a new world. Callers see one unified tree. A Mount MAY change which filesystem answers a subtree and which capabilities are supported there. A Mount MUST NOT change path semantics, `VFSResult`/`Entry` shape, or the error taxonomy (Article 2).

Cross-mount operations (moves, copies, unions of searches) are NOT atomic. Any operation that crosses a mount boundary MUST either declare so in its result or raise `CrossMount`. Silent cross-mount behavior is forbidden.

Composition is the only permitted form of backend combination. URL chaining, per-path backend hints, and side-channel routing tables are forbidden.

### 1.4 Revision

A **revision** is a monotone coherence stamp attached to every Entry. It is the unit of cache invalidation and read consistency. The stamp answers two questions cheaply: "is my cached copy stale?" and "has anyone changed the public state of this Entry since I read it?"

A revision is:

- **Monotone per path.** A later write MUST produce a stamp that sorts after every prior stamp for that path. Encoding is the backend's choice — an integer counter, a ULID, `updated_at || content_hash`, or anything else that sorts monotonically — but the ordering MUST be total and stable.
- **Bumped on every material public-state change.** A write or mutation that would make a public operation on that path return materially different state MUST produce a new stamp. This includes more than content bytes: exposed metadata, directory membership, and other observable Entry state count. No-op writes and internal maintenance MAY keep the stamp.
- **Usable for optimistic concurrency.** A caller MAY pass `if_revision=X` on a read or write; a mismatch MUST surface as `Conflict` in the error taxonomy (Article 2).
- **Carried on every result.** Every Entry in every `VFSResult` MUST include its current stamp.

A revision is *not* stored history. The stamp tells you *that* the Entry changed, not *what it was before*. Retrieving prior content is an optional backend capability — the **version-history capability** — governed by Article 4 and reached through the reserved `/.vfs/path/to/file/__meta__/versions/N` namespace.

## Article 2 — Agent-First Contract

VFS is designed for agent callers. "Agent-first" is not branding; it is four testable contract invariants. A PR that violates any of them fails review.

1. **One envelope.** Every public operation MUST return `VFSResult` (`src/vfs/results.py:250`). Success, failure, and data share one shape. Errors MUST belong to a closed taxonomy: `NotFound | PermissionDenied | UnsupportedCapability | Conflict | CrossMount | BackendUnavailable | Invalid`. Raw transport or driver errors MUST be mapped into this taxonomy before crossing the public boundary.

2. **Declared capabilities.** A filesystem MUST be able to answer whether it supports a given operation on a given path *without executing the operation*. Agents MUST NOT be required to probe via trial-and-error.

3. **Bounded output by default.** Every listing, search, or traversal op MUST accept a limit and MUST return a deterministic cap with a refine or cursor mechanism when the limit is reached. Unbounded reads are reserved for operations that address a single known path.

4. **Composable results.** Two results of compatible function class MUST combine under set algebra (`&`, `|`, `-`) without reserialization. Cross-class combinations MUST coerce to a documented envelope (`function="hybrid"`) or refuse with `Invalid`.

A pattern fails this article if it forces an agent to guess, retry blindly, or parse prose to learn state.

## Article 3 — Lineage from Plan 9 and Unix

VFS a student of Plan 9 and Unix. In the cases where either of those tools has a convention or a standard, this project SHOULD follow as completely as possible.

**Kept.** One rooted namespace; longest-prefix mount routing; composition through mounts, not through backend URLs; text-shaped I/O that the classic tools (`grep`, `cat`, set operators) can inspect; the Plan 9 insight that resources other than plain files — chunks, versions, connections — belong in the namespace.

**Rejected.** POSIX mode bits; raw inode exposure; symlink-heavy indirection; per-process bind as a user feature (VFS mounts are client-global); sprawling protocol surfaces with implicit capability discovery.

**Limits.** Plan 9 itself refused to map every adjacent concern into the namespace. The Pike et al. 1992 paper is explicit: process creation and shared memory stayed as system calls because forcing them into file I/O would demand a dishonest file shape. VFS inherits this discipline. When a concern would require lying about what a file *is*, keep it out.

Deviations from Plan 9 and Unix in future work MUST be well documented and recorded in `context/decisions/` with the motivating constraint.

## Article 4 — Backend-Agnostic Contract

A storage engine, search provider, graph provider, embedder, or future runtime is a replaceable implementation of a declared capability. The user-facing contract (Articles 1–2) MUST hold across any backend that claims the capability.

- Backends MUST declare capability explicitly (Article 2, §2). Partial or silent implementations are forbidden.
- Public operations MUST NOT accept backend-specific path grammar, URL chains, or connection strings inside path arguments.
- A backend MAY implement a superset of the contract. Extensions MUST be exposed as new named operations, never as overloads of existing ones.

Portability is architectural and the contract does not shrink to a least common denominator, but a caller MUST be able to discover capability without reading backend source.

## Article 5 — Operational Discipline at Scale

VFS runs over millions of entries, concurrent writers, and heterogeneous backends. This article governs runtime behavior, not contract shape.

- **Reads are snapshots.** No live handles. A reader sees one coherent point-in-time view; retries are idempotent.
- **Writes declare their conflict mode.** Every write path MUST specify last-writer-wins, revision-guarded, or reject-on-conflict. Silent clobbering is forbidden.
- **Enumeration is bounded and refinable** by default (Article 2, §3).
- **Long-running ops expose progress and cancellation** when the transport allows. MCP surfaces MUST carry them; in-process Python calls MAY omit them with an inline note.
- **Cost is part of the contract.** A backend that makes an operation O(tenants) when the contract implies O(1) MUST declare so in capability metadata.

## What This Constitution Does Not Govern

The following are out of scope here and governed by sibling documents under `context/standards/`:

- **Public API versioning, deprecation, back-compat.** → `versioning.md` (pending).
- **Security, authentication, multi-tenant isolation.** → `security.md` (pending). The constitution assumes every filesystem is single-tenant unless it declares tenant scope.
- **Observability, telemetry, tracing.** → `observability.md` (pending).
- **Language style, testing policy, release mechanics.** → existing `python-style.md`, `testing.md`, `release.md`, `tooling.md`.

Anything not covered here and not covered by a sibling standard is engineering judgment, not constitutional rule. Live trade-offs belong in `context/open-questions.md`.
