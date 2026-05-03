# 019 — Union mounts and shadow resolution

- **Status:** draft
- **Date:** 2026-05-02
- **Owner:** Clay Gendron
- **Kind:** feature · namespace · search/graph correctness
- **Depends on:** 015, 016, 017, 018
- **Enables:** 023 (per-session unions are the highest-leverage use)

## Intent

Allow more than one filesystem to be mounted at the same path,
with flags controlling order and write eligibility. The classic
use case: a writable scratch overlay on top of a shared
read-only corpus.

This story also resolves the **shadow problem** the user raised:
when a file in scratch shadows a file of the same name in the
read-only base, search and graph traversal of the base alone
might still surface the shadowed file's path — and the agent
that asks for that path through the union sees the scratch
version, not the one search returned. The whole story has to
make these two views consistent.

## Why

- **Layering.** "Writable private over read-only shared" is the
  natural shape for many workflows: per-user scratch, branch
  overlays, snapshot-on-top-of-live.
- **Plan 9 fidelity.** Union directories are the namespace
  paper's headline idea. We're keeping faith with the model.
- **Shadow correctness.** Right now we have no opinion about what
  happens when two backends own the same path. Once unions exist,
  the question becomes mandatory; this story is where it gets
  answered.

## Scope

### In

1. **`MountFlag` activates beyond `REPL`.**
   ```python
   class MountFlag(IntFlag):
       REPL   = 0          # default: replace existing
       BEFORE = 1 << 0     # search this member first
       AFTER  = 1 << 1     # search after existing
       CREATE = 1 << 2     # this member receives create()
   ```

2. **`_mounts` becomes a dict of lists.**
   ```python
   self._mounts: dict[str, list[MountedFS]] = {}

   @dataclass(frozen=True)
   class MountedFS:
       fs: VirtualFileSystem
       flags: MountFlag
       permissions: PermissionMap
       added_at: float
   ```

3. **`add_mount(... flags=...)` honors flags.**
   - `REPL`: replace existing list.
   - `BEFORE`: prepend.
   - `AFTER`: append.
   - Combined with `CREATE`: union member is write-eligible.
   - Pure `BEFORE`/`AFTER` without `CREATE` requires the union to
     already have a `CREATE` member, otherwise reject with
     `MountError(UnionWithoutCreate)`.

4. **Read resolution walks the union.**
   - `_match_mount` returns the first member whose backend resolves
     the path. (For directories: union the listings.)
   - `read`/`stat` walk members in order, return on first hit.
   - `glob`/`grep`/`search` fan out to **every** member and merge.
     Each candidate carries `Detail.mount` to mark which member
     it came from.

5. **Write resolution finds first `CREATE`.**
   - `write`/`edit`/`mkdir`/`mkedge` find the first member with
     `CREATE` flag and dispatch there.
   - If no member has `CREATE`, return
     `MountError(UnionWithoutCreate)`.
   - This is the "promote-on-write" idiom from overlay
     filesystems: the first `CREATE` member receives the new
     file even if a non-create member would have served the read.

6. **Shadow resolution in dir listings.**
   - `ls /home` returns the union of all members' listings,
     deduplicated by name. **First-wins** ordering: if two
     members have the same filename, the higher-priority member's
     entry is what the listing shows.
   - Hidden entries (lower-priority members of a shadowed file)
     are not surfaced unless the caller asks for
     `expand_shadows=True` on `ls`/`glob`.

7. **Shadow resolution in search/graph.**
   This is the user's specific concern. The rule:
   > **Search, grep, and graph results returned through a union
   > resolve to the same path the agent would read.**

   Concretely, when a backend returns a candidate with path
   `/home/x.md`, and that path is shadowed by a higher-priority
   union member, the candidate is **dropped** — because the agent
   that calls `read("/home/x.md")` will not get this content.

   Two implementation paths:
   - **(a) Filter at the router:** after gathering all members'
     candidates, drop any whose path is shadowed by a
     higher-priority member.
   - **(b) Pass down a shadow set:** the router computes the set
     of paths the higher-priority members own (via a `glob` /
     `stat` round-trip), passes it to lower-priority members as
     a "skip these paths" filter.

   We pick **(a)** for simplicity — one extra router pass. (b)
   is an optimization for later if the dropped-results-rate is
   high.

8. **Per-candidate `mount` provenance.**
   `Detail` (and `Candidate.mount`) carry which union member
   produced the result. For a search across `[scratch, shared]`:
   - candidates from `scratch` get `mount: "/home(scratch)"`
   - candidates from `shared` get `mount: "/home(shared)"`

   Agents can branch on this. UI can display "(from your scratch)"
   vs "(from shared corpus)".

9. **MountInfo evolution.**
   `/.mounts/home/` becomes a directory with one subdirectory per
   member:
   ```
   /.mounts/home/
     0/                       (BEFORE | CREATE)
       backend  inproc://ScratchFS/0xdeadbeef
       flags    BEFORE|CREATE
     1/                       (AFTER)
       backend  database://shared
       flags    AFTER
   ```
   Index in the union becomes a directory name — readable and stable.

### Out

- **Cross-mount transactions across union members.** A write that
  spans the same union still hits a single backend (the first
  CREATE member). No coordinator.
- **Smart shadow resolution at the SQL level.** The router does
  it in Python. SQL-level coordination across heterogeneous
  backends is too hard for this story.
- **Search ranking that prefers higher-priority members.** Per-
  candidate `Detail.mount` is enough; ranking adjustments are
  story 022 (hybrid search across mounts).
- **Diff between members at the same path.** "What's in scratch
  that's not in shared?" is a useful tool but not core.
- **Materializing shadowed files into scratch on first edit.**
  A future story.

## Acceptance Criteria

1. **Three-member union resolves reads in order.** `BEFORE` member
   wins over default member wins over `AFTER` member. Test fixture.

2. **Create finds first `CREATE`.** When `BEFORE | CREATE` plus
   `AFTER` (no create), `write` lands in the BEFORE member; the
   AFTER member is untouched.

3. **No-create union rejects writes.** When all members have
   no `CREATE` flag, `write` returns
   `MountError(UnionWithoutCreate)`.

4. **`ls` deduplicates by name.** Test: scratch has `notes.md`,
   shared has `notes.md` and `intro.md`. `ls /home` returns two
   entries; `notes.md` shows scratch's content.

5. **`glob` deduplicates by path.** Same scenario, `glob("/home/*.md")`
   returns two candidates; the `notes.md` candidate is from scratch.

6. **`grep` skips shadowed files.** Pattern that matches inside
   the shared `notes.md` does not surface — because shadowed —
   but the same pattern matching scratch's `notes.md` does.

7. **Search drops shadowed candidates.** Vector or BM25 hit on
   a shadowed file is filtered before the merged result returns.

8. **`Detail.mount` includes union member identity.** Two
   candidates from the same path-prefix but different members
   carry distinguishable `mount` values.

9. **`/.mounts/<path>/` is a directory of members.** Each member
   has its own metadata files. `glob("/.mounts/home/**")` works.

10. **Cycle guard interacts with unions correctly.** A bind cycle
    through one union member raises `BindCycle` only when that
    member is reached during resolution.

11. **`expand_shadows=True` opt-in.** Setting this flag on
    `ls`/`glob` returns shadowed entries with explicit
    `Detail.shadowed_by` set. Off by default.

12. **No regression on single-member mounts.** All existing
    `add_mount(path, fs)` calls continue to behave as before
    (single-member union, REPL flag).

## Risks

- **Performance: shadow filtering is O(N members × M results).**
  Merge-and-dedup over fanout. Mitigation: most unions have 2
  members; the algorithmic cost is small. Watch the dropped-
  results rate; switch to (b) (skip-set push-down) if needed.

- **Search relevance with shadows dropped.** Dropping shadowed
  candidates may lose hits that *would have ranked highly* in the
  shared backend's BM25 / vector index. The user gets a
  consistent view (path = readable) but possibly a less-rich
  result set. Mitigation: agent receives `Detail.mount` so it
  knows the result came from a specific member; for cases where
  the agent wants "everything", `expand_shadows=True` exists.

- **Graph traversal correctness.** Edges in the shared backend
  pointing to a now-shadowed node still exist. When traversing,
  the router must rewrite the target to the shadowing member's
  qid (or refuse the edge). Coordination with story 021
  (cross-server edges) is required — this story declares the
  edges, story 021 makes them work across backends.

- **Write semantics for shadowed files.** Writing to
  `/home/notes.md` writes to the `CREATE` member, even if a
  lower-priority member already has a `notes.md`. That can
  surprise. Document with examples.

- **Unmount ordering.** Removing the BEFORE member
  reveals the AFTER member's contents. Shadowed-now-visible
  paths might confuse caches. `notifications/resources/updated`
  fires (from story 017) so subscribers can rebuild.

## Open Questions

1. **Should shadow filtering happen in `_match_mount` or as a
   post-pass after fanout?** Default: post-pass. `_match_mount`
   stays simple ("first member that resolves wins").

2. **Should write-to-shadowed produce a "promoted from shared"
   indicator?** Default: yes, in `Detail` provenance — the new
   file in scratch carries `Detail.promoted_from = "<shared mount>"`.

3. **How does `delete` on a union behave?** Default: deletes
   from the `CREATE` member only. If the file existed in a
   lower-priority member, it's now visible again ("promoted-to-
   delete is a no-op against the immutable base").

4. **Does the bind-cycle guard need to track union member index?**
   Default: yes. `(id(fs), rel, member_index)`.

## References

- `src/vfs/base.py:80-141` — mount table, `_match_mount`,
  `_resolve_terminal` (all need to handle list values)
- `src/vfs/base.py:1029` — `_exclude_mounted_paths` (related
  semantic for shadowing across mount holes; not the same thing
  as union shadowing)
- `src/vfs/results.py` — `Detail.mount` field becomes meaningful
- Plan 9 names paper — explicit on union directory create
  semantics
- `docs/plan9-mount-namespace-recommendations.html` — Rec 02
