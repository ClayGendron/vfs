<!--
DIÁTAXIS TYPE: How-to guide (task-oriented)
THE RULE: Assume competence. Steps to a goal. No "why" — link to Explanation.
-->

# How to bulk load as the system actor

Goal: ingest a batch of files whose owners are already known, preserving each row's owner.

The system actor is the one identity whose writes honor the `owner_id` declared on each entry. Every other authority ignores the declared owner and stamps its own subject. For the reasoning, read [Ownership is a floor, attribution is a record](../explanation/ownership-and-attribution.md).

## Build a filesystem with the system default

```python
from vfs import Authority, VirtualFileSystem

etl = VirtualFileSystem(storage=storage, default_authority=Authority.system())
```

Keep this filesystem object separate from the one your application serves. The system actor bypasses grants, so it should not be the default anywhere a user's call can reach.

## Declare the owner on each entry

```python
from vfs.models import Entry

rows = [
    Entry(path="/import/a.md", content="...", owner_id="alice"),
    Entry(path="/import/b.md", content="...", owner_id="bob"),
]
result = await etl.write(rows, parents=True)
```

An entry with no `owner_id` gets no owner. Batches of ten thousand entries in one call are supported; the backend chunks the statements.

## Pass the system authority per call instead

If you do not want a separate filesystem object, pass the authority explicitly. It wins over any default.

```python
result = await fs.write(rows, parents=True, authority=Authority.system())
```

## Confirm the owner

Ownership is not yet exposed through a verb. To confirm it during development, query the entry table directly with SQLAlchemy and read the `owner_id` column.
