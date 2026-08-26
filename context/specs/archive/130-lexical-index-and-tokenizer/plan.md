# 130 — plan

The spec fixes the tables, the formula, the tokenizer rules, and the
epoch discipline; this plan records the four places where building it
took a decision the spec left open or where reality disagreed with the
spec's sketch.

## 1. The build is a two-pass stream, not a whole-corpus builder

The spec sketched one builder that tokenizes every chunk, holds the
postings, and computes weights once the last document fixes `df`. On
the linux store that residency is not a slow path but an out-of-memory:
the 4,000-file sample already carries 3.1 M postings (96 per chunk), so
the full checkout is ~60 M postings held as Python tuples — a reindex
that succeeded before this spec would fail after it.

`LexicalIndexBuilder` therefore makes **two passes over the same chunk
stream**: `observe` counts `df`, `N`, and the length total and hands
back the batch's `lex_docs` rows; `finish` fixes the statistics and
every term's idf; `weigh` re-tokenizes each batch into its weighted
`lex_terms` rows. Nothing but the vocabulary (one `df` per distinct
term — 487 k entries on the sample) is held across batches, every table
is written in bounded inserts as batches complete, and the SQL stays
plain inserts on every dialect (no `UPDATE … FROM`, no `LN()` — both
dialect-divergent). The price is tokenizing twice, which is precisely
the number the spec asks to record as the Rust-port trigger (§ landing
note in `spec.md`).

## 2. Insert batches are row-budgeted, not byte-metered

Every `lex_*` row is bounded-width (a term is ≤ 64 bytes post-fold), so
a row budget *is* a byte budget; `_LEXICAL_INSERT_ROWS = 20_000` bounds
one insert, and SQLAlchemy's `insertmanyvalues` splits each on the
dialect's bind cap beneath it. The tokenize batches stay byte-metered
(`ByteBatcher`, 4 MiB of content per hop — pass two's transient term
rows are ~100 per chunk, so the hop budget also bounds that transient).

## 3. Schema choices

- `term` is `BytewiseString(MAX_TERM_BYTES)`: the key must compare
  bytewise (an accent- or case-unifying collation would collide two
  folded terms on the PK); the mysql family gets `VARBINARY(64)`,
  MSSQL the BIN2 UTF-8 collation, Postgres `COLLATE "C"`.
- `weight`, `idf`, `avg_dl` are `Double` — `Float` is single precision
  on MySQL, which would make the rounding-before-order law engine-
  dependent. Oracle maps it to `DOUBLE PRECISION` (a NUMBER subtype
  wide enough to round-trip a float64).
- SQLite tables are `WITHOUT ROWID`: a PK-only table with a rowid
  stores every row twice (98 MB table + 76 MB autoindex on the
  sample); the clustered engines (InnoDB, MSSQL) already store the row
  in the key B-tree.
- `VFSTables.epoch_scoped()` names every epoch-keyed table so the two
  reclaim sweeps and any future epoch consumer cannot forget one.

## 4. Tokenizer edges the spec left implicit

- One-character terms are dropped whether whole or part (`x_y` keeps
  `x_y`, drops both parts); the spec said "parts", the rule is applied
  uniformly because a one-letter whole carries the same non-signal.
- Case change is lower/digit → upper, or the last capital of an
  acronym run (`HTTPServer` → `http`, `server`; `sha256Hash` → `sha256`,
  `hash`). A digit-led piece never splits (`0xDEADbeef` stays whole).
- `\w+` is the run — Python's Unicode alphanumerics plus underscore,
  the closest stdlib spelling of `[\p{L}\p{N}_]`.
- The chunk scan's `indexable` predicate is documentary: `chunk_dirty`
  writes chunk rows only for eligible bodies, so an ineligible entry
  never has rows to scan. It is kept for parity with the gram scan's
  spelling of the coverage set; a mutation dropping it survives the
  suite by design and is not a ledger row.
- The options hash reads the lexical constants *live*
  (`options_fingerprint()`), so a monkeypatched or retuned constant
  moves the fingerprint and forces the rebuild the ledger row demands.

## Order of work

A — `models/lexical.py` and its pins; B — tables, `build_epoch`
extension, reclaim parity, format bumps; C — `lexical_stats`, the
fidelity referee (`tests/support/lexical_fidelity.py`, shared by the
sqlite test and the four engine legs), the linux-store measurements.
