# 005 — Root LocalFileSystem accepts cwd-relative and host-absolute paths

- **Status:** draft
- **Date:** 2026-04-20
- **Owner:** Clay Gendron
- **Kind:** feature + path-model + routing

## Intent

Define the path contract for the future mode where `LocalFileSystem` is the filesystem that owns the root namespace directly rather than being mounted under a synthetic VFS prefix like `/code`.

In that mode, Grover should behave like a host filesystem namespace:

- full host-absolute paths are the canonical path form
- working-directory-relative paths are accepted as caller input sugar
- mounted child filesystems are mounted at full host-absolute prefixes too
- results come back in the same canonical host-absolute form regardless of which backend actually owned the path

This story is intentionally pre-implementation. It standardizes the contract before the larger routing, path-normalization, and `LocalFileSystem` root-ownership work lands.

Today:

- `normalize_path()` in [`src/vfs/paths.py`](../../../src/vfs/paths.py) treats a relative input like `src/main.py` as VFS path `/src/main.py`, not as `cwd/src/main.py`.
- `VirtualFileSystem._normalize_mount_path()` in [`src/vfs/base.py`](../../../src/vfs/base.py) only accepts single-segment mount paths, so system-like mount prefixes such as `/Users/claygendron/Git/Repos/grover/docs/archive` are impossible.
- The router's canonical namespace is VFS-absolute, not host-absolute, so callers must know synthetic mount roots in advance.

After this story's future implementation:

- when `LocalFileSystem` owns the root namespace, canonical file/directory paths are full host-absolute paths
- relative input paths resolve against an explicit working directory before normalization and routing
- mount routing uses longest-prefix matching on normalized host-absolute mount paths
- results emitted from self or from mounts are indistinguishable except by backend capability, not by path shape

## Why

- **Agent ergonomics:** editors, shells, and coding agents naturally produce paths like `src/auth.py` and `/Users/.../src/auth.py`, not synthetic router paths.
- **Mount transparency:** a caller should not need to know whether `/Users/.../repo/docs/spec.md` lives on local disk or in a mounted database/filesystem backend.
- **Compatibility with root-local operation:** if `LocalFileSystem` is the namespace owner, synthetic mount-root path conventions become friction rather than help.
- **Preemptive clarity:** the current code still assumes VFS-style absolute paths and single-segment mounts. This story locks the destination before the refactor starts.

## Expected Touch Points

- [`src/vfs/paths.py`](../../../src/vfs/paths.py)
- [`src/vfs/base.py`](../../../src/vfs/base.py)
- [`src/vfs/routing.py`](../../../src/vfs/routing.py)
- future/current `LocalFileSystem` root path resolution and security boundary code
- query/parser/executor path normalization at the API boundary
- docs and tests covering root-local behavior

## Scope

### In

1. This story applies only when `LocalFileSystem` is the root/base filesystem that owns the namespace directly.
2. In that mode, the canonical path form for ordinary files and directories is the normalized host-absolute path.
3. Relative caller inputs are accepted, but only as syntax sugar. They are resolved against an explicit working directory before mount matching, metadata parsing, permission checks, or backend dispatch.
4. The working directory itself is a canonical host-absolute path.
5. Public results always emit canonical host-absolute paths. Relative paths are input-only convenience, never stored as canonical identities and never emitted in `Entry.path`.
6. Mounted child filesystems are registered at canonical host-absolute prefixes, not at synthetic single-segment mount names.
7. Multi-segment mount paths are required in this mode. Longest-prefix routing must choose the deepest matching absolute mount path.
8. Relative and absolute spellings of the same target must resolve to the same terminal filesystem and the same canonical `Entry.path`.
9. Path-bearing filters and selectors follow the same rule:
   - relative `path=` filters are anchored at the working directory
   - relative glob roots/patterns are anchored at the working directory
   - absolute `path=` filters and absolute glob roots stay absolute
10. Mount shadowing rules continue to apply, but against host-absolute mount prefixes. Self-owned local-disk results under a mounted prefix are excluded in favor of the mounted filesystem's results.
11. The path contract must not depend on ambient `os.getcwd()` calls scattered through backend code. Relative resolution happens through one explicit working-directory seam at the public boundary.
12. Story 002's `/.vfs/.../__meta__/...` namespace remains the metadata contract. When the canonical user path is host-absolute, the embedded user path inside `/.vfs` is that host-absolute path without its leading slash.

### Out

- Implementing root-owned `LocalFileSystem` in this story. This document is a contract, not the delivery story for the refactor itself.
- Deciding the full host-security policy for which absolute prefixes are allowed. Authorization and boundary enforcement are separate concerns from path syntax and routing.
- Changing path behavior for routers whose root is not `LocalFileSystem`.
- Defining Windows drive-letter or UNC path behavior. This story is POSIX-host-path only.
- Defining shell/session UX like `cd`, prompt state, or interactive directory stacks.
- Solving every metadata-path relative-input convenience. The core requirement is canonical host-absolute ordinary paths plus absolute mount routing.

## Path Contract

Assume:

```text
working_dir = /Users/claygendron/Git/Repos/grover
```

Then these caller inputs all name the same file and must canonicalize to the same path before routing:

```text
README.md
./README.md
/Users/claygendron/Git/Repos/grover/README.md
```

Canonical output path:

```text
/Users/claygendron/Git/Repos/grover/README.md
```

This applies to every path-taking public method: `read`, `write`, `edit`, `delete`, `stat`, `ls`, `tree`, `glob`, `grep`, graph operations that accept paths, and any CLI/query adapter built on top of them.

## Mount Contract

Assume the root filesystem is a `LocalFileSystem` and a child filesystem is mounted at:

```text
/Users/claygendron/Git/Repos/grover/docs/archive
```

Then all of these must route to the mounted child filesystem, not to the base local-disk implementation:

```text
docs/archive/spec.md
./docs/archive/spec.md
/Users/claygendron/Git/Repos/grover/docs/archive/spec.md
```

The caller should see the same canonical result path either way:

```text
/Users/claygendron/Git/Repos/grover/docs/archive/spec.md
```

No synthetic mount prefix like `/archive` or `/docs` should appear solely because a mount boundary exists internally.

### Longest-prefix example

If mounts exist at both:

```text
/Users/claygendron/Git/Repos/grover/docs
/Users/claygendron/Git/Repos/grover/docs/archive
```

then:

```text
/Users/claygendron/Git/Repos/grover/docs/archive/spec.md
```

must route to the deeper `/Users/claygendron/Git/Repos/grover/docs/archive` mount.

## Metadata Alignment

This story does not replace Story 002's metadata shape. It defines how host-absolute user paths project into it.

Example ordinary path:

```text
/Users/claygendron/Git/Repos/grover/src/auth.py
```

Corresponding metadata root:

```text
/.vfs/Users/claygendron/Git/Repos/grover/src/auth.py/__meta__/
```

Example version path:

```text
/.vfs/Users/claygendron/Git/Repos/grover/src/auth.py/__meta__/versions/3
```

Relative ordinary inputs must resolve to the same canonical ordinary path first; metadata derivation then follows the existing `/.vfs` rules from Story 002.

## Design Constraints

1. Canonical identity must be single-form. In root-local mode, that form is host-absolute POSIX path, not a mixture of relative and absolute spellings.
2. Relative-path support is a boundary concern, not a storage concern. Backends should receive canonical paths after resolution rather than each backend inventing its own `cwd` logic.
3. Mount routing must be compatible with nested absolute prefixes and longest-prefix selection.
4. Result rebasing must preserve canonical host-absolute paths even when the terminal filesystem was a child mount.
5. Existing non-root-router behavior should remain intact. This story adds a new root-local path mode; it does not force every mounted deployment to abandon VFS-style paths immediately.
6. The eventual implementation must not quietly treat `src/a.py` as `/src/a.py` in root-local mode. That is the current behavior and the thing this story exists to replace.
7. The eventual implementation must centralize the relative-to-absolute step in one helper/API seam so tests can prove that the same rules apply across every public method.

## Acceptance Criteria

A reviewer can verify this story's future implementation with the checks below.

### Canonicalization

- [ ] In root-local mode, `read("README.md")`, `read("./README.md")`, and `read("/Users/claygendron/Git/Repos/grover/README.md")` resolve to the same terminal path and return `Entry.path == "/Users/claygendron/Git/Repos/grover/README.md"`.
- [ ] `stat`, `delete`, `write`, `edit`, and `mkdir` follow the same relative-to-absolute rule.
- [ ] Returned results never emit relative `Entry.path` values in root-local mode.

### Mount routing

- [ ] Absolute multi-segment mount paths are allowed in root-local mode.
- [ ] Longest-prefix routing works for nested absolute mount paths.
- [ ] A relative path whose resolved absolute target falls under a mounted prefix routes to the mount, not to the base local-disk backend.
- [ ] `_exclude_mounted_paths()` or its successor filters self-owned results using absolute mount prefixes so self does not leak shadowed local entries under mounted paths.

### Query/path-bearing operations

- [ ] `glob("src/**/*.py")` in root-local mode anchors at the working directory and emits canonical host-absolute result paths.
- [ ] `glob("/Users/claygendron/Git/Repos/grover/src/**/*.py")` matches the same files as the equivalent relative form.
- [ ] `grep`, `tree`, and `ls` use the same path interpretation rules for roots/filters.
- [ ] Search or graph results originating from mounted filesystems still render as canonical host-absolute paths with no synthetic mount-only path shape.

### Metadata alignment

- [ ] `meta_root("/Users/claygendron/Git/Repos/grover/src/auth.py") == "/.vfs/Users/claygendron/Git/Repos/grover/src/auth.py"`.
- [ ] Relative ordinary input resolves to the same absolute canonical path before metadata helpers derive `/.vfs/...` paths.

### Boundary discipline

- [ ] Relative resolution is performed through one explicit working-directory seam rather than by direct `os.getcwd()` calls in individual backends.
- [ ] Existing non-root-router tests continue to pass, proving this mode is additive rather than a silent global semantic rewrite.

## Test Plan

### New behavioral tests

- **`test_root_local_relative_read_matches_absolute_read`** — same target via relative and absolute input yields the same canonical path.
- **`test_root_local_write_and_delete_accept_relative_inputs`** — mutation APIs honor the same resolution rules as read APIs.
- **`test_root_local_results_always_emit_absolute_paths`** — no relative `Entry.path` leakage.
- **`test_absolute_multi_segment_mount_routing`** — mount at a full host path and verify dispatch.
- **`test_longest_prefix_routing_for_nested_absolute_mounts`** — deeper absolute mount wins.
- **`test_relative_path_enters_absolute_mount_after_resolution`** — relative input resolves first, then routes.
- **`test_shadow_filter_uses_absolute_mount_prefixes`** — self results under mounted host-absolute prefixes are excluded.
- **`test_glob_relative_and_absolute_forms_match_same_files`** — canonical absolute outputs from both spellings.
- **`test_explicit_working_directory_overrides_process_cwd`** — proves the path contract does not depend on ambient process state.
- **`test_metadata_root_for_host_absolute_path`** — Story 002 helper output matches the new host-absolute path contract.

### Regression tests that must still pass

- current routing tests for non-root-router setups
- current path normalization tests outside root-local mode
- current Story 002 metadata-path tests, updated only where the new host-absolute examples are intentionally covered

## Dependencies and Sequencing

This story is not first in the queue. It depends on earlier foundation work.

1. **Root-local mode must exist.** The codebase currently centers on VFS-style absolute paths and mounted routers. A real root-owned `LocalFileSystem` mode has to land first.
2. **Path normalization must split into two phases.**
   - user-input resolution (`relative -> absolute using working_dir`)
   - canonical path normalization (`collapse .`, `..`, slashes, Unicode)
3. **Mount-path validation must stop assuming single-segment names.** Absolute multi-segment prefixes are required.
4. **`LocalFileSystem` boundary/security rules need their own story.** Current docs describe `workspace_dir` as a hard path boundary. Root-local host-path mode may keep, broaden, or replace that boundary, but that policy decision should not be hidden inside this story.
5. **Query/parser adapters need the same canonicalization seam.** CLI and library entry points must not diverge on how relative paths are interpreted.

## References

- [`src/vfs/base.py`](../../../src/vfs/base.py) — current router and single-segment mount assumptions
- [`src/vfs/paths.py`](../../../src/vfs/paths.py) — current normalization behavior
- [`src/vfs/routing.py`](../../../src/vfs/routing.py) — current mount rewrite helpers
- [Story 002](../../002-posix-aligned-sidecar-namespace/spec.md) — `/.vfs/.../__meta__/...` metadata contract that this story must compose with
- [`docs/internals/fs.md`](../../../docs/internals/fs.md) — current `LocalFileSystem` path-security notes tied to `workspace_dir`

## Open Questions

1. Should root-local mode expose the whole host `/` namespace, or a configured absolute root prefix that still uses host-absolute canonical paths within that prefix?
2. Where should the working directory live: router state, per-request context, CLI session state, or all three with one canonical source of truth?
3. Do we want initial relative-path support only for ordinary file/directory paths, or also for directly typed metadata paths under `/.vfs/...`?
4. Should root-local mode be an explicit constructor/factory mode only, or can an existing `LocalFileSystem` become root-local automatically when used as the top-level filesystem?
