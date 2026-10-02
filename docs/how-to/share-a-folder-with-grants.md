<!--
DIÁTAXIS TYPE: How-to guide (task-oriented)
THE RULE: Assume competence. Steps to a goal. No "why" — link to Explanation.
-->

# How to share a folder with grants

Goal: make a mount private, then give named people and groups access to parts of it.

For why hidden rows read as missing and why posture is a row, read [Open in process, loud at the edge](../explanation/open-in-process-loud-at-the-edge.md).

## Load the files as the system actor

The system actor sees and writes everything, whatever the posture.

```python
from vfs import Authority, Principal
from vfs.results import VFSErrorKind

system = Authority.system()
await fs.write(path="/eng/spec.md", content="the spec", parents=True, authority=system)
await fs.write(path="/eng/plan.md", content="the plan", authority=system)
await fs.write(path="/pub/readme.md", content="hello", parents=True, authority=system)
```

## Make the mount private

A new mount is `open`: everyone reads and writes. Set the root to `private` so a caller holds only what it is granted.

```python
result = await fs.posture("/", "private", authority=system)
assert result.success
```

`shared` lets everyone read and nobody write without a grant. A posture on a deeper path decides everything beneath it.

## Grant a person a folder

```python
alice = Authority.of(Principal("alice"))
await fs.grant("/pub", "alice", "read", authority=system)

assert (await fs.read("/pub/readme.md", authority=alice)).success
hidden = await fs.read("/eng/spec.md", authority=alice)
assert hidden.errors[0].kind is VFSErrorKind.not_found
```

A path the caller cannot see answers `not_found`, exactly as a path that does not exist. A path it can see but not write answers `permission_denied`:

```python
denied = await fs.write(path="/pub/readme.md", content="edited", authority=alice)
assert denied.errors[0].kind is VFSErrorKind.permission_denied
```

The levels are `read` and `read_write`. Grants only widen: there is no deny row.

## Grant a group

Group ids start with `group:`. Only the system actor changes membership.

```python
await fs.add_member("group:eng", "alice", authority=system)
await fs.grant("/eng", "group:eng", "read_write", authority=system)

assert (await fs.write(path="/eng/notes.md", content="mine", authority=alice)).success
```

A group may be a member of another group. Nesting is capped at eight levels, and a cycle is refused.

## Let a granted person share onward

A caller holding `read_write` on a path may grant on it, up to its own level.

```python
bob = Authority.of(Principal("bob"))
await fs.grant("/eng/plan.md", "bob", "read", authority=alice)

assert (await fs.read("/eng/plan.md", authority=bob)).success
```

## See what decides a path

`grants` lists the rows on a path and on its ancestors. A caller holding `read_write` there sees every row; anyone else sees only its own, its groups', and the everyone rows.

```python
listed = await fs.grants("/eng/plan.md", authority=alice)
rows = {(row["principal_id"], row["path_prefix"], row["level"]) for row in listed.grants}
assert ("group:eng", "/eng", "read_write") in rows
assert ("bob", "/eng/plan.md", "read") in rows
```

## Revoke

`revoke` removes the row at exactly that path. A row on an ancestor is untouched.

```python
await fs.revoke("/eng/plan.md", "bob", authority=alice)
assert (await fs.read("/eng/plan.md", authority=bob)).errors[0].kind is VFSErrorKind.not_found
```

## What a caller with no name gets

A call that names nobody runs as the anonymous principal. On a private mount it is refused with `unauthenticated`, and the hint says to open a session or configure a default authority.

```python
anonymous = await fs.read("/pub/readme.md")
assert anonymous.errors[0].kind is VFSErrorKind.unauthenticated
```
