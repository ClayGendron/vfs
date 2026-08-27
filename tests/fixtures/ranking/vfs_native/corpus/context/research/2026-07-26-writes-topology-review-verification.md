# Writes/topology post-086 review — adversarial verification campaign

- **Date:** 2026-07-26
- **Status:** final (append-only; supersede with a newer memo)
- **Owner:** Clay Gendron (agents: three reviewers + three adversarial
  verifiers, orchestrated in-session)
- **Subject:** `src/vfs/storage/backends/database/writes.py` and
  `topology.py` as landed by spec 086 (uncommitted tree on `main` after
  `ce198c3`).
- **Method:** three independent review agents (correctness; precedent
  alignment; shared-concept extraction), then three adversarial
  verifiers instructed to *refute* the combined findings — empirically
  where possible, by writing standalone repro scripts and executing
  them against live Docker engines (Postgres 17, MySQL 8.4, MSSQL
  2022, Oracle 23ai Free; isolated `table_name` per verifier). The
  scripts were session-ephemeral scratchpad artifacts; every confirmed
  repro below is described precisely enough to re-stage, and the
  durable pins land with spec 087's test family.

## 1. Confirmed defects (empirically reproduced)

### 1.1 Delete applies a stale descendant-rewrite list (torn namespace)

Reproduced on Postgres and MySQL. Staging: `/d/sub/keep.txt`
pre-exists; trash chain pre-minted; rival `write(/d/sub/new.txt)`
lands at the `delete:post-collect` seam; victim `delete(/d)`.
Both operations report success; afterward the table holds
`path='/d/sub/new.txt'` whose parent row lives at
`/.vfs/trash/<bucket>/<ulid>-d/sub` — a live-looking address whose
whole parent chain is in trash, and `stat /d/sub/new.txt` succeeds.

Mechanics: `_descendant_rewrites` is collected before the claim; the
reparent guard covers only the delete target's row; the rival's
guarded parent bump touches only its *direct* parent (`/d/sub`), so at
depth ≥ 2 both guards pass and `_apply_rewrites` applies the pre-seam
list, missing the new row. The landed race test stages only a depth-1
child — which bumps the delete target itself and flips the guard —
so the depth-2 case was unpinned. Escalation: the stranded row's path
never matches the trash prefix, so a later sweep purges its parent and
leaves it permanently unreachable.

**The move/restore analogue was refuted**: the identical depth-2
staging against `move` came out clean, because `_execute_move` runs
`_rewrite_descendants`, which *re-collects* descendants after the
guarded root claim. Delete alone applies its pre-claim list — and
move's shape is the proven fix. Residual minor lead (traced, not
executed): the transfer byte-budget check judges the pre-seam subtree,
so a late child whose rewritten path exceeds the budget would be
stored over-budget.

### 1.2 Overwrite-move/restore silently destroys a rival's committed file

Reproduced on Postgres (move and restore arms) and MySQL (move arm).
Staging: `/b` an empty directory occupant, victim
`move /a → /b, overwrite=True`; rival `write(/b/f.txt)` at
`transfer:post-collect` (for restore: `restore:post-resolve`) — both
seams sit after the `_has_live_children` emptiness check and before
`_execute_move`. Observed: rival write success, move success, **no
error anywhere**, and the rival's row and content are gone — not in
trash; `_purge_subtree`'s loop-until-empty design (built to avoid
orphans) re-collects, sees the freshly committed child, and hard
deletes it. Sequentially the ladder refuses `not_empty`; the joint
history is non-linearizable. This is the severest finding: silent
permanent data loss of a success-reported write on `move`'s default
path.

Fix shape validated by trace: destroy the occupant root under a
version guard at the value the emptiness probe read — any child
committed after the check has executed a guarded bump of the occupant,
so the guard misses, raises the stale-snapshot signal, and the redrive
refuses `not_empty` honestly. Machinery identical to
`_reparent_to_trash`.

### 1.3 The absorb arm can land a write's content on a trash row

Reproduced on Oracle and MSSQL; structurally unreachable on Postgres
(the `ON CONFLICT … WHERE path = excluded.path` clobber resolves the
race atomically inside the INSERT) and on MySQL (the REPEATABLE READ
occupant probe returns `None`, so absorb never fires — see 1.4).
Staging on the catch-retry engines: victim write loses arbitration to
a rival create, `_resolve_rows` flips to absorb, then a rival
`delete` of the same path commits before `_update_materials` (window
staged via an in-script patch of the module global; every statement
between absorb and update is an await point, so the interleaving is
realizable under natural timing). Observed: victim write success with
observation `created /a/f.txt v3` while `stat`/`read` of `/a/f.txt`
fail and the content sits on the trash row. The absorb update is
keyed by bare `entry_id` (executemany arm on Oracle; `_values_update`
`guard=False` on MSSQL — no path predicate), and the parent bump's
guard on `/a` passes because a delete's parent bump changes no path.

Severity: torn observation / wrong success report, not data loss
(restore resurrects the absorbed content). Fix caveat from the
verifier: the path predicate alone is insufficient on the executemany
arm — the version read-back "learns" by `entry_id` and would still
find the trash row; application must be verified (per-row rowcount or
read-back path comparison). A *version* guard would be wrong here: it
would break by-design last-writer-wins between concurrent overwrites.

### 1.4 Concurrent ancestor-minting hard-fails the loser's whole batch

Two clients concurrently `write(..., parents=True)` under a shared
new directory `/x`: sequential execution succeeds both (existing
ancestors are forgiven — the `put_dir` "unchanged" outcome), but the
concurrent loser's **entire batch** fails on an ancestor the caller
never demanded to create exclusively. Measured (seam-staged plus 300
genuine `asyncio.gather` trials per engine):

| Engine | Loser outcome | Mechanism |
| --- | --- | --- |
| Postgres | rescued in 296/300 (40001 → redrive); **4/300 hard-fail** `conflict retryable=False` | path-unique-index escape → `_resolve_rows` probe at RR sees no occupant |
| MySQL | **300/300 hard-fail** `conflict retryable=False "lost arbitration"` | InnoDB RR probe consistent-reads the pre-rival snapshot → occupant `None` |
| MSSQL | hard-fail `exists retryable=False "Already exists: /x"` | RC probe sees the rival dir → `already_exists` |
| Oracle | hard-fail `exists retryable=False` | same as MSSQL |

The MySQL arm directly contradicts the dialect's own declared
`guard_miss="redrive"` doctrine ("never classify off a probe this
engine may contradict") — `_resolve_rows` probes anyway. In every
failing case an immediate identical retry succeeds, so
`retryable=False` is factually wrong. Two-part fix validated: (a)
occupant-probe-returns-`None` arms raise the stale-snapshot signal
(redrive) instead of classifying off a blinded probe — converges
MySQL/Postgres with the 40001 path; (b) a directory create losing to
a directory occupant at the matching stored path absorbs as
"unchanged" (mkdir-p parity) — required for the RC engines, where the
probe honestly sees the rival directory.

### 1.5 Copy/move destination claim races misclassify

Reproduced on Postgres: `copy /src → /dest` (existing dir occupant,
`overwrite=True`), rival `write(/dest/a.txt)` mid-window → the copy
fails `exists retryable=False path=/dest` with the driver detail in
`data` naming the *true* collision (`a.txt`) — wrong path, an
occupancy the caller was already granted, and self-evidencing
misattribution. The retryability half of the original claim was
**refuted**: a plain retry does not succeed — it returns the honest
ladder refusal `not_empty` (the rival's child made the occupant
non-empty) — so the defect is misclassification, not suppressed
success, and the fix is redrive (fresh ladder, honest per-pair answer
with correct paths), not flipping `retryable`. The same shape exists
in `_execute_move`'s use of `_classify_claim_race`. The claimed
self-pollution variant (probe finding the copy's own uncommitted row)
was **refuted as race-reachable** — every arrangement requires
already-torn state as a precondition.

### 1.6 Topology's single-row claim guards skip the capability gate

Code fact: `supports_sane_rowcount` appears only in writes.py;
`_reparent_to_trash` and `_execute_move` test `rowcount == 0` bare.
Empirically: on a simulated insane dialect (`CursorResult.rowcount`
patched to −1 after a rival commits), delete reported success and the
audit found a committed torn path cache — the exact silent guard miss.
Exposure today is GENERIC-floor-theoretical: every dialect the async
backend can mount reports sane single-row rowcount (verified live on
all five), and SQLAlchemy's default is `True`; but the generic floor
is precisely the population the project doctrine promises to serve
safely, and writes.py already refuses this case with a classified
`unsupported`. `_purge_subtree`'s lenient `0 <= rowcount` form is
*not* the model — on a guarded claim, skipping verification commits
torn state.

### 1.7 `retryable` is dialect-dependent for the same race

`classified()` never sets `retryable` (default `False`); the
stale-snapshot exhaustion path and `_classify_claim_race`'s conflict
arm set `True` explicitly. Net effect, measured: the same
one-increment race yields `conflict retryable=False` on MSSQL
(reprobe mode — and a plain retry then succeeded) vs
`conflict retryable=True` on MySQL (redrive exhaustion — the arm that
already burned four attempts). `_incoherent_row`'s docstring rationale
("the caller raced ordinary traffic as far as it can know",
`retryable=True`) applies verbatim to the sites that don't apply it.

## 2. Confirmed precedent findings (smaller)

- **`already_exists` monopoly violation** — envelope.py declares it
  "the one construction" of the occupied-site `exists`; topology's
  claim-race handler hand-rolls a second construction because the
  helper cannot carry `data`. All other sites comply (census in the
  verifier report: six helper sites, one violation).
- **Restore attribution loss** — demonstrated live on Postgres: a
  trash-side restore refused by an occupant returns
  `exists path='/f' data=None`; the requested trash path appears
  nowhere and is unrecoverable, while the *adjacent* `wrong_kind` arm
  stamps `data={'target': …}`. Also collapses under the envelope's
  value-identity dedup for two trash rows restoring to one dest. The
  transfer-verb `already_exists(dest)` site has the same latent shape.
- **`wrong_kind()` helper bypass** — topology hand-rolls
  "Cannot restore/move onto: {dest}" naming no kind;
  `wrong_kind(occupant["kind"], dest)` is strictly more informative in
  both directions and test-safe (conformance pins kinds, not
  messages). Requires the helper to grow `target=`.
- **`_PendingTransfer` layout tier** — defined in the Move/copy
  banner group but first consumed by `restore_rows` (a backward
  reference); by the CLAUDE.md tier rule a cross-group NamedTuple
  belongs in the shared-types tier. Cosmetic.

## 3. Extraction analysis (verified against all sites)

**Do extract** (all into `descent.py` unless noted; no import cycles —
verified against descent.py's current imports):

- **Chunked path-`IN` fetch kernel** (`rows_by_path`): five congruent
  sites (`_fetch_committed`, `_fetch_snapshot`, `_final_rows`,
  `_dest_parent_id`'s fetch half, reads' `_mappings_by_path`) — the
  identical `chunked(paths, membership_budget)` → `path.in_(chunk)` →
  merge-into-dict loop. Sharpening: the kernel takes a caller-computed
  path iterable; a separate `targets_with_ancestors` builder serves
  the two snapshot sites (a third site needs chain-without-target, so
  an `ancestors=` flag cannot express all sites). All five key by
  `path`; the id-keyed loops are a different family, left alone. The
  content join is a clean `source`/columns parameter; reads'
  `_entry_select` reshapes mechanically.
- **Subtree LIKE predicates** (`subtree_filter` self-or-descendants;
  `descendant_filter` strict): ~6 sites across topology/reads/descent.
  Implementation traps found: the ROOT case (`escape_like("/") + "/%"`
  would produce `//%` — the helper must own the root branch), and
  `liveness_filters`' De Morgan form must stay composed as conjuncts
  (a negated `or_` changes SQL text). Glob's bare-prefix LIKE is a
  different predicate; excluded.
- **Escaped-LIKE behavior pinned empirically**: wildcard-metachar
  paths (`/we%ird`, `/we_ird2`, `/we\ird` + decoy siblings a naive
  LIKE would match) pass through the full public API (write, tree,
  glob pattern + scope anchor, cascade delete, trash-side tree) on
  all four engines. Engine notes an extracted helper must preserve:
  `escape=` always explicit (MySQL's default escape is coincidentally
  backslash and would mask omissions; Oracle has *no* default escape).
  Nothing in the conformance suite currently pins LIKE-metachar paths
  — worth permanent pins.
- **`miss_errors` dict builder**: two sites (reads helper + writes
  inline), equivalent semantics; bundle with the kernel extraction,
  not standalone. **`supports_values_update` predicate** → dialects.py
  (two writes.py sites; placement argument, not deduplication).

**Do not extract** (upheld under pressure): the guarded-statement
primitive (writes' batch ladder vs topology's single-row guards share
a 2–3-line kernel; one abstraction needs mode flags for execution
strategy, miss semantics, and error type — the 1.6 fix is a *narrow
single-statement claim helper*, not a merge), the savepoint-claim
combinator (4-line idiomatic SQLAlchemy; classifiers irreducibly
site-specific), incoherent-row refusal (no topology analogue exists —
only writes matches rows through `(parent_id, name)` where the stored
path can contradict the request), chunked bulk insert recovery
(per-row blame vs fail-the-pair), error-text constructors (a
results-vocabulary question), observation assembly (three data
sources, shared model already extracted).

## 4. Cross-cutting conclusion

Findings 1.3–1.5 and 1.7 are one defect family: **probe-and-classify
at a race seam produces non-retryable verdicts that a whole-method
redrive would resolve honestly** — and the codebase already owns the
correct mechanism (the stale-snapshot signal → `with_retry` redrive),
which was empirically flawless everywhere it fired during the
campaign. Routing those arms into it, plus the mkdir-p absorb
semantic, collapses most of the classification defects into landed
discipline. Findings 1.1 and 1.2 are missing guard/re-collection
applications of the same 086 machinery; 1.6 is a missing capability
gate with an existing refusal precedent to port.

Also verified clean in passing: every `IN` list and multi-row insert
in both files chunks within the declared budgets at 10k+ batch sizes;
no raw driver text reaches any public message; seam naming and the
delete `local_bumps` accounting are sound; per-driver rowcount
semantics match the arms that rely on them (checked against the
SQLAlchemy sources).
