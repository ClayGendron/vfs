# 128 — one owner for the byte-bounded batcher, and the budgets get referees

- **Status: draft, 2026-08-25.**
- **Born from** the remediation-round landing review
  (`../../../research/2026-08-25-remediation-round-landing-review.md`),
  finding F9 (the split-batch byte budget can be deleted or voided
  with the suite green) and design question Q1 (three spellings of
  the byte-bounded singleton-exempt batcher), plus the unverified
  lead that `_POSTING_BATCH_BYTES` / `_EXTRACT_BATCH_BYTES` may
  share F9's gap. Both ruled taken-up in the 2026-08-25 decision
  pass.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** consolidation plus pins in the database backend. Batch
  boundaries never change any splitter, builder, or grep output —
  the consolidation is behavior-preserving and the pins referee that
  the budgets *exist*, not new behavior.
- **Depends on:** spec 120 (whose `_SPLIT_BATCH_BYTES` and
  sub-batcher this consolidates), grep's `_content_batches` (ADR 049
  territory), `build_epoch`'s extract batching, the `chunked()`
  precedent in `dialects.py` (the shared slicing helper this
  parallels).
- **Relates to:** the no-designed-caps rule — every budget here is a
  residency bound, never a corpus or batch ceiling; spec 129's
  residency-prose scoping (the char-proxy qualifier) describes the
  same batchers this spec consolidates.

## Intent

1. **Three spellings, no owner (Q1).** `indexing._split_batches` is
   a verbatim copy of grep's `_content_batches`; `build_epoch`'s
   inline extract batcher is a third spelling with a *divergent
   flush law* — post-add (bound = budget + one body) where the other
   two flush pre-add (bound = max(budget, one body) via the
   singleton exemption). The divergence is real but bounded: the
   `MAX_INDEXABLE_BYTES` filter caps the overshoot at one ≤2 MiB
   indexable body (~6.25 % of the 32 MiB budget), which is why the
   review filed it as a question, not a defect. Three spellings of
   one idea is exactly the shotgun-surgery risk `chunked()` exists
   to prevent for count-bounded slicing.
2. **The budgets are unrefereed (F9).** Executed: replacing
   `_split_batches` with one whole-set call survives every test
   (only the coverage gate objects, via the then-dead helper — a
   brittle defense inviting deletion of the "dead" code); setting
   `_SPLIT_BATCH_BYTES = 1 << 60` survives the tests *and* the
   100 % coverage gate, because the pin monkeypatches the constant
   and never observes the declared value. Spec 120 §2's byte-bound
   promise has no referee. The posting/extract budgets may share the
   gap — unverified, investigated here.

Laws that bind the slices:

1. **One owner:** a `byte_chunked(items, size_of, budget)` helper
   lands beside `chunked()` in `dialects.py`, owning byte-bounded
   singleton-exempt slicing; grep's `_content_batches`,
   indexing's `_split_batches`, and `build_epoch`'s inline extract
   batcher all consume it (or are deleted into it).
   `postings.py`'s `next_batch` stays — a different shape, as Q1
   recorded.
2. **One flush law:** the spec's first slice rules pre-add vs
   post-add for the extract site and pins that the unification
   changes no output — batch boundaries are invisible in every
   consumer's results (the split-equality pin, the postings
   fixtures, and the existing feed pins are the referees). The
   pre-add law is the presumptive winner (two of three sites, and
   the tighter bound); if the extract site turns out to *need*
   post-add, that is a finding to record, not silently keep.
3. **Budgets are refereed two ways:** existence — a consumption spy
   under a small monkeypatched budget proves the batcher actually
   slices (kills F9's mutation a); declared value — an assert ties
   the constant to its stated identity
   (`_SPLIT_BATCH_BYTES == _EXTRACT_BATCH_BYTES`, the "declared
   twin" spec 120 named) so voiding it fails without any
   monkeypatch (kills F9's mutation b).
4. **No designed caps:** `byte_chunked` bounds *residency per
   batch*; nothing about it may bound corpus size, batch count, or
   file size.

## Shape

- **§1 The owner.** `byte_chunked()` in `dialects.py` beside
  `chunked()`, same doc discipline: the singleton exemption stated,
  the flush law stated, `size_of` as the caller's metering choice
  (chars-as-proxy at the indexing sites, `size_bytes` at grep's —
  the difference is the *caller's* declared proxy, not the
  helper's).
- **§2 The three consumers.** Each site converts; the copies die.
  Behavior-preservation referees per site: the split-batch equality
  pin (indexing), the postings/epoch fixtures (extract), grep's
  batcher rows (content).
- **§3 The referees.** The spy pin and declared-value assert for
  `_SPLIT_BATCH_BYTES`; the same investigation run against
  `_EXTRACT_BATCH_BYTES` and `_POSTING_BATCH_BYTES` — any gap found
  gets the same two-referee treatment, and a clean verdict is
  recorded in the landing note.
- **§4 The ledger rows.** Executed under safe-restore: the
  whole-set reversion (killed by the spy pin) and the voided budget
  (killed by the declared-value assert); a batcher-loses-its-tail
  mutation against the shared helper re-proves P15's intent at the
  new anchor — P15's anchor line is re-derived to name
  `byte_chunked` when the copy it names dies.

## Slices

- **A** — §1 + §2: the owner lands, three consumers convert, the
  flush law ruled and pinned.
- **B** — §3 + §4: the referees and the ledger rows (including the
  P15 anchor re-derivation).

Gates: `scripts/ci.sh 3.13` at 100 % coverage; all four engine legs
(grep's batcher and the reindex pipeline both ride the change).
