# 057 — Plan

Approach: two passes, each independently landable and verified at its
own session end (pytest/ruff/ty once per session). Pass A is
self-contained in `results2.py` + its law suite; Pass B threads the new
envelope through the router, backend, and renderer and fixes the
envelope's own consumers. The field deletions are the migration's
safety mechanism: removing stored `success` and the `function` str
makes every stale construction site a hard `ty` error, so nothing
migrates silently (runtime stays open by design: `extra='allow'`
swallows unknown kwargs, so the guard is static-only).

Ordering constraint: this story lands **before 056 Pass C** — the
payload shape freezes into the vfs MCP dialect there.

## Pass A — the envelope (`vfs/results2.py`, new law suite)

### 1. Vocabulary and contract tables

- `Severity` (error | warning | info; unknown reads as error — the
  coercion validator keeps unknown strings, `is_fatal` degrades them).
- Retry-class enum (never | transient | refresh) + the normative
  per-kind table: retry class, hint, `path_means`. One invariant test
  pins totality over `VFSErrorKind`.
- `kind_family()` longest-dotted-prefix lookup; `_KIND_ALIASES` with
  the `vfs.backend_unavailable` tombstone.
- `VFSErrorKind`: re-parent `backend_unavailable` →
  `"vfs.unavailable.backend"`; add `unaddressable`; docstring gains the
  namespace partition (`vfs.*` core, `x.<vendor>.*` for backends),
  prefix-dispatch rule, producer-exclusivity rules, and per-kind
  `path_means`.

### 2. ResultError

- New fields: `severity` (default error), `source: Path | None`.
  `extra='allow'`.
- `with_mount`: always returns a copy; stamps `source=mount` on first
  hop, re-roots it every later hop (including path=None); overflow
  writes the reserved `data["vfs.overflow"]` record via `setdefault`
  (append-once, namespaced — never dict-union clobber).
- `without_mount`: strips the prefix from `path` and `source`.
- Derived: `is_fatal` (severity-based, unknown → fatal),
  `retry_class` (contract-table lookup via `kind_family`; unknown kind
  → None, no assumption).
- Identity: frozen value equality is the documented dedup key;
  "distinct facts must differ in some field" joins the docstring as
  producer contract.

### 3. Result

- Drop stored `success`; derived property (no fatal-severity errors),
  serialized outbound by `to_payload`, stripped inbound by a
  before-validator. `__bool__` unchanged in meaning.
- Drop `function: str`; `ops: tuple[str, ...]` with ordered-union merge
  and an `.op` property (sole op or None) — spec decision 8 amendment:
  one vocabulary with `vfs.ops`, plus a transitional `.function` alias
  until Pass B. A before-validator shims inbound/legacy `function="x"`
  to `ops=("x",)` — keeps most construction sites source-compatible
  during Pass B.
- `extra='allow'`; `_combined_errors` by value equality.
- `Result.merge(results, *, function)` — the plain fold (successor to
  `_merge_results`); `Result.merge_branches(results, *, function)` —
  the zero-progress rule (any branch progressed → other branches'
  error-severity entries demote to warnings; none progressed → stay
  fatal). Demotion preserves kind/source/data.
- `to_payload(max_errors=None)`: emits derived `success`; when capped,
  groups errors by (kind, severity) and rolls each tail into one entry
  with `data={"vfs.rollup": {count, sources}}`.
- `from_payload(payload, *, strict=False)`: strips `success`
  (reconciliation: peer claimed failure but no fatal error survived →
  synthesize `internal` error carrying the claim); per-item validation
  of observations (quarantine → warning `vfs.internal` with raw item)
  and errors (quarantine → error `vfs.internal`); hopeless payload →
  fatal `internal` Result, never raises. `strict=True` restores
  raise-on-invalid.
- Row algebra, sequence protocol, sort/top/filter/kinds, to_json/to_str:
  unchanged.

### 4. Law suite (`tests/test_result_laws.py`, new)

- L1 associativity of `|`; L2 idempotence + `Result()` identity;
  L3 success is a homomorphism (`(a|b).success == a.success and
  b.success`); L4 rebase distributes over merge (including overflow
  rows); L5 wire round-trip preserves value + dedup behavior (the
  repro §2 diamond becomes a regression test).
- Contract tests: retry-table totality; prefix degradation
  (`vfs.unavailable.dns` → unavailable handling); alias resolution;
  unknown severity reads as error; quarantine both arms; the
  reconciliation rule; source stamping across two hops; overflow
  address reconstruction after three hops; rollup leaves derived
  success invariant.

Session end: pytest (results-law suite green; the rest of the tree may
be red mid-story per repo posture — Pass B restores it), ruff/ty on
`results2.py`.

## Pass B — threading and consumers (`base2.py`, `memory.py`, `render.py`, tests)

### 5. Router seams

- `_error`: op required, `severity` param (default error), no
  `success=` (gone from the model).
- `_backend_unsupported`: gains `path=ROOT` — anchored to the entry by
  the funnel's existing rebase; state the seam invariant once (the
  TransportError arm already relies on it) and delete the pun comment.
- Replace `_merge_results` with `Result.merge(..., op=op)` at
  grouped/two-path/entry-batch sites and
  `Result.merge_branches(..., op=op)` at `_route_fanout` and
  `_tree_entry` — the only two demotion sites; scoped dispatch never
  demotes. Replace the docstring's false disjointness claim with the
  stated bind-path decoration rule.
- Fan-out capability skips append an info-severity `vfs.unsupported`
  entry per skipped entry (`source` = its bind path); re-apply
  `max_count`/`limit` after the merge.
- `_probe_bind_site`: dispatch on `kind_family` — not_found → mkdir
  advice; unavailable.* → surface the transport failure.
- `add_mount`/`remove_mount`: raise `MountError(ValueError)` carrying
  the `ResultError` list; `str()` stays the prose (existing tests keep
  matching).

### 6. Backend + renderer

- `memory.py`: delete every `success=` construction; keep per-row read
  classification. Fast-follow (same pass if cheap): enumerate all
  failing entries per mutation batch; `status="deleted"` on delete rows.
- `render.py`: dispatch on `.function` (None → generic arrangement,
  killing the 'hybrid' branch); errors render one line each —
  SEVERITY, locus (path or `mount <source>`), message, contract hint,
  retry directive — grouped errors → warnings → info; rollups render
  counts.

### 7. Suite rework + ripples

- Tests: grep `success=` constructions (attach errors instead);
  assertions on `'hybrid'`, `''` function, and the old
  `vfs.backend_unavailable` string; new assertions per acceptance
  criteria (fan-out demotion both arms, probe kind dispatch, max_count
  post-merge, MountError).
- `exceptions.py`: `exception_for_kind` consults `kind_family`.
- 056 spec notes (decision 12 kind value; decision 7 docstring);
  repro.py retires (cases live in the law suite).

Session end: full pytest/ruff/ty on touched files.

## Trade-offs accepted (recorded in the spec)

- Derived success inverts the missing-error failure mode (silent
  success instead of silent failure); the single-funnel classification
  seam is the mitigation.
- Demotion makes severity context-dependent (same dead mount: warning
  in fan-out, error when scoped) — kind, not severity, identifies the
  condition; both arms are pinned by tests.
- `extra='allow'` admits junk fields into token-billed payloads and
  into value equality; parse-boundary size clamp bounds the first,
  namespaced-data discipline the second.
- Warning-severity losses are invisible to bit-only consumers — by
  design; the bit was the thing lying.
