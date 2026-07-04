# 042 — Serialize Mount-Table Mutation: a Lock Plus a Commit Gate

- **Status:** implemented (commit 5f84052, 2026-07-04)
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** fix (TOCTOU races that corrupt the mount-tree invariants)
- **Depends on:** 00116ae (`_is_path_mountable` composed from the awaited
  public `stat` — the suspension that opens the window), 037 (single
  result channel — the probe's failure semantics)
- **Enables:** concurrent namespace assembly (an app wiring mounts in
  parallel at startup, agents adding mounts mid-session), 041 (the spine
  derives from a table whose invariants actually hold)

## Intent

`add_mount` is check-then-act with an `await` in between: every guard —
duplicate path, deeper-mount ownership, single parent, cycle — runs
*before* the awaited mountability probe (`base2.py:169`), and the commit
(`base2.py:173-175`) runs after. On a storage-backed router the probe is
a real backend round-trip, so the event loop is free to run a second
mutation between check and use. Every fact the guards established can be
stale at commit time.

This story makes mount-table mutation safe under concurrency with two
complementary mechanisms:

- **A per-instance `asyncio.Lock`** serializing the mutators
  (`add_mount`, `remove_mount`, `close`) — closes every race over facts
  derived from *this* instance's table.
- **A synchronous commit gate** re-checking the *cross-instance* facts
  (the incoming filesystem's `_parent`, the cycle check) immediately
  before commit — closes the races no lock of ours can see, because the
  contested state lives on the other filesystem.

The division is exact: the lock protects our table; the commit gate
re-proves what we asserted about *theirs*.

## Why — verified failures

Reproduced against `base2.py` at `06cf551` (`repro.py` in this folder;
all three become regression tests). All three interleavings need only
two concurrent `add_mount` calls on a storage root — no exotic timing.

### 1. Same path, same parent: silent overwrite + permanent orphan

```text
errors raised: []                     ← both calls "succeeded"
mount table holds: c2                 ← c2 silently overwrote c1
orphaned (parent set, in no table): ['c1']
```

Both tasks pass `_match_mount` while the path is still free, both
suspend in the probe, both commit. The dict assignment overwrites; `c1`
is left with `_parent` set and membership in no table — every future
`add_mount(c1, ...)` anywhere raises "already mounted elsewhere"
(`base2.py:145-147`), with no public way back.

### 2. Same child, two parents: the mount graph stops being a tree

```text
errors raised: []
in p1 table: True | in p2 table: True | child._parent: p2
```

Both parents verify `child._parent is None`, both suspend, both commit.
The child is now reachable from two roots while claiming one parent —
`_root()`, `_reachable_ids()`, and the cycle rejection all reason from
invariants that no longer hold. **A per-instance lock cannot close this
one**: p1 and p2 hold different locks; the contested fact is on `child`.

### 3. Ancestor and descendant paths: ownership check defeated

```text
errors raised: []
table (both at one level — deeper-mount check defeated): ['/a', '/a/b']
```

`/a`'s guard ("rejected when a deeper mount sits beneath",
`base2.py:165-168`) ran while `/a/b` was uncommitted, and vice versa.
Both land in one table — exactly the shadowing arrangement the
reverse-order rejection exists to prevent, and a state `add_mount` could
never produce sequentially.

The window is real in every production shape (a `DatabaseFileSystem`
root — the probe genuinely suspends) and absent only on a pure router,
where `_is_path_mountable` returns without yielding, which is why the
suite has never seen these. `close()` has the same exposure in a milder
form: a mount added during its await loop is cleared from the table
without its `_parent` being reset — the same orphan as race 1.

## Design

### D1 — one per-instance lock over the mutators

```python
# __init__
self._mount_lock = asyncio.Lock()
```

`add_mount`, `remove_mount`, and `close` wrap their bodies in
`async with self._mount_lock`. Everything each guard reads from
`self._mounts` is then stable through its own commit — races 1 and 3
become ordinary sequential outcomes (first wins; second gets the
existing classified rejection: "Mount already exists", "owned by a
deeper mount").

**Readers never take the lock.** Routing reads (`_match_mount`,
`_resolve_terminal`, fan-out target collection) are synchronous — they
complete without a suspension point, so on a single event loop they
always observe a consistent table. The lock is a mutator-serialization
device, not a reader guard; this keeps the dispatch hot path untouched.

**Deadlock argument.** The lock is not reentrant, so the rule is:
a mutator may acquire only locks *below* itself. All three mutators
comply — delegation (`mount_fs.add_mount(...)`,
`mount_fs.remove_mount(...)`) and `close()`'s child loop descend
existing mount edges, so locks are always acquired parent-before-child
along a tree. A partial order admits no cycle, so no deadlock. The
incoming `filesystem`'s lock is never acquired at all (its fields are
only read/written synchronously), which is what keeps mutual
`a.add_mount(x)` / `b.add_mount(y)` calls on disjoint trees fully
independent. The mountability probe self-dispatches through the public
`stat` — a read path that takes no lock — so holding the lock across
the probe cannot self-deadlock.

### D2 — the commit gate re-proves the cross-instance facts

The lock cannot protect facts about the *incoming* filesystem (race 2:
its `_parent`; the mirror case: its subtree growing to reach our root
during the probe). Those are re-checked **synchronously, immediately
before commit** — no suspension between re-check and the three commit
lines, so on a single event loop the pair is atomic:

```python
# after the probe, still under the lock — the commit gate
if filesystem._parent is not None:
    msg = f"Cannot mount at {mount_path}: that filesystem is already mounted elsewhere"
    raise ValueError(msg)
if id(self._root()) in filesystem._reachable_ids():
    msg = (
        f"Mounting at {mount_path} would create a cycle: "
        "that filesystem already contains this namespace's root"
    )
    raise ValueError(msg)

filesystem._parent = self
self._mounts[mount_path] = filesystem
self._rebuild_sorted_mounts()
```

The pre-await checks **stay** — failing fast before a wasted backend
round-trip is worth two cheap synchronous walks, and the early failure
carries the same messages. Implementation may hoist gate-plus-commit
into a small `_commit_mount(filesystem, mount_path)` helper so the
"no await between re-check and commit" property is a fact about one
function body rather than a discipline across a long method.

### D3 — `close()` under the lock, and the orphan it fixes

`close()` acquiring the lock serializes it against `add_mount`, fixing
its variant of race 1: today a mount added during the child-close loop
is removed by the final `self._mounts.clear()` without its `_parent`
being reset. Under the lock, the add either completes before the close
(and the new mount is closed with the rest) or begins after the table
is cleared. Whether mounting into a *closed* filesystem should itself
be rejected is a lifecycle question this story leaves alone — the
invariant defended here is only that no filesystem is ever orphaned.

*(Amended 2026-07-04, post-landing pressure test: the loop originally
reset each child's `_parent` as it went and cleared the table only at
the end. `CancelledError` is a `BaseException`, so an ordinary
`asyncio.wait_for(root.close(), ...)` timing out mid-loop escaped the
per-child `except Exception` and left already-closed children reset
but still in the table — a **reverse orphan** (`_parent is None`,
table membership intact) that passes every `add_mount` guard and can
then be mounted into a second tree, the exact double-parent this story
exists to prevent. `close()` now detaches each child synchronously
after its close (pop + `_parent` reset + rebuild), so a cancellation
splits the loop cleanly into fully-detached and fully-attached
children, and a second `close()` finishes the job. Pinned by
`test_cancelled_close_leaves_no_half_detached_child`. Pre-existing
exposure, not introduced by this story's lock.)*

### D4 — scope note: single event loop, by contract

All guarantees are event-loop-local, matching the codebase's existing
concurrency model (asyncio throughout; no cross-thread mutation
anywhere). Sharing one `VirtualFileSystem` across threads or loops is
out of contract — worth one sentence on the class docstring, not
machinery.

## Out of scope

- **In-flight dispatch vs. `remove_mount`/`close`.** A verb already
  routed to a mount completes against the detached object and returns a
  valid `Result` — acceptable and unchanged. Draining or cancelling
  in-flight work is a lifecycle story.
- **Rejecting mounts into a closed filesystem** (see D3).
- **Cross-thread / multi-loop safety** (see D4).
- The mountability probe's semantics — unchanged from 00116ae/037; this
  story only changes what may interleave around it.

## Test plan

All three repro races become tests, with the suspending stat fake as the
fixture; each asserts both the *outcome* and the *invariants*:

1. **Same path:** exactly one of two concurrent `add_mount` calls
   succeeds; the loser raises "Mount already exists"; the loser's
   `_parent` is `None` (no orphan) and it mounts cleanly elsewhere
   afterward.
2. **Same child, two parents:** one winner; the loser raises "already
   mounted elsewhere"; the child appears in exactly one table and
   `_parent` agrees with it.
3. **Ancestor/descendant:** whichever order the loop resumes them, the
   table never holds both `/a` and `/a/b` at one level — the loser gets
   the existing classified rejection for its resume order.
4. **Cycle gate:** the D2 mirror case — concurrently mounting `F` under
   `R` and `R` under `F` — ends with exactly one edge and no
   parent-chain cycle (`_root()` terminates by invariant, not by its
   visited guard).
5. **Close vs. add:** `close()` racing `add_mount` leaves no filesystem
   with `_parent` set outside any table, in either interleaving.
6. **No reader stall:** dispatch (`read`/`grep`) through an existing
   mount proceeds while another task sits inside `add_mount`'s probe —
   pins that readers take no lock.
7. **Delegated depth:** concurrent adds through delegation
   (`root.add_mount(fs, "/data/deep")` racing a direct add on the
   `/data` mount) serialize per owner without deadlock — exercises the
   parent→child acquisition order.

## Open questions

- None. (The lifecycle questions surfaced here — closed-filesystem
  mounts, in-flight drain — are noted out of scope and should become
  their own story when the `DatabaseFileSystem` port makes them
  concrete.)
