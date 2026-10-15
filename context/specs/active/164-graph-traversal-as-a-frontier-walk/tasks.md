# 164 — tasks

Ordered; each leaves the tree green (`uv run pytest`, `ruff check`,
`ruff format --check`, `ty`). `scripts/ci.sh` before any commit.

## Slice A — vocabulary, gate, model, render

- [ ] 0. Spec 165 (the ladder) lands first — Clay, 2026-10-14
      (**landed 2026-10-14**: `VERB_RUNGS["graph"]`, `Visibility.admits
      → Rung`, `holds`, `at(rung)` are in place); then Clay accepts
      ADR 079. Names, `limit` 128 and the induced edges
      are decided.
- [ ] 1. `ops.py`: `GRAPH_METHODS` = the four names; the `graph`
      entries in spec 165's verb-to-rung table; module docstring
      paragraph rewritten.
- [ ] 2. `params.py`: the new `graph` ParamSpecs; the conflicting-type
      refusal; the `minimal`-only-with-`meet` shape rule; `tests/test_params.py`.
- [ ] 3. `base.py` `graph()` and `protocol.SupportsGraph`: the three
      keyword parameters; dispatch kwargs pin in `tests/base/test_dispatch.py`;
      samples in `tests/test_ops.py`, `tests/base/test_authority.py`.
- [ ] 4. `models/entry.py`: `depth` query field; `OBSERVATION_QUERY_FIELDS`;
      the drift test still green.
- [ ] 5. `results/projection.py` default; `results/render.py`
      tree-glyph graph arrangement (edge type per line, cross-links
      and cycles marked, meeting point, count line); render tests
      (hierarchy, cycle marker, meeting point, edge row never in the
      node table, truncated line). No Mermaid.

## Slice B — the walks

- [ ] 6. `storage/backends/database/graph.py`: `resolve_seeds`,
      `hop_statements` (direction, chunk, type filters with `fs` off
      unless named, liveness, `range_join`), `walk` (visited set,
      discovering-edge tie-break, `depth=None`), `induced_edges`
      (shared with `meet`), `observe_nodes`, `observe_edges`, `limit`
      128 with edges following nodes, and the truncated warning.
- [ ] 7. `backend.py` `graph` under `_execute` / `_viewed`;
      `capabilities()` no longer withholds `graph`; flip the pins in
      `tests/storage/database/test_reads.py` and `tests/storage/test_memory.py`.
- [ ] 8. `tests/support/oracles/graph_bfs.py` (readable BFS over an
      edge list) and the conformance family in `storage_contract.py`:
      directions × depths, multi-seed union, seeds at depth 0, tombstone
      cut, the leak test under both predicate forms, the road
      difference, type filters, induced edges, `limit`.
- [ ] 9. `tests/storage/database/test_graph.py`: statement counts at
      10,000 seeds (`slow`) under the SQLite profile and a 1,000-budget
      profile; the cycle bomb's 2 statements; the planner pin (the hop
      statement renders the profile's join keyword); no statement over
      budget.

## Slice C — meet

- [ ] 10. `graph.py`: `meet` loop (ownership order, meetings,
       union-find, early stop, radius), `prune` (undirected), `prune_minimal`
       (articulation points), `induced_edges`, the `components` info record.
- [ ] 11. `tests/support/oracles/meeting_subgraph.py` from the study's
       `r4_reference.py` with the declared tie-breaks; 200 seeded
       random digraphs; `a → x ← b`; the two-route cycle; hidden and
       tombstoned intermediaries; one seed; no seed; early-stop statement
       count (`slow`).

## Slice D — docs and the claim

- [ ] 12. README banner, verb table, search section, the Sybil example.
- [ ] 13. `docs/reference/api.md` graph section; `docs/how-to/walk-the-edges-around-a-file.md`.
- [ ] 14. ADR 059 and ADR 016 status lines record the amendments; ADR
       079 status → accepted; `STATUS.md`; this spec's status line and
       landing notes.
- [ ] 15. `db_test` skill: run the four engine legs; record outcomes
       in the landing notes.
