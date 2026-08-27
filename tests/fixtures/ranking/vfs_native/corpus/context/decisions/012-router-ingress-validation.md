# 012. Router Ingress Validation: Strict Gates, Never Repair

- **Status:** accepted
- **Date:** 2026-07-16
- **Deciders:** Clay Gendron
- **Decided by:** human (three-track research review 2026-07-10;
  implemented same day)

## Context

The router's contract is *values in, `Result` out — the data plane
never raises* (story 037). That held for paths (one gate:
`resolve_path`) but not for the other typed parameters of the public
verbs. The 2026-07-10 adversarial probe sweep produced raw
`TypeError`/`AttributeError` raises from garbage a JSON adapter could
forward verbatim (`grep(123)`, `before_context="2"`), and worse, silent
acceptances: a non-str `write` content **stored** and detonated in a
later unrelated `grep`; bogus `case_mode` values silently behaved as
the default; every `bool` parameter accepted any truthy object. Which
code touched a bad value first decided whether the caller got a
classified `invalid` or a stack trace.

Story 071's research inputs, all pointing one way:

- **Linux:** `openat2(2)` exists partly because `open(2)` masked
  invalid flag bits instead of rejecting them — the lesson is recorded
  in an in-source comment in `build_open_flags` (fs/open.c);
  `copy_struct_from_user` demands unknown trailing bits be zero. There
  is no global EINVAL-vs-EPERM order, but each entry point's order is
  fixed, deliberate, and tested.
- **9P:** fixed typed wire layouts mean the semantic layer *cannot*
  receive type garbage — decode failures die in transport before
  semantics ever run. Structural decode sits strictly below semantics.
- **MCP (spec 2025-11-25):** servers MUST validate all tool inputs, and
  validation failures are *tool execution errors* ("actionable feedback
  that language models can use to self-correct") — natively the shape
  of a classified `Result`, and not the shape of a raise.

## Options considered

- **Funnel-level catch** (convert backend `TypeError`s to results) —
  rejected: launders forwarded caller garbage *and* real backend bugs
  into one channel, destroying the impl-bug loudness 037 preserves.
- **Adapter-owned validation** — rejected: leaves every embedded Python
  caller unprotected and contradicts MCP's server-MUST-validate
  posture. The adapter gets the *decode* job, not the validation job.
- **Pydantic-backed gates** (`validate_call`/`TypeAdapter`) — rejected,
  and not for performance (a reused adapter runs ~200 ns): lax mode
  performs the exact scalar coercions being refused (`"5"`→5,
  `True`→1); strict mode breaks the container params (rejects even
  `set`→`frozenset`); `ValidationError` raises inside the router; and
  generated messages regress the KindContract's name-the-parameter
  hint. The counterpoint — free `TypeAdapter.json_schema()` — is
  answered by mechanical projection from the table instead.
- **Router-side container coercion** — rejected as a coercion; what
  survives of the argument is tuple-or-list acceptance for sequence
  params: validation widened one notch, values passed through untouched.

## Decision

1. **Every public verb strictly validates the types, value domains, and
   input shapes of its non-path parameters before any router state is
   read and before any dispatch.** A violation classifies
   `vfs.invalid`, names the parameter, and dispatches nothing. The
   router *validates*; it never repairs a value.
2. **Structural decode belongs to the wire adapter; strict validation
   to the router.** JSON cannot express `tuple`, `frozenset`, or
   `Observation`; the wire dialect's deserializer constructs typed
   values (through real pydantic validation, never `model_construct`),
   and the router's gates then assume decoded values and check domains.
   Layered, not chosen: FastAPI/FastMCP coerce because their boundary
   *is* the wire; ours is a typed Python API with a wire layer in front.
3. **Caller-input facts take precedence over state and entry facts.**
   Parameter types, domains, and exclusivity groups classify before
   router-state facts (closed, busy) and entry facts (capability,
   permission) — a bad parameter reports `invalid` even on a closed
   table or a busy path. The exclusivity matrices (path/observations,
   write's entries-vs-path+content, edit's old/new-vs-edits) are
   caller-input facts and live in the table as shape rules; path
   *validity* stays fused with resolution.
4. **One declarative table, one checking helper** — `src/vfs/params.py`:
   `ParamSpec` (name, type kind, `required`, `nullable`, `minimum`,
   `choices`, default, doc — line 48) and `ShapeRule` (exclusive
   parameter groups — line 66), grouped per op in `PARAMS` (line 87),
   importing nothing above `ops.py`. `param_violation` (line 290) walks
   the table; `_gate_params` (`src/vfs/base.py:1718`) mints the refusal
   and runs first at every public verb. Nullability is declared per
   parameter — a JSON `null` against a non-`| None` signature
   classifies through the type message (added after the verification
   pass showed `None` bypassing every check). The table doubles as
   story 045's per-verb wire schema source: type tags project to JSON
   Schema mechanically, and the drift test and `inputSchema` generator
   read the same table.
5. **Backends keep semantic validation only** — bad regex *value*,
   not-found, kind conflicts — defense in depth, never type repair.
   After these gates, a `TypeError` escaping a backend is once again
   what 037 says it is: our bug, loud.

## Consequences

- **Easier:** the garbage matrix per verb classifies `vfs.invalid` with
  the parameter named and verified zero dispatch; gate, drift test, and
  wire schema share one source of truth; embedded Python callers get
  the same protection as wire callers.
- **Harder:** hand-rolled checks over a small type vocabulary must
  track signature changes (the drift test — every public-verb parameter
  appears in the table and vice versa — is the guard); one divergence
  on record: a bad parameter on a closed router reports `invalid` while
  a bad path on a closed router reports closed.
- **Committed to:** the router never coerces; per-verb check order is
  suite-pinned, not docstring-pinned; strictness on scalars stays
  deliberate — the router's direct callers are typed Python, where
  `"5"` for an `int` is a bug to surface, not repair.

Executed by story 071 (`context/specs/archive/071-ingress-type-gates/`),
which supersedes in part 045's "garbage kwargs are a `TypeError` at the
outermost public method" bullet — the probe evidence showed that
premise false.
