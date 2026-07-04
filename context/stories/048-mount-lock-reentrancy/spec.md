# 048 — Re-entrant Mount Mutation Fails Loud, Not Silent

- **Status:** draft
- **Date:** 2026-07-04
- **Owner:** Clay Gendron
- **Kind:** fix (a silent hang becomes an immediate error) — small
  story, one guard plus tests
- **Depends on:** 042 (the non-reentrant `_mount_lock` held across the
  mountability probe — the mechanism this story hardens)
- **Enables:** the `DatabaseFileSystem` port (the first real storage
  backend is where an accidental re-entrant shape becomes likely)

## Intent

The mount lock from 042 is a plain `asyncio.Lock`: not reentrant, and
held across the awaited mountability probe. The probe self-dispatches
through the public `stat` — a read path that takes no lock — so the
design is self-deadlock-free **as long as the storage impl stays a
read**. A storage `_call_local_impl` that calls back into a mutator
during its own probe re-acquires a lock its task already holds and
hangs forever, with no error, no timeout, and no traceback.

That shape is out of contract — an impl mutating the mount table from
inside its own stat is a design smell — but it is plausible by
accident, and the failure mode is the worst one available. Two shapes,
both verified against `base2.py` post-042 (`repro.py` in this folder):

1. **Self re-entrancy:** an "auto-mount on first access" backend whose
   impl calls `self.add_mount(...)` mid-probe deadlocks on its own
   lock.
2. **Ancestor re-entrancy:** a delegated add descends root→child
   holding root's lock; the child's impl calls `root.add_mount(...)`
   and re-enters the lock the same task holds up the stack.

This story turns both into an immediate `RuntimeError` naming the
misuse, so the first accidental lazy-mount backend fails its test run
loudly instead of hanging CI.

## Design

Track the holding task. On acquire, record `asyncio.current_task()`;
on release, clear it. A mutator entered while the recorded holder *is
the current task* raises before touching the lock:

```python
# in each mutator, before `async with self._mount_lock`
if self._mount_lock_owner is asyncio.current_task():
    msg = (
        "Re-entrant mount mutation: a storage impl called add_mount/"
        "remove_mount/close during a mount operation it is part of"
    )
    raise RuntimeError(msg)
```

The check-and-set is synchronous around the `async with`, so it is
race-free on a single event loop. The ancestor shape is caught by the
same guard firing on the *ancestor's* re-entered mutator, since the
owner task matches there too. Distinct tasks are unaffected — they
queue on the lock exactly as 042 intends.

Alternatives considered:

- **Docstring-only contract note** — cheapest, but the failure stays a
  silent hang; rejected as the sole measure (a sentence on the class
  docstring is still worth adding alongside the guard).
- **A reentrant lock** — rejected. Letting the nested mutation proceed
  mid-probe would interleave a table mutation inside a half-finished
  `add_mount`, exactly the state 042 exists to forbid. The nested call
  is wrong; the fix is to say so.

## Out of scope

- Re-entrancy across *different* tasks (already correct: they queue).
- Cross-thread / multi-loop use (out of contract per 042 D4).
- Any change to the probe's read-path self-dispatch, which remains
  lock-free and legal.

## Test plan

Both repro shapes become tests asserting the loud failure, not the
hang (each wrapped in a short `asyncio.wait_for` so a regression fails
fast instead of hanging the suite):

1. **Self re-entrancy:** an impl calling `self.add_mount` mid-probe →
   `RuntimeError` naming re-entrant mount mutation; the outer add
   fails; the lock is released; the table is unchanged.
2. **Ancestor re-entrancy:** the delegated shape → same error from the
   ancestor's guard; both tables unchanged.
3. **Negative control:** two *tasks* contending on one instance still
   serialize normally (no false positive from the owner check).
4. **Read-path unaffected:** the probe's own `stat` self-dispatch under
   the held lock still completes (pins that the guard sits on mutators
   only).

## Open questions

- None. Land it with, or just ahead of, the `DatabaseFileSystem` port.
