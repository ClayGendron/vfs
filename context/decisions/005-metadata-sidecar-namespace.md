# 005. Metadata Lives in a Hidden Sidecar Tree, Never as Children of the File

- **Status:** accepted
- **Date:** 2026-07-16 (decision landed with story 002, 2026-04-20; this
  record promotes it out of the archived story)
- **Deciders:** Clay Gendron
- **Decided by:** human

## Context

Every file in VFS carries derived metadata that is itself
path-addressable: chunks, versions, and directed graph edges. The
original namespace modeled these as *children of the file path*:

```text
/src/auth.py/.chunks/login
/src/auth.py/.versions/3
/src/auth.py/.connections/imports/src/utils.py
```

That works in a database-backed logical namespace, where "path" is just
a string column. It cannot be projected onto a conventional POSIX
filesystem or a FUSE mount, because `/src/auth.py` would have to behave
as **both a file and a directory** — a shape no POSIX backend can
represent (see `context/research/2026-04-18-posix-and-related-standards.md`
and `context/research/2026-04-19-libfuse.md`). With local-disk and FUSE
backends on the roadmap, the metadata namespace had to become a layout
a traditional filesystem can hold without special-casing.

## Options considered

- **Metadata as children of the file** (status quo) — natural to
  address, but structurally invalid on POSIX/FUSE; every filesystem
  backend would need a second, incompatible namespace.
- **Per-directory sidecar containers** (a `.vfs/` inside every
  directory) — POSIX-valid, but scatters metadata containers across the
  whole namespace and pollutes every directory listing.
- **One hidden parallel tree at the mount root** (chosen) — a single
  `/.vfs/` tree mirrors the logical user path, then crosses a reserved
  `__meta__/` boundary into the metadata families. POSIX-valid, hidden
  by ordinary dotfile convention, one reservation to enforce.

## Decision

Chunks, versions, and edges live in a hidden parallel tree rooted at
`/.vfs`, mirroring the owning path before a reserved `__meta__` segment
— never as children of the file:

```text
/src/auth.py                                               file
/.vfs/src/auth.py/__meta__/chunks/3/login                  chunk
/.vfs/src/auth.py/__meta__/versions/3                      version
/.vfs/src/auth.py/__meta__/edges/out/imports/src/util.py   edge
```

The settled semantics, all live in `src/vfs/paths.py`:

- **`METADATA_ROOT = "/.vfs"` and `META_SEGMENT = "__meta__"`**
  (`paths.py:39-40`) are reserved: `/.vfs` at the mount root is VFS
  space, and `__meta__` is refused in user paths so the boundary can
  never be forged from user space. Reserved-path mutations reject at
  path validation, before any backend runs. Outside `/.vfs`, boundary
  enforcement is what keeps the sidecar honest.
- **`__meta__` is deliberately not a dotname**: inside already-hidden
  `/.vfs`, the concern is schema clarity, not Unix hiding — and it
  avoids recursive dot-prefix conventions. Dotfiles like `/src/.env`
  follow the same mapping rule as any other file; no name-based
  special-casing.
- **Edges are directed projections of one canonical record**
  (`source, target, type`): the source-side
  `edges/out/<type>/<target-without-leading-slash>` path is canonical
  and writable; the target-side `edges/in/...` path is the required
  inverse readable projection (`edge_out_path` / `edge_in_path`,
  `paths.py:632-645`). The embedded endpoint stays a nested path — not
  an encoded leaf — so edge sets remain prefix-browseable with `ls`.
- Two refinements tightened the story-002 shape as the live gate
  hardened: **chunks are version-addressed**
  (`.../chunks/<version>/<name>`, `chunk_path`, `paths.py:596`), and
  **edge endpoints must be user-space paths** — `validate_edge_endpoint`
  (`paths.py:616`) rejects any `/.vfs` path as an endpoint, and nested
  `__meta__` segments are refused outright (`paths.py:541`), which
  retires story 002's metadata-to-metadata edges (chunk/version
  endpoints) rather than carrying their recursive parsing rules.

## Consequences

- **Easier:** any backend that can store ordinary directories can store
  the full metadata tree — the future FUSE/local-disk projection needs
  no second namespace; plain `ls /` stays clean (one hidden entry);
  metadata stays path-addressable, so read/ls/glob work on it without a
  separate metadata API; edge browsing by type and target prefix is
  just directory listing.
- **Harder:** every path helper carries the mirror-then-`__meta__`
  grammar (`parse_kind`, owner/parent derivation, edge decomposition
  in `paths.py` all speak it); embedded endpoint paths make deep
  metadata paths long, so the namespace-wide `MAX_PATH_LENGTH` budget
  (`paths.py:36`) does real work; `/.vfs` and `__meta__` are permanent
  reservations user content can never use.
- **Committed to:** the sidecar tree is the one metadata namespace —
  no child-of-file aliases, no per-backend variants. Backends may
  persist or synthesize the `edges/in` projection, but the path shape
  callers see is fixed.

Executed by story 002
(`context/specs/archive/002-posix-aligned-sidecar-namespace/`); the
live grammar is `src/vfs/paths.py`.
