# 071 — Ingress type gates: the router owns wire-facing validation

- **Status:** implemented 2026-07-10 (same day as the draft, from a
  three-track research review: parameter inventory of
  `base.py`/`memory.py`/`protocol.py`; in-repo constraint survey;
  external prior art — Linux syscall ingress, 9P wire typing,
  MCP/pydantic mechanics). Supersedes the 2026-07-10 seed. One naming
  amendment during implementation: the traversal vocabulary moved to
  `ops.py` under the single name `GRAPH_METHODS` — the
  `TRAVERSAL_FUNCTIONS` alias was retired, not kept.
- **Date:** 2026-07-10
- **Owner:** Clay Gendron
- **Kind:** hardening (data-plane contract — no new verbs, no storage
  protocol changes)
- **Depends on:** 037 boundary-raise-and-result-channel (the never-raise
  canon this story enforces), 057 result envelope (`vfs.invalid` and its
  KindContract), 069 routing decomposition (the union rule the gates
  must fit), 045 verb wire contract (the schema table this story
  triggers into existence — see Decision 8)
- **Supersedes in part:** 045 §Out of scope, the bullet declaring
  in-process garbage kwargs "a `TypeError` at the outermost public
  method, correctly." The premise is false: probe evidence shows garbage
  does not fail at the outermost method — it detonates mid-dispatch in
  router arithmetic or inside backends via blind `**kwargs` forwarding,
  on the impl-bug channel 045 itself reserves for *our* bugs. 045's own
  skew rule ("signature mismatch at the boundary is `invalid` … never a
  raw `TypeError`") is the principle; this story applies it to the
  Python boundary too.

## Intent

The router's contract is *values in, `Result` out — the data plane never
raises* (037 D1). That holds for paths (one gate: `resolve_path`) but
not for the other typed parameters of the public verbs. The adversarial
probe sweep (2026-07-10) produced raw `TypeError`/`AttributeError`
raises through public verbs from type garbage a JSON adapter could
forward verbatim: `grep(123)`, `glob(123)`, `ext=(123,)`,
`before_context="2"`, grep's per-file `max_count="3"`, non-str `edit`
old/new. Worse than the raises are the silent acceptances: a non-str
`write` content **stores** and detonates in a later unrelated `grep`;
bogus `case_mode`/`output_mode` values silently behave as the default;
every `bool` parameter accepts any truthy object.

Three ad-hoc gates have already landed under this rationale (tree
`max_depth`, fan-out `row_cap`, mkedge `edge_type`). This story replaces
ad-hoc with systematic:

> **The governing rule.** Every public verb validates the types and
> value domains of its non-path parameters before any router state is
> consulted and before any dispatch. A violation classifies
> `vfs.invalid`, names the parameter, and dispatches nothing. The
> router *validates*; it never repairs a value.

Which code touches a bad value first must never again decide whether the
caller gets a classified `invalid` or a stack trace.

## Decisions

1. **The router owns ingress — strict, not lax.** Validation lives at
   the routing layer, not the funnel, not the adapter, not the backends.
   The three ecosystems surveyed converged here: MCP requires servers to
   validate all tool inputs and files "value out of range / wrong
   format" under *tool errors* — which is exactly what a classified
   `Result` projects to; 9P's semantic layer never sees type garbage
   because the typed wire kills it at decode; and Linux documents the
   cost of the alternative in source — `openat2(2)` exists partly
   because `open(2)` masked invalid flag bits instead of rejecting them
   (`build_open_flags`, fs/open.c: "openat2(2) checks all of its
   arguments"). Strictness on scalars is deliberate: the router's direct
   callers are typed Python, where `"5"` for an `int` is a bug to
   surface, not repair — ty enforces it statically and the gate is the
   runtime belt over those suspenders.

2. **Gates are pure refusal checks — validate, never coerce.** The gate
   shape is the established policy-check pattern under 069's union rule:
   `(op, params) -> Result | None`, refusal or proceed, parameters flow
   onward untouched. A gate that returned normalized values *and* could
   refuse would both violate the rule ("no function both produces a
   value and refuses") and silently accept the wire garbage this story
   exists to refuse. All three landed gates already have this shape;
   this decision makes it binding for every gate the table drives.

3. **Structural decode belongs to the wire adapter; the router stays
   typed.** JSON cannot express `tuple`, `frozenset`, `Observation`, or
   `Entry` — so *some* layer must construct typed values from arrays and
   objects. That layer is the wire dialect's deserializer (045), which
   already must construct model objects through real pydantic validation
   (never `model_construct` — a validation-bypassed `Observation`
   detonates at the rebase seam). Building tuples and frozensets is the
   same deserialization step, driven by the same schema table (Decision
   8). This is 9P's layering: structural decode strictly below
   semantics; the router's gates then assume *decoded* values and check
   domains. Divergence from mainstream noted on record: FastAPI and
   FastMCP coerce at their boundary because their boundary *is* the
   wire; ours is a typed Python API with a wire layer in front — we
   split decode (adapter, lax by necessity) from validation (router,
   strict), layered instead of chosen.

4. **One declarative table, one checking helper.** A new leaf module
   `src/vfs/params.py` holds a `ParamSpec` entry per parameter (name,
   type tag, bounds or literal set, required, default, one-line
   semantics) grouped per op, importing only `Op` and the vocabularies
   from `ops.py` (itself stdlib-only — no cycle). One helper walks the
   table for an op against the supplied values and mints the refusal.
   The two landed deep gates migrate into the table; their sites keep
   nothing. Checks are hand-rolled against the table's small type
   vocabulary (`str`, `int`, `bool`, `dict`, `tuple[str, ...]`,
   `frozenset[str]`, literal sets) — see Declined for why not
   pydantic-backed.

5. **Placement and precedence: caller-input gates run first.** The
   param gate is invoked at the top of each public verb — the only
   layer that sees an op's full typed signature, since every route
   shape forwards `**kwargs` blind. This pins a precedence that has
   until now been emergent: **caller-input facts (parameter types,
   domains, and exclusivity groups) classify before router-state facts
   (closed, busy) and entry facts (capability, permission).** It
   extends 069's pinned `invalid` -beats- `busy` principle uniformly —
   closed is a state fact like busy. Two consequences on record:
   - The exclusivity matrices (path/observations, write's
     entries-vs-path+content, edit's old/new-vs-edits, move/copy's
     pair-vs-batch) are caller-input facts and move into the table as
     mutually-exclusive parameter groups, checked by the same helper.
     The shapes' internal checks are removed with them — one copy of
     each rule.
   - Path *validity* stays where it lives (inside the shapes, fused
     with resolution, after the closed check) — resolution is already
     the path's gate and re-homing it buys nothing. Divergence on
     record: a bad parameter on a closed router now reports `invalid`
     where a bad path on a closed router reports closed. Linux offers
     no cleaner precedent — it has no global EINVAL-vs-EPERM order
     (`prlimit` validates before the capability check; `reboot` trusts
     first, explicitly) — what it does model is that each entry point's
     order is fixed, deliberate, and tested. Ours is, per verb, by the
     acceptance matrix.

6. **Domain rules, decided per family** (full table in `params.py`;
   the load-bearing rows):
   - *Ints*: `bool` is rejected wherever `int` is expected — adopting
     the repo's own strictest precedent (`_validate_version`,
     paths.py). The two landed int gates (`max_depth`, `row_cap`)
     currently accept `True`; they are retrofitted by the migration.
     Bounds: `max_depth >= 1`, glob `max_count >= 1` (one gate covers
     its double life as row-cap and per-entry cap), glean `limit >= 1`,
     grep per-file `max_count >= 1`, `before_context`/`after_context`
     `>= 0`, graph `depth >= 1`.
   - *Enums*: `case_mode`, `output_mode` gate against their `Literal`
     vocabularies (`typing.get_args` on the ops.py types) — closing the
     silent-default hole. `graph.method` is already gated against
     `TRAVERSAL_FUNCTIONS`; it moves into the table unchanged.
   - *Strs*: `pattern`, `query`, `old`, `new`, `edge_type`, `content`
     (when the path form of `write` is used) require `str`. An empty
     `pattern` stays legal (fnmatch and regex both define it); emptiness
     is a semantic question backends already answer.
   - *Bools*: `overwrite`, `parents`, `exist_ok`, `permanent`,
     `cascade`, `replace_all`, `fixed_strings`, `word_regexp`,
     `invert_match` require `bool` — truthy objects are wire noise, not
     intent.
   - *Containers*: `paths`, `ext`, `ext_not`, `globs`, `globs_not`
     require a tuple (or list — the one container the gate accepts
     interchangeably, since Python literals and JSON decode both
     produce it and iteration is the only downstream use) of `str`
     items; `str`/`bytes`/generators are rejected explicitly — the
     probe showed a naked string fanning out per-character and a
     truthy-but-empty generator classifying as a zero-entry scope.
     `columns` requires `frozenset | set | list | tuple` of `str` by
     the same reasoning (memory ignores it entirely today, so this
     gate is the only place garbage in it can ever surface).
   - *Models*: `observations`, `entries`, `edits`, `moves`/`copies`
     keep their existing item-wise `isinstance` gates, relocated into
     the table's vocabulary so the rule is declared, not scattered.
   - *`run.arguments`*: `dict | None`; JSON objects guarantee `str`
     keys, values stay `Any` — deep argument validation belongs to the
     tool's own schema, not the router.
   - *`user_id`*: `str | None` type-gated, semantics opaque. 045
     decided identity is connection-derived and this parameter never
     rides the wire; the gate only stops a non-str from reaching
     backends.
   - *Nullability is declared per parameter*: `None` passes only where
     the signature says `| None`. A JSON `null` against anything else —
     the likeliest wire garbage of all — classifies through the kind's
     own type message (`got NoneType`). Added post-implementation when
     the adversarial verification pass showed `None` bypassing every
     type check (`glob(ext=None)` raised a raw `TypeError` from the
     backend; `case_mode=None` silently defaulted past the enum gate).

7. **Messages follow the KindContract.** `vfs.invalid`'s agent hint is
   "Fix the flagged parameter and retry," so every refusal names the
   parameter. Two codified shapes, both already in the mints:
   type-only — `"{op} {param} must be <type>, got {type(v).__name__}"`;
   value-relevant — `"{op} {param} must be <rule>, got {v!r}"`.

8. **The table is 045's schema, landed.** 045 left its per-verb request
   schema in the story folder "until a second consumer arrives," naming
   `ops.py`-adjacent as its destination and the drift test plus the MCP
   `inputSchema` generator as the consumers. The gates are the third
   consumer — the trigger fires, and `params.py` is that destination.
   The type tags project to JSON Schema mechanically (tuple-of-str →
   array-of-string, literal set → enum, int bound → minimum); the
   adapter's unknown-param skew check (045 item 2) reads the same
   table. One source of truth for gate, drift test, and schema.

9. **Backends keep semantic validation only — defense in depth, not
   type repair.** A backend still classifies what only it can know
   (bad regex *value*, not-found, kind conflicts) and keeps its
   existing type checks for direct un-routed use; it never coerces.
   The funnel's narrow catch (`TransportError` only) is unchanged —
   after these gates, a `TypeError` escaping a backend is once again
   what 037 says it is: our bug, loud.

## Research inputs (2026-07-10) — evidence the decisions stand on

- **Linux** (verified in the local clone, current mainline):
  `build_open_flags` fs/open.c — `openat2` rejects unknown flag bits
  with `EINVAL` where `open` masks them, with the in-source comment
  recording the lesson; `copy_struct_from_user`
  include/linux/uaccess.h — unknown trailing bits must be zero or
  `-E2BIG`, the extensibility-safe ingress shape 045's skew rule
  mirrors; `poll_select_set_timeout` fs/select.c and `do_prlimit`
  kernel/sys.c — range checks classify before any wait or mutation;
  `do_prlimit` vs `sys_reboot` kernel/reboot.c — no global
  EINVAL-vs-EPERM precedence exists, orderings are per-entry-point and
  deliberate.
- **9P** (intro(5); net/9p in the local clone): fixed typed wire
  layouts mean the semantic layer cannot receive type garbage — decode
  failures die in transport (`p9_parse_header` → `-EINVAL`) before
  `p9_check_errors` ever reads semantics. The layering Decision 3
  adopts.
- **MCP** (spec 2025-11-25): servers MUST validate all tool inputs;
  input validation failures are *tool execution errors* ("actionable
  feedback that language models can use to self-correct"), not
  protocol errors — a classified `vfs.invalid` `Result` is natively
  that shape; a raw raise is neither. Clients are not required to
  validate before sending.
- **Pydantic 2.12.5** (verified against the installed version): lax
  mode coerces `"5"`→5 and `True`→1 (the behaviors Decision 1
  refuses); strict mode rejects even `set`→`frozenset` (unusable for
  the container params without per-param laxity); a *reused*
  `TypeAdapter` runs ~200 ns/validation vs ~9.3 µs when rebuilt per
  call. FastAPI and FastMCP both coerce-then-validate at their
  boundaries and return structured validation errors — the mainstream
  wire-boundary posture, which Decision 3 assigns to our adapter
  rather than our router.
- **In-repo probes** (2026-07-10 sweep): the full garbage inventory in
  the Intent; the per-verb parameter tables and file:line evidence
  live in the plan when drafted — the inventory was code-verified
  against `base.py`, `memory.py`, and `protocol.py` as of commit
  `74f21c8`.

## Declined — assessed and rejected, recorded so they stay rejected

- **Funnel-level catch** (convert `TypeError`/`ValueError` from any
  backend call into classified results): one seam and zero per-verb
  work, but it launders both forwarded caller garbage *and* real
  backend bugs into the same classified channel — destroying the
  impl-bug loudness 037 deliberately preserves.
- **Adapter obligation** (validation is the wire adapter's job): leaves
  every embedded Python caller unprotected, re-implements the table per
  adapter, and contradicts MCP's server-MUST-validate posture. The
  adapter gets the *decode* job (Decision 3), not the validation job.
- **Pydantic-backed gates** (`validate_call` / `TypeAdapter`): lax mode
  performs the exact scalar coercions Decision 1 refuses; strict mode
  breaks the container params; `ValidationError` raises inside the
  router and per-verb conversion is more machinery than the checks it
  replaces; generated messages regress the KindContract's
  flagged-parameter hint and the tests' message pins; zero `ty`
  precedent in-repo. Performance was *not* the reason — a reused
  adapter is ~200 ns. Recorded counterpoint: pydantic would hand the
  wire dialect `TypeAdapter.json_schema()` for free; Decision 8 gets
  the same artifact from the table's mechanical projection instead.
- **Router-side container coercion** (accept JSON-shaped lists and
  normalize to tuple/frozenset in the gate): argued for as "the one
  justified laxity" since pure strictness would make the router
  unreachable from any wire. Rejected as a *coercion*: the adapter
  constructs typed values as part of deserialization it must do anyway
  (Decision 3), and a normalizing gate violates the union rule
  (Decision 2). What survives of the argument is Decision 6's
  tuple-or-list acceptance for the sequence params — validation
  widened one notch, values still passed through untouched.
- **Silent enum defaulting** (status quo for `case_mode` /
  `output_mode`): `open(2)`'s flag-masking in miniature; the kernel's
  own comment is the rebuttal.
- **Deep validation of `run.arguments` values**: tool schemas are the
  tool's contract (045/034 territory); the router checks the envelope
  type only.

## Non-goals

- Hung-backend timeouts and regex catastrophic backtracking (probe
  observations; DoS surfaces, not type validation — separate story if
  pursued).
- `user_id` semantics, permission integration, or wire identity (045
  decided connection-derived identity; 070 owns principals).
- Advertising per-verb schemas through `capabilities()` (034 decided
  against; the wire contract is versioned, 045).
- The adapter's own lax decode design (045's story; this one hands it
  the table).
- Retrofitting `tests2/` or `src2/` reference trees.

## Acceptance criteria

- A garbage matrix per public verb — wrong type, out-of-range,
  bogus enum member, truthy-non-bool, str-where-container,
  bool-where-int — classifies `vfs.invalid` with the parameter named
  in the message and a recorder-verified **zero dispatch**.
- The three landed gates are table entries; their old inline sites are
  gone; `max_depth=True` and `max_count=True` now classify `invalid`
  (bool retrofit).
- Exclusivity matrices live only in the table; the shapes' inline
  copies are removed; existing exclusivity tests pass unmodified or
  with deliberate re-pins listed in the plan.
- Precedence pins per Decision 5: bad param beats closed; bad param
  beats busy; path-after-closed unchanged.
- `params.py` imports nothing above `ops.py`; a drift test asserts
  every public-verb signature parameter appears in the table and vice
  versa (045's skew rule, enforced at home).
- `uv run pytest tests/ -q` green; `uv run ruff check src tests` and
  `uv run ty check src tests` clean.

## Open questions

- `graph.depth` lower bound: `>= 1` chosen to mirror `max_depth`, but
  no reference backend implements `graph` yet — confirm against the
  first real implementation whether `depth=0` (the node itself) is a
  meaningful request. `[NEEDS CLARIFICATION]`
- Whether the drift test belongs in `tests/` now or arrives with 045's
  wire dialect — the table exists either way; only the test's home is
  open.
