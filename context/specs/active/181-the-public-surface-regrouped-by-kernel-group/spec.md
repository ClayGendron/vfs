# 181 — The public surface regrouped by kernel group: `entry_id` on `stat`, chaining onto `Result`, the facets named

- **Status:** draft — cut 2026-10-24 from ADR 087 (proposed the same
  day) and the two memos it stands on. Not started. Six open
  `[NEEDS CLARIFICATION]` markers (listed under *Open markers* at the
  end).
- **Date:** 2026-10-24
- **Owner:** Clay Gendron
- **Kind:** refactor (the public surface regrouped by kernel group in
  `ops.py`, `base.py`, `session.py`, `params.py`, the README and the
  docs; in-process chaining moved off `glob` and `grep` onto
  `Result.pipe` and a facet module), plus one feature: `entry_id` and
  `owner_id` become read-only, projectable columns on every row.
- **Depends on:** ADR 087. Spec 167 slice A (`run` and `SupportsRun`
  gone; `cli` and `bound` added as fronts). Spec 174 (`write(if_version=)`,
  the guarded write the derived `edit` and the shell's regex `sed -i`
  use). Spec 175 (written rows return `content_hash`; `entry_id` lands
  beside it). Spec 176 (the cursor; the resumption key on `Result`).
  Spec 179 (the storage seam as the kernel and the conformance suite
  organised by kernel operation; this spec adds rows to that suite, it
  does not reorganise it). Spec 171 (input schemas from `PARAMS`).
  **This spec lands last** in ADR 087's series: it is the regroup, not
  new behaviour, except `entry_id` and `owner_id` on rows.
- **Decisions it implements:** ADR 087 pins 1 (the kernel and its
  groups; the facets), 4 (`entry_id` read-only, never an address),
  5 (the trust tiers, stated in `base.py` and `docs/`), 12 (rows stay
  the one result type), 16 (flat names, a lean), 17 (replace keeps the
  destination's identity, a lean, carried as a rebase note for spec
  167); the first memo's step 7.
- **Research it stands on:**
  `../../../research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md`
  §4.2–§4.4 and §8 Q1/Q2;
  `../../../research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md`
  §2.9, §2.10, §5 step 10, §6 Q4; the studies
  `../../../research/studies/2026-10-24-ostep-principles-for-vfs/02-files-and-directories-the-api.md`
  (principle 1, the `struct stat` row map, principles 2, 5, 6,
  13–15), `08-virtualization-abstraction-gate-allocation-caching.md`
  (the trap-table map, principles 1, 2, 11, 20),
  `06-distribution-nfs-afs.md` (principle 6: `(path, version)` is not
  a safe cache key), and
  `../../../research/studies/2026-10-23-filesystem-shaped-api/05-vfs-surface-audit.md`
  (the 25 routed verbs; 36 filesystem-shaped slots against 89
  tool-shaped ones; the three cross-cutting channels; `observations=`
  already off the wire). New facts were gathered by four probes run
  with `uv run python` against `InMemoryStorage` at HEAD `ba77449`
  (the `entry_id` lifecycle; what each rung's `stat` row populates;
  statements for a 10,000-row plural; ULID decodes with `entry_id`
  simulated in the read columns). They are labelled **EXECUTED**
  below. Nothing was timed.

## Intent

After this spec, a reader of vfs's public surface sees the kernel. Every
routed verb sits in exactly one group: the filesystem core, the query
operations, the history operations, the rights operations, or the
derived verbs that are built from them. The groups are one list in
`ops.py`, and every surface that names verbs (the op literal, the rung
table, the parameter table, the router, the session, the README) lists
them in that one order, held by a drift test. The names stay flat:
`vfs.read`, `vfs.grep`, `vfs.grant`.

A caller can also see a file's permanent name. `stat` and `ls` (and
every row a read returns) can carry `entry_id`, the ULID the entries
row has always had. It survives a move and a restore. It is fresh for a
new file. No verb takes it as an address: rights and routing stay keyed
by path. In-process chaining moves off the kernel: `Result.pipe` feeds
a result's rows to the next verb, and the two rows-in-hand filters that
never reached storage leave `glob` and `grep` for a facet module.

## Terms used below

- **Kernel.** The gate and everything under it (ADR 087 pin 1): the
  router's half of the gate (parameters, capability, the reserved
  grammar, the permission maps) and storage's half (the caller's
  grants, judged inside each SQL statement).
- **Kernel group.** One of four kinds of kernel operation: filesystem
  core, query, history, rights.
- **Facet.** Anything built on top of kernel calls that stores no fact
  of its own. Two kinds: **fronts** (the MCP tool, the shell, the WASI
  mount, the `Session`) and **derived verbs** (`tree`, `edit`, and
  `rmdir`, which has no method).
- **Dispatch class.** How a verb is routed and gated today
  (`MUTATING_OPS`, `READ_OPS`, `GRANT_OPS`, `TWO_PATH_OPS`). It is a
  different axis from the group. `mkedge` is in the query group and is
  a mutation; `restore` is in the history group and is a mutation.
- **Plural form.** A verb's batch input: `entries=`, `moves=`,
  `copies=`, `edges=`, `edits=`, `observations=`. It is the 10,000-row
  ETL contract (ADR 087 pin 3). It stays.
- **Sugar form.** A singular input the gate folds into the plural
  before storage sees it: `path`+`content` into one `Entry`, `src`+
  `dest` into one pair, `old`+`new` into one `EditOperation`, the edge
  triple into one `Edge`.
- **`entry_id`.** The 26-character ULID on every entries row
  (`rows.py` L427). It is the inode number of the textbook: minted once
  at create, never reused, kept across a move (ADR 004 pin 1).
- **Trust tier.** Where the gate is a wall and where it is a
  convention (ADR 087 pin 5).

## 1. The 24 verbs, one group each

At HEAD there are 25 routed verbs (`ALL_OPS`, `ops.py` L103). Spec 167
slice A removes `run`. This spec groups the 24 that remain, and it
does not land before that slice: `run` has no group (it would be the
only verb that executes rather than reads or writes a stored fact, and
ADR 082 pin 12 already retires it). The table
is the whole public verb surface. "Kernel arguments" are the ones the
gate judges and storage receives (directly, or composed by the router
into what storage receives). "Sugar" is folded at the gate. "Front
machinery" is what a front adds and the kernel never sees.

`authority` is a kernel argument of every verb and is left out of the
table to save space.

### 1.1 Filesystem core (8)

| Verb | Dispatch class | Rung | Kernel arguments | Sugar | Front machinery (never in the kernel) |
|---|---|---|---|---|---|
| `stat` | read | `list` | `path`, `observations` (plural), `columns` | — | `ls -d`, `stat -c FMT`, `test -e` (shell) |
| `ls` | read | `list` | `path`, `observations`, `columns`; `after`, `limit` (spec 176) | — | `-a`/`-A` dot filtering, `-l` long format, `-t -S -r` sorts, `-F` markers (shell) |
| `read` | read | `read` | `path`, `observations`, `columns`; `range` (spec 178) | — | `cat -n`, line windows (`head`, `tail`, `sed -n`), the binary placeholder (render) |
| `write` | mutating | `contribute`, create `add` | `entries` (plural), `parents`; `if_version`, `if_absent`, `append` (spec 174; `overwrite` leaves with 174) | `path`+`content`/`data` → one `Entry` | `>`, `>>`, `touch` (shell); the staged buffer (WASI) |
| `mkdir` | mutating | `contribute`, create `add` | `path`, `parents`, `exist_ok` | — | `mkdir -p` = both flags (shell) |
| `delete` | mutating | `read_write` | `path`, `observations`, `cascade` | — | `rm -f` swallowing `not_found`; `rm`'s kind probe (shell); `rmdir` = `cascade=False` (§5) |
| `move` | mutating, two-path | `read_write`, create `add` | `moves` (plural pairs); `overwrite` (spec 167) | `src`+`dest` → one pair | `mv`'s `D/basename(S)` rule and `-n` (shell) |
| `copy` | mutating, two-path | `read_write`, create `add`, traverse `read` | `copies`; `overwrite` (spec 167) | `src`+`dest` → one pair | `cp -r` refusal of a bare directory (shell) |

### 1.2 Query (6)

| Verb | Dispatch class | Rung | Kernel arguments | Sugar | Front machinery |
|---|---|---|---|---|---|
| `glob` | read | `list` | `pattern`, `paths`, `ext`, `ext_not`, `globs_not`, `kind`, `max_count`, `columns`; `case_mode` (spec 167); `after`, `limit` (spec 176) | — | `find`'s predicate tree, `-print0` (shell); **the rows-in-hand filter leaves for `vfs.chain.glob` (§4)** |
| `grep` | read | `read` | see §6 | — | see §6; **the rows-in-hand filter leaves for `vfs.chain.grep` (§4)** |
| `glean` | read | `read` | `query`, `limit`, `paths`, `observations` (the candidate set; storage ranks within it), `ext`, `ext_not`, `globs`, `globs_not`, `columns` | — | `--limit --ext --glob --exclude` spellings (shell) |
| `graph` | read | `read`, traverse `list` | `method`, `path`, `observations` (seeds), `depth`, `edge_types`, `edge_types_not`, `minimal`, `limit`, `columns` | — | the tree drawing (render) |
| `mkedge` | mutating | `contribute`, traverse `list` | `edges`, `provenance` | `source`+`target`+`edge_type` → one `Edge` | the MCP adapter stamps `provenance` (spec 171) |
| `rmedge` | mutating | `contribute`, traverse `list` | `edges` | the same triple | — |

### 1.3 History (2)

| Verb | Dispatch class | Rung | Kernel arguments | Front machinery |
|---|---|---|---|---|
| `restore` | mutating | `read_write` | `path`, `observations` | `restore P` (shell) |
| `sweep` | mutating, developer plane | `read_write` | `path`; `limit` and a resumption key (spec 180) | none: no front registers it |

Spec 180's `versions(path)` read, when it lands, joins this group.

### 1.4 Rights (6)

| Verb | Dispatch class | Rung | Kernel arguments | Front machinery |
|---|---|---|---|---|
| `grant` | grant, write | `read_write` | `path`, `principal`, `level` | MCP tool only |
| `revoke` | grant, write | `read_write` | `path`, `principal` | MCP tool only |
| `grants` | grant, read | `read` | `path` | MCP tool only |
| `posture` | grant, write; developer plane | `read_write` | `path`, `posture` | none |
| `add_member` | grant, write; developer plane | `read_write` | `group`, `member`, `path` (picks the mount) | none |
| `remove_member` | grant, write; developer plane | `read_write` | `group`, `member`, `path` | none |

ADR 087 pin 1 names this group's last member `members`. In the code it
is two verbs, `add_member` and `remove_member`. This spec keeps the two
(the ADR amendment says so).

### 1.5 Derived verbs (2 routed, 1 without a method)

| Verb | Dispatch class | Rung | Kernel arguments | Its definition from kernel calls | Push-down |
|---|---|---|---|---|---|
| `tree` | read | `list` | `path`, `max_depth`, `columns`; the cursor (spec 176) | `ls` repeated, breadth by path order | storage's `tree` (one subtree select, `reads.py` `tree_rows`) |
| `edit` | mutating | `contribute` | `path`, `observations`, `edits` | `read` then `write(if_version=)` per file | storage's `edit` (match and replace inside one transaction) |
| `rmdir` | — | — | — | `delete(path, cascade=False)` | none needed |

§5 says what "derived" commits to.

### 1.6 What is not a verb

These public members of `VirtualFileSystem` are not ops and sit in no
kernel group:

- **Control plane (11):** `bind`, `unbind`, `add_mount`,
  `remove_mount`, `remount`, `close`, `mounts`, `locate`,
  `locate_edge`, `session`, `capabilities`. No dispatched verb can
  change a mount table (`base.py` module docstring; study 08
  principle 4).
- **Fronts (2, from spec 167):** `cli` (the meta-verb that parses a
  command into ops and re-enters through the public methods) and
  `bound` (the `Fs` capability a shell builtin holds).

EXECUTED: `VirtualFileSystem.__dict__` at HEAD holds 36 public
members in this order: the 11 control-plane members, then the 25
routed verbs. After spec 167 it holds 37 (the 24 verbs, `cli` and
`bound`, the 11 control-plane members).

## 2. `ops.py`: the groups, declared once

### 2.1 The new names

At the top of `ops.py`, under the `Op` literal:

```python
OpGroup = Literal["filesystem", "query", "history", "rights", "derived"]

OP_GROUPS: Final[dict[OpGroup, tuple[Op, ...]]] = {
    "filesystem": ("stat", "ls", "read", "write", "mkdir", "delete", "move", "copy"),
    "query": ("glob", "grep", "glean", "graph", "mkedge", "rmedge"),
    "history": ("restore", "sweep"),
    "rights": ("grant", "revoke", "grants", "posture", "add_member", "remove_member"),
    "derived": ("tree", "edit"),
}
"""Every op in exactly one group, in the one order every surface lists them.

The first four are the kernel's groups: what kind of stored fact an op
touches. The derived ops are facets built from kernel calls that a
backend may also answer natively.
"""

GROUP_OF: Final[dict[Op, OpGroup]] = {op: group for group, ops in OP_GROUPS.items() for op in ops}
SURFACE_ORDER: Final[tuple[Op, ...]] = tuple(op for ops in OP_GROUPS.values() for op in ops)

CONTROL_METHODS: Final[frozenset[str]] = frozenset(
    {"bind", "unbind", "add_mount", "remove_mount", "remount", "close",
     "mounts", "locate", "locate_edge", "session", "capabilities"},
)
FRONT_METHODS: Final[frozenset[str]] = frozenset({"cli", "bound"})
```

- `MANAGEMENT_METHODS` leaves `tests/test_ops.py` and becomes
  `CONTROL_METHODS | FRONT_METHODS` here, so "every public member is
  listed once" is a fact of `ops.py`, not of a test file.
- `RIGHTS_OPS` is not added: the rights group is exactly `GRANT_OPS`.
  The drift test pins `frozenset(OP_GROUPS["rights"]) == GRANT_OPS`
  instead of naming the same set twice.
- The `Op` literal is rewritten in `SURFACE_ORDER` order.
  `VERB_RUNGS` is rewritten in the same order.
- The module docstring gains one paragraph: there are two axes. The
  **group** says what kind of fact an op touches. The **dispatch
  class** says how the router routes and gates it. They are
  independent, and the docstring names `mkedge` and `restore` as the
  two examples.

### 2.2 The drift tests (`tests/test_ops.py`)

1. **Exactly one group.** `sorted(GROUP_OF) == sorted(ALL_OPS)` and
   `sum(len(ops) for ops in OP_GROUPS.values()) == len(ALL_OPS)`. The
   dict and the sum together say: every op is in a group, and none is
   in two.
2. **The public surface is fully listed.** Every public name in
   `VirtualFileSystem.__dict__` that is a function, coroutine function
   or property is in exactly one of `ALL_OPS`, `CONTROL_METHODS`,
   `FRONT_METHODS`. This replaces today's coroutine-only check
   (`test_router_public_verbs_are_exactly_the_registered_ops`), which
   missed the sync members `mounts`, `session` and `capabilities`.
3. **One order everywhere.** These five sequences are equal to
   `SURFACE_ORDER`: `get_args(Op)`; `list(VERB_RUNGS)`;
   `list(PARAMS)`; the routed verbs of `VirtualFileSystem.__dict__` in
   definition order; the verbs of `Session.__dict__` in definition
   order.
4. **The rights group is the grant class.**
   `frozenset(OP_GROUPS["rights"]) == GRANT_OPS`.

Rule (3) is what makes "regrouped" checkable. Without it, a later edit
could add a verb at the bottom of `base.py` and the groups would drift
back into the read/mutate/search shape they have today.

## 3. `entry_id` and `owner_id` on rows

### 3.1 What a caller gets

- `entry_id` is a projectable column, like `version` or
  `content_hash`. It is read-only: a value the kernel reports, never a
  value it accepts as an address (ADR 087 pin 4; study 02 principle 1).
- It rides on **every row a read builds from the entries table**:
  `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `glean`, and `graph`'s
  node rows. These all derive their columns through one function,
  `reads.py`'s `effective_columns`, so one change serves all eight.
- It also rides on **every mutation status row**: `write`, `edit`,
  `mkdir`, `delete`, `restore`, `move`, `copy`, `sweep`. The id is
  already in hand on each of those paths (§3.5), so it costs no
  statement and no decode. The reason is the one ADR 087 pin 9 gives
  for `content_hash` on written rows: a client should not need a
  second `stat` to learn what it just changed. Spec 177's
  recognisable `move` replay and spec 172's cache key both read it
  there.
- It never rides on: **edge rows** (`mkedge`, `rmedge`, `graph`'s edge
  rows; an edge row has two endpoints and one id would be ambiguous),
  **bare rows** (a row the caller holds only `list` on, or a directory
  shown only on the road: `path` and `kind`, nothing else, as today),
  and the grant answers (`grants=`, `members=`, which are not
  observations).
- `columns=None` means "every stat column" today
  (`effective_columns`, `reads.py` L124–L141). `entry_id` and
  `owner_id` join that default. A narrow `columns=` set includes them
  only when it names them. They are not always-on: `ALWAYS_ON_FIELDS`
  stays `{"path", "kind", "version"}`.

`owner_id` follows the same path, with one difference in who may see
it (§3.4).

### 3.2 What `entry_id` does over a file's life (EXECUTED)

Method: write, move, delete, restore, sweep and copy through
`VirtualFileSystem` over `InMemoryStorage` at HEAD `ba77449`, reading
`vfs_entries.entry_id` with a direct select after each step (no public
surface exposes it yet). Results:

| Sequence | `entry_id` after | Why |
|---|---|---|
| `write /a`, `move /a /b` | `/b` has `/a`'s id | a move rewrites only the path cache (ADR 004) |
| then `write /a` (a new file at the old path) | fresh | a new row |
| `write /c`, `delete /c`, `write /c` | **the same id** | a write onto a tombstone revives the row (ADR 074) |
| `write /u`, `delete /u`, `restore /u` | the same id | restore lifts the tombstone |
| `write /e`, `delete /e`, `sweep /e`, `write /e` | fresh | sweep destroyed the row; ids are never reused |
| `write /f`, `copy /f /g` | `/g` fresh, `/f` unchanged | a copy mints a new row |

So "fresh after a delete-then-create" is true only when a `sweep`
separates them. A plain delete-then-write revives the same file. ADR
004 pin 1 said a delete-then-recreate mints a fresh ULID; ADR 074
changed that when the trash became a tombstone on the row, and the
probe confirms the ADR 074 behaviour. The criteria below test the
behaviour as it is.

This is the exact case study 06 principle 6 names: `(path, version)`
repeats after a move-then-create or a sweep-then-create, with a
different body. `entry_id` does not repeat. A client cache keyed by
`entry_id` (or by `(path, version, content_hash)`) is safe; one keyed
by `(path, version)` is not.

### 3.3 The model (`models/entry.py`)

- `Observation` gains two fields:

  ```python
  path: Path
  entry_id: str | None = None
  kind: ObjectKind | None = None
  ...
  owner_id: str | None = None
  created_at: datetime | None = None
  ```

  `entry_id` sits right after `path` (identity first). `owner_id` sits
  before the timestamps, where `Entry` keeps it.
- `owner_id` is an ordinary **Entry-owned mirror**: `Entry.owner_id`
  (`entry.py` L108) owns it, so `OBSERVATION_MIRROR_OWNERS` and
  `ENTRY_OWNED_MIRRORS` pick it up with no new table entry, and
  `Entry.to_observation` projects it.
- `entry_id` has **no domain-model owner**. `Entry` never carries a
  database id, by design (`Entry` docstring: "path is the model's only
  identity"; `rows.py` keeps `entry_id` in `ENTRY_ROW_ONLY_COLUMNS`),
  and that stays true: a caller must not be able to author one. So the
  field partition gains a third part:

  ```python
  # Mirrors of an entries-row column no domain model carries: the
  # entry's permanent public name, reported and never authored.
  OBSERVATION_ROW_FIELDS: Final[frozenset[str]] = frozenset({"entry_id"})
  OBSERVATION_MIRROR_FIELDS: Final[frozenset[str]] = (
      frozenset(Observation.model_fields) - OBSERVATION_QUERY_FIELDS - OBSERVATION_ROW_FIELDS
  )
  ```

  `models/__init__.py` exports `OBSERVATION_ROW_FIELDS`.
- `entry.py`'s module docstring changes one sentence. Today: "Database
  identifiers never appear on these models." After: "The integer row
  locator never appears on these models, and `Entry` carries no id at
  all; `Observation.entry_id` reports the entry's permanent public
  name, read-only."
- The drift tests in `tests/models/test_models.py` change:
  - `test_partition_is_total_and_disjoint` becomes three-way:
    mirror ∪ query ∪ row = every field, pairwise disjoint.
  - A new test pins each row field to a column:
    `OBSERVATION_ROW_FIELDS <= ENTRY_ROW_ONLY_COLUMNS`, and
    `tables.entry.c.entry_id.type` is a `ULIDKey`, whose Python type
    is `str`, matching the field's inner type.
  - A new test: `"entry_id" not in Entry.model_fields`, and the same
    for `Edge`, `Version`, `Chunk`, `EditOperation` and
    `TwoPathOperation`. This is the model half of "never an address":
    no input model can carry it.
  - `test_projection_covers_every_entry_owned_mirror` gets an `Entry`
    with `owner_id="ann"` so the new mirror is exercised.
  - `test_non_entry_mirrors_stay_unpopulated` also asserts that
    `to_observation()` leaves `entry_id` unpopulated: an `Entry` has
    none to give.

### 3.4 Who sees `entry_id` and `owner_id`

- Both are row facts shown at the **`read` rung**, like every stat
  column today. The router's `_observe_for` (`reads.py` L922) already
  decides this per row: a row the caller reads comes back whole (with
  whatever `fetched` names); a row the caller holds only `list` on
  comes back bare. Nothing new is needed for `entry_id`.
- EXECUTED (HEAD): a `stat` as the system actor, as a principal
  holding a `read` grant, and as anonymous under a `read` posture all
  return the same eleven populated fields; a principal holding only
  `list` gets `{path, kind}`. After this spec the first three gain
  `entry_id` and `owner_id`; the `list` row stays `{path, kind}`.
- **`owner_id` is a principal's `sub`.** Showing it to every reader
  discloses who wrote a row. The `grants` verb is stricter today: a
  caller below `read_write` sees only its own, its groups' and the
  everyone rows (`base.py` `grants` docstring). This spec's lean is the
  `read` rung for `owner_id` too. Three reasons. Spec 167's `ls -l`
  already plans to print it (§4.1 of that spec), and today it prints
  nothing because the column is silently dropped (EXECUTED:
  `ls("/", columns={"owner_id", "kind"})` populates
  `{kind, path, version}`). The `add` rung means "alter only one's own
  rows", so a reader needs ownership to predict what it may do. And
  ownership is an authored fact about a row, while a grant row is a
  fact about another person's rights.
  `[NEEDS CLARIFICATION: owner_id at the read rung (the lean), or only
  where the caller holds read_write on the row or is its owner — the
  grants verb's disclosure rule. The stricter rule costs a second rung
  check per row in _observe_for and a rights fetch at read_write on
  every listing.]`

### 3.5 Storage: where the columns come from (`storage/backends/database/`)

All of it is columns inside statements that already run. No statement
is added anywhere.

- **`reads.py`.** `ENTRY_OBSERVATION_FIELDS` (L93) gains `"entry_id"`
  and `"owner_id"`. Through `effective_columns` this reaches every
  read builder, `grep.py` L214, `glean.py` L289 and the graph request
  in `backend.py` L441.
- **One duplicate-column fix.** `_entry_projection` (L900) prepends
  `entry.c.entry_id` when `with_entry_id=True`. When `fetched` also
  names `entry_id`, the column would appear twice. The function
  builds its list from `fetched | {"entry_id"}` instead, once. (The
  decode probe below shows the duplicate is real: two extra decodes
  per `ls`.)
  `_mappings_by_path` (L812) has the same shape for the rights fields:
  it appends `RIGHTS_FIELDS` (which holds `owner_id`) to a list that
  may already hold `owner_id`; it appends `RIGHTS_FIELDS - fetched`.
  `_children_by_parent` and `tree_rows` build `wanted` as a set union
  and need no change.
- **What a narrow projection hides.** `_observe` (L929) builds a row
  from `fetched` only. So `ls` still selects `entry_id` for its own
  use (it keys children by the target's id, L230), but a caller who
  did not ask for `entry_id` does not get it. That is today's
  behaviour for every internal column, kept.
- **Mutation rows.** Every site already holds the id:
  - `writes.py` `_finish` (L336–L356): staged rows carry
    `StagedEntry.entry_id` (minted for a create, copied for an
    update); unchanged rows read it from `plan.committed[path]`,
    whose snapshot selects it. Both branches pass
    `entry_id=` to the `Observation`.
  - `serialized.py` `PendingRow` (L91) gains `entry_id: str`.
    `topology.py` fills it from `src_row["entry_id"]` for a move and a
    rename-to-self (L171, L223); for a copy, `_execute_copy` (L440,
    which mints `id_map` in Python) returns `id_map[root_id]` and the
    caller passes it. `trash.py` L321 (restore) fills it from the
    fetched row, whose columns include `entry_id`. `observe_final`
    passes it. `final_rows` needs no new column.
  - `trash.py` `_observe_deleted` (L635) reads `row["entry_id"]`: its
    rows come from the snapshot or tombstone columns, which include it.
- **Cost, counted (EXECUTED).** Method: 1,000 files under `/big`,
  `ULID.from_bytes` wrapped with a counter, statements counted with a
  `before_cursor_execute` listener; the design simulated by widening
  `reads.ENTRY_OBSERVATION_FIELDS` at runtime (the model ignores the
  unknown key).

  | Call | HEAD decodes | Simulated decodes | Statements (both) |
  |---|---|---|---|
  | `stat("/big/f0001.md")` | 0 | 3 | 2 |
  | `ls("/big")` | 1,002 | 2,004 | 3 |
  | `glob("/big/*.md")` | 0 | 1,000 | 2 |

  Reading it. `ls` at HEAD decodes one `parent_id` per child plus the
  ids of `/big` and `/`, which the target fetch selects for its own
  use. The simulation's 2,004 is two more than one-per-row because of
  the duplicate column named above: the two target rows decode
  `entry_id` twice. With the fix it is 2,002. `stat` decodes 3, not 1:
  the point fetch returns the target and its ancestors in one
  statement (`_mappings_by_path`, so a miss classifies without a
  second query), and the column decodes on every row it returns. Those
  extra decodes grow with depth, never with batch size. No statement
  is added anywhere. On the mutation side the decode count does not
  change at all: every id is already a Python `str` in hand. The
  per-row cost is one decode and one 26-character string, linear and
  honest; spec 176's cursor bounds the rows per call, which bounds
  it. On the mutation side the decode count
  does not change either: every id is already a Python `str` in hand.
  The per-row cost is honest and linear; spec 176's cursor bounds the
  rows per call, which bounds it.

### 3.6 Read-only, proved four ways

"No verb accepts `entry_id`" is a contract with four doors, and each
door gets a test (§ *Acceptance criteria* 9 and 10):

1. **Parameters.** No `ParamSpec` in `PARAMS` is named `entry_id`. No
   parameter of any public method of `VirtualFileSystem`, `Session`,
   `vfs.chain`, `Result.pipe`, or any `Supports*` protocol method is
   named `entry_id`. (A projection *value* `columns={"entry_id"}` is
   allowed: it names a field to read.)
2. **Input models.** No input model has the field (§3.3).
3. **The wire.** Spec 171 builds every input schema from `PARAMS`. A
   test walks `input_schema(op)` for every agent-facing op and finds no
   property named `entry_id` at any depth. The `columns` enum will list
   `"entry_id"` as a value, which is correct.
4. **Inbound rows.** `observations=` takes `Observation` rows, and
   after this spec a row can carry an `entry_id`. The router and the
   seam address rows by `path` only (`targets_of`, `protocol.py`;
   `_dispatch_grouped_observations`, `base.py` L1750). A test forges
   one: `stat` and `delete` with
   `observations=[Observation(path="/a", entry_id=<the id of /b>)]`
   act on `/a`, and `/b` is untouched. The docstring of `_ONE_TARGET`'s
   verbs says so in one line: "rows are addressed by path; any other
   field on an inbound row is ignored."

### 3.7 The merge law gains one coordinate (`results/envelope.py`)

`Result._merge_observation` (L466) has an agree-or-null rule for
`version`: two rows at one path with different versions merge to
`version=None`, still masked, because a composite of two snapshots
claims no single one. `entry_id` is the same kind of coordinate, and
stronger: two rows at one path with different ids are two different
files. The rule extends to it:

```python
# Snapshot coordinates: two rows that disagree on one merge to null,
# because a composite of two files or two versions claims neither.
_COORDINATES: Final = ("version", "entry_id")
```

and the loop at the end of `_merge_observation` runs over
`_COORDINATES`. The law stays associative, commutative and idempotent.
A test pins `(a | b).one().entry_id is None` when the ids differ and
equals the id when they agree.

### 3.8 The wire

- `Result.to_payload` emits `entry_id` and `owner_id` wherever they
  are populated (`exclude_none=True` drops them elsewhere).
  `from_payload` reads them back; the round-trip test covers both.
- `projection.py` needs no edit: `OBSERVATION_FIELDS` is derived from
  the model. The default renders do not change: `stat` still renders
  `path, kind, size_bytes, updated_at`; `all` includes the two new
  fields when populated.

## 4. Chaining moves onto `Result`

### 4.1 Two meanings of `observations=` today

`observations=` means two different things, and only one of them is a
kernel argument.

1. **The plural of a row-addressed verb.** On `read`, `stat`, `ls`,
   `delete`, `restore`, `edit`, `graph` and `glean` the rows are the
   batch: the router groups them by mount and storage receives them
   (`SupportsRead.read(path | observations)`; `SupportsGlean.glean(...,
   observations, ...)`). This is the plural form of ADR 087 pin 3. It
   stays, as a kernel argument.
2. **A filter over rows in hand.** On `glob` and `grep` the rows never
   reach storage (ADR 034 decision 3). The router filters them in
   memory (`_glob_rows_in_hand`, `base.py` L1817;
   `_grep_rows_in_hand`, L1858), and it reaches storage only through
   its own public kernel calls (`self.stat(observations=…)` for a
   missing `kind`, `self.read(observations=…)` for missing content).
   That is a derived verb by ADR 087's own definition. It is facet
   machinery wearing a kernel argument's name.

ADR 034 made the same argument about the seam: "a contract that says
more than the router ever sends is drift by construction." This spec
applies it one level up.

### 4.2 The new shape

- **`Result.pipe`** (`results/envelope.py`, in the *Enrichment chains*
  group):

  ```python
  def pipe(self, step: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
      """Feed this result's rows to *step* as its ``observations=`` and return what it returns.

      In process only: the rows travel as Python objects and never cross
      a wire. *step* is a verb with a plural form, a ``Session`` verb, or
      a ``vfs.chain`` filter; awaiting the return value runs it.
      """
      return step(*args, observations=list(self.observations), **kwargs)
  ```

  `T` is a module-level `TypeVar` (the matrix runs Python 3.11, so no
  PEP 695 syntax). Passing `observations=` in `kwargs` as well raises
  Python's own `TypeError` for a repeated keyword; `pipe` adds no check
  of its own. An empty result pipes an empty plural, and every plural
  answers that with an empty, successful `Result` (EXECUTED at HEAD for
  `stat`, `read`, `delete` and `grep`). The precedent is pandas'
  `DataFrame.pipe`.
- **`src/vfs/chain.py`** (new, a facet module). It holds the two
  filters, moved from `base.py` with their behaviour unchanged:

  ```python
  async def glob(fs: VirtualFileSystem, pattern: str, *, observations: Sequence[Observation],
                 ext: tuple[str, ...] = (), ext_not: tuple[str, ...] = (),
                 globs_not: tuple[str, ...] = (), kind: ObjectKind | None = None,
                 max_count: int | None = None, authority: Authority | None = None) -> Result: ...

  async def grep(fs: VirtualFileSystem, pattern: str, *, observations: Sequence[Observation],
                 ext=(), ext_not=(), globs=(), globs_not=(), case_mode="sensitive",
                 fixed_strings=False, word_regexp=False, invert_match=False,
                 before_context=0, after_context=0, output_mode="lines",
                 max_count=None, columns=None, authority=None) -> Result: ...
  ```

  Each validates its shared flags with `vfs.params.param_violation`
  against the verb's own row (so the flag rules have one home), checks
  the rows are `Observation`s, and reaches storage only through
  `fs.stat` and `fs.read`, gated as the caller. `VirtualFileSystem` is
  imported under `TYPE_CHECKING` only; `base.py` never imports
  `chain.py`, so there is no cycle. `_observation_rows`, `_cap_rows`
  and `_hit_row` move with them where only the filters use them.
- **The kernel signatures shrink.** `VirtualFileSystem.glob` and
  `.grep`, `Session.glob` and `.grep`, and `PARAMS["glob"]` and
  `PARAMS["grep"]` lose `observations`. `RULES` loses the two
  `paths`-or-`observations` shape rules for `glob` and `grep`. `glean`
  keeps its `observations` (meaning 1) and its rule.
- **Usage.**

  ```python
  from vfs import chain

  found = await fs.glob("**/*.py", paths=("/src",))
  hits = await found.pipe(chain.grep, fs, "TODO")        # filter rows in hand
  fresh = await hits.pipe(fs.stat)                        # the kernel plural
  await hits.pipe(fs.delete, cascade=False)               # the kernel plural
  ```

- **Off the wire, as before.** Spec 171 withholds `observations` from
  every input schema; after this spec `glob` and `grep` have no such
  parameter to withhold. `Result.pipe` is a Python method; no schema
  ever names it. Spec 167's shell passes no rows on a pipe (its
  decision 1), so nothing in the shell changes.
- **The envelope docstring** example (L9–L12) becomes the `pipe` form
  above.

### 4.3 Boundedness at 10,000 rows

`pipe` adds no statement. It hands N rows to a plural that already
chunks: `_dispatch_grouped_observations` groups by mount, and the
storage read builders fetch through `rows_by_path`, chunked by
`membership_budget(profile, parameter_budget)` via `chunked()`.

EXECUTED at HEAD on SQLite (membership budget 32,668): a 10,000-row
`glob` result fed to `stat(observations=…)` issued one `SELECT`; fed
to `delete(observations=…)`, two `SELECT`s and two `UPDATE`s. Under a
profile narrowed to `in_list_budget=1000` (Oracle's floor, set the way
`tests/storage/database/test_graph.py` L265 sets it), the `stat` fetch
must issue ⌈10,002 / 1,000⌉ = 11 `SELECT`s for the 10,000 targets plus
their two ancestors. That count is a criterion.

### 4.4 The plural keeps its name

The plural of meaning 1 could also become a plain list of paths, so
that rows in a caller's hand were purely a facet concern and the kernel
took only strings. That would change seven verbs' signatures, the
seam's `path | observations` addressing (`protocol.py`) and every ETL
caller, for no change in what storage does. The lean keeps
`observations=` as the plural's name.
`[NEEDS CLARIFICATION: keep observations= as the row-addressed plural
of read, stat, ls, delete, restore, edit, graph and glean (the lean),
or replace it with a paths: Sequence[str] plural and let Result.pipe
map rows to paths.]`

## 5. The derived verbs as facets

ADR 087 pin 1 says `tree`, `edit` and `rmdir` are built from kernel
calls and store no fact of their own. Both routed ones also have a
storage push-down that is faster or safer than the composition, and
the push-down stays. "Derived" commits vfs to three things:

1. **A reference definition**, written once as a readable oracle in
   `tests/support/oracles/derived.py`:
   - `tree(fs, path, max_depth)` is `ls` repeated over each directory
     row, collected in path order, to `max_depth` levels.
   - `edit(fs, path, edits)` is `read(path, columns={"content",
     "version"})`, the edits applied in Python with the same
     replacement function storage uses (`vfs.storage.replace`), then
     `write(path=…, content=…, if_version=<the read's version>)`
     (spec 174).
   - `rmdir(fs, path)` is `delete(path, cascade=False)`.
2. **A parity test per verb** against the push-down. `tree` and the
   oracle return the same rows in the same order on a three-level
   fixture, at the system actor and at a named principal with a
   partial view. `edit` and the oracle return the same bodies,
   versions and statuses on the edit battery of the conformance
   suite. The oracle's guarded write, given a rival write staged
   between its read and its write, classifies spec 174's precondition
   kind; native `edit` has no such gap to test, because its match runs
   inside the transaction (ADR 087 pin 6; OSTEP study 07 executed it:
   20 rival appends through `edit` kept all 20).
3. **A front that does read-then-write uses the guarded write.** The
   one such front in flight is spec 167's regex `sed -i` (its §4.1:
   "`read(P)`, first-per-line replace, `write(P)`"), which today would
   lose a rival's change. It carries `if_version=` from its `read`
   (rebase note below). Spec 172's close-time write-back is the second;
   ADR 087 already rebases it.

No router fallback is added. Every shipped backend answers `tree` and
`edit` natively, and a synthesized fallback for a backend that does not
is spec 179's (it already owns the synthesized `tree` and `copy`). If
179 adds one for `edit`, it must be the oracle above, guarded.

The docstrings say this in one or two sentences each:

- `tree`: "Every row beneath *path*, as `ls` repeated would list them;
  storage answers it in one subtree read."
- `edit`: "A read then a guarded write, run by storage inside one
  transaction so no rival write lands between the match and the
  replace."
- `delete`: gains "With `cascade=False` this is `rmdir`: a non-empty
  directory refuses `not_empty`."

## 6. The flag split: `grep` and `glob`

ADR 087 pin 2 keeps the query verbs' flag tables on the kernel. The
reason is that the flags change *which rows match*, and matching runs
in storage against the index plus the dirty overlay, with the caller's
rights inside the statement. A flag that only changes how a match is
*printed*, or that a front can build from other kernel calls, belongs
to the front. The CLI front's facts come from spec 167 §4 and §4.1 and
the first memo's audit (study 05 §1, §5).

| `grep` input | Where it lives | Why |
|---|---|---|
| `pattern` | kernel | the match itself |
| `paths` | kernel | scope; composed into the `globs` channel per mount (ADR 031) |
| `ext`, `ext_not`, `globs`, `globs_not` | kernel | path gates inside the statement (`--include`/`--exclude` map here) |
| `case_mode` (`-i`), `fixed_strings` (`-F`), `word_regexp` (`-w`) | kernel | change the compiled verifier and the trigram plan |
| `invert_match` (`-v`) | kernel | changes the candidate plan (scan all) |
| `before_context` (`-B`), `after_context` (`-A`) | kernel | the regions a row carries |
| `output_mode` (`-l` files, `-c` count) | kernel | the row shape storage builds |
| `max_count` (`-m`) | kernel | per-file cap applied while matching |
| `allow_scan` | kernel | the index-tier opt-in storage judges; no CLI flag maps to it (study 05 §5) |
| `columns` | kernel | the select list |
| `-n` (line numbers) | CLI front | rows already carry line numbers in `Match`; printing them is rendering |
| `-h`, `-H`, `--color`, `rg --heading`/`--no-heading` | CLI front | rendering |
| `-r` | CLI front | vfs `grep` is always recursive under its operands; the front only refuses a bare directory without `-r` ("Is a directory") |
| several `-e` | CLI front | composed into one pattern, `(?:p1)\|(?:p2)` |
| BRE (default) vs `-E` | CLI front | the front translates BRE to the kernel's one regex dialect |
| `-C N` | CLI front | sugar for `-A N -B N` |
| `-L` | CLI front | the scope's files minus the `-l` set (two kernel calls) |
| `-o` | CLI front | re-matches the returned lines with the same verifier |
| `-q`, `-s` | CLI front | exit status and stderr only |
| `rg -t`/`-T` | CLI front | mapped to `ext`/`ext_not` |
| `-P` | neither | `unsupported` (spec 167) |
| `observations` | **leaves the kernel** | a filter over rows in hand; `vfs.chain.grep` (§4) |

`glob` splits the same way. Kernel: `pattern`, `paths`, `ext`,
`ext_not`, `globs_not`, `kind`, `max_count`, `columns`, and spec
167's `case_mode`. Front: `find`'s predicate tree (`-name`, `-type`,
`-size`, `-newer`, `-empty`, `-prune`, …) runs in the shell over
`glob("**", columns=…)` candidates; `-print0` is rendering. `kind=`
stays a kernel argument although `find -type` filters in the shell,
because the MCP surface uses it and storage filters it inside the
statement (`kind_membership`, `reads.py` L439). `observations` leaves
for `vfs.chain.glob`.

## 7. `base.py`, `session.py` and `params.py` regrouped

### 7.1 `base.py`'s module docstring

Two paragraphs are added after the current fourth paragraph ("Public
methods are routers: …"). No spec or ADR number appears in them.

```text
The kernel is the gate and everything under it. The gate has two
halves: this router judges parameters, capability, the reserved
grammar and the permission maps; storage judges the caller's grants
inside each statement. A front that skipped either half would skip
the gate. Under the gate sit four groups of operations, listed once
in ``vfs.ops.OP_GROUPS``: the filesystem core (stat, ls, read, write,
mkdir, delete, move, copy), the query operations (glob, grep, glean,
graph, mkedge, rmedge), the history operations (restore, sweep) and
the rights operations (grant, revoke, grants, posture, add_member,
remove_member). Everything else is a facet built from kernel calls
that stores no fact of its own: the derived verbs (tree is ls
repeated, edit is a read then a guarded write, rmdir is delete with
cascade=False), in-process chaining (``Result.pipe``, ``vfs.chain``),
the session, and the fronts (the MCP tool, the shell, the WASI mount).

The gate is a wall in two of three places. In process it is a
convention: any caller can construct the system authority or call a
storage object directly, and vfs trusts in-process code by design. On
the wire it is a wall: a token comes in, an ``Authority`` comes out,
and the caller can name nothing else. In the WebAssembly guest it is a
wall: the guest's only exits are the file calls and the host door, and
each is gated as the caller. ``entry_id`` is reported on rows and never
accepted as an address in any tier; rights and routing stay keyed by
path.
```

### 7.2 The method order and the banners

Inside `VirtualFileSystem`, after the control plane (unchanged, under
its existing `mount administration` banner):

| Banner (67 dashes, as today) | Methods, in order |
|---|---|
| `# kernel — filesystem core` | `stat`, `ls`, `read`, `write`, `mkdir`, `delete`, `move`, `copy` |
| `# kernel — query` | `glob`, `grep`, `glean`, `graph`, `mkedge`, `rmedge` |
| `# kernel — history` | `restore`, `sweep` |
| `# kernel — rights` | `grant`, `revoke`, `grants`, `posture`, `add_member`, `remove_member` |
| `# facets — derived verbs` | `tree`, `edit` |
| `# facets — fronts` | `cli`, `bound` (from spec 167) |

The private sections that follow (`dispatch shapes`, `hop budget`,
`resolution`, `gates`, `the funnel`, `settlement and merging`,
`errors`) are unchanged. The `public methods — execution` banner left
with `run` in spec 167.

Docstring additions, each one or two sentences:

- `move`: "The moved row keeps its `entry_id`, versions and edges, and
  takes on the rights of its new place: grants attach to path
  prefixes, so a move can change who may read a file." (study 02
  principle 2).
- `stat`: "Each row may carry `entry_id`, the entry's permanent name:
  the same across a move and a restore, fresh for a new file. It is
  reported, never accepted as an address."
- `tree`, `edit`, `delete`: §5.

### 7.3 `session.py` and `params.py`

- `Session`'s verbs are reordered into the same five groups with the
  same banners (`kernel — filesystem core`, …). `Session.glob` and
  `.grep` lose `observations`. The session's docstring line "every
  verb delegates into the router's ordinary funnel" stays; it gains
  "a session is a front: it curries one authority and adds nothing
  else."
- `PARAMS` is rewritten in `SURFACE_ORDER` order, with a one-line
  comment above each group (`# filesystem core`, …). The `RULES` and
  `VALUE_RULES` dicts keep their keys; their order follows too.

## 8. The README and the docs

### 8.1 README

The verb table under *The verb surface* (README L52–L63) becomes, in
full:

```markdown
| Group | Verbs | What they answer |
|---|---|---|
| Filesystem core | `stat` · `ls` · `read` · `write` · `mkdir` · `delete` · `move` · `copy` | path-keyed rows and bodies; `delete` is reversible through the trash |
| Query | `glob` · `grep` · `glean` · `graph` · `mkedge` · `rmedge` | *where it sits · what it says · what it means · how it connects*, and the typed edges between files |
| History | `restore` · `sweep` | bring a deleted entry back; destroy for good (operators only) |
| Rights | `grant` · `revoke` · `grants` · `posture` · `add_member` · `remove_member` | who may see and change what |
| Derived | `tree` · `edit` | built from the kernel: `ls` repeated; a read then a guarded write |
```

The sentence under it becomes: "The first four rows are the kernel:
every call passes one gate, and storage judges the caller's rights
inside each statement. The derived verbs are built from kernel calls.
Every verb takes paths, returns one `Result`, and names nothing by any
other key; each row can report its `entry_id`, the entry's permanent
name, which survives a move."

A test in `tests/test_ops.py` parses the README rows between the
header and the next blank line, maps the first cell through a title
table (`{"Filesystem core": "filesystem", "Query": "query", …}`), reads
the backticked names of the second cell, and asserts the result equals
`OP_GROUPS`: five rows, 24 verbs, each once, in order.

### 8.2 `docs/`

- **`docs/explanation/architecture.md`** is an empty stub today (eight
  lines, a heading). It gains the section "The kernel and its facets":
  the gate and its two halves, the four groups, the facets, and the
  three trust tiers of §7.1 in discursive form, with the alternatives
  ADR 087 weighed (a POSIX-shaped API; search as a program over `read`)
  and why they lost. It ends with "Further reading" links to ADR 087
  and `open-in-process-loud-at-the-edge.md`.
- **`docs/explanation/open-in-process-loud-at-the-edge.md`** gains one
  sentence in *Loud at the edge* pointing to the tiers.
- **`docs/reference/api.md`** gains, before *Identity*, a section
  *Surface* with the 24 verbs in five tables by group (signature, rung,
  dispatch class), the control-plane and front members, the row field
  `entry_id` (read-only; populated by every read row and mutation row;
  absent on bare and edge rows), the row field `owner_id`,
  `Result.pipe`, and `vfs.chain.glob` / `vfs.chain.grep`. Austere and
  complete, per the file's Diátaxis header.
- **`docs/reference/session.md`**'s verb list is rewritten in group
  order and drops `run` (if spec 167 has not already).
- **`docs/reference/glossary.md`** gains `entry_id`, *kernel*,
  *kernel group*, *facet*, *front*, *derived verb*, *trust tier*.
- Every fenced Python example in `docs/` and the README still runs:
  `scripts/ci.sh`'s docs step executes them. The examples that chain
  `grep(observations=…)` (EXECUTED grep: 31 single-line call sites, in
  `tests/base/test_grep_namespace.py`,
  `tests/base/test_glob_namespace.py`, `tests/base/test_dispatch.py`
  and the envelope docstring; none in `docs/` or the README) move to
  `pipe`.

## 9. Flat names, and what namespaces would cost (pin 16, lean)

The lean keeps every name flat: `vfs.read`, `vfs.grep`, `vfs.restore`,
`vfs.grant`. The groups live in `ops.py`, in the order of every
surface, in the docs and in the conformance suite, not in attribute
paths.

The alternative is namespaces: the core flat, and the rest as
`vfs.query.grep`, `vfs.history.restore`, `vfs.rights.grant`,
`vfs.derived.tree` (the first memo's Q1). What it would cost, measured:

- **Call sites.** EXECUTED: `grep -E "<receiver>.(glob|grep|glean|graph|mkedge|rmedge|restore|sweep|grant|revoke|grants|posture|add_member|remove_member|tree|edit)\("`
  over `src/`, `tests/`, `docs/` and the README finds 1,286 matches;
  857 have the receiver `storage` (the seam, which would not change);
  48 are in the frozen ranking corpus under `tests/fixtures/` (which
  must not change). That leaves about **381 router-level call sites**
  to rewrite.
- **Machinery.** Four namespace objects holding the router; the same
  four on `Session`; the drift tests walking attribute paths instead of
  `__dict__`; spec 171's handler resolving `getattr(getattr(fs,
  group), op)`; spec 167's `Fs` capability mirroring the namespaces.
- **What it buys.** Discoverability in an IDE. Nothing at the wire:
  MCP tool names are op names either way, and the shell spells verbs
  as programs.
- **What it costs readers.** Two spellings of one idea: a reader would
  learn that `read` is flat and `grep` is not, although both pass the
  same gate.

`[NEEDS CLARIFICATION: ADR 087 pin 16 — flat names with the groups as
documentation, ops.py's OP_GROUPS and surface order (the lean), or
kernel groups as namespaces (vfs.query.grep), about 381 call sites and
four namespace objects. Renaming delete and move (pin 3's question) is
independent of this choice and is not taken here.]`

## 10. Boundedness and the standing axes

ADR 087 pin 15's axes, scored for this spec's one behaviour change
(`entry_id` and `owner_id` on rows):

| Axis | Effect |
|---|---|
| Agent latency | no statement and no round trip added; one ULID decode per returned row, plus one per ancestor on a point read |
| ETL throughput | a 10,000-entry `write` issues the same statements (EXECUTED at HEAD: 35 on SQLite); its 10,000 rows each carry an id already in hand |
| Boundedness | no new statement, no new `IN` list; every list stays chunked by `membership_budget` through `chunked()` and `rows_by_path` |
| Correctness under rivals | unchanged; the merge law nulls a disagreeing id (§3.7) |
| Atomic unit | unchanged |
| Dialect reach | `ULIDKey` already decodes on every engine (native `uuid` on Postgres, `RAW(16)` on Oracle, `BINARY(16)` elsewhere); the engine legs prove it per criterion 18 |
| Protection | `entry_id` widens nothing: a bare row still shows only `path` and `kind`; `owner_id`'s disclosure is the open marker of §3.4 |
| Overhead above the engine | one decode and one 26-character string per row |

`Result.pipe` and `vfs.chain` add no statement (§4.3). The regroup
moves code and adds none to any hot path.

## Scope

**In:** `ops.py`'s groups, order and member lists; the order of `Op`,
`VERB_RUNGS`, `PARAMS`, the router and the session, with drift tests;
`entry_id` and `owner_id` on `Observation`, the read builders and the
mutation rows; the read-only tests; the merge law's second coordinate;
`Result.pipe`; `src/vfs/chain.py` and the removal of `observations`
from `glob` and `grep`; the derived-verb oracles and parity tests; the
docstrings of §5 and §7; the README table with its test; the docs of
§8; conformance rows for `entry_id` in spec 179's `stat` family.

**Out:** the conformance suite's reorganisation by kernel operation
(spec 179); the storage seam's `Supports*` rewrite and capability
declarations (179); a synthesized `edit`, `tree` or `copy` fallback
(179); the cursor (176), the ranged read (178), write preconditions
(174), integrity (175), replay (177), history and `pack` (180);
`move`/`copy` with `overwrite=` (spec 167 task 13, rebased below);
namespaces (§9's marker); any verb renamed (pin 3); `entry_id` as an
address anywhere.

## Acceptance criteria

Counts and states, never clocks. "Three authorities" means the system
actor, a named principal holding `read` on the row, and anonymous under
a `read` posture.

1. **`stat` reports `entry_id` at every authority.** On one file,
   `stat` at the three authorities returns one row each, with
   `entry_id` populated, 26 characters, and equal across the three.
2. **It is the entry's permanent name.** After `move(src, dest)`,
   `stat(dest).entry_id` equals the pre-move `stat(src).entry_id`.
   After `delete` then `restore`, and after `delete` then `write` at
   the same path (a revive), the id is unchanged.
3. **A new file gets a new name.** The id is fresh (differs from every
   earlier id in the test) after a move-away then a create at the old
   path, after `delete` + `sweep` + `write` at one path, and for a
   `copy`'s destination. Criteria 1–3 run as one probe in the shape of
   §3.2's EXECUTED table.
4. **A bare row carries no name.** A principal holding only `list` on
   a row gets `populated == {"path", "kind"}` from `stat`, `ls` and
   `tree`: no `entry_id`, no `owner_id`.
5. **`owner_id` is served.** `ls(P, columns={"owner_id", "kind"})`
   populates `owner_id` (at HEAD it is dropped). A row alice created
   reports `"alice"`; a system-actor row with no declared owner reports
   `None` with `owner_id` in the mask. (If §3.4's marker resolves to
   the stricter rule, this criterion gains: a reader below
   `read_write` who is not the owner gets no `owner_id` in the mask.)
6. **Every read row can carry it.** `read`, `stat`, `ls`, `tree`,
   `glob`, `grep`, `glean` and `graph` node rows each populate
   `entry_id` under `columns=None` and under `columns={"entry_id"}`,
   and none populates it under `columns={"kind"}`. Graph edge rows
   never carry it.
7. **Every mutation row carries it, for free.** The rows of `write`,
   `edit`, `mkdir`, `delete`, `restore`, `move`, `copy` and `sweep`
   carry `entry_id`; for each live row it equals a following `stat`'s.
   Each verb's statement count (a `before_cursor_execute` listener) is
   equal to HEAD's. `write(entries=…)` of 10,000 files returns 10,000
   distinct ids at HEAD's statement count.
8. **The read cost is counted.** `stat` and `ls` at the three
   authorities issue the same number of statements as at HEAD. Counted
   ULID decodes: `stat` of a file at depth 2, 3 (HEAD 0: the target
   and its two ancestors); `ls` of a directory with 1,000 children,
   2,002 (HEAD 1,002; 2,004 would mean the duplicate column is back);
   `glob` matching 1,000 files, 1,000 (HEAD 0).
9. **No door accepts it.** No `ParamSpec` in `PARAMS` is named
   `entry_id`. No parameter of any public method of
   `VirtualFileSystem` or `Session`, of `Result.pipe`, of
   `vfs.chain.glob`/`grep`, or of any `Supports*` protocol method is
   named `entry_id`. `Entry`, `Edge`, `Version`, `Chunk`,
   `EditOperation` and `TwoPathOperation` have no such field. For every
   agent-facing op, spec 171's `input_schema(op)` has no property named
   `entry_id` at any depth.
10. **A forged id is ignored.** `stat` and `delete` with
    `observations=[Observation(path="/a", entry_id=<id of /b>)]` act on
    `/a` only: one row, `/a`'s own id, and `/b` still live afterwards.
11. **The merge law.** `(a | b)` of two rows at one path with
    different `entry_id`s has `entry_id is None` with `entry_id` in the
    mask; with equal ids it keeps the id. The existing algebra laws
    (associative, commutative, idempotent) hold over rows that carry
    ids.
12. **One group each.** Every op is in exactly one `OP_GROUPS` group;
    the groups' union is `ALL_OPS` (24 ops); `OP_GROUPS["rights"]` as
    a set equals `GRANT_OPS`. Every public member of
    `VirtualFileSystem` is in exactly one of `ALL_OPS`,
    `CONTROL_METHODS`, `FRONT_METHODS`.
13. **One order.** `get_args(Op)`, `list(VERB_RUNGS)`, `list(PARAMS)`,
    the routed verbs of `VirtualFileSystem` in definition order, and
    the verbs of `Session` in definition order all equal
    `SURFACE_ORDER`.
14. **The README matches.** The README's verb table parses to
    `OP_GROUPS`: five rows, 24 verbs, each once, in order.
15. **Chaining moved, unchanged in effect.** `glob` and `grep` (router,
    session, `PARAMS`) have no `observations` parameter. Every test of
    ADR 034's chained behaviour passes through
    `result.pipe(chain.glob | chain.grep, fs, …)` with the same rows,
    order, masks and errors as HEAD's `observations=` form.
16. **`pipe` is one plural call.** `found.pipe(fs.stat)` on a
    10,000-row result makes exactly one call to `VirtualFileSystem.stat`
    (spied) with 10,000 rows, and returns 10,000 rows. Under a profile
    with `in_list_budget=1000` the fetch issues 11 `SELECT`s.
17. **Derived-verb parity.** `tree(P)` equals the oracle (`ls`
    repeated) row for row and in order on a three-level fixture, at the
    system actor and at a principal with a partial view. Native `edit`
    equals the oracle (`read` + `write(if_version=)`) on the
    conformance edit battery. The oracle, given a rival write staged
    between its read and its write, returns spec 174's precondition
    kind and leaves the rival's body. `delete(P, cascade=False)` on a
    non-empty directory returns `not_empty`.
18. **On every engine.** Criteria 1–3, 6 and 7 pass as conformance
    rows on SQLite, Postgres (the native-`uuid` decode), MariaDB, SQL
    Server and Oracle.
19. **Green.** `ruff check`, `ruff format --check` and `ty` are clean
    over `src/` and `tests/`, and `scripts/ci.sh` is green at 100%
    coverage after every task.

## ADR amendments this spec needs

- **ADR 087 pin 1.** "`members`" in the rights group means the two
  verbs `add_member` and `remove_member`. The derived verbs `tree` and
  `edit` are routed ops with a storage push-down; `rmdir` has no
  method and is `delete(cascade=False)`. The groups are declared once
  in `ops.py` (`OP_GROUPS`).
- **ADR 087 pin 4.** Add: `entry_id` rides every read row and every
  mutation status row, never an edge row or a bare row; the list rung
  does not see it. Add the correction of §3.2: a delete then a write
  at one path revives the same id (ADR 074); a fresh id needs a sweep
  between them, or a move away.
- **ADR 087 pin 16.** On Clay's answer: either "the groups are
  `ops.py`'s `OP_GROUPS` and the order of every surface, enforced by a
  drift test", or the namespaced shape.
- **ADR 087 pin 3.** On Clay's answer to the naming marker in the
  rebase note for spec 167: `overwrite=` (one word across `write`,
  `move` and `copy`) or `replace=` (the pin's word).
- **ADR 034.** The rows-in-hand filters leave `glob`'s and `grep`'s
  signatures for `vfs.chain.glob` and `vfs.chain.grep`, reached by
  `Result.pipe`. Their behaviour (decisions 1 and 2) is unchanged.
- **ADR 010.** `Result` gains `pipe`. The merge law's agree-or-null
  rule covers `entry_id` beside `version`.
- **ADR 004.** Pin 1's "delete-then-recreate at the same path mints a
  fresh ULID" is superseded by ADR 074's revive for a plain delete;
  it holds after a sweep. Add: the ULID is now reported on rows,
  read-only, as the ADR's "the public name is the ULID" foresaw.

## Rebase notes for specs 167, 171 and 172

### Spec 167

- **Task 13, `copy`/`move` with `overwrite=`, takes ADR 087 pin 17
  (lean): the destination's identity survives.** When
  `move(src, dest, overwrite=True)` lands on an occupant:
  - the destination row keeps its `entry_id`, its edges and its
    history; its body becomes the source's body, and the body it
    replaced is minted as a version (the version mint `write` already
    runs);
  - the source row is tombstoned at its own path, as a `delete` would
    (restorable; listed in `/.vfs/trash`);
  - edges keyed on the source's `entry_id` follow it into the trash
    and surface as dangling until it is restored or they are
    re-pointed;
  - the move's row reports the destination's `entry_id`.

  The reason, in one line: the atomic-save idiom (write a temp file,
  rename it over the real one) then keeps the file's identity, history
  and edges, which is what an editor and every `entry_id`-keyed cache
  want; POSIX's rule would give the real file a new identity on every
  save and dangle every edge pointing at it. POSIX's rule would also
  leave two rows claiming one `(parent_id, name)` under the tombstone
  law (ADR 074). `copy(overwrite=True)` is already this shape: a write
  of the source's body onto the destination row.
  A **directory over a directory** has no identity rule yet (POSIX
  replaces an empty one); task 13 refuses it `exists` until one is
  decided.
  Task 13 gains three tests that read `entry_id` (available once this
  spec lands; until then, a direct select as in §3.2): the
  destination's id is unchanged, `restore(src)` brings back the
  source's original id, and an edge from a third file to the source
  dangles and returns with the restore.
  `[NEEDS CLARIFICATION: ADR 087 pin 17 — the destination's identity
  survives a replace (the lean; spec 167's version mint), or the
  source's (POSIX's), with the destination tombstoned. Also: a
  directory replacing an empty directory, refused until decided.]`
- **The parameter's name.** Spec 167 spells it `overwrite=`, which
  matches `write(overwrite=)`. ADR 087 pin 3 spells it `replace=`,
  POSIX's word (`os.replace`, `RENAME_NOREPLACE`). One word should
  serve the whole filesystem core. The lean is `overwrite=`, because
  `write` already has it and changing `write` would touch every ETL
  caller. `[NEEDS CLARIFICATION: overwrite= on move and copy, matching
  write (the lean), or replace= as ADR 087 pin 3 words it, renaming
  write's flag too.]`
- **The regex `sed -i` form** (§4.1: "`read(P)`, first-per-line
  replace, `write(P)`") carries `if_version=` from its `read` (spec
  174), and on the precondition kind prints the GNU-shaped error with
  exit 4. The fixed-string form already maps to `edit` and needs
  nothing.
- **`ls -l`** gets a real `owner_id` once this spec lands (at HEAD the
  column is dropped). No change to 167's text.
- **No row passes on a pipe** (167 decision 1), so `vfs.chain` changes
  nothing in the shell. The README verb table that 167's task 20
  updates is this spec's table; whichever lands second rebases onto
  the other.

### Spec 171

- **`WITHHELD`.** The `observations` row of §1.1's table loses `glob`
  and `grep`: they no longer have the parameter.
- **`columns`.** The enum is `OBSERVATION_FIELDS`, so it gains
  `"entry_id"` and `"owner_id"` with no edit to 171's code.
- **`ResultPayload`.** Its row properties must equal `Observation`'s
  fields (171's drift test), so they gain `entry_id` and `owner_id`.
- **A drift test** asserts no input schema has a property named
  `entry_id` (this spec's criterion 9 names it; it lives with 171's
  schema tests).
- Tool names stay op names under the flat lean. Tool descriptions may
  open with the verb's group ("Query: …"); optional.

### Spec 172

- The staged-buffer cache keys by `entry_id`, not `(path, version)`
  (study 06 principle 6; §3.2's table shows the repeat). The open-time
  `read` asks for it in the same call:
  `read(path, columns={"content", "data", "version", "entry_id"})`.
  It costs no statement.
- The close-time write-back carries `if_version=` from that read (ADR
  087's consequence, restated here because the same read supplies
  both).

### Notes for the other specs in the series

- **174:** `edit`'s oracle and 167's regex `sed -i` need the guarded
  write on the single form; the derived `edit` over a plural would need
  a per-entry expected version on `entries=`. If 174 lands only the
  single form, the oracle loops per file, which is fine for a test
  oracle and is not shipped.
- **175:** written rows return `content_hash`; this spec adds
  `entry_id` beside it in the same constructors.
- **176:** the resumption key is a field of `Result` (pin 12, lean).
  `Result.pipe` forwards rows only, never the key: a piped call starts
  its own listing. `[NEEDS CLARIFICATION: ADR 087 pin 12 — the
  resumption key as a field of Result (the lean; pipe then ignores it)
  or a separate return value (pipe unchanged, but every verb's return
  type changes).]`
- **177:** a replayed `move` can name the occupant's `entry_id` in its
  error data, from the snapshot it already holds.
- **179:** this spec's conformance rows (criterion 18) go in 179's
  `stat` and mutation families. 179 owns any synthesized `edit`
  fallback, and must build it as §5's guarded oracle.

## Open markers (for `context/open-questions.md`)

1. §3.4 — `owner_id` at the `read` rung, or `read_write`-or-owner.
2. §4.4 — `observations=` keeps its name as the plural, or becomes a
   path list.
3. §9 — ADR 087 pin 16: flat names, or namespaces.
4. Rebase note 167 — ADR 087 pin 17: whose identity survives a
   replace; a directory over a directory.
5. Rebase note 167 — `overwrite=` or `replace=`.
6. Notes, 176 — ADR 087 pin 12: the resumption key on `Result`, or a
   separate return.

## Landing notes

(Filled in on landing.)
