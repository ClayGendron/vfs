# 106 — Bytes through the content path: BLOB fetch and a bytes-native verify seam

- **Status: drafted 2026-08-17** — from two independent
  measurements: the fetch-path study during the scoped-grep
  optimization arc (`CAST(content AS BLOB)` fetched 181.6 MB in
  55.6 ms vs 63.1 ms as text, −12%, while also skipping an 11.4 ms
  Python-side UTF-8 encode — ~25% off fetch+encode combined) and
  the storage-organizations research
  (`../../../research/2026-08-17-search-storage-organizations.md`),
  whose line-offset experiment independently found the seam's
  re-encode is 4.9 ms of the 7.6 ms whole-corpus verify. Ranked
  there as the top open lever on the local backend.
- **Date:** 2026-08-17
- **Owner:** Clay Gendron
- **Kind:** a fetch-representation change inside the database
  backend plus a widened native seam. No schema change — content
  stays `str`-typed at rest; the cast happens at query time. No
  contract, verb, or Result shape moves: observations still carry
  `str` content, matches still carry `str` lines.
- **Depends on:** spec 103 (the Rust verify core and the
  `vfs/native.py` seam this widens), spec 104 / the perf landing
  (the fetch and gate shapes this modifies), ADR 039 (verify
  authority — the core stays the match authority over bytes as it
  is over text).
- **Relates to:** the parked chunk-granularity design (same study —
  if ever revived for a networked engine, it composes with this
  seam), spec 098 (literal text and line semantics — the decode
  rules below must preserve its contracts).

## Intent

Content is stored as `str` and travels the read path as `str`:
sqlite3 decodes UTF-8 inside the driver, the seam re-encodes to
UTF-8 bytes for the Rust matcher, and matching lines are sliced
from the Python string. Both directions of that round trip are
measured waste: the driver-side decode inflates fetch (~12% on
bulk content reads), and the seam-side encode is the majority of
verify's wall time (4.9 of 7.6 ms per 94 MB). The Rust core is
byte-exact already — the `str` leg exists only because the fetch
hands us text.

The fix is to fetch content as bytes where the engine can cast
cheaply, verify bytes end-to-end, and decode only what the caller
actually receives: matching lines and hit observations. Non-hit
candidates — the overwhelming majority of fetched bytes on heavy
rows — are never decoded at all.

Laws that bind the slices:

1. **Byte-identical results.** Match sets, line numbers, line
   text, counts, truncation reporting, and error shapes are
   unchanged on every row of both benchmark ladders. Content is
   valid UTF-8 by construction (it was `str` at write time), so
   decode-on-hit is lossless; a decode failure is an internal
   error, never a silently different result.
2. **The seam keeps one authority and two engines.** The Rust core
   and the pure-Python fallback both accept the bytes form, and
   `tests/test_native.py` pins them byte-identical over it, as
   today. `VFS_PURE_PYTHON=1` continues to force the fallback.
3. **Portable by default, cast where measured.** The bytes fetch
   is a per-dialect capability: engines whose text→bytes cast is
   free-or-cheap opt in; everything else keeps today's `str` path
   through the same code (the seam accepts both). No engine is
   required to change behavior to stay correct.

## Shape

- **§1 The bytes fetch.** The candidate-fetch and scan-tier
  statements select content through a dialect-conditional cast to
  the engine's bytes type (sqlite `CAST(content AS BLOB)`; other
  engines per their audit, §3). The cast is expressed once at the
  statement-construction site behind a small seam so callers never
  branch on representation. Pushdown predicates, chunking, budgets,
  and ride-along columns are untouched.
- **§2 The bytes-native verify seam.** `vfs/native.py`'s batch
  calls accept `bytes | str` bodies; the Rust binding takes the
  bytes without re-encoding (the current owned-conversion machinery
  already handles the buffer forms), and the pure-Python fallback
  operates on the same bytes with identical semantics. Line
  extraction returns byte offsets/slices; the assembly layer
  decodes hit lines (and hit observations' content field, when the
  output mode carries it) at the boundary where `str` enters the
  Result models. The case-fold and line-semantics rules of the
  matcher are byte-defined already and must not drift.
- **§3 The per-engine cast audit.** For each floor engine, record:
  the cast expression, whether it is server-side free or a copy,
  and whether the driver returns bytes without its own decode.
  sqlite is measured (−12% fetch, encode eliminated). Postgres
  (`convert_to`/`bytea`), MSSQL, MySQL, Oracle are hypotheses to
  measure in the `db_test` legs — an engine measuring worse keeps
  the `str` path via its profile, which is the §1 seam's fallback
  arm, not a special case. Unknown dialects (GENERIC) stay on
  `str`.
- **§4 The bench gate.** Both ladders re-run: expect the heavy
  fetch rows to move (~25% of their fetch+encode share —
  `mutex_lock @ drivers/gpu/drm/**` is the headline), zero
  regressions elsewhere, identical counts everywhere. The
  per-candidate fetch micro-bench re-runs so the recorded
  ~9.6 µs/candidate constant stays honest. Budget re-derivation
  recorded if the constants move it (they should not — the change
  shrinks per-candidate cost).

## Slices

- **A. The seam.** §2 without any fetch change: bytes-capable
  native + fallback, parity pinned over bytes and str inputs,
  decode-on-hit in the assembly layer proven equal on a corpus
  battery (including multi-byte UTF-8 at line boundaries, the
  spec 098 semantics).
- **B. The sqlite fetch.** §1 behind the dialect seam for sqlite
  only; statement-shape pins; both ladders re-run (§4's sqlite
  numbers).
- **C. The audit legs.** §3's per-engine `db_test` measurements
  (skip without servers); profiles updated only where an engine
  measures a win; the record updated with whatever the servers
  say.

## Open questions

- **Non-UTF-8-representable engines.** If a future backend stores
  content in an encoding whose bytes are not the UTF-8 of the
  `str` (collation-transformed storage), its cast must be declined
  in the audit — the seam's `str` arm exists precisely for that.
  No such engine is currently on the floor list; recorded so the
  audit checks for it explicitly.
- **Chunked-content interaction.** Chunk rows also carry content;
  if the parked chunk-granularity design ever revives, its fetch
  should be born on the bytes arm rather than ported later. No
  action now.
