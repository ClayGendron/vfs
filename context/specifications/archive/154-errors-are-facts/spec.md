# 154 — Errors are facts: storage names a kind and its fields, the contract table owns the words

- **Status:** landed and archived 2026-10-10 — commit `a64b48a`, the `ErrorKind` rename following as `76ce536`; the gate `scripts/ci.sh` ran green on 2026-10-10 at `b446c76`.
- **Earlier status:** **built 2026-10-10, awaiting Clay's review** — both slices in one landing over `4b598bc`: the phrase table, the one constructor, the seams' `vfs.target`, the renderer's target clause, all 109 producer sites and 27 test files migrated, 17 new tests in `tests/results/test_facts.py`. ruff, format and ty green; see *Landing notes* for the full suite's outcome and the deviations. Rewritten 2026-10-10 after a design pass with Clay (the 2026-10-08 cut fixed the wording at 51 sites; this cut removes the class of bug: no producer authors `message`). Stands on a prior-art read of thirteen reference repos the same day, summarised under *Prior art*.
- **Date:** 2026-10-10
- **Owner:** Clay Gendron
- **Kind:** refactor (the results envelope's construction verbs and contract table; every producer site migrates; one reclassification)
- **Depends on:** ADR 076 (proposed 2026-10-10, Clay's acceptance gates slice A), which amends the envelope law: today it reads *rebase seams touch `path`, `source` and `data`, never `message`*; it gains *no producer authors `message`; the contract table composes it from the kind and its fields, and the renderer attaches every locus last*. The seam as built (`src/vfs/results/envelope.py`, `with_mount` and `without_mount`), the contract table (`results/kinds.py`, `KIND_CONTRACTS`) and the error line (`results/render.py`, `_error_line`) are the three pieces this spec extends; none is replaced.
- **Research it stands on:** `../../../research/2026-10-08-smartowl-workspace-integration-issues.md` items 7, 8 and 23, and `../../../research/2026-10-10-who-composes-the-error-message.md` (the prior-art read the table below summarises, with citations).

## Intent

An agent reading `ERROR /mine/missing.md: Not found: /missing.md` sees two paths and retries the wrong one. The first is the rebased locus the renderer prints from the structured `path`. The second is the storage's own coordinates, which the producer wrote into `message`. The rebase seam cannot fix it, by law: `message` is prose, and no seam touches it.

The 2026-10-08 cut of this spec stripped the path from 51 messages and added a test to catch the next one. That treats the symptom. The cause is that two construction doors are open and both take prose: 67 raw `ResultError(...)` calls and 53 calls to `classified(kind, message, ...)`, whose second positional argument is a sentence. Every producer is invited to write words, and 109 of them do.

This cut closes the doors. Storage returns a fact: a kind, a locus and named fields. The contract table, which already owns each kind's hint and retry class, owns its phrase too. One constructor builds every `vfs.*` error and takes no message argument, so a producer cannot put a path in prose because there is nowhere to put prose. The renderer prints the locus, and the second entry when there is one, from the rebased fields at the last moment.

One line: keep the nouns, fix the verbs. The kind says what went wrong, the fields say where and with what, the table says it in words, and the path is attached after every rebase has run.

## Prior art (read 2026-10-10, thirteen repos, cited in the memo to follow)

Three models, and only two of them stay correct across a mount boundary.

| Model | Who writes the words | Where the path goes | Seen in |
|---|---|---|---|
| Code only | the consumer's library, from a table | the program prepends it at print time | errno and `strerror`; libfuse (a bare negative errno, no text field in the reply); pjdfstest (tests assert the errno *name*, never the text) |
| Fields, rendered late | a template filled from fields when printed | a structured field the sub-filesystem rebases | opendal (a short phrase; a layer above the service attaches `path` as context); pyfilesystem2 (`{path}` template filled in `__str__`, `SubFS` rewrites the field); mirage (errno plus the mount-level path stamped at construction) |
| Producer prose | the backend, path baked in | only in the text | Plan 9 (the kernel writes the quoted path into the string and `cat` prepends the name again); fsspec (`DirFileSystem` leaks the delegate path); afs (the router passes provider errors through); deepagents (`CompositeBackend` strips the route from `path` but not from the error string, and its middleware greps the text for `not_a_directory`) |

vfs is in the third row today and already has the second row's parts: a hierarchical kind, a structured locus, a seam that rebases fields, and a per-kind contract table consulted at render time. This spec moves the one remaining piece, the message, into the same model.

## Decided semantics

1. **A `vfs.*` error is constructed only by the envelope's own verbs.** `classified(kind, path=None, *, target=None, detail=None, retryable=False, **fields)` is the one general constructor; `already_exists(path, *, target=None)` and `wrong_kind(kind, path, *, target=None)` stay as the two conveniences that encode a field. None takes a message. The router's `_error` helper loses its positional `message` and takes `detail=` like the constructor. A raw `ResultError(...)` appears in `src/vfs` only inside `src/vfs/results/`: the constructor, the wire decoder (`from_payload`) and the rollup and quarantine machinery.
2. **The contract table owns the phrase.** `KindContract` gains a fourth member, `phrase`, the message template for the kind. A phrase never contains a locus. It may name a field in braces, filled from `fields` (`wrong_kind`'s `kind`: "Is {article} {kind}"). The constructor composes `message` as the phrase, then `: ` and the detail when one is given. Composition happens at construction because the phrase carries no path, so timing cannot bake a wrong locus in; the locus is the renderer's.
3. **`detail` is the escape hatch, and it is a phrase, not a sentence with a locus.** Two causes a template cannot carry: a driver's own text ("cannot start a transaction within a transaction") and a parameter cause ("max_depth must be >= 1, got 0"). A detail never contains a path, never repeats the phrase, and never names a Python keyword. For `invalid` a detail is required: the cause is the content. For `not_found`, `exists`, `not_empty`, `read_only` and `permission_denied` a detail is unusual and the review asks why.
4. **The locus is `path`; the second entry is `data["vfs.target"]`, and the seam rebases both.** Today `classified()` writes the requested row to `data["target"]` in the producer's coordinates and the seam never touches it, so it is a merge discriminator an agent cannot use. The key becomes `vfs.target` (envelope machinery writes only `vfs.`-prefixed keys), `with_mount` and `without_mount` rebase it with `path`'s rule, and a target whose rebased form overflows is kept producer-local under `data["vfs.overflow"]["target"]` exactly as `path` is. Merge identity is unchanged: two errors distinct under one mount are distinct after it. This resolves the 2026-10-08 marker (lean: rebase) by the design rather than by a separate call.
5. **The renderer prints every locus last.** The error line becomes `SEVERITY <path>: <message> (target <vfs.target>) — <hint> (retry:
   <class>)`, the target clause present only when the key is. Nothing
   else in the line changes; spec 155's regrouping of `_render_errors`
   is independent of it.
6. **A hint names no language.** `KIND_CONTRACTS` and every detail use
   caller-neutral wording: "or request the scan tier (`allow_scan`)",
   naming the parameter as a parameter, not as Python. An exception
   raised to a Python caller may name a keyword; it is Python.
7. **The binary-edit refusal is a `wrong_kind` fact.** Today
   `writes.py` emits `unsupported`, a kind the vocabulary reserves for
   capability gates, with a hint that sends the agent to another
   mount. It becomes `classified(wrong_kind, target, detail="binary
   body; replace the bytes through write")`, rendering `Wrong kind:
   binary body; replace the bytes through write`.
8. **Peer kinds keep their prose.** An error decoded from the wire with
   an `x.<vendor>.*` or unknown kind carries the message the peer sent,
   and an unknown kind renders bare, as today. The wire shape of
   `ResultError` does not change: `message` stays a string field,
   populated for every `vfs.*` kind by derivation and for every other
   kind by the peer. No new wire field; `detail` is not stored apart
   from the message it composed. (Considered and declined: a `detail`
   field on the wire. It buys nothing a consumer may use, because no
   consumer may parse prose, and it widens the envelope.)

### The phrase table (proposed; Clay tunes the words)

| Kind | Phrase | Fields | Detail |
|---|---|---|---|
| `not_found` | Not found | | rare |
| `exists` | Already exists | | rare |
| `wrong_kind` | Is {article} {kind} / Wrong kind | `kind` when the occupant's kind is the cause | when it is not (the binary body) |
| `not_empty` | Directory not empty | | rare |
| `unauthenticated` | Unauthenticated | | optional |
| `permission_denied` | Permission denied | | rare |
| `read_only` | Read-only | | optional ("mount default", "prefix rule") |
| `unsupported` | Unsupported | | the verb and the mount, no path |
| `unrecognized` | Unrecognized verb | | the verb |
| `invalid` | Invalid | | required |
| `unindexable_pattern` | Unindexable pattern | | optional |
| `unaddressable` | Unaddressable | | optional |
| `conflict` | Conflict | `version` | optional |
| `busy` | Busy | | optional |
| `cross_mount` | Crosses a mount boundary | | optional |
| `budget_exhausted` | Budget exhausted | | optional |
| `truncated` | Truncated | | the budget that cut it and the refinement |
| `authority_budget` | Authority budget exceeded | | optional |
| `unavailable` | Unavailable | `retry_after_ms` | the failure, driver text allowed |
| `backend_unavailable` | Backend unavailable | `retry_after_ms` | the failure |
| `schema_mismatch` | Schema mismatch | `expected`, `found` | optional |
| `timeout` | Timed out | `retry_after_ms` | optional |
| `cancelled` | Cancelled | | optional |
| `internal` | Internal error | | required |

A kind without a phrase cannot ship: the test in slice A renders every member of `ErrorKind` and fails on a missing one.

## Scope

**Slice A, the verbs and the table.** `results/kinds.py`: the `phrase` member, every row filled, the `unindexable_pattern` hint rewritten. `results/envelope.py`: the constructor's new signature; `vfs.target` written, rebased in both seams, overflow-recorded; the two conveniences kept. `results/render.py`: the target clause. `base.py`: `_error`'s signature. Tests under `tests/results/`: every kind constructed with a path and a target under `/inner`, rebased through `/mine`, rendered; the message contains no `/`-led token, the locus and the target read in `/mine` coordinates, and the round-trip `with_mount` then `without_mount` still holds with the new key. A construction-door gate: `grep -rn "ResultError(" src/vfs` outside `src/vfs/results/` is empty, and no call to `classified` or `_error` passes `message=`.

**Slice B, the migration.** The 109 producer sites move to the constructor. By file: `topology.py` (23), `rights.py` (15), `engine.py` (9), `backend.py` (8), `writes.py` (6), `staging.py` (5), `grep.py` (5), `edges.py` (5), `indexing.py` (4), `editing.py` (3), `glean.py` (3), `descent.py` (3), `segments.py` (2), `reads.py` (2), `signals.py` (1), `session.py` (1), `rerank.py` (1), `permissions.py` (1), and `base.py`'s 25 `_error` calls. The binary edit reclassification lands here. The driver and parameter messages become details; the path variables (`{path}`, `{target}`, `{ancestor}`, `{named}`, `{endpoint}`, `{link}`, `{staged.path}`) become the locus or the target. Tests: 27 files carry 108 assertions on `message` or `error_message`, about 49 of them pinning a path inside the text (`tests/support/grants_contract.py`, `tests/results/test_results.py`, `tests/storage/database/test_grep.py` and the rest). Each moves to the field it was really testing: `kind`, `path`, `data["vfs.target"]`, or the rendered line.

**Out of scope.** The renderer's grouping of errors (spec 155). The exception boundary (`exceptions.py` builds each kind's exception from `message` and attaches the whole result; it keeps doing so). The `validation_message` flattener for pydantic errors, which feeds an `invalid` detail unchanged. Any new kind.

## Acceptance criteria

- Reading a missing `/mine/missing.md` through a mount at `/mine` (parent present) renders `ERROR /mine/missing.md: Not found — Check the path with ls or glob, or create the entry first. (retry: never)`.
- Moving `/mine/a.md` to `/mine/gone/a.md` with no `/mine/gone` renders `ERROR /mine/gone: Not found (target /mine/gone/a.md) — ...`: the locus is the missing ancestor, the target is the requested row, both in the caller's coordinates, and `message` is the bare phrase.
- Every member of `ErrorKind` has a phrase; the slice A test renders each through a mount and finds no `/`-led token in any `message`.
- `grep -rn "ResultError(" src/vfs | grep -v "src/vfs/results/"` is empty; `grep -rn "message=" src/vfs` finds no constructor call.
- No `KindContract.hint`, phrase or detail in `src/` contains `=True` or the word `kwarg`.
- `edit` of a bytes body refuses `wrong_kind` with the message `Wrong kind: binary body; replace the bytes through write`.
- `e.with_mount(m).without_mount(m) == e` holds for an error carrying `vfs.target`.
- `scripts/ci.sh 3.13` green.

## Tasks

0. Done 2026-10-10: ADR 076 (proposed) and the memo `2026-10-10-who-composes-the-error-message.md`. Clay's acceptance of the ADR gates slice A.
1. Slice A.
2. Slice B, in two landings if the review prefers: the storage backend's files, then the router and the tests.

## Landing notes (2026-10-10)

Both slices landed in one pass over `4b598bc`, since the constructor's new signature breaks every producer at once and a half-migrated tree is not green. Where the landing differs from the scope above, the reason:

- **Phrases are plain strings, not templates.** The scope sketched `wrong_kind` as "Is {article} {kind}" filled from fields. A template needs a fallback phrase for the fact that lacks the field (the binary body), which is two phrases for one kind. Instead every phrase is fixed and the varying part is the detail: `wrong_kind("directory", path)` renders `Wrong kind: directory` and carries `data["kind"] = "directory"`; the binary edit renders `Wrong kind: binary body; replace the bytes through write`. One grammar for every kind: phrase, then `: `, then detail.
- **A target equal to the locus is not recorded.** The old discriminator was written even when it repeated `path`; the locus already tells those rows apart, and printing `(target /x)` after `ERROR /x:` is noise. Four tests that read the old key on such facts now read `path`.
- **The constructor takes `source`, for the router alone.** Two coverage records in `base.py` (an unverifiable root, a skipped entry) are minted above the rebase seam and stamp their own bind path as provenance. Without the keyword they would have stayed raw `ResultError(...)` calls and the door gate could not close.
- **A missing detail on `invalid` or `internal` raises `ValueError`.** A producer that omits the cause has a bug; shipping a bare "Invalid" would hide it. The raise is a programming-error signal, not input validation, and `python -O` changes nothing.
- **Facts that named a path in prose now carry it as a field.** The read-only refusal keeps its rule prefix in `data["rule_prefix"]`; a missing edge names its target as the second entry; the render notes carry `data["render_status"]`; the "restore the parent first" refusal moves its locus to the trashed parent and keeps the requested row as the target; the schema mismatch carries `expected` and `found`. Five `StaleSnapshot` contexts that interpolated a destination path were reworded, since they become the `conflict` detail.
- **The replace helper's wording.** `replace_all=True is only allowed with exact matches` became `replace_all applies only to exact matches`, because it feeds an `invalid` detail and rule 6 forbids the keyword form.
- **Suite outcome:** ruff, format and ty green on `src/`, `tests/` and the root `conftest.py`; the full suite green with the 100% coverage gate (3,957 passed, 1,347 skipped engine-leg tests, 100.00% of 11,291 statements). `scripts/ci.sh` was not run, at Clay's ask; the other four engines are untested on the migration.
- **`VFSErrorKind` became `ErrorKind`** in a follow-up commit the same day (Clay). The prefix repeated the package, the values already carry the `vfs.` namespace, its siblings `Severity`, `RetryClass` and `KindContract` are bare, and the prior art (Rust's `io::ErrorKind`, opendal's `ErrorKind`) names it so. `VFSError` keeps its prefix as the package's base exception; `VFSTables` is untouched. The dated ADR and memo keep the old name as written.
