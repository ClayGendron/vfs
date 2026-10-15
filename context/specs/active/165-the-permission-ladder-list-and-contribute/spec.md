# 165 — The permission ladder: `list`, `add` and `contribute` rungs, the verb-to-rung table, and the walk's rung

- **Status:** **landed 2026-10-14** (ADR 080 accepted by Clay the
  same day: "accepted, please implement the full 165 spec"; the three
  slices built in one landing, see *Landing notes*). Draft history:
  promoted from seed 2026-10-14 on ADR 080
  (proposed the same day) and the memo it stands on; revised the same
  day with Clay's decisions (postures named by their rung; `add` as
  the own-only rung and `contribute` as edit-any, verified against
  SharePoint and Drive; delete-own by the floor; type-only edges at
  `list`; `mkedge`'s target at `list`; dense ranks; anonymous judged
  at the addressed path); **revised again the same day after a
  pre-build review** (`../../../research/studies/2026-10-14-permission-ladder/04-spec-165-review-before-build.md`:
  fifteen findings, three executed probes — the read leg's body leak,
  the anonymous gate's mechanism, the `rmedge` shape, the trashed
  hint, slice A's sequencing, the format door, the aliasing object,
  the occupied-creation leg, the road as an edge target, the full
  table, the missing tests). **Lands before spec 164** (Clay,
  2026-10-14). Not started. Three slices (A–C). The review's three
  product questions were answered by Clay the same day (a revive is a
  restore; no road for anonymous; `rmedge`'s hidden target takes the
  absent target's per-row record); no `[NEEDS CLARIFICATION]` remains.
- **Date:** 2026-10-14
- **Owner:** Clay Gendron
- **Kind:** feature (three rungs; posture words equal to the rungs;
  one declared verb-to-rung table; `Visibility.admits` answers a rung)
  and a schema format bump (the stored label renumbers; old mounts are
  re-provisioned).
- **Depends on:** ADR 080 (all twelve pins, as amended after the
  review); ADRs 062–074 as built (`grants.py`, `rights.py`,
  `labels.py`, `ranges.py`, `reads.py`'s road, `descent.py`'s ladder);
  ADR 079 pin 2 (the graph walk reads its rung from the table).
- **Decisions it implements:** ADR 080. Resolves the 2026-10-07 ladder
  addendum. Closes the `rmedge` leak (ADR 080 pin 10).
- **Research it stands on:**
  `../../../research/2026-10-14-the-permission-ladder-list-and-contribute.md`
  and the studies under
  `../../../research/studies/2026-10-14-permission-ladder/`:
  `01-vfs-impact-map.md` (the file-by-file change list and the road
  baseline), `03-traversal-and-verbs-on-the-ladder.md` (the worked
  examples and executed baselines), and `04-spec-165-review-before-build.md`
  (the review this revision answers; its three probes are the first
  tests of slice B). Note: the memo and studies 01–03 describe one
  middle rung named `contribute` with `add`'s meaning; the ADR and
  this spec carry Clay's split.

## Intent

After this spec a caller can hold `list` on a prefix and see the names
and kinds beneath it without reading a body, a caller can hold `add`
on a prefix and create rows there while altering only its own, a
caller can hold `contribute` and also edit anyone's rows there without
trashing or moving them, every verb's rung is one entry in one table,
and a graph walk passes any node the caller holds `list` on. The road
of ADR 070 keeps every behaviour it has today and becomes a derived
`list`. Nothing changes for a caller who holds `read` or `read_write`
except that `rmedge` no longer reveals a hidden target.

## 1. The ladder, the words and the table (slice A)

Slice A lands the vocabulary with the tree green. The review found
that renumbering `LEVEL_RANK` alone turns every test that inserts a
raw label red and that one docs fence runs `posture("/", "private")`,
so slice A carries the test-support and docs constants with it.

- `grants.py`: `GrantLevel = Literal["none", "list", "read", "add",
  "contribute", "read_write"]`; `LEVEL_RANK` dense 0..5; `Posture`
  is the same `Literal` — a posture is named by the rung everyone
  holds — and `POSTURE_LEVELS` **goes**; its four readers
  (`rights.py` `set_posture` and `posture_row`, `engine.py`'s root
  row, `params.py`) take the word as the level. `open`, `shared`,
  `private` retire everywhere they are typed: the constructor defaults
  (`engine.py`, `backend.py`: `read_write`), `serve()`'s refusal, the
  how-to `share-a-folder-with-grants.md` line 31 (a docs fence
  `scripts/ci.sh` executes), the tests. The resolver's algebra is
  untouched. `Rung` is declared in `ops.py`, which imports nothing of
  vfs; `grants.py` imports it from there, so the drift test's
  `LEVEL_RANK` import has no cycle.
- `params.py`: `GRANTABLE_LEVELS` derived as the ladder minus `none`;
  `POSTURES` derived from the same `Literal`.
- `rows.py`: `SCHEMA_FORMAT_VERSION` bump; the label comment names six
  ranks. `engine.py`: an old-format mount is refused at first touch as
  today; **there is no repair door** — an old mount is re-provisioned,
  as every format bump before it (specs 143, 162; ADR 020 rule 2); the
  refusal text says so. `rebuild_labels` stays what it is, a tool the
  tests and a future operator verb may call.
- `ops.py`: `Rung`, `Needs(primary, create, traverse)`, and
  `VERB_RUNGS: Final[dict[Op, Needs]]` — the full table, one entry per
  `Op`:

  | Op | primary | create | traverse | note |
  |---|---|---|---|---|
  | `read` | `read` | — | — | |
  | `stat`, `ls`, `tree`, `glob` | `list` | — | — | fields by the row's own rung |
  | `grep`, `glean` | `read` | — | — | the readable set only |
  | `graph` | `read` | — | `list` | passes at `list`, returns contents at `read`; spec 164 |
  | `write` | `contribute` | `add` | — | a fresh name at `create`; an occupied row at `primary` or own; a tombstoned row per §2 |
  | `edit` | `contribute` | — | — | or own |
  | `mkdir` | `contribute` | `add` | — | an occupied name is judged at `create` by the row's rung, never `exists` |
  | `delete`, `restore` | `read_write` | — | — | or own, on the row and every row beneath |
  | `move` | `read_write` | `add` | — | source subtree at `primary` or own; destination parent at `create` |
  | `copy` | `read_write` | `add` | `read` | source subtree at `traverse`; destination at `create`; copies are the caller's |
  | `mkedge`, `rmedge` | `contribute` | — | `list` | source at `primary` or own; target at `traverse`; a road directory passes as a target |
  | `grant`, `revoke`, `posture` | `read_write` | — | — | until `manage` |
  | `grants` | `read` | — | — | own rows at `read`, every row at `read_write` (as `list_grants` does today); a `list` path answers `not_found` |
  | `run` | `read` | — | — | its own axis is parked; today it takes no write gate |
  | `sweep`, `add_member`, `remove_member` | `read_write` | — | — | developer plane |

  A drift test in `tests/test_ops.py` pins one entry per `Op` and the
  three invariants: a mutation never sits below `add`; a read never
  mints; creating is never harder than modifying.
- Test support and raw constants move here from slice C: the fifteen
  raw `everyone_level=2` inserts and the `{0, 1}` pins become
  `LEVEL_RANK[...]`; `_POSTURE_OF`, `grant_worlds`' level tuples,
  `test_grants.py`'s `posture_regions` and `need` literals take the six
  words. The new-rung *tests* stay in slice C.
- Docstrings for `grant` and `posture` in `base.py`, `session.py`,
  `protocol.py`, `backend.py` name the six rungs as both card levels
  and postures.

## 2. The storage half (slice B)

- **`Resolution`** becomes a mapping from rung to `Rights` with an
  `at(rung)` accessor. Aliasing shares the compiled pieces, never the
  `Rights` object: when no row and no pending posture sits at exactly
  rung L, `at(L)` is a `Rights` at level L built on the same `spans`,
  `owner_arms`, `roots`, `holes` and the same `ranges()` object as
  `at(L+1)` (the review showed an aliased object answers `admits`
  wrongly, because a `Rights` admits by its own level); `weight`
  counts a `ranges()` object once. `resolve_authority` compiles the
  rungs the verbs can need; the system actor holds everything at every
  rung.
- **`Visibility(resolution, need)`** holds the `list` and `read`
  compiles; `admits(mapping)` returns the rung the caller holds on the
  row (`Rights.admits` itself stays a bool); `narrow`, `entries` and
  `clauses` run at the view's need; the road probes (`_open_beneath`,
  `_owned_beneath`, `_existing_roots`) run at the `list` compile.
  `tombstones(rows, need)` takes the rung: the gate asks at `list`
  (an occupied path is judged), the descent ladder asks at `read`, so
  the trashed hint and its `deleted_at` ride only on a tombstone the
  caller may read, and a tombstoned `list` row answers a plain
  `not_found` on the live side. The public surface spec 164 consumes
  is: `need`, `admits → Rung`, `narrow` at need, `at(rung)`.
- **`WriteGate`** reads `Needs`. Every leg that passes a row it has
  seen compares the row's rung with its slot: the `read` leg refuses
  `denied(target)` when `admits(row) < needs.traverse` (the review's
  blocking finding: today the leg consults no compile, so `copy` from
  a `list` file would copy its body); the occupied-creation leg
  compares `admits(row) >= needs.create` (so `mkdir(exist_ok=True)`
  on a `list` directory is `permission_denied`, never `unchanged`);
  the occupied branch judges at `primary` with the owner floor riding
  (`contribute` for overwrite and edit, `read_write` for delete, move
  and restore); the creation leg judges a fresh name at `create`
  through `reaches` (no owner leg). The road refusal applies to legs
  needing more than `list`; a leg whose slot is `list` (an edge
  target) passes a road directory. `_grant_refusal` accepts every
  grantable rung. **A `write` at a tombstoned row is judged as
  `restore`** (`read_write` or own; Clay, 2026-10-14): a deleted
  row keeps its path name and its owner until a permanent delete
  clears the row, so a revive by anyone else is a restore of another's
  row, which `contribute` lacks.
- **The anonymous gate.** `posture_refusal` leaves `_resolution` (which
  sees no path) and moves into the gate and the view: for each target,
  the level the posture rows on its chain give everyone
  (`label_of(posture_rows(prefixes))`, one chunked read of rows the
  resolver already fetches — never the stored label, which lags during
  a relabel) is compared with the lowest rung the verb can need at
  that target: `create` on a fresh name, `traverse` on a source it only
  reads, `primary` otherwise. A pattern scope (`glob`, `grep`,
  `glean`) is judged at each pattern's literal prefix; `tree`, `ls`
  and `stat` at the path named; a two-path verb at each path; a batch
  per target (ADR 068 rule 6's per-target classification). So
  `posture("/", "none")` plus `posture("/scratch", "read_write")`
  admits an anonymous `write("/scratch/hello.txt")` and refuses one at
  `/notes.txt` as `unauthenticated`. **Anonymous never derives the
  road** (Clay, 2026-10-14): `ls("/")` under that setup answers
  `unauthenticated` for anonymous, judged at `/`, while a named nobody
  sees `/scratch` bare; the docs show `ls("/scratch")`. This is the
  Unix and Plan 9 answer for the `other` class: listing a directory
  needs read on it, and neither system shows a road to anyone (memo
  2026-09-28 §2–3; Plan 9 `open(5)`: a directory opens only for
  reading, and reading it is the listing). The road itself is the
  SharePoint and Drive precedent ADR 070 chose for named callers.
- **`backend.py`**: `_viewed(op, ...)` passes `VERB_RUNGS[op].primary`;
  `_gate` and `_resolution` default from the table; the eleven level
  literals go and a grep pin keeps them gone.
- **`rmedge`**: the target is checked at `list` per target before
  `_endpoint_ids`, never climbing the descent ladder (an ancestor name
  must not surface). A target the caller does not hold `list` on,
  hidden or absent alike, is folded into `rmedge_rows`' own per-row
  record exactly as an absent target is today (Clay, 2026-10-14):
  `not_found` at warning severity, `path` = the source, `target` = the
  target, `data = {edge_type, vfs.target}`, the message "no
  {edge_type} edge to the target"; the batch commits what it found.
  The review showed that a gate-shaped refusal beside today's warning
  shape would re-open the leak at the batch level.
- **`reads.py`**: `_screen`, `_children_by_parent`, `tree_rows`,
  `glob_rows`, `_point_rows` and `_visible_rows` project a row bare
  when `admits(row) < read`; `ROAD_FIELDS` becomes `LIST_FIELDS` with
  the old name kept as an alias; `read_rows` answers
  `permission_denied` on a `list` row; `glob`'s `max_count` and its
  truncation warning count `list` rows (they are visible); `grep`'s do
  not count them (they are never candidates).
- **`grep.py`, `glean.py`**: the post-filter, the candidates, the
  lexicon and the statistics run at the `read` view; a `list` row's
  body never enters `N`, `avg_dl`, `df` or `lexical_stats`. The
  nominators' candidate budget is **not** touched here: that is the
  open question "grep's candidate budget counts hidden candidates",
  which stays open with `list` named as a second kind of non-candidate.
- **`labels.py`**: docstring numbering; `rebuild_labels` loops the
  regions as today. **`trash.py`** and the trash view: a tombstoned
  `list` row shows bare, no `deleted_at`.
- **Edge rows**: an edge touching a `list` node carries `edge_type`
  and no weight or distance; `mkedge`'s target is at `list`.
- **Renderer**: the "not populated" note already fires on road rows;
  the docs show it beside a bare `ls`.

## 3. Tests, docs and the amendments (slice C)

Every acceptance criterion names its test here.

- **The road baseline** (criterion 2): port study 01 §9's world
  (`l1_road_baseline.py`: `/projects/alpha`, `/projects/beta`, `/pub`;
  `ann` holds `read` on one deep file) into `test_rights.py` as a pin;
  every line unchanged; a granted `list` on `/projects/beta` adds
  exactly the bare rows it names; `read` on a `list` file is
  `permission_denied`; `stat` on a hidden sibling stays `not_found`
  in the same shape as an absent name; `stat` on a tombstoned `list`
  row is a plain `not_found` with no `deleted_at`.
- **The verb matrices** (criterion 4), one row per entry of the table
  in §1, as a single named user, as a set of two, and as anonymous:
  under `add` create yes, overwrite/edit/delete/restore own yes,
  another's no; under `contribute` additionally overwrite and edit
  another's yes, trash/move/restore another's no; `copy` from a `list`
  file and from a `list` directory `permission_denied`; `mkdir` and
  `mkdir(exist_ok=True)` on a `list` directory `permission_denied`;
  `mkedge` to a `list` file passes and to a road directory passes;
  `grants` on a `list` path `not_found`; a `write` at another's
  tombstone refused at `contribute` and passing at `read_write` or
  own; the set holds a member's floor where every other
  member holds the rung by grant; anonymous creates under `add` and
  `contribute` postures and alters nothing, its own creations included.
- **The search verbs** (criterion 3): `glob` with `kind=` and `ext=`
  over `list` rows, bare; `tree` of a `list` directory lists only its
  `list`+ children; `grep` and `glean` return nothing from a `list`
  row and `glean`'s exported `lexical_stats` (`N`, `df`) exclude its
  body; `grep`'s truncation warning never counts a `list` row.
- **`rmedge`** (criterion 5): the review's `rmedge_leak.py` as a test —
  a hidden target and an absent target answer the identical per-row
  record, and a mixed batch commits the good edge in both cases.
- **The anonymous gate** (criterion 8): every verb shape of §2 under
  `posture("/", "none")` plus `posture("/scratch", "read_write")`:
  `write`, `mkdir`, `read`, `ls("/scratch")`, `ls("/")`, `tree("/")`,
  `glob("/scratch/**")`, `grep` scoped to `/scratch` and to `/`,
  `move` and `copy` across the boundary, a batch with one target on
  each side.
- **Aliasing** (criterion 9): `at("list").admits` passes a
  `list`-labelled row while `at("read")` refuses it, with and without
  a pending posture at `list`; `weight` counts shared pieces once.
- **The clause fan and the three-seek join** agree on `list` views;
  `tests/support/grant_worlds.py` and `oracles/grants.py` sweep the
  six rungs; `grants_contract.py` carries the `list`, `add` and
  `contribute` contract on both legs.
- **Docs**: `docs/reference/authority.md` and the share-a-folder
  how-to gain the three rungs and the six posture words (slice A
  already changed the one fence); the README's permission strings.
- **ADR status lines**: 065, 068, 070, 073, 074, 079 record the
  amendments; ADR 080 → accepted; `STATUS.md`; this spec's landing
  notes.

## Scope

In: everything above. Out: `manage` (parked); group ownership
(parked); an append verb; a `create`-only rung; `run`'s own axis;
`grep`'s nominator budget (its own open question); an in-place label
repair for old mounts (re-provision, as before); the graph verb itself
(spec 164, which reads `VERB_RUNGS["graph"]`).

## Acceptance criteria

1. `GrantLevel` has six rungs in the stated order; a posture takes
   exactly those six words and `open`/`shared`/`private` are refused
   at the gate; `VERB_RUNGS` has one entry per `Op` and the drift test
   passes.
2. The road baseline is unchanged line for line; a `list` grant adds
   bare rows only where it names them; `read` on a `list` row is
   `permission_denied`; a hidden sibling is `not_found` in the
   absent-name shape; a tombstoned `list` row is a plain `not_found`.
3. `grep` and `glean` never return, count or rank a `list` row and
   its body is absent from the exported statistics; `glob` returns it
   bare.
4. The verb matrices of §3 hold for a named user, a set and anonymous,
   including `copy` and `mkdir` on `list` rows and `mkedge` to a road
   directory.
5. `rmedge` on a hidden target answers the identical per-row record to
   an absent path, and a mixed batch behaves identically in both cases.
6. An old-format mount is refused at first touch with a message that
   says to re-provision; a fresh mount provisions at the new format.
7. Anonymous is judged at the addressed path for every verb shape of
   §2; under a `none` root with a `read_write` posture on `/scratch`,
   an anonymous write creates `/scratch/hello.txt` and one at
   `/notes.txt` is `unauthenticated`.
8. The aliasing tests of §3 pass.
9. `scripts/ci.sh` green at 100 % coverage after each slice; the four
   engine legs green before landing (`db_test`).

## Landing notes

Landed 2026-10-14, all three slices in one tree-green landing
(`uv run pytest`, `ruff check`, `ruff format --check`, `ty`, 100 %
coverage through `scripts/ci.sh`).

- **Slice A as specified**: `Rung`, `RUNGS`, `Needs` and `VERB_RUNGS`
  in `ops.py` (the drift test's three invariants in
  `tests/test_ops.py`); `GrantLevel = Rung`, dense `LEVEL_RANK`,
  `Posture = GrantLevel`, `GRANTABLE_LEVELS` in `grants.py`,
  `POSTURE_LEVELS` gone; `params.py` derives both choice sets; format
  23 in `rows.py`, the refusal text says re-provision; the constructor
  defaults are `read_write`; every raw rank and posture word in
  `tests/` and the one docs fence moved with it.
- **Slice B as specified**: `Resolution` is a mapping with
  `at(rung)`, compiled from `read_write` down and aliased through
  `Rights.at_level` (pieces shared, never the object); `weight`
  counts a shared tuple once. `Visibility(resolution, need)` carries
  the pushdown compile at the verb's rung and the `list` compile for
  the road, `admits → Rung`, `holds`/`shows`/`reads`, `tombstones(rows,
  need)`, `road=False` for anonymous. `WriteGate(resolution, needs,
  …, authority=)` compares every leg with its slot; a write at a
  tombstone is judged at `restore`'s rung; a road directory passes a
  `list` slot; `named()` serves `rmedge`. The anonymous check is
  `unauthenticated_at` / `unauthenticated_refusals`, called per target
  in the gate, per addressed path in `_viewed` (patterns through
  `addressed_by`, braces expanded first — an unexpanded brace prefix
  walked the ancestor chain forever, found at the build), and in the
  grant verbs. `rmedge_rows(unnamed=…)` folds a hidden target into the
  absent target's record. The listing verbs project through
  `_observe_for` (`bare_observation`; `LIST_FIELDS` with `ROAD_FIELDS`
  as an alias); `read_rows` answers `permission_denied` on a `list`
  row; `grep`/`glean` hold at the `read` view.
- **One rule added, flagged to Clay**: an overwrite or an edit keeps
  the row's owner (`writes.py`: `owner_id` left the clobber columns
  and is stamped at creation only). The tree stamped the last writer
  as owner on every overwrite — `test_overwrite_restamps_the_owner`
  and a sentence in `docs/explanation/ownership-and-attribution.md` —
  which would have let a `contribute` holder take any row in one
  write and trash it in the next. ADR 064 rule 5 and ADR 080's
  consequences record the extension; the test and the doc now pin the
  new rule.
- **Two spec sentences corrected by the build**: a named nobody under
  `posture("/", "none")` + `posture("/scratch", "read_write")` sees
  `/scratch` *whole* in `ls("/")` (the posture labels the directory
  row `read_write`), not bare; and a holder of `add` on a prefix may
  `mkdir(exist_ok=True)` at the prefix itself (the occupied-creation
  leg compares the `create` slot, which it holds) — the
  `permission_denied` of §2 is for `list` holders, as the matrix test
  pins.
- **Tests**: `tests/storage/database/test_ladder.py` (the road
  baseline pin, the matrices as a user, a set and anonymous, the
  search verbs, the `rmedge` record, the anonymous shapes, aliasing
  and weight); five ladder tests in `grants_contract.py` on both
  legs; the parity sweeps in `test_grants.py` and `test_rights.py`
  run every grantable rung; the recompile spies count the
  `read_write` compile (the one never aliased).
- **Docs**: the share-a-folder how-to (two new sections), the
  glossary (`Ladder`, `Posture`, `Grant`, `Unauthenticated`), the
  open-in-process explanation, the ownership explanation, the README
  banner line. ADR status lines 064, 065, 068, 070, 073, 074 and 079
  carry the amendments; ADR 080 is accepted.
- **Engine legs** (`db_test`, 2026-10-14, the four legs run
  concurrently against fresh containers): Postgres 342 passed;
  MariaDB 333 passed, 8 skipped (its declared capability skips);
  SQL Server 343 passed; Oracle 338 passed. No failures on any engine.
  The sqlite CI gate the same day: 4,055 passed at 100 % coverage,
  the docs fences green.
- **Found and fixed on the way**: the cache weight estimate could
  reuse a freed temporary tuple's id mid-count and undercount (the
  arm tuples are now held for the count); the recompile spies in the
  tests counted the `read` compile, which aliasing no longer always
  makes, and now count `read_write`.
