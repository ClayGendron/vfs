# 175 — Integrity: verify on read, the hash on write, and a report-only scrub

- **Status:** draft — cut 2026-10-24 from ADR 087 (proposed the same
  day) and the two memos it stands on. Not started. Five open
  `[NEEDS CLARIFICATION]` markers (§2, §1.2, §4.4, §6 and the rebase
  note for spec 178).
- **Date:** 2026-10-24
- **Owner:** Clay Gendron
- **Kind:** feature and fix (a new error kind; a body check on `read`;
  `content_hash` on every written row; the edit and the version mint
  check what they replace and hash off the event loop; a new
  developer-plane verb `scrub`; one new module
  `storage/backends/database/integrity.py`).
- **Depends on:** ADR 087 pins 8 and 9. Commit `ba77449` (the router's
  write-path hash off the loop: `MEASURE_OFFLOAD_BYTES` in `base.py`,
  the `MEASURED_BODY` door in `models/entry.py`), which this spec
  builds on and does not redo. Slice D (`scrub`) depends on spec 176's
  resumption key on `Result` (ADR 087 pins 3, 11 and 12).
- **Decisions it implements:** ADR 087 pin 9 (verify on every read;
  `hashlib`; the 100 KB offload rule; a report-only `scrub` over
  version rows too; `content_hash` returned on every written row) and
  pin 8 (`content_hash` is vfs's detector for logical faults above the
  engine; out-of-band writers are its main case). ADR 080 (every verb
  names its rung) for `scrub`.
- **Research it stands on:**
  `../../../research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md`
  §2.3 and §6 Q1 (the latency, Rust-versus-`hashlib` and offload
  tables); the studies
  `../../../research/studies/2026-10-24-ostep-principles-for-vfs/05-crash-consistency-and-data-integrity.md`
  §2.8–§2.11 and its experiment B (`experiments/s05/silent_rot.py`),
  `06-distribution-nfs-afs.md` principle 13, and
  `03-file-system-implementation-vsfs.md` principle 3; the executed
  references `experiments/synthesis/hash_latency.*`, `hashbench/` and
  `offload_threshold.*`; the kernel memo
  `../../../research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md`
  §4. New probe for this spec, EXECUTED at HEAD `ba77449`:
  `scratchpad/175/probe.py` (its findings are in §0).

## Intent

vfs stores a sha256 of every file body on the file's own row. That
hash is called `content_hash`. Today nothing ever compares it with the
body. So a body changed or deleted underneath vfs, by an ETL job with
SQL credentials or by a vfs bug, is served by `read` as success. After
this spec, `read` checks every body it serves against `content_hash`.
A body that does not match, or a body row that is missing, is an
error. The error names both hashes. It carries no body bytes.

Three more things follow. Every row a mutation reports carries its
`content_hash`, so a client can check end to end without a second
`stat`. The edit and the overwrite check the body they replace, so a
damaged body cannot slip into history looking healthy. And a new
developer-plane verb, `scrub`, walks the cold bodies nobody reads,
version rows included, and reports what fails. It never repairs:
vfs has no second copy to repair from.

## Terms

Each term is defined once here and used the same way below.

| Term | Meaning |
|---|---|
| body | The bytes of a file. A text file's body is in `vfs_content.content`. A bytes file's body is in `vfs_blobs.data`. A version's body is in `vfs_versions.content` or `.data`. |
| `content_hash` | The sha256 hex of a body, stored on the row that owns it: `vfs_entries.content_hash` for the current body, `vfs_versions.content_hash` for an old one. For text it is the hash of the UTF-8 bytes. |
| recorded hash | The `content_hash` stored on the row. |
| actual hash | The sha256 of the body as fetched now. |
| fault | A body whose actual hash differs from its recorded hash (a **mismatch**), or a row with a recorded hash and no body row (a **missing** body). |
| rot | Shorthand for any fault. The usual cause is not bit rot. It is an out-of-band writer: an ETL job, a migration, a hand-run `UPDATE`. |
| hop | One hand-off of CPU work to the backend's worker-thread pool through `call_offloaded` (`offload.py:79`). One hop costs about 32 µs. |
| the threshold | `MEASURE_OFFLOAD_BYTES = 100_000`. Below it a hash runs on the event loop. At or above it the hash takes a hop. |
| redrive | The retry layer's restart of a whole verb in a fresh transaction, triggered by `StaleSnapshot` (`dialects.py:48`, `engine.py:298`). |
| scrub | A paged, read-only walk that hashes stored bodies and reports faults. Report-only: it never writes. |
| resumption key | The opaque value a paged call returns so the next call continues where it stopped (spec 176). |

## 0. What the code does today (EXECUTED)

Probe `scratchpad/175/probe.py`, SQLite file, HEAD `ba77449`, through
`VirtualFileSystem` with its default authority. Counts only.

| Question | Answer today |
|---|---|
| Does a write's observation carry `content_hash`? | No. The mask is `{path, kind, size_bytes, status, version}`. |
| Which rows carry a hash? | Every file row, text or bytes, including the empty file. No directory. |
| Does an empty text file have a `vfs_content` row? | Yes. So a text file with no body row is always a fault. |
| Statements for `read` (small and 1 MB) | 4: three rights checks and one `vfs_entries` ⟕ `vfs_content` select. |
| Statements for `stat` (1 MB file) and `ls /` | 4 and 5. None names `vfs_content`, `vfs_blobs` or `vfs_versions`. |
| Hops on a 1 MB read | 0. |
| Read after the body is rewritten by direct SQL | `success=True`, serving the rewritten text. |
| Read after the `vfs_content` row is deleted | `success=True`, `content=None`, `size_bytes=11`, no error. |
| Read with `data` projected after the `vfs_blobs` row is deleted | `success=True`, `data=None`, no error. |
| `edit` of a file whose body row is deleted | `wrong_kind`, "no editable content". The wrong kind. |
| `edit` of a file whose body was rewritten | Success. The damaged text is edited and stored with a fresh, matching hash. |
| Overwrite of a file whose body was rewritten | Success. The version mint keeps the damaged body with its own fresh hash (`versions.py:158`), so history now holds the damage looking healthy. |

The last three rows are new findings. Study 05 found the first
three. Together they say: the damage is served, and two verbs launder
it into rows that later checks cannot catch.

## Slices and landing order

Four slices. Each lands green on its own (`scripts/ci.sh`). B, C and D
also run the four real-engine legs before landing (the `db_test`
skill).

| Slice | Name | Sections | Needs |
|---|---|---|---|
| **A** | The hash law, the offload rule, the kind | §1, §2 | nothing |
| **B** | Verify on read | §3 | A |
| **C** | The write side | §4 | A |
| **D** | `scrub` | §5 | A, B (the shared check), spec 176's `Result` key |

## 1. Slice A — one hash law and one offload rule

### 1.1 The hash law (`models/version.py`)

There must be exactly one function that turns a body into a hash.
Today `measure_text` and `measure_bytes` (`models/version.py:66`, `:77`)
each call `hashlib.sha256` themselves. The read check and the scrub
need the hash without the size and line count.

- Add `content_digest(body: str | bytes) -> str`: the sha256 hex of
  `body` if bytes, of `body.encode()` if text.
- `measure_text` and `measure_bytes` call `content_digest`. Their
  results do not change.
- `Version.reconstruct` (`version.py:191`) calls `content_digest` too.

`hashlib` stays the engine. It runs OpenSSL's hardware path, and it
measured faster than the Rust `sha2` crate (memo §6 Q1: 2.46 GB/s
against 0.35 GB/s default and 2.1 GB/s with `asm`). ADR 057's rule
sends hot paths to our Rust crate; this one measured faster where it
is, so it stays. `hashlib` also releases the GIL for inputs over
2 KB, which is what lets a hop hash in parallel with the loop.

### 1.2 The threshold moves to the models layer

`MEASURE_OFFLOAD_BYTES` lives in `base.py:137` today. Storage needs
the same number, and storage must not import the router. Move the
constant to `models/version.py`, beside the measure functions, and
export it from `vfs.models`. `base.py` imports it from there.
`_authored_entry` (`base.py:314`) keeps its `asyncio.to_thread` hop on
the loop's default executor: the router owns no pool, and `ba77449`'s
pins stay as they are.

[NEEDS CLARIFICATION: keep 100,000 bytes as the one constant
(measured on one arm64 laptop, memo §6 Q1), or re-measure the
crossover on a CI-class x86 runner before pinning it? ADR 087 lists
the constant as pending. Lean: keep it; it is a cost knob, not a
correctness rule, and every pin counts hops at both sides of
whatever value it holds.]

### 1.3 The offload rule is per call, not per body (`offload.py`)

The memo's rule is "hash inline under 100 KB, offload above". Applied
per body, it breaks on a batch. A 10,000-file read of 10 KB bodies has
no body over the threshold, yet hashing all 100 MB inline would hold
the loop for about 40 ms. So the rule is stated per call: **the event
loop hashes at most `MEASURE_OFFLOAD_BYTES` per call.** For a single
body this is exactly the memo's rule.

Add to `storage/backends/database/offload.py`:

```python
async def measure_all(
    executor: Executor,
    items: Sequence[T],
    measure: Callable[[T], R],
    size_of: Callable[[T], int],
) -> list[R]:
    """*measure* over every item, in order; on the loop only while the call stays small.

    When the items together weigh less than the offload threshold they
    are measured inline. Otherwise they are cut into blob pages and each
    page is measured on the pool, the pages in parallel.
    """
```

- Inline when `sum(size_of(i)) < MEASURE_OFFLOAD_BYTES`: zero hops.
- Otherwise: `byte_chunked(items, size_of, BLOB_PAGE_BYTES)`
  (`dialects.py:727`), one `call_offloaded` per page, gathered with
  `asyncio.gather`, results flattened in input order. Hops =
  number of pages. An oversized body rides alone in its page (the
  `ByteBatcher` singleton rule), so a 16 MB body is one hop.
- `size_of` is exact bytes for `bytes` and the character count for
  `str`, a declared proxy that undercounts multibyte text by at most
  4×. The reindex batchers already meter text this way
  (`offload.py` docstring).
- The `.encode()` of a text body happens inside `measure`, so it runs
  on the worker too.
- The module docstring's list of deliberate threads gains the read
  check, the edit, the version mint and the scrub.

Every hash this spec adds or moves goes through `measure_all`. One
place owns the rule, so one pin family (counted hops) covers it.

## 2. Slice A — the kind

A fault needs a classification. ADR 087 left open whether it rides
`unavailable` or gets a kind of its own. This spec does both: a child
kind under `unavailable`.

In `results/kinds.py`:

```python
integrity = "vfs.unavailable.integrity"  # EIO: a stored body fails its recorded hash, or is missing
```

with the contract:

| Field | Value |
|---|---|
| phrase | `"Integrity check failed"` |
| retry class | `RetryClass.never` |
| hint | `"The stored body is damaged; do not retry. Rewrite the file from a trusted copy, or report it to the operator."` |
| `path` means | `"the entry whose body failed its check"` |

Why a child of `unavailable`:

- The vocabulary is hierarchical (`kind_family`, `kinds.py`). A
  consumer that does not know the child degrades it to
  `vfs.unavailable`, which maps to EIO, the right errno for a bad
  block. No front breaks.
- `vfs.unavailable.schema` is the precedent: a child of
  `unavailable` whose retry class is `never`, because retrying cannot
  help.
- A caller that knows the child can tell "the database is down, retry"
  from "this body is damaged, do not retry". Plain `unavailable` would
  tell a caller to retry a fault that will never heal.

The per-kind `data` record, added to the `ErrorKind` docstring's list:

| Key | Value |
|---|---|
| `reason` | `"mismatch"` (the hashes differ), `"missing"` (no body row) or `"unhashed"` (a file row with no recorded hash) |
| `expected_hash` | the recorded hash; `None` when `unhashed` |
| `actual_hash` | the actual hash; `None` when no hash was taken (`missing`, `unhashed`) |
| `body` | the table that should hold it: `"vfs_content"`, `"vfs_blobs"` or `"vfs_versions"` |
| `version` | the entry's `version`, or the version row's number |
| `deleted` | `True` when the row is tombstoned (scrub only; absent otherwise) |

Never in `data`: any byte of the body. The `detail` is a fixed,
body-free phrase per reason ("the body does not match its recorded
hash", "the body row is missing", "the row records no hash").

[NEEDS CLARIFICATION: a child kind `vfs.unavailable.integrity` (lean,
above), or a top-level `vfs.integrity`, or plain `vfs.unavailable`
with the `data` record? ADR 087 lists this as pending Clay. The lean
keeps every existing consumer correct and gives a new one the
"do not retry" fact.]

## 3. Slice B — verify on read

### 3.1 Where the check runs

The check runs inside the read's own transaction, in `reads.py`,
between the screen that decides which rows are served and the
construction of each `Observation`.

Today `_point_rows` (`reads.py:558`) fetches every target and its
ancestors in one bounded statement (`_mappings_by_path`, `:793`),
screens them (`_screen`, `:678`), and turns each served mapping into
an `Observation` in a single loop. The body check needs three things
that loop does not give it: the recorded hash even when the caller
did not ask for it; the bodies of the whole batch at once, so the hops
can be paged; and a way to drop a row before it becomes an
`Observation`.

So:

1. `read_rows` (`reads.py:149`) computes `served` (today's
   `effective_columns(..., content=True)`) and `fetched = served |
   {"content_hash", "source"}` whenever `served` holds a body field.
   The two extra columns are short; no statement is added.
2. `_point_rows` takes an optional `check: BodyCheck | None` and a
   separate `served` mask. Its loop collects the rows it would serve,
   in target order, instead of observing them at once. Rows refused
   for kind or permission are refused exactly as today, **before** any
   hash, so a caller who may not read a row learns nothing about its
   integrity.
3. With a check, `await check.screen(collected)` returns the set of
   targets that failed and their errors. The rest are observed with
   the `served` mask, so `content_hash` appears in the row only when
   the caller asked for it.
4. `stat_rows` passes no check and fetches no body. Nothing changes
   for `stat`, `ls` or `tree`.

The check runs inside the transaction because a fault must be
confirmed before it is reported (§3.3), and the confirmation is a
redrive of the same transaction. The cost is honest: while a large
body hashes on the pool, the read's connection stays checked out
(about 0.4 ms per MB), and on `InMemoryStorage` the host lock is held
for that time. The future direction, if a pool ever runs short, is to
release the connection before hashing and carry the recorded hashes
out beside the rows.

### 3.2 Which bodies are checked

| Row | Served body | Checked against | Missing body means |
|---|---|---|---|
| text file | `content` | `content_hash` | no `vfs_content` row |
| bytes file, `data` projected | `data` | `content_hash` | no `vfs_blobs` row |
| bytes file, `data` not projected | `content` (the rendering) | nothing | not a fault here (see below) |
| file row whose `content_hash` is `NULL` | any | — | a fault, `reason "unhashed"`: vfs writes a hash for every file, empty ones included (§0), so a file row without one was changed underneath vfs |
| directory | none | — | — |
| any row, projection without a body field | none | — | no check, no hop: no body, no hash |

A bytes file's rendering has no hash of its own.
`render_source_hash` records which bytes it came from, not what the
rendering is. So a read that serves only the rendering cannot be
checked. This is stated in the `read` docstring; a rendering hash
column is the future direction if it is ever wanted.

The trash view (`/.vfs/trash/...`) serves tombstoned rows through the
same path, so its bodies are checked by the same rule.

### 3.3 A fault is believed only when two reads agree

One statement fetches the entry row and its body together (a left
join). On every engine but one, that statement sees one consistent
snapshot: Postgres and MariaDB run reads at `REPEATABLE READ`
(`dialects.py:436`, `:500`), Oracle's read committed is consistent per
statement, and SQLite reads one snapshot. SQL Server is the exception.
Its profile pins no isolation (`dialects.py:463`), so it runs locking
read committed, where a single join can read the entry row before a
rival's commit and the body after it. That would look exactly like a
mismatch. (INFERRED from SQL Server's documented locking behaviour;
not reproduced. Study 07 notes the same gap: "isolation levels have no
chapter".)

So the check never trusts one read. It confirms by redrive:

- `BodyCheck` is created once per `read` call, in
  `DatabaseStorage.read` (`backend.py:307`), and passed into
  `read_rows` through the `_viewed` lambda. It holds a set of
  suspects: `(path, version, recorded hash)`.
- On a fault it has not seen before, it adds the suspect, reaches the
  seam `read:suspect`, and raises `StaleSnapshot("a body failed its
  hash; confirming")`. The retry layer (`with_retry`) discards the
  session and runs the whole read again, after its jittered wait.
- On a fault whose suspect is already in the set (same path, same
  version, same recorded hash), the fault is confirmed: the row
  becomes an `integrity` error.
- If the row changed between the two reads (a rival committed), its
  version differs, the suspect does not match, and the new body is
  checked on its own merits. A torn read on SQL Server therefore
  heals into a correct answer.
- If faults keep moving through every attempt, the retry budget runs
  out and the read classifies as a retryable `conflict`, the same
  answer any other verb gives under that much churn.

Cost: zero statements on the healthy path. A confirmed fault costs one
extra read and one jittered wait (25 to 50 ms at the default base
delay). Faults are rare, and a fault path that is a little slow is
the right trade for a check that is uniform on every engine.

### 3.4 What the check computes, and where

`BodyCheck.screen(collected)`:

1. Picks the rows with a body to check (§3.2). Rows without one pass.
2. Missing bodies and `NULL` hashes are faults at once; no hash runs.
3. The rest go through `measure_all(executor, bodies, content_digest,
   size_of)`. Below the threshold per call, zero hops. At or above it,
   one hop per blob page. The executor is `host.offload_executor`
   (`engine.py:227`).
4. Each actual hash is compared with the recorded one.
5. Confirmed faults become errors (§2) in target order. A failed
   target yields **no `Observation`**: the body never reaches the
   caller, not even as a field set to `None`.

The healthy path adds one hash per served body and nothing else.

### 3.5 One pass over bytes already in hand (SQLite)

`content_bytes` (`dialects.py:191`) is declared where casting the
content column to the engine's bytes type returns its exact UTF-8
bytes cheaply. Only SQLite declares it today. Grep already fetches
bodies as bytes there (`content_for_entries`, `reads.py:478`).

Where it is declared, the read fetches the text body as bytes too
(`cast(content.c.content, LargeBinary).label("content")` in
`_entry_projection`, `reads.py:900`). The check hashes the bytes
directly, then the row decodes them once with `bytes.decode()` before
the `Observation` is built. That is two passes (hash, decode) instead
of three (the driver's decode, `.encode()`, hash). The decode cannot
fail after a match: a matching body is the UTF-8 vfs wrote. A
mismatched body is never decoded.

Everywhere else the driver returns `str`, and `content_digest`
encodes it once on the worker or the loop, by the per-call rule.
Rows that skip the check (bytes renderings) are decoded the same way
on SQLite.

### 3.6 Versions read the same way

No verb reads a version row today. The history read is owed by spec
161's read side, which ADR 087 folds into spec 180. When it lands it
uses `BodyCheck` unchanged: a version row's body is checked against
the version row's own `content_hash`, with the same confirm-by-redrive
law and the same per-call offload rule. A diff row (none exist until
`pack` writes them) is checked by `Version.reconstruct`, which already
compares the rebuilt text with the target's hash. This spec builds the
shared check; the history spec wires it. See the rebase notes.

### 3.7 The seam's promise

The `SupportsRead` docstring (`storage/protocol.py:118`) gains one
sentence: a backend that stores a body hash never serves a body that
fails it, and reports the failure as `integrity`. `DatabaseStorage`'s
module docstring says the same in one line.

## 4. Slice C — the write side

### 4.1 Every written row returns its `content_hash`

- `_finish` (`writes.py:315`): the staged branch (`:343`) adds
  `content_hash=staged.content_hash`. Write, edit and mkdir share
  `_finish`, so all three report it. A directory's is `None`, so the
  default mask leaves it out.
- The committed-row branch (`:356`) serves `unchanged` rows (a
  forgiven `mkdir`). It stays as it is: those are directories.
- `final_rows` (`serialized.py:283`) adds `entry.c.content_hash` to its
  select list, and `observe_final` (`:291`) passes it. Move, copy,
  delete and restore report it where the row has a body. The fallback
  `PendingRow` branch (a row a later target moved away) stays without
  it.

No statement is added: `_finish` already holds the staged hash, and
`final_rows` is the re-read that already runs. The default projection
for mutations stays `("path",)` (`results/projection.py`), so the text
render does not change. The payload and the MCP structured content
carry the field. A client can now check a write end to end: hash
what it sent, compare with the row.

### 4.2 The snapshot learns the recorded hash

`_fetch_committed` (`writes.py:284`) adds `entry.c.content_hash` to
its columns. 64 bytes per row, no statement added. `stage_update`
(`staging.py:401`) copies it into a new `StagedEntry` field,
`base_content_hash`, beside `base_size_bytes` and `base_content`. An
arbitration clobber (`absorb`) never saw the row at snapshot, so its
`base_content_hash` stays `None`.

### 4.3 The edit checks the body it edits, and hashes off the loop

An edit is a read and a write. It must obey the read's law, or it
launders damage (§0: a rotten body was edited and stored with a fresh,
matching hash). Today `edited_entry` (`storage/editing.py:27`) applies
the edits and builds the `Entry` in one sync call, and the `Entry`
validator hashes the result inline on the loop. A 16 MB edit holds the
loop for the whole hash.

`edited_entry` splits in two, both still sync and backend-neutral:

```python
def edited_text(target: Path, *, kind: str, content: str | None, edits: Sequence[EditOperation]) -> str | ResultError:
    """The edit sequence applied to one target's text, or a classified refusal."""

def edited_entry(target: Path, *, kind: str, content: str, measured: BodyMetrics | None = None) -> Entry | ResultError:
    """The validated entry for an edited text; *measured* enters through the measured-body door."""
```

`edit_rows` (`writes.py:226`) becomes:

1. **Check the pre-images.** For each distinct target whose snapshot
   row is a live text file: a missing content row is an `integrity`
   error with `reason "missing"` (today it is `wrong_kind`), and a
   `NULL` recorded hash one with `reason "unhashed"`. The rest
   are measured with `measure_all(executor, texts, measure_text, len)`
   and each hash is compared with the row's `content_hash`. A mismatch
   is an `integrity` error. Any error fails the whole batch before a
   statement runs, as every edit error already does. The metrics are
   kept on the staged row as `base_metrics`.
2. **Apply.** For each target occurrence, `edited_text` on the
   overlay's current text (`material_of`), then `stage_update` with
   the text and placeholder metrics. A repeated target edits its own
   staged output, as today.
3. **Measure the results.** One `measure_all` over the final staged
   text of each distinct path. Then `edited_entry(..., measured=m)`
   per path, through `Entry.model_validate(..., context={MEASURED_BODY:
   m})` (`models/entry.py:55`), and `refresh_material` with the
   validated metrics.

Two consequences, both stated in the `edit_rows` docstring:

- Validation judges the stored result of each path, not each
  intermediate of a repeated target. The stored result is what the
  invariants protect.
- An edit hashes each distinct target twice (pre-image, result), the
  same count as today (result, then the mint's pre-image), and the
  mint re-hashes nothing (§4.4). Hops: zero for an edit under the
  threshold, two for a 1 MB edit.

Confirm-by-redrive (§3.3) applies here too. The edit runs in a writer
transaction whose snapshot read is the plan's first statement, and on
SQL Server that read can tear the same way. So the edit raises
`StaleSnapshot` on an unconfirmed pre-image fault and confirms on the
redrive, holding its suspects in a closure in `DatabaseStorage.edit`
(`backend.py:717`).

`edit_rows` gains an `executor` parameter; `DatabaseStorage.edit`
passes `host.offload_executor`.

### 4.4 The version mint keeps damage visible

The mint (`versions.py:65`) reads each replaced body and stores it as
a version row. Today it measures the body it reads and stores that
hash (`_version_row`, `:158`). If the body was damaged, the version
row is born self-consistent, and no later check can see that version
N was not what was written.

Change, in `_mint_rows` (`:125`):

- Pre-images are measured with `measure_all` (inline under the
  threshold per call, a hop per page above it). Rows held from an
  edit's snapshot reuse `base_metrics` from §4.3 and are not hashed
  again.
- Where `base_content_hash` is known and differs from the measured
  hash, the replaced body was damaged. The version row stores
  **`base_content_hash`, the recorded hash**, with the body as found.
  The row is now a fault the scrub reports and a history read refuses,
  which is the truth: version N's bytes are not what version N was.
  The mint returns a warning beside its count: an `integrity` error at
  `Severity.warning`, `reason "mismatch"`, `version` = the replaced
  number. `_finish` attaches it to the write's `Result`. The write
  succeeds: overwriting a damaged file is how an operator repairs it.
- Where `base_content_hash` is `None` (an arbitration clobber), the
  mint measures and stores as today. That gap is honest and stated.
- No redrive is needed here. The recorded hash comes from the entry
  row alone (no join to tear), and the mint reads the pre-image after
  the guarded update has locked that row at its snapshot version, so
  the two describe the same version on every engine.
- The "identical body mints nothing" rule still compares the
  measured hash with the new body's hash.

`versions.py`'s docstring changes its sentence "measured from the
body itself, never copied from the entry row" to say the snapshot's
recorded hash wins when the snapshot saw the row, and why.

`write_rows`, `_finish`, `_apply` and `mint_versions` gain the
`executor` parameter. `DatabaseStorage.write` passes it. Topology
verbs do not mint today and are untouched.

[NEEDS CLARIFICATION: an overwrite of a damaged body succeeds with a
warning, and its version row keeps the recorded hash so the damage
stays visible (lean, above). The alternatives: refuse the overwrite
until an operator acts (blocks the natural repair), or store the
measured hash and warn once (the damage leaves no lasting trace).]

### 4.5 What the write side does not change

- The router's single write keeps `ba77449`'s hop.
- A caller's own `entries=` batch is hashed when the caller builds the
  `Entry` objects, on the caller's loop. That is the caller's choice.
- `copy` copies body rows with the source's recorded hash, so a
  damaged source makes a damaged copy that is equally detectable. Copy
  does not hash (it serves no body to the caller).

## 5. Slice D — `scrub`

### 5.1 The verb

```python
async def scrub(
    self,
    path: str = "/",
    *,
    after: str | None = None,
    limit: int = SCRUB_LIMIT_DEFAULT,
    authority: Authority | None = None,
) -> Result:
    """Check every stored body at or beneath *path* against its recorded hash; report, never repair."""
```

- **Vocabulary** (`ops.py`): `"scrub"` joins `Op`, `READ_OPS` (it only
  observes, so a read-only mount answers it) and `DEVELOPER_OPS`
  (never on an agent tool surface: it reads every body in a mount).
  `VERB_RUNGS["scrub"] = Needs("read")`. `SCRUB_LIMIT_DEFAULT: Final =
  1_000` sits beside the graph defaults.
- **`deny_ops`** (`base.py:882`): the guard that refuses masking a
  read op becomes `mask & (READ_OPS - DEVELOPER_OPS)`, so a host can
  deny `scrub`.
- **Params** (`params.py`): `path` (default `"/"`), `after` (`str`,
  nullable), `limit` (`int`, 1 to `INT_CEILING`), `authority`.
- **Router**: a public method like `sweep` (`base.py:1111`), routed by
  `_route_single` to the one mount that holds `path`; an arm in
  `_call_storage` behind `isinstance(storage, SupportsScrub)`, else
  `unsupported`. `Session` gains the same method.
- **Protocol**: `SupportsScrub` (optional, like `SupportsReindex`) with
  `scrub(*, path, after, limit, authority)`, and a row in
  `_FAMILY_OPS`.
- **Projection**: `_DEFAULT_PROJECTION["scrub"] = ("path",)`.

### 5.2 The gate

`DatabaseStorage.scrub` runs in one read session (`_execute`). It
takes the write gate's resolution (`_gate`, `backend.py:1559`) at the
`read` rung. The system actor and any caller whose rights cover the
scope whole pass at once. Otherwise `checks.subtrees(session, [path],
"read")` (`rights.py:730`) must return nothing: a caller missing
`read` on one row beneath `path` is refused `permission_denied`
before any body is fetched. No partial scrub: a recorded hash is an
oracle for a body (it confirms a guess), so the scrub reports only to
someone who may read everything it covers.

### 5.3 The walk

The scope is every row at or beneath `path`, live and tombstoned, the
`/.vfs` meta rows included. Bodies in the trash are cold data too. Two
phases, in order:

1. **Bodies** — the current body of each file row.
2. **Versions** — every row of `vfs_versions` whose entry is in scope.

The walk is ordered by `path`, which is unique per row under the
tombstone law (ADR 074) and indexed, so a subtree scrub seeks
instead of scanning the mount. The versions phase orders by
`(path, version_number)`.

Per page, with `P = min(limit_remaining, membership_budget)`:

**Bodies phase.**

1. A metadata statement, no body bytes:
   `SELECT path, entry_id, source, size_bytes FROM vfs_entries WHERE
   kind = 'file' AND (path = :p OR <descendant_filter>) AND path >
   :after ORDER BY path LIMIT :P`. `descendant_filter` is
   `descent.py:198`.
2. The page splits by `source`. Each group is cut with
   `byte_chunked(rows, size_bytes, BLOB_PAGE_BYTES)` and then
   `chunked(ids, membership_budget)`. Each piece is one statement:
   text pieces select `entry.path, entry.version, entry.content_hash,
   content.content` over `vfs_entries` ⟕ `vfs_content`; bytes pieces
   the same over `vfs_blobs.data`. The recorded hash comes from the
   same statement as the body, so a rival commit between the metadata
   statement and the body statement cannot fake a mismatch.
3. A row with no body is `missing` and a row with no recorded hash
   `unhashed`, without hashing. The rest hash with `measure_all`
   (per-call rule) and compare. Every fault becomes a suspect.

**Versions phase.**

1. A metadata statement:
   `SELECT e.path, v.entry_id, v.version_number, v.is_snapshot,
   v.size_bytes FROM vfs_versions v JOIN vfs_entries e ON e.entry_id =
   v.entry_id WHERE <scope on e.path> AND (e.path > :p OR (e.path = :p
   AND v.version_number > :n)) ORDER BY e.path, v.version_number LIMIT
   :P`.
2. Pieces by `byte_chunked(..., BLOB_PAGE_BYTES)`. Inside a page an
   entry's wanted numbers are one contiguous range, so each piece is
   one statement of OR-arms, one arm per distinct entry:
   `(entry_id = :e AND version_number BETWEEN :lo AND :hi)`, chunked
   by `arm_budget(profile, parameter_budget, 3)` (`dialects.py`; the
   glob fan's precedent). The arms select `content_hash, content,
   data, is_snapshot`.
3. A snapshot row is hashed and compared. A row with neither `content`
   nor `data` is `missing`. A diff row (`is_snapshot` false) is not
   checked here and is counted under `unverified`: its check is
   `Version.reconstruct` over its chain, which `pack` (spec 180)
   defines. None exist today.

**Confirm.** Suspects from the call are re-fetched in a fresh read
session (a second `_execute`), one piece per `membership_budget` keys
(and per arm budget for versions). Only rows that fail again at the
same `version` (entries) or the same `content_hash` (version rows) are
reported. A row that changed, or vanished, is dropped: the next pass
sees it fresh. This is §3.3's law, said for a walk.

**Stop.** The call stops when it has visited `limit` rows or both
phases are exhausted. It returns the resumption key when it stopped at
`limit`, and none when the walk is done.

### 5.4 The resumption key

The key is the last row visited: `("bodies", path)` or
`("versions", path, version_number)`, encoded as a short JSON string
that callers treat as opaque. It rides the resumption-key field that
spec 176 adds to `Result` (ADR 087 pin 12, lean), the same shape as
`ls` and the bounded `sweep` (pin 11). A key whose path lies outside
the scope checks nothing outside it: every statement carries the scope
predicate, so a forged key can only skip, never widen.

### 5.5 The report

- Each confirmed fault is one `integrity` error at
  `Severity.warning`, with `path`, and `data` per §2 (`body`,
  `version`, `deleted` when tombstoned). Warnings, because the scrub
  did its job; the faults are facts on record, in the style of
  `reindex`'s drift warnings (`_drift_warning`, `edges.py:536`).
- One extra, `scrub`: `{"checked": rows, "bytes": recorded bytes,
  "faults": n, "unverified": diff rows skipped}`.
- No observations. A fault is reported, not a row served.
- The scrub writes nothing: no repair, no flag, no mark. Storage owns
  no background work, so pacing is the caller's: call, sleep, call
  again with the key, off-peak.

### 5.6 Bounds

| Unit | Bound per call |
|---|---|
| metadata statements | `ceil(limit / membership_budget)` per phase entered |
| body statements | per page: `pieces = Σ byte pages × ceil(keys / membership_budget)` (bodies) or `× ceil(entries / arm_budget)` (versions) |
| confirm statements | zero on a clean store; the same piece rule over suspects otherwise |
| keys in one statement | `membership_budget` (Oracle 1,000; SQL Server 2,000), never more |
| declared body bytes in one statement | `BLOB_PAGE_BYTES` (8 MiB), one oversized body alone |
| hops | zero under the threshold per call; one per blob page above it |
| warnings | at most `limit` |

A body grown underneath vfs is metered at its recorded `size_bytes`,
so it can overshoot its page by its own growth. The singleton rule
bounds that at one body per statement. This is stated in the
docstring, not converted into a cap.

The scrub is O(stored bytes) across the wire, the same shape as
`fsck`. That is right for a scheduled job and wrong as recovery, which
is why it is paged and report-only.

### 5.7 Why not a `reindex` phase

`reindex` holds a lease, writes, and is idempotent-cheap when nothing
is dirty. A scrub reads everything every time and writes nothing. Its
pacing is the operator's, not the index's. Folding it into `reindex`
would make every reindex O(stored bytes). It stays its own verb.

## 6. Out of scope

- **`grep` and `glean` text.** Grep's verify stage reads candidate
  bodies and returns matched lines from them, unhashed. Its false hits
  are already impossible (study 05: verification dropped the rotten
  candidate), but a hit's line can come from a damaged body. Hashing
  every candidate would add a full hash pass to grep's scan tier.
  [NEEDS CLARIFICATION: leave grep and glean unverified, with `read`
  as the verified door and a hit a pointer to it (lean), or hash each
  candidate body in grep's verify batch on the same pool?]
- **A rendering's integrity.** No hash of the rendering exists (§3.2).
- **Repair.** vfs keeps no second copy. Restore from a version is the
  history spec's read, not a repair here.
- **Orphan bodies** (body rows with no entry). Those are `sweep`'s
  (spec 180).
- **An `integrity` trait.** No second backend exists that could
  declare otherwise. Add it when one does.
- **Hashing in Rust.** Measured slower (memo §6 Q1). Revisit only if a
  read ever decodes bodies in Rust and the hash can ride that call.

## 7. Conformance: the integrity family on every engine leg

A new mixin, `IntegrityContract`, in
`tests/support/integrity_contract.py`, joins `StorageContract` and
`GrantsContract` on every conformance class in
`tests/storage/test_conformance.py` (memory, SQLite file, Postgres,
MariaDB, SQL Server, Oracle). Its fixture plants faults with direct
SQL through the backend's own `tables` and `session_factory`, the way
an out-of-band writer would:

- `plant_rewrite(path, text)` — `UPDATE vfs_content`.
- `plant_blob_rewrite(path, data)` — `UPDATE vfs_blobs`.
- `plant_delete(path, table)` — `DELETE` from `vfs_content` or
  `vfs_blobs`.
- `plant_null_hash(path)` — `UPDATE vfs_entries SET content_hash =
  NULL`.
- `plant_version_rewrite(path, number, body)` — `UPDATE
  vfs_versions`.

Counts come from a `before_cursor_execute` listener on the sync engine
(the S03 probe's method) and a spy on `call_offloaded`. Never a clock.

## Scope

In: everything in §1–§5 and §7. Out: §6.

## Acceptance criteria

Counts and states, never clocks. Each is tagged with its slice. "Every
leg" means memory, SQLite file and the four real-engine legs.

1. **(A)** `content_digest` is the one hash: for an ASCII, a
   multibyte, an empty text and a bytes body,
   `measure_text(t).content_hash == content_digest(t)` and
   `measure_bytes(b).content_hash == content_digest(b)`, and
   `Version.reconstruct`, `BodyCheck` and the scrub reach the hash only
   through `content_digest` (spied).
2. **(A)** `MEASURE_OFFLOAD_BYTES` has one definition, in
   `models/version.py`; `base.py` imports it; `ba77449`'s hop pins pass
   unchanged.
3. **(A)** `measure_all` hops: 0 for one 99,999-byte item; 1 for one
   100,000-byte item; 0 for 99 items of 1,000 bytes; 1 for 200 items
   of 1,000 bytes; 3 for 20 items of 1,000,000 bytes; 1 for one
   16,000,000-byte item. Results equal the inline results, in input
   order.
4. **(A)** `kind_family("vfs.unavailable.integrity")` is
   `ErrorKind.integrity`; an unknown sibling `vfs.unavailable.x`
   degrades to `unavailable`; the contract's retry class is `never`;
   the kind-contract drift tests pass.
5. **(B, every leg)** A text body rewritten underneath vfs reads as an
   error: `success is False`, zero observations, one `integrity` error
   whose `data` has `reason "mismatch"`, `expected_hash` equal to the
   hash `stat` reports, and `actual_hash` equal to the sha256 of the
   planted text. The planted text appears nowhere in
   `result.to_payload()` or `result.to_str()`.
6. **(B, every leg)** A deleted `vfs_content` row behind a text file
   reads as an `integrity` error with `reason "missing"` and
   `actual_hash None`, zero observations, never `success`. The same for
   a deleted `vfs_blobs` row when `data` is projected. A file row whose
   `content_hash` was set to `NULL` reads as `integrity` with `reason
   "unhashed"`.
7. **(B, every leg)** A batch read of four targets, one damaged,
   returns three observations and one error, in target order.
8. **(B, every leg)** Confirm by redrive: a damaged read issues exactly
   two data statements (two attempts). With a handler on
   `read:suspect` that commits a fresh write of the same path, the read
   succeeds with the fresh body and zero `integrity` errors.
9. **(B)** Hops per read: a 99,999-byte body, 0; a 100,000-byte body,
   1. A healthy read issues the same statements as before this spec
   (one data statement at the system actor).
10. **(B, every leg)** Projections: `read(columns={"path",
    "size_bytes"})` of a damaged row succeeds with no statement naming
    `vfs_content` or `vfs_blobs` and zero hops. `read(columns={"path",
    "content"})` of a healthy row has `populated == {"path", "kind",
    "version", "content"}`.
11. **(B, every leg)** `stat`, `ls` and `tree` over a 4 MiB file issue
    no statement naming `vfs_content`, `vfs_blobs` or `vfs_versions`,
    and zero hops.
12. **(B)** A bytes file read without `data` serves its rendering with
    zero hashes; with `data`, one hash; a damaged blob reads as
    `integrity`.
13. **(B)** On SQLite the read statement selects the content body cast
    to `BLOB`; on the other legs it does not; outputs are identical.
14. **(C, every leg)** `write`, `edit`, `copy` and `move` report
    `content_hash` on every file row, equal to the sha256 of the stored
    body and to a following `stat`'s. Directories report none. The
    statement counts of a create (6) and an overwrite (8) at the system
    actor are unchanged (the pins in `test_writes.py`).
15. **(C, every leg)** `edit` of a file with no body row is
    `integrity` (`reason "missing"`), not `wrong_kind`. `edit` of a
    damaged body is `integrity`, and the batch writes zero rows (every
    table's row count unchanged).
16. **(C)** Hops per edit: a 50,000-byte file, 0; a 1,000,000-byte
    file, 2 (pre-image and result). The mint hashes no edit pre-image
    a second time (spied: zero `measure_text` calls from the mint for
    held rows).
17. **(C, every leg)** Overwrite of a damaged body succeeds with one
    `integrity` warning naming the replaced version. The new version
    row's `content_hash` equals the entry's recorded hash before the
    write, not the damaged body's hash. Hops for the mint: 1 for a
    1,000,000-byte pre-image, 0 for 50,000.
18. **(D, every leg)** A store of 2,500 files, each overwritten once
    (2,500 version rows; 100 of the files are bytes files), with five
    planted faults (a rewritten text
    body, a deleted content row, a deleted blob row, a rewritten
    version `content`, a rewritten version `data`, one on a tombstoned
    row): a full scrub reports exactly those five, with the right
    paths, `body` tables and versions, and nothing else. A clean store
    reports zero. Every table's rows are byte-identical before and
    after.
19. **(D, every leg)** Bounds: a full pass with `limit=1,000` issues
    exactly the statements §5.6's formula gives with the leg's own
    budgets (counted), and no statement binds more than
    `membership_budget` keys. Chaining calls by the returned key
    checks every row exactly once (`checked` totals 5,000), and the
    last call returns no key.
20. **(D)** Gate: the system actor scrubs; a principal holding `read`
    on the whole scope scrubs; a principal missing `read` on one row
    is `permission_denied` with no statement naming a body table.
    `scrub` is in `DEVELOPER_OPS`, answered on a read-only mount, and
    maskable by `deny_ops`. A key naming a path outside the scope
    checks nothing outside it.
21. **(all)** `scripts/ci.sh` is green at 100% coverage after every
    task. The four engine legs are green before B, C and D land.

## ADR amendments this spec needs

- **087 pin 9:** record (a) the kind decision of §2; (b) the threshold
  as a per-call budget ("the loop hashes at most the threshold per
  call"), with its home in `models/version.py`; (c) the law that a
  fault is believed only when two reads in two transactions agree on
  the same row version (§3.3); (d) that a read serving only a bytes
  file's rendering is unchecked, for want of a rendering hash; (e)
  the edit's pre-image check and the mint's recorded-hash rule (§4.3,
  §4.4); (f) that `scrub` is a read-family developer-plane verb at the
  `read` rung, walking by `path`, reporting warnings, writing nothing.
- **087 pin 8:** the fault model gains one engine behaviour: SQL
  Server's locking read committed can tear a single join between an
  entry row and its body under a rival commit (INFERRED); the
  confirm-by-redrive law absorbs it.
- **080 (the ladder):** `VERB_RUNGS` gains `scrub` at `read`.
- **Kinds docstring (`kinds.py`):** the per-kind `data` record list
  gains `integrity`'s keys (§2). ADR 076 is unchanged: the detail is
  a fixed phrase, never prose about the body.

## Rebase notes for specs 167/171/172

- **167 (the shell):** `cat` of a damaged file meets `integrity` and
  prints bash's EIO line, `cat: <path>: Input/output error`, with exit
  1; the kind's family (`vfs.unavailable`) already maps to EIO in the
  errno table. `cat f > g` refuses to copy a damaged body, which is
  correct. `scrub` is developer-plane, so `cli` answers it
  `unrecognized` like `sweep` (167's criterion 12 gains `scrub`).
- **171 (the MCP adapter):** a read's `integrity` error is `isError`
  with no retry hint (retry class `never`). Every mutating tool's
  structured content now carries `content_hash` per file row; its
  output schema gains the field. `scrub` joins the developer-plane
  verbs the tool never registers.
- **172 (the WASI runtime):** a guest read of a damaged file fails
  with `EIO`. The write observation now returns `content_hash`, so the
  close-time write-back can record the hash it wrote without a
  `stat`, and the staged-buffer cache can key by `content_hash`
  (ADR 087's consequence for 172) at no extra statement.

Further notes, for specs ADR 087 schedules after this one:

- **176 (the listing cursor):** `scrub` consumes 176's resumption-key
  field on `Result`. Slice D waits for it.
- **178 (the ranged read):** a range cannot be checked without the
  whole body, and fetching the whole body defeats the range.
  [NEEDS CLARIFICATION: a range that covers the whole body is checked
  and a partial range is served unchecked with an `info` note (lean),
  or every ranged read fetches and hashes the whole body (Clay's
  "every read" taken literally), or per-page hashes stored beside the
  body let a range check only its pages (a schema change)?]
- **180 (history, `pack`, bounded `sweep`):** the history read uses
  `BodyCheck` (§3.6). `pack` must write diff rows whose
  `content_hash` is the full version's hash (already `Version.create`'s
  rule), and the scrub's versions phase then checks a diff row by
  reconstructing its chain; until then diff rows count as
  `unverified`. `sweep`'s orphan reclaim stays `sweep`'s.

## Landing notes

(Filled in on landing, per slice.)
