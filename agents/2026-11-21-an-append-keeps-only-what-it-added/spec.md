# An append keeps only what it added

A draft, written on 2026-11-21 from what the review of `write`'s preconditions and the append left. It is not reviewed, and nothing is built.

## The outcome wanted

An append costs storage in proportion to what it adds, a caller who holds only `add` cannot change what kind of file another caller's file is, and an `edit` under contention behaves the same on every engine.

## Builds on

`agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md`, built as pull request 22, and its review, `context/reviews/2026-11-20-write-takes-preconditions-and-an-append-code-review.md`, findings M2 and M3.

## The problem

- **Each append keeps a full copy of the old body as a version.** N appends keep N copies, and only the trash sweep removes a live row's versions. 200 appends of 10 bytes to a 10 KB file kept about 2.2 MB of history. A caller who holds `add` can grow another caller's file history this way. The spec's "Cost" has the measurement.
- **A caller who holds `add` may turn another's text file into a bytes file by appending bytes that are not text.** The file then becomes a bytes file, and a read of it returns no text. The old body is kept as a version. `documentation/reference/access-levels.md` says so.
- **`edit` takes no row lock, and so behaves differently on each engine.** It keeps 20 of 20 concurrent edits on SQLite only, where every writer holds the one writer lock. On Postgres and MariaDB a losing edit runs again up to four times and is then refused, and on SQL Server and Oracle it is refused `conflict` at once. No edit is lost in silence. Read, and not run on a server engine.
- **The draft spec is still under `context/`.** `context/specifications/active/174-write-preconditions-and-the-guarded-append/` is replaced and points at the new spec. Its notes for the shell, the WASI host and the adapter specs were not carried over.

## Decisions

1. **An append keeps a version that holds only what it added,** with the offset it was added at. A read of an old version replays the appends onto the last full version.
2. **A non-owner's append that would change the row's source from text to bytes is refused `invalid`.** The owner's append may change it, as a `write` may.
3. **`edit` takes the row lock an append takes,** so a losing edit waits and then applies to the body the winner left, on every engine.
4. **The notes of the draft spec for the shell, the WASI host and the adapters are carried into the specs they concern,** and the draft is deleted.

## Cost

Decision 1 makes 200 appends of 10 bytes keep about 2 KB of history, not 2.2 MB, and makes a read of an old version cost one replay per append since the last full version. A full version is kept every so many appends to bound that replay.

## Tests

Counted tests first: the bytes a series of appends keeps, and the statements a read of an old version sends. For decision 3, 20 concurrent edits keep 20 edits on the Postgres leg.

## Scope

In: the version rows of an append, the append's source check, `edit`'s lock, and the draft under `context/`. Out: the trash sweep.

## Not checked

- How many appends a full version should be kept after.
- What `edit`'s row lock costs a 10,000-file batch of edits.

## Choices to confirm

1. **Decision 1: keep only what an append added?** Recommended: yes. Alternative: keep a full copy and say what it costs, as today.
2. **Decision 2: refuse a non-owner's append that changes the source?** Recommended: yes.
3. **Decision 3: does `edit` take the row lock?** Recommended: yes.

## One line

An append keeps only what it added, cannot change another's file from text to bytes, and an `edit` waits on the row as an append does.
