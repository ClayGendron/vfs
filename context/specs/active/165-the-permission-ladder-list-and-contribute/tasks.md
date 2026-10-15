# 165 — tasks

Ordered; each leaves the tree green. `scripts/ci.sh` before any commit;
`db_test` before landing slice B.

## Slice A — the words and the table

- [x] 0. Clay accepts ADR 080 (the review's three questions answered
      2026-10-14).
- [x] 1. `grants.py`: six rungs, dense ranks; `Posture` = the rung
      words; `POSTURE_LEVELS` removed and its four readers take the
      word; `open`/`shared`/`private` retired in the constructor
      defaults and `serve()`; docstrings.
- [x] 2. The same commit: the fifteen raw `everyone_level=2` inserts
      and the `{0, 1}` pins → `LEVEL_RANK[...]`; `_POSTURE_OF`,
      `grant_worlds` tuples, `test_grants.py:215,428`; the docs fence
      in `share-a-folder-with-grants.md`. Green.
- [x] 3. `params.py`: `GRANTABLE_LEVELS` and `POSTURES` derived;
      `tests/test_params.py`.
- [x] 4. `ops.py`: `Rung`, `Needs`, the full `VERB_RUNGS` table of
      spec §1; the drift test with its three invariants in
      `tests/test_ops.py`; `grants.py` imports `Rung` from `ops`.
- [x] 5. `rows.py` format bump; `engine.py` refusal text says
      re-provision; `tests/storage/database/test_engine.py`.

## Slice B — the storage half

- [x] 6. `rights.py`: `Resolution` mapping + `at()`; aliasing of pieces
      with a shared `ranges()`; `weight`; the system actor;
      `resolve_authority`; the aliasing tests (`at("list").admits` on a
      `list`-labelled row, with and without a pending posture).
- [x] 7. `rights.py`: `Visibility(need)` with two compiles; `admits`
      returns a rung; `tombstones(rows, need)`; road probes at the
      `list` compile; `seen_kinds`; the descent ladder's hint at `read`.
- [x] 8. `rights.py` `WriteGate` reads `Needs`: the read leg compares
      `traverse`; the occupied-creation leg compares `create`; the
      occupied branch at `primary` or own; the road passes `list`
      slots; a write at a tombstone judged as `restore`; `_grant_refusal`;
      `list_grants`' `not_found` on a `list` path. Tests: `copy` from a
      `list` file and directory; `mkdir(exist_ok=True)` on a `list`
      directory; `mkedge` to a road directory.
- [x] 9. `rights.py` + `backend.py`: the anonymous check moves to the
      gate and the view with the posture rows as its source, per
      target and per verb shape; `_resolution` loses it; the `/scratch`
      tests for every shape of spec §2.
- [x] 10. `backend.py`: `_viewed`, `_gate` from the table; the eleven
      literals removed; the grep pin.
- [x] 11. `backend.py` + `edges.py`: `rmedge`'s per-target `list` check
      before `_endpoint_ids`, folded into `rmedge_rows`' per-row record; the review's `rmedge_leak.py` as the test (identical
      records; mixed batch).
- [x] 12. `reads.py`: bare projection at `< read` in `_screen`,
      `_children_by_parent`, `tree_rows`, `glob_rows`, `_point_rows`,
      `_visible_rows`; `read_rows` refuses; `LIST_FIELDS` with the
      `ROAD_FIELDS` alias; `glob`'s counts include `list` rows.
- [x] 13. `grep.py`, `glean.py`: the `read` view for the post-filter,
      candidates, lexicon and statistics; the `lexical_stats` test;
      `grep`'s truncation warning excludes `list` rows.
- [x] 14. `trash.py` / the trash view: bare tombstone, no `deleted_at`;
      the live-side plain `not_found`.
- [x] 15. Edge rows: type only on an edge touching a `list` node;
      `mkedge` target at `list`.

## Slice C — tests, docs, amendments

- [x] 16. `grant_worlds.py`, `oracles/grants.py`, `grants_contract.py`:
      the six rungs in every sweep; the `list` projection oracle; the
      `list`, `add` and `contribute` contract on both legs.
- [x] 17. `test_rights.py`: the road baseline world from
      `l1_road_baseline.py` as a pin; the three matrices (named user,
      set, anonymous); the search-verb tests; the clause fan versus
      three-seek on `list` views.
- [x] 18. Docs: `docs/reference/authority.md`, the share-a-folder
      how-to (the rungs and postures; the "not populated" note beside a
      bare `ls`), the README permission strings.
- [x] 19. ADR status lines 064, 065, 068, 070, 073, 074, 079; ADR 080 →
      accepted; `STATUS.md`; landing notes. `db_test`: see the landing notes.
