# 095 — Reindex integrity: flag algebra, epoch safety, engine parity

- **Status: implemented and committed 2026-08-13 (`4de5878`)** — born from the
  review campaign memo
  (`research/2026-08-13-glob-grep-indexing-review-campaign.md`),
  which carries the executed repro for every defect below. Both owner
  forks resolved by Clay at kickoff (2026-08-13): fork 1 → demote on
  coverage exit, landed at the delete claim; fork 2 → no designed
  ceiling (see the CLAUDE.md never-cap-scale principle) — details in
  `open-questions.md`. All four slices landed same day: suite green
  at 100% coverage, ruff/ty zero, and **all four Docker legs green
  with the §9 reindex rows live** (Postgres/MySQL 195, MSSQL 197,
  Oracle 194 passed — pass counts moved on every leg). Both §5 guard
  mutants killed by hand: the publish-flip guard against the sqlite
  facade pin, the chunk-flip guard against the live-MSSQL pin. §7's
  round-trip pin ran on the live MySQL leg. Notes vs the drafted
  shape: §3 additionally mints epochs past every *built* number
  (crash-orphaned builds self-heal); §6's knob already existed —
  landed as declaration (constant comment + ADR 033 amendment).
- **Date:** 2026-08-13
- **Owner:** Clay Gendron
- **Kind:** correctness hardening of the reindex verb and the
  `chunked`/`encoded` flag algebra + real-engine conformance coverage
  for the index tier + one declared index-format knob (decision 5 of
  the memo's decision pass).
- **Depends on:** ADR 033 (flag-partitioned overlay, epoch lifecycle,
  the D1 rule that a search verb may never silently lose a match),
  ADR 029 (error-message hygiene), spec 093 (the landed machinery this
  spec repairs).
- **Relates to:** spec 097 (grep-side epoch consistency — the reader
  half of the same race surface); the open-questions entry
  "MySQL-family batch UPDATEs are per-row driver round trips" (§7
  closes its reindex instance).

## Intent

The review campaign found that every critical defect in the landed
glob/grep/indexing arc lives in the flag-partitioned index lifecycle:
the flag algebra has a state (`encoded=True`, no grams in the current
epoch) that makes an entry permanently invisible to both tiers; the
reindex verb is outright broken on MSSQL after its first epoch; and a
rival-reindex window destroys a published epoch's postings. The
structural enabler is that no test anywhere runs `reindex()` against a
real engine — the four-legs-green claim never touched the index tier.

One sentence: **make the flag algebra total (no reachable state hides
a live entry from both tiers), make every reindex statement legal and
correctly classified on all four engines, make epoch publish/reclaim
safe under rivals, declare index-format identity as one hand-bumped
knob, and pin all of it with conformance rows that actually reindex on
real engines.**

## Shape

### 1. The flag algebra closes — no entry is invisible to both tiers

Memo finding 1 (critical): delete → reindex → restore leaves a live
row with `encoded=True` and zero grams in the current epoch; the index
side cannot nominate it, the scan side (`WHERE NOT encoded`) excludes
it, and `_work_pending` (`chunked & ~encoded`) sees no work. Silent
false negative, unbounded on an idle namespace, permanent for
trash-scoped grep — the exact ADR 033 D1 forbidden failure.

The invariant to establish and state in `indexing.py`'s docstring:
**`encoded=True` implies the entry's grams are present in the current
epoch.** Fork resolved (Clay, 2026-08-13): **demote on coverage
exit**, landed at the exit verb itself rather than at publish —
`deleted_at` is stamped only on the trashed *root* (descendants keep
`deleted_at` NULL and stay in builds), so the delete claim that stamps
it also demotes `encoded` in the same guarded statement. The invariant
then holds from the moment coverage is lost: the trashed root serves
scan-side immediately (trash-scoped grep included), restore needs no
repair (`chunked & ~encoded` is already pending work), and the
build→publish restore window is closed because the row was demoted
before it could be restored. Writes already reset both flags, so
delete was the one coverage exit without a demote.

Conformance rows pin delete → reindex → restore → grep serves the
content, and the trash posture: after delete → reindex, trash-scoped
grep serves the trashed root (scan side) and a trashed directory's
descendants (index side, meta-scoped gates).

### 2. `_work_pending` compiles on every engine; syntax errors are not retryable

Memo finding 2 (critical): `select(exists().where(...))` compiles to a
bare `SELECT EXISTS (...)` — invalid T-SQL. The branch is reached only
once an epoch exists, so the first reindex passes and every subsequent
one fails permanently on MSSQL, misclassified as `unavailable`
(retryable). The index freezes at epoch 1.

- Reshape the probe to a form every dialect compiles — the shape
  already proven in the tree is the correlated `.exists()` inside a
  WHERE (`topology.py:615`); `select(literal(1)).where(...).limit(1)`
  with a row-presence check is the alternative. Either is fine; pick
  one and use it for both pending probes.
- Classification: a driver syntax error (`42000`-class) is a permanent
  defect, never `unavailable`. Route it to the loud non-retryable
  channel so a broken statement surfaces as a bug instead of an
  infinite retry invitation.

### 3. Epoch reclaim cannot destroy a rival's published epoch

Memo finding 6 (major): `reclaim_epochs` deletes `epoch != current`
using the reindexer's own stale in-memory epoch, in a separate
transaction after publish. A rival publishing in that window has its
epoch's posting rows destroyed; the pointer names an empty epoch;
covered entries are `encoded=True` so both tiers go blind until the
next reindex.

Fix (either discriminates the repro): reclaim `epoch < current`, or
re-read the live pointer inside the reclaim transaction and reclaim
strictly below *it*. Also close the adjacent verified leak: a
CAS-losing publish must reclaim its own built epoch's rows (today they
linger indefinitely).

### 4. Rival reindexers land on the declared conflict channel

Memo finding 22 (minor): both rivals mint `previous + 1`, so the loser
hits the `(epoch, gram_key)` PK in the build phase and never reaches
the CAS whose declared classification is `conflict`; raw driver text
(constraint names, key values) reaches a public Result, against
ADR 029's hygiene line.

Fix: classify the build-phase PK collision as `conflict` with a clean
message (no driver text), or arbitrate epoch numbers so rivals cannot
collide before the CAS. State stays consistent either way (verified);
this is an error-channel repair, not a data repair.

### 5. The version guards get their missing pins

Memo finding 10 (major): deleting the `entry.c.version` guard from
`publish_epoch` or `chunk_dirty` survives the entire suite, and the
protected behavior is a *permanent* silent loss (a write raced into
the publish window is stamped `encoded=True` over dead grams, then
`_work_pending` no-ops forever).

- The publish pin: a rival `storage.write` installed on the existing
  `reindex:before-publish` seam, asserting the raced entry's flags
  stay `(False, False)` and grep serves the fresh body afterward.
  Home: beside `TestPublishRace`.
- The `chunk_dirty` guard needs a new seam (`reindex:before-chunk` or
  equivalent) and the same shape of pin.

### 6. `INDEX_FORMAT_VERSION` — one hand-bumped knob (decision 5)

The epoch fingerprint hand-transcribes the fold identity that
`code_grams` owns and omits chunk grain and the extraction algorithm;
deriving it was examined and rejected (it still cannot see grain or
algorithm changes). Per the decision pass and prior art (zoekt's
`IndexFormatVersion`/`IndexFeatureVersion`, codesearch's magic
string): declare `INDEX_FORMAT_VERSION` as a hand-bumped integer
constant in the indexing module, fold it into the epoch fingerprint,
and document it — in the module docstring and in ADR 033 via an
annotation — as **the one knob every fold, chunk-grain, or
extraction change must bump**. Spec 096's grain change is the first
consumer: it must bump the knob.

### 7. Flag flips become set-based statements

Memo finding 17 (minor): the per-entry guarded UPDATE degrades to one
round trip per entry on the MySQL family (driver fallback) and MSSQL
(per-row execution server-side) — 10k dirty entries ≈ 20k sequential
round trips inside writer transactions. Fix: set-based guarded
updates — `_values_update` is legal on MSSQL/Postgres; the MySQL
family (no UPDATE…RETURNING) takes a chunked row-constructor `IN`
under the declared budgets. Add a round-trip-shaped scale pin (the
existing bind-count pin cannot see this). This closes the reindex
instance of the standing open-questions entry; the ordinary write
path's `_guarded_by_aggregate` (outside the reviewed range) stays
with that entry.

### 8. Reindex memory posture is documented — never a designed cap

Memo finding 16 (minor, design note): every rebuild holds ≈3.6–4.3×
live corpus bytes resident, paid in full when one entry is dirty; the
dominant term is the whole-corpus posting dict ADR 033 §6 mandates.
Fork resolved (Clay, 2026-08-13): **no ceiling is declared, ever** —
per the CLAUDE.md never-cap-scale principle, vfs does not design
toward intentional scale limits. The in-memory build stays for now;
the module docstring acknowledges the ≈4× resident-memory profile as
a known suboptimality and names gram-range partitioned builds as the
future direction that removes it. No number becomes a supported-corpus
limit. (`session.stream()` trims only 15–32% and is not the
boundedness fix.)

### 9. The index tier runs on real engines in conformance

The structural gap (memo finding 2, second half): no test calls
`reindex()` on a non-sqlite engine; on every server leg the epoch
pointer is `None` and all grep conformance rows silently run
scan-side.

- Engine-marked conformance rows: write → reindex → indexed grep →
  rewrite → reindex → grep, asserting the epoch pointer advanced and
  the indexed tier actually served (via the tier-observable seam the
  battery already uses).
- The §1/§3 rows (restore coverage, reclaim safety) ride the same
  battery.
- The four-legs claim in any future landing message is thereby made
  true for the index tier.

## Verification obligations

- Suite green, coverage 100%, `ruff`/`ty` zero — throughout.
- Every defect's memo repro re-run and passing at the tip: restore
  blindness (facade + Postgres), MSSQL reindex-twice, rival
  publish/reclaim on Postgres, conflict-channel rival pair.
- Four Docker engine legs green **with the new reindex rows live** —
  the pass counts must move on every leg (they cannot stay at the
  pre-095 numbers, which never exercised the tier).
- Round-trip pin for §7 on the MySQL leg.

## Touch points

`src/vfs/storage/backends/database/indexing.py` (§1–§8),
`src/vfs/storage/backends/database/backend.py` (verb classification,
§2/§4), `src/vfs/models/rows.py` (only if fork 1(b) touches build
filters), `tests/storage/database/test_indexing.py`,
`tests/support/storage_contract.py` + `tests/test_storage_conformance.py`
(§9 rows), ADR 033 (annotations: §6 knob, §1 invariant, §3 reclaim
rule).

## Slices (each landing leaves the tree green)

- **A** — §2 + §4: statement legality and error channels (unblocks
  MSSQL; smallest, highest urgency).
- **B** — §1 + §3 + §5: flag-algebra invariant, reclaim safety, the
  guard pins.
- **C** — §9: real-engine conformance rows (proves A and B on all
  four legs).
- **D** — §6 + §7 + §8: the knob, set-based flips, declared memory
  posture.

## Open questions

None — both forks resolved by Clay at the 2026-08-13 kickoff (recorded
above and in `open-questions.md`): §1 demotes at the delete claim;
§8 documents the memory profile without declaring any cap.
