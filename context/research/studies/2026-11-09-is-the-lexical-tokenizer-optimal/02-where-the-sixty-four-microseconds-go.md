# A third of the tokenizer's time is the per-term clone and the rest is rules; the builder's sort-and-count costs twice the tokenizer, the chunk scan costs twice the builder, and the tokenizer itself is under a tenth of a 100,000-file rebuild

This is study 02 of [the tokenizer brief](00-brief.md): the profile of `vfs_core::tokenize` in `crates/vfs-core/src/lexical.rs`, the candidate variants that keep its output byte-identical, the builder `LexicalAccumulator` against a borrowed-lookup variant, and the share the lexical build takes of a full rebuild of study 02's 100,000-file SQLite store. It extends [study 03 of the dirty-row budgets memo](../2026-11-09-the-dirty-row-budgets-of-grep-and-glean/03-the-overlay-counts-kernel-spike.md), which measured the tokenizer at 64 µs per 7,167-byte body and guessed at where the time went; the approach (a scratch crate depending on `vfs-core` by path, the 2,000 bodies of study 02's generator, medians of seven passes after a warm-up) is the same, the sources are new. The box was two and a half hours; every step of the brief ran, including the rebuild, which took 75 seconds against the 20 minute stop. Nothing under `src/`, `tests/` or `crates/` was edited and no existing file under `context/` was changed.

Labels: EXECUTED means a command ran here and the claim reports its output; READ means read in a cited file; INFERRED means reasoning from the two.

## Sources

Machine: Apple M1 Pro, 10 cores, 32 GB (34,359,738,368 bytes), macOS Darwin 25.5.0 (EXECUTED: `sysctl -n machdep.cpu.brand_string hw.ncpu hw.memsize`). rustc 1.97.1 (8bab26f4f 2026-07-14), cargo 1.97.1; Python 3.13.11 through uv; vfs at commit b85e3df with its Rust extension `vfs._native` already built. The Rust bench and the SQLite rebuild never ran at the same time; no other heavy process ran on the machine.

Code read for the method: `crates/vfs-core/src/lexical.rs` (`tokenize`, `fold_into`, `emit`, `identifier_parts`, `case_boundary`, the `is_*` checks over `in_ranges`, `LexicalAccumulator::add_doc`, `TermList::push` and `seal`, `finish`, the two drains), `crates/vfs-core/src/lexical_tables.rs` (the header and the shapes: `WORD` 749 ranges, `UPPER` 651, `LOWER` 671, `DIGIT` 83, `ASSIGNED` 707, `CASEFOLD` 1,530 `(u32, &str)` pairs, all `pub static`), `crates/vfs-core/src/lib.rs` (the re-exports), `crates/vfs-core/Cargo.toml` (the `python` feature), `crates/vfs-core/src/python.rs` (the `tokenize` pyfunction and the `LexicalBuilder` pyclass), `src/vfs/storage/backends/database/lexical.py` (`build_lexical_epoch`, `_chunk_batches`, the budgets), `src/vfs/storage/backends/database/indexing.py` (`build_epoch` and its docstring, `_feed_docs`), `src/vfs/models/lexical.py` (`LexicalBuilder` protocol, `lexical_builder`).

Scripts and raw outputs, all under [experiments/](experiments/): [corpora.py](experiments/corpora.py) (writes corpus A and the manifest of corpus B), [tokbench/](experiments/tokbench/) (the scratch crate: [Cargo.toml](experiments/tokbench/Cargo.toml), [src/main.rs](experiments/tokbench/src/main.rs) the driver, [src/variants.rs](experiments/tokbench/src/variants.rs) the stages and candidates, [src/builder_variant.rs](experiments/tokbench/src/builder_variant.rs) the borrowed-lookup accumulator, [src/alloc.rs](experiments/tokbench/src/alloc.rs) the counting allocator), [rebuild.py](experiments/rebuild.py) (the rebuild harness); the outputs [bench_output_ab.txt](experiments/bench_output_ab.txt) and [bench_results_ab.json](experiments/bench_results_ab.json) (corpora A and B), [bench_output_c.txt](experiments/bench_output_c.txt) and [bench_results_c.json](experiments/bench_results_c.json) (corpus C, with corpus B repeated), [rebuild_log.txt](experiments/rebuild_log.txt) and [rebuild_results.json](experiments/rebuild_results.json). The crate was built with `CARGO_TARGET_DIR` in the session scratch directory (`cargo build --release`, an empty `[workspace]` table keeping it out of the repository's workspace); the bodies and the store copy live there too and are not kept.

## 1. The answer in one paragraph

EXECUTED and INFERRED. On this machine the engine's `tokenize` runs at 61 µs per 7,167-byte prose body (117 MB/s, 56 ns a token) and 182 µs per 20,367-byte body of the repository's own code and prose (112 MB/s, 61 ns a token). Cut stage by stage, a third of that is the per-term `String` clone (34%), a fifth is the run scan with its class checks (20 to 23%), the fold is 15 to 17%, the identifier split 14%, the length check 8% and the `Vec<char>` collection 7%. Every candidate the brief named kept byte-identical output on every body of both corpora. Removing the clone through a borrowed `&str` sink is the one large win (41 µs, 0.67×, one allocation per body instead of 1,096); the ASCII run path is a small one (0.96×); the byte-first length check and the ASCII class table change nothing (0.99× to 1.01×); and dropping the `Vec<char>` for `char_indices` is a loss (1.17×), because the collection is a 4.6 µs decode cache that the split and the folds then read three times. The combination with a borrowed sink runs at 34 µs (0.56×, 210 MB/s, 31 ns a token, zero allocations); with a `Vec<String>` result it is 57 µs (0.94×), because the clone comes back. The bigger number is the builder: `LexicalAccumulator::add_doc` costs 181 µs per prose body, three times the tokenizer, in the clone, the sort of every token and the run-length count; a variant that hands terms to an interner as borrowed `&str`, clones only a corpus-new term and bumps a pending slot per term list produces identical drained rows at 74 to 92 µs (0.41× to 0.51×). In the rebuild of the 100,000-file store, `reindex()` took 74.6 s, the lexical build 61.5 s of it (82%), the builder's `add_docs` 17.6 s (24%), of which the tokenizer is about 5.6 s (7.5% of the rebuild) by the bench's ratio; about 36 s of the lexical build is neither the builder nor the inserts and is the keyset scan of 462,963 chunk rows in pages of 256. The tokenizer candidates save 0.5 to 2.7 s of 74.6; the builder variant saves 10 to 11 s; at the reference deployment's 11,000,000 daily visits those are 5 and 21 CPU-minutes a day against a lexical build of about 1.9 CPU-hours a day, two thirds of it the scan.

## 2. The corpora

EXECUTED. Corpus A is study 02's generator at `generate(2000)`: 2,000 bodies, 14,334,854 bytes, 7,167 bytes a body, all ASCII, 2,184,212 tokens by `vfs_core::tokenize` (1,092 a body), 33,294 distinct terms. Corpus B is the repository's own text read from disk: 943 files (239 `.py` under `src/vfs` and `tests/`, 11 `.rs` under `crates/vfs-core/src` without `lexical_tables.rs`, 693 `.md` under `context/research` and `context/specifications/archive`), 19,205,768 bytes, 20,367 bytes a file, 105,803 non-ASCII bytes (0.551%), 19,138,593 chars, 2,821,882 tokens (2,992 a file), 50,347 distinct terms; 107 of the 943 files are all-ASCII, so 836 take the general path somewhere. Corpus C is what the builder actually sees: a uniform sample of 20,000 of the store's 462,963 chunk rows, 29,552,453 bytes, 1,478 bytes a chunk, all ASCII, 4,501,638 tokens (225 a chunk), 35,764 distinct terms. The store's chunks are 1,473 bytes on average (minimum 3, maximum 2,048) and partition the bodies: the gram feed and the lexical feed saw the same 681.75 million chars (EXECUTED, the rebuild timers).

## 3. The profile: where the 64 µs go

EXECUTED. The staged copy rebuilds `tokenize` one stage at a time in [variants.rs](experiments/tokbench/src/variants.rs); its full form is asserted identical to the engine's on every body and runs 5 to 7% slower than the engine's own function (64.7 against 61.2 µs on A), a code-layout difference, so the shares below are of the staged copy's own total. Each row is the median of seven passes; the delta is the stage's cost.

| stage | A µs per body | A share | A ns per token | B µs per body | B share | B ns per token | C µs per chunk | C share |
|---|---|---|---|---|---|---|---|---|
| (i) `Vec<char>` collection | 4.6 | 7% | 4.2 | 12.9 | 7% | 4.3 | 1.0 | 7% |
| (ii) run scan and class checks | 12.9 | 20% | 11.9 | 43.2 | 23% | 14.4 | 2.8 | 21% |
| (iii) identifier split | 8.8 | 14% | 8.0 | 26.3 | 14% | 8.8 | 1.7 | 13% |
| (iv) fold into scratch | 11.0 | 17% | 10.1 | 29.5 | 15% | 9.9 | 2.4 | 18% |
| (v) length check | 5.1 | 8% | 4.7 | 14.4 | 8% | 4.8 | 1.0 | 7% |
| (vi) clone into `Vec<String>` | 22.3 | 34% | 20.4 | 64.2 | 34% | 21.4 | 4.6 | 34% |
| staged full function | 64.7 | 100% | 59.2 | 190.5 | 100% | 63.6 | 13.5 | 100% |
| `vfs_core::tokenize` | 61.2 | | 56.1 | 181.8 | | 60.8 | 12.8 | |

EXECUTED. Allocations: the engine's `tokenize` makes 1,096 allocations and 11 reallocations per A body for 131,869 bytes (one `String` per term plus the `Vec<char>`, the `Vec<String>` growth, the parts vector and the scratch), 2,996 and 14 per B file, 229 and 9 per C chunk; the pipeline through stage (v) makes 3 allocations and 3 to 5 reallocations per body.

INFERRED. The per-token costs are flat across the three corpora (20 to 21 ns for the clone, 12 to 14 for the scan, 8 to 9 for the split, 10 for the fold, 4 to 5 each for the collection and the check), so the tokenizer's time is proportional to tokens and the body size only changes the µs. Corpus B's scan is 2 to 3 ns a token dearer than A's because 836 of its files have some non-ASCII run that reaches the 749-range binary search, and because code has more short runs per byte than prose.

## 4. The candidates

EXECUTED. Every candidate was asserted equal to `vfs_core::tokenize(body)` on every body of A and B before timing (same terms, same order); the builder variants were asserted equal on the drained summary rows and block rows. None failed. The rows are medians of seven passes; allocations are per body for one pass.

| variant | parity | A µs per body | A MB/s | A allocs per body | B µs per body | B MB/s | B allocs per body | C µs per chunk | C allocs per chunk |
|---|---|---|---|---|---|---|---|---|---|
| `vfs_core::tokenize` (the engine) | reference | 61.2 | 117 | 1,096 | 181.8 | 112 | 2,996 | 12.8 | 229 |
| (a) no `Vec<char>`: `char_indices`, byte slices | identical | 71.4 | 100 | 1,095 | 210.6 | 97 | 2,995 | 14.8 | 228 |
| (b) borrowed `&str` sink, counter, no clone | identical | 41.3 | 173 | 1 | 124.6 | 163 | 1 | 8.6 | 1 |
| (c) ASCII run fast path on (a)'s scan, `Vec<String>` out | identical | 58.6 | 122 | 1,095 | 175.0 | 116 | 2,995 | 12.1 | 228 |
| (d) byte-first length check | identical | 61.0 | 117 | 1,096 | 179.5 | 113 | 2,996 | 12.7 | 229 |
| (e) 128-entry ASCII class table | identical | 62.1 | 115 | 1,096 | 184.3 | 110 | 2,996 | 12.9 | 229 |
| (f) a+b+c+d+e, counter sink (the builder's use) | identical | 34.1 | 210 | 0 | 107.0 | 190 | 0 | 7.0 | 0 |
| (f) a+b+c+d+e, `Vec<String>` out (the binding's use) | identical | 57.4 | 125 | 1,095 | 173.5 | 117 | 2,995 | 11.7 | 228 |

EXECUTED. (b) is the profile's clone row realised: 20 µs off A and 57 off B, 1,095 allocations fewer per A body, 37.9 ns a token. (f) with a counter sink is 31 ns a token on A and 36 on B: 0.56× and 0.59× of the engine, zero allocations, because the caller's `parts` and `scratch` buffers are reused across bodies. (f) returning a `Vec<String>` is 0.94×: the clone is 20 ns of every token and the binding's shape keeps it.

INFERRED, from the stage table and (a). The `Vec<char>` is not dead weight. Collecting it costs 4.6 µs per A body (4 ns a token) and after that every stage indexes a `char` in one load; without it the scan decodes UTF-8 once in `char_indices`, the identifier split decodes each run again with one char of lookahead, and the fold decodes each run and each part a third time, so (a) is 10 µs slower than the engine on A and 29 on B. The ASCII run path in (c) recovers that and a little more (58.6 against 61.2) because an all-ASCII run's split, fold (`make_ascii_lowercase` over a copied slice) and check (bytes are chars) work on bytes with no decode; the general path stays for a run with any non-ASCII char, in the same function. (d) and (e) change nothing because the compiler already compiles `is_ascii_alphanumeric` and friends to range compares and `chars().count()` on a short string is a few nanoseconds: the stage table's 5 µs for the length check is the branch, not the counting, since (d) keeps the branch and recovers 0.2 µs.

## 5. The builder

READ. `LexicalAccumulator::add_doc` in `crates/vfs-core/src/lexical.rs` calls `tokenize` for a `Vec<String>`, takes its length as `dl`, `sort_unstable`s the tokens, run-length counts them into `counts: Vec<(String, u32)>`, then for each distinct term does one `HashMap<String, TermList>` lookup (`get_mut` by `&String`) and pushes `(doc_id, tf, dl)` as three varints, sealing at `BLOCK_SIZE` 128. The binding `LexicalBuilder.add_docs` in `crates/vfs-core/src/python.rs` receives `Vec<(i64, PyBackedStr)>` and calls `add_doc` under `py.detach`, so Python passes the chunk strings and the tokenizing happens in Rust: there is no Python-side token list in the index build. `build_lexical_epoch` in `src/vfs/storage/backends/database/lexical.py` feeds `(chunk_id, content)` pairs in byte-bounded batches of 4 MiB of chars through `call_offloaded`, and the `tokenize` pyfunction returning a Python list is used by the glean overlay and the query path, not by the build.

EXECUTED. The variant in [builder_variant.rs](experiments/tokbench/src/builder_variant.rs) keeps `TermList`, the sealing, `finish` and both drains as the engine writes them and replaces the per-document counting: the tokenizer hands each term as a borrowed `&str` to a sink; the sink looks the term up in an interner `HashMap<String, u32>` and clones it only when it is new to the corpus; each `TermList` carries a `pending_doc` and `pending_tf` the sink bumps in place, with a `touched` list of the slots this document reached; once the document's length is known the touched lists get their one `push(doc_id, tf, dl)`. Terms are hashed once each (twice when new); nothing is sorted. It was run with the baseline-shaped feed (b) and the combined feed (f), each with the default SipHash and with an FNV-1a hasher written in the file.

| builder variant | parity | A µs per body | A ns per token | A allocs per body | B µs per body | B allocs per body | C µs per chunk | C allocs per chunk |
|---|---|---|---|---|---|---|---|---|
| `LexicalAccumulator::add_doc` (the engine) | reference | 181.5 | 166 | 1,147 + 105 reallocs | 450.4 | 3,158 | 39.9 | 235 |
| borrowed lookup, (b) feed, SipHash | identical rows | 91.8 | 84 | 68 + 94 reallocs | 217.7 | 216 | 20.2 | 8 |
| borrowed lookup, (b) feed, FNV-1a | identical rows | 81.9 | 75 | 68 + 94 reallocs | 195.8 | 216 | 17.8 | 8 |
| borrowed lookup, (f) feed, SipHash | identical rows | 82.3 | 75 | 68 + 94 reallocs | 199.7 | 216 | 18.0 | 8 |
| borrowed lookup, (f) feed, FNV-1a | identical rows | 73.6 | 67 | 68 + 94 reallocs | 184.9 | 216 | 15.6 | 8 |
| engine `add_doc` + `finish` + block drain | reference | 194.4 | 178 | 1,271 | 477.9 | 3,540 | 40.6 | 251 |

EXECUTED. The engine's `add_doc` is 2.5 to 3.1 times its own tokenizer (181.5 against 61.2 on A, 39.9 against 12.8 on C): the tokenizer is a third of the builder, the sort and count of 1,092 owned strings and the 1,147 allocations are the other two thirds. `finish` and the block drain add only 13 µs per A body on top of `add_doc`, so `add_doc` is 93% of the builder's CPU. The borrowed-lookup counting with the baseline-shaped feed halves `add_doc` (0.51× on A, 0.48× on B, 0.51× on C) with 16 times fewer allocations; the combined feed takes another 10 µs; FNV-1a over SipHash another 9. The allocations that remain (68 per A body, 94 reallocations) are the varint stream growth of the term lists and the touched list, the same in every variant because they are the postings themselves.

INFERRED. The counting change, not the tokenizer, is where the builder's time is: on corpus C the tokenizer candidates save at most 5.8 µs per chunk (12.8 to 7.0) and the counting change saves 20 to 24 (39.9 to 15.6 or 20.2), and the two compose because the borrowed sink is what both need.

## 6. The rebuild and the lexical build's share

READ. `build_epoch` in `src/vfs/storage/backends/database/indexing.py` rebuilds the whole posting set under a fresh epoch when any live entry awaits encoding or the fingerprint drifts ("Anything else rebuilds whole"), then calls `build_lexical_epoch` under the same epoch; the lexical build streams every covered chunk row in ascending id by keyset pages of `_SCAN_PAGE_ROWS` 256 ("never a streaming cursor", for SQL Server over ODBC), batches them to 4 MiB of chars, and writes `lex_docs` per batch, then `lex_stats`, `lex_df` and `lex_postings` in inserts of 20,000 rows. Study 02's harness built its base by `storage.write` then `storage.reindex()` on `DatabaseStorage(url="sqlite+aiosqlite:///...")` after `_host.ensure_ready()`; [rebuild.py](experiments/rebuild.py) does the same on a copy of `base_100000.db` (2,451,095,552 bytes, copied in 1.0 s), rewrites one file (`document(0, salt=1)`) through `write()` so one live entry is not encoded, and times `reindex()` with timers patched over `chunk_dirty`, `build_epoch`, `publish_epoch` and `reclaim_epochs` in `backend.py`'s namespace, `build_lexical_epoch`, `_feed_docs` and the gram `bulk_insert` in `indexing.py`'s, the lexical `bulk_insert` and a timing proxy around the native builder in `lexical.py`'s, plus a statement counter on the engine. The proxy's clocks run on the offload thread around the Rust calls, so they are the Rust boundary.

EXECUTED. Before: 100,000 live files, 462,963 chunk rows, epoch 1, 768,707 `lex_postings` rows, 131,296 `lex_df` terms, 7,480 gram posting rows, nothing awaiting the index. After the one write, 1 entry not encoded. `reindex()` succeeded in 74.62 s wall and 72.94 s of process CPU with 2,475 statements; after it, epoch 2, 768,702 `lex_postings` rows, 131,296 terms, nothing awaiting the index.

| phase | wall s | share of reindex | calls | rows | chars |
|---|---|---|---|---|---|
| `chunk_dirty` (the one dirty file) | 0.05 | 0.1% | 1 | | |
| `build_epoch` | 66.62 | 89.3% | 1 | | |
| of which gram feed `_feed_docs` (fold + extract in Rust) | 2.83 | 3.8% | 21 | 100,000 | 681,754,131 |
| of which gram posting inserts | 0.10 | 0.1% | 186 | | |
| of which `build_lexical_epoch` | 61.45 | 82.4% | 1 | | |
| of which builder `add_docs` (tokenize + count + post, in Rust) | 17.55 | 23.5% | 163 | 462,963 | 681,751,944 |
| of which builder `finish` | 0.45 | 0.6% | 1 | | |
| of which builder drains (`next_df_batch`, `next_batch`) | 0.27 | 0.4% | 48 | 131,296 + 768,702 | |
| of which lexical inserts (`lex_docs`, `lex_df`, `lex_postings`) | 6.77 | 9.1% | 209 | | |
| of which the remainder: the keyset chunk scan and the loop | 36.41 | 48.8% | about 1,809 pages | 462,963 | |
| `publish_epoch` | 0.88 | 1.2% | 1 | | |
| `reclaim_epochs` | 0.97 | 1.3% | 1 | | |
| outside the phases (lease, render, segment, edge and flag passes) | 5.26 | 7.0% | | | |

INFERRED. The remainder of 36.4 s inside `build_lexical_epoch` is what is left after the builder and the inserts; the only other work in the function is `_chunk_batches`, 462,963 rows at 256 a page is about 1,809 round trips, and 2,475 statements were counted in all against 209 lexical inserts, 186 gram inserts and a handful of phase statements, which leaves about 1,800 scan pages at about 20 ms each: a `LIMIT 256` keyset page over the chunk-entry join at 1.5 KB a row. The gram side streamed the same 681 million chars in 2.8 s with a server-side cursor at `yield_per` 256, so the difference is the page-per-round-trip shape, not the bytes. This is the one figure here that the memo should not take further without the experiment named in the last section.

EXECUTED and INFERRED. The builder's measured 17.553 s over 462,963 chunks is 37.9 µs a chunk, against the bench's 39.9 µs per corpus-C chunk, so the bench transfers to the rebuild within 5%. By the bench's ratio on corpus C (tokenizer 12.8 of `add_doc` 39.9, 32%) the tokenizer is about 5.6 s of the rebuild, 7.5% of its wall and 9% of the lexical build.

## 7. The projection

INFERRED from the bench's corpus C figures and the rebuild's 462,963 chunks (4.63 chunks a file at 7,167 bytes a file here; the reference deployment's median file is 4 KB, so its chunk count per file is lower and these per-file figures are upper bounds). The saving per chunk is the bench difference; the rebuild saving is that times 462,963; the daily figure is the per-file saving times the brief's 11,000,000 index visits (the partial passes' million plus the daily rebuild's ten million), with 1.9 CPU-hours a day the lexical build's own total at 614 µs a file (61.45 s over 100,000).

| change | µs saved per chunk | saved of the 74.6 s rebuild | share of rebuild | saved at 11,000,000 visits a day |
|---|---|---|---|---|
| (f) returning `Vec<String>` (the binding unchanged) | 1.1 | 0.5 s | 0.7% | 1 CPU-minute |
| (c) alone, `Vec<String>` out | 0.7 | 0.3 s | 0.4% | 0.6 CPU-minute |
| (f) through a borrowed sink (needs the builder to take `&str`) | 5.8 | 2.7 s | 3.6% | 5 CPU-minutes |
| borrowed-lookup builder, (b) feed, SipHash | 19.7 | 9.1 s | 12.2% | 17 CPU-minutes |
| borrowed-lookup builder, (f) feed, SipHash | 21.9 | 10.1 s | 13.6% | 19 CPU-minutes |
| borrowed-lookup builder, (f) feed, FNV-1a | 24.3 | 11.2 s | 15.1% | 21 CPU-minutes |
| the keyset chunk scan, if it ran at the gram feed's rate | about 72 | about 33 s | about 44% | about 62 CPU-minutes |

INFERRED. Read as a ranking: the per-term clone is a third of the tokenizer and the tokenizer is a third of the builder, so the tokenizer candidates alone move the rebuild by under 4%; the builder's counting is where the Rust time is and the borrowed sink is the change that unlocks it, taking `add_docs` from 17.6 to about 7 s; and the lexical build's largest cost is not in Rust at all. The brief asked whether the tokenizer is optimal: its rules cost 31 to 38 ns a token with no allocation, which is where the same-output floor sits on this machine without a second tokenizer, and the 20 ns a token of clone is a shape the builder chose, not the tokenizer.

## What this study does not settle

The remainder of 36 s in `build_lexical_epoch` is attributed to the keyset chunk scan by subtraction and statement count, not by a timer on `_chunk_batches`; the experiment is the rebuild harness with a timer around the page `execute` and a variant that streams the chunk rows with `yield_per` as the gram scan does, on SQLite and on Postgres, counting pages and reporting the wall as a fact.

Whether the pyo3 `tokenize` pyfunction, which the glean overlay and the query path call for a Python list, should also move to the (f) shape was not costed here beyond the 0.94× `Vec<String>` row; study 03's kernel already measured the overlay with a borrowed sink, and the experiment is that kernel rebuilt on (f) against its own 41 µs.

The borrowed-lookup builder's memory was not measured: it adds a `pending_doc` and `pending_tf` to every term list (16 bytes a term against the docstring's 660) and an interner map beside the lists; the experiment is the bench with peak resident size recorded on corpus B's 50,347 terms and on a corpus the size of the store's 131,296.

The FNV-1a row is a probe of what SipHash costs on short keys, not a proposal; the experiment is the same bench with an adversarial corpus of colliding terms, counting probe lengths.

The corpus B figures stand on 0.55% non-ASCII bytes; the experiment that pins the general path is the bench on a corpus of mostly non-ASCII text (Cyrillic, CJK, mixed-script identifiers) with the parity assertion kept, since every candidate's non-ASCII branch ran here on 836 files but on few runs.

## One line

A third of the tokenizer's 61 µs per 7 KB body is the per-term clone and a borrowed `&str` sink removes it (34 µs, zero allocations, identical output); the builder's sort-and-count is twice the tokenizer again and a borrowed-lookup accumulator halves `add_doc` with identical rows; in the 100,000-file rebuild of 74.6 s the lexical build is 61.5 s, the builder 17.6 s, the tokenizer about 5.6 s, and about 36 s is the keyset scan of 462,963 chunk rows, so the tokenizer candidates save under 4% of the rebuild, the builder change about 15%, and the scan is the figure to measure next.
