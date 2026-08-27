# 010. Result Envelope: Evidence In, Verdict Derived

- **Status:** accepted
- **Date:** 2026-07-16
- **Deciders:** Clay Gendron
- **Decided by:** human (research review 2026-07-08 — 8 primary-source
  studies, 2 adversarial critics, 3 design lenses; owner amendments
  same day; this record makes the bundle binding)

## Context

`Result` stored its verdict beside its evidence: `success` was an
independent bool, errors carried no severity, no provenance, and no
machine-readable retry semantics, and error identity was `id()`-based.
None of that survives what story 056 built the envelope for — being
merged across fan-out entries, rebased across mount seams, and
serialized across MCP hops. The story's `repro.py` reproduced ten live
defects, among them: a lying `success=True`-with-errors state that was
default-constructible and wire-survivable; dedup double-counting after
one wire round-trip; one dead mount in a fan-out hiding every live
mount's rows behind `isError=true`; one malformed remote path
destroying a 1,000-row envelope and crashing the caller's fan-out; and
mid-chain hops silently stripping any field a newer peer added.

These are wire-shape decisions: the Result payload is the vfs MCP
dialect's `structured_content`, and after the first independent peer
ships, kind strings and fold rules are permanent. The study corpus
(`context/research/2026-07-08-result-envelope.md`) found the reference
systems — errno, 9P, FUSE, fsspec, MCP, SQLite, LSP, agent CLIs —
differ in almost everything except one thing: **verdict/evidence
disagreement is unrepresentable** (errno's `ret<0`, 9P's reply type,
FUSE's `error==0`, LSP's result-xor-error, SQLite's `code==0`).

## Options considered

- **Keep the stored `success` bool** — rejected: three producer idioms
  had already drifted in-repo, and the lying state rode the wire.
- **A `fatal` severity tier** — deferred, additively safe later: under
  unknown-reads-as-error, old readers degrade it to `error`, the
  correct conservative read.
- **Retry class as a wire field** — rejected: 9P2000.u's optional errno
  rotted to permanently-zero because producers never filled it; the
  kind is the wire truth, the table is the contract over it.
- **Capping errors inside `|`** — rejected: breaks associativity;
  capping is a boundary concern (`to_payload`).
- **Per-entry whitelist demotion** — rejected: the zero-progress rule
  inherently needs cross-branch knowledge, and the whitelist variant
  quietly yields all-warnings success when every mount is dead.

## Decision

The envelope carries **evidence** — frozen error values with severity,
provenance, and pinned locus semantics — and every verdict is
**derived** from that evidence. The bundle, governing `src/vfs/results/`:

1. **`success` is derived, never stored** — a property, true iff no
   fatal-severity entry (`src/vfs/results/envelope.py:280`); serialized
   outbound for isError-checking MCP clients, stripped and re-derived
   inbound. A peer payload claiming failure with no classifiable error
   synthesizes a reconciliation `vfs.internal` error carrying the claim.
2. **`severity: error | warning | info` on `ResultError`**, with
   unknown-or-absent reading as `error` — never silently downgrade
   (`src/vfs/results/kinds.py:106`, `envelope.py:145`). Warning = loss
   or caveat, rows trustworthy; error = something asked for failed;
   info = advisory (capability skips, rollups).
3. **`source` provenance, stamped structurally at the rebase seam** —
   the bind path of the producing hop, in the reader's namespace;
   `with_mount` always returns a copy and re-roots on every hop
   (`envelope.py:154`), so which mount produced an error survives any
   merge depth with zero producer discipline.
4. **Error identity is value identity; `id()` dies.** Frozen value
   equality is the dedup key; diamond chains collapse on both sides of
   a wire hop, and two mounts failing identically stay two facts
   *because their sources differ* — equality dedup without provenance
   was rejected as over-collapsing (the errseq/fsync lesson).
5. **The kind vocabulary is hierarchical**: dotted kinds with normative
   longest-prefix dispatch (`kind_family`, `kinds.py:248`) and
   permanent tombstoned inbound aliases (`_KIND_ALIASES`,
   `kinds.py:91` — `vfs.backend_unavailable` →
   `vfs.unavailable.backend` is the first). Unknown kinds degrade to
   their longest known prefix. Namespace partition pinned before any
   peer ships: `vfs.*` is core; backends mint under `x.<vendor>.*`.
6. **Retryability is a derived contract, not a wire field**:
   `retry_class` (never/transient/refresh) derives from the kind via
   longest-prefix lookup into the versioned `KIND_CONTRACTS` table
   (`envelope.py:149`); unknown kinds get `None`, never an assumption.
7. **The envelope is open and parsing is lenient per item**: both
   models are `extra='allow'` (`envelope.py:107,255`) so unknown fields
   round-trip through mid-chain hops; `from_payload`
   (`envelope.py:633`) quarantines a malformed row as a warning and a
   malformed error at error severity instead of destroying siblings —
   a structurally hopeless payload returns a fatal `vfs.internal`
   Result rather than raising (`strict=True` restores raise for tests).
   `to_payload(max_errors=…)` rolls up at the boundary, never in the
   algebra (`envelope.py:603`).
8. **Fan-out demotion is the zero-progress rule at the merge seam**
   (`merge_branches`, `envelope.py:472`): if any branch produced rows
   or succeeded, failed branches' errors demote to warnings — kind,
   source, retry class intact — and the envelope succeeds; if every
   branch failed, errors stay fatal. Progress is envelope-level, not
   per-branch. Scoped dispatch never demotes — an entry the caller
   named fails loudly. Capability skips become info-severity
   `vfs.unsupported` coverage records instead of silence.

## Consequences

- **Easier:** one dead mount in twenty ships nineteen mounts' rows past
  MCP's `isError` with one warning; agents dispatch retries on
  structured fields; additive evolution survives deployed old hops; the
  lying envelope is unrepresentable; the merge algebra stays lawful
  (associative, idempotent, `Result()` identity — pinned by
  `tests/test_result_laws.py`).
- **Harder:** a producer that fails without minting an error now yields
  silent success (the funnel as single classification seam is the
  mitigation); adversarial field bloat rides `extra='allow'` (bounded
  by a size clamp at the parse boundary); demoted permanent kinds
  (e.g. `permission_denied`) can arrive as warnings when siblings
  progressed — kind and retry class stay intact for consumers needing
  the distinction.
- **Committed to:** shipped kind strings are never renamed or reused —
  only tombstoned (SQLite discipline); `message` is never load-bearing
  ("no consumer may parse message" is contract text); hints live in
  the contract table and renderer, off the wire.

Executed by story 057 (`context/specs/archive/057-result-envelope/`).
Evidence: `context/research/2026-07-08-result-envelope.md`.
