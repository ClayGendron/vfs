# 057 — Research corpus (distilled)

Method: 8 primary-source studies over local reference repos
(`~/Git/Repos/{linux, plan9, plan9port, libfuse, filesystem_spec,
modelcontextprotocol, python-sdk, sqlite, language-server-protocol,
opencode, gemini-cli}`), then 2 adversarial critics of the current
`results2.py` informed by all studies, then 3 independent redesign
proposals (wire-first, algebra-first, agent-first). This file keeps the
load-bearing findings; spec.md holds the adjudicated decisions.

## The one unanimous finding

Every studied system makes verdict/evidence disagreement
**unrepresentable**: errno (`ret < 0` IS the verdict), 9P (the reply
type byte), FUSE (`error == 0` in the out header), LSP (`result` XOR
`error`, "result MUST NOT exist if there was an error"), SQLite
(`SQLITE_OK == 0`), MCP (`isError` absent = false, derived into
TaskStatus), gemini-cli (`success = toolResult.error === undefined`).
No system stores a success bit beside its evidence. vfs's stored bool
is the outlier, and its three producer idioms have already drifted.

## Per-system lessons (with the vfs consequence)

### Linux (errno + fs_context log)

- Flat integer codes forced brutal overloading: EBUSY alone means
  umount-has-users, rmdir-of-mountpoint, already-mounted-here,
  wrong-fsconfig-phase, and a pivot_root *loop* (fs/namespace.c:4695
  literally `return -EBUSY; /* loop */`). Once shipped, disambiguation
  is impossible. → Never let `vfs.busy` (or `vfs.invalid`) absorb a
  second meaning; mint kinds before ambiguity ships.
- errno cannot express partial success; the workarounds are the scar
  tissue: short-write silently drops the errno of the failed tail;
  errseq_t collapses N page errors into one 32-bit slot (the fsync
  data-loss bug class); the mount API bolted on fc_log — a bounded ring
  of 8 severity-prefixed prose strings — 25+ years later because codes
  alone couldn't explain mount failures. → rows+errors coexistence is
  strictly richer; keep it; add severity as a *field*, not a parallel
  list; bound merged error lists.
- The kernel keeps internal-only codes (ERESTARTSYS, EPROBE_DEFER,
  ENOPARAM — "should never be seen by user programs") translated at the
  boundary; ENOSYS is contractually policed. → keep the
  unsupported/unrecognized exclusivity rules; internal sentinels never
  cross the wire.
- errno carries no locus because the syscall caller owns all context —
  an assumption that dies the moment results outlive their call site
  (exactly vfs's post-merge fan-out). → record locus eagerly at
  production; anything implicit is permanently unrecoverable.

### Plan 9 / 9P (Rerror strings)

- Error-as-string meant classification was possible only via prose —
  and everyone, including the kernel, ended up strcmp-ing error text;
  each producer's prose became a de-facto incompatible vocabulary.
  9P2000.u retrofitted numeric errno as a *second optional channel* and
  it rotted: plan9port's decoder zeroes `errornum` on every Rerror
  because native producers never filled it. → kind stays mandatory;
  **optional dual channels rot** — new fields must be
  defaulted-by-construction or derived, never optional-and-parallel
  (this killed retry-on-the-wire).
- exportfs relays the error string verbatim across hops — that worked;
  werrstr prefix-chaining ("%s: %r") broke exact matchers — that
  failed. → rebase seams touch path/source/data, never message.
- "The string is only advisory" written in the spec did not stop the
  kernel from parsing it. The only durable defense is making the
  structured channel strictly more useful than the prose. → severity +
  source + retry class on every error; contract text forbids parsing
  message.

### libfuse

- No success bit anywhere; success IS `error == 0`. The reply layer
  validates codes at the boundary and clamps unknown ones (-ERANGE)
  rather than trusting producers. → derive success; validate at the
  wire seam, per item.
- Every device-level failure funnels through one switch with three
  outcomes (permanent/transient/interrupted). → the 056 funnel's
  TransportError normalization is this done right; keep one seam.
- FUSE separates per-request errors from `se->error`, the
  session-fatal slot. → "this row failed" ≠ "this envelope is
  unreliable"; expressed via severity + `vfs.internal` (fatal tier
  deferred).
- ENOSYS is cached by the kernel — capability refusal has permanence
  semantics. → `unsupported`/`unrecognized` documented
  cacheable-permanent per (mount, op); retry class `never`.
- Rich userspace error info squeezed through int32 survives only as a
  stderr perror nobody consumes. → any hop that narrows an error must
  carry the original forward in-band (`data`, append-only).

### fsspec (filesystem_spec)

- Batch error attribution is *structural* — the exception occupies the
  failing item's slot (dict key / list index), so which-entry-failed is
  never lost and dedup has no identity problem. → errors need a
  mandatory anchor; vfs's optional path with producer-dependent
  semantics is the anti-pattern.
- `on_error` grew four incompatible per-method vocabularies with
  context-dependent defaults; `_cat_ranges` accepts-and-ignores the
  parameter. → uniform envelope semantics across operations; no
  declared-but-unenforced contract (the stored success bit is exactly
  this).
- `on_error='omit'` silently loses failures with zero audit trail;
  `return_exceptions=False` raises the first error, cancels siblings,
  and discards completed work. → never drop without a trace; never
  first-error; keep all-errors concatenation.
- Single-path returns bytes, multi-path returns dict — shape-dependent
  returns force defensive code everywhere. → always-a-Result stays.

### MCP (spec + python-sdk)

- Two-level error model: protocol-level JSON-RPC errors vs tool-level
  `isError` results; tool failures must never become protocol errors.
  → the Result payload is tool-level; one boundary adapter maps both
  directions (spec decision 13).
- `isError`'s absence is false, and TaskStatus derives from it — a
  lying success bit misclassifies the whole call for pollers. → derive.
- The python-sdk's pydantic `extra='ignore'` strips unknown fields at
  every hop even though the TS schema makes every object open — a
  proxy is a field-stripper. → `extra='allow'`; this is the exact bug
  repro §8 reproduces in vfs.
- The SDK's catch-all flattens tool exceptions to prose with
  `is_error=true` and emits `ErrorData(code=0)` — a code in no defined
  range. → the inbound synthesis rule must produce a real kind
  (`vfs.internal`), never a placeholder.
- Numeric code ranges collide (-32000 squatted twice, no registry).
  → namespaced string kinds are the right call; numeric mapping, if
  ever needed, is a lossy projection.

### SQLite (result codes)

- The definitive taxonomy-retrofit case study: flat primary codes
  (1-101) needed fine distinctions (BUSY vs BUSY_SNAPSHOT, the IOERR
  family), and the fix — extended codes as `primary | (n << 8)`, maskable
  down via `rc & 0xff` — required a per-connection opt-in API,
  an errMask field, dual accessors, and is *still off by default* two
  decades later. → hierarchy goes in pre-1.0 or never cleanly;
  `vfs.unavailable.backend` + longest-prefix dispatch is the textual
  equivalent, nearly free today.
- Split a kind exactly when the correct client reaction differs
  (BUSY: time-driven retry; LOCKED: event-driven; BUSY_SNAPSHOT:
  abandon) — reaction, not cause taxonomy, is the criterion. → the
  audit rule for any future kind proposal.
- Precision that would mislead is deliberately withheld
  (BUSY_SNAPSHOT downgraded to BUSY where the finer meaning is wrong);
  internal signal codes are asserted never to escape. → producers emit
  a fine kind only when its specific semantics hold.
- Retired codes are permanent "Not Used" tombstones. → `_KIND_ALIASES`
  forever; never reuse a shipped string.

### LSP

- Two-layer split: ResponseError (request failed) vs Diagnostic
  (severity, source, code, relatedInformation) on successful responses
  — a report full of error-severity diagnostics is still a *successful
  response*. → severity on ResultError; success derives from severity,
  not presence.
- Absent/unknown severity reads as Error — never silently downgrade
  the unknown. → adopted verbatim.
- Reserved code bands, capability-gated field evolution, deprecated
  aliases carried forever, and its own scar tissue (codes squatting in
  JSON-RPC's reserved band "for backwards compatibility"). → pin the
  namespace partition before third parties emit kinds; new fields
  optional-with-safe-defaults.
- Three cancellation codes (RequestCancelled / ServerCancelled /
  ContentModified) because clients handle each differently. → recorded;
  `vfs.cancelled` split deferred until a consumer needs it.
- Per-code data schemas with defined absence semantics
  (DiagnosticServerCancellationData.retriggerRequest defaults true).
  → the per-kind data schema table.

### Agent CLIs (opencode, gemini-cli)

- Both derive success from error presence; neither stores it.
- Both refuse to fail an envelope that made progress: gemini reserves
  the error field for zero-progress outcomes (partial reads succeed
  with skip records); opencode's batch reports 3/5 as success. → the
  zero-progress rule for fan-out demotion.
- Errors are written for the model, ending in an imperative next step
  ("Use offset/limit to view more", "Did you mean one of these?").
  → the hint column in the contract table + one-line rendering.
- Truncation is a continuation protocol, not a caveat: central caps,
  spooled full output, machine-readable counts, explicit continuation
  instructions. → `to_payload(max_errors)` rollups with counts.
- Neither dedups errors at all — each failure is keyed to its producing
  call (opencode's callID). → provenance-keyed identity, not heuristic
  dedup.
- gemini's `returnDisplay` carries an in-source regret note about UI
  concerns in the tool envelope. → keep the payload display-free.
- opencode's string-typed errors force message-sniffing for retry
  ('Overloaded'.includes) — the counter-example for prose-only.

## Critic findings (adversarial pass over results2.py + base2.py)

Fundamental (all verified against live code; repro.py reproduces each):

1. `success` stored, invariant enforced nowhere; three producer idioms
   drift; merge ANDs trust it never checks; MCP fold inherits the lie.
2. `id()`-based dedup: diamond double-counts after one wire round-trip;
   identity depends on whether the error carried a path (with_mount
   returns self for path=None); no origin field anywhere.
3. `error.path` has five incompatible referents by producer (row-local
   rebased; bind path at the gate; ROOT-sentinel coordinate pun at the
   TransportError arm; None at `_backend_unsupported` for the same
   condition the gate anchors; None + data locus on overflow).
4. No severity channel: one dead mount fails a 20-mount fan-out's
   envelope with 19 mounts' rows hidden behind isError; rebase overflow
   fails whole results; fan-out capability skips are silently
   unrecordable.

Significant: `from_payload` strips unknown fields (contradicting the
documented lossless claim) and is a per-envelope poison pill (one bad
path destroys all rows and the raw ValidationError crashes the fan-out
via `_gather_settled`); overflow classified `vfs.invalid` (caller-input
kind for a topology condition) with its locus frozen in hop-local
coordinates and dict-union key clobbering; `_merge_results`'
disjointness docstring false at bind paths (tree fuses two backends'
rows via left-wins fill); `max_count` multiplies by mount count;
`function` free string with two in-band sentinels ('hybrid', '');
`backend_unavailable` a flat sibling of `unavailable` (the SQLite
trap); retryability prose-only; dual isError/success channel unpinned
inbound; unbounded merged error lists; `_probe_bind_site` consumes only
the bit (mkdir advice against a dead backend); mutation batches report
first-error-only and delete rows carry no status.

## Defenses (choices that must survive — no design argued them down)

- Rows and errors coexisting in one envelope; per-row read
  classification. Strictly richer than errno/9P/FUSE; FUSE's silent
  readdir omission is the counter-example.
- Unknown-kind preservation as raw string + broadest-fallback; extend
  the discipline to new open fields, never remove it.
- All-errors concatenation, never first-error-wins; fix identity, not
  the keep-everything policy; equality dedup without provenance
  over-collapses (errseq/fsync lesson).
- One uniform Result envelope; router never raises on caller input.
- The single classification funnel (TransportError → one seam).
- kind mandatory / message never load-bearing / machine detail in data;
  messages never rewritten in transit.
- One serializer (to_payload via model_dump_json); payload display-free.
- unsupported/unrecognized exclusivity; budget_exhausted separate from
  busy/timeout (never let a retryable kind absorb it).
- Batch mutations staged-and-committed atomically at the storage seam.

## Design-lens adjudication (spec decisions 10, 11, 14 record outcomes)

- **Wire-first** contributed: payload-as-contract framing, extra='allow'
  + shim rules, namespaced envelope data keys, the no-wire-retry-field
  argument, kind_family.
- **Algebra-first** contributed: the law-test suite (associativity,
  identity, success-homomorphism, rebase-distributes, round-trip dedup
  equivalence), always-copy with_mount, cap-outside-the-algebra. Its
  creation-context demotion (per-entry whitelist pre-merge) was
  rejected: it cannot express the zero-progress rule — all mounts dead
  would demote to all-warnings success.
- **Agent-first** contributed: merge_branches + zero-progress at the
  router seam, the contract-table hint column and one-line rendering,
  MountError, probe kind-dispatch. Its wire `retry`/`hint` fields were
  rejected (9P2000.u rot; misleading-hint permanence).
