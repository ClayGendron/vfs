---
name: test_review
description: Review the tests of a diff or branch — not the code — asking whether they actually pin the contract the code declares. Use when the user asks to "review the tests", "check test coverage" of a change, asks "would a test catch this", wants to know if a contract is pinned, or before landing a change whose tests were written alongside it.
---

# Test review — do the tests pin the contract?

A procedure for reviewing the **tests** of a change, not the code. The
question is never "is there a test near this code" or "is coverage
high" — executing a line proves nothing about detecting a bug in it.
The question is: **for each promise the code makes, which test fails
when that promise breaks?** A promise with no failing-test is an
unpinned contract, and unpinned contracts drift silently.

Ground rules for this repo: `tests/` is the only live suite (`uv run
pytest tests/ -q`); contracts live in docstrings and `context/specs/`;
the two storage backends (`src/vfs/storage/backends/memory.py` and
`src/vfs/storage/backends/database/`) must behave identically, with
shared behavior pinned in `tests/storage_conformance.py` and only
backend-specific facts in the per-backend test files.

## Process

### 1. Trace contracts to tests

List every behavioral clause the changed code declares: docstring
promises, error classifications returned, ordering guarantees,
atomicity claims, boundary values (budgets, caps, chunk sizes), and
spec clauses the change claims to implement. For each clause, find the
specific test that would fail if the clause broke — name it, don't
gesture at a file. Build a table:

| Clause (code file:line) | Pinning test (test file:line) or UNPINNED |

A clause is pinned only if some assertion *distinguishes* the promised
behavior from a plausible wrong one. "A test calls this function" is
not pinning.

### 2. Think in mutations

For each key changed line, ask: if I flipped this condition, off-by-
one'd this bound, swapped `<` for `<=`, reordered these two calls, or
deleted this call entirely — **which test fails?** Name the test. If
you cannot name one, that surviving mutation is a finding: the line is
executed but unchecked. Prioritize mutations on branches (error
classification, capability gates, chunk boundaries) and on calls whose
effect is only visible later (version stamps, cleanup, ordering).
Do not run a mutation tool; reason it out and cite the lines.

### 3. Audit error paths

Untested error handling is where catastrophic failures live. Every
classified error the changed code can return (each `VFSErrorKind` it
can mint, each raise, each per-row batch classification) must be
*produced* by at least one test — a test that constructs the offending
input and asserts the exact classification, not just "an error
happened". List each error the code can emit and the test that
triggers it; an emitter with no trigger is a finding. Check batch
paths specially: an error tested only for a single-item call may be
classified differently (or lost) in a 10,000-row batch.

### 4. Check backend parity

Behavior promised by both backends but tested against one is a parity
gap. For each behavioral clause from step 1, decide where its test
lives:

- **Shared semantics** belong in `storage_conformance.py`, where both
  backends run it. A shared behavior tested only in
  `test_backends_memory.py` or `test_backends_database.py` is a
  finding — the other backend can break it unnoticed.
- **Per-engine conditionals inside the conformance suite are out of
  contract** — an `if backend is ...` in a shared test hides a real
  divergence instead of pinning it.
- Backend-specific files should hold only what is genuinely specific
  (identity, capabilities, provisioning, dialect policy).

The second implementation is the strongest oracle available — use it.

### 5. Scan for test smells

Weak tests pass review while pinning nothing. Flag:

- **Assertions that cannot fail** — asserting a value the test itself
  just set, tautologies, `assert result is not None` on a constructor.
- **Over-broad assertions** — checking `success is True` while leaving
  `observations`, error kinds, versions, or ordering unchecked; a
  test's power lives in its assertions, not its coverage.
- **Conditional test logic** — `if`/`for` guarding assertions, so a
  path through the test can pass without asserting anything.
- **Assertion roulette** — long unexplained assertion runs where a
  failure won't say which promise broke.
- **Fragile coupling** — assertions on incidental facts (dict/list
  order not promised, exact message text where only the kind is the
  contract, timestamps), which fail on lawful change and train people
  to ignore them.
- **Missed properties** — a pile of near-identical examples where one
  invariant (round-trip, idempotence, order-independence) would pin
  the whole family; suggest the property.

### 6. Evidence standard

Every finding names the untested clause or the surviving mutation,
with `file:line` for the code **and** for the test that should have
caught it (or the file where the missing test belongs). "Coverage
seems thin" is not a finding. Verify before reporting: read the test
you claim is missing a check — it may pin the clause indirectly (via
the conformance suite, a fixture, or a law test). A finding that a
test *would not fail* must survive you actually tracing the assertion.

### 7. Deliver findings

Report a severity-ordered list. Severity: **high** — unpinned
docstring/spec clause, unproduced error classification, or parity gap
on shared semantics; **medium** — surviving mutation on a key line,
over-broad assertion on a changed path; **low** — smells and fragile
couplings. For **each** finding, include the one-sentence test that
should exist ("a test that writes at the chunk boundary +1 and asserts
both chunks land with the same version"), and say which file it
belongs in. Close with the clauses that *are* well pinned, so the
strong parts of the suite are visible too.
