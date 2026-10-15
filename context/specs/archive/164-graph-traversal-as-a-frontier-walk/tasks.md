# 164 — tasks

Ordered; each leaves the tree green (`uv run pytest`, `ruff check`,
`ruff format --check`, `ty`). `scripts/ci.sh` before any commit.

## Slice A — vocabulary, gate, model, render

- [x] 0. Spec 165 landed (2026-10-14; `VERB_RUNGS["graph"]`,
      `Visibility.admits → Rung`, `holds`, `reads`, `road` in place);
      the pre-build review's amendments folded into this spec.
- [x] 1. `ops.py`: `GRAPH_METHODS` = the four names; module docstring
      paragraph rewritten.
- [x] 2. `params.py`: the new `graph` ParamSpecs; `OnlyWith`,
      `Disjoint`, `Segments` and `VALUE_RULES`; `tests/test_params.py`
      (the refusals and the signature-default pin).
- [x] 3. `base.py` `graph()`, `session.py` `graph()` and
      `protocol.SupportsGraph`: the new keyword parameters with the
      defaults; dispatch kwargs pin in `tests/base/test_dispatch.py`;
      samples in `tests/test_ops.py`, `tests/base/test_authority.py`.
- [x] 4. `models/entry.py`: `depth` query field; `OBSERVATION_QUERY_FIELDS`;
      the drift test still green.
- [x] 5. `results/projection.py` default; `results/render.py`
      tree-glyph graph arrangement (parent rule, edge type and arrow
      per line, cross-links and cycles marked, count line); render
      tests (hierarchy, cycle marker, orphan root, edge row never a
      node, truncated line). No Mermaid.

## Slice B — the walks

- [x] 6. `ranges.py`: `pinned_join` public.
- [x] 7. `storage/backends/database/graph.py`: the request, seed
      resolution with the road screen, `hop_statements` (direction,
      chunk, type filters with `fs` off unless named, liveness, the
      pinned join, the road probe), `walk` (visited set,
      discovering-edge tie-break, `depth=None`, early stop at `limit`),
      `induced_edges` (one list, far endpoint judged in Python),
      `observe` (whole and bare nodes, type-only edges, `limit` with
      edges following nodes, the truncated warning).
- [x] 8. `backend.py` `graph` under `_execute` / `_viewed`; `_viewed`
      at the traverse rung; `capabilities()` unchanged (derived); flip
      the pins in `tests/storage/database/test_reads.py` and
      `tests/storage/test_memory.py`.
- [x] 9. `tests/support/oracles/graph_walk.py` (readable BFS over an
      edge list) and the conformance family in `storage_contract.py`:
      directions × depths, multi-seed union, seeds at depth 0, the
      tombstone cut, type filters, induced edges incl. back-edges,
      `limit` and the early stop, observation seeds.
- [x] 10. `tests/storage/database/test_graph.py`: the leak test under
      both predicate forms, the `list` pass, the road probe, statement
      counts at 10,000 seeds (`slow`) under the SQLite profile and a
      1,000-budget profile, the cycle bomb, the planner pin (the hop
      statement renders the profile's join keyword), no statement over
      budget, the type-list refusal.

## Slice C — meet

- [x] 11. `graph.py`: `meet` loop (claim order, meetings, union-find,
       early stop, radius, the boundary hop), `prune` (undirected),
       `prune_minimal` (articulation points), the components record.
- [x] 12. `tests/support/oracles/meeting_subgraph.py` written to the
       declared rules; 200 seeded random digraphs; `a → x ← b`; the
       two-route cycle; hidden, `list`-only and tombstoned
       intermediaries; one seed; no seed; the boundary meeting; the
       early-stop statement count (`slow`).

## Slice D — docs and the claim

- [x] 13. README banner, verb table, search section, the Sybil example.
- [x] 14. `docs/reference/api.md` graph section;
       `docs/how-to/walk-the-edges-around-a-file.md`; the how-to index.
- [x] 15. ADR 059 and ADR 016 status lines record the amendments; ADR
       079 status → accepted; `STATUS.md`; this spec's status line and
       landing notes; the folder to `archive/`.
- [ ] 16. `db_test` skill: run the four engine legs; record outcomes
       in the landing notes (not run at the landing: no Docker here).
