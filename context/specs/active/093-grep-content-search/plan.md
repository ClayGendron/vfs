# 093 — Plan: grep in four slices, test-first

Implements `spec.md`'s shape. Drafted 2026-08-05, same session as the
shaping review (all forks resolved). Working discipline: tests first
(the 091/092 discipline) — each slice opens red against the
not-yet-written surface; every slice lands green (`uv run pytest`,
`ruff`, `ty`, coverage 100%); the four Docker engine legs run at the
contract-changing slices (C and D) via the `db_test` skill.

## Module layout (decisions)

1. **`src/vfs/models/postings.py`** (new) — the pure codec, no
   storage imports: `encode_postings(doc_ids) -> bytes` /
   `decode_postings(blob) -> ndarray` (delta+varint over strictly
   increasing ids, numpy-vectorized decode) and
   `PostingCorruptionError`. The 013 audit's hardening carries over:
   encode bounds ids to the signed-BIGINT range and requires strictly
   increasing input; decode rejects over-wide varints, out-of-range
   ids, non-monotone deltas, and trailing bytes — loud corruption
   errors, never silently-wrong results. numpy becomes a core
   dependency here (`uv add numpy`).
2. **`src/vfs/storage/backends/database/indexing.py`** (new) — the
   write side: chunk the unchunked (`Chunk.split`), gram-encode the
   unencoded, build posting rows under a new epoch, CAS the pointer
   flip (rows-affected checked), flip flags version-guarded, reclaim
   old epochs, apply the ineligibility gates. Called only by the
   `reindex()` admin method on `DatabaseStorage` — beside `close()`,
   not routed, invisible to `capabilities()`.
3. **`src/vfs/storage/backends/database/grep.py`** (new) — the read
   side: the four-step gate, the execution ladder, the overlay
   union, output modes, budgets. Takes a session; never begins or
   commits (`backend.py` owns transactions, per the house rule).
4. **`src/vfs/base.py`** — the glob probe helpers generalize to
   op-agnostic root-probe helpers shared by glob and grep;
   `_grep_dispatches` composes `globs`/`globs_not` per root and
   residuates through the landed `composed_pattern`/`residuals`;
   grep leaves the generic fan-out else-branch, and the dispatch
   tests that used grep as the generic specimen re-anchor on glean.
5. **`src/vfs/results/kinds.py`** — `unindexable_pattern` joins the
   classified vocabulary (exact placement decided against the kinds
   hierarchy when slice C opens); the refusal message names
   `allow_scan=True`.

## Mechanics pinned here (the spec delegated these)

1. **doc identity**: posting `doc_id` = `chunks.id`; candidate chunk
   ids join back to entries through the chunks table and dedupe to
   entries before any content fetch.
2. **Planning vs verifying**: gram planning always folds
   (`build_code_gram_query` folded; `grams_for_fixed_string` for
   `fixed_strings`); verification always compiles the caller's
   original pattern with the conformance-pinned modifier wrapping
   (`fixed_strings` escape → `word_regexp` wrap → case-mode flags,
   smart-case judged on the raw pattern).
3. **`invert_match` bypasses gram planning by construction** — the
   wanted lines are the non-matches, which no occurrence index can
   narrow — and runs the scan side under the runtime budgets
   *without* requiring `allow_scan`. The refusal gate is
   pattern-shaped; the pinned conformance row (default invert
   succeeds) is the contract. Recorded here so nobody later "fixes"
   this into a refusal without a decision.
4. **One scan executor** serves three callers: the permanent
   `NOT encoded` overlay union on the index side, the `allow_scan`
   opt-out, and `invert_match`.
5. **Structural narrowing is side-independent**: the globs
   LIKE-superset fan, the ext prefilter, liveness, and the meta
   exclusion apply before content fetch on both sides; the
   authoritative Python gates (compiled glob filters with
   name-vs-path dispatch; path-derived ext) run on every candidate.
6. **Budgets** are declared module constants in `grep.py`
   (candidate ~10,000; posting-bytes a few MiB; wall-time deadline
   checked between ladder stages — the spike's numbers); a tripped
   budget adds the truncation warning record whose message names the
   refine moves.
7. **Ineligibility gates** are declared constants in `indexing.py`
   (2 MiB body cap, NUL byte, sub-gram-size, 20,000 distinct grams);
   an ineligible chunk never sets `encoded` and is served by the
   scan side forever — the gates bound index bloat, never coverage.
8. **MySQL**: the postings blob declares `mysql.LONGBLOB` via
   `with_variant` (the 64 KB plain-BLOB silent-truncation cliff).
9. **Traits**: `grep_tier="indexed"`, `grep_staleness="overlay"`;
   the protocol `Literal` vocabulary updates in slice C.

## Slice B design (pinned at implementation, 2026-08-05)

The live entries schema has **no** `chunked`/`encoded` columns — ADR
013 D3 describes them as "already stamped," but they never landed.
Slice B adds them, honoring ADR 013's letter (entry-level Boolean
flags, version-guarded flips, flag-partitioned mutual exclusivity):

1. **Two entry columns**: `chunked` (chunk rows reflect current
   content) and `encoded` (the current epoch's postings cover this
   entry), both `Boolean NOT NULL default False`. Content-writing
   ops (write-overwrite, edit) reset both to False in the same
   statement that writes the body; new rows get the defaults;
   move/copy/restore never touch them (doc ids key on chunk id, so a
   rename invalidates nothing; a copy's new entry starts unindexed
   by default).
2. **Eligibility is an entry property** (zoekt's gates are per-file):
   body ≤ 2 MiB, no NUL byte, ≥ 3 bytes, ≤ 20,000 distinct grams.
   An ineligible entry is marked `chunked=True` with **zero chunk
   rows** and `encoded` stays False forever — scan-side residency is
   derivable (`chunked AND NOT encoded AND NOT EXISTS chunks`), no
   tri-state column needed. The per-chunk `encoded` column is
   reserved for the incremental future ADR 013 envisions; this pass
   drives entry-level flags only.
3. **Grep's partition**: index side `WHERE encoded`; scan side
   `WHERE NOT encoded`. Mutually exclusive by one column.
4. **Reindex phases**: (a) chunk phase — per dirty entry
   (`NOT chunked`): read content at version V, delete stale chunks,
   insert new chunk rows (or none if ineligible), then
   `SET chunked=true WHERE entry_id=:id AND version=:V`
   (rows-affected checked; a raced entry stays dirty); (b) posting
   build — full rebuild from all chunks of chunked-and-eligible
   entries under epoch N+1, bulk-inserted sorted by
   `(epoch, gram_key)` in byte-capped batches (invisible until the
   flip); (c) **one publish transaction**: version-guarded
   `SET encoded=true` for every covered entry **and** the CAS epoch
   pointer flip together — flag flips outside that transaction would
   open a false-negative window where a reader treats an entry as
   index-side before its grams are queryable; (d) old-epoch
   reclamation, separate and slower.
5. **Idempotent-cheap no-op**: no `NOT chunked` rows, no
   chunked-with-chunks-but-unencoded rows, and the current epoch's
   two-part fingerprint matches → return without building.

## Slices

- **A — codec.** Property tests red first: round-trip over random
  strictly-increasing id sets (including empty, singleton, and
  BIGINT-edge values), numpy decode equivalent to a pure-Python
  reference, and the corruption battery (trailing bytes, over-wide
  varint, non-monotone delta, out-of-range id) → loud errors. Then
  `postings.py` to green; numpy lands in core deps.
- **B — reindex.** Direct backend tests: chunking populates chunk
  rows with line ranges and flags; posting rows land under a fresh
  epoch in `(epoch, gram_key)`-sorted, byte-capped batches; the
  pointer flip is CAS-guarded; flag flips are version-guarded (a
  concurrent write's bump survives); the verb is idempotent-cheap
  when nothing is dirty; ineligible content stays unencoded; the
  epoch fingerprint is two-part and a mismatch drops-and-rebuilds.
- **C — the seam and the pipeline.** Protocol flip (grep loses
  `paths`; family docstring true-up; `scope_of` deleted), router
  dispatch + probe adoption with dispatch tests rewritten, then
  `grep.py` test-first against the already-written conformance rows
  run locally on sqlite: gate → ladder → overlay → output modes →
  budgets. `unindexable_pattern` lands with its ingress/kind rows.
- **D — the flip and proof.** `capabilities()` gains grep (via
  `storage_ops(self)` — task 22), traits declared, the memory-backend
  drift pin moves; all 14 conformance rows live on every engine leg;
  the differential battery grep edition (new dated study, `grep -rn`
  / `rg -uu` legs with the allowlist); scale rows (10k roots → one
  call + one probe; posting-build statement budget); epoch-atomicity
  and overlay-exclusivity rows; the rerunnable benchmark harness
  under `research/studies/`; 072/STATUS true-ups.
