# 078 — `StagedEntry` persistence state: one named discriminator

- **Status:** proposed 2026-07-22. Not yet implemented.
- **Evidence:** `context/research/2026-07-22-persistence-state-precedent.md`
  — BSD `nameiop`, Plan 9 `namec` amode, Linux `i_state`/`d_is_negative`
  for the naming argument; SQLAlchemy's unit of work
  (`has_identity` + "row switch") and Postgres speculative insertion for
  the structural one. The note records that SQLAlchemy encodes this
  decision as a sentinel-plus-predicate, i.e. as evidence *against* the
  encoding chosen here as much as for it; the case for a one-of is
  argued below on our own terms.
- **No ADR:** this changes no contract, no schema, and no wire surface —
  it renames and re-shapes one in-memory field.

## Problem

`StagedEntry.created: bool` (`staging.py:44`) is read by every reviewer
as past tense — "this entry has been created" — while it means the
opposite: no row exists, so the **insert pass** must write it. Three
compounding defects:

1. **The stated meaning is not the true one.** "No row exists yet" is a
   plan-time belief that execution falsifies without the flag moving. In
   `_upsert_layer` (`writes.py:399-405`) a file create that clobbers a
   rival lands on an **existing** row, adopts the rival's `entry_id` and
   version, and keeps `created=True`. Only the catch-retry path flips it
   (`writes.py:474`). The invariant the field actually holds is *which
   execution pass writes this row's material columns* — the flip is a
   hand-off from the insert pass to the update pass, not a change in
   whether a row exists.
2. **The token collides with itself.** `Status = Literal["created",
   "updated", "unchanged"]` sits twenty lines above the field
   (`staging.py:34`) and is genuine past tense, surfacing as
   `Observation.status`. A catch-retry conversion is reported
   `status="created"` while carrying `created=False`; the existing test
   at `tests/test_backends_database.py:1168` asserts exactly that pair.
3. **Routing is split across two fields, one of which is data.**
   `_update_materials` re-partitions on `base_version is None`
   (`writes.py:508-509`, re-derived at `531` and `534`) — that is
   "converted vs ordinary update" wearing a sentinel disguise:

   | state | `created` | `base_version` | pass / arm |
   |---|---|---|---|
   | create | `True` | `None` | insert |
   | material update | `False` | `int` | update, guarded |
   | arbitration conversion | `False` | `None` | update, unguarded |
   | — | `True` | `int` | **representable, meaningless** |

The gain to claim here is precise: a one-of does **not** reduce the
count of representable-but-meaningless combinations — three states
crossed with `base_version ∈ {None, int}` admits more, not fewer. The
gain is that **routing stops reading `base_version` at all**, so the
field reverts to being pure data consumed by the guarded arm, and the
decision lives in one named place.

The canon supports naming the decision for its intent: BSD's `enum
nameiop { LOOKUP, CREATE, DELETE, RENAME }` and Plan 9's
`Acreate`/`Aremove` ("is to be created", "will be removed by caller").
It does **not** settle enum-vs-sentinel — SQLAlchemy, the closest
structural relative, uses `has_identity = bool(state.key)` plus a
separate `row_switch` marker for the same mid-flight conversion.

## Scope

Replace the boolean and the routing sentinel with a single named state
on `StagedEntry`:

```python
persistence: Literal["insert", "update", "absorb"]
```

The state names **which pass writes this row's material columns, and
under what guard**. `"absorb"` is the catch-retry conversion, named for
the code's own words at `writes.py:473` — "The rival's row absorbs our
write."

**Untouched:** the schema, the wire and result envelope, `Status` and
`Observation`, POSIX gate semantics, version rules, both arbitration
modes and their SQL, the two-budget chunking discipline, and the
memory backend (no staging exists there).

### Why not `"clobber"`

It would land a fresh collision inside the module it lives in, of the
same species as defect #2 above. `_CLOBBER_COLUMNS` (`writes.py:60`)
means "material columns any overwrite writes" and is consumed by the
upsert `DO UPDATE` arm (`:390`) *and* both update arms (`:510`);
`_upsert_layer` carries a local flag literally named `clobber` (`:384`)
for the `DO UPDATE` path — which pin 5 requires stay
`persistence="insert"`. A reader would find a variable named `clobber`
routing rows that are not in the `"clobber"` state. `"absorb"` has no
other use in the module.

## Pins

1. **The field (`staging.py`).** `created: bool` → `persistence:
   PersistenceState`, with `PersistenceState = Literal["insert",
   "update", "absorb"]` declared beside `Status` (`staging.py:34`) so
   the two vocabularies are visibly distinct. The field carries the one
   comment on that dataclass that earns its keep: that it names the
   execution pass, and that arbitration may rewrite it. The module
   docstring's phrase "the create/update discriminator"
   (`staging.py:14`) is re-worded to match.
2. **Staging sets the plan-time state.** `stage_create` → `"insert"`
   (`staging.py:255`); `stage_update` → `"update"` (`staging.py:295`).
   No staging path mints `"absorb"` — it is reachable only from
   execution.
3. **`_apply` partitions on the pass** (`writes.py:306`, `313`):
   `== "insert"` for creates, `!= "insert"` for updates. The ordering
   comment at `writes.py:311-312` is rewritten to say that arbitration
   may re-route a create to `"absorb"`, dropping its `(created=False)`
   parenthetical.
4. **Arbitration conversion** (`_resolve_rows`, `writes.py:472-476`)
   sets `persistence = "absorb"` alongside adopting the occupant's
   `entry_id`. The line `staged.base_version = None` is **deleted as
   dead**: the entry reached `_resolve_rows` from the creates layer, so
   `base_version` is already `None` from the dataclass default.
5. **The upsert clobber stays `"insert"`** — pinned because it is the
   counterintuitive case and the reason `"is_new"` was rejected. In
   `_upsert_layer` the insert statement itself performs the clobber via
   `ON CONFLICT DO UPDATE`, so no hand-off occurs and
   `_update_materials` must not see the entry. Postgres puts ON CONFLICT
   arbitration inside the INSERT executor node for the same reason
   (`nodeModifyTable.c:1131`, speculative insertion). The two
   arbitration modes therefore reach different states for the same
   user-visible event; the field is honest about this because it names
   the pass, not the world.
6. **`_update_materials` keys both arms on the state**
   (`writes.py:508-509`): guarded is `== "update"`, unguarded is
   `== "absorb"`. The two re-derivations follow — `writes.py:531`
   becomes `persistence == "update" and observed != staged.version`,
   `writes.py:534` becomes `elif staged.persistence == "absorb"`. The
   docstring's guarded/unguarded vocabulary stays valid and gains the
   state names.
7. **The neighbouring field comments go stale and must move with it.**
   `staging.py:52` (`# the update guard; None = unguarded (arbitration
   clobber)`) is false after this change — `None` no longer signals the
   unguarded arm, `persistence` does; it becomes a plain statement of
   what the guard holds. `staging.py:53` (`# ... clobbers learn theirs
   post-execution`) is ambiguous under the new vocabulary, since upsert
   clobbers learn their version via RETURNING while carrying
   `"insert"`; it is re-worded to name the states. No grep-based
   acceptance criterion catches a stale comment, hence the pin.
8. **Tests** (`tests/test_backends_database.py`). Constructor kwargs at
   `883, 1158, 1193, 1222, 1270, 1358` → `persistence="insert"`; the
   stale-guard construction at `1406` → `persistence="update"` (it
   carries `base_version=999_999`). Assertions at `1041, 1168-1169,
   1232, 1280` re-expressed against the new state. The clobber
   assertion at `1232` drops its `base_version is None` clause — that
   fact is now carried by the state name — and `1168`'s comment stays,
   since it is what makes pin 5's asymmetry legible.

## Explicitly out of scope

- **The material data clump.** The seven-field bundle (kind, content,
  content_hash, size_bytes, lines, ext, mime_type) threads through
  `put_file`, `stage_create`, `stage_update`, `refresh_material`, and
  reappears as `_material_values`/`_CLOBBER_COLUMNS`. A `Material`
  dataclass would collapse five signatures. Larger than this story and
  worth its own; noted here so it is not lost.
- **The read-back's version-equality inference** (`writes.py:531`) — a
  reachable torn-row defect on READ COMMITTED engines, recorded in
  `open-questions.md` and awaiting its own fix story. This story must
  leave the check untouched: its safety as a review object rests on
  behavior being bit-identical.
- **`entries.version` nullability** (`rows.py:287`) — see the caveat
  under acceptance criteria.

## Acceptance criteria

- `grep -rn "\.created\b" src/ tests/` returns nothing referring to
  `StagedEntry`; remaining hits are `created_at` / `created_by` / the
  `Status` string.
- No site outside the guarded arm's parameter construction reads
  `base_version is None`; the routing decision is read only off
  `persistence`.
- The state `("insert", base_version=int)` is unreachable: no
  constructor or assignment in `src/` produces it.
- Behavior is bit-identical — both arbitration modes, the guarded and
  unguarded update arms, and every `Observation.status` unchanged. The
  suite passes with no test's *expectations* edited, only its
  vocabulary (pin 8 touches kwargs and assertion spelling, never an
  expected value).
  - **Caveat:** this equivalence assumes `entries.version` is never
    NULL. The column is nullable at `rows.py:287`, and a committed row
    with a NULL version would make `stage_update` mint
    `base_version=None` — routed unguarded today, routed `"update"`
    after this change. No live writer produces NULL versions, so it is
    unreachable in practice; `nullable=False` is a latent fix that
    belongs to another story.
- `ruff` and `ty` at zero across `src/` and `tests/`.

## Ordering

One landing, no slices: pins 1-2 (staging) → pins 3-7 (writes and the
staging comments) → pin 8 (tests), then the full suite. The change is
mechanical once the state names exist; splitting it would leave the tree
red between steps. `plan.md` is written at execution time per house
convention.
