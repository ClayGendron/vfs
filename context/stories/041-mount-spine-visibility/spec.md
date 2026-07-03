# 041 — Mount-Spine Visibility: the Namespace Is Discoverable Top-Down

- **Status:** draft
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** feature (router namespace semantics) + fix (silent partial
  scope coverage)
- **Depends on:** 036 (router verb surface), 037 (single result channel),
  040 (terminal gate — spine targets run the same gate; land 040 first)
- **Enables:** agent-facing MCP exposure (an agent can start at `/` and
  walk the namespace), the client facade port (a facade over a pure
  router finally has a listable root)

## Intent

**Decided policy: `ls("/")` returns every entry stored at the root plus a
row for every filesystem mounted there.** Generalized: the paths a router
owns *by virtue of its mount table* — call them the **spine**: `/` plus
every proper ancestor of every mount path — are real, visible directories.
`ls`/`stat`/`tree` answer on them, and a scoped fan-out whose scope lands
on the spine expands across the mounts beneath it.

Today the spine is invisible. The docstring says "the filesystem object
itself owns `/`" (`base2.py:3-4`), but every verb addressed at `/` or a
mount ancestor dies in the `fs is self and not self._storage` routability
gate. An agent handed this namespace cannot do the first thing every agent
does: list the root and walk down. Unscoped fan-out works; addressing does
not.

## Why — verified failures

Reproduced against `base2.py` at `06cf551` (`repro.py` in this folder).

### The spine is unroutable on a pure router

Mounts at `/data/a` and `/data/b` on a storageless router:

```text
ls('/')                  FAILED  No mount found for path: /
stat('/data')            FAILED  No mount found for path: /data
tree('/')                FAILED  No mount found for path: /
grep scoped to '/data'   FAILED  No mount found for path: /data
grep unscoped            success rows=['/data/a/x.txt', '/data/b/y.txt']
```

### Scoped fan-out silently omits mounts under the scope

Worse than the error: on a *storage* root holding `/data/local.txt` with a
mount at `/data/a`, the scope resolves to self-storage and dispatches only
there —

```text
grep unscoped            success rows=['/data/a/inside.txt', '/data/local.txt']
grep scoped to '/data'   success rows=['/data/local.txt']
```

Narrowing a scope silently shrinks coverage. It looks like an answer; it
is a partial one, with no error and no marker. Every fan-out verb (`glob`,
`grep`, `glean`) has this shape.

### The defect recurses: a mid-tree router can't answer its own root

A pure router mounted as an intermediate node cannot answer `stat` of its
own mount point — the parent routes rel `/` into it, and the child hits
the same gate one level down:

```text
outer.stat('/hub')       FAILED  No mount found for path: /
outer.ls('/hub')         FAILED  No mount found for path: /
```

(Note the message also leaks the child-local `/` instead of `/hub` — the
router-side-path rule from 040 D2 covers the structured field; the spine
fix makes the failure disappear entirely.)

This recursion is also the key to the design: give every node an answer
for its *own* root and spine, and mount-point queries compose for free —
no parent ever needs to speak for a child.

## Design

### D0 — vocabulary and the one helper

```
spine(fs) = { "/" } ∪ { proper ancestors of every path in fs._mounts }
```

Spine membership and children derive from the existing sorted mount table
— no new state:

```python
def _spine_children(self, rel: Path) -> dict[str, VirtualFileSystem | None]:
    """Immediate child segments of *rel* implied by the mount table.

    Maps segment → mounted filesystem when the child IS a mount point,
    or → None when it is an intermediate spine directory (a mount lies
    deeper). Empty when *rel* is not on the spine.
    """
```

A path is on the spine iff it is `/` or `_spine_children` is non-empty
for it. Mount points themselves are *not* spine paths — they already
route into their mount (rel `/`), which D2 makes answerable.

### D1 — `ls` on a spine path: storage rows ∪ synthesized rows

`_route_single("ls", ...)` gains a spine branch when the terminal is
`self`: instead of failing routability, compose

- **storage rows** — the local impl's `ls` answer, when `self._storage`
  (a storage root can hold real entries beside its mounts, e.g.
  `/data/local.txt` next to the mount `/data/a`);
- **synthesized rows** — one per spine child: a mount-point child yields
  `Observation(path=child, kind="directory", description=mount.description)`;
  an intermediate child yields a bare directory row.

Merged `storage | synthesized` — left wins. Collisions are safe by
construction: a mount point cannot exist in storage (the mountability
invariant, `_is_path_mountable`), and an intermediate that also exists in
storage is the same directory, merged losslessly.

Synthesis is **local-only**: mount rows come from the mount table and the
mounted object's own constructor metadata (`name`/`title`/`description`),
never a wire call — `ls("/")` stays one local dispatch even over remote
mounts.

Two behavior changes to state plainly:

- `ls("/")` on an empty pure router returns **success with zero rows**
  (today: `not_found`). The root always exists.
- `ls` on a non-spine, non-storage path keeps today's `not_found`.

### D2 — `stat` on a spine path: the synthesized directory row

`stat` of `/` or any spine path returns the one synthesized directory
row. This is the recursion base the tree stands on: since *every* node
now answers `stat("/")`, a parent's `stat("/hub")` — which routes rel `/`
into the child — composes with no parent-side special case. The same
composition makes `ls` of a pure-router mount point work (repro case 3).

### D3 — `tree` on a spine path: skeleton + budgeted descent

`tree(P, max_depth)` where `P` is on the spine returns the spine skeleton
under `P` (within depth), the storage subtree (when storage), and each
mount at distance `s` segments below `P` dispatched as
`tree("/", max_depth - s)` — skipped when the remaining budget is `<= 0`,
unlimited when `max_depth is None`. Results rebase and merge as in any
fan-out; a child's own root row lands on the mount-point path and merges
left-wins with the skeleton row.

### D4 — scoped fan-out expands across the spine

In `_route_fanout`'s scoped branch, a scope path resolving to `(self,
rel)` where `rel` is on the spine (or `/`) expands to:

- self-storage scoped to `rel`, when `self._storage`;
- every mount strictly under `rel`, dispatched **unscoped** (the scope
  covers the whole mount), in mount-table order.

Capability semantics follow the *unscoped* rule for expanded targets —
silent skip when `capabilities()` lacks the op. The caller named a
region, not a terminal; one incapable catalog under `/data` must not fail
the query. A scope that resolves *inside* a mount keeps today's explicit
`unsupported` error — there the caller named the terminal.

Corollary, pinned by test: `grep(pattern, paths=("/",))` ≡
`grep(pattern)`.

This D also *fixes* the silent-omission defect: the storage-root scope
now reaches the mounts beneath it.

### D5 — grouped reads over spine rows round-trip

Chaining is the core result idiom (`results2.py` docstring), and D1's
output feeds straight back in: `stat(observations=(await fs.ls("/")).observations)`
must not die on the mount-ancestor rows it was just handed. In grouped
dispatch for the read verbs (`ls`/`stat`/`tree`), observations whose path
is on the spine peel off into a synthesized group answered locally;
everything else groups and dispatches as today. Mutating verbs are
unchanged — a spine path is not a mutation target, and their existing
classified failures stand.

### D6 — spine paths are directories, for every other verb

**Decided policy: a spine path is an ordinary directory, not a special
type.** The namespace never invents a "mount" entity kind: an agent
learns *where* the mounts are and *what* they hold from the operator —
developers inform the agent up front in the system prompt (a future
helper will compose that message part from the mount table and
descriptions; see Out of scope). The namespace itself just behaves like
a filesystem.

Consequence: a non-listing single-path verb addressed at a spine path
fails exactly the way it fails on a stored directory — `wrong_kind`,
never `not_found`:

```text
read("/data")   → wrong_kind  "Is a directory: /data"   (today: not_found)
graph("/data")  → wrong_kind                            (today: not_found)
run("/data")    → wrong_kind                            (today: not_found)
```

The classification surfaces at the routability step: the spine branch
replaces today's `not_found` with `wrong_kind` for these verbs, so the
capability and permission gates are untouched and gate order (040) is
unchanged. Mutating verbs keep their existing earlier rejections
(mutation resolution, permission); a mutation that reaches routability
on a spine path classifies `wrong_kind` the same way.

An exact mount *point* (`read("/data")` when `/data` itself is the
mount) gets the same answer by composition, not by parent-side special
casing: the parent routes rel `/` into the mount, and the child's own
D6 classifies its root as a directory — one more place the
every-node-answers-its-own-spine recursion (D2) pays off.

## Out of scope

- **Mutations addressed at spine paths** beyond the `wrong_kind`
  classification in D6. Writing a *file* over a spine directory is
  already largely excluded by the kind grammar (an extensionless leaf
  parses as a directory), and an exact-mount-point write routes into the
  child where the root-mutation check rejects it. A write-time guard
  against mount-table shadowing, if ever needed, is its own story.
- **The mount-manifest helper** — a method composing the mount table
  (paths + descriptions) into an agent-facing prose block for the
  operator's system prompt. Deliberately future work: D6 depends on the
  *doctrine* (discovery lives in the prompt, not in a namespace entity
  kind), not on the helper existing yet.
- **Mount-point rows carrying live child state** (entry counts, health).
  Synthesis is static constructor metadata only.
- The `add_mount` TOCTOU race — separate story; this one does not touch
  the mount-table mutation path.
- Old `base.py` / `client.py`.

## Test plan

1. **The acceptance criterion, verbatim:** a storage root with entries at
   `/` and filesystems mounted at `/a` and `/b/c` — `ls("/")` returns the
   storage entries, the mount-point row `/a` (with the mount's
   description), and the intermediate row `/b`. Repro case 1 becomes the
   pure-router regression.
2. **Empty root:** `ls("/")` on a mountless pure router → success, zero
   rows; `ls("/ghost")` → `not_found` unchanged.
3. **Deep spine:** mounts at `/data/a` and `/data/b` — `ls("/data")`
   returns both mount rows; `stat("/data")` returns the directory row.
4. **Composition:** repro case 3 — `stat`/`ls` of a pure-router mount
   point answered by the child's own spine, no parent special case
   (assert via a spy that the parent dispatched across the boundary).
5. **Tree budgeting:** `tree("/", max_depth=1)` shows spine children
   only; depth `s` mounts receive `max_depth - s`; budget `<= 0` skips
   the child dispatch but keeps the skeleton row; `None` descends fully.
6. **Scope expansion:** repro case 2 becomes the regression — scoped
   `/data` equals unscoped when the scope covers everything; `paths=("/",)`
   ≡ unscoped for every fan-out verb; an incapable mount under an
   expanded scope is skipped silently; a scope inside a mount still
   errors `unsupported`; a scope at an exact mount point routes into the
   mount unchanged.
7. **Chaining:** `stat(observations=ls("/").observations)` succeeds,
   spine rows answered synthetically, mount rows dispatched.
8. **Merge precedence:** a storage directory that coincides with an
   intermediate spine row survives left-wins with its stored fields;
   synthesized description fills only where storage left null.
9. **Directory semantics (D6):** `read`/`graph`/`run` on `/`, an
   intermediate spine path, and a deep spine path all fail `wrong_kind`
   with the router-side path in the structured `path` field; the same
   verbs on a genuinely absent path keep `not_found` — the two kinds
   never blur.
10. **No double-cover leakage:** `tree` on a *storage* spine path where
    the storage impl also returns rows under the mount ancestors it
    stores — left-wins merge absorbs the overlap, and no row inside a
    mount's territory ever originates from parent storage (those paths
    route away before reaching the impl; this test pins that argument
    as executable fact rather than prose).

## Open questions

None. Mount-point rows expose no `title` — decided: no new
`Observation` fields; `description` is enough for discovery (revisit
only if agent evals demand more, and note 044's rights-visibility
surface rides the same rows under the same constraint). The
storage-double-cover concern is now test-plan item 10.
