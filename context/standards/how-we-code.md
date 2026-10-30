# How we code

The reusable patterns this repository follows, written so a code review can check a change against them line by line. Each rule is one or two sentences and names the file and line that shows it in the live tree (`src/` and `tests/`; `src2/` and `tests2/` are archived and show nothing). Rules that [CLAUDE.md](../../CLAUDE.md) already states are pointers to it, not copies, so each rule has one home.

Two binding words. **Must** is checked: by a lint test where one exists, by the reviewer otherwise. **Prefer** is the default, and a change that departs from it says why in its docstring.

## 1. Test first, then code

This group is an instruction of how to code, not a record to produce. The order of work in the working tree is the test, then the code; nothing asks for proof that the order was followed, and no lint reads for one.

- **The test comes before the code, and it is seen failing.** A new behaviour's test must be written and run red before the code that turns it green, and a bug's reproducing test before its fix. A test that could not have failed on the base pins nothing.
- **"Test" means the pin at the layer the behaviour lives.** A verb's behaviour is a row in the mirrored test file (`tests/.../test_<module>.py`) or in the conformance contract (`tests/support/storage_contract.py:1`) when every backend must agree; a Rust kernel is a parity row against its oracle in `tests/support/oracles/`; a performance claim is a count pin (statements, calls, rows); a race is a seam test that commits a rival mid-window (`src/vfs/storage/backends/database/seams.py:1`).
- **The spec names the test before it exists.** Each acceptance criterion in a spec names the test file and node id, or the conformance row, that will pin it; the test is written to that name.
- **Tests land in the same commit as the code they pin.** Every commit on `main` is green, so a test never lands ahead of its code or after it.
- **The reviewer may check it.** A reviewer reads each new test, asks which line of the diff makes it pass, and may check out the base and run one red; a test that passes on the base is a finding.
- **The mutant is the referee after landing.** A pinned law names the one-line mutation that breaks it in its docstring and lands as a ledger row that review campaigns replay; see [testing.md](testing.md), "Pins land with their mutant", and [mutant-ledger.md](mutant-ledger.md).

## 2. Boundaries: gate, parse, classify

- **Gate, then act.** A verb must run every check before any work: the single-path funnel refuses, resolves, guards and only then dispatches (`src/vfs/base.py:1709`), and a batch is refused whole before any row is dispatched (`src/vfs/base.py:1773`).
- **Parse at the boundary; carry the proof in the type.** Caller input is parsed once at the edge into a branded type (`Path`, `src/vfs/paths.py:174`) and never re-checked below; a function under the gate takes the brand, not `str`, and the storage seam says a bare `str` is out of contract (`src/vfs/storage/protocol.py:24`). One unchecked constructor per brand, and its docstring lists every call site (`src/vfs/paths.py:221`).
- **Gates never raise.** A gate returns the value or the reason (`ResolvedPath`, `src/vfs/paths.py:359`; `param_violation`, `src/vfs/params.py:502`), and the caller mints the refusal.
- **Failures are `Result` rows, not exceptions.** Every op returns a `Result` (`src/vfs/results/envelope.py:316`); an error is built by `classified(kind, ...)` from the kind table (`src/vfs/results/envelope.py:239`), and `success` is derived from the rows, never stored. A raw exception from an in-process backend is a bug (`src/vfs/storage/protocol.py:30`).
- **Exceptions at two places only.** A constructor argument raises `ValueError` at construction (`src/vfs/storage/backends/database/backend.py:207`), and a caller who wants loud failures wraps with `raise_if_failed` (`src/vfs/exceptions.py:121`). A control-flow signal says so on its class line (`StaleSnapshot`, `src/vfs/storage/backends/database/dialects.py:48`).
- **Per-target classification on reads; whole-batch refusal on writes.** A missing read target classifies beside the healthy rows (`src/vfs/storage/protocol.py:43`); a bad write target refuses the batch before a statement runs (`src/vfs/storage/backends/database/writes.py:327`).
- **`assert` narrows, never validates.** See [CLAUDE.md](../../CLAUDE.md), "Code smells".

## 3. Contracts: declare, don't sniff

- **One ingress table.** A verb's parameters are rows in `PARAMS` (`src/vfs/params.py:139`); the router gate, the drift test (`tests/test_params.py:28`) and the wire schema read that table and nothing else. A new verb or parameter is a new row first.
- **Capabilities are declared.** A backend says what it serves through `capabilities()` and nothing reads its method surface (`src/vfs/storage/protocol.py:7`; `src/vfs/storage/backends/database/backend.py:276` withholds `glean` when the profile has no distance function). Tests gate on the declaration with `@needs` (`tests/support/storage_contract.py:58`).
- **Ports are `Protocol`s; one adapter per technology; specialization is construction-only.** The router depends on the `Supports*` protocols (`src/vfs/storage/protocol.py:113`); `InMemoryStorage` is `DatabaseStorage` pointed at a private file (`src/vfs/storage/backends/memory.py:32`); engine differences live in `DialectProfile` (`src/vfs/storage/backends/database/dialects.py:150`), never in a subclass.
- **Code names no document.** A comment or docstring gives its reason in words and never cites a spec, a memo, a review or a `context/` path; the document cites the code. See [CLAUDE.md](../../CLAUDE.md), "Code comments".

## 4. Storage: bounded, planned, one transaction

- **Never assume SQLite; design to the tightest cap.** See [CLAUDE.md](../../CLAUDE.md), "Production posture".
- **Read facts off the live `Dialect`; a profile field only where SQLAlchemy takes no position.** Every `DialectProfile` field's docstring names the fact SQLAlchemy does not model (`src/vfs/storage/backends/database/dialects.py:150`).
- **Measure, don't remember.** A per-row bind cost is measured by compiling the statement over one and two probe rows (`statement_budget`, `src/vfs/storage/backends/database/dialects.py:763`), so a declared width that undershoots fails at build, never at an engine cap.
- **No statement grows with the batch.** Every `IN` list, bulk insert and bulk update must chunk by `membership_budget` (`src/vfs/storage/backends/database/dialects.py:651`) through `chunked` (`:683`) and merge results, as the write path's snapshot read does (`src/vfs/storage/backends/database/writes.py:284`). A reviewer looks for any loop that builds a statement from caller-sized input without a budget.
- **Plan, then execute.** A write batch is one snapshot read, a pure staging pass that holds no session and runs no SQL (`src/vfs/storage/backends/database/staging.py:1`), then execution of an error-free plan only (`src/vfs/storage/backends/database/writes.py:3`, `:129`).
- **One batch, one transaction, owned by the protocol method.** A builder takes the live session, the tables, the profile and the budgets as its first parameters and never begins or commits (`src/vfs/storage/backends/database/writes.py:17`, `:129`); `_execute_write` opens the one writer transaction (`src/vfs/storage/backends/database/backend.py:1666`).
- **Snapshot reads, guarded writes, declared arbitration, redrive on stale.** A write proves its snapshot still holds or aborts whole (`src/vfs/storage/backends/database/writes.py:14`) and redrives through `with_retry` (`src/vfs/storage/backends/database/engine.py:298`); concurrent create follows the profile's `arbitration` (`src/vfs/storage/backends/database/writes.py:30`).
- **Provision explicitly; verify at first touch.** Schema, extensions and functions are installed by an explicit verb (`install_extensions`, `src/vfs/storage/backends/database/engine.py:271`) and proven by the idempotent first touch (`ensure_ready`, `:252`); the request path never creates, and a test pins that a reopen issues no `CREATE` (`tests/storage/database/test_engine.py:151`).
- **Race windows are named seams.** A window no public call can reach is an `await seam("<verb>:<point>")`, a no-op in production and a hook for a rival in tests (`src/vfs/storage/backends/database/seams.py:1`; `src/vfs/storage/backends/database/writes.py:331`).

## 5. The engine: one seam, oracles referee

- **One Rust engine, no Python fallback.** See [CLAUDE.md](../../CLAUDE.md), "Tooling" and "Code smells".
- **The seam imports nothing from vfs; surface owners dispatch.** `vfs.native` checks the protocol version and hands out the handle (`src/vfs/native.py:1`); the owner module of each surface is the only caller of that surface (`src/vfs/native.py:13`).
- **Every kernel has an oracle, and the oracle never imports the seam.** A readable pure-Python twin in `tests/support/oracles/` pins each kernel by parity (`tests/support/oracles/__init__.py:1`), and a test asserts no oracle touches `vfs.native` (`tests/test_oracles.py:12`).

## 6. Shape of a module

- **Layout by banner.** See [CLAUDE.md](../../CLAUDE.md), "File organization".
- **Imports at the top, always.** See [CLAUDE.md](../../CLAUDE.md), "Imports".
- **Small named types over bare tuples.** A heterogeneous record is a `NamedTuple` or a frozen model, never `parts[2]` (`ResolvedPath`, `src/vfs/paths.py:352`; `ParamSpec`, `src/vfs/params.py:62`; `_FanoutPlan`, `src/vfs/base.py:279`).
- **Constants are named, placed and explained.** A derived constant sits directly under the public one it comes from (`src/vfs/paths.py:56`, `:161`), and a reserve or ceiling carries a two-line comment saying what it holds back (`src/vfs/storage/backends/database/dialects.py:642`).
- **Models are pure.** A domain model never holds a session, a connection or persistence bookkeeping (`src/vfs/models/entry.py:6`); that bookkeeping lives beside the plan that needs it (`src/vfs/storage/backends/database/staging.py:11`).
- **Algebra is a pure fold; policy stays outside it.** `Result.merge` is the fold and `merge_branches` adds the fan-out demotion (`src/vfs/results/envelope.py:339`).
- **The docstring says why; the comment is two lines.** See [CLAUDE.md](../../CLAUDE.md), "Code comments".
- **Reflect on smells after writing.** See [CLAUDE.md](../../CLAUDE.md), "Code smells".

## 7. Tests

- **Mirrored files.** A test file sits at the mirrored path of its source module (`src/vfs/storage/backends/database/reads.py` and `tests/storage/database/test_reads.py`); a new module is a new test file.
- **One contract, zero per-engine conditionals, one subclass per backend.** Behaviour lives in `StorageContract` (`tests/support/storage_contract.py:1`); `test_conformance.py` only wires backends in (`tests/storage/test_conformance.py:1`).
- **Count operations, never the clock.** See [CLAUDE.md](../../CLAUDE.md), "Performance tests". Record statements with `before_cursor_execute` and assert on the list (`tests/storage/database/test_engine.py:146`; `tests/models/test_rows.py:297`).
- **Pins land with their mutant.** See [testing.md](testing.md).
- **Never mock the database.** See [testing.md](testing.md).
- **Fixtures own what they make; engine legs deselect, never skip.** An autouse fixture closes every `DatabaseStorage` a test built (`tests/conftest.py:33`), and a real-engine leg whose `VFS_TEST_<ENGINE>_URL` is unset is deselected at collection (`tests/conftest.py:73`).
- **Heavy tests are marked `slow`, never hand-skipped.** See [CLAUDE.md](../../CLAUDE.md), "Tooling".

## When the rules do not say

Decide by these questions, in order:

1. Was its test written first and seen red on the base?
2. Does it keep the gate whole: is the input parsed once at the edge and carried as a type?
3. Does it stay bounded on the least generous engine at a 10,000-row batch?
4. Does it return a classified `Result` where a caller could see it?
5. Does the test count work rather than time, on a real database?
6. Is it the smallest change that keeps the tree green?

## In one line

Write the test first and watch it fail; then parse once at the edge, declare what you serve, plan before you write, never let a statement grow with the batch, classify every failure as a `Result`, and pin every kernel with an oracle and every cost with a count.
