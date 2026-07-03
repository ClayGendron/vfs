# 035 — One Operation Vocabulary (`vfs/ops.py`)

- **Status:** draft
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** refactor (small; spec-only story)
- **Depends on:** the base2 router core (mount routing, capabilities gate,
  `_route_single`); 032 (unified path resolution)
- **Enables:** the router verb-surface buildout (write/edit/delete/mkdir/
  mkedge/move/copy/tree/glob/grep/glean/graph), the `DatabaseFileSystem`
  port — both need a settled op list before they can pin anything to it

## Intent

Create `src/vfs/ops.py` as the **single source of truth for operation names
and their dispatch classes**, and rewire the three modules that currently
each hand-maintain their own copy (`base2`, `permissions`, `projection`) to
import from it. Add a drift test so the vocabulary and the router surface
cannot diverge again.

This story defines the vocabulary only. It does **not** build the missing
router methods — the router still publicly answers only `read`, `stat`,
`ls`, and `run` when this story ships.

## Why — the friction

The op vocabulary is defined three times today, and two of the copies
already disagree:

- `base2._MUTATION_OPS` = `{write, edit, move, copy, mkedge, rm, delete}`
- `permissions.MUTATING_OPS` = `{write, edit, delete, mkdir, mkedge, move, copy}`
- `projection.ACTION_FUNCTIONS` = `{write, delete, edit, move, copy, mkdir, mkedge}`

The `rm`-vs-`mkdir` mismatch is a live gate bug in waiting: when the verbs
land, an `mkdir` would pass the router's mutation-path check unauthorized,
and an `rm` (a verb we have since decided against — `delete` wins) would
skip the permission gate. Three hand-copies of a list that must agree is
exactly the drift the codebase's chokepoint philosophy exists to prevent.

## Decided vocabulary

Sixteen routed ops. `cli` is deliberately **not** one of them (see below).

| set | members |
|---|---|
| `MUTATING_OPS` | `write`, `edit`, `delete`, `mkdir`, `mkedge`, `move`, `copy` |
| `TWO_PATH_OPS` | `move`, `copy` (subset of `MUTATING_OPS` — a routing shape, not a third permission class) |
| `READ_OPS` | `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `glean`, `graph` |
| `EXEC_OPS` | `run` |
| `ALL_OPS` | `MUTATING_OPS | READ_OPS | EXEC_OPS` (16 ops) |

Supporting decisions, settled here so later stories don't reopen them:

- **`delete` is the removal verb.** `rm` is gone from every set.
- **`cli` is a meta-verb, not an op.** It parses a command string into an
  AST of the real verbs (`vfs/query/`) and re-enters through their public
  methods, so every permission and mutation gate fires on the real verb. It
  must never appear in `MUTATING_OPS`, capability sets, or `ALL_OPS` — a
  read-only mount cannot otherwise distinguish `cli "grep foo"` from
  `cli "delete /x"`. State this in the module docstring; do not model it as
  a set (a `META_OPS` set would invite someone to iterate it into a gate).
- **`graph` routes as one op** (`method=` selects the algorithm); results
  report the *specific* method name (`pagerank`, `descendants`, ...) in
  `VFSResult.function`. That rendering vocabulary stays in `projection.py`;
  `ops.py` is dispatch-only and must not grow a `GRAPH_METHODS` table.
- **`glean` is the ranked-search verb** (the indexed counterpart of `grep`).
  The method-specific function names (`vector_search`, `bm25`, ...) remain
  in `projection.py` as rendering vocabulary.
- **`Op` is a `typing.Literal`** of the sixteen names, used to type the
  router's internal `op` parameters so a misspelled verb is a type error,
  not a runtime `AttributeError`. The public `capabilities()` return stays
  `frozenset[str]` — a remote peer may advertise ops this client does not
  know (same forward-compatibility stance as `VFSErrorKind`).

## Current state

- `base2.py` defines `_MUTATION_OPS` (with the stray `rm`, missing `mkdir`)
  and consults it in `_route_single` / `_dispatch_grouped_observations`.
- `permissions.py` defines `MUTATING_OPS` and consults it in
  `check_writable`; its `TYPE_CHECKING` imports point at the dead stack
  (`vfs.base`, `vfs.results`).
- `projection.py` defines `ACTION_FUNCTIONS` as a third copy; it has no
  default projection for `glean` or `run`.
- `exceptions.py`'s `TYPE_CHECKING` import of `VFSResult` points at the
  dead `vfs.results`.
- No test pins any of these to each other.

## Target state

- `src/vfs/ops.py` exists: module docstring (stating the `cli` and `graph`
  rules above), `from __future__ import annotations`, the `Op` Literal, and
  the five `Final[frozenset[Op]]` constants with exactly the memberships in
  the table. Nothing else — no functions, no graph-method or rendering
  vocabulary. Follow the CLAUDE.md module layout.
- `base2.py`: `_MUTATION_OPS` is deleted; the two gate sites use
  `ops.MUTATING_OPS`. Internal `op` parameters are typed `Op` where that
  does not fight the `getattr` dispatch.
- `permissions.py`: its `MUTATING_OPS` definition is deleted; it imports
  the name from `vfs.ops` (keeping `from vfs.ops import MUTATING_OPS` so
  existing references to `permissions.MUTATING_OPS` still resolve).
  `TYPE_CHECKING` imports point at `vfs.base2` / `vfs.results2`.
- `exceptions.py`: `TYPE_CHECKING` import points at `vfs.results2`.
- `projection.py`: `ACTION_FUNCTIONS` is assigned from `ops.MUTATING_OPS`
  (derived, not copied). `glean` joins `RANKED_SEARCH_FUNCTIONS` (default
  projection `("path", "score")`); `run` gets a default projection of
  `("path",)`. `KNOWN_FUNCTIONS` therefore grows by exactly `glean` and
  `run`.
- `tests/test_ops.py` exists (see acceptance criteria for its assertions).

## Scope

### In

1. `src/vfs/ops.py` as specified.
2. Rewiring `base2.py`, `permissions.py`, `projection.py`.
3. The stale `TYPE_CHECKING` import fixes in `permissions.py` and
   `exceptions.py`.
4. The `projection.py` additions for `glean` and `run`.
5. `tests/test_ops.py`.

### Out

- **No new router methods.** The twelve unbuilt verbs are the next story;
  this one only names them.
- **No xfail/skip markers.** Every test added by this story must pass
  green. Do not write a test asserting that every op in `ALL_OPS` is a
  public router method — that is the *buildout* story's acceptance
  criterion, and it would fail today. This story's drift test asserts the
  subset direction only (see criterion 5).
- **No gate-behavior tests.** Whether `mkdir` is now write-gated and `rm`
  unrecognized is observable only through routed verbs that do not exist
  yet; that coverage lands with the router buildout story.
- No changes to `render.py`, the old stack (`base.py`, `models.py`,
  `results.py`, `backends/`), or `vfs/query/`. Broken imports in the old
  stack are expected mid-refactor and are not this story's problem
  (per CLAUDE.md).
- No rewrite of `permissions.py`'s long module docstring (it references
  old-base chokepoints; that cleanup belongs to the router buildout story
  that makes it true again).

## Acceptance criteria

1. `vfs.ops` defines `Op` and the five sets with **exactly** the
   memberships in the *Decided vocabulary* table; `ruff` and `ty` pass for
   `ops.py` and every touched live-stack file.
2. Set invariants hold and are asserted in `tests/test_ops.py`:
   `ALL_OPS == MUTATING_OPS | READ_OPS | EXEC_OPS`;
   `TWO_PATH_OPS <= MUTATING_OPS`; `MUTATING_OPS`, `READ_OPS`, and
   `EXEC_OPS` are pairwise disjoint; `"cli"` and `"rm"` appear in no set.
3. Grepping the live stack finds no other definition of the mutation list:
   `base2._MUTATION_OPS` is gone; `permissions.MUTATING_OPS` and
   `projection.ACTION_FUNCTIONS` are the `ops` objects themselves
   (assert identity or equality in the drift test), so the three consumers
   cannot drift independently.
4. `projection.default_projection("glean") == ("path", "score")` and
   `projection.default_projection("run") == ("path",)`; both names are in
   `KNOWN_FUNCTIONS`.
5. Drift test, subset direction: every public async verb currently on
   `VirtualFileSystem` other than the mount-management surface
   (`add_mount`, `remove_mount`, `close`) is a member of `ALL_OPS` — i.e.
   today `{read, stat, ls, run} <= ALL_OPS`, and any *future* public
   coroutine added to the router must be either a registered op or added
   to the management allowlist for the test to pass.
6. Full live suite (`uv run pytest tests/`) passes with **zero** xfail,
   skip, or warning markers added by this story.
