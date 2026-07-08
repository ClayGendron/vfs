# 057 — Result Envelope: Evidence In, Verdict Derived

- **Status:** spec settled — research review 2026-07-08 (8 primary-source
  studies, 2 adversarial critics, 3 independent design lenses; convergent
  on the core, divergences adjudicated below); plan/tasks pending
- **Date:** 2026-07-08
- **Owner:** Clay Gendron
- **Kind:** refactor (result/error model) — wire-contract shaping
- **Depends on:** 056 Pass A (one funnel, rebase seam, per-row grouped
  reads), ADR 001 (storage is composed)
- **Amends:** 056's `backend_unavailable` kind value (re-parented, alias
  kept); the `with_mount` overflow classification; `_merge_results`'
  disjointness docstring (already flagged false in 056 decision 7)
- **Enables:** 056 Pass C — the Result payload becomes the vfs MCP
  dialect's `structured_content` and freezes there; agent-side retry
  dispatch on structured fields
- **Ordering:** must land **before Pass C**. Every decision below is a
  wire-shape decision; after the first independent peer ships, the kind
  strings, field names, and fold rules are permanent.
- **Evidence:** `repro.py` in this directory reproduces all ten defects
  against the current envelope (run: `uv run python
  context/stories/057-result-envelope/repro.py`). `research.md` holds the
  distilled study corpus.

## Intent

`Result` today stores its verdict beside its evidence: `success` is an
independent bool, errors carry no severity, no provenance, and no
machine-readable retry semantics, and error identity is `id()`-based.
None of that survives what 056 built the envelope for — being merged
across fan-out entries, rebased across mount seams, and serialized across
MCP hops. The reproduced consequences (repro.py): the lying
`success=True`-with-errors state is default-constructible and
wire-survivable (§1); dedup double-counts after one wire round-trip (§2)
and depends on whether an error happened to carry a path (§3); one dead
mount in a fan-out hides every live mount's rows behind `isError=true`
(§4); the router's own probe consumes only the bit and advises `mkdir`
against a dead backend (§5); `error.path` means five different things by
producer (§6); one malformed remote path destroys a whole envelope and
crashes the caller's fan-out (§7); a mid-chain hop silently strips any
field a newer peer added, contradicting the documented lossless claim
(§8); `max_count` multiplies by mount count (§9); and the merge's
disjointness premise is false at bind paths (§10).

After this story the rule is: **the envelope carries evidence — frozen
error values with severity, provenance, and pinned locus semantics — and
every verdict (`success`, `is_error`, retry class, rendering) is derived
from that evidence.** Disagreement between verdict and evidence becomes
unrepresentable, exactly as in every system studied (errno's `ret<0`,
9P's reply type, FUSE's `error==0`, LSP's result-xor-error, SQLite's
`code==0`): the reference systems differ in almost everything except
this.

## Decisions settled (research review 2026-07-08)

1. **`success` is derived, never stored.** A property — no
   error-severity entries — serialized outbound for isError-checking MCP
   clients, **ignored inbound** and re-derived by `from_payload`. One
   reconciliation rule, pinned in one place: a peer payload claiming
   failure with no classifiable error synthesizes
   `ResultError(kind=internal, severity=error)` carrying the claim in
   `data`. Every studied system makes verdict/evidence disagreement
   unrepresentable; three producer idioms have already drifted in this
   repo (memory's `success=not errors`, `_error`'s manual bit,
   `with_mount`'s recompute — repro §1). Trade-off accepted: a producer
   that fails without minting an error now yields silent success instead
   of silent failure; the funnel being the single classification seam is
   the mitigation.

2. **`severity: error | warning | info` on `ResultError`;** unknown or
   absent reads as `error` (LSP's never-silently-downgrade rule). Trust
   contract per tier, in the model docstring: *warning* = loss or caveat,
   rows present are trustworthy, success unaffected; *error* = something
   the caller asked for failed; *info* = advisory (capability skips,
   rollups). Rebase overflow, dead fan-out branches among live ones, and
   the currently-unrecordable capability skips all become warnings/info
   on successful envelopes (repro §4). A `fatal` tier (rows untrusted —
   FUSE's `se->error`) was considered and **deferred**: under the
   unknown-reads-as-error rule it can be added later additively, since
   old readers will degrade it to `error` and fail the envelope, which is
   the correct conservative read.

3. **`source` provenance, stamped structurally by the rebase seam.**
   `ResultError` gains `source: Path | None` — the bind path of the
   producing hop, in the reader's namespace. `with_mount` **always
   returns a copy** and always transforms: the first hop stamps
   `source=mount`, every later hop re-roots it, including when `path` is
   `None` (killing the return-`self` identity shortcut, repro §3, and the
   frozen-inner-coordinates defect on overflow records). Which mount
   produced an error now survives any merge depth and any number of wire
   crossings, with zero producer discipline — the seam that already
   rebases rows does the stamping. Precedent: 9P's tag, FUSE's `unique`,
   LSP's `Diagnostic.source`, errseq's counter.

4. **Error identity is value identity; `id()` dies.** Frozen value
   equality is the dedup key (`e not in errors`). Diamond chains collapse
   by value on both sides of a wire hop (repro §2 fixed); two mounts
   failing identically stay two facts *because their sources differ*
   (decision 3 is what makes this lawful — equality dedup without a
   provenance field was rejected as over-collapsing, the errseq/fsync
   lesson). Producers wanting N-occurrence semantics from one source add
   a `data` discriminator.

5. **The kind vocabulary goes hierarchical, now.** Dotted kinds with a
   normative longest-prefix dispatch rule — the textual form of SQLite's
   `rc & 0xff`. `vfs.backend_unavailable` is re-parented to
   `vfs.unavailable.backend`; the old string is a permanent inbound alias
   (SQLite tombstone discipline: shipped values are never renamed or
   reused). Unknown kinds degrade to their longest known prefix before
   falling to base handling — partial degradation instead of total.
   Namespace partition pinned before any peer ships: `vfs.*` is reserved
   for the core; backend/mount-minted kinds use `x.<vendor>.*`.
   SQLite's retrofit — a per-connection opt-in API still off by default
   twenty years later — is the cost of doing this after 1.0.

6. **`vfs.unaddressable` is minted; `vfs.invalid` means caller-fixable,
   only.** Rebase overflow (a row that exists but exceeds
   `MAX_PATH_LENGTH` through this mount) stops classifying as `invalid`
   — the caller sent nothing invalid and no parameter change fixes it
   (the errno-EBUSY overloading pitfall in embryo). It becomes
   `vfs.unaddressable` at `severity=warning`: rows kept, envelope
   successful, loss on record. Its locus is `source` + a reserved
   `data` record written **append-once** (`setdefault`, never dict-union
   clobber) with the entry-local path; because `source` keeps rebasing
   (decision 3), the row's address is reconstructible at any depth —
   fixing the frozen-coordinates and key-clobbering defects. Envelope
   machinery may write only namespaced (`vfs.*`-prefixed) `data` keys.

7. **Retryability is a normative contract table, derived — not a wire
   field.** `ResultError.retry_class` (never / transient / refresh)
   derives from the kind via longest-prefix lookup into a versioned
   table, tested total over the enum; unknown kinds get `None` — no
   assumption, never inherited. Per-kind `data` schemas with defined
   absence semantics are documented beside it (`retry_after_ms` for
   busy/unavailable/timeout, `revision` for conflict). Putting retry on
   the wire was rejected: 9P2000.u's optional errno field rotted to
   permanently-zero because producers never filled it — the kind is the
   wire truth, the table is the contract over it.

8. **`functions: tuple[str, ...]` replaces `function: str`; the
   `'hybrid'` and `''` sentinels die.** Merge is ordered union —
   lossless, both source names survive, no in-band magic value a peer
   could collide with. A `.function` property returns the sole verb or
   `None` (renderers fall back to the generic arrangement on `None`).
   Router-side, `_error` requires the op — the router always knows it;
   `''` defaults disappear.

9. **The envelope opens: `extra='allow'` + lenient per-item
   `from_payload`.** Unknown fields on `Result` and `ResultError`
   round-trip through mid-chain hops instead of being silently stripped
   (repro §8 — the python-sdk `MCPModel extra='ignore'` bug; without
   this, every deployed old hop is a permanent field-stripper and no
   additive evolution is possible). `from_payload` validates
   observations and errors **per item**: a malformed row quarantines as
   a warning-severity `vfs.internal` error carrying the raw item, a
   malformed error as error-severity; a structurally hopeless payload
   returns a fatal `vfs.internal` Result instead of raising (repro §7 —
   today one bad path kills 999 rows and the raw `ValidationError`
   crashes the caller's whole fan-out through `_gather_settled`).
   `strict=True` opt-in restores raise-on-invalid for tests. FUSE's
   boundary clamp, applied per item. Trade-off accepted: adversarial
   field bloat rides the envelope — a size clamp at the parse boundary
   bounds it.

10. **Fan-out demotion happens at the router's merge seam, under the
    zero-progress rule; the algebra stays lawful.** `|` remains a pure
    fold — associative, idempotent, `Result()` identity, rebase
    distributes over merge — with a law-test suite pinning it.
    `Result.merge_branches(results, function=op)` (the successor to
    `_merge_results` at fan-out/tree sites) applies policy: **if any
    branch produced rows or succeeded, failed branches' errors demote to
    warnings — kind, source, retry class intact — and the envelope
    succeeds; if every branch failed, errors stay fatal.** One dead
    mount in twenty ships nineteen mounts' rows past MCP's `isError`
    with one warning (repro §4 fixed); all-dead still fails.
    Creation-context demotion (a per-entry whitelist applied before
    merge) was considered for its associativity purity and **rejected**:
    the zero-progress rule inherently needs cross-branch knowledge, and
    the whitelist variant quietly yields all-warnings success when every
    mount is dead. Scoped dispatch never demotes — an entry the caller
    named fails loudly. Capability skips in unscoped fan-out/tree stop
    being silent: each skipped entry contributes an info-severity
    `vfs.unsupported` entry (recorded coverage, not failure).

11. **Error accumulation is capped at the boundary, never in the
    algebra.** `to_payload(max_errors=…)` groups by `(kind, severity)`,
    keeps the head of each group, and rolls each tail into one entry
    with `data={"vfs.rollup": {count, sources}}` — a 500-mount outage
    ships as one line and a count instead of 500 token-billed entries
    (fc_log's bounded ring; the agent-CLI truncation-as-protocol
    lesson). Capping inside `|` was rejected: it breaks associativity.
    In-process, nothing is ever dropped.

12. **`error.path` semantics are pinned: the implicated row or entry, in
    the reader's namespace, rebased every hop; `None` means "no single
    entry implicated," in which case `source` carries the locus.** A
    per-kind `path_means` note joins the vocabulary's contract table and
    is tested. The two current same-condition divergences close (repro
    §6): `_backend_unsupported` gains entry anchoring (`path=ROOT`,
    rebased to the bind path by the funnel's existing seam — the same
    invariant the `TransportError` arm uses, now documented as the seam
    contract rather than a coordinate pun). The 041-lineage rule
    "capability failures report the entry's bind path" (landed 2026-07-08
    in `_gate_entry`) is the same principle; this story extends it to
    every path-less producer via `source`.

13. **The MCP dual-channel rule is pinned at one seam, both
    directions.** Outbound: `is_error = not result.success` (derived, so
    it cannot lie). Inbound at `VFSStorage` (Pass C): a parseable vfs
    payload is authoritative and `isError` is ignored; `isError=true`
    with no parseable payload synthesizes
    `ResultError(kind=internal, severity=error)` with the peer's prose
    preserved as `message`. Closes the 9P2000.u dual-channel rot before
    it opens.

14. **Hints live in the contract table and the renderer — off the
    wire.** The per-kind table carries an imperative next step ("Unmount
    the bind site first, then retry"); `to_str()` renders each error as
    one agent-facing line — severity, locus, cause, hint, retry
    directive — grouped errors, then warnings, then info. Tokens are
    spent where they change model behavior (the gemini-cli/opencode
    lesson), but a wrong hint on the wire would mislead every consumer
    forever; the renderer can be fixed, a shipped payload cannot.
    `message` stays non-load-bearing and truncatable — "no consumer may
    parse message" graduates from folklore to contract text (the Plan 9
    lesson: writing "advisory" in the spec is not enough; the structured
    channel must be strictly more useful than the prose).

15. **The envelope's own consumers are fixed with it.**
    `_probe_bind_site` dispatches on kind instead of the success bit —
    `not_found` keeps the mkdir advice, `unavailable.*` surfaces the
    transport failure (repro §5). `add_mount`/`remove_mount` raise a
    typed `MountError` carrying the underlying `ResultError` list
    (`str()` stays the prose) instead of flattening kinds into
    `ValueError` text. `_route_fanout` re-applies `max_count`/`limit`
    after the merge so the caller's bound survives composition (repro
    §9).

## Scope

### 1. The envelope (`vfs/results2.py` — rewritten)

- `Severity`, retry-class enum, the normative per-kind contract table
  (retry class, hint, `path_means`), `kind_family()` longest-prefix
  lookup, `_KIND_ALIASES` tombstones.
- `VFSErrorKind`: re-parent `backend_unavailable` →
  `vfs.unavailable.backend`; add `vfs.unaddressable`; docstring gains the
  namespace-partition and prefix-dispatch contract, the
  producer-exclusivity rules (only capability gates emit `unsupported`,
  only dispatch emits `unrecognized`), and per-kind `path_means`.
- `ResultError`: `severity`, `source`; `extra='allow'`; always-copy
  `with_mount` with source stamping and the append-once namespaced
  overflow record; derived `retry_class` and `is_fatal`; value identity.
- `Result`: drop stored `success` (derived property, serialized
  outbound, stripped inbound) and `function` (→ `functions` tuple +
  `.function` property); `extra='allow'`; value-equality
  `_combined_errors`; `merge_branches` with the zero-progress rule;
  `to_payload(max_errors=…)` rollup; lenient per-item `from_payload`
  (+ `strict=True`); `warnings`/`failures` accessors. Row algebra
  (left-wins fill, sequence protocol, sort/top/filter/kinds) unchanged.
- `tests/test_result_laws.py` (new): associativity, idempotence +
  identity, success-is-a-homomorphism, rebase-distributes-over-merge
  (including overflow rows), wire-round-trip dedup equivalence, retry
  table totality, prefix degradation, alias resolution, quarantine
  behavior, reconciliation rule, unknown-severity-reads-as-error.

### 2. Router seams (`vfs/base2.py`)

- `_error`: op required (no `''`), gains `severity` (default `error`),
  drops `success=False` (derived).
- `_backend_unsupported`: `path=ROOT` (entry anchoring via the funnel's
  rebase — one seam contract, stated once).
- `_merge_results` → `Result.merge(results, function=op)` at
  scoped/grouped sites; `Result.merge_branches(...)` at `_route_fanout`
  and `_tree_entry` — the only two demotion sites. Docstring's false
  disjointness claim replaced by the stated bind-path decoration rule
  (repro §10 documented honestly; a row-precedence fix is deferred, see
  open questions).
- Fan-out: capability skips append info-severity `vfs.unsupported`
  entries; `max_count`/`limit` re-applied post-merge.
- `_probe_bind_site`: kind dispatch per decision 15.
- `add_mount`/`remove_mount`: typed `MountError`.

### 3. Backends and renderer (`vfs/backends/memory.py`, `vfs/render.py`)

- memory: delete every `success=…` construction (field gone; `ty`
  enumerates the sites). Unblocked-but-not-forced by the new envelope,
  as a fast-follow: enumerate all failing entries per mutation batch
  instead of first-error (staging already makes this safe), and give
  delete rows `status="deleted"`.
- render: dispatch on `.function` being `None` (kills the `'hybrid'`
  branch); errors render one line each via the contract table (severity,
  locus, cause, hint, retry directive), grouped errors → warnings →
  info; rollups render their counts.

### 4. Ripples

- 056 spec: note on decision 12 (`backend_unavailable` value
  re-parented, alias kept) and decision 7 (`_merge_results` docstring
  correction superseded by the stated decoration rule). Pass C scope
  inherits decision 13's dual-channel rule and the payload freeze.
- `exceptions.py` boundary mapping: `exception_for_kind` consults
  `kind_family` so unknown child kinds degrade partially.
- This directory's `repro.py` assertions invert as the fixes land; the
  file retires with the story (its cases live on in
  `test_result_laws.py` and the reworked suites).

## Acceptance criteria

- `Result(success=True, errors=[not_found])` is unrepresentable; a wire
  payload carrying `success` has it ignored and re-derived, and the
  claiming-failure-without-errors payload synthesizes the reconciliation
  error. (repro §1)
- The diamond `(a | b) & b` yields identical errors before and after a
  `to_payload`/`from_payload` round-trip; two identical failures from
  two mounts both survive with distinct `source`. (repro §2, §3)
- Unscoped grep, one dead mount of two: `success=True`, the live
  mount's rows present, one warning with
  `kind=vfs.unavailable.backend`, `source=/dead`, retry class
  transient. Both mounts dead: `success=False`. Scoped grep at the dead
  mount: `success=False` (no demotion). (repro §4)
- Rebase overflow: rows kept, envelope successful, one
  `vfs.unaddressable` warning whose locus reconstructs as
  `source + local_path` after three further hops. (repro §6 family)
- An unknown kind `vfs.unavailable.dns` dispatches as `unavailable`
  (prefix degradation); the retired string `vfs.backend_unavailable`
  parses to the new kind; unknown severity reads as `error`.
- `from_payload` with one corrupt row keeps the other rows and records
  one quarantine warning; a corrupt error becomes an error-severity
  quarantine; `strict=True` raises. A novel field on an error survives
  a full hop (parse → re-serialize). (repro §7, §8)
- `bind` beneath a dead backend reports the transport failure, not
  mkdir advice. (repro §5)
- `glob(max_count=1)` over two matching mounts returns one row.
  (repro §9)
- `test_result_laws.py` green; suite/ruff/ty green on touched files.

## Open questions

All resolved (review 2026-07-08):

- **Severity `fatal` tier: deferred.** Additively safe later under
  unknown-reads-as-error; envelope-unreliability is expressible today as
  `kind=vfs.internal` + error severity.
- **`vfs.cancelled` split (who cancelled, is retry sane — LSP's three
  codes): deferred** until a consumer needs it; keep the vocabulary
  under ~20 kinds (the LSP RequestFailed discipline).
- **Row ordering across merges (mount-major concatenation vs fused
  ranking for glean): deferred.** An envelope-level ordering semantic is
  real but orthogonal; recorded, not designed here.
- **Bind-path row fusion in left-wins fill (repro §10): documented, not
  redesigned.** The decoration rule is stated honestly at the merge
  seam; a row-precedence mechanism is a later story if composition
  through adapters makes the fusion visible in practice.
- **Backend first-error mutation reporting: unblocked, not forced.**
  The envelope now supports per-entry mutation enumeration; memory
  adopts it as a fast-follow, the storage contract does not yet require
  it.
- **Retry on the wire: rejected outright** (9P2000.u rot); revisit only
  if a non-vfs consumer of raw payloads materializes with no access to
  the contract table.
