# Study 5: Code — the patterns the repository follows, written as one standard

This is a study for [the development-process memo](../../2026-10-29-the-development-process-seven-studies-and-what-they-recommend.md), owned by Clay Gendron. Its question: which reusable coding patterns does this repository already follow, which should it adopt, and how should they be written down as one standard a reviewer can check? Its method: read the live tree (`src/` and `tests/` only; `src2/` and `tests2/` untouched) at the files the intention names: `paths.py`, `params.py`, `results/`, `base.py`, `storage/protocol.py`, `storage/backends/database/{dialects,reads,writes,staging,backend,engine,seams}.py`, `native.py`, `models/`, `tests/conftest.py`, `tests/support/oracles/`, `tests/support/storage_contract.py`, `tests/storage/test_conformance.py`, and the count pins in `tests/storage/database/test_engine.py` and `tests/models/test_rows.py`; every pattern below carries a `file:line` from that read. Compared the four existing standards (`python-style.md`, `testing.md`, `tooling.md`, `contributing.md`) against `CLAUDE.md` and against `grep` over `src/`. Read eight online prior-art pages and wasi-python's `docs/contributing/principles.md` and `AGENTS.md` (read-only). Time box 30 minutes; the box was reached after the write-up, with nothing left unread from the list above.

## Sources

- This repository at the working tree of 2026-10-29: `CLAUDE.md`; `context/standards/{python-style,testing,tooling,contributing}.md`; `context/intentions/2026-10-29-the-development-process.md`; `context/README.md`; the source and test files cited inline.
- `~/Git/Repos/wasi_python` at `1431ba6f` (committed 2026-10-28), read-only: `docs/contributing/principles.md`, `AGENTS.md` ("Code speaks for itself", 2026-10-20).
- Google Python Style Guide, https://google.github.io/styleguide/pyguide.html (read 2026-10-29).
- Alexis King, "Parse, don't validate", https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/ (read 2026-10-29).
- Alistair Cockburn, "Hexagonal architecture", https://alistair.cockburn.us/hexagonal-architecture/ (read 2026-10-29).
- Django, "Design philosophies", https://docs.djangoproject.com/en/5.2/misc/design-philosophies/ (read 2026-10-29).
- Kubernetes, "API conventions", https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md (read 2026-10-29).
- Hynek Schlawack, "Subclassing in Python Redux", https://hynek.me/articles/python-subclassing-redux/ (read 2026-10-29).
- SQLAlchemy, "Performance" FAQ, https://docs.sqlalchemy.org/en/20/faq/performance.html, and "Develop", https://www.sqlalchemy.org/develop.html (read 2026-10-29).
- pydantic, "Contributing", https://pydantic.dev/docs/validation/latest/get-started/contributing/ (read 2026-10-29).
- Polars, "Contributing", https://docs.pola.rs/development/contributing/ (read 2026-10-29).
- orjson README, https://github.com/ijl/orjson/blob/master/README.md (read 2026-10-29).

## What the repository does today

Each paragraph names one pattern, says what it means in plain words, and points at the code. All labelled READ: I opened the file at that line.

**Gate, then act.** Every public verb checks its inputs first and does work only after every check has passed. The router's single-path funnel refuses a closed namespace, resolves the path, runs the busy guard and the entry gate, and only then dispatches (`src/vfs/base.py:1709-1745`). For a batch, all gates run before any dispatch, so a batch that touches one bad entry is refused whole (`src/vfs/base.py:1773-1778`). The same shape repeats inside storage: the write builders adjudicate the whole batch before any statement runs (`src/vfs/storage/backends/database/writes.py:3-7`). READ.

**Parse at the boundary and carry the proof in the type.** A path that has passed the gate becomes a `Path`, a `str` subclass that is canonical and validated by construction (`src/vfs/paths.py:174-233`). There is one gate, `resolve_path`, which never raises and returns either a `Path` or a reason (`src/vfs/paths.py:359-392`), and one unchecked construction site, `_brand`, whose docstring lists exactly where it may be called (`src/vfs/paths.py:221-233`). The storage seam then declares that a bare `str` is out of contract (`src/vfs/storage/protocol.py:24-30`). This is "parse, don't validate" in practice: the check runs once, and the type remembers it. READ.

**Classify failures as `Result` rows, never as exceptions.** Every op returns a `Result`; a raw exception from an in-process backend is a bug (`src/vfs/storage/protocol.py:30-36`). An error is built by the one constructor `classified(kind, path, detail=...)`, from a kind vocabulary with a contract table, never from prose (`src/vfs/results/envelope.py:239-285`, `src/vfs/results/kinds.py:152`). `success` is a derived property — true if no fatal row — so a result can never say "ok" beside evidence that it is not (`src/vfs/results/envelope.py:316-355`). Callers who want exceptions wrap at the boundary with `raise_if_failed` (`src/vfs/exceptions.py:121-135`). Configuration errors are the one exception: a constructor with a bad argument raises `ValueError` at construction time (`src/vfs/storage/backends/database/backend.py:205-216`). READ.

**One declared ingress table, read by three consumers.** The per-verb parameter contract is a table of `ParamSpec` rows in a leaf module; the router's gate, the signature-drift test, and the wire schema all read it (`src/vfs/params.py:1-11`, `src/vfs/params.py:139`). `param_violation` is pure and total — it returns the first problem as a string and the router mints the refusal (`src/vfs/params.py:502-527`). The drift test asserts the table and the public signatures never diverge (`tests/test_params.py:19-33`). READ.

**Capabilities are declared, never sniffed.** A backend states its op set through `capabilities()`; the protocol docstring forbids structural sniffing (`src/vfs/storage/protocol.py:7-11`). `DatabaseStorage.capabilities()` withholds `glean` when the dialect profile has no distance function (`src/vfs/storage/backends/database/backend.py:282-294`). The conformance suite gates each test family on the declared set with `@needs(...)`, not on `hasattr` (`tests/support/storage_contract.py:21-24`, `:58`). READ.

**Ports and adapters.** The router depends on `typing.Protocol` families (`SupportsRead`, `SupportsMutation`, ...) and calls nothing else (`src/vfs/storage/protocol.py:113-482`). There is one database adapter; the in-memory backend is a construction-only subclass that points it at a private SQLite file, so one code path serves every engine (`src/vfs/storage/backends/memory.py:1-16`, `:30-36`). Engine differences live in a data object, the `DialectProfile`, not in subclasses (`src/vfs/storage/backends/database/dialects.py:150`). READ.

**Read facts off the live `Dialect`; a profile field only where SQLAlchemy takes no position.** The profile docstring justifies each field by naming the fact SQLAlchemy does not model — the `IN`-list cap, `VALUES`-join support, bracket classes in `LIKE` (`src/vfs/storage/backends/database/dialects.py:150-200`). `statement_budget` measures a statement's real per-row bind cost by compiling it over one and two probe rows, rather than remembering the number (`src/vfs/storage/backends/database/dialects.py:763-791`). READ.

**Chunk every membership list by the declared budget.** `membership_budget` is the tighter of the `IN`-list cap and the bind-parameter budget net of a reserve; `chunked` slices by it (`src/vfs/storage/backends/database/dialects.py:651-657`, `:683-687`). The write path's one snapshot read goes through `rows_by_path` with that budget (`src/vfs/storage/backends/database/writes.py:284-312`). Pattern fans have their own `arm_budget` with a measured ceiling (`src/vfs/storage/backends/database/dialects.py:666-676`). The rule: no statement grows with the batch. READ.

**Plan, then execute.** A write batch is one snapshot read, a pure in-memory staging pass that holds no session and runs no SQL, and then execution only of an error-free plan (`src/vfs/storage/backends/database/staging.py:1-10`, `src/vfs/storage/backends/database/writes.py:129-177`). `_finish` returns early with the plan's errors before the first mutation statement (`src/vfs/storage/backends/database/writes.py:315-328`). READ.

**One batch, one transaction, owned by the protocol method.** Builders take the op's live session and never begin or commit (`src/vfs/storage/backends/database/writes.py:18-20`). The backend's `_execute_write` opens the one writer transaction (`src/vfs/storage/backends/database/backend.py:1666-1673`). Builders are plain `async` functions whose first parameters are session, tables, profile and the budgets — the same signature shape everywhere (`src/vfs/storage/backends/database/writes.py:129-140`, `src/vfs/storage/backends/database/reads.py:149`). READ.

**Snapshot reads, guarded writes, declared conflict mode, redrive on a stale snapshot.** Every parent bump proves the parent still lives at the snapshot's address, or the batch aborts and redrives (`src/vfs/storage/backends/database/writes.py:12-17`). Concurrent create follows the profile's declared `arbitration` (`upsert` or `catch_retry`) (`src/vfs/storage/backends/database/writes.py:30-34`). `StaleSnapshot` is a control-flow signal, marked as such with the `noqa` that names it (`src/vfs/storage/backends/database/dialects.py:48-60`), and `with_retry` restarts the whole op with jittered backoff (`src/vfs/storage/backends/database/engine.py:252-266`, `:296`). READ.

**Provisioning explicit, verification at first touch.** `ensure_ready` is the idempotent first touch; it proves the schema and the distance function and returns a classified error otherwise (`src/vfs/storage/backends/database/engine.py:252-269`). `install_extensions` is the explicit half, "never called by first touch" (`src/vfs/storage/backends/database/engine.py:271-294`). A test pins that reopening a database issues no `CREATE` (`tests/storage/database/test_engine.py:144-151`). READ.

**One Rust engine behind one seam; surface owners dispatch.** `vfs.native` imports the extension, checks the protocol version, and raises an `ImportError` naming the fix when either is wrong (`src/vfs/native.py:1-42`). It imports nothing from the rest of vfs, and each surface's owner module does the dispatch (`src/vfs/native.py:12-19`). READ.

**Oracle-pinned kernels.** Readable pure-Python twins of each engine surface live in `tests/support/oracles/` and ship in no wheel (`tests/support/oracles/__init__.py:1-16`). A lint-style test walks the package and asserts no oracle imports the seam, because an oracle that dispatched to the engine would referee nothing (`tests/test_oracles.py:12-18`). READ.

**Mirrored test files, one conformance contract, one subclass per backend.** Test files mirror source modules (`src/.../database/reads.py` ↔ `tests/storage/database/test_reads.py`; the listing of `tests/storage/database/` matches the module list). The storage contract is one class with zero per-engine conditional assertions (`tests/support/storage_contract.py:1-24`); `test_conformance.py` only wires backends in, one subclass each (`tests/storage/test_conformance.py:1-20`). READ.

**Count operations, never the clock.** Pins record statements through SQLAlchemy's `before_cursor_execute` event and assert on the list (`tests/storage/database/test_engine.py:144-151`; `tests/models/test_rows.py:297-304`). No test asserts elapsed time. READ.

**Named seams for race windows.** A race window that no public call can reach is a named `await seam("write:before-apply")` in production code; a test installs a handler that commits a rival there, then drives the real verb (`src/vfs/storage/backends/database/seams.py:1-18`, `src/vfs/storage/backends/database/writes.py:329-331`). READ.

**Fixtures own what they make; engine legs deselect, never skip.** An autouse fixture tracks every `DatabaseStorage` a test builds and closes it on the test's own loop (`tests/conftest.py:33-56`). Real-engine legs are deselected at collection when `VFS_TEST_<ENGINE>_URL` is unset, because a skip still pays fixtures and clutters the summary (`tests/conftest.py:63-91`). READ.

**Small named types instead of bare tuples; constants named and placed.** Gate outcomes, parameter rows, profile hints and fan-out plans are `NamedTuple`s (`src/vfs/paths.py:352`, `src/vfs/params.py:62`, `src/vfs/storage/backends/database/dialects.py:76`, `src/vfs/base.py:279`). A derived constant sits under the public one it comes from (`src/vfs/paths.py:56`, `:161`). Reserves carry a two-line comment saying what they hold back (`src/vfs/storage/backends/database/dialects.py:642-648`). READ.

**Module layout by banner.** Every module runs docstring, future import, imports, constants, public groups under three-line banners, internal helpers last (`src/vfs/paths.py:170`, `:395`, `:482`, `:614`, `:644`, `:844`; `src/vfs/params.py:29`, `:498`, `:530`). No file in `src/vfs/` lacks `from __future__ import annotations`; no file uses a relative import; the rule is already uniform. READ.

**Models are pure; persistence bookkeeping lives beside the plan.** Domain models are plain pydantic models never bound to a session (`src/vfs/models/entry.py:6`). The staged row's `entry_id`, `base_version` guard and persistence pass live in `staging.py` beside the plan, "and not among the session-free models" (`src/vfs/storage/backends/database/staging.py:11-17`). READ.

**Result algebra is a pure fold; policy stays outside it.** `|` is associative and idempotent with `Result()` as identity; `merge` is the plain fold and `merge_branches` adds the fan-out demotion (`src/vfs/results/envelope.py:338-347`). READ.

**The docstring says why; the comment is two lines; code names no document.** The writes module docstring explains plan-then-execute, arbitration and versions in words (`src/vfs/storage/backends/database/writes.py:1-37`). CLAUDE.md already forbids story, spec and decision numbers in comments and docstrings. READ.

**Test first — held by the mutant, not by the order of commits.** The owner's ruling (2026-10-29) is that the code stage is tests first: a new behaviour's test is written and seen failing before the code, and a bug's reproducing test before its fix. Where vfs does this today: `testing.md`'s "Pins land with their mutant" asks that every pinned law be proven by a one-line mutation that breaks it, with the mutation named in the test docstring; 68 test files name their mutant (`tests/models/test_code_grams.py:473-480`, the "cap mutant" rows), the ledger holds 56 replayable rows (`context/standards/mutant-ledger.md`), and 89 of 842 commit messages name a mutation or a kill. The kernel fixes of 2026-10-24 landed "each with a count pin proven to bite" (`context/specs/STATUS.md:8`), and one archived spec was built "tests first throughout" (`context/specs/archive/091-glob-namespace-routing/spec.md:4`). Where it does not: no commit message in the history says "seen failing", "red on the base" or "fails before" (zero hits), so the order — test red, then code green — is nowhere recorded for a reader; `commits-and-prs.md` asks only for a "Test plan: what was checked" (`context/standards/commits-and-prs.md:64`); and the proof is a *mutation after the fact* (apply a one-line break, watch the pin fail), which proves the pin has teeth but not that it was written first. The repository has the referee (the mutant) and lacks the record (the red run). READ.

## What the sources say

**Google Python Style Guide** (READ). Each language rule has Definition, Pros, Cons, Decision; style rules are stated directly with yes/no examples. Relevant decisions: imports at the top of the file; type hints on public APIs with a checker in the build; nested functions only to close over a local; small `try` blocks. The lesson for our page: a rule reads best as *decision first*, with the reason in one sentence after it.

**"Parse, don't validate"** (READ). A validator checks and throws the knowledge away; a parser checks and returns a more precise type that keeps it. Parse at the boundary once, so a later check cannot be forgotten and nothing is half-done when a late error surfaces. Our `Path` brand and the `resolve_path` gate are this idea exactly; naming it gives the reviewer one word for the check.

**Hexagonal architecture** (READ). A port is a purposeful conversation defined by an API; an adapter is the technology-specific piece that plugs into it; the core must not know which adapter it talks to, which is what lets an in-memory adapter stand in for the database under test. Our `Supports*` protocols are ports; `DatabaseStorage` is the adapter; the conformance suite is the proof that the core cannot tell.

**Django design philosophies** (READ). One page, grouped by component, each philosophy a bold heading and one or two paragraphs with the reason. Named entries include loose coupling, DRY, explicit over implicit, SQL efficiency ("as few statements as possible"). The format is the one a contributor can scan.

**Kubernetes API conventions** (READ). Rules are imperatives with a reason and often the past problem that caused them; MUST/SHOULD/MAY mark how binding each is; examples are labelled non-normative. Several are shaped like ours: optional versus required fields marked explicitly; booleans treated with suspicion because they grow into enums; defaults never override a user's value. The lesson: state the binding level, and attach the incident when there is one.

**Hynek Schlawack on subclassing** (READ). Never mix the three kinds of subclassing — code sharing, interfaces, specialization. Interfaces take `typing.Protocol`; code sharing takes adapters, decorators or functions; specialization only where the subclass is the base plus properties and substitution holds. Our tree already matches: protocols for interfaces, one adapter, `InMemoryStorage` as a construction-only specialization.

**SQLAlchemy** (READ). Its performance FAQ diagnoses with `cProfile` call counts and `before_cursor_execute` statement logging, read alongside times — the same event our count pins use. Its develop page covers process (issue first, Gerrit review, pre-commit); the dialect-level test suite is documented elsewhere, so that part is INFERRED from the test code in the SQLAlchemy clone, not from this page.

**pydantic** (READ). Tests with every change, docs with every feature, Google-style docstrings on every public name, `ruff` for lint and format, a Rust core in a separate crate with its own symlinked tests.

**Polars** (READ). Rust in `crates/`, Python in `py-polars/`; the Python tests are the main check on behaviour "even when you only change Rust"; one `make pre-commit` runs ruff, mypy, rustfmt, clippy; failing it blocks the PR. The seam itself (pyo3, maturin) is not named on the page — INFERRED from the build files.

**orjson** (READ). Ships only as a compiled module, documents the exact wheel matrix, tests against external fixture suites and naughty-strings corpora, and keeps benchmarks in separate scripts outside the test run. The pattern: no fallback, honest platform table, clock outside the tests.

**wasi-python `principles.md` and `AGENTS.md`** (READ, commit `1431ba6f`). Rules are short declaratives under bold heads: "Every input is pinned", "Tests count operations, never time", "Prior art is studied, never copied", "Code speaks for itself" — a code file names no specification, memo, review or `context/` path; comments give the reason in words; the number lives in the document that cites the file. The page ends with "When the rules do not say", an ordered list of tie-break questions, and "In one line". That closing shape is worth adopting.

## What is stale in `context/standards/`

Checked with `grep` over `src/` on 2026-10-29.

- **`contributing.md` says "Do not treat the repo as greenfield."** `CLAUDE.md` says the opposite: "This is still greenfield work: do not discount ideas because they would require a big refactor." The standard loses; the sentence must go.
- **`contributing.md` names `VFSResult` and `DatabaseFileSystem`.** Neither exists in `src/` (zero hits). The live names are `Result` (`src/vfs/results/envelope.py:316`) and `DatabaseStorage` (`src/vfs/storage/backends/database/backend.py`). Its "backend subclass overrides the hot path" advice is also gone: there is one adapter and engine differences live in `DialectProfile`.
- **`contributing.md` names `install_*()` / `verify_*()` and `__meta__/edges/in`.** The pattern survives under `install_extensions` / `ensure_ready` (`engine.py:252`, `:271`); `__meta__` has zero hits in `src/`. The namespace rules now live in `paths.py` constants (`METADATA_ROOT`, `TRASH_ROOT`, `AGENTS_ROOT`).
- **`python-style.md`** lists per-file ignores for `src_old/**`, `tests_old/**` (now `src2/`, `tests2/`); says `from __future__ import annotations` only "where it helps" (CLAUDE.md's layout rule puts it in every module, and every module has it); describes `VirtualFileSystem` as a sync facade (it is the async router, `base.py:357`); names an `_{op}_impl` hook pattern that has four incidental hits and is not load-bearing; and tells readers to use `exceptions.py` from public surfaces, where the live rule is "every op returns a `Result`; exceptions only at `raise_if_failed`".
- **`testing.md`** says `fail_under = 99` (it is 100, `pyproject.toml:167`), `--mssql` and `docker/mssql/` (now `VFS_TEST_<ENGINE>_URL` and `docker/compose.test.yml`), and cites `tests/test_database_fs.py` (does not exist). Its "pins land with their mutant", "don't mock the database", and "engine legs are reentrant" sections are current and should carry into the new page by pointer.
- **`tooling.md`** says `uv pip`, "not `uv sync`" (CLAUDE.md and `scripts/ci.sh` use `uv sync --all-extras --group dev`), `uvx ruff` (ci.sh runs `uv run ruff`), and "`ty` runs on `src/` only" (ci.sh runs `ty check src/ tests/`).

The four pages overlap and disagree with each other and with `CLAUDE.md`. The fix is one `how-we-code.md` that owns the coding patterns, points at `CLAUDE.md` for the rules already there, and retires `contributing.md`; `python-style.md`, `testing.md` and `tooling.md` get corrected in the same landing or folded in.

## The recommended standard

The page is one file, `context/standards/how-we-code.md`. Each rule is one or two sentences a reviewer can check against a diff, followed by its example location. Rules already in `CLAUDE.md` appear as pointers so there is one source for each. Binding words: **must** is checked by review or lint; **prefer** is a default a reviewer may ask about.

```markdown
# How we code

- **Status:** standard
- **Date:** 2026-10-29
- **Owner:** Clay Gendron

The reusable patterns this repository follows, written so a code review can
check a change against them line by line. A rule names the file that shows
it. Rules that `CLAUDE.md` already states are pointers here, not copies.

Words: **must** is checked (by a lint test where one exists, by the reviewer
otherwise); **prefer** is the default, and a change that departs from it
says why in its docstring.

## 1. Test first, then code

- **The test comes before the code, and it is seen failing.** A new
  behaviour gets its test written and run red before the code that turns
  it green; a bug gets its reproducing test before its fix. A change whose
  tests could not have failed on the base is not finished.
- **"Test" means the pin at the layer the behaviour lives.** A verb's
  behaviour is a row in the mirrored test file (`tests/.../test_<module>.py`)
  or in the conformance contract (`tests/support/storage_contract.py`)
  when every backend must agree; a Rust kernel is a parity row against
  its oracle in `tests/support/oracles/`; a performance claim is a count
  pin (statements, calls, rows) that fails on the base; a race is a seam
  test that commits a rival mid-window.
- **The author records the red run.** The commit message's test plan
  names each new test and says it was seen failing on the base, with the
  failure's shape in a few words (`test_x: AssertionError, 8 statements,
  expected 6`); the test's docstring names the one-line mutation that
  breaks it, as `testing.md` already asks. A spec's landing notes carry
  the same line per acceptance criterion.
- **The reviewer checks it.** The reviewer reads every new test, asks
  which line of the diff makes it pass, and checks out the base to run
  one of them red when the message does not convince; a test that passes
  on the base, or a test with no named mutant, is a finding.
- **The mutant is the referee after landing.** A pinned law lands as a
  ledger row and review campaigns replay it. → `context/standards/testing.md`,
  "Pins land with their mutant"; `context/standards/mutant-ledger.md`.

## 2. Boundaries: gate, parse, classify

- **Gate, then act.** A verb runs every check before any work, and a batch
  is refused whole before any row is dispatched. `src/vfs/base.py:1709`,
  `:1773`.
- **Parse at the boundary; carry the proof in the type.** Caller input is
  parsed once at the edge into a branded type (`Path`, `RelativePath`) and
  never re-checked inside. A function below the gate takes the branded
  type, not `str`. One unchecked constructor per brand, and its docstring
  lists every call site. `src/vfs/paths.py:174`, `:221`, `:359`;
  `src/vfs/storage/protocol.py:24`.
- **Gates never raise.** A gate returns the value or the reason
  (`ResolvedPath`, `param_violation`); the caller mints the refusal.
  `src/vfs/paths.py:359`, `src/vfs/params.py:502`.
- **Failures are `Result` rows, not exceptions.** Every op returns a
  `Result`. An error is built by `classified(kind, ...)` from the kind
  table; `invalid` and `internal` must carry a detail. `success` is
  derived, never stored. A raw exception from an in-process backend is a
  bug. `src/vfs/results/envelope.py:239`, `:316`;
  `src/vfs/storage/protocol.py:30`.
- **Exceptions at two places only.** Constructor arguments raise
  `ValueError` at construction; callers who want loud failures wrap with
  `raise_if_failed`. Control-flow signals (`StaleSnapshot`) say so in their
  class line. `src/vfs/storage/backends/database/backend.py:205`,
  `src/vfs/exceptions.py:121`,
  `src/vfs/storage/backends/database/dialects.py:48`.
- **Per-target classification on reads; whole-batch refusal on writes.**
  A missing read target classifies beside the healthy rows; a bad write
  target refuses the batch before a statement runs.
  `src/vfs/storage/protocol.py:44`,
  `src/vfs/storage/backends/database/writes.py:315`.
- **`assert` narrows, never validates.** → `CLAUDE.md`, Code smells.

## 3. Contracts: declare, don't sniff

- **One ingress table.** A verb's parameters are rows in `params.py`; the
  router gate, the drift test and the wire schema read that table and
  nothing else. A new verb or parameter is a new row first.
  `src/vfs/params.py:139`; `tests/test_params.py:19`.
- **Capabilities are declared.** A backend says what it serves through
  `capabilities()`; nothing reads its method surface. Tests gate on the
  declaration with `@needs`. `src/vfs/storage/protocol.py:7`,
  `src/vfs/storage/backends/database/backend.py:282`,
  `tests/support/storage_contract.py:58`.
- **Ports are `Protocol`s; one adapter per technology; specialization is
  construction-only.** The router depends on `Supports*` protocols. Engine
  differences live in `DialectProfile`, never in a subclass.
  `src/vfs/storage/protocol.py:113`, `src/vfs/storage/backends/memory.py:30`.
- **Code names no document.** A comment or docstring gives its reason in
  words and never cites a spec, memo, review or `context/` path; the
  document cites the code. → `CLAUDE.md`, Code comments.

## 4. Storage: bounded, planned, one transaction

- **Never assume SQLite; design to the tightest cap.** → `CLAUDE.md`,
  Production posture.
- **Read facts off the live `Dialect`; a profile field only where
  SQLAlchemy takes no position**, and its docstring names that gap.
  `src/vfs/storage/backends/database/dialects.py:150`.
- **Measure, don't remember.** A per-row bind cost is measured by
  compiling the statement over one and two probe rows; a declared width
  that undershoots the measurement fails loudly at build, never at an
  engine cap. `src/vfs/storage/backends/database/dialects.py:763`.
- **No statement grows with the batch.** Every `IN` list, bulk insert and
  bulk update chunks by `membership_budget` / `statement_budget` through
  `chunked` and merges results. A reviewer looks for any loop that builds
  a statement from caller-sized input without a budget.
  `src/vfs/storage/backends/database/dialects.py:651`, `:683`;
  `src/vfs/storage/backends/database/writes.py:284`.
- **Plan, then execute.** A write batch is one snapshot read, a pure
  staging pass that holds no session and runs no SQL, then execution of
  an error-free plan only. `src/vfs/storage/backends/database/staging.py:1`,
  `src/vfs/storage/backends/database/writes.py:129`.
- **One batch, one transaction, owned by the protocol method.** Builders
  take the live session and the tables, profile and budgets as their
  first parameters; they never begin or commit.
  `src/vfs/storage/backends/database/writes.py:18`, `:129`;
  `src/vfs/storage/backends/database/backend.py:1666`.
- **Snapshot reads, guarded writes, declared arbitration, redrive on
  stale.** A write proves its snapshot still holds (a guarded update with
  the row's version) or aborts whole and redrives through `with_retry`;
  concurrent create follows the profile's `arbitration`.
  `src/vfs/storage/backends/database/writes.py:12`, `:30`;
  `src/vfs/storage/backends/database/engine.py:296`.
- **Provision explicitly; verify at first touch.** Schema, extensions and
  functions are installed by an explicit verb (`install_extensions`) and
  proven by the idempotent first touch (`ensure_ready`); the request path
  never creates. `src/vfs/storage/backends/database/engine.py:252`, `:271`;
  `tests/storage/database/test_engine.py:144`.
- **Race windows are named seams.** A window no public call can reach is
  an `await seam("<verb>:<point>")`, a no-op in production and a hook for a
  rival in tests. `src/vfs/storage/backends/database/seams.py:1`.

## 5. The engine: one seam, oracles referee

- **One Rust engine, no Python fallback.** → `CLAUDE.md`, Tooling and
  Code smells.
- **The seam imports nothing from vfs; surface owners dispatch.**
  `vfs.native` checks the protocol version and hands out the handle; the
  owner module of each surface (`models.lexical`, `models.postings`, ...)
  is the only caller of that surface. `src/vfs/native.py:1`.
- **Every kernel has an oracle, and the oracle never imports the seam.**
  A readable pure-Python twin in `tests/support/oracles/` pins each
  kernel by parity; a lint test asserts no oracle touches `vfs.native`.
  `tests/support/oracles/__init__.py:1`, `tests/test_oracles.py:12`.

## 6. Shape of a module

- **Layout by banner.** → `CLAUDE.md`, File organization.
- **Imports at the top, always.** → `CLAUDE.md`, Imports.
- **Small named types over bare tuples.** A heterogeneous record is a
  `NamedTuple` (or a frozen model), never `parts[2]`.
  `src/vfs/paths.py:352`, `src/vfs/params.py:62`.
- **Constants are named, placed and explained.** A derived constant sits
  under the public one; a reserve or ceiling carries a two-line comment
  saying what it holds back. `src/vfs/paths.py:56`, `:161`;
  `src/vfs/storage/backends/database/dialects.py:642`.
- **Models are pure.** A domain model never holds a session, a connection
  or persistence bookkeeping; that lives beside the plan that needs it.
  `src/vfs/models/entry.py:6`,
  `src/vfs/storage/backends/database/staging.py:11`.
- **Algebra is a pure fold; policy stays outside it.** `Result.merge` is
  the fold; `merge_branches` adds the fan-out policy.
  `src/vfs/results/envelope.py:338`.
- **The docstring says why; the comment is two lines.** → `CLAUDE.md`,
  Code comments.
- **Reflect on smells after writing.** → `CLAUDE.md`, Code smells.

## 7. Tests

- **Mirrored files.** One test file per source module at the mirrored
  path; a new module is a new test file. `tests/storage/database/`.
- **One contract, zero per-engine conditionals, one subclass per
  backend.** Behaviour lives in `StorageContract`; `test_conformance.py`
  only wires backends in. `tests/support/storage_contract.py:1`,
  `tests/storage/test_conformance.py:1`.
- **Count operations, never the clock.** → `CLAUDE.md`, Performance tests.
  Record statements with `before_cursor_execute` and assert on the list.
  `tests/storage/database/test_engine.py:144`.
- **Pins land with their mutant.** → `context/standards/testing.md`.
- **Never mock the database.** → `context/standards/testing.md`.
- **Fixtures own what they make; engine legs deselect.**
  `tests/conftest.py:33`, `:63`.
- **Heavy tests are marked `slow`, never hand-skipped.** → `CLAUDE.md`,
  Tooling.

## When the rules do not say

Decide by these questions, in order:

1. Was its test written first and seen red on the base?
2. Does it keep the gate whole — is the input parsed once at the edge and
   carried as a type?
3. Does it stay bounded on the least generous engine at a 10,000-row batch?
4. Does it return a classified `Result` where a caller could see it?
5. Does the test count work rather than time, on a real database?
6. Is it the smallest change that keeps the tree green?

## In one line

Write the test first and watch it fail; then parse once at the edge,
declare what you serve, plan before you write, never let a statement grow
with the batch, classify every failure as a `Result`, and pin every kernel
with an oracle and every cost with a count.
```

Three rules in the skeleton are **adoptions**, not yet uniformly held: "Test first, seen failing" has the referee (the mutant) but no record of the red run in any of 842 commit messages; "Code names no document" is in `CLAUDE.md` but has no lint test; "every kernel has an oracle" is true today but nothing pins that a new `_native` surface gets one. Each gets a check below.

## Which rules a lint test or `ruff` can hold, and which need a reviewer

| Rule | Held by | How |
|---|---|---|
| Test first, seen failing | commit-message lint plus reviewer | a lint test (or a `scripts/ci.sh` step) reads the landing commit's test plan and refuses a commit that touches `src/` without naming a new or changed test and its red run; the reviewer runs one named test on the base and expects red |
| Every pinned law names its mutant | lint test (new) plus the ledger | a test file under `tests/` that adds a `test_` function must carry a docstring; a review campaign replays the ledger (`testing.md`) |
| Imports at the top; sorted; no relative | `ruff` (`I`, `E402`, `TID252`) and a lint test for function-local imports | `ruff` already selects `I`; add `TID252` (ban relative imports) and `PLC0415` (import outside top level) to `pyproject.toml` |
| Layout by banner, future import present | lint test | walk `src/vfs`, assert `from __future__ import annotations` and that every `# ----` banner block follows the docstring/imports/constants order |
| Comments two lines max; no document names in code | lint test (new) | regex over `#` runs and docstrings in `src/` and `tests/` for runs over two lines and for `spec `, `ADR `, `context/`, `story ` tokens — the rule wasi-python holds the same way |
| One ingress table; signatures match | lint test (exists) | `tests/test_params.py:19` |
| Oracles never import the seam | lint test (exists) | `tests/test_oracles.py:12` |
| Every `_native` surface has an oracle | lint test (new) | compare `_native.pyi` exports with the oracle modules' names |
| `assert` narrows only | reviewer, aided by `ruff` `S101` in `src/` | the linter flags every `assert`; the reviewer confirms each follows a gate |
| No `time.perf_counter` / elapsed asserts in tests | lint test (new) | grep `tests/` for `perf_counter`, `monotonic`, `elapsed` in an `assert` |
| Gate then act; per-target vs whole-batch | reviewer | read the verb top to bottom; every early return before the first dispatch |
| Parse at the boundary; `str` below the gate | `ty` plus reviewer | annotate builders with `Path`; `ty` catches a `str` passed in; the reviewer catches a re-validation |
| Failures as `Result`; exceptions only at the two places | reviewer, aided by `ruff` `TRY` family | add `TRY` to catch bare raises in op paths; reviewer confirms `classified(...)` use |
| Read facts off `Dialect`; profile field justified | reviewer | every new `DialectProfile` field names the SQLAlchemy gap in the docstring |
| No statement grows with the batch | reviewer, plus the `scale_review` skill | look for `in_(...)`, `insert().values(rows)` fed by caller input without `chunked` |
| Plan then execute; one transaction | reviewer | a builder that calls `begin`, `commit` or `rollback` is a finding |
| Provision explicitly | lint test (exists) | `tests/storage/database/test_engine.py:144` pins no `CREATE` on reopen |
| Mirrored test files | lint test (new) | for each `src/vfs/**/x.py` (non-`__init__`) assert `tests/**/test_x.py` exists |
| Conformance has no per-engine conditionals | lint test (new) | grep `storage_contract.py` for `dialect`, `sqlite`, `postgres`, `mssql`, `oracle` |
| Small named types; constants placed | reviewer | the smell list in `CLAUDE.md` |

The lint tests belong in one place, `tests/lint/`, run by the gate (`scripts/ci.sh`) and by `uv run pytest`; wasi-python keeps the same split and runs its writing rules in a `lint` step.

## One line

Write `how-we-code.md` as about thirty-five one-sentence rules in seven groups, test-first at the top, each pointing at the file that shows it; hold the mechanical ones with `ruff` and a `tests/lint/` package, record the red run in the commit's test plan, leave the judgment ones to the reviewer, and retire `contributing.md`, whose greenfield sentence and `VFSResult`/`DatabaseFileSystem` names no longer match the tree.
