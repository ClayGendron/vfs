# FTS5 trigram tokenizer divergence — native FTS5 is not VFS's gram alphabet

- **Status:** recorded — extracted 2026-07-16 from story 013's
  `analysis-fts5.md` / `analysis-zoekt.md` evidence files during the archive
  mining pass (source-verified against `fts5_tokenize.c` / zoekt at the time
  of the original 2026-05-27 analysis)
- **Supersedes (in part):**
  `2026-05-25-database-agnostic-code-trigram-index.md` — its claim that
  `tokenize='trigram case_sensitive 1'` is "a native code-search-ish option"
  is corrected below.

## The finding

SQLite's native FTS5 trigram tokenizer produces a **different gram alphabet**
from VFS's byte-trigram stream for any non-ASCII content. Native FTS5 trigram
tables can therefore never produce VFS's canonical grams — they are usable as
an independent SQLite read accelerator, but **not** as the SQLite backend's
read path with identical candidate semantics.

Three substantive divergences (`fts5_tokenize.c:1275-1421`,
`fts5TriCreate` / `fts5TriTokenize`):

1. **Per-codepoint, not per-byte.** FTS5 fills its window with 3 decoded
   UTF-8 codepoints (`READ_UTF8`, `fts5_tokenize.c:1369-1377`) and slides one
   codepoint at a time (`fts5_tokenize.c:1406-1417`). VFS slides over raw
   UTF-8 bytes, so a 3-byte non-ASCII codepoint becomes byte-trigrams FTS5
   would never emit. Pure-ASCII content coincides (1 byte = 1 codepoint).
2. **Case-fold without NFC.** FTS5 folds per codepoint
   (`sqlite3Fts5UnicodeFold`, `bFold` default 1) but never NFC-normalizes —
   `café(NFC)` and `café(NFD)` index differently. VFS NFC-normalizes before
   folding; VFS is stricter here.
3. **Diacritic skipping.** Under `remove_diacritics`, codepoints folding to 0
   are skipped mid-trigram (`fts5_tokenize.c:1370-1375,1392-1400`), so FTS5
   can emit a trigram spanning non-adjacent source characters. VFS preserves
   every byte and has no equivalent.

## What FTS5 independently validates

`sqlite3Fts5ExprPattern` (`fts5_expr.c:364-430`) compiles LIKE/GLOB into a
trigram MATCH exactly on the Cox model VFS adopted: phrases only for literal
runs of ≥3 chars, AND-combined; a pattern with no 3-char run yields no MATCH
expression → full scan — the same planner contract as VFS's
fixed-string → AND-of-trigrams with `GramAny` fallback, with candidates
rechecked against the stored value.

## Secondary residue (zoekt ingestion gates)

Zoekt's `DocChecker` limits, kept here since the evidence file is deleted:
max indexable file size 2 MiB (`SizeMax`, `index/builder.go:325-326`); any
NUL byte ⇒ binary, skip; < 3 bytes ⇒ too-small
(`shard_builder.go:685-697`); `IgnoreSizeMax` allowlist escape hatch. Zoekt
also carries a branch-mask version-membership dedup scheme — a possible
future model if VFS ever indexes multiple versions of one path.
