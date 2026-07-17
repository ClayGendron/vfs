# 002 — POSIX-aligned root metadata namespace for chunks, versions, and edges

- **Status:** draft
- **Date:** 2026-04-20
- **Owner:** Clay Gendron
- **Kind:** migration + feature

## Intent

Replace VFS's current "metadata as children of the file path" namespace with a POSIX-valid hidden metadata namespace rooted at the mount root, so the full metadata tree can be represented by a traditional filesystem implementation without special-casing "file that is also a directory".

Today, VFS models metadata like this:

```text
/src/auth.py/.chunks/login
/src/auth.py/.versions/3
/src/auth.py/.connections/imports/src/utils.py
```

That works well in the database-backed logical namespace, but it cannot be projected onto a conventional POSIX filesystem because `/src/auth.py` would need to behave as both a file and a directory.

After this story, metadata lives under a single hidden mount-root `/.vfs/` tree, with a reserved `__meta__/` boundary separating mirrored user paths from VFS-internal metadata families:

```text
/src/auth.py
/.vfs/src/auth.py/__meta__/chunks/login
/.vfs/src/auth.py/__meta__/versions/3
/.vfs/src/auth.py/__meta__/edges/out/imports/src/utils.py
/.vfs/src/utils.py/__meta__/edges/in/imports/src/auth.py
```

Dotfiles follow the same rule:

```text
/src/.env
/.vfs/src/.env/__meta__/versions/1
```

The new namespace must preserve the useful properties of the current model:

- metadata is still path-addressable
- chunks and versions remain children of the owning file's metadata namespace
- directed graph edges remain browseable by type and by target/source path prefix
- any canonical VFS path, including a path already under `/.vfs/`, can be an edge endpoint
- one-hop graph operations can still use canonical `source_path`, `target_path`, and `type` columns directly

## Why

- **POSIX validity:** `/.vfs/<logical-path>/...` is a normal, representable filesystem layout. `<file>/.chunks/...` is not.
- **Raw filesystem hiding:** `/.vfs/` is hidden by normal Unix filesystem conventions, so a mounted implementation behaves more like a real filesystem under plain `ls`.
- **Single metadata root:** one hidden tree at the mount root is simpler than scattering metadata containers across every directory in the namespace.
- **Explicit schema boundary:** `__meta__/` cleanly separates mirrored user paths from reserved VFS metadata families and avoids collisions with future directory types under `/.vfs/<path>/...`.
- **Why `__meta__` instead of `.meta`:** once the caller is already inside hidden `/.vfs/`, the remaining concern is schema clarity, not Unix hidden-file behavior. `__meta__` avoids reintroducing recursive dot-prefix conventions and dotfile special-casing inside the metadata tree.
- **Filesystem backend path:** a future local-disk or FUSE implementation should not need a second, incompatible namespace just to map VFS objects onto real directories.
- **Prefix browsing for edges:** embedding the full target/source path as nested path components preserves the ability to list subsets like `ls /.vfs/src/a.py/__meta__/edges/out/imports/src/path/to/conns`.
- **Graph clarity:** `edges/out` and `edges/in` describe a directed relationship more precisely than `.connections`, and the public verb family should use the same terminology.
- **Uniform rule for dotfiles:** `.env` and other dotfiles use the same metadata rule as any other file. No filename-based special casing.
- **Backend flexibility:** database-backed implementations can keep `source_path`, `target_path`, and `type` as the canonical edge record while materializing or synthesizing `edges/in` as needed.
- **Normal path behavior:** paths under `/.vfs` are ordinary VFS entries once addressed directly; listing, traversal, and search semantics should not treat them as a second-class opt-in namespace.
- **Known host-filesystem constraint:** embedded full endpoint paths can grow long, especially for metadata-to-metadata edges. This story standardizes the public VFS namespace, not a guarantee that every host filesystem can store every projected path naively without length budgeting; filesystem-backed implementations must account for per-component and total path limits behind the public mount.

## Scope

### In

1. Replace the current metadata path conventions with a hidden mount-root metadata tree rooted at `/.vfs/`.
2. Standardize a reserved metadata subtree rooted at `/.vfs/<logical-path>/__meta__/`.
3. Standardize metadata-bearing endpoint kinds:
   - file endpoints may expose `chunks/`, `versions/`, and `edges/{out,in}/`
   - chunk endpoints may expose only `edges/{out,in}/`
   - version endpoints may expose only `edges/{out,in}/`
   - projected edge leaves and synthetic edge browse directories never expose `__meta__/`
4. Standardize `meta_root(path)` classification and exact boundary checks:
   - a path is already under the metadata root only when it uses the exact root component `/.vfs` (`path == "/.vfs"` or `path.startswith("/.vfs/")`)
   - `/.vfsbar/...` is not treated as already rooted in metadata
   - bare `/.vfs` is the reserved metadata root, not a valid edge endpoint
   - for any valid endpoint path already under `/.vfs/`, `meta_root(path) == path`
   - otherwise `meta_root(path) == "/.vfs" + path`
5. Standardize directed edge semantics:
   - the public verb family uses `edge*` terminology consistently (`mkedge(...)`, related remove/list/query helpers, docs, and errors)
   - the edge-creation operation accepts arguments in `source, target, type` order
   - the canonical directed relationship is always `source -> target`
   - the source-side path projection is `meta_root(source)/__meta__/edges/out/<type>/<target-without-leading-slash>`
   - the inverse target-side path projection is `meta_root(target)/__meta__/edges/in/<type>/<source-without-leading-slash>`
   - the `type` string is identical on both sides of the same directed edge
6. Preserve full embedded paths in the user-facing edge namespace. No percent-encoding or single-segment escaping in the public path shape.
   The embedded target/source path is the full canonical VFS path with the leading slash removed. If the endpoint is itself a metadata path under `/.vfs`, that embedded path includes `.vfs/.../__meta__/...` literally.
7. Standardize edge parsing so that everything after `.../edges/out/<type>/` or `.../edges/in/<type>/` is treated as the opaque embedded canonical endpoint path, even when that remainder itself contains `/.vfs/.../__meta__/...`.
8. Preserve canonical edge columns/fields (`source_path`, `target_path`, `type`) for direct one-hop graph queries in database-backed implementations.
9. Define `edges/out` as the canonical writable edge namespace and `edges/in` as the required inverse readable projection, whether that inverse view is persisted or synthesized.
10. Allow canonical edge records to dangle against nonexistent endpoints. `edges/out` remains authoritative immediately; `edges/in` visibility is derived from canonical edge data and attaches automatically once the target endpoint is addressable.
11. Do not add or depend on persisted `in_degree` / `out_degree` columns on the owning file row. Degree-like values are derived from edge data, not stored as denormalized object metadata.
12. Apply the same `/.vfs` mapping rule to ordinary files and dotfiles. No special-casing based on whether the basename already starts with `.`.
13. Treat `/.vfs` paths as ordinary addressable entries for `ls`, `tree`, `glob`, and search. If the caller targets `/.vfs`, normal visibility rules apply with no separate metadata-only opt-in behavior.
14. Update all path helpers, parsing helpers, parent/base-path resolution, docs, tests, and examples to the new root-metadata shape and the renamed `edge*` verb family.
15. Reserve both `/.vfs` and `__meta__` as VFS-internal path components in the metadata namespace, and define enforcement semantics:
   - `/.vfs` at the mount root is globally reserved metadata space
   - inside `/.vfs`, only the mirrored endpoint path plus reserved `__meta__/` subtree is valid VFS-managed structure
   - `__meta__` is reserved only inside the `/.vfs/...` namespace; outside `/.vfs`, names like `/src/__meta__/notes.md` remain ordinary user content
   - attempts to create arbitrary user content in reserved metadata space fail validation before backend mutation rather than being interpreted as ordinary writes

### Out

- No requirement to keep the old `/.chunks`, `/.versions`, and `/.connections` paths as long-term aliases. This story assumes a hard cut; no migration script ships as part of it, and external data lifecycle or backfill is the caller's responsibility.
- No redesign of non-file metadata namespaces beyond allowing chunk/version endpoints to carry `__meta__/edges/...`.

## Target namespace

### Chunks

```text
/.vfs/<file-without-leading-slash>/__meta__/chunks/<chunk-name>
```

Examples:

```text
/.vfs/src/auth.py/__meta__/chunks/login
/.vfs/docs/plan.md/__meta__/chunks/summary
/.vfs/src/.env/__meta__/chunks/current
```

### Versions

```text
/.vfs/<file-without-leading-slash>/__meta__/versions/<version-number>
```

Examples:

```text
/.vfs/src/auth.py/__meta__/versions/1
/.vfs/src/auth.py/__meta__/versions/2
/.vfs/src/.env/__meta__/versions/1
```

### Metadata-bearing endpoints

The `__meta__` subtree is intentionally not uniform across every projected node kind.

- File endpoints (`/.vfs/<file>/__meta__/`) may contain `chunks/`, `versions/`, and `edges/{out,in}/`.
- Chunk endpoints (`/.vfs/<file>/__meta__/chunks/<chunk>/__meta__/`) may contain only `edges/{out,in}/`.
- Version endpoints (`/.vfs/<file>/__meta__/versions/<version>/__meta__/`) may contain only `edges/{out,in}/`.
- Projected edge leaves and synthetic edge browse directories never contain `__meta__/`, `chunks/`, `versions/`, or nested `edges/`.

This keeps chunks and versions usable as real edge endpoints while preventing recursive metadata families like "chunk versions" or metadata attached to individual projected edge entries.

### Directed edges

Canonical `out` projection:

```text
meta_root(source)/__meta__/edges/out/<type>/<target-without-leading-slash>
```

Inverse `in` projection:

```text
meta_root(target)/__meta__/edges/in/<type>/<source-without-leading-slash>
```

Example:

```text
mkedge("/src/a.py", "/src/b.py", "imports")
```

must project as:

```text
/.vfs/src/a.py/__meta__/edges/out/imports/src/b.py
/.vfs/src/b.py/__meta__/edges/in/imports/src/a.py
```

not:

```text
/.vfs/src/b.py/__meta__/edges/in/imported_by/src/a.py
```

The direction changes between `out` and `in`; the edge `type` does not.

File to chunk example:

```text
mkedge("/src/file.py", "/.vfs/src/target.py/__meta__/chunks/login", "references")
```

must project as:

```text
/.vfs/src/file.py/__meta__/edges/out/references/.vfs/src/target.py/__meta__/chunks/login
/.vfs/src/target.py/__meta__/chunks/login/__meta__/edges/in/references/src/file.py
```

This is intentional: edge endpoints are always canonical VFS paths, not synthetic endpoint-kind shorthands like `files/`, `chunks/`, or `versions/`.

When parsing an edge projection, the parser stops interpreting structure after `.../edges/out/<type>/` or `.../edges/in/<type>/`. The remainder is the embedded canonical endpoint path. That remainder may itself contain `/.vfs/.../__meta__/...` literally; it is not a second edge frame.

Intermediate segments inside the embedded path are synthetic browse directories. For example, in:

```text
/.vfs/src/a.py/__meta__/edges/out/imports/src/path/to/conns/b.py
```

the segments `src/`, `src/path/`, and `src/path/to/conns/` are synthetic metadata directories created by the projection so prefix browsing works. They behave like directories for `ls`/`stat`, but they are not standalone user-authored directories and they do not carry `__meta__/`.

### Reserved namespace semantics

The reserved-path rules are intentionally narrow and structural rather than global:

- `/.vfs` is a reserved root-level path component for VFS metadata.
- Inside `/.vfs`, callers may not create arbitrary ordinary files or directories. The only valid structure is the mirrored endpoint path plus the reserved `__meta__/` subtree.
- `__meta__` is reserved only inside `/.vfs/...`; outside `/.vfs`, a user path like `/src/__meta__/notes.md` is ordinary content.
- Reserved-path collisions are rejected by path validation before the backend mutates storage. Backends should treat them as invalid/reserved-path writes, not reinterpret them as user content.

### Dangling edges

Canonical edge records may reference endpoints that do not currently exist as ordinary files or metadata nodes.

- The source-side `edges/out` projection is authoritative and must exist immediately when the edge is created.
- The inverse `edges/in` view is required as a readable projection, but it may be synthesized lazily from canonical edge data rather than persisted eagerly.
- If a target endpoint does not yet exist, creating it later causes its inverse view to reflect already-recorded incoming edges without rewriting the canonical edge record.

### Resolution example

For the recursive inverse path:

```text
/.vfs/src/target.py/__meta__/chunks/login/__meta__/edges/in/references/src/file.py
```

the resolution rules are:

- owning endpoint root: `/.vfs/src/target.py/__meta__/chunks/login`
- owning file: `/src/target.py`
- metadata family: `edges/in`
- edge type: `references`
- embedded source path remainder: `src/file.py`

This example is the reference case for parent/base-path helpers: they must distinguish the chunk endpoint root from the synthetic browse directories that sit under `edges/in/...`.

## Migration behavior

This story is a hard cut to a single canonical namespace. No migration script ships as part of it, and external data migration/backfill is the caller's responsibility. The story is complete only when:

- the `/.vfs` namespace is canonical in helpers, docs, and tests
- new writes project into the `/.vfs` namespace
- graph/path parsing logic treats `/.vfs` paths as authoritative
- old dot-prefix child-of-file paths are removed rather than carried as long-term aliases

## Acceptance criteria

A reviewer can verify this story shipped by checking the items below.

### Path shape and parsing

- [ ] Path helpers construct `/.vfs` paths:
  - `chunk_path("/src/a.py", "login") == "/.vfs/src/a.py/__meta__/chunks/login"`
  - `version_path("/src/a.py", 3) == "/.vfs/src/a.py/__meta__/versions/3"`
  - `edge_out_path("/src/a.py", "/src/b.py", "imports") == "/.vfs/src/a.py/__meta__/edges/out/imports/src/b.py"`
  - `edge_in_path("/src/a.py", "/src/b.py", "imports") == "/.vfs/src/b.py/__meta__/edges/in/imports/src/a.py"`
- [ ] `meta_root(path)` uses exact-root matching:
  - `meta_root("/src/a.py") == "/.vfs/src/a.py"`
  - `meta_root("/.vfs/src/a.py/__meta__/chunks/login") == "/.vfs/src/a.py/__meta__/chunks/login"`
  - `"/.vfsbar/src/a.py"` is not treated as already under the metadata root
  - bare `"/.vfs"` is rejected as an edge endpoint
- [ ] Dotfiles follow the same mapping rule:
  - `version_path("/src/.env", 1) == "/.vfs/src/.env/__meta__/versions/1"`
- [ ] Metadata paths can also be edge endpoints:
  - `edge_out_path("/src/file.py", "/.vfs/src/target.py/__meta__/chunks/login", "references") == "/.vfs/src/file.py/__meta__/edges/out/references/.vfs/src/target.py/__meta__/chunks/login"`
  - `edge_in_path("/src/file.py", "/.vfs/src/target.py/__meta__/chunks/login", "references") == "/.vfs/src/target.py/__meta__/chunks/login/__meta__/edges/in/references/src/file.py"`
- [ ] Only file endpoints expose `chunks/` and `versions/`; chunk/version endpoints expose only `edges/{out,in}`, and projected edge paths never expose nested `__meta__/`.
- [ ] Edge-path parsing treats everything after `.../edges/out/<type>/` or `.../edges/in/<type>/` as the embedded canonical endpoint path, even when that suffix contains `/.vfs/.../__meta__/...`.
- [ ] Base-path and parent-path resolution correctly map any `/.vfs` metadata path back to both its owning endpoint root and, when applicable, its owning file.
  - Example: `/.vfs/src/target.py/__meta__/chunks/login/__meta__/edges/in/references/src/file.py` resolves to endpoint root `/.vfs/src/target.py/__meta__/chunks/login` and owning file `/src/target.py`.
- [ ] Kind detection distinguishes `__meta__/chunks`, `__meta__/versions`, `__meta__/edges/...`, and synthetic embedded-path browse directories under `/.vfs/` from ordinary user directories.
- [ ] The `/.vfs` root path component and context-sensitive `__meta__` subtree are treated as reserved metadata namespace, not arbitrary user content.
- [ ] Writes like `write("/.vfs/tmp.txt", ...)` or `mkdir("/.vfs/src/a.py/random")` fail as reserved-path mutations rather than creating ordinary user content under `/.vfs`.

### Edge semantics

- [ ] The edge-creation operation accepts `source, target, type` in that order.
- [ ] Creating a directed edge with type `imports` projects the same type string on both the `out` and `in` views.
- [ ] `edges/out` is treated as the canonical namespace for writes and invariants.
- [ ] `edges/in` is readable as a first-class namespace for traversal and listing, whether it is persisted eagerly or synthesized lazily from canonical edge data.
- [ ] Dangling edges are allowed at the canonical record level: creating `mkedge("/src/a.py", "/src/missing.py", "imports")` preserves the `out` projection immediately and makes the inverse view attach once `/src/missing.py` becomes addressable.
- [ ] Database-backed one-hop queries can answer "successors", "predecessors", or equivalent source/target lookups directly from canonical `source_path`, `target_path`, and `type` fields without needing to walk the `edges/in` path tree.

### Prefix browsing

- [ ] Given an edge `/src/a.py -> /src/path/to/conns/b.py` of type `references`, listing `/.vfs/src/a.py/__meta__/edges/out/references/src/path/to/conns` returns `b.py`.
- [ ] Given the same edge, listing `/.vfs/src/path/to/conns/b.py/__meta__/edges/in/references/src` can expose the incoming source hierarchy rooted at `src/...`.
- [ ] Given a file-to-chunk edge, listing `/.vfs/src/file.py/__meta__/edges/out/references/.vfs/src/target.py/__meta__/chunks` returns `login`.
- [ ] The user-facing edge path remains nested and prefix-browseable; it is not collapsed into an encoded single leaf segment.

### Listings and search

- [ ] `/.vfs` entries behave like ordinary addressable paths for `ls`, `tree`, `glob`, and search once the caller targets them; there is no separate metadata-only visibility mode for traversing `/.vfs`.
- [ ] Direct reads and explicit path lookups on `/.vfs/.../__meta__/...` paths work without special flags.

### Docs and examples

- [ ] README, architecture docs, query examples, and tests use the `/.vfs/.../__meta__/...` namespace instead of the old dot-prefix child-of-file paths.
- [ ] Any examples of edge creation/documentation describe the edge in `source -> target` terms and show the same `type` on both `out` and `in`.
- [ ] Public helper names, docs, examples, and error text use `edge*` terminology consistently rather than mixed `conn*` / `edge*` naming.

## Test strategy

The acceptance criteria are the behavior contract. The implementation plan should cover at least these test buckets:

- `tests/test_paths.py` equivalents for helper construction, parsing, base-path, and parent-path roundtrips
- backend tests for `ls`, `read`, `write`, `delete`, `move`, and edge creation under the new namespace
- graph tests asserting `source, target, type` semantics and the `out`/`in` projections
- graph tests covering dangling targets and metadata-to-metadata edges such as file -> chunk and version -> file
- listing tests proving target/source prefix browsing works with nested embedded paths
- parser tests proving `/.vfs/.../__meta__/...` inside an embedded edge endpoint is treated as opaque endpoint path rather than re-parsed as a nested edge frame
- docs/example audits to catch stale `/.chunks`, `/.versions`, `/.connections`, or prior `/.vfs/<path>/{chunks,versions,edges}` forms without `__meta__`

## Dependencies and references

- Current path implementation: `src/vfs/paths.py`
- Current logical namespace documentation: `README.md`, `docs/plans/everything_is_a_file.md`, `docs/plans/database_filesystem.md`
- POSIX literacy reference: `context/learnings/2026-04-18-posix-and-related-standards.md`
- Filesystem/FUSE motivation: `context/learnings/2026-03-04-expansion-opportunities.md`, `context/learnings/2026-04-19-libfuse.md`

## Decisions and open questions

- **Resolved:** use `edges` rather than `connections` for the path family that represents directed graph relationships.
- **Resolved:** the canonical stored edge is `source_path`, `target_path`, `type`; `edges/out` is canonical, `edges/in` is inverse.
- **Resolved:** the edge `type` is stable across both projections of the same directed edge.
- **Resolved:** graph degree values are derived from edge data and are not persisted on the owning file row.
- **Resolved:** metadata is stored under a hidden mount-root `/.vfs/` tree with a reserved `__meta__/` boundary, not as child-of-file paths and not as per-directory sidecars.
- **Resolved:** dotfiles use the same `/.vfs` mapping rule as ordinary files; there is no special casing for names that already start with `.`.
- **Resolved:** file endpoints may carry `chunks`, `versions`, and `edges`; chunk/version endpoints may carry only `edges`; projected edge paths never carry their own metadata.
- **Resolved:** `edges/in` is a required readable projection, but implementations may persist it eagerly or synthesize it lazily from canonical edge data.
- **Resolved:** dangling edges are allowed; inverse visibility derives from canonical edge data rather than proving endpoint existence.
- **Resolved:** `__meta__` is intentionally visible inside hidden `/.vfs` so the metadata boundary is explicit without recursive dot-prefix conventions.
- **Resolved:** the public verb family uses `edge*` terminology consistently rather than mixed `conn*` / `edge*` naming.
- **Resolved:** `/.vfs` entries behave like ordinary addressed paths for listing, traversal, and search; there is no special metadata-only visibility mode once the caller is operating in that namespace.
