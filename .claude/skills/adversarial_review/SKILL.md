---
name: adversarial_review
description: Attack the current diff or branch single-handedly by writing and executing throwaway scripts against it, with an executed-repros-only evidence standard. Use when the user asks to "adversarially review", "attack", "pressure test", or "try to break" a change, or wants a dynamic review before committing substantive work.
---

# Adversarial review — one agent, executed evidence

Attack a change the way an exploratory tester runs a session: pick a
small set of chartered attack dimensions, time-box each one, and probe it
by **writing and executing scratch scripts** — never by reading alone.
The fault model: developers routinely fail to constrain inputs, outputs,
state, and computation, and those failures hide from example-based tests.
This is the work of a single agent — no subagents, no fan-out. Depth on
a few well-chosen dimensions beats shallow coverage of many.

**The evidence standard is absolute: a finding without a script that was
actually run, with its output quoted, is worthless.** Static suspicion is
at most a lead to chase with a script, never a finding.

## House rules (bind every step)

- **uv project**: everything runs from the repo root as
  `uv run python ...`, `uv run pytest ...`, `uv run ty check ...`.
- **The repo is read-only.** Never modify, stash, checkout, or commit
  anything in it. Scratch scripts go ONLY under the session scratchpad
  directory (from the system prompt), e.g. `<scratchpad>/adversarial/<dimension>/`.
- **Read intent first.** Module docstrings, the touched code's tests, the
  relevant spec in `context/specs/` (or `context/stories/*/spec.md`), and
  ADRs in `context/decisions/`. Intended, documented, or test-pinned
  behavior is not a defect, and triage (step 4) is judged against these.

## Process

### 1. Scope the change under test

- `git status` and `git diff` (plus staged and untracked files, or the
  branch diff against `main` if reviewing a branch) — know exactly what
  is new before choosing what to attack.
- Read every touched module in full, its tests, and its governing docs
  (see house rules). Write down a short intent sheet: what the change
  promises, its declared error channels, and its stated limits (budgets,
  caps, ordering guarantees). This sheet is the triage yardstick later.

### 2. Charter 4–8 attack dimensions

Derive a small, prioritized list tailored to *this* change — never a
stale generic list. Each dimension gets a one-line charter (mission: what
to attack and what "broken" would look like) and a time box: roughly a
handful of scripts, then move on. Shapes to draw from, picking what fits:

- **Adversarial inputs and boundary values** — empty/huge/unicode/null
  bytes, off-by-one at every declared limit, values just inside and just
  outside each boundary, exceptional values fed through the public API.
- **API misuse and hostile objects** — wrong types, duck-typed impostors
  (`__getattr__` tricks, iterables that lie about length, `__eq__`/`__hash__`
  misbehavers), old-API call shapes, arguments in bad combinations.
- **Lifecycle abuse** — double close/dispose, reuse after teardown,
  re-entry, operations on half-constructed or failed objects,
  cancellation mid-operation.
- **Concurrency probes** — where suspension points, locks, or shared
  state open races: interleave operations, run the same operation from
  many workers, check ordering and isolation claims.
- **Property and invariant probes** — the highest-yield property shapes:
  round-trips (encode/decode, write/read), idempotence (twice equals
  once), order-independence, and model comparison against a trivially
  correct oracle (a dict, a real filesystem, sorted lists).
- **Scale and budget probes** — batches past every declared chunking or
  bind-parameter budget (10,000+ items is contract here, not edge case);
  statements that must not grow with batch size.

### 3. Execute each charter

For each dimension, in priority order:

- Write a scratch script under `<scratchpad>/adversarial/<dimension>/`
  that drives the change **through its public surface** — no reaching
  into internals to manufacture states the API cannot produce.
- Run it. Record the exact command and the actual output. Let results
  steer the session: a suspicious output buys follow-up scripts against
  the same area; a clean sweep ends the charter at its time box.
- Keep notes as you go: what was probed, what held, what looked off.
  When the box is spent, note what was *not* covered and move on —
  bounded effort is the design, not a compromise.

### 4. Triage every observation against intent

Before anything becomes a finding, try to refute it yourself:

- Re-run the repro from a clean state; flaky evidence is no evidence.
- Check the intent sheet, tests, and docstrings. A designed error on the
  declared channel is the system working. The defect shape to keep is
  the **wrong channel**: a raw traceback, hang, or silent corruption
  where a clean, typed error belongs — or an error where success belongs.
- API misuse outside the documented contract refutes the finding unless
  the failure mode is still unacceptable (crash, corruption, hang).
- Severity: `critical` (corruption, crash, wrong results), `major`
  (contract violated, wrong error channel), `minor` (rough edge within
  contract), `question` — allowed for demonstrated design smells where
  intent is genuinely ambiguous. When refutation and finding both seem
  plausible, present it as `question` with both readings.

### 5. Report

Lead with the verdict: findings by severity, and which dimensions were
attacked and held. Then, for each surviving finding:

- **Claim** — one sentence, plus severity.
- **Repro** — absolute script path, the exact command run.
- **Evidence** — quoted actual output, and expected vs actual.
- **Read** — why the intent sheet says this is (or may be) a defect.

Close with the coverage ledger: charters executed, time-box leftovers
(what was deliberately not probed), and refuted leads in one line each.

## Notes

- This is a deliberate pre-commit spend — invoke it for substantive
  changes, not per edit.
- Scratch scripts are session-local and disposable. If a repro deserves
  to live on, propose porting it into `tests/` as a real test in a
  follow-up edit — never move scratch files into the repo yourself.
- One full `uv run pytest tests/ -q` run belongs somewhere in the
  session: a red suite is a finding in itself, and a green suite scopes
  what the attack scripts must reach beyond.
