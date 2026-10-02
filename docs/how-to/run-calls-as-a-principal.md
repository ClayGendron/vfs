<!--
DIÁTAXIS TYPE: How-to guide (task-oriented)
THE RULE: Assume competence. Steps to a goal. No "why" — link to Explanation.
-->

# How to run calls as a principal

Goal: make VFS calls carry a named identity instead of running as the anonymous principal.

What this changes: storage receives the authority on every call, rows you create get an `owner_id` of your subject name, and on a mount whose posture is not `open` the authority decides what the call may see and write. To set that up, see [How to share a folder with grants](share-a-folder-with-grants.md). For the design, read [Open in process, loud at the edge](../explanation/open-in-process-loud-at-the-edge.md).

## Build the authority

```python
from vfs import Authority, Principal

alice = Authority.of(Principal("alice"))
```

Use the id your identity provider verified as the `sub`. Do not use the reserved names `system` or `anon`.

## Pass it per call

Every verb accepts `authority=`. An explicit value always wins over a filesystem default.

```python
result = await fs.write(path="/notes/alice.md", content="hi", authority=alice)
result = await fs.read("/notes/alice.md", authority=alice)
```

## Or open a session

A session fills in `authority=` for you. Its verbs have the same signatures minus that parameter.

```python
async with fs.session(alice) as s:
    await s.write(path="/notes/session.md", content="hi")
    result = await s.read("/notes/session.md")
```

A closed session refuses every verb with the error kind `vfs.invalid`, and re-entering it raises `ValueError`. Open a new one instead.

```python
from vfs.results import VFSErrorKind

assert s.closed
result = await s.read("/notes/session.md")
assert result.errors[0].kind is VFSErrorKind.invalid
```

## Or set a filesystem default

For a single-user app, set the identity once.

```python
from vfs import VirtualFileSystem

fs = VirtualFileSystem(storage=storage, default_authority=alice)
await fs.write(path="/notes/default.md", content="hi")   # runs as alice
```

## Act for several people at once

When an agent works for a set of people, name the agent as the actor and the people as subjects. Rows created this way have no owner; see [Ownership is a floor, attribution is a record](../explanation/ownership-and-attribution.md).

```python
bot = Principal("assistant", kind="service")
room = Authority.on_behalf_of({Principal("alice"), Principal("bob")}, actor=bot)
await fs.write(path="/notes/room.md", content="hi", authority=room)
```

## Check what you passed

A non-authority value is refused before dispatch:

```python
from vfs.results import VFSErrorKind

result = await fs.read("/notes/alice.md", authority="alice")
assert result.errors[0].kind is VFSErrorKind.invalid
assert result.errors[0].message == "read authority must be an Authority, got str"
```
