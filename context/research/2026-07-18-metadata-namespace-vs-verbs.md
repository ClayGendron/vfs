# Research — Metadata as namespace paths vs. entry-scoped verbs

- **Date:** 2026-07-18
- **Status:** verified — 2026-07-18; five parallel researchers over local
  checkouts, adversarially instructed (strongest for/against), each grading
  supports / contradicts / nuanced / no-precedent with file:line evidence.
- **Method:** the research.md protocol — five researchers, one per facet
  (version addressability, search-index/chunk addressability, edge
  addressability, the metadata-as-subfile steelman + FUSE requirement, agent
  ACI ergonomics) over `~/Git/Repos` read-only checkouts and vfs's own
  research memos. General knowledge is flagged where a source was not
  vendored (VMS, resource forks, ZFS/WAFL semantics).
- **Question under evaluation:** vfs projects each file's chunks, versions,
  and edges as addressable paths under a hidden parallel tree
  (`/.vfs/<path>/__meta__/{chunks,versions,edges}/...`, ADR 005). Should this
  namespace-addressability be **removed** — chunks/versions/edges becoming
  strictly entry-scoped metadata, keyed by owner + discriminator and
  retrieved by verbs, with the `__meta__` grammar and `/.vfs` metadata
  reservation retired from the core?

## Bottom line

**The proposal is well-supported; adopt it.** The decisive finding is that
ADR 005's load-bearing justification is factually wrong: the sidecar tree was
chosen because a FUSE/POSIX projection supposedly *requires* metadata to be
path-addressable (a file can't be both file and directory), but **FUSE ships
a dedicated xattr vtable** (`getxattr`/`listxattr`, `libfuse/include/fuse.h:
576-585`) precisely so per-file metadata need not be a path. The projection
constraint only bites if you *insist* metadata live at or under the file's
own path — which vfs already avoids with the parallel tree, and which
disappears entirely once metadata is verb-retrieved. Remove the architectural
necessity and the question becomes ergonomics and precedent, where the
evidence splits cleanly by kind:

- **Chunks:** *no precedent anywhere* for addressing search-index units as
  namespace paths — unanimous across zoekt, codesearch, scip, LightRAG,
  opendal, fsspec. Clear removal.
- **Edges:** near-universal row-store + verb traversal (juicefs, Oak,
  SpiceDB, OpenFGA, every graph lib). The one genuine *for* precedent —
  kernel symlink forests (`/proc/PID/fd`, sysfs `/sys/class`) — is a
  small-cardinality, read-mostly *convenience projection* over an
  authoritative in-kernel structure, never the system of record at scale.
  Removal favored; browseability, if ever wanted, is an optional projected
  view, not the addressing model.
- **Versions:** real precedent *both* ways — VMS peers and Plan 9 fossil
  `/n/dump` make history canonically path-addressable; git (the closest match
  to vfs's agent read/edit/write loop) and btrfs are verb-only; ZFS/WAFL
  `.zfs`/`.snapshot` are read-only *views* over a verb-driven create path.
  But every namespace projection lives in a sibling/parallel tree and is a
  read-only view — none is the canonical write surface, and the agent-facing
  dominant model is the verb.

And for the audience that actually matters — **agents** — the verdict is
one-sided: every agent-native system surveyed (agentfs, deepagents, Letta)
exposes derived per-file metadata as **verbs returning structs**, none as a
navigable path grammar, and MCP's own tools-vs-resources split explains why
(derived facts the agent decides to fetch are model-controlled *tools*; a
navigable URI space is application-controlled and, for tool-only clients, is
bridged back into `list`/`read` verbs regardless). The reconciling
distinction across all the evidence: **navigable paths for authored content
(files, `/.agents` tools/skills); typed verbs for derived per-file metadata
(versions/chunks/edges).**

## Verdict matrix

Claim graded per system: *"this kind of derived metadata is canonically
addressable as namespace paths."* S = supports · C = contradicts · N =
nuanced · — = no-precedent / not assessed.

| Facet | Strongest SUPPORTS | Strongest CONTRADICTS | Net |
|---|---|---|---|
| **Versions** | VMS `;N` (S), Plan 9 fossil `/n/dump` (S) | git (C), btrfs (C) | **split** — ZFS/WAFL (N) are read-only views over a verb |
| **Chunks** | *(none found)* | zoekt, codesearch, scip, LightRAG, opendal, fsspec (all C/—) | **no precedent for paths** |
| **Edges** | Linux `/proc/PID/fd` (S), sysfs symlink forests (S) | juicefs, Oak, SpiceDB, OpenFGA, rustworkx, LightRAG (all C) | **verbs dominate**; symlink forests are convenience projections |
| **Metadata-as-subfile** | Plan 9 `/proc`,`/net`; Solaris/BSD `O_NAMEDATTR` dirs (S) | UFS extattr (—), sysfs one-value rule (N) | **precedent exists but is diagnostic / verb-gated** |
| **Agent ACI** | uniform ls/grep composability (steelman only) | agentfs, deepagents, Letta, MCP, SWE-agent ACI (all favor verbs) | **verbs** |

## V — Versions: split precedent, parallel-tree placement universal

Version history *is* canonically path-addressable in two real systems: VMS
Files-11 mints each version as a peer `NAME.TYP;N` in the same directory (a
bare open resolves to highest `;N`); Plan 9 fossil exposes snapshots at
`/snapshot/yyyy/mmdd` and `/n/dump/...` as the primary openable objects, with
`history(1)` (`plan9/sys/man/1/history:34-37`) merely *computing* those paths
— proof that verbs and namespace paths coexist. Against: **git** retrieves
history strictly by verb over content-addressed objects
(`git cat-file`/`git show`, `Documentation/git-cat-file.adoc:11-27`), the
working tree holding exactly one version; **btrfs** gates history behind an
ioctl that creates a separate subvolume tree (`linux/fs/btrfs/ioctl.c:704`,
`5159-5161`); **ZFS/WAFL** `.zfs/snapshot` / `.snapshot` are read-only
*views* whose canonical create path is a volume verb (`zfs snapshot`), not a
namespace write.

**The crux, and the one universal finding:** *no* surveyed system makes a
live file path double as a directory of its own versions. Every namespace
projection — VMS peers, ZFS `.zfs`, Plan 9 `/n/dump` — lives in a sibling or
parallel location. vfs's `/.vfs/.../__meta__/versions/N` is in that
tradition; the anti-pattern has no precedent. So keeping namespace versions
would be defensible (WAFL/ZFS/Plan 9 read-only-view tradition); dropping them
for a `versions(path)` verb moves toward git/btrfs — also well-precedented,
and the better match for an agent read/edit/write loop.

## C — Chunks: no precedent for addressing index units as paths

Unanimous. Every search/retrieval system stores index units as an internal
store reached only by a query verb, never a listable path: zoekt ngrams live
in binary shards touched only inside `Search` (`api.go:418-419`); codesearch
trigrams are 3-byte keys into a posting table (`index/read.go:34-58`); scip
symbols/occurrences are protobuf records — the only paths present are the
*source-file* paths the index points *at* (`scip.proto:79-89`), the opposite
direction of the vfs claim; LightRAG chunks are content-hash-id'd KV/vector
rows fetched by `get_by_id`/`query` (`lightrag/base.py:262-372`). Decisively,
the two storage abstractions that *do* define a namespace — opendal
(`EntryMode = {FILE, DIR, Unknown}`, `core/src/types/mode.rs:23-30`) and
fsspec (`info()`/`ls()` types only `"file"`/`"directory"`,
`fsspec/spec.py:679-709`) — admit **no** index-artifact entry kind at all.
No diagnostic interface even *lists* chunks as paths.

## E — Edges: verbs dominate; browseable edges are a narrow convenience precedent

The dominant pattern is edges-as-rows-traversed-by-API, without exception
among dedicated stores: juicefs dirents are adjacency rows keyed
`(parent, name)` (`pkg/meta/sql.go:65-71`) but no relation (xattr, symlink,
chunk) is itself a path; Oak references are UUID properties with the inverse
edge in a hidden index reached only by `getReferences()`
(`ReferenceIndex.java:124-141`); SpiceDB/OpenFGA relation tuples are MVCC rows
filtered by struct and traversed by `Check`/`Expand`/`Read`
(`pkg/datastore/datastore.go:560-572`; `pkg/storage/storage.go:152-210`);
rustworkx/strwythura/LightRAG/graphify keep edges as in-memory graph elements
or DB rows. Even Plan 9 — the expected strongest *for* — declined to browse
edges, serving process→fd and process→ns relations as *readable text
snapshots* (`sys/man/3/proc:76-104`), not browseable directories.

The one genuine *for*: **kernel symlink forests** — `/proc/PID/fd`
(`linux/fs/proc/fd.c:174,209,310`) and sysfs `/sys/dev`,`/sys/class`,`/sys/
block` (`fs/sysfs/symlink.c:84`; `Documentation/filesystems/sysfs.rst:
328-342`) materialize directed relations as `ls`/`readlink`-able symlink
directories — structurally vfs's exact move. But two cautions: these are
small-cardinality, read-mostly *projections* over an authoritative in-kernel
structure (dozens of fds, hundreds of devices), never a bulk relational store
at vfs's 10k+ scale; and they are the convenience surface, never the system
of record. Honest reading: browseable edges have real but narrow precedent as
a projection layer, and none as the primary storage/traversal model — favoring
row/tuple storage with verb traversal, browseability optional.

## S — The steelman and the FUSE requirement: ADR 005's premise refuted

There is genuine precedent for exposing rich, *listable*, per-object metadata
as a walkable namespace: Plan 9 `/proc/PID` is a directory of ~19
heterogeneous named files (`plan9/sys/src/9/port/devproc.c:78-97`), `/net/tcp/
N` projects `ctl`/`data`/`local`/`remote`/`status` (`devip.c:78-101`), Linux
`/proc/PID` mixes dozens of REG/DIR/LNK entries (`linux/fs/proc/base.c:
3313-3354`), and — most damaging to ADR 005's "POSIX can't hold it" claim —
a **Solaris/BSD file owns a listable hidden directory of named-attribute
files**, opened via `O_NAMEDATTR` (`freebsd-src/sys/kern/vfs_syscalls.c:
4775-4783`; `fcntl.h:144` "Solaris compatibility"). A POSIX-family kernel
*does* give a file a listable metadata sub-namespace.

**But the FUSE requirement is false.** FUSE declares a dedicated xattr vtable
separate from lookup/readdir (`libfuse/include/fuse.h:576-585`;
`fuse_lowlevel.h:852-931`), which vfs's own research already calls the
"arbitrary metadata surface" (`context/research/2026-04-19-libfuse.md`), and
`listxattr` supplies the very enumerate/discover affordance the "you need
`ls` to browse metadata" argument leans on. UFS extattr attaches `name=value`
to a file with **no** namespace entry (`freebsd-src/sys/ufs/ufs/
README.extattr`). So a FUSE/POSIX projection does not require path-addressable
metadata; xattrs are the idiomatic non-namespace channel, and the
named-attribute-directory precedent that *does* give a listable sub-namespace
gates it behind an entry-scoped open *flag* (`O_NAMEDATTR` ≈ a verb), not
path overloading. The surviving steelman narrows to: *edges are genuinely
tree-shaped, so a listing idiom fits them* — but that is ergonomics
deliverable as an `edges(path, ...)` verb or an optional projected view, not
the architectural necessity ADR 005 asserted. And the closest same-path
precedents (resource forks, NTFS ADS) are cautionary tales; sysfs is
explicitly restricted to one-value-per-file (`sysfs.rst:62`); `/proc` is
introspection, never a durable storage schema with a 10k-batch write
contract.

## A — Agent ACI: verbs, decisively

Every agent-native system exposes derived per-file metadata as verbs
returning structs: **agentfs** retrieves metadata via `stat()` → `Stats`
struct (`sdk/python/agentfs_sdk/filesystem.py:578`) and puts version history
in *separate tables* as an extension point, not path children
(`SPEC.md:480-486`); **deepagents**' tools are all verbs (`ls`/`read`/`grep`/
`glob`), and vfs's own analysis proposed its metadata additions as verbs
`list_versions`/`successors`/`search_semantic`
(`context/research/2026-03-04-deepagents-analysis.md:201-206`); **Letta**
retrieves archival/derived data via `archival_memory_search`, `get_version`,
`diff` (`context/research/2026-04-23-letta.md:71,250-257,444-449`) while
keeping navigable paths only for *authored* memory content.

**MCP explains the mechanism.** MCP splits data exposure by who controls
navigation: **tools** are model-controlled, discovered as JSON Schema
(`modelcontextprotocol/.../server-concepts.mdx:16,85`) — option (B);
**resources** are application-controlled, browsed through the app's UI, "not
the model's lane" (`:167-174`). A `__meta__` grammar the *agent* drives is
neither — it is the model hand-constructing schema-less URIs, exactly what
resource-templates + `list_resources`/`read_resource` bridges
(`fastmcp/.../resources-as-tools.mdx:13-19`) exist to avoid. This violates
the two highest-leverage principles from vfs's own ACI research
(`context/research/2026-04-18-swe-agent-aci-principles.md:17-29`): *compact —
high-order ops in one call* (path navigation is multi-turn `ls`→`ls`→`read`
discovery of what a verb returns once) and *guardrails against malformed
input* (a hand-constructed `edges/out/<type>/<target>` grammar with no schema
is a hallucination surface a typed verb eliminates). Recovery decays fast —
90.5% success with 0 prior errors, 57.2% after one — so prevention beats
multi-turn repair.

## Recommended deltas (actionable)

1. **Supersede ADR 005.** Its premise (FUSE/POSIX requires path-addressable
   metadata) is refuted by `libfuse/include/fuse.h:576-585`. The new decision:
   chunks/versions/edges are entry-scoped metadata keyed by owner +
   discriminator (`(entry_id, chunk_index)`, `(entry_id, version_number)`,
   `(source_id, target_id, edge_type)` — already the table PKs in `rows.py`),
   retrieved by verbs, with **no `path`/`name` in the namespace**.
2. **Retire the `__meta__` grammar and `/.vfs` metadata reservation from the
   core.** `parse_kind`'s chunk/version/edge branches, `decompose_edge`,
   `chunk_path`, `version_path`, `edge_out_path`/`edge_in_path`,
   `METADATA_ROOT`/`META_SEGMENT`, and the meta-path validation all leave the
   hot path — a large `paths.py` simplification. `PathRole` collapses to
   `file | directory` (reinforcing spec 076).
3. **Model consequence (feeds spec 076):** `Chunk`/`Version`/`Edge` carry no
   `path` field — they are addressed by owner entry + discriminator. `Entry`
   loses `parent_file`/`source_file`/`target_file` (already planned).
4. **Preserve as explicitly-optional future:** if a POSIX-mount / FUSE
   backend ever wants browseable history or edges, deliver it as a *read-only
   projection regenerated from the rows* (the ZFS `.zfs` / sysfs symlink-forest
   pattern) or via `listxattr`, never as stored namespace state. Record it so
   the option isn't relitigated.
5. **Interface direction (future verb spec, not this pass):** derived
   metadata surfaces as entry-scoped verbs — `versions(path)`,
   `chunks(path)`, `edges(path, direction, type)` — and embedded in
   grep/search results (feedback-in-one-call). The distinction to pin:
   navigable paths for authored content, verbs for derived metadata.

## What this does not settle

- The exact verb surface (names, arguments, pagination) for
  `versions`/`chunks`/`edges` — a future interface spec.
- Whether edges keep a `revision` and how graph traversal verbs page at scale
  — orthogonal, owned by the graph-traversal work.
- The memory backend's internal edge representation — follows the same
  owner+discriminator model but is wiring, deferred with spec 076's out-of-scope.
