# MSSQL Trigram Inverted Index for Regex Prefiltering

## Purpose

This document summarizes the design conversation around building a trigram-based regex prefiltering system in Microsoft SQL Server. The goal is to support fast regex-like searches across a large text corpus, such as 1 million documents, without running the full regex against every document.

In Grover, this is the base physical design for the portable code-gram index. MSSQL should prove it first because it has no native `pg_trgm` equivalent, but the same staged immutable posting-block model is intended to be implemented in PostgreSQL as the punctuation-preserving alternative to native `pg_trgm`.

The core idea is to build an inverted index:

```text
trigram -> compressed list of document IDs containing that trigram
```

Then regex search becomes a two-phase process:

```text
regex pattern
  -> extract required trigrams
  -> use trigram index to find candidate documents
  -> run exact regex only against candidates
```

This is not meant to replace exact regex matching. It is a candidate-generation layer that makes exact verification cheaper.

---

## Key Design Conclusion

The best MSSQL-native design is not a giant relational table forever and not one endlessly mutable row per trigram. The recommended design is:

```text
Document writes -> staging table -> periodic flush job -> immutable compressed posting blocks
```

In other words:

1. When documents are written, extract distinct trigrams and write `(CorpusId, Gram, DocId, Action)` rows into a staging table.
2. Periodically, group staging rows by trigram.
3. Apply staged deletes before staged adds for each trigram.
4. Sort and deduplicate document IDs.
5. Split each trigram's document list into bounded chunks, such as 1,024 or 4,096 doc IDs.
6. Compress each chunk into a `VARBINARY(MAX)` posting block.
7. Store those blocks in a main inverted-index table.
8. Queries fetch posting blocks, decompress them in the app, union blocks within each trigram, apply still-pending staging adds/deletes, intersect across trigrams, then exact-regex verify the candidate documents.

This approximates a production inverted index while keeping SQL Server as the storage system.

---

## Why Not One Relational Row per `(Gram, DocId)` Forever?

A simple prototype table looks like this:

```sql
CREATE TABLE dbo.DocumentTrigrams (
    CorpusId INT NOT NULL,
    Gram     BINARY(3) NOT NULL,
    DocId    BIGINT NOT NULL,

    CONSTRAINT PK_DocumentTrigrams
        PRIMARY KEY CLUSTERED (CorpusId, Gram, DocId)
)
WITH (DATA_COMPRESSION = PAGE);
```

This creates one row per distinct `(CorpusId, Gram, DocId)` pair.

That means if document `123` contains trigram `0x666F6F` (`foo`), the table has:

```text
CorpusId | Gram     | DocId
1        | 0x666F6F | 123
```

If `foo` occurs 20 times inside the same document, it should still have only one row. The index is based on document membership, not occurrence count.

This table is useful for a prototype because SQL Server can answer:

```text
For this corpus and this trigram, give me all matching DocIds.
```

The clustered primary key `(CorpusId, Gram, DocId)` physically/logically sorts data by corpus, then trigram, then document. That makes `WHERE CorpusId = ? AND Gram = ?` efficient.

However, at scale this can become enormous:

```text
1,000,000 documents
x 2,000 distinct trigrams per document
= 2,000,000,000 rows
```

That may be possible, but it is heavy. It creates large indexes, expensive writes, expensive deletes, and large transaction logs. It is a good first version, but not the best long-term representation.

---

## Why Not One Giant Row per Trigram?

A natural inverted-index design is:

```text
Gram | CompressedDocIds
foo  | compressed([7, 19, 103, 991, ...])
bar  | compressed([2, 19, 103, 500, ...])
```

This is closer to how search engines think. But in SQL Server, one giant mutable row per trigram can become painful.

For common trigrams such as:

```text
the
ing
ion
ent
```

that posting list may contain hundreds of thousands or millions of document IDs. If every write appends to the same row, the system must repeatedly:

```text
read huge blob
possibly decompress huge blob
append document IDs
recompress huge blob
rewrite huge blob
log huge update
```

This creates hot rows, high write amplification, large transaction log entries, and difficult delete/update semantics.

The better design is to store the posting list as many immutable blocks.

---

## Segment vs Posting Block

During the conversation, the word `segment` came up. A helpful distinction is:

| Term | Meaning |
|---|---|
| Segment | A larger immutable batch of indexed documents, usually created by a flush or compaction job. |
| Posting block | A compressed chunk of document IDs for one trigram. |

A row like this:

```text
Gram | SegmentId | CompressedDocIds
```

means:

```text
For this trigram, in this indexed batch/block, here is a compressed list of documents that contain it.
```

The user proposed a max of 1,000 documents per trigram block. That is valid. It is best described as a posting-block cap:

```text
Gram | BlockId | CompressedDocIds | DocCount | IsFull
cat  | 1       | [3, 19, 88, ...] | 1000     | 1
cat  | 2       | [2200, 2217, ...] | 713      | 0
```

For a read-heavy system, though, the recommended write model is not to append to open compressed blocks for every document write. Instead:

```text
writes -> staging rows -> periodic flush -> new immutable blocks
```

The block size can still be 1,000, 1,024, 4,096, or another benchmarked value.

---

## Recommended Physical Model

### 1. Documents Table

This stores the actual searchable content and metadata.

```sql
CREATE TABLE dbo.Documents (
    DocId       BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CorpusId    INT NOT NULL,
    Body        NVARCHAR(MAX) NOT NULL,
    CreatedAt   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    UpdatedAt   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    IsDeleted   BIT NOT NULL DEFAULT 0
);
```

In a production system, you would likely store metadata columns here as well, such as document type, owner, path, source system, permissions, timestamps, and tenant/corpus information.

---

### 2. Trigram Staging Table

This is the pending write area.

```sql
CREATE TABLE dbo.TrigramStage (
    StageId   BIGINT IDENTITY(1,1) NOT NULL,
    BatchId   BIGINT NOT NULL,
    CorpusId  INT NOT NULL,
    Gram      BINARY(3) NOT NULL,
    DocId     BIGINT NOT NULL,
    Action    TINYINT NOT NULL, -- 1 = add, 2 = delete
    AppliedAt DATETIME2 NULL,

    CONSTRAINT PK_TrigramStage
        PRIMARY KEY CLUSTERED (BatchId, CorpusId, Gram, DocId, Action),
    CONSTRAINT UQ_TrigramStage_StageId UNIQUE (StageId)
)
WITH (DATA_COMPRESSION = PAGE);
```

Purpose:

```text
cheap bulk writes
simple add/delete deltas
batch-oriented flush
no permanent row-per-posting storage
```

On document ingest, the application extracts distinct trigrams and bulk inserts `Action = add` rows into this table. On document edit, the application computes the old and new trigram sets and inserts only the differences:

```text
old - new -> Action = delete
new - old -> Action = add
```

On document delete, the application recalculates the document's current trigrams before the content disappears and inserts `Action = delete` rows for each current trigram.

If the same document changes multiple times before compaction, staging may hold
more than one action for the same `(CorpusId, Gram, DocId)`. Query and flush code
must fold those rows by `StageId` and use the latest action as the current truth.
That gives the expected behavior for sequences like:

```text
delete gram X
add gram X back
```

The final staged state for `X` is `add`, because the newer row wins.

---

### 3. Batch Metadata Table

This tracks staging batches and flush status.

```sql
CREATE TABLE dbo.TrigramBatches (
    BatchId       BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    CorpusId      INT NOT NULL,
    Status        VARCHAR(30) NOT NULL DEFAULT 'Open',
    CreatedAt     DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    ClosedAt      DATETIME2 NULL,
    FlushedAt     DATETIME2 NULL
);
```

Possible statuses:

```text
Open
Closed
Flushing
Flushed
Failed
```

A common workflow:

```text
current writes go to Open batch
flush job closes current batch
new Open batch is created
closed batch is transformed into posting blocks
```

---

### 4. Main Posting Block Table

This is the actual inverted index.

```sql
CREATE TABLE dbo.TrigramPostingBlocks (
    CorpusId      INT NOT NULL,
    Gram          BINARY(3) NOT NULL,
    BlockId       BIGINT IDENTITY(1,1) NOT NULL,
    BatchId       BIGINT NOT NULL,
    DocCount      INT NOT NULL,
    MinDocId      BIGINT NOT NULL,
    MaxDocId      BIGINT NOT NULL,
    Encoding      TINYINT NOT NULL,
    Postings      VARBINARY(MAX) NOT NULL,
    IsActive      BIT NOT NULL DEFAULT 1,
    CreatedAt     DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_TrigramPostingBlocks
        PRIMARY KEY CLUSTERED (CorpusId, Gram, BlockId)
)
WITH (DATA_COMPRESSION = PAGE);
```

Important fields:

| Column | Purpose |
|---|---|
| `CorpusId` | Keeps separate corpora/tenants isolated. |
| `Gram` | The trigram key as `BINARY(3)`. |
| `BlockId` | Unique posting block identifier. |
| `BatchId` | Source batch used to build the block. |
| `DocCount` | Number of document IDs inside the compressed posting list. |
| `MinDocId`, `MaxDocId` | Useful metadata for diagnostics and possible skipping. |
| `Encoding` | Identifies the compression format. |
| `Postings` | Compressed sorted document ID list. |
| `IsActive` | Allows old blocks to be retired after compaction. |

Example rows:

```text
CorpusId | Gram | BlockId | DocCount | Postings
1        | cat  | 1       | 1024     | compressed([3, 19, 88, ...])
1        | cat  | 2       | 713      | compressed([2200, 2217, ...])
1        | dog  | 3       | 1024     | compressed([...])
```

---

### 5. Trigram Statistics Table

This helps the query planner choose selective trigrams first.

```sql
CREATE TABLE dbo.TrigramStats (
    CorpusId   INT NOT NULL,
    Gram       BINARY(3) NOT NULL,
    DocFreq    BIGINT NOT NULL,
    BlockCount INT NOT NULL,
    UpdatedAt  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_TrigramStats
        PRIMARY KEY CLUSTERED (CorpusId, Gram)
);
```

Purpose:

```text
avoid starting intersections with huge common trigrams
choose rare grams first
estimate candidate sizes
reject too-broad patterns early
```

---

### 6. Delete Deltas Instead of Tombstones

For deletes and updates, avoid mutating old posting blocks immediately. Instead, store gram-specific delete deltas in `TrigramStage`.

Example:

```text
deleted document 123 currently has grams: abc, bcd, cde

stage:
  abc, 123, delete
  bcd, 123, delete
  cde, 123, delete
```

At query time, candidate document IDs from compressed posting blocks are adjusted by latest-action staging rows:

```text
candidate docs = compressed_postings + latest_staged_adds - latest_staged_deletes
```

Later compaction removes deleted document IDs from newly written blocks. Delete staging rows are not discarded merely because they were read by a flush; they can be marked applied only after every active posting block that could contain the deleted `(Gram, DocId)` pair has been rewritten or retired.

---

## Write Path

### Step 1: Insert or Update Document

Application writes the document to `dbo.Documents`.

```sql
INSERT INTO dbo.Documents (CorpusId, Body)
VALUES (@CorpusId, @Body);
```

Capture the assigned `DocId`.

---

### Step 2: Extract Distinct Trigrams in Application Code

Do trigram extraction in application code, not T-SQL.

Important normalization choices:

```text
case-sensitive or case-insensitive?
Unicode character trigrams or UTF-8 byte trigrams?
include whitespace?
normalize punctuation?
normalize accents?
```

For Grover, the canonical index stream is:

```text
normalize line endings to \n
encode as UTF-8
extract byte trigrams
store each trigram as BINARY(3) or the equivalent packed integer
```

Case-insensitive grep should use a separate folded stream generated from
Unicode `casefold()` text, either as a second index or as a `gram_kind` dimension.
A lowercase-only index is acceptable only as a broad prototype prefilter; it is
not the canonical code-gram semantics because it weakens case-sensitive
selectivity.

Example:

```text
hello -> hel, ell, llo
```

Python-like pseudocode:

```python
def extract_trigrams(text: str) -> set[bytes]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    if len(normalized) < 3:
        return set()
    return {normalized[i:i+3] for i in range(len(normalized) - 2)}
```

---

### Step 3: Bulk Insert Stage Rows

For each distinct trigram change:

```text
(BatchId, CorpusId, Gram, DocId, Action)
```

Use bulk loading:

```text
SqlBulkCopy
TVP/table-valued parameter
staging file + BULK INSERT
```

Avoid one-row-at-a-time inserts.

---

### Step 4: Periodic Flush Job

A scheduled job closes a batch and converts staging rows into compressed posting blocks.

High-level algorithm:

```text
1. Close current batch.
2. Create a new open batch for incoming writes.
3. Read closed batch ordered by CorpusId, Gram, DocId, StageId.
4. For each CorpusId + Gram:
      a. Load active compressed postings for that gram if this flush is compacting the gram.
      b. Fold staging rows by latest StageId per DocId.
      c. Apply latest staged deletes.
      d. Apply latest staged adds.
      e. Deduplicate and sort DocIds.
      f. Split into blocks of N doc IDs.
      g. Compress each block.
      h. Insert replacement TrigramPostingBlocks.
      i. Mark old blocks inactive if replacement blocks were written.
5. Update TrigramStats.
6. Mark batch as Flushed.
7. Mark add rows applied once their replacement/add blocks are durable.
8. Mark delete rows applied only after no active block can still contain the deleted posting.
```

Example pseudocode:

```python
BLOCK_SIZE = 4096

for (corpus_id, gram), delta in grouped_latest_stage_rows(batch_id):
    doc_ids = load_active_postings(corpus_id, gram)
    doc_ids.difference_update(delta.deletes)
    doc_ids.update(delta.adds)
    doc_ids = sorted(doc_ids)

    for chunk in chunks(doc_ids, BLOCK_SIZE):
        blob = encode_delta_varint(chunk)

        insert_posting_block(
            corpus_id=corpus_id,
            gram=gram,
            batch_id=batch_id,
            doc_count=len(chunk),
            min_doc_id=chunk[0],
            max_doc_id=chunk[-1],
            encoding=1,
            postings=blob,
        )
```

---

## Compression Format

Start simple.

Recommended v1:

```text
sorted BIGINT doc IDs
-> delta encode
-> varint encode deltas
-> optionally zstd/gzip the result
```

Example:

```text
DocIds:  [100, 105, 120, 121]
Deltas:  [100, 5, 15, 1]
Varints: compact byte representation
```

Why this works:

```text
sorted doc IDs tend to have small gaps
small integers compress well with varints
blocks are independent and easy to decode
```

Possible future encodings:

```text
Roaring bitmaps
SIMD-BP128 / frame-of-reference encoding
EWAH compressed bitmaps
plain sorted int arrays for small blocks
```

The `Encoding` column lets you change formats later.

---

## Query Path

### Step 1: Parse Regex and Extract Required Trigrams

Example:

```regex
foo.*bar
```

Required trigrams:

```text
foo
bar
```

Example:

```regex
[a-z]+Exception
```

Required trigrams from the literal substring `Exception`:

```text
Exc
xce
cep
ept
pti
tio
ion
```

Some regexes do not produce useful trigrams:

```regex
a.*b
.*
[a-z]{2,}
^\d+$
```

For those, options include:

```text
reject as too broad
require metadata filters
fall back to full scan
run only on a smaller filtered corpus
```

---

### Step 2: Choose the Best Trigrams

Use `TrigramStats` to avoid extremely common trigrams.

For example, if a regex yields 20 required trigrams, you may not need all 20 initially. Start with the rarest few:

```text
pick 3-8 rarest required trigrams
intersect those postings
if candidate set is still too large, add more grams
```

This prevents loading huge posting lists unnecessarily.

---

### Step 3: Fetch Posting Blocks

```sql
SELECT
    Gram,
    BlockId,
    DocCount,
    MinDocId,
    MaxDocId,
    Encoding,
    Postings
FROM dbo.TrigramPostingBlocks
WHERE CorpusId = @CorpusId
  AND IsActive = 1
  AND Gram IN (@Gram1, @Gram2, @Gram3);
```

The application then groups rows by `Gram`.

---

### Step 4: Union Blocks Within Each Gram

For each required trigram:

```text
all_docs_for_foo = union(foo block 1, foo block 2, foo block 3, ...)
all_docs_for_bar = union(bar block 1, bar block 2, bar block 3, ...)
```

Because each posting block stores sorted doc IDs, union can be done efficiently.

---

### Step 5: Intersect Across Grams

For required trigrams:

```text
foo AND bar AND baz
```

Compute:

```text
candidate_docs = docs(foo) ∩ docs(bar) ∩ docs(baz)
```

Always intersect starting with the smallest posting list.

---

### Step 6: Apply Pending Deletes and Metadata

Apply still-pending staging deletes:

```text
candidate_docs = candidate_docs - staged_deletes
```

Then apply metadata filters if needed:

```sql
SELECT DocId, Body
FROM dbo.Documents
WHERE CorpusId = @CorpusId
  AND DocId IN (...candidate ids...)
  AND IsDeleted = 0;
```

For very large candidate lists, use a temp table or table-valued parameter rather than a huge `IN (...)` clause.

---

### Step 7: Exact Regex Verification

Finally, run the real regex against the candidate documents.

This is mandatory because trigram filtering is approximate. A document containing `foo` and `bar` might not match `foo.*bar` in the correct order.

Verification can happen:

```text
in application code using a safe regex engine
or in SQL Server if the deployed version supports suitable regex functions
```

For safety and control, application verification is usually preferable. It lets you enforce timeouts, memory limits, and engine selection.

---

## Optional: Querying the Pending Stage

For Grover grep, committed writes must remain visible to the candidate path. Queries should therefore search both `TrigramPostingBlocks` and pending `TrigramStage` rows, synchronously flush relevant pending rows, or scan unflushed documents as a fallback.

For systems where search freshness is allowed to lag, queries can read only `TrigramPostingBlocks`, but that is not the default Grover correctness target.

The fresh query shape is:

```text
candidate docs from main posting blocks
UNION latest staged adds
EXCEPT latest staged deletes
```

This mirrors the idea of a pending list. The tradeoff is that a large staging table can slow reads. A practical compromise:

```text
small flush every 5-15 minutes
large compaction nightly
daily full optimization if needed
```

---

## Compaction

Over time, there may be many small posting blocks. Reads get slower because each query must fetch and decode many blocks.

Compaction merges older blocks into newer blocks and applies staged delete rows:

```text
read active blocks for selected batches/ranges
merge doc IDs per trigram
remove staged-deleted doc IDs
add staged-added doc IDs
write new larger blocks
mark old blocks inactive
mark applied staging rows as applied
```

Important: compaction should usually be copy-on-write.

Do this:

```text
create new compacted blocks
mark old blocks inactive
```

Avoid this:

```text
mutate old compressed blobs in place
```

Copy-on-write keeps queries safer and simplifies failure recovery.

---

## Similarity to PostgreSQL `pg_trgm` / GIN

PostgreSQL's `pg_trgm` extension provides trigram-based text search and supports index operator classes for fast trigram searching. When used with a GIN index, the general shape is an inverted index: keys map to posting lists of rows containing those keys.

GIN also has a write optimization called `fastupdate`, where new entries can go to a pending list before being merged into the main GIN index structure. That is conceptually similar to this MSSQL design's `TrigramStage` table plus periodic flush job.

Important similarity:

```text
Postgres GIN pending list ~= MSSQL TrigramStage
Postgres main GIN structure ~= MSSQL TrigramPostingBlocks
Postgres pending-list cleanup ~= MSSQL flush/compaction job
```

Important difference:

```text
Postgres implements this inside the database engine/index access method.
This design implements the inverted-index mechanics in application code, with SQL Server as durable storage.
```

For regex queries, `pg_trgm` extracts trigrams from patterns when possible. If the pattern does not imply useful trigrams, the index becomes much less selective and may need to scan broadly. The same limitation applies here.

---

## How This Relates to SQL Server Full-Text Search

SQL Server Full-Text Search is an inverted index too, but it is word/token oriented. It is useful for:

```text
word search
phrase search
prefix terms
proximity search
language-aware tokenization
```

It is not a general replacement for arbitrary substring or regex trigram prefiltering.

Recommended approach:

```text
Use SQL Server Full-Text Search for word-like search.
Use trigram posting blocks for substring/regex candidate generation.
Use exact regex verification for correctness.
```

---

## Recommended MVP Plan

### Phase 1: Prove the Search Logic

Build the simpler relational table first:

```sql
CREATE TABLE dbo.DocumentTrigrams (
    CorpusId INT NOT NULL,
    Gram     BINARY(3) NOT NULL,
    DocId    BIGINT NOT NULL,

    CONSTRAINT PK_DocumentTrigrams
        PRIMARY KEY CLUSTERED (CorpusId, Gram, DocId)
)
WITH (DATA_COMPRESSION = PAGE);
```

Use it to validate:

```text
trigram extraction
regex-to-trigram planning
candidate-set sizes
exact verification latency
index size
query patterns
```

### Phase 2: Add Staging + Posting Blocks

Implement:

```text
TrigramStage
TrigramBatches
TrigramPostingBlocks
TrigramStats
```

Move query logic into an application-level interface:

```python
class TrigramIndex:
    def get_postings(self, corpus_id: int, gram: bytes) -> list[int]:
        ...
```

This makes it easier to swap from relational rows to compressed postings.

### Phase 3: Add Compaction and Delete Deltas

Implement:

```text
delete handling
staged delete filtering
copy-on-write compaction
inactive block cleanup
statistics refresh
```

### Phase 4: Optimize Encoding and Block Size

Benchmark:

```text
1,024 doc IDs per block
4,096 doc IDs per block
8,192 doc IDs per block
Roaring bitmap vs delta-varint
query latency vs storage size
common trigram behavior
rare trigram behavior
```

---

## Main Risks

### 1. Regex Patterns With No Useful Trigrams

Some patterns cannot be accelerated well:

```regex
.*
a.*b
^\d+$
[a-z]{2,}
```

Mitigation:

```text
require a literal substring of length >= 3
require metadata filters for broad regexes
cap max candidate set size
fallback to offline/slow path
```

### 2. Too Many Small Blocks

Small blocks are good for writes but can hurt reads.

Mitigation:

```text
periodic compaction
block-count statistics
larger blocks for cold data
smaller blocks for fresh data
```

### 3. Common Trigrams Are Huge

Trigrams like `the`, `ing`, and whitespace-heavy grams may appear everywhere.

Mitigation:

```text
track document frequency
skip extremely common grams when better grams exist
use rarest grams first
limit candidate expansion
```

### 4. Compression Format Becomes a Bottleneck

Poor encoding can waste CPU or storage.

Mitigation:

```text
start simple with delta-varint
keep Encoding column
benchmark with realistic data
consider Roaring bitmaps later
```

### 5. Staging Table Grows Too Large

If staging grows too large, near-real-time queries that include staging become slow.

Mitigation:

```text
flush frequently
partition or batch by BatchId
keep staging short-lived
monitor row count and age
```

---

## Final Recommended Architecture

```text
                   +----------------+
                   |  Documents     |
                   |  Body + metadata|
                   +--------+-------+
                            |
                            | app extracts distinct trigrams
                            v
                   +----------------+
                   | TrigramStage   |
                   | row pending    |
                   | BatchId,Gram,Doc|
                   +--------+-------+
                            |
                            | periodic flush
                            v
              +--------------------------+
              | TrigramPostingBlocks     |
              | Gram -> compressed DocIds|
              | immutable blocks         |
              +------------+-------------+
                           |
                           | query fetches postings
                           v
              +--------------------------+
              | Application Search Layer |
              | regex planner            |
              | posting decompression    |
              | union/intersection       |
              | exact regex verification |
              +--------------------------+
```

The core strategy is:

```text
Use SQL Server for durable storage, metadata, staging, and posting-block persistence.
Use application code for search-engine-specific behavior: regex planning, trigram extraction, compression, posting-list intersection, and exact verification.
```

That gives you a realistic path to build a trigram-powered regex prefilter in MSSQL without forcing SQL Server to be a native trigram index engine.

---

## Source Notes

- PostgreSQL GIN indexes are generalized inverted indexes that map keys to posting lists: https://www.postgresql.org/docs/current/gin.html
- PostgreSQL `pg_trgm` provides trigram functions/operators and GIN/GiST operator classes for trigram search: https://www.postgresql.org/docs/current/pgtrgm.html
- PostgreSQL GIN has pending-list behavior for faster updates and later cleanup/merge: https://www.postgresql.org/docs/current/gin.html and https://www.postgresql.org/docs/16/gin-tips.html
- PostgreSQL `pg_trgm` source shows trigram extraction paths for values, wildcard patterns, and regex-like searches: https://doxygen.postgresql.org/trgm__gin_8c_source.html
- SQL Server Full-Text Search is an inverted index over terms/keywords, not arbitrary character trigrams: https://learn.microsoft.com/en-us/sql/relational-databases/search/full-text-search?view=sql-server-ver17
- SQL Server full-text indexes use internal fragments and merge intermediate indexes as needed: https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-fulltext-index-fragments-transact-sql?view=sql-server-ver17 and https://learn.microsoft.com/en-us/sql/relational-databases/search/limit-search-results-with-rank?view=sql-server-ver17
