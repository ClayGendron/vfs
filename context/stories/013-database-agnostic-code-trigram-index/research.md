# Research — Code-Oriented N-Gram Indexing Across Databases

> Date: 2026-04-24
> Scope: production code-search systems, database-native n-gram/trigram support,
> and a portable design for Grover grep candidate generation.

## Summary

The production pattern is consistent:

1. Build an inverted index from fixed-size character or byte n-grams.
2. Translate literals and regular expressions into a boolean gram query.
3. Use that query to return candidate documents/chunks.
4. Run the exact matcher afterward.

This is how Google Code Search worked, how Zoekt/Sourcegraph search works, how
GitHub's Blackbird describes substring search at scale, and how Elasticsearch's
`wildcard` field accelerates wildcard/regexp queries. PostgreSQL `pg_trgm`
implements the same broad idea inside a database index, but its tokenizer is
word-oriented: non-alphanumeric punctuation is ignored and words are padded.
That is useful for natural-language-ish strings, but it is not the ideal
canonical model for source code.

For Grover, the cross-database story should be a **code gram index**, not an
English word trigram index. The canonical tokenizer should preserve punctuation,
operators, indentation, and path separators.

## Production Code-Search Systems

### Google Code Search / Russ Cox

Russ Cox's "Regular Expression Matching with a Trigram Index" describes Google
Code Search as an inverted trigram index over source documents. Regex queries
are compiled into boolean expressions over required trigrams, those trigrams
select candidate documents, and the full regex runs afterward.

Important lessons:

- Word indexes are insufficient because regex/code matches do not align to word
  boundaries.
- Bigrams are too broad and 4-grams are too sparse; trigrams are the practical
  middle.
- Regex-to-gram extraction must handle alternation and concatenation as boolean
  logic, not just "extract all literals and AND them."
- Patterns with no required trigrams must degrade to a scan/capped fallback.
- The final regex matcher is still required.

Source: https://swtch.com/~rsc/regexp/regexp4.html

### Zoekt / Sourcegraph

Zoekt is explicitly a trigram-based source-code search engine. The active
Sourcegraph-maintained repo says it supports substring and regexp matching over
source code and can search across many repositories. Sourcegraph's own docs say
indexed search uses Zoekt to create trigram indexes of repository default
branches, and Sourcegraph's indexing docs call out skipped files with more than
20,000 unique trigrams.

Important lessons:

- Source code search needs substring and regexp search, not just token search.
- Production systems impose file-size, binary, encoding, and unique-trigram
  limits to control index blowups.
- Indexing and freshness are explicit operational concerns; unindexed fallback
  still exists.
- Ranking may incorporate code-specific signals such as symbols, but candidate
  generation starts with grams.

Sources:

- https://github.com/sourcegraph/zoekt
- https://sourcegraph.com/docs/admin/search
- https://sourcegraph.com/docs/cody/core-concepts/enterprise-architecture
- https://sourcegraph.com/blog/sourcegraph-accepting-zoekt-maintainership

### GitHub Blackbird

GitHub's Blackbird article describes a custom Rust code search engine built
because general text search products did not satisfy code-search needs at
GitHub scale. It uses n-gram inverted indexes for substring search, intersects
posting-list iterators lazily, and stores a compressed content copy for final
verification and rendering.

Important lessons:

- Code search at large scale is a domain-specific search problem.
- Inverted n-gram indexes are used because code queries include substrings,
  punctuation, identifiers, paths, and regex-like shapes.
- Posting-list intersection should be lazy and ordered so the engine does not
  materialize every candidate for top-k style interactions.
- Deduplication and content-addressed storage matter when indexing many repos.

Source: https://github.blog/2023-02-06-the-technology-behind-githubs-new-code-search/

### Elasticsearch Wildcard Field

Elastic's `wildcard` field is built for finding patterns inside arbitrary
strings such as logs and security data. The design uses an n-gram index as an
approximate filter, then verifies candidate values with wildcard/regexp logic.

Important lessons:

- The "approximate index, exact verification" contract is not limited to code
  search.
- Keyword indexes are the wrong data structure for infix search over high
  cardinality values.
- N-gram indexing has write/storage cost and still needs verification.

Sources:

- https://www.elastic.co/blog/find-strings-within-strings-faster-with-the-new-elasticsearch-wildcard-field
- https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-ngram-tokenizer.html

## Database-Native Support

### PostgreSQL `pg_trgm`

`pg_trgm` provides GIN/GiST operator classes for trigram matching and can index
`LIKE`, `ILIKE`, `~`, and `~*`. PostgreSQL extracts trigrams from the query or
regular expression and uses the index to narrow candidate rows.

The mismatch for code is tokenizer behavior: `pg_trgm` ignores non-word
characters and pads words. For example, `foo|bar` is treated as separate
word-like pieces rather than raw grams crossing the `|` operator. That is often
fine for identifiers and prose, but it loses useful punctuation grams for code.

Implication for Grover:

- Keep using `pg_trgm` as the native Postgres adapter because it is already
  fast and deeply integrated with the planner.
- Do not treat `pg_trgm` as the canonical semantics for code grams.
- Add an optional code-gram side index when punctuation-sensitive narrowing is
  worth the storage cost.

Source: https://www.postgresql.org/docs/current/pgtrgm.html

### SQLite FTS5 Trigram Tokenizer

SQLite FTS5 has a built-in trigram tokenizer that supports substring matching.
Its docs explicitly say it treats each contiguous sequence of three characters
as a token. FTS5 trigram tables can also accelerate `LIKE` and `GLOB` where the
pattern has at least one non-wildcard sequence of three or more characters.

Implication for Grover:

- SQLite can be a serious local prototype target for this story.
- `tokenize='trigram case_sensitive 1'` is a native code-search-ish option.
- FTS5 still has edge cases: sub-3-character searches cannot use the trigram
  index, `LIKE` has case-sensitivity constraints, and `ESCAPE` prevents index
  use.

Source: https://sqlite.org/fts5.html

### SQL Server / MSSQL

SQL Server Full-Text Search is word-breaker based. It is excellent for
linguistic/token search and exposes `CONTAINSTABLE`/`FREETEXTTABLE`, but it is
not a raw trigram index. SQL Server 2025 adds `REGEXP_LIKE`, which helps
server-side verification, but it does not provide a native `pg_trgm` equivalent.

Implication for Grover:

- MSSQL should use a materialized side table for code grams.
- Full-Text Search can remain a separate lexical-search path.
- `CONTAINSTABLE` can still be used as an additional prefilter for word-like
  terms, but it should not be the code grep index.

Sources:

- https://learn.microsoft.com/en-us/sql/relational-databases/search/full-text-search
- https://learn.microsoft.com/en-us/sql/relational-databases/search/full-text-index-binaries

### MySQL Ngram Full-Text Parser

MySQL has a built-in ngram full-text parser, mainly motivated by CJK languages
that do not use whitespace word boundaries. It tokenizes into contiguous
`n`-character sequences and is available for InnoDB and MyISAM full-text
indexes. The token size is a server-level configuration.

Limitations for code:

- The parser is attached to MySQL full-text semantics, not grep semantics.
- Stopword behavior can drop tokens containing stopwords.
- Boolean/phrase behavior is not a direct equivalent of raw posting-list
  intersection.

Implication for Grover:

- MySQL native ngram FTS can be an optional adapter.
- A portable side-table adapter is still preferable for exact code-search
  behavior and predictable cross-database semantics.

Source: https://dev.mysql.com/doc/refman/8.0/en/fulltext-search-ngram.html

### ClickHouse N-Gram Bloom Filter

ClickHouse has `ngrambf_v1` data-skipping indexes. These are not row-level
inverted indexes; they are Bloom filters over granules that help ClickHouse skip
blocks. They can help substring-like queries, but they are probabilistic and
block-oriented.

Implication for Grover:

- ClickHouse-style ngram Bloom filters are useful for analytics scans.
- They are not the canonical model for exact candidate row/chunk ids.

Source: https://clickhouse.com/docs/en/optimize/skipping-indexes

## Design Conclusion

The portable Grover primitive should be:

```text
chunk content -> raw code grams -> inverted index -> candidate chunks -> exact Python matcher
```

Do not use natural-language tokenization as the canonical index. It loses
punctuation and operator information that matters in code.

For databases without native raw n-gram indexing, materialize a side table.
For databases with good native support, use the native index behind the same
capability interface.

## Recommended Canonical Tokenizer

Use raw sliding UTF-8 byte trigrams for candidate generation:

- Normalize line endings to `\n` before chunking/indexing.
- Encode content as UTF-8 bytes.
- Emit every 3-byte window, including punctuation, whitespace, path separators,
  operators, and bytes inside non-ASCII code points.
- Deduplicate grams per chunk before writing the inverted index.
- For case-insensitive search, maintain a second folded gram stream or a
  `folded` flag dimension generated from Unicode `casefold()` text.

Why bytes rather than SQL `nchar(3)`:

- SQL Server `nchar(3)` is UTF-16-code-unit based and can split surrogate pairs.
- Collations can rewrite equality behavior unless binary collations are used.
- Byte grams are compact and database-agnostic.
- Code search is mostly byte-oriented in practice, and final Python matching
  protects correctness.

The index should never be the semantic authority. It only needs to be a safe
superset generator.

## Candidate Query Model

The logical query is a boolean expression over grams:

```text
AND(pos, ost, stg, tgr, gre, res)
OR(AND(pos, ost, ...), AND(dat, ata, ...))
ANY
```

Implementation tiers:

1. Fixed string: all byte trigrams from the string, ANDed.
2. Regex with literal runs: required gram sets from guaranteed literals.
3. Regex with alternation: OR of per-branch gram conjunctions when safe.
4. Regex with no required grams: fallback to structural filters and capped scan.

Every result is then verified by the authoritative Python/ripgrep-style matcher.

## Open Risks

- Storage blowup: large chunks can contain many unique byte trigrams.
- Hot grams: whitespace and common punctuation produce huge posting lists.
- Case-insensitive search doubles index size if stored separately.
- Regex-to-gram extraction is easy to make unsound. Conservative extraction is
  mandatory until a real regex AST compiler is built.
- Side-table maintenance must be atomic with chunk writes/deletes.
- Query plans vary widely by database. The same logical index may need
  different physical layouts per backend.
