# Edge authoring API — prior art for mkedge batches and edge removal

- **Status:** research memo (commits us to nothing)
- **Date:** 2026-07-19
- **Owner:** Clay Gendron
- **Method:** three parallel researchers over `~/Git/Repos` read-only
  checkouts (POSIX heritage: linux, freebsd-src, plan9, libfuse, pjdfstest;
  tuple stores: spicedb, openfga; graph/agent systems: LightRAG, graphify,
  rustworkx, letta, agentfs, jackrabbit-oak, juicefs), file:line evidence
  throughout, plus vfs's own surface (`base.py`, `protocol.py`, `ops.py`).
- **Question under evaluation:** edges are caller-authored metadata (ADR
  016 made them entry-scoped, verb-addressed) — unlike chunks and versions,
  which storage mints. What should the public *write* surface look like:
  `mkedge` accepting `Edge` models in bulk (the 10,000+ ETL contract), and
  a removal verb? The only storage-side edges are parent-directory→child.

## Bottom line

Every surveyed family separates the same three concerns vfs must:

1. **Caller-authored edges get an explicit create/remove verb pair;
   system-structural edges are never writable through it.** POSIX `link(2)`
   refuses directories outright (EPERM in both kernels) because parent↔child
   is exclusively the filesystem's to maintain; juicefs keeps dirent
   adjacency rows writable only inside create/link/rename/unlink
   transactions, with no public edge API at all. No surveyed system mixes
   system-maintained and user-authored edges in one table guarded by a
   reserved edge type.
2. **Batch, transactional, identity-keyed mutation is the modern norm** —
   POSIX's one-edge-per-syscall arity is the outlier explained by syscall
   economics, not a design endorsement; SpiceDB (`Updates` list, one
   `ReadWriteTx`, 1000-update default cap) and OpenFGA (writes+deletes in
   one atomic `Write`, 100-tuple default cap) both batch, and both reject a
   duplicate identity within one request.
3. **Upsert-vs-strict and missing-on-delete are the real decision axes,
   and the field splits.** Strict heritage: pjdfstest pins link → EEXIST,
   unlink → ENOENT; OpenFGA defaults to both errors but offers
   `on_duplicate=ignore` / `on_missing=ignore`. Idempotent modernity:
   SpiceDB's TOUCH upserts and its DELETE silently no-ops; LightRAG's verb
   is literally `upsert_edge`, and its `remove_edges` no-ops on missing.
   SpiceDB holds both: CREATE (strict) and TOUCH (upsert) as per-update
   operations in one list.

Recommended shape for vfs (sketch in §S): `mkedge(edges: Sequence[Edge])`
mirroring `write(entries)` — batch-native, single-form sugar, touch/upsert
semantics reported per row as `created`/`updated` (already vfs's contract);
a paired `rmedge` addressing edges by the same identity coordinates that
created them, with per-row `deleted`/`not_found` reporting rather than
batch failure; parent→child stays `parent_id`-only (juicefs pattern), never
minted as edge rows, with the graph verb free to *project* parent edges at
read time (ADR 016 pin 5 spirit).

## P — POSIX heritage: verb pairing, arity, strictness, protected edges

Naming and pairing are asymmetric: `link`↔`unlink`, `symlink`↔`unlink`
(no `unsymlink`; removal is one verb), `mkdir`↔`rmdir` a separate pair
(`linux/fs/namei.c:5871,5691,5600`; `freebsd-src/sys/kern/vfs_syscalls.c:
1631,1816,1970`). Arity is strictly one edge per call — no batch link
syscall exists in either syscall table (`linux/arch/x86/entry/syscalls/
syscall_64.tbl:86-88,263-267`).

Strict, non-idempotent semantics are pinned by pjdfstest: link over an
existing target → EEXIST (`tests/link/10.t`), link a directory → EPERM
(`tests/link/11.t`), unlink a missing name → ENOENT (`tests/unlink/04.t`),
unlink a directory → EPERM/EISDIR (`tests/unlink/08.t`). Removal addresses
the edge by the same coordinates that created it — (parent dir, name) —
with FreeBSD's `funlinkat(oldinum)` as the lone optional identity guard
(EIDRM on inode mismatch, `vfs_syscalls.c:2054-2057`).

The system-edge boundary is absolute: `.`/`..` and parent→child dirents
are minted inside mkdir by the filesystem (`ufs_vnops.c:2168-2184`;
`ext4/namei.c:2934-2944`), and no syscall writes one directly; `vfs_link`
refuses directories (`namei.c:5756-5757`, `vfs_syscalls.c:1734-1736`).
Caller-authored relations (hard links) and storage-maintained relations
(dirents) share the dirent representation but never the write surface.
Plan 9 went further: no link syscall, no nlink field, no 9P link message
(`plan9/sys/src/libc/9syscall/sys.h`) — relations live in the per-process
namespace via `bind`, never as stored edges.

## T — Tuple stores: batch shapes, operation semantics, delete-by-filter

**SpiceDB** (`internal/services/v1/relationships.go`,
`internal/datastore/memdb/readwrite.go`): `WriteRelationships` takes a
list of `RelationshipUpdate`s, each an operation + relationship, all in
one transaction (`relationships.go:407-447`), default cap 1000
(`relationships.go:152`). Operations: CREATE errors on exists
(`readwrite.go:87-93`), TOUCH upserts idempotently (`readwrite.go:
112-119`), DELETE silently no-ops on missing (`readwrite.go:122-126`);
the three mix freely in one list. A duplicate identity within one request
is rejected up front (`relationships.go:375-384`). Bulk load past the cap
is a *separate* streaming verb, `ImportBulkRelationships`, create-only
(`permissions.go:1111-1183`). `DeleteRelationships` is filter-based —
type, exact id or id-prefix, relation, subject, any subset — but a fully
empty filter is refused (`relationships.go:658-668`), and a limited
delete either aborts when the match exceeds the limit or reports PARTIAL
progress (`relationships.go:547-584`). No weight/distance on tuples.

**OpenFGA** (`pkg/server/commands/write.go`, `pkg/storage/storage.go`):
one `Write` verb carries `Writes` and `Deletes` together, deletes applied
first, one transaction (`storage.go:274-277`), default cap 100 combined
(`storage.go:13-17`). Defaults are strict — write-existing and
delete-missing both error — with opt-in `on_duplicate=ignore` /
`on_missing=ignore` flags (`write.go:58-78`, `storage.go:221-235,
260-264`). Duplicate identity within a request is rejected
(`write.go:189-209`). Deletes address exact tuple keys only — no filter.

Both stores: every stored tuple is caller-authored; derived relations are
computed at read time, never materialized; neither has per-object cascade
(dangling tuples are the caller's cleanup, via filtered delete in SpiceDB).
Traversal (`Check`/`Expand`/`Lookup`) never shares a verb with mutation.

## G — Graph and agent systems: upsert norm, delete addressing, cascade

LightRAG's abstract contract is `upsert_edge(source, target, edge_data)` —
"insert or update", never an error on duplicate — with
`upsert_edges_batch` over tuples (`lightrag/base.py:614-644`);
`remove_edges` takes (source, target) pairs and silently no-ops on missing
(`networkx_impl.py:234-237`). Edge type is a property, not identity, in
both LightRAG and graphify (`extract.py:2233` carries `relation` as an
attribute). rustworkx splits removal semantics by addressing mode:
by-endpoints raises `NoEdgeBetweenNodes` on missing (`graph.rs:
1049-1052`), by-edge-index no-ops; `add_edge` upserts the payload on
non-multigraphs (`graph.rs:892-894`) and errors only on a missing
endpoint node (`graph.rs:907-911`).

Node deletion cascades to incident edges everywhere it was assessed:
NetworkX `remove_node` semantics (LightRAG), FK `ON DELETE CASCADE`
(letta's `blocks_agents` join-edge, `orm/blocks_agents.py:17-34`).
Jackrabbit Oak is the nuanced datum: strong `REFERENCE` properties fail
the *commit that deletes a referenced target* while `WEAKREFERENCE`
permits dangling (`ReferenceEditor.java:56-93`) — the
strict-vs-tolerant fork appearing as two declared reference kinds.

juicefs is the cleanest system-edge precedent: the `edge` table (parent,
name, inode, type — `pkg/meta/sql.go:65-71`) is written only inside
create/link/rename/unlink transactions (`sql.go:1912,2045`); the public
`Meta` interface exposes filesystem verbs, never a raw edge write; the
caller-authored metadata surface (xattr) is a different table and API
entirely (`interface.go:488-491`).

## V — vfs-internal constraints the API must fit

- `write(entries: Sequence[Entry] | None, *, path=..., content=...)` is
  the house batch pattern: model-typed batch as the native input, single
  form as sugar constructing the validated model at the gate, "storage
  only ever receives entries" (`base.py:724-767`). `Edge` already carries
  `weight`/`distance`/`version` that the current string-triple `mkedge`
  cannot express (`base.py:863-924`).
- `mkedge` already gates permissions at both endpoint paths and refuses
  cross-mount pairs; the memory backend already implements touch semantics
  (`created`/`updated` status, version tick on re-touch, `memory.py:
  458-467`). `MUTATING_OPS` has no removal verb for edges (`ops.py:50-52`).
- Batches must chunk by dialect budgets (`membership_budget`, CLAUDE.md);
  a SpiceDB-style hard cap of 1000 would break vfs's own 10,000+ contract
  — chunking, not refusal, is the house answer to statement growth.
- Result envelope reports per-row observations with status; an edge
  observation is the source path with `edge_type` and `version` populated.

## S — Proposed API sketch (for the ADR to accept, amend, or reject)

```python
async def mkedge(
    self,
    edges: Sequence[Edge] | None = None,
    *,
    source: str | None = None,
    target: str | None = None,
    edge_type: str | None = None,
    user_id: str | None = None,
) -> Result: ...

async def rmedge(
    self,
    edges: Sequence[Edge] | None = None,
    *,
    source: str | None = None,
    target: str | None = None,
    edge_type: str | None = None,
    user_id: str | None = None,
) -> Result: ...
```

- **Batch-native, sugar-formed** exactly like `write`: `edges` is the
  native input (validated `Edge` models — `weight`/`distance` reachable);
  the triple form is sugar constructing one `Edge` at the gate. Mutually
  exclusive forms, as `write` pins.
- **`mkedge` is touch/upsert** (SpiceDB TOUCH, LightRAG, current vfs
  behavior): per-row `created`/`updated` status, `version` ticked on
  re-touch. A duplicate identity within one batch is `invalid` (SpiceDB/
  OpenFGA precedent — last-write-wins hides caller bugs).
- **`rmedge` addresses by the creating coordinates** — exact
  `(source, target, edge_type)` triples (POSIX: removal by creation
  coordinates; OpenFGA: exact keys). Per-row `deleted` vs `not_found`
  reporting, not batch failure: strict-visible like POSIX yet
  batch-friendly like SpiceDB — the envelope reports, the caller decides.
- **Naming `rmedge`**: vfs's own morphology (`mkdir`/`mkedge` → `rmedge`)
  over POSIX's `unlink`, whose asymmetry is idiosyncratic; `dropedge`/
  `deledge` have no precedent line. One two-verb family, both in
  `MUTATING_OPS`, both permission-gated at both endpoint paths.
- **No filter-delete in v1.** SpiceDB's filter-based delete (with its
  empty-filter refusal and PARTIAL semantics) is powerful but adds a
  second addressing model and partial-failure vocabulary; OpenFGA,
  LightRAG, and POSIX all remove by exact identity. If bulk clearing by
  type/endpoint proves needed, it arrives as a later flag or verb with
  SpiceDB's guardrails, not silently in v1.
- **Parent→child stays `parent_id`-only** — never minted into `edges`
  rows, mirroring juicefs (separate representation + no public write
  path) and POSIX (EPERM on caller-authored directory edges). The graph
  verb may *project* parent edges at traversal time from `parent_id`
  (read-only projection, ADR 016 pin 5 spirit). Consequence: no reserved
  `edge_type` needs guarding in the shared table, and `Edge` model
  validators stay purely about caller-space lawfulness.
- **Entry deletion and edges:** the graph consensus is cascade on node
  delete; Oak's strong/weak split is the alternative. Not pinned here —
  the edge-wiring spec must decide (cascade aligns with `delete`'s
  existing `cascade=True` posture; trash/restore interaction needs its
  own look since a trashed entry keeps its identity).

## Open decisions for the ADR

1. Touch-only `mkedge`, or SpiceDB-style per-call strictness option
   (`create` that errors on exists)? Recommendation: touch-only until a
   consumer needs the guard; the per-row `created`/`updated` status
   already tells the caller what happened.
2. `rmedge` missing-edge row: `not_found` observation (recommended) vs
   silent no-op (SpiceDB/LightRAG) vs batch error (POSIX/OpenFGA default).
3. Edge fate on entry delete/trash: cascade, refuse-while-referenced
   (Oak-strong), or dangle-and-filter (tuple stores). Deferred to the
   wiring spec, but the ADR should name the default posture.
4. Whether `graph` projects parent→child edges from `parent_id` at
   traversal time, and under what type name, is an interface-spec detail —
   only the "never stored as edge rows" pin belongs to the ADR.

Evidence: agent reports over `linux`, `freebsd-src`, `plan9`, `libfuse`,
`pjdfstest`, `spicedb`, `openfga`, `LightRAG`, `graphify`, `rustworkx`,
`letta`, `agentfs`, `jackrabbit-oak`, `juicefs` (file:line citations
inline above); `research/2026-07-18-metadata-namespace-vs-verbs.md` (the
edges-leave-the-namespace finding this builds on); ADR 016 (verbs as the
sole metadata interface); ADR 013/017 (per-edge `version` semantics);
`base.py:724-767,863-924`, `storage/protocol.py:202-269`, `ops.py:50-52`
(the house patterns the shape must fit).
