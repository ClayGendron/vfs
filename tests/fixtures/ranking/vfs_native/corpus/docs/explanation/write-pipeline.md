<!--
DIÁTAXIS TYPE: Explanation (understanding-oriented)
THE RULE: Make the design argument. Don't instruct, don't enumerate the API.
Name each design decision, the alternative it rejects, and why. The reader
should leave understanding *why the pipeline is shaped this way*, not how to call it (that's reference/how-to).
SOURCE TO MIGRATE FROM: docs/internals/write_pipeline.md (the design-rationale parts -- leave the signatures, phase table, and worked examples for reference).
-->

# What Happens When Writing a File to VFS



# Why the write pipeline works this way

<!-- One paragraph: a write() is not "INSERT a row." It chunks, indexes,
embeds, versions, and maintains a trigram delta-log — all from one call. State
the thesis the rest of the page defends: the whole thing is one transaction,
indexing happens before the row is written, and unchanged content costs
nothing. -->

## One write, one transaction

<!-- The core invariant. Argue why the entire pipeline (validate → chunk →
index → embed → persist) commits or rolls back as a unit. The alternative:
write the row, then a follow-up maintenance pass builds the index. Name its
failure mode — a window where the row exists but its trigrams/embedding don't,
so grep and vector search disagree with the file listing. Tie to the
"candidates = in the database" contract. -->

## Indexing before persist, not after

<!-- Why trigram extraction, delta staging, and the embedding call all happen
*before* the single persist flush. The alternative: INSERT the row, then a
second UPDATE back-fills the embedding. Failure mode of that ordering: a
provider error leaves a written-but-unembedded row, and there's a second
statement that can fail independently. Pre-persist means a provider failure
aborts cleanly — nothing is in the DB yet. The embedding and the row it
describes land in the same statement. -->

## Change detection is per entry, not per batch

<!-- Why a single write() of 100 files where 3 changed does work for only 3.
content_hash comparison decides each entry's branch independently. The payoff:
re-running an ingestion pipeline over identical content writes nothing — no
version row, no chunk cascade, no trigrams, no embedding call, no updated_at
churn. Argue why "unchanged is free" is a feature, not an optimization detail:
it makes updated_at a trustworthy change signal for downstream consumers. -->

## The trigram delta-log, and why it's append-only

<!-- Why search maintenance is a log of add/delete deltas (latest-action-wins
per (gram_key, entry_id)) rather than rewriting a posting list on every write.
The alternative: maintain the compressed index inline on the write path.
Failure mode: every edit pays full index-rebuild cost, and the write
transaction balloons. Explain how grep stays correct by reading compressed
blocks + unflushed adds − unflushed deletes, so compaction can lag behind the
write. Reference VFSGram / VFSPostingBlock / VFSGramBatch at the conceptual
level only — the schema belongs in reference. -->

### Bulk insert vs. ORM per-row

<!-- The honest tradeoff / known tension. A large file produces tens of
thousands of delta rows; per-row session.add() is the current bottleneck
(~50× slower than Core bulk insert on SQLite). Explain WHY bulk insert is safe
here — atomicity comes from the transaction, not the flush, and nothing reads
the server-assigned seq off the in-memory object. Cite the measurement memo.
Source: context/learnings/2026-05-26-bulk-insert-vs-orm-per-row.md -->

## Failure: what rolls back, what doesn't

<!-- Distinguish the two failure regimes. (1) Within one mount: phase-fatal
errors roll the whole transaction back; write() returns errors, candidates is
empty, "this didn't happen." Per-entry Python-level failures in persist are
tolerated (partial persist) but a DB error poisons the transaction. (2) Across
mounts: no two-phase commit. Per-mount atomicity holds; cross-mount does not.
Argue why vfs deliberately does NOT roll back a committed mount when a sibling
fails (can't without distributed txn; would violate content-before-commit). -->

## When you'd turn the maintenance off

<!-- Brief. The design supports auto_chunk/auto_index=False for bulk ingest,
where amortizing index work across every write is the wrong call and a single
end-of-load maintenance pass wins. This is the one place the reader chooses a
different shape — explain the reasoning, link the how-to for the steps. -->

## See also

<!-- Link the reference page (signatures, phase table, VFSResult contract) and
the how-to (steps to write / to defer indexing). Explanation links out to
those; it does not duplicate them. -->
- Write pipeline reference — *(reference/write-pipeline.md, TBD)*
- [Filesystem internals](filesystem-internals.md)
- [Why VFS is database-backed](why-database-backed.md)
