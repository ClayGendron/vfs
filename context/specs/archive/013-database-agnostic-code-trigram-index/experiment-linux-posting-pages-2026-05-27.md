# Experiment — Linux Trigram Posting Pages on Local Postgres

Date: 2026-05-27

Purpose: use real Linux source data and a localhost Postgres database to inform
Story 013's posting-list storage design, especially whether posting blocks
should be large blobs or page-shaped segments.

## Harness

Script:

```bash
uv run --with asyncpg python scripts/bench_linux_trigram_posting_pages.py
```

Main run:

```bash
uv run --with asyncpg python scripts/bench_linux_trigram_posting_pages.py \
  --max-files 10000 \
  --max-chunks 10000 \
  --payload-targets 512,1024,2048,4096,8192,16384,65536 \
  --staging-rows 100000
```

The script creates a fresh `vfs_linux_trgm_bench` database, extracts folded VFS
byte trigrams from `/Users/claygendron/Git/Repos/linux`, materializes compressed
posting pages in Postgres, measures storage/read timings, measures a real append
batch against an existing base index, and drops the database unless `--keep-db`
is passed.

## Corpus

| Metric | Value |
|---|---:|
| Chunks | 10,000 |
| Indexed files | 7,256 |
| Files scanned | 7,257 |
| Distinct `(gram, doc)` postings | 9,189,305 |
| Distinct grams | 120,437 |
| Binary skips | 1 |
| Decode skips | 0 |
| Large-file skips | 0 |
| Median gram document frequency | 5 |
| Max gram document frequency | 8,265 |

The chunk count is intentionally smaller than the full Linux tree so the
experiment can be rerun quickly. It is large enough to produce hot grams that
cross 2 KB, 4 KB, and 8 KB compressed payload targets.

## Results

### Initial Storage Sweep

```text
payload  blocks     load_s  read_s  table     total     toast     avg_docs  p95_docs  avg_B  p95_B  max_B
----------------------------------------------------------------------------------------------------------------
    512  130,646    2.001   0.026     21 MB     34 MB  8192 bytes      70.3       512     74    512    512
  1,024  124,251    1.678   0.015     20 MB     33 MB  8192 bytes      74.0       528     77    536  1,024
  2,048  121,617    1.598   0.016     19 MB     31 MB    264 kB      75.6       338     79    354  2,048
  4,096  120,694    1.542   0.014     18 MB     31 MB    320 kB      76.1       288     80    304  4,096
  8,192  120,438    1.567   0.016     18 MB     30 MB    384 kB      76.3       277     80    294  8,192
 16,384  120,437    1.568   0.017     18 MB     30 MB    384 kB      76.3       277     80    294  8,264
 65,536  120,437    1.546   0.014     18 MB     30 MB    384 kB      76.3       277     80    294  8,264
```

Read timing fetches and decodes up to four rarest grams for each built-in query
literal. This is a narrow candidate-generation microbenchmark, not a complete
grep benchmark.

Write-path staging measurement from the same run:

```text
100,000 staging rows inserted in 0.924s
```

### Append-Flush Sweep

After extending the harness, the same 10,000-chunk corpus was split into:

| Split | Value |
|---|---:|
| Existing/base chunks | 9,000 |
| Append-batch chunks | 1,000 |
| Append-batch postings | 985,259 |
| Append-batch grams | 40,514 |

Default Postgres `bytea` storage:

```text
payload  blocks     load_s  append_s  append_rows  read_s  table     total     toast     avg_docs  p95_docs  avg_B  p95_B  max_B
----------------------------------------------------------------------------------------------------------------------------------------
    512  130,646    1.906     0.571       40,744   0.023     24 MB     41 MB  8192 bytes      54.8       506     57    512    512
  1,024  124,251    1.962     0.537       40,514   0.015     23 MB     39 MB  8192 bytes      56.7       310     59    320  1,024
  2,048  121,617    1.966     0.523       40,514   0.015     22 MB     38 MB     72 kB      57.5       236     60    247  2,048
  4,096  120,694    2.133     0.567       40,514   0.015     22 MB     38 MB     72 kB      57.8       213     60    225  4,096
  8,192  120,438    2.052     0.425       40,514   0.014     22 MB     38 MB     72 kB      57.9       209     60    222  7,404
 16,384  120,437    1.429     0.418       40,514   0.017     22 MB     38 MB     72 kB      57.9       209     60    222  7,404
 65,536  120,437    1.355     0.411       40,514   0.018     22 MB     38 MB     72 kB      57.9       209     60    222  7,404
```

Staging measurement from the same default-storage run:

```text
100,000 staging rows inserted in 1.044s
```

`append_s` times only the database insert of already-built posting pages. It
does not include Python gram extraction or page construction. That is deliberate:
the storage question is whether immutable page insertion is plausible once the
indexer has a batch of sorted doc IDs.

### Forced Inline Storage

The harness also supports:

```bash
uv run --with asyncpg python scripts/bench_linux_trigram_posting_pages.py \
  --max-files 10000 \
  --max-chunks 10000 \
  --payload-targets 512,1024,2048,4096 \
  --staging-rows 100000 \
  --append-docs 1000 \
  --storage plain
```

`ALTER TABLE posting_pages ALTER COLUMN postings SET STORAGE PLAIN` avoids TOAST
for tested payloads through 4 KB:

```text
payload  blocks     load_s  append_s  append_rows  read_s  table     total     toast     avg_docs  p95_docs  avg_B  p95_B  max_B
----------------------------------------------------------------------------------------------------------------------------------------
    512  130,646    1.941     0.612       40,744   0.024     24 MB     41 MB  8192 bytes      54.8       506     57    512    512
  1,024  124,251    1.866     0.592       40,514   0.016     23 MB     39 MB  8192 bytes      56.7       310     59    320  1,024
  2,048  121,617    1.836     0.572       40,514   0.017     23 MB     39 MB  8192 bytes      57.5       236     60    247  2,048
  4,096  120,694    1.850     0.623       40,514   0.016     23 MB     39 MB  8192 bytes      57.8       213     60    225  4,096
```

The same `PLAIN` run fails at the 8 KB target:

```text
asyncpg.exceptions.ProgramLimitExceededError: row is too big: size 8280, maximum size 8160
```

So forced-inline storage is useful as a guardrail, but the hard payload ceiling
must stay comfortably below 8 KB if `PLAIN` is enabled.

A retained inspection database was then created with:

```bash
uv run --with asyncpg python scripts/bench_linux_trigram_posting_pages.py \
  --max-files 10000 \
  --max-chunks 10000 \
  --payload-targets 1024 \
  --staging-rows 100000 \
  --append-docs 1000 \
  --keep-db
```

Verification:

```text
database: vfs_linux_trgm_bench
layout: 1,024-byte payload target, default bytea storage, base + append pages
posting_pages rows: 161,956
posting_pages doc_count sum: 9,189,305
total relation size: 39 MB
toast relation size: 8192 bytes
```

## Implications

1. **A 64 KB default is not justified for Postgres.** On this real corpus, the
   largest hot gram only needs an 8,264-byte encoded blob. Allowing 64 KB does
   not improve row count over 16 KB for this sample, and it invites much larger
   TOASTed values on bigger corpora.

2. **Postgres starts showing TOAST once payload targets reach ~2 KB.** The 512 B
   and 1 KB layouts keep the TOAST table at its empty baseline. The 2 KB target
   produces measurable TOAST usage. This does not make 2 KB invalid, but it means
   the design should be explicit about whether small amounts of TOAST are
   acceptable.

3. **Page-shaped rows are viable.** Moving from 512 B to 2 KB reduces posting
   rows by about 9,000 rows for this sample, while total storage drops from 34 MB
   to 31 MB. Larger targets produce only minor additional savings.

4. **Append-only immutable-page flush is plausible.** A 1,000-chunk append batch
   with 985,259 postings compiled to about 40.5k posting-page rows and inserted
   in roughly 0.4-0.6s. This supports the staging -> background flush model.
   It does not argue for doing flush inline with user writes; extraction,
   sorting, and compaction still belong off the foreground path.

5. **Forced inline storage is a tradeoff, not an obvious win.** `STORAGE PLAIN`
   eliminates TOAST through 4 KB but did not improve total size or timing in
   this run. It also turns too-large rows into hard failures. That is attractive
   if the design wants strict page-shaped rows, but default storage with a 1 KB
   target already avoids TOAST on this corpus.

6. **The payload target should be backend-specific.** A Postgres-oriented default
   should be much closer to 1-2 KB than 64 KB. SQLite or object-storage-backed
   implementations may choose larger pages.

7. **Rarest-first reads dominate the query story.** The read timings are low for
   these literals because the query path reads selective grams first. Hot grams
   should be late filters or skipped when they add little selectivity.

## Recommended Next Defaults

For the Postgres portable-table implementation:

| Setting | Recommendation |
|---|---:|
| Normal compressed payload target | 1,024 B |
| Larger benchmark candidate | 2,048 B |
| Hard payload ceiling with default storage | 8,192 B |
| Hard payload ceiling with `STORAGE PLAIN` | 4,096 B |
| Row shape name | posting page / posting segment |
| Required metadata | `gram_key`, `min_doc_id`, `max_doc_id`, `doc_count`, `byte_count`, `encoding`, `is_active` |

The current `VFSPostingBlock` model already has most of this shape. The main
schema addition suggested by the experiment is `byte_count`; the main spec
change is to describe the rows as page-shaped segments and to set a
backend-specific compressed byte target instead of implying large generic blobs.

For Postgres, the strongest current recommendation is:

```text
target payload = 1 KB
benchmark 2 KB
do not default to 64 KB
consider STORAGE PLAIN only if the implementation also enforces <= 4 KB payloads
```
