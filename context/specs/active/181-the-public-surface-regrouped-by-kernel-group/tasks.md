# 181 — tasks

This spec lands last in ADR 087's series. Before task 1, specs 167
(slice A at least: `run` out, `cli` and `bound` in), 174, 175, 176 and
179 have landed; where one has not, the task that needs it says so and
waits. Each task lands green through `scripts/ci.sh` (lint, format,
types, the suite at 100% coverage, the docs fences, the wheel budget).
Tasks 4, 5 and 9 also run the four engine legs (`db_test`) before they
land, because they change what the read and write builders select.

## The groups and the order (spec §1, §2, §7)

1. **`ops.py` declares the groups.** Add `OpGroup`, `OP_GROUPS`,
   `GROUP_OF`, `SURFACE_ORDER`, `CONTROL_METHODS` and `FRONT_METHODS`.
   Rewrite the `Op` literal and `VERB_RUNGS` in `SURFACE_ORDER` order.
   Add the two-axes paragraph to the module docstring. Move
   `MANAGEMENT_METHODS` out of `tests/test_ops.py` (it becomes
   `CONTROL_METHODS | FRONT_METHODS`). Add the drift tests of §2.2
   rules 1, 2 and 4 (criterion 12).
2. **Every surface in one order.** Reorder `PARAMS` (with the group
   comments), `RULES` and `VALUE_RULES`; reorder `VirtualFileSystem`'s
   public verbs under the five new banners (§7.2) and `Session`'s
   under the same banners. Add §2.2 rule 3, the order test
   (criterion 13). No behaviour changes in this task: the diff is moves
   and banners, and the suite passes untouched.
3. **The docstrings.** `base.py`'s module docstring gains §7.1's two
   paragraphs (the kernel and its facets; the three trust tiers).
   `move`, `stat`, `tree`, `edit` and `delete` gain §5's and §7.2's
   sentences; `Session`'s docstring gains the front sentence.

## `entry_id` and `owner_id` (spec §3)

4. **The model and the read builders.** Add `entry_id` and `owner_id`
   to `Observation` (§3.3), `OBSERVATION_ROW_FIELDS`, the three-way
   partition and its drift tests, the no-input-model-carries-it test,
   and the `to_observation` fixture with an owner. Add both fields to
   `reads.py`'s `ENTRY_OBSERVATION_FIELDS`; fix the duplicate columns
   in `_entry_projection` and `_mappings_by_path` (§3.5). Tests:
   criteria 1–6 and 8 at the router (three authorities, the lifecycle
   probe of §3.2, bare rows, `owner_id` served, every read verb, the
   counted statements and ULID decodes). Run the engine legs.
5. **Mutation rows.** Pass `entry_id` in `writes.py` `_finish`, add it
   to `PendingRow` and its four construction sites (`topology.py`
   move, rename-to-self and copy via `_execute_copy`'s returned id;
   `trash.py` restore), and to `trash.py` `_observe_deleted`. Tests:
   criterion 7, including the 10,000-entry `write` at HEAD's statement
   count. Run the engine legs.
6. **Read-only, proved.** The parameter-name sweep over
   `VirtualFileSystem`, `Session`, `Result.pipe` (task 8 adds it; until
   then the sweep covers the rest), `vfs.chain` (task 8) and every
   `Supports*` protocol method; the `PARAMS` sweep; the forged-row test
   (criteria 9 and 10). If spec 171 has landed, add the input-schema
   walk to 171's schema tests; otherwise leave a note in this spec's
   landing notes and add it when 171 lands.
7. **The merge law.** Extend `_merge_observation`'s agree-or-null rule
   to `_COORDINATES = ("version", "entry_id")` and pin it, with the
   algebra-law tests run over rows that carry ids (criterion 11).
   Update the payload round-trip test to carry both new fields.

## Chaining (spec §4)

8. **`Result.pipe` and `vfs.chain`.** Add `Result.pipe` (§4.2) and
   `src/vfs/chain.py` with `glob` and `grep` moved from `base.py`'s
   `_glob_rows_in_hand` and `_grep_rows_in_hand`, behaviour unchanged.
   Remove `observations` from `glob` and `grep` on the router, the
   session and `PARAMS`, and their two shape rules from `RULES`. Move
   every chained test (the 31 single-line sites in
   `tests/base/test_grep_namespace.py`,
   `tests/base/test_glob_namespace.py` and
   `tests/base/test_dispatch.py`, plus any multi-line ones) to the
   `pipe` form. Update the envelope docstring example. Tests: criteria
   15 and 16, the latter at 10,000 rows with `in_list_budget=1000`.

## The derived verbs (spec §5)

9. **Oracles and parity.** Add `tests/support/oracles/derived.py`
   (`tree`, `edit`, `rmdir` from kernel calls; `edit` uses spec 174's
   `write(if_version=)`). Add the parity tests of criterion 17 at the
   system actor and at a principal with a partial view. Add the
   `entry_id` rows of criterion 18 to spec 179's conformance families.
   Run the engine legs.

## The README and the docs (spec §8)

10. **README.** Replace the verb table and the sentence under it
    (§8.1). Add the README table test (criterion 14). If spec 167's
    task 20 has already edited the table, rebase onto it.
11. **Docs.** Write `docs/explanation/architecture.md`'s section "The
    kernel and its facets" with the trust tiers; add the pointer
    sentence to `open-in-process-loud-at-the-edge.md`; add the
    *Surface* section to `docs/reference/api.md`; rewrite
    `docs/reference/session.md`'s verb list in group order; add the
    glossary entries. Every fenced example runs under the docs step of
    `scripts/ci.sh`.

## Close-out

12. **Landing.** Run `scripts/ci.sh` and the four engine legs once more
    (criteria 18 and 19). Record in *Landing notes*: Clay's answers to
    the six markers, the measured ULID-decode and statement counts, and
    the ADR amendments (087 pins 1, 3, 4, 16; 034; 010; 004) for the
    session lead to fold in. Move the spec to `specs/archive/`.
