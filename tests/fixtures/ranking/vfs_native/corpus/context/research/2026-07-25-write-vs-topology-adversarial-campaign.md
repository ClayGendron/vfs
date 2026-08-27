# Write-vs-topology adversarial campaign — findings report

- **Date:** 2026-07-25
- **Provenance:** synthesized output of a 23-agent adversarial test campaign
  (6 Opus attackers, one per race surface; Opus skeptic verification of every
  critical/major finding; run `wf_2932b694-72b`). Repro scripts were written
  to the session scratchpad (ephemeral); every finding cites its script and
  exact command. Two verifier agents died on API errors mid-run — the §4.1
  purge-arm residual repro and the delete-carrier known-race confirmation
  carry attacker evidence without an independent skeptic verdict (the delete
  carrier is cross-confirmed by other surfaces' verifiers).
- **Feeds:** spec 086 (guarded-bump write-vs-topology hardening) — see §7.

---

# Adversarial-Concurrency Campaign Report: Write-vs-Topology Races in the vfs Storage Backend

**Empirical input to spec 086 (guarded-bump hardening of the torn-path-cache race).**
All repro scripts live under the campaign scratch root, hereafter `<SCRATCH>`:
`/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/8b014bcd-77ba-48e7-abbe-b3fd59cf5480/scratchpad`
Every script resets its own table namespace and is re-runnable from the repo root with `uv run python <script> [engine ...]`. Engines: Postgres, MySQL, MSSQL, Oracle (SQLite out of scope per brief). Findings below carry their skeptic verdicts; refuted and downgraded claims are in §5, honestly labeled.

---

## 1. Verdict

The documented torn-path-cache race (open-questions ledger item (a)) is real, deterministic, and worse than the ledger describes. On MySQL, MSSQL, and Oracle, any write that creates or updates under a directory a rival delete/move/restore relocates mid-window commits a row whose cached path contradicts its parent chain — 1/1 seam-staged, and at natural timing without any seam (MySQL up to 30/30 storm rounds). The ledger's per-engine table is wrong in one load-bearing place: **Postgres is NOT safe** — the reverse ordering (rival write commits after delete's descendant-rewrite SELECT but before its reparent) tears on Postgres at 7–9/30 natural-timing rounds, and the sketched guarded bump structurally cannot close that ordering. Beyond the known race, four skeptic-confirmed **new** defects landed: a copy metadata/body tear on all four engines (seam-free reproducible), a Postgres-only permanent content-row leak, false-success reporting from edit/overwrite-write when an ancestor is relocated (a ~500 ms natural window on MySQL at N=2000), and a raw-driver-leaking `vfs.unavailable` misclassification in restore/move address races. Ledger item (b), the residual purge window, got its first executed reproductions (MySQL/Oracle; Postgres and MSSQL are clean). What held: batch atomicity at 1,200 entries, uniqueness invariants (zero duplicate `(parent_id, name)` or duplicate paths anywhere), refusal ladders under contention, winner-take-all sweep semantics, restore/sweep idempotence, zero raw exceptions escaping any verb, and Postgres's 40001-redrive defense **for the forward ordering only**.

---

## 2. New defects confirmed (skeptic-verified; distinct from the documented race as filed)

### 2.1 CRITICAL — Torn path cache reproduces on Postgres via the reverse ordering; the "Postgres safe" ledger claim is false and the guarded-bump sketch does not close this window

- **Engines**: Postgres (9/30 attacker, 7/30 verifier), MySQL (30/30), Oracle (29/30) — delete storm; MySQL/Oracle 20/20 move storm; Postgres 1/8 with a 1,200-entry batch. **Skeptic: CONFIRMED**, mechanism proven deterministically; independently re-confirmed on Postgres by a second verifier (`dataloss` chain, tear at round 4, seed 555).
- **Interleaving** (no seams; two genuine instances): delete takes the serialization point and runs `_descendant_rewrites`' `path LIKE '/d/%'` SELECT; the rival write INSERTs `/d/fN.txt`, bumps `/d` (still at its pre-delete path/version), and **commits first**; delete then reparents `/d` and rewrites only its stale descendant list. No 40001 fires on Postgres because nothing the write updated had been concurrently modified *before* it updated it. Topology's deliberate READ COMMITTED pin (`dialects.py:109-111`) is load-bearing for refusal correctness, so isolation cannot be the fix.
- **Invariant violated**: `row.path == parent.path + '/' + row.name`.
- **Why the fix sketch misses it**: at bump time the parent's committed path is still `/d` — a guard on `(entry_id, path-at-snapshot)` matches. The stale party is the **delete's descendant list**, not the write. No declared seam covers this window (`delete:post-snapshot` fires before the SELECT).
- **Repro**: `uv run python <SCRATCH>/wt_storm/storm.py postgres delete 30 4242` (verifier's DDL-deadlock-free variant: `<SCRATCH>/wt_storm/verify/mine/storm2.py`; deterministic mechanism proof: `<SCRATCH>/wt_storm/verify/mine/mech.py` — 100% torn on postgres/mysql/oracle).

### 2.2 MAJOR — COPY tears an entry's metadata from its body: stale `content_hash`/`size_bytes` (and `lines`/`mime_type`) over the rival's fresh content, on ALL FOUR engines, with no seam required

- **Engines**: postgres, mysql, mssql, oracle — every engine hit; seam-free repro 13/40 rounds across all four. **Skeptic: CONFIRMED** ("tried hard to refute this and could not"); decisive test: zero seams, plain `asyncio.gather`, still tears.
- **Mechanism** (confirmed in source): `_execute_copy` stamps hash/size/lines/mime from `_fetch_subtree`'s snapshot (`topology.py:957-961`), then fetches bodies with a **second, later** SELECT (`topology.py:973-977`) inside a READ COMMITTED topology transaction. A rival overwrite committing between the two reads lands its new body under the old metadata. Postgres's REPEATABLE READ defense does not apply — topology is deliberately pinned READ COMMITTED. The occupant-overwrite arm (`topology.py:932-946`) is exposed identically by inspection.
- **Impact**: silent (`success=True`), `stat` reports size 8 for a 14-byte body, copied tree lies to dedup/integrity/size accounting. Self-heals on the next overwrite; escalates to critical the moment `content_hash` becomes load-bearing for dedup/GC.
- **This is a second, independent instance of the invariant spec 079 fixed in `writes.py` — topology's copy path was never touched.** Not a guarded-bump problem: the fix is one read, not a guard (e.g. `VFSTables.content_joined()`).
- **Repro**: `uv run python <SCRATCH>/wt_move/e3_copy_content_tear.py`; seam-free: `<SCRATCH>/wt_move/verify/v3b_no_seam.py`.

### 2.3 MAJOR — EDIT and overwrite-WRITE report success at an address that no longer exists when a rival relocates an ANCESTOR: the version guard is blind to unversioned descendant path rewrites

- **Engines**: mysql, mssql, oracle (deterministic seam-staged); Postgres redrives and honestly fails `not_found`. **Skeptic: CONFIRMED and STRENGTHENED** — the filing called the natural window "narrow"; the verifier's no-seam probe at N=2000 hit on MySQL at **10 of 14 swept delays (~500 ms window)**, and one edit call returned **2,000 observations all naming paths that did not exist post-commit**. The window scales with rival topology transaction duration — a 10k delete/move makes it seconds wide.
- **Mechanism**: `_apply_rewrites` (`topology.py:779-788`) rewrites descendant paths with **no version bump** ("nothing observable on a descendant changed" — false for the write family, whose entire concurrency detector IS the version). The guarded `UPDATE ... WHERE entry_id=E AND version=1` matches, content lands on the trashed/moved row, and the caller is told `updated /d/f.txt` while stat/read/ls/glob agree `/d/f.txt` is gone. The file-level control (rival touches the file itself) correctly classifies `conflict` — the escape is specifically ancestor relocation.
- **Post-state is fully coherent** (audit clean; content preserved on the same entry_id, restorable) — this is purely a false Result, violating the in-code contract at `writes.py:289`/`writes.py:698` ("the observation must equal a post-commit stat of its path").
- **Repro**: `PYTHONPATH=<SCRATCH>/wt_edit uv run python <SCRATCH>/wt_edit/s1_edit_vs_delete_parent.py parent` (control: `... file`; move/overwrite flavours: `s2_edit_vs_move.py`; natural-scale: `<SCRATCH>/wt_edit/verify/v1_natural_scale.py`).

### 2.4 MAJOR — Orphaned CONTENT rows: rival write vs move-with-occupant purge permanently leaks file bodies on Postgres

- **Engines**: postgres only (mysql 0/6, oracle 0/4, mssql 0/3 under storm). **Skeptic: CONFIRMED**, including an executed reclaim test: after delete + full trash sweeps, an **empty filesystem still holds a file body** — content rows with no entry are unreachable by every verb (all purge paths resolve by path).
- **Mechanism**: `_purge_subtree` issues side-table deletes **before** the entry delete, from one stale id list; the re-collect loop re-drives only the ENTRY select. A rival writer's `_replace_content` (DELETE-then-INSERT) commits a fresh content row the purge's already-issued content DELETE never sees. No FK anywhere in the schema backstops it.
- **Impact**: monotonic unbounded growth under write + move-overwrite workloads, and deleted bodies persisting indefinitely — a retention/confidentiality problem. Distinct from ledger item (b): entry table stays fully consistent; only `content` leaks.
- **Repro**: `uv run python <SCRATCH>/wt_storm/content_orphan.py postgres 6 4 8888`; producer identification: `<SCRATCH>/wt_storm/orphan_body.py`; reclaim proof: `<SCRATCH>/wt_storm/verify/reclaim.py`.

### 2.5 MAJOR — Restore and move losing a destination-address race to an unserialized rival write classify `vfs.unavailable` / `retryable=True` with a raw driver unique-constraint string, instead of the ladder's `vfs.exists`

- **Engines**: all four (postgres/mysql/oracle ~90-95% of raced rounds; mssql mostly lands the honest `exists`, hit `unavailable` in 3/20 and 7/20 runs). **Skeptic: CONFIRMED**, independently re-derived in a fresh namespace; move arm confirmed 10/10 postgres, 10/10 mysql, 9/10 oracle.
- **Mechanism**: `restore_rows` probes the live occupant (`_point_row`, `topology.py:241`) then `_execute_move`'s deliberately unguarded UPDATE claims the destination; a rival write (unserialized against topology) takes the address in between. The IntegrityError is in no profile's retryable set, escapes `with_retry`, and `classify_failure` emits `unavailable`/`retryable=True`/`path=None` with the raw driver message (asyncpg UniqueViolation / MySQL 1062 / ORA-00001 / MSSQL 2627). `writes.py:445/466` already translates the identical exception into `conflict`/`exists` — topology is internally inconsistent with its own backend's translation.
- **Bounds** (verifier corrections): a retry terminates immediately with the honest `vfs.exists` (not an infinite loop); the incremental batch damage is loss of per-target path attribution, not batch atomicity. Post-state coherent every round; fail-and-keep holds.
- **Repro**: `PYTHONPATH=<SCRATCH>/wt_restore uv run python <SCRATCH>/wt_restore/exp5_address_detail.py postgres mysql mssql oracle`; move arm: `exp7_move_same_window.py`; verifier: `<SCRATCH>/wt_restore/verify/v1_restore_move_address_race.py`.

---

## 3. The known torn-path-cache race (ledger item (a)) — confirmations and characterization

### 3.1 Carriers and per-engine results

One root cause, **four confirmed carriers** — the rival topology verb differs, the tear is identical:

| Carrier | Repro | MySQL | MSSQL | Oracle | Postgres (forward ordering) |
|---|---|---|---|---|---|
| delete | `<SCRATCH>/wt_delete/exp2_variants.py`, `exp4_storm.py` | TORN 1/1; 8/12 natural | TORN 1/1 | TORN 1/1 | SAFE (40001 redrive → not_found; 0/12 natural) |
| move | `<SCRATCH>/wt_move/e1_torn_move.py`, `e6_write_under_moving_source.py` | TORN 1/1; 6/6 unseamed | TORN 1/1 | TORN 1/1 | SAFE (0/6 natural) |
| restore | `<SCRATCH>/wt_restore/exp2_torn_aftermath.py` | TORN 1/1 | TORN 1/1 | TORN 1/1 | SAFE |
| create-under-relocated-parent (edit surface) | `<SCRATCH>/wt_edit/s4_parent_bump_torn.py` | TORN 1/1 | TORN 1/1 | TORN 1/1 | SAFE |

Torn variants: new-file child, mkdir child, deep write with `parents=True`, deep-ancestor delete. NOT torn: overwrite of an existing file (rides into trash structurally clean — the winner-take-all family). Two filings understated MSSQL exposure; verifiers confirmed MSSQL tears identically on the aftermath chains.

**The Postgres-safe claim held on every forward-ordering interleaving tested (dozens of staged runs plus 0/12, 0/6, 0/20, 0/25 storms) and is falsified on the reverse ordering — see §2.1.** Spec 086 must treat the guard as engine-uniform and must not treat the redrive as an existing Postgres defense.

### 3.2 Two tear directions — only one is self-healing, and the ledger's named carrier is the benign one

- **Delete carrier** (parent → trash; child keeps the live path): child stays stat/read-able; `restore` of the trashed parent **heals it — by coincidence, not design** (restore returns the parent to exactly the prefix the stale path already names; restore takes no destination, so this is reliable for plain delete→restore). But the **unattended** outcome is the 90-day retention sweep, which orphans the row (verified: `<SCRATCH>/wt_edit/verify/v_delete_flavour_sweep.py`).
- **Restore/move carrier** (parent live; child keeps a stale/trash prefix — the **inverted tear**): the ghost is unreachable and unlistable from both sides, and **name-squats its apparent address**. Skeptic-verified escalation (raised to critical): because arbitration matches by `(parent_id, name)` without checking the matched row's path, a later **purely sequential, lawful** `write /d/late.txt` reports `created` while landing the caller's bytes in the ghost at its stale path — `read`/`stat`/`delete` of `/d/late.txt` then all return `not_found`. Silent data loss from non-racing traffic. Reproduced with plain user-space `move` (no `/.vfs` path involved), so this is not restore-specific (`<SCRATCH>/wt_restore/verify/v3_ghost_name_squat.py`, `v4_absorb_into_ghost.py`, `v6_move_carrier_inverted_tear.py`).

### 3.3 Post-state characterization (what the fix design needs)

- **Visibility split**: path-keyed verbs (stat/read/tree/glob) resolve the torn row forever; parent_id-keyed `ls` never shows it (or shows a directory as empty). `ls` renders the **stored path column**, so listing a directory can emit an address outside that directory — both an extra bug and the cheapest detector (select by parent_id, compare stored path to `parent.path + '/' + name`).
- **Adoption and propagation** (skeptic-confirmed, re-labeled known; `<SCRATCH>/wt_delete/exp3_aftermath.py` aftermath B, mysql/oracle/mssql): re-`mkdir /d` mints a new id; a later write at the path **adopts the torn row** (`status=updated` — create-becomes-update) into the entity owned by the *trashed* `/d`; a second `delete /d` then rewrites the torn row's path by LIKE into the **new** trash entry while `parent_id` points at the **old** one — the tear spans two sibling trash entries. Restoring either half cannot reunite them; verified worse: restoring the old entry leaves the caller's last write as a **live row reachable by no verb**, sitting at a trash-prefixed path a later sweep destroys (`<SCRATCH>/wt_delete/verify/v_restore.py` — wait, `<SCRATCH>/wt_move/... `; correct path: `<SCRATCH>/wt_delete/verify/` per the adoption verdict, and `v_restore.py` under `<SCRATCH>/wt_restore/verify/` for the restore probe).
- **Cleanability asymmetry**: cascade delete and purge collect by path-LIKE and **miss** the torn row; emptiness checks are parent_id-keyed (`_has_live_children`, `topology.py:502`), so a directory whose only child is torn is simultaneously "not empty" (`cascade=False` refuses forever) and "empty" (`cascade=True` strands the child live). A **path-addressed delete always reclaims** a torn/orphaned row — "no verb collects it" claims were refuted (§5.4).
- **Sweep escalates torn → orphan** on every carrier (path-prefix purge deletes the parent, leaves the child dangling; no FK on `parent_id`, `models/rows.py:341`, so the engine never objects). Trash names are deterministic in `entry_id` + hour bucket, so re-deleting the same directory in the same hour re-mints the same trash address and the ghost silently rejoins — the audit flips clean with nothing repaired.
- **A false-clean hazard**: "audit clean" and self-healing observations in the benign direction must not soften the fix; the damaging direction has no repair path at all today.

---

## 4. Residual purge window (ledger item (b)) — reproduced

First executed reproductions of the documented-but-never-reproduced window, in three shapes:

1. **Purge arm** (`<SCRATCH>/wt_sweep/02_residual_window.py`): rival write SPAWNED (not awaited) during the last firing collection pass; its uncommitted INSERT is invisible to the final re-collection on **every isolation level**; it commits after the purge with a silently-zero-row parent bump. MySQL and Oracle: deterministic 3/3, plus raw-timing (no seams) MySQL 1/25 and Oracle 2/20 rounds. Postgres and MSSQL are **safe** (rival classifies `not_found`). Orphan is stat/read/tree/glob-visible, ls-invisible, and a plain delete recovers it. *(Attacker evidence only — this filing carries no independent skeptic verdict; its two siblings below were verified and confirm the same mechanism.)*
2. **Retention arm** (`<SCRATCH>/wt_sweep/04_retention_arm.py write`): same window through the 90-day sweep, leaving a ghost under a purged hour bucket that later retention sweeps silently skip (parent_id enumeration). **Skeptic: CONFIRMED but DOWNGRADED** — "never reclaimable" was refuted: `tree` sees it, `delete` of its path succeeds and rehomes it into a live bucket, restoring normal retention. Reachability is narrow (requires a client writing into an already-expired bucket). MySQL/Oracle exposed; Postgres/MSSQL clean.
3. **Move-with-overwrite generalization** (`<SCRATCH>/wt_move/e2_dest_purge_orphan.py`): the destination occupant is hard-deleted by `_purge_subtree`, then the frozen rival write INSERTs a child with the purged `parent_id` — a **self-perpetuating dangling orphan** (later writes to the path succeed without rewiring it; it survives a full trash round trip; only an explicit `move` of that exact path repairs it). **Skeptic: CONFIRMED, major** — and notes the true mechanism is flavor (a) with the parent **destroyed** rather than relocated: spec 086 should treat relocation and destruction as one failure mode. MySQL/MSSQL/Oracle exposed; Postgres clean (redrive lands the child correctly under the new row).

Key structural facts: a guard **inside the topology transaction cannot close this** (the rival is uncommitted and invisible by definition); the fix must be write-side (revalidate/lock the resolved parent before apply) or an FK. The write path treats a 0-row parent bump as success — that is the enabling defect.

---

## 5. Refuted, downgraded, and unverified claims

### 5.1 REFUTED as standalone: "Sweep turns a torn child into a permanent orphan that ordinary sweep cannot reclaim"
Skeptic verdict: **not a new defect** (downgraded to an informational note on item (a)). The headline "sweep cannot reclaim" was a **harness-ordering artifact** — the script ran `delete` before `sweep` on the same path, so the sweep's `not_found` was correct; a direct sweep of the orphan succeeds on mysql, oracle, AND mssql. The "post-sweep observable disagreement" was byte-identical **before** the sweep — it is the known tear's visibility, not a sweep consequence. Salvaged facts for 086: restore heals the tear **until the bucket is purged** (the trash retention window is the repair deadline), and the purge predicate is path-only.

### 5.2 REJECTED as a separate finding: "Falsely-acknowledged edit silently destroyed by sweep — acknowledged-write loss (critical)"
Skeptic verdict: **no incremental severity over the false-success finding (§2.3)**. Three executed refutations: (i) the edit is durable — pre-sweep it sits in trash, readable, and `restore` returns it to its original address; (ii) the identical "loss" post-state is produced by a **fully serial, uncontested** edit→delete→sweep on all four engines including Postgres — i.e., it is the designed semantics of delete + purge; (iii) the repro used the explicit purge arm, not the retention path the narrative leaned on. Surviving substance: the stale-address observation, already filed as §2.3, rated major.

### 5.3 DOWNGRADED: retention-arm "unreclaimable trash ghost" — see §4.2. Also: the storm "dataloss" filing's "critical, new" framing — skeptic re-labeled it known (post-state characterization of item (a); the sweep destroys **no user bytes**), while extracting the genuinely new fact: the **Postgres reproduction** (folded into §2.1).

### 5.4 Overstatements corrected inside otherwise-confirmed findings
- "PERMANENT ORPHAN that no verb collects" — false: path-addressed `delete` reclaims it on every exposed engine. Accurate narrower claim: the purge that *owned* the subtree reports success and misses it, and nothing automatic ever collects it.
- "Moving the parent again would not heal it" — false as written: after a delete→restore heal, later moves stay coherent; also `restore` has no destination parameter, so "restore elsewhere" is unreachable.
- "Retrying can never succeed" (§2.5) — a retry terminates immediately with the honest `vfs.exists`; the defect is the dishonest `retryable=True`, not a livelock.

### 5.5 UNVERIFIED (no skeptic pass — leads, not evidence)
- **MSSQL cold first-touch inside a topology window fails "Attempt to use a closed connection"** (2/2; warm control clean; other engines clean). `<SCRATCH>/wt_delete/exp5_firsttouch_stall.py`. Also caused a hard hang that blocked MSSQL legs of exp2 S5/S6.
- **MSSQL cold first touch blocks indefinitely (observed 237 s) behind any in-flight topology transaction** — consistent with `_serialize`'s documented meta X-lock, filed as a production startup-latency question. `<SCRATCH>/wt_sweep/05_mssql_blocking.py`.
- **Winner-take-all observation gap** (question): a successful overwrite whose effect rode into trash reports `updated /d/f.txt` with no `trash_path`, and an immediate stat fails. Structurally clean; pinned semantics; observation contract question. `<SCRATCH>/wt_delete/exp2_variants.py` S3.
- **Postgres path-index arbitration misclassification** (minor): a create losing arbitration on the unique `path` index (only reachable via these races) escapes ON CONFLICT (declared on `(parent_id, name)` only) as `vfs.unavailable` + raw asyncpg text; other engines classify `conflict`. Independently observed once by the §4.3 verifier — one observation, unisolated. `<SCRATCH>/wt_move/e2_dest_purge_orphan.py postgres`.
- **Cross-engine error-kind divergence** (question): the same interleaving yields `conflict` on three engines and `not_found`/`invalid` on Postgres (the redrive honestly reports what a fresh attempt found — including `invalid: old_string not found`, a semantic-looking failure that is really a lost race). Post-state identical everywhere. `<SCRATCH>/wt_edit/s3_restore_and_loss.py b`.

---

## 6. Clean surfaces (attacked and held)

- **Direction A of the delete race**: a rival write staged at `delete:post-snapshot` is swept into the trash rewrite (live `_descendant_rewrites` reads post-rival); restore reunites. Clean on tested engines.
- **Refusal ladders under contention**: `cascade=False` on a directory being filled refuses `not_empty` (single and batch, batch fails whole); move onto an occupied destination refuses `exists`/`wrong_kind`/`not_empty` with rival data intact — all four engines, zero duplicates.
- **Guarded material update composes with subtree rewrites**: rival overwrite inside a moving source, both orderings, all four engines — content preserved at the new path, version monotone.
- **Copy destination-child race**: 0/24 anomalies ×4 engines (rival blocks on the uncommitted unique key, classifies honestly). Noted gap: copy's child inserts carry no arbitration, so the reverse ordering would raise an unhandled IntegrityError — never achieved (single-SELECT-wide gap).
- **Restore**: same-address create race resolves to exactly one owner both orders; double restore 15/15 exactly-one-winner ×4 engines; restore vs parent-delete is honest, fail-and-keep; restore's own purge window 12/12 clean.
- **Sweep**: sweep-vs-sweep idempotent with one winner (postgres/mysql); retention vs restore and vs fresh-bucket delete coherent ×4; quiet purge fires `purge:post-collect` exactly once ×4; mid-purge awaited rival swept winner-take-all (pinned item (c) re-confirmed ×4).
- **Edit controls**: file-level rivals classify `conflict` correctly ×3 (+PG redrive); restore-with-overwrite purging the edit target mid-flight leaves no orphan content (`_apply` ordering returns before `_replace_content`); sweep mid-edit clean.
- **Storm-scale invariants**: 1,200-entry batch atomicity 16/16 (all-or-nothing under chunking); zero duplicate `(parent_id,name)` and zero duplicate paths across every campaign; zero raw exceptions escaped any verb; zero false write successes/failures in ~4,000 checked Results; content-hash audits clean everywhere except the copy tear (§2.2).
- **Postgres forward-ordering safety**: upheld on every seam-staged interleaving across all six surfaces.

**Not reached** (honesty items): MSSQL storm campaigns (harness never completed a round — MSSQL's exposure to §2.1's reverse ordering is untested); mssql legs of some aftermath probes; 10k-batch topology races; edges/versions/chunks audit beyond content; "two live rows sharing one path" (adoption pre-empts it — unproven either way); copy as an edit-rival; multi-pair transfer batches.

---

## 7. Implications for spec 086

### 7.1 Shape of the guarded bump (what the verified evidence demands)
1. **Guard on `(entry_id, path-at-snapshot)`, verified by rowcount, per chunk.** A re-read-and-compare design misses the destroyed-parent case (§4.3 — no row left to re-read). `_bump_parents` (`writes.py:692`) already has both values in hand; sum affected rowcounts per `chunked()` chunk and require equality with the chunk's id count.
2. **Path, not parent_id.** `_apply_rewrites` changes only `path` on descendants — a parent_id guard catches immediate-parent relocation and misses a grandparent's. Budget the bind cost (1,024-byte paths × 10k rows) explicitly; this interacts with the MySQL batch-UPDATE story (spec 080).
3. **Cover `_update_materials`, not just `_bump_parents`.** The edit/overwrite flavor (§2.3) misses on the *target's own* row — its version stood still while its path moved. Both VALUES-join and per-row arms.
4. **A guard miss must abort the whole batch.** By bump time the torn creates are already inserted in the same transaction; "skip and continue" commits the tear. Confirm the session is not committed on the `late`-error branch of `_finish`.
5. **Engine-uniform, including Postgres** (§2.1 — Postgres is exposed on the reverse ordering), and covering all confirmed carriers: delete, move, restore, and the retention/purge destruction case (relocation and destruction are one failure mode).
6. **Do not bump descendant versions** — the path predicate detects without flooding the dirty overlay; the no-bump policy can stand.

### 7.2 What the guarded bump does NOT close (each needs its own decision)
- **The reverse ordering (§2.1)** — the delete side holds the stale data. Candidates: re-run `_descendant_rewrites` after `_reparent_to_trash`; `SELECT ... FOR UPDATE` on the subtree before the descendant SELECT; key rewrites off the parent_id closure instead of path-LIKE; or a parent "topology generation" the write revalidates at commit.
- **The residual purge window (§4)** — uncommitted rivals are invisible to any purge-side re-read. Write-side parent revalidation/locking, or an FK.
- **The copy tear (§2.2)** — single-read fix (bodies joined into `_fetch_subtree` via `content_joined()`, chunked and memory-budgeted) or recompute hash from the fetched body; fix the occupant-overwrite arm too; state the invariant globally ("hash/size/lines describe the content row stored with the entry") and audit every writer of those columns.
- **Content-row orphans (§2.4)** — delete entry rows first per chunk (then side tables from the same chunk), or a final side-table pass over the union of collected ids; plus a one-time reconciliation for already-leaked rows.
- **The classification channel (§2.5)** — catch IntegrityError around `_execute_move`'s UPDATE, re-probe under a SAVEPOINT (the `writes.py` `begin_nested` pattern), and emit the ladder's own `exists`/`conflict` **with target attribution**; applies to restore, move, and copy alike. Same treatment for the Postgres path-index escape (§5.5).

### 7.3 The path-keyed vs parent_id-keyed split — pick one definition of "subtree"
Path-only: `_fetch_committed` (`writes.py:101/224` — doesn't even select `parent_id`), `_descendant_rewrites` (`topology.py:774`), `_rewrite_descendants` (`:791`), `_purge_subtree` (`:508-532`), tree/glob. Parent_id-only: `_has_live_children` (`:502`), `ls`. This split is what turns one torn row into propagating damage (adoption, create-becomes-update, cascade/emptiness contradiction, purge blindness). Cheap defense-in-depth worth landing even if the bump guard slips: (a) write arbitration asserts the matched row's stored path equals the requested path → retryable `conflict` (this alone blocks the §3.2 silent data loss); (b) `_descendant_rewrites`/`_purge_subtree` containment or id-closure collection — the id-closure purge also self-heals legacy torn rows and closes item (b)'s prefix blindness by construction.

### 7.4 Detection and repair
Nothing reports incoherence today — every verb in every torn scenario returned plausible successes. Decide whether 086 owns: a repair scan (must recompute path from the parent_id chain — `deleted_at` cannot identify stranded-live rows; descendants of trashed dirs keep it NULL); the **repair deadline** (restore heals a tear only while the trashed parent survives — the trash retention window bounds any repair sweep); an orphan probe surfaced as a sweep warning; and a verify/fsck hash-vs-body check over the content join (would have caught §2.2). The `ls` stored-path rendering doubles as a one-query detector. Also decide the FK question explicitly: `parent_id` and every side table carry **zero referential integrity** (`models/rows.py:341`) — an FK is the only engine-level backstop for both orphan classes, at a real cost to insert ordering and bulk load.

### 7.5 Missing seams and regression-test shape
No seam exists for: delete's descendant-SELECT → reparent gap (the §2.1 window — the actual tearing window on Postgres); `_purge_subtree`'s side-table-deletes → entry-delete gap (§2.4); restore's resolve → `_execute_move` gap (§2.5 — a `restore:post-resolve` seam would make it a one-shot repro). Regression tests must include **two-instance natural-timing races at N in the low thousands**, not seam-only stages — the §2.3 window is ~500 ms wide on MySQL at N=2000 and seam-free copy tears hit 13/40.

### 7.6 Conformance pins
- A write/edit never reports `success=True` for an effect whose address the post-commit parent chain contradicts (`writes.py:289/:698` is the citable in-code contract). Assert the **exposed-engine legs explicitly** — Postgres passes most of these either way and would mask regressions.
- Both tear directions, all four carriers, and all three transfer callers (move/copy/restore) of `_execute_move`.
- The address-race error is a non-retryable, path-attributed `exists`/`conflict` on every engine; no raw driver text on the public Result surface.
- Decide and pin the cross-engine classification divergence (§5.5): either document the Postgres redrive's `not_found`/`invalid` as legitimate re-execution reporting, or normalize to `conflict`.
- Winner-take-all observations: decide whether a success whose effect rode into trash carries `trash_path` (§5.5 question).