# 016. Chunks, Versions, and Edges Leave the Namespace — Entry-Scoped Metadata, Not Paths

- **Status:** accepted
- **Date:** 2026-07-18
- **Deciders:** Clay Gendron
- **Decided by:** human (direction and approval by Clay in the 2026-07-18
  model session, on the five-researcher prior-art memo below)

## Context

ADR 005 put each file's derived metadata — chunks, versions, edges — into a
hidden parallel tree as addressable paths
(`/.vfs/<path>/__meta__/{chunks,versions,edges}/...`). Its load-bearing
justification was a projection requirement: a future FUSE / local-disk
backend must render the metadata onto a conventional POSIX filesystem, and a
live file path cannot be both a file and a directory, so metadata went into a
parallel tree rather than under the file.

The 2026-07-18 prior-art survey
(`research/2026-07-18-metadata-namespace-vs-verbs.md` — five parallel
researchers, adversarially instructed, file:line evidence) tests that
premise and finds it false, then finds the design precedent-poor and the
agent ergonomics wrong:

- **The FUSE premise is refuted.** FUSE ships a dedicated xattr vtable
  (`getxattr`/`listxattr`, `libfuse/include/fuse.h:576-585`) — a first-class,
  non-namespace metadata surface — so a POSIX/FUSE projection does **not**
  require metadata to be path-addressable. The "a path can't be both file and
  directory" constraint only bites if you insist metadata live at the file's
  own path; it never compelled a namespace at all. UFS extattr attaches
  `name=value` to a file with no namespace entry (`freebsd-src/sys/ufs/ufs/
  README.extattr`); the one POSIX-family precedent that *does* give a file a
  listable metadata directory gates it behind an entry-scoped open flag
  (`O_NAMEDATTR`, `freebsd-src/sys/kern/vfs_syscalls.c:4775-4783`) — a verb,
  not path overloading.
- **Chunks: no precedent anywhere** for addressing search-index units as
  namespace paths (zoekt, codesearch, scip, LightRAG); the two storage
  abstractions that define a namespace admit only `FILE`/`DIR` entry kinds
  (opendal `core/src/types/mode.rs:23-30`, fsspec `spec.py:679-709`).
- **Edges: near-universal row-store + verb traversal** (juicefs dirents,
  Oak references, SpiceDB/OpenFGA tuples, every graph lib). The lone *for*
  precedent — kernel symlink forests (`linux/fs/proc/fd.c`, sysfs) — is a
  small-cardinality, read-mostly convenience projection over an authoritative
  in-kernel structure, never the system of record at scale; even Plan 9
  declined to browse edges.
- **Versions: split precedent** — VMS peers and Plan 9 fossil `/n/dump` are
  path-addressable; git and btrfs are verb-only; ZFS/WAFL `.zfs`/`.snapshot`
  are read-only *views* over a verb-driven create path. No system makes a
  live file double as a directory of its own versions. git — the closest
  analog to vfs's agent read/edit/write loop — is verb-only.
- **Agent ACI favors verbs decisively.** Every agent-native system
  (agentfs, deepagents, Letta) exposes derived per-file metadata as verbs
  returning structs, never a path grammar; MCP's tools-vs-resources split
  makes the model-controlled *tool* the right home for facts an agent decides
  to fetch, and vfs's own SWE-agent ACI research penalizes hand-constructed
  schema-less path grammar on two of its highest-leverage principles
  (`research/2026-04-18-swe-agent-aci-principles.md:17-29`).

The reconciling distinction across all five facets: **navigable paths for
authored content; typed verbs for derived per-file metadata.** And the
enabling fact: the row schema already keys these on owner + discriminator —
`(entry_id, chunk_index)`, `(entry_id, version_number)`, `(source_id,
target_id, edge_type)` (`models/rows.py`) — so the path is a *derived
projection today*, not the identity. Removing it changes no storage key.

## Options considered

- **(a) Keep the `__meta__` sidecar (ADR 005 status quo)** — path-addressable
  metadata, uniform `ls`/`read`/`grep` over everything, browseable edge sets.
  But it rests on a projection *necessity* that does not exist (xattrs), has
  no precedent for chunks and only a narrow convenience precedent for edges,
  carries a heavy path grammar through every `paths.py` helper, and is the
  wrong ACI for the agent audience.
- **(b) Keep versions path-addressable, drop chunks and edges** — versions
  have real precedent (VMS, Plan 9). But it splits the model, keeps half the
  `__meta__` grammar alive, and git — the agent-loop analog — is verb-only
  anyway; the ergonomic win (one `read` for source and history) is available
  from a `versions` verb without the reservation.
- **(c) Retire namespace-addressability for all three; entry-scoped metadata
  keyed by owner + discriminator, retrieved by verbs (chosen).** Matches the
  universal chunk finding, the dominant edge finding, the agent ACI finding,
  and the refuted FUSE premise; a large `paths.py` simplification falls out.
- **(d) Project metadata as FUSE xattrs in the core** — non-namespace, but
  bakes a projection concept into the core model prematurely. Projection is a
  backend concern; the core should hold rows keyed by identity and expose
  verbs, and let a future POSIX-mount backend choose xattr vs read-only view.

## Decision

We choose (c). **Supersedes ADR 005.** Six pins:

1. **Chunks, versions, and edges are entry-scoped metadata, not namespace
   entries.** They are addressed by owner + discriminator — the row PKs that
   already exist (`(entry_id, chunk_index)`, `(entry_id, version_number)`,
   `(source_id, target_id, edge_type)`) — and carry no `path`/`name` in the
   namespace. `ObjectKind` and the path-role vocabulary collapse to
   `file | directory`.

2. **The `__meta__` per-file metadata grammar is retired.** `META_SEGMENT`
   (`__meta__`), `chunk_path`, `version_path`, `edge_out_path`/`edge_in_path`,
   `decompose_edge`, `compute_parent_file`, the chunk/version/edge branches of
   `parse_kind`, and the metadata-family path validation
   (`validate_edge_endpoint`, nested-`__meta__` refusal, family-tail parsing)
   leave `paths.py`. The models carry no path field; `Entry` loses the
   `parent_file`/`source_file`/`target_file` computed fields.

3. **`METADATA_ROOT` (`/.vfs`) stays — only the per-file `__meta__`
   projection under it goes.** `/.vfs` remains the hidden meta scope that
   hosts `/.vfs/trash` (ADR 014) and mount-level metadata; retiring the
   metadata families does not touch the trash subtree, its scope, or ADR
   014's one-scope model.

4. **Metadata surfaces through entry-scoped verbs, not navigation.** The
   agent retrieves derived metadata by verbs scoped to the owning entry
   (`versions(path)`, `chunks(path)`, `edges(path, direction, type)`) and
   embedded in grep/search results (feedback in one call). The exact verb
   surface — names, arguments, pagination — is a future interface spec, not
   pinned here; this ADR pins only that the interface is verbs, never a path
   grammar the agent hand-constructs.

5. **Any future FUSE/POSIX browse-view is a read-only projection regenerated
   from rows, never stored namespace.** Should a POSIX-mount backend ever want
   browseable history or edges, it renders them from the metadata rows on
   demand (the ZFS `.zfs` / sysfs symlink-forest pattern) or exposes them via
   `listxattr` — the projection is a backend concern, not core state, and it
   is not built until a backend needs it. Recorded so the option is not
   relitigated.

6. **The distinction is durable:** navigable paths are for *authored* content
   — ordinary files and directories, the `/.agents` tools/skills tree —
   whose identity *is* the path; typed verbs are for *derived* per-file
   metadata, whose identity is its owner plus a discriminator. New derived
   metadata families follow the verb model; they do not acquire a namespace.

## Consequences

- **Easier:** `paths.py` sheds the entire mirror-then-`__meta__` grammar and
  the metadata-family parsing/validation — a large simplification of the hot
  path; the domain models mirror the tables one-to-one with no path
  projection to keep consistent; the agent interface loses a schema-less path
  grammar that was an error and token-cost surface; `MAX_PATH_LENGTH` stops
  doing load-bearing work for deep embedded-endpoint edge paths; there is one
  fewer reserved segment (`__meta__`) to enforce.
- **Harder:** metadata is no longer reachable by the same `read`/`ls`/`glob`
  used for files — exposing it requires the verbs of pin 4 (a future spec),
  and a browseable view, if ever wanted, becomes a projection to build
  (pin 5) rather than a free consequence of storage; edge browsing by
  type/target prefix is no longer directory listing; the memory backend's
  edge representation and any code path that constructed metadata paths must
  move to owner + discriminator.
- **Committed to:** owner + discriminator as the sole identity of chunks,
  versions, and edges; verbs as their sole interface; `/.vfs` retained only
  as the meta scope for trash and mount metadata; projection kept strictly a
  backend concern. Executed as part of spec 076 (the Entry/Chunk/Version/Edge
  model split), which this ADR folds into.

Evidence: `research/2026-07-18-metadata-namespace-vs-verbs.md` (the
five-facet survey); `libfuse/include/fuse.h:576-585` (the refuted premise);
`models/rows.py` (owner+discriminator PKs already in place). Supersedes
ADR 005; relates to ADR 014 (trash keeps `/.vfs` as its scope, untouched
here), ADR 015 (the model split this rides in on), and ADR 004 (stable
identity — dependent tables key on the integer surrogate, reaffirmed).
