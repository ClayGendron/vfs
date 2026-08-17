# codesearch (raw agent findings)

Checkout: ~/Git/Repos/codesearch, HEAD b34f2a0, index format v2 (64-bit).

## Format: trigram → sorted delta-coded docid list, no positions, no counts
- index/read.go:7-14 — layout: "csearch index 2\n", roots, names, posting lists, name index, posting-list index, trailer.
- index/read.go:31-46 — posting list = `trigram [3]` + γ-coded deltas ending in zero delta ("[2,5,1,1,0] encodes 1,6,7,8"). v1 used uvarint deltas; v2 γ-coding (read.go:100-108, index/delta.go).
- index/read.go:52-64 — posting-list index: (trigram, file count, offset) triples, 256-byte aligned for binary search; sparse trigrams omitted (read.go:71-74).
- index/write.go:100-123 — postEntry is packed uint64 `trigram<<40 | fileid`; no offset/line/count field. Set-valued per file (sparse.Set at write.go:44,72,216,245; one entry per distinct (trigram,file) at write.go:286-293) — index can't even count occurrences.
- Rejection rules (write.go:128-134): maxFileLen 1<<30, maxLineLen 2000, maxTextTrigrams 20000, invalid-UTF-8 rejected (write.go:252-258).
- Sizing (read.go:113-124, Linux git v6.9): 147,703,290 B postings of a 157,759,443 B index — ~94% of index is docid postings.

## Planner
- index/regexp.go:14-21 — Query is a conservative superset of the regexp; filter files before "comparatively more expensive regexp machinery".
- regexp.go:22-36 Query{Op, Trigram, Sub} QAll/QNone/QAnd/QOr; regexp.go:333-338 RegexpQuery = analyze → simplify(true) → addExact. Simplification regexp.go:50-230; regexp.go:170-175 "okay to return false negatives" in implies (conservative).

## Evaluation & verification
- read.go:561-615 postingQuery → []int fileids; postingAnd read.go:519-536; postingOr read.go:541-560 + mergeOr read.go:617-638; postReader read.go:405-468. QAll materializes all ids (read.go:568-575).
- cmd/csearch/csearch.go:107-118 query → post []int; name-only prefilter csearch.go:127-140; csearch.go:147-189 opens each candidate, full scan via g.Reader at csearch.go:187.
- regexp/match.go:432-549 Grep.Reader: 1MB buffer, io.ReadFull loop, DFA over whole file to EOF; no seek, no positional hint; only -l short-circuit (csearch.go:149-152) and Limit (match.go:355-377). csweb identical (cmd/csweb/web.go:80,113,147).

## Cox article (swtch.com/~rsc/regexp/regexp4.html, Jan 2012)
- Positions (phrase-search section): "Storing the position information in the index entries makes the index bigger but avoids loading a document from disk unless it is guaranteed to be a match." Alternate = AND query + filter after loading bodies; "phrases built out of common words ... make this approach unattractive."
- Trigram choice: too few 2-grams, too many 4-grams → trigrams.
- Size: "index tends to be around 20% of the size of the files being indexed. For example, indexing the Linux 3.1.3 kernel sources, a total of 420 MB, creates a 77 MB index."
- Precision numbers: Datakit query 2,739 → 3 files (all matches); "hello world" on Linux 3.1.3: 36,972 → 25 files, ~100x faster. Precision-vs-memory knob: ab[cd]e example — "tradeoff between memory usage and precision."
- I/O model: mmap of index + OS page cache; verification cost reported as wall clock only. "The article's cost model silently assumes candidate bodies are cheap to read — page-cache-warm local files."
- Never argues positions are useless for regexp verification; simply never revisits after the phrase paragraph. Stated reasons: index size + simplicity ("new matcher is under 500 lines of code").

## Draft verdict
- codesearch = vfs's current design. Cost accepted: fetch+scan entire body of every candidate (including false positives, and the non-matching remainder of true positives) in exchange for ~20%-of-corpus index and a tiny matcher.
- Why it dominates in vfs but not csearch: csearch's bodies come from the OS page cache; vfs's come via SQL round-trips — the term Cox treats as ~free is vfs's whole bill.
- Planner precision attacks only half: even zero false positives pays full-body transfer per true-positive file. Cox's numbers show precision is already good; remaining cost is bytes-per-true-candidate.
- The lever codesearch declined (positions) is the one vfs needs; even coarse block/line-level positions convert O(candidate size) → O(match neighborhood).
