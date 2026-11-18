# Access Levels

An access level says what a caller may do at a path and everything below it. There are six levels. They are ordered, and **each level includes everything the levels before it allow**.

## The Levels

| Level | What it adds |
|---|---|
| `none` | Nothing. The path does not exist for the caller. |
| `list` | See that files and folders exist: their names, kinds, and sizes. |
| `read` | Read file contents, search them, and see who has access. |
| `add` | Create new files and folders. |
| `contribute` | Change files that other people created. |
| `read_write` | Delete, move, and restore files, and change who has access. |

A new file system gives everyone `read_write`.

## What Each Level Allows

The table shows each call on a file that someone else created. "Yes" means the call succeeds. "Hidden" means the call succeeds and leaves the file out of its result. Any other cell is the error the caller receives.

| Call | `none` | `list` | `read` | `add` | `contribute` | `read_write` |
|---|---|---|---|---|---|---|
| `ls`, `tree`, `glob` | Hidden | Yes | Yes | Yes | Yes | Yes |
| `stat` | Not found | Yes | Yes | Yes | Yes | Yes |
| `read` | Not found | Permission denied | Yes | Yes | Yes | Yes |
| `grep`, `search` | Hidden | Hidden | Yes | Yes | Yes | Yes |
| `grants` | Not found | Not found | Yes | Yes | Yes | Yes |
| `write` to a new path, `mkdir` | Permission denied | Permission denied | Permission denied | Yes | Yes | Yes |
| `copy` to a new path | Not found | Permission denied | Permission denied | Yes | Yes | Yes |
| `write` over the file | Permission denied | Permission denied | Permission denied | Permission denied | Yes | Yes |
| `edit` | Not found | Permission denied | Permission denied | Permission denied | Yes | Yes |
| `delete`, `move`, `restore` | Not found | Permission denied | Permission denied | Permission denied | Permission denied | Yes |
| `grant`, `revoke`, `set_posture` | Not found | Permission denied | Permission denied | Permission denied | Permission denied | Yes |
| `sweep` | Not found | Permission denied | Permission denied | Permission denied | Permission denied | Yes |

`sweep` destroys a file for good, and `delete` moves it to the trash.

## Files the Caller Created

A named caller owns each file it creates. **An owner may always read, overwrite, edit, and delete their own file**, whatever level they hold at its path, including `none`.

Moving a file creates it at a new path, so an owner needs `add` at the destination to move their own file.

A file written by the system, or by a caller with no name, has no owner.

## Who Holds a Level

A level is given to a person, to a group, or to everyone.

| Given to | Call | Example |
|---|---|---|
| A person | `grant` | `fs.grant("/eng", "ada", "read")` |
| A group | `grant` | `fs.grant("/eng", "group:eng", "read")` |
| Everyone | `set_posture` | `fs.set_posture("/eng", "read")` |

Each of these calls also takes `authority=`, which names the caller making the change. [Who May Change Access](#who-may-change-access) says which callers are allowed.

- **A group's name starts with `group:`.** `fs.add_member("group:eng", "ada", authority=Authority.system())` puts a person in a group, and `fs.remove_member` takes them out. A group may hold other groups, up to eight deep.
- **`grant` accepts every level except `none`.** `set_posture` accepts all six.
- **`fs.grants(path)` lists the rows that decide access at a path.** Everyone appears in those rows as `*`.

## How a Caller's Level Is Decided

- **A level covers a path and everything below it.** A grant on `/eng` reaches `/eng/specs/api.md`.
- **A caller holds the highest level given to them at a path**, counting their own grants, their groups' grants, and what everyone holds.
- **Grants only add access.** No grant takes a level away from a person.
- **The deepest posture decides what everyone holds.** With `/` set to `read_write` and `/hr` set to `none`, everyone holds `none` at `/hr/case.md`.

## Who May Change Access

| Call | Who may call it |
|---|---|
| `grant`, `revoke`, `set_posture` | A caller who holds `read_write` at the path and everything below it |
| `add_member`, `remove_member` | The system only |
| `add_mount`, `remove_mount`, `update_mount` | A caller who holds `read_write` at the path of the mount |

A caller with `Authority.system()` passes every check on this page. It stands for your own application code.

## Callers with No Name

A call made with no authority holds only what everyone holds. When that level does not allow the call, the error is "Unauthenticated".

The `default_authority` argument of `VirtualFileSystem` names the caller for every call that passes no authority.

## Errors

| Error | Meaning |
|---|---|
| Not found | The path does not exist, or the caller cannot see it. The error is the same in both cases. |
| Permission denied | The caller's level at the path does not allow the call. |
| Unauthenticated | The caller has no name, and what everyone holds does not allow the call. |
