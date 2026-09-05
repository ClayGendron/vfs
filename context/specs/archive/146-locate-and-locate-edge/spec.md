# 146 — `locate` and `locate_edge`: where a path lives, and whether two paths can share an edge

- **Status:** landed and archived 2026-09-05 (see the landing note) —
  drafted the same day from Clay's ask: a user of the router sees one
  namespace, not the storages behind it, and needs a way to learn
  where a path lands — and, for an edge, whether its two endpoints
  land on the same storage — without running anything against a
  database.
- **Born from:** the `cross_mount` refusal in `mkedge` (ADR 018's
  no-cross-mount-edges rule, the EXDEV posture) and the mount table
  `mounts()` already exposes; the prior-art survey below.
- **Date:** 2026-09-05
- **Owner:** Clay Gendron
- **Kind:** two synchronous inspection methods on
  `VirtualFileSystem` and two frozen, JSON-native row types beside
  `MountInfo`. No storage I/O, no lock, no schema or verb change.
- **Depends on:** the router's longest-prefix resolution
  (`_resolve_terminal`), `Path` gating (`resolve_path`).
- **Relates to:** `mounts()` (the table these read), `mkedge` (whose
  `cross_mount` refusal `locate_edge` predicts), spec 137 (cross-mount
  merge — the read side of the same boundary).

## Intent

Every path resolves through one mount table to exactly one binding,
by longest prefix, with the root storage as the fallback. `mkedge`
does that resolution for both endpoints and refuses `cross_mount`
when they land on different bindings. Nothing public exposes the
resolution itself: a caller can list the table (`mounts()`) but cannot
ask "which row owns this path" or "would these two share a storage"
without attempting the write. Two helpers close that gap, reading only
the table, sharing the router's own resolution so their answer and
the verb's refusal come from one place and cannot disagree.

## Prior art

- **POSIX** answers "same filesystem?" by comparing `st_dev` from
  `stat` on both paths; `rename` across devices fails with `EXDEV`
  (`pjdfstest/tests/rename/15.t`). The check is a lookup and the
  failure is a classified answer.
- **Linux `findmnt --target PATH` / `df PATH`** walk the mount table
  for a path and print the mount point and source — table only, no
  I/O on the target.
- **Plan 9 `ns(1)`** prints the mount table as replayable commands;
  `mounts()` already is that.
- **pyfilesystem2 `MountFS`**: private `_delegate(path)` returns the
  mounted filesystem and the path in its coordinates (the shape wanted
  here); public `desc(path)` renders "path on fs" but calls `exists`
  first, which is the I/O these helpers must not do.
- **Mirage `explain`**: a dry run of the gate a command would pass,
  sharing the gate's code so the explanation and the refusal cannot
  drift — the design rule adopted here.

## Decided semantics

1. **`locate(path) -> Location`** — one path, where it lives:

   ```python
   class Location(NamedTuple):
       path: str          # the caller's path, canonical
       mount: str         # the bind path that owns it
       storage_name: str
       storage_type: str
       storage_path: str  # the path in the storage's own coordinates
   ```

   Longest-prefix resolution, the deepest binding for a nested mount,
   the root binding as fallback — `_resolve_terminal`, the router's
   own call. `storage_path` is the terminal's `rel`.

2. **`locate_edge(source, target) -> EdgeLocation`** — two paths,
   whether an edge between them is possible:

   ```python
   class EdgeLocation(NamedTuple):
       source: Location
       target: Location
       same_storage: bool
       reason: str | None  # a sentence only when same_storage is False
   ```

   `same_storage` is the bindings' bind paths being equal — the exact
   test `mkedge` applies before it dispatches. `reason` names both
   mounts when they differ; it is prose for a person, never a
   classified error, because nothing failed.

3. **Table facts only.** No storage I/O, no mount lock (one dict
   snapshot, as `mounts()` reads), no permission, capability,
   existence or liveness check. The answer does not depend on a user
   id. A "would `mkedge` succeed" dry run that layers the gates on top
   is a separate future method, not this one.

4. **Rows, not envelopes.** Both types are frozen `NamedTuple`s of
   JSON fixed points, like `MountInfo`; `json.dumps(row._asdict())`
   always succeeds. A `Result` is for something that ran.

5. **The two ways there is no answer raise `ValueError`**, as `Path()`
   itself does: a structurally invalid path (null byte, control
   character, over-long segment) and a closed filesystem (the table
   is empty — `mounts()` returns `()` there; a lookup has no row to
   return). A non-canonical path is canonicalised, not refused, so
   `locate("/a/../b")` reports `/b`.

6. **Reserved paths route like any other.** The trash and the
   metadata scope land on whichever binding owns their prefix; the
   helpers say where, and nothing about whether a verb would accept
   them.

7. **`locate_edge` is `locate` twice plus the verdict.** The one-path
   method is the building block; the two-path method adds only the
   comparison and the sentence.

## Scope

In: the two types, the two methods, a row in `docs/api.md`, tests
that pin `locate_edge` against `mkedge`'s own `cross_mount` refusal on
a two-mount fixture. Out: permission or capability dry runs, a
rendering helper, MCP exposure (a later tool can wrap these
unchanged).

## Landing criteria

- `scripts/ci.sh 3.13` green, 100 % coverage held.
- Tests: root fallback; a nested mount reports the deepest binding and
  the residual path; `same_storage` agrees with `mkedge`'s refusal on
  the same pair; a canonicalised path; the two `ValueError` cases;
  rows are JSON-native.

## Landing note (2026-09-05)

`Location` and `EdgeLocation` sit beside `MountInfo` in `vfs/base.py`;
`locate` and `locate_edge` sit beside `mounts()`, both built on one
private `_locate_terminal` that gates the caller path through
`resolve_path` and resolves it through `_match_mount` — the same
longest-prefix table read the verbs use. Tests in
`tests/base/test_mount_admin.py`: the root fallback; a nested mount
reporting the deepest binding, the storage-local path (`/` for the
bind site itself) and a canonicalised input, with the storages'
recorded calls proving nothing was asked of them; `locate_edge`
agreeing with `mkedge`'s `cross_mount` refusal and its success on the
same pairs; the two `ValueError` cases; JSON round-trips. Decisions
Clay left open were taken as proposed: the names `locate` /
`locate_edge`, and raising `ValueError` on an invalid path rather
than reporting it in the row. `docs/api.md` predates the rebuild and
lists none of the router's table methods, so no row was added there.
Gates: `scripts/ci.sh 3.13` green, 3,205 passed, 100 % coverage.
