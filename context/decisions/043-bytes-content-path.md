# 043. Bytes Through the Content Path: the `content_bytes` Fact and the Bytes-Native Seam

- **Status:** accepted 2026-08-17 — spec 106's decision set,
  written at its mining pass.
- **Date:** 2026-08-17
- **Deciders:** Clay Gendron (portable-by-default, sqlite-specific
  tuning explicitly licensed — sqlite is the local store that races
  ripgrep toe-to-toe).
- **Context source:** two independent measurements — the fetch-path
  prototype (`CAST(content AS BLOB)`: −12% on bulk content fetch
  plus the skipped Python-side encode, ~25% off fetch+encode
  combined) and the storage-organizations research
  (`../research/2026-08-17-search-storage-organizations.md`), whose
  line-offset experiment found the seam's re-encode was 4.9 ms of
  the 7.6 ms whole-corpus verify. Implemented by spec 106.

## Context

Content is `str`-typed at rest and traveled the read path as
`str`: the driver decoded UTF-8 into Python strings at fetch, and
the verify seam immediately re-encoded them to UTF-8 bytes for the
Rust matcher — both directions measured waste, paid per candidate,
scaling with body bytes. The stored bytes were already exactly what
the matcher wanted.

## Decision

1. **The verify seam is bytes-native** (`Body = str | bytes`
   through `ContentMatcher`, `verify`, `match_texts`): the core
   takes bytes without the per-call encode; the pure-Python
   fallback decodes them — mirror conversions, results pinned
   identical four ways (engine × spelling) including multi-byte
   UTF-8 at line boundaries and mixed batches.
2. **`content_bytes` is a `DialectProfile` fact**: the engine's
   bytes cast returns exactly the content column's UTF-8 bytes as a
   cheap reinterpretation. Where declared, grep's body fetch
   selects the cast and only *hit* rows ever decode, at assembly.
   **Never declare it where the cast transcodes** (NVARCHAR's
   UTF-16) or where the database character set may not be UTF-8 —
   wrong bytes match nothing, silently.
3. **Declared for sqlite only; every server earns it through an
   audit leg.** The per-engine `db_test` legs assert the candidate
   cast yields the body's exact UTF-8 bytes: Postgres
   `convert_to(content, 'UTF8')`, MySQL `CAST AS BINARY`, MSSQL
   `CAST AS VARBINARY(MAX)` — valid for our schema because the
   content column is VARCHAR(max) under the pinned UTF-8 collation,
   not NVARCHAR. Oracle is recorded as declined (CLOB reaches bytes
   only through a DBMS_LOB copy). Profiles flip only on a real
   server run's evidence.

## Consequences

- Every unscoped benchmark row moved 6–25% (`copyright -i`
  665 → 624 ms; zero-hit floor 55 → 41 ms); the scoped board
  reached 11-of-12 ahead of rg, counts identical everywhere.
- Fetch alone is arm-neutral (~8.5 µs/candidate at typical body
  sizes) — the win is the eliminated byte-proportional
  decode+encode on large bodies. Recorded so nobody expects the
  cast to speed up small-body fetches.
- The content column's at-rest type is unchanged; the cast is a
  query-time representation choice, reversible per engine by
  flipping its profile fact.
