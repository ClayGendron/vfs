# A grant can be aimed at a mount point

This spec is drafted and not yet reviewed. The decisions below were taken on 2026-11-17. The work is built on its own branch after the branch `public-names-follow-the-naming-rules` has landed.

## Terms

- **Mount point.** The path a mount is attached at, such as `/data`.
- **Covered directory.** The empty directory stored at the mount point. It is an ordinary entry in the storage of the mount above. For a mount at `/data` on the root, it is the entry `/data` in the root's storage.
- **Mounted root.** The root of the storage that is attached at the mount point. Its own path is `/`, and callers see it as `/data`.
- **Storage above.** The storage that holds the covered directory.
- **Mount right.** `read_write` at the covered directory. It is what `add_mount`, `remove_mount` and `update_mount` require.

## The problem

One path names two entries. `/data` is the covered directory in the storage above, and it is the mounted root in the mounted storage. Each storage keeps its own rights.

There is one permission model, not two. The covered directory is an ordinary entry with ordinary grants and an ordinary posture. A mount change is judged by those ordinary rights. The problem is only one of addressing.

- A mount change is judged on the covered directory. The kernel asks the storage above through `holds`.
- Every routed verb at `/data` goes to the mounted root. That includes `grant`, `revoke`, `grants` and `set_posture`.

So once a mount exists, no verb can reach the rights of its covered directory.

## Evidence

Executed on 2026-11-17 with an in-memory root, a mount at `/data`, and a spy on every storage method.

| Call at `/data` | Storage that answers | Its path |
|---|---|---|
| `stat`, `ls`, `mkdir`, `locate` | mounted storage | `/` |
| `ls("/")`, which lists the name `data` | storage above | `/` |
| `delete` | none, the kernel refuses with `busy` | |
| `grant`, `revoke`, `grants`, `set_posture` | mounted storage | `/` |
| `holds`, inside a mount change | storage above | `/data` |

Three consequences, all executed.

- After the mount, `grant("/data", "ada", "read_write")` succeeds, and `remove_mount("/data")` by ada is still refused.
- A grant made at `/data` before the mount cannot be revoked after it. `revoke("/data", "ada")` returns success with a warning that no such grant is held, and ada can still remove the mount.
- A caller granted only inside the mount does not see the name `data` in `ls("/")`, because the storage above decides whether the covered directory shows.

The only way left to change the mount right is a grant on a directory above the mount point, which reaches more than the one mount.

## Prior art

Each system judges a mount change on the covered directory and sends ordinary access to the mounted root. The operation picks which of the two a path means.

- Plan 9 resolves the mount point of `mount` and `bind` with the access mode `Amount`, which does not cross into what is mounted there. Ordinary walks do cross. `sys/src/9/port/sysfile.c:1080` and `chan.c:1516` in 9front at a0806493.
- Linux requires `CAP_SYS_ADMIN` to mount and does not read the mount point's mode bits. A path lookup crosses into the mounted root, so `chmod` on a mount point changes the mounted root. `fs/namespace.c:2002` and `fs/namei.c:1682` at faeab1661.
- FUSE requires a user who is not root to have write access to the mount-point directory. `util/fuser_conf.c:401` in libfuse at fe66006f.
- FreeBSD requires a user who is not root to own the covered directory. `sys/kern/vfs_mount.c:1166` at 5e809bf1c93f.

The clones were read as they stood and were not refreshed.

## Decisions

### 1. The four grant verbs take `mount_point: bool = False`

`grant`, `revoke`, `grants` and `set_posture` gain the keyword. With `mount_point=True` the call is sent to the storage that holds the covered directory at the path, at that storage's own path. Without it, every call keeps the meaning it has today.

```python
await fs.grant(
    "/data", "ada", "read_write",
    mount_point=True, authority=system,
)
```

Reason: it is the only design that keeps the rule that the storage above judges a mount change, and it changes no call that works today.

### 2. The default is not flipped

A grant verb with no flag at a mount point still reaches the mounted root.

Reason: `set_posture("/data", "none")` is how a mounted storage is closed. A new mount starts at posture `read_write` even under a closed root. If that call went to the storage above, the mounted storage would stay open and nothing would say so.

### 3. The flag is allowed at any path

Away from an exact mount point the flag changes nothing, because the covered directory and the routed target are then the same entry. This holds before a mount exists, beneath a mount, and at `/`.

Reason: a setup script can grant the mount right before or after it adds the mount.

### 4. A flagged call passes the gate as a mount change does

The capabilities of the storage above and the permission maps above the mount point decide. The mount's own map has no say over its own mount point.

Reason: the same rule already governs `add_mount`, `remove_mount` and `update_mount`.

### 5. A session takes the flag

`AsyncSession` and `Session` take `mount_point` on the same four verbs, and so does the synchronous kernel.

Reason: a call through a session equals the direct call with that authority. The storage above still judges the caller, so a session gains no right it was not given.

### 6. `remove_mount` deletes the rights rows on the mount point

When a mount is removed, the grant rows whose path is exactly the mount point are deleted from the storage above. A later mount at the same path starts with no rights carried over.

Consequence to state in the docs: the rows are ordinary rows of the storage above. A grant made at that path before the mount was added is the same row, and it is deleted too.

### 7. "Mount point" becomes a glossary term

It is defined as above, with the covered directory and the mounted root told apart.

### 8. The mount right of the root is `read_write` over the root storage

There is no storage above the root, so the root storage judges its own `/`. This is today's behaviour.

## Not yet decided

- Whether `remove_mount` also deletes a posture row set at the mount point with the flag. Deleting it matches decision 6.
- How the rows are deleted. The storage protocol has no call that removes every grant row at one exact path. Either one is added to `SupportsGrants`, or the kernel lists the rows and revokes each. The first is one statement, and the second grows with the number of rows.
- What `remove_mount` does when the rows cannot be deleted. The mount is already out of the table at that point, as it is when the directory cannot be deleted.
- Whether the deletion runs as the system actor, as the delete of the covered directory does.

## Design

- The routing choice is a pure function of the mount table, a path and the flag. It returns the mount to call and the path inside it. It lives in `src/vfs/mounts.py`, because `src/vfs/base.py` is held at its line count.
- `_route_grant` in `base.py` gains one branch that calls it. Rows that come back are rebased to the kernel's paths, as they are today.
- `params.py` gains one shared boolean entry for the four verbs.
- `sync.py` and `session.py` pass the flag through. `sync.py` is also held at its line count.
- No statement and no lock is added. A flagged call is today's grant call, sent to a different storage. Its admin lock is the lock of the storage above and is held for a commit.

## What the docs must say

- One path at a mount point has two sets of rights, and `grants` must be called twice to see both.
- The mount right is the right to replace what appears at that path. A caller who removes a mount can add another storage there.
- Leaving the flag off `revoke` does not take the mount right away. It returns a warning that no such grant is held.
- A `list` grant with the flag makes the mount's name show in the parent's listing.

Pages: `documentation/reference/access-levels.md`, `documentation/maintainers/mounts.md`, the glossary, and the docstrings of the four verbs.

## Tests, written before the code

In a new `tests/base/test_mount_point_grants.py`.

- A flagged grant is sent to the storage above at the mount point, and the mounted storage is not called.
- A flagged grant gives the right to update and remove the mount. A caller without it is refused.
- A grant made before the mount is revoked with the flag after it, and `remove_mount` is then refused.
- Without the flag, a grant reaches the mounted root and gives no mount right.
- A flagged grant gives nothing inside the mount, neither a read nor a grant.
- A flagged `list` grant shows the mount's name in the parent's listing.
- Flagged `grants` lists the rows above in the kernel's paths.
- A flagged `set_posture` leaves the mounted storage as it was.
- Away from a mount point the flag changes nothing, at `/`, beneath a mount, and at a path with no mount.
- A flagged grant made before the mount is honoured after the mount is added.
- After `remove_mount`, no grant row is left at the mount point in the storage above, and a caller who held the mount right is refused a new `add_mount` there.
- The mount's own map does not gate a flagged call, and a map above does.
- A storage above that keeps no grants answers a flagged call with `unsupported`.
- A nested mount point is granted on the mount that holds it.
- A session and the synchronous kernel pass the flag through.
- A `mount_point` that is not a boolean is refused as `invalid`, and no storage is called.

The storage contract in `tests/support/grants_contract.py` gains a case if a call is added to `SupportsGrants`.

## Not checked

- The server engines. Every probe ran on the in-memory storage.
- A storage above that wraps a remote kernel, whose own mount table could send the path elsewhere.
- Why `stat` of a closed mounted root succeeded for a named caller in one probe.

## One line

A mount point names two entries with two sets of rights, and `mount_point=True` on the four grant verbs aims a call at the covered directory, which is where the right to change the mount is kept.
