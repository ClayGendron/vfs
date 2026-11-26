# Study: The permission ladder, its list, add and contribute rungs, the verb-to-rung table, and the walk's rung

## Verdict

Landed. All three slices (A, the words and the table; B, the storage half; C, the tests, docs and amendments) are in the tree, the spec's own landing notes record a single tree-green landing on 2026-10-14 with the four engine legs green, and the roadmap lists 165 as "built but not archived" with story R7 criterion 1 moving it to `specifications/archive/`. No unit is proposed; the folder is archived with its landing notes, after the stale names below are corrected or footnoted.

## Against the tree

- READ `src/vfs/ops.py:117`: `Rung = Literal["none", "list", "read", "add", "contribute", "read_write"]`, the six rungs in the spec's order; `RUNGS` at `ops.py:123` derived with `get_args`.
- READ `src/vfs/ops.py:127-139`: `Needs(primary, create, passing)`; the third field is `passing`, not the spec's `traverse`.
- READ `src/vfs/ops.py:142-166`: `VERB_RUNGS` has one entry per routed op and its values match spec §1's table row for row, under the renamed ops `search` (was `glean`) and `traverse` (was `graph`).
- READ `tests/test_ops.py:119,125,133`: the drift test and the ladder-order and mutation-floor invariants exist.
- READ `src/vfs/storage/grants.py:62,72,79,85,88`: `GrantLevel = Rung`, `GRANTABLE_LEVELS` derived as the ladder minus `none`, dense `LEVEL_RANK`, `Posture = GrantLevel`. EXECUTED grep for `POSTURE_LEVELS` under `src/vfs`: no match, so it is gone.
- EXECUTED grep for the literals `"open"`, `"shared"`, `"private"` under `src/vfs/*.py`: no match. READ `backend.py:167` and `engine.py:181`: constructor default posture `"read_write"`.
- READ `src/vfs/storage/backends/database/rights.py:179,217,519,560,660,692`: `Resolution` with `at(rung)`, `Visibility` with `admits -> Rung`, `tombstones(rows, need)`, `WriteGate`.
- READ `backend.py:695-1059`: every gate call passes `VERB_RUNGS[...]`; READ `authorized.py:55,312-344` and `edges.py:46,391` read the same table.
- EXECUTED grep: `unauthenticated_at` / `unauthenticated_refusals` live in `rights.py`, `backend.py` and `authorized.py`, the per-target anonymous check of §2.
- READ `edges.py:205-222` and `backend.py:969-977`: `rmedge_rows(unnamed=...)` folds a target the caller may not name into the absent-target record, closing the leak of §2.
- READ `reads.py:113-114,910`: `LIST_FIELDS = {"path", "kind"}` with `ROAD_FIELDS` kept as an alias; `traverse.py:51,81` builds on it.
- READ `writes.py:112-125`: `_CLOBBER_COLUMNS` holds no `owner_id`, the "an overwrite keeps the row's owner" rule the landing notes added.
- EXECUTED `ls tests/storage/database/test_ladder.py`: present; EXECUTED grep counts 26 test functions in it.
- READ `src/vfs/models/rows.py:139`: `SCHEMA_FORMAT_VERSION = 27`; the spec's bump to 23 landed and four later format bumps followed (INFERRED from the number).
- The problem statement is closed at HEAD: the vocabulary, the table and the storage half it asked for exist (INFERRED from the reads above).
- Later archived specs built on top of the ladder rather than replacing it (READ `context/standards/roadmap.md:367`): the grant gate judges the subtree (2026-11-07), a read-only rule gates the verbs beneath (2026-11-07), the scan tier reveals nothing about hidden rows (2026-11-12), a mutation is authorized at its commit point (2026-11-14). None undoes a slice of 165 (INFERRED from their titles and the roadmap's "built, on every engine leg" status).
- READ `context/specifications/archive/2026-11-09-the-verbs-take-the-names-agents-know.md:1`: `glean` became `search`, `graph` became `traverse`, and the needs table's `traverse` field was renamed (to `passing`) "so the word has one meaning"; rungs kept their values.

## Where the roadmap places it

- READ `context/standards/roadmap.md:106`: "of the numbered, 4 built but not archived (165, 162, 152 A/B, 173)".
- READ `context/standards/roadmap.md:960-965`: story R7, Context-pipeline true-up, gate b; criterion 1 moves 165 to `specifications/archive/` with landing notes, its stale lines corrected first.
- READ `context/standards/roadmap.md:34,366`: the ladder (six rungs) is "built, on every engine leg".
- Gate: b, as an archive action under R7, not a build.

## Units proposed

None. The spec is landed; its conversion is an archive move under R7 criterion 1, not a nine-section spec.

## Open choices, each verified

- The spec holds no `[NEEDS CLARIFICATION]` marker (READ spec.md:3, "no `[NEEDS CLARIFICATION]` remains"). The three review questions (a revive is a restore; no road for anonymous; `rmedge`'s hidden target takes the absent target's record) were decided 2026-10-14 and are built (READ spec.md:3, `rights.py` tombstone-as-restore per `ops.py` docstring at 166, `edges.py:205-222`). Verification: already-ruled, and built.
- "`grep`'s candidate budget counts hidden candidates" is named in spec §2 as left open and out of scope (READ spec.md "grep.py, glean.py" bullet and Scope). Not a choice of this spec. The 2026-11-12 archived spec "the scan tier reveals nothing about rows a caller cannot read" covers the hidden-row side of the scan tier (READ roadmap.md:367); whether it closes the nominator budget in full is not settled by this study. Verification: already-ruled in part; no action for 165.
- `manage`, group ownership, an append verb, a `create`-only rung and `run`'s own axis are parked (READ spec.md Scope; roadmap.md:372 "`manage` rung, group ownership, non-system membership admin | parked"). Verification: already-ruled (parked by the roadmap).
- The landing flagged one added rule for confirmation: an overwrite or edit keeps the row's owner (READ spec.md landing notes). It is built and pinned (READ `writes.py:112-125`). Precedent: the commit-point spec of 2026-11-14 and the roadmap carry the ladder as built without reversing it (READ roadmap.md:367). Verification: holds; precedent is the landed code path `writes.py` `_CLOBBER_COLUMNS` and SharePoint/Drive's edit-any-without-ownership-transfer semantics cited by the spec's research memo (`context/research/2026-10-14-the-permission-ladder-list-and-contribute.md`).
- Adjacent but not this spec's choice: D15, what "open" means on the six-rung ladder for `serve()`'s refusal (READ roadmap.md:369,1087, lean "refuse when any mount's root everyone-level is `add` or above"). It belongs to story I2, not to 165, and does not block archiving.

## What is stale

- `Needs(primary, create, traverse)` (spec §1): the field is `passing` (READ `ops.py:139`; renamed by the 2026-11-09 archived spec).
- Ops `glean` and `graph` in the table and §2-§3: now `search` and `traverse` (READ `ops.py:148-149`; the 2026-11-09 archived spec).
- Module names `glean.py`, `graph.py`: now `search.py`, `traverse.py` (READ the 2026-11-09 archived spec, line 3; EXECUTED grep found `traverse.py` importing `LIST_FIELDS`).
- "spec 164 reads `VERB_RUNGS["graph"]`": the entry is `VERB_RUNGS["traverse"]` (READ `ops.py:149`).
- `SCHEMA_FORMAT_VERSION` bumped to 23 (landing notes): the current format is 27 (READ `rows.py:139`).
- Test location: spec §3 names `test_rights.py` for the baseline and matrices; the landing put them in `tests/storage/database/test_ladder.py` (READ spec.md landing notes; EXECUTED ls).
- Docs paths: `docs/reference/authority.md` and `docs/how-to/share-a-folder-with-grants.md` still exist (EXECUTED ls), but the docs site's source moved to `documentation/` on 2026-11-12 (READ roadmap.md:807); the API reference page is `documentation/reference/python-api/authority.md` (EXECUTED find).
- ADR references (ADR 080 and the amended 064, 065, 068, 070, 073, 074, 079) and `STATUS.md`: decision records were retired on 2026-10-30, commit `3667fec2`, and `STATUS.md` is frozen (READ roadmap.md:106,962).
- Status line wording "Not started" inside the draft history sits beside "landed 2026-10-14" (READ spec.md:3); the landed line is the true one.
- Owner name in the Status and Owner lines: the archived copy follows the archive's convention; under `agents/` voice rules a ruling is written "Decided 2026-10-14: ..." (INFERRED from AGENTS.md).

## Notes for the conversion

- Action: archive, not convert. Move `context/specifications/active/165-the-permission-ladder-list-and-contribute/` to `context/specifications/archive/` under R7 criterion 1; correct the Status line first (drop "Not started"; say landed 2026-10-14) and add a footnote that `glean`/`graph`/`Needs.traverse` were renamed `search`/`traverse`/`Needs.passing` on 2026-11-09 and the format has since moved to 27.
- Dependents: spec 164 (the graph walk) consumed `VERB_RUNGS`; its walk is built as `traverse` with `passing="list"` (READ `ops.py:149`). Any backlog spec that cites "ADR 080" for the ladder should cite this archived spec and `ops.py` instead.
- Roadmap decisions needed to archive: none. D15 is adjacent (serve()'s refusal on the ladder) and belongs to I2.
- Nothing in this study changes behaviour; it is landed work recorded as landed.
