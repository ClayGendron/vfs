# A row a caller may read reports its owner, no row reports the entry's id, and an entry that names the id is refused

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. Every fact about the code was read or run on `dev` at `27f3d24d`, on the in-memory store, which is the database backend over a private in-process SQLite; the probes sit outside the repository. It is unit 181-2 of [the unit map](../2026-11-25-the-backlog-converted/units.md) and serves criterion 3 of roadmap story K9 at gate b. It is converted from section 3 of [spec 181](../../context/specifications/archive/181-the-public-surface-regrouped-by-kernel-group/spec.md), read with [the study of that spec](../2026-11-25-the-backlog-converted/studies/165-181/181-the-public-surface-regrouped-by-kernel-group.md) and [the reassessment against dev](../2026-11-25-the-backlog-converted/reassessment/history-and-surface.md), section 181-2. It rests on [the vid spec](../2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/spec.md), whose first landing it follows, and on roadmap decision D55. Three choices are taken and listed under Choices to confirm; none waits.

## The outcome wanted

A caller that reads, stats, lists, globs, greps, searches or walks a row it may read sees who owns it, as `Observation.owner_id`, by default and whenever it names `owner_id` in `columns=`. A caller that may only list a row sees its path and kind and no owner. No row carries the entry's database id, `entry_id`: a row says which entry at which version it is through its `vid`, which the vid spec gives every row that carries a version. Building an `Entry` that names `entry_id` fails at once with a message that names the key, so no write can carry one. `ls -l` in the shell has a real owner to print.

```python
row = (await fs.stat("/notes.md", authority=who)).one()
row.owner_id            # "alice", the subject that created the row; None for a row no one owns
"entry_id" in Observation.model_fields   # False
Entry(path="/a.md", content="x", entry_id="01J...")   # raises pydantic.ValidationError naming entry_id
```

## Builds on

- [The vid spec](../2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/spec.md), specified on `dev`; its first landing is built on the open branch `origin/every-row-carries-a-vid`, whose review stands at "lands", and is not merged. The shapes relied on, by decision number: decision 1, "Every row that carries a version carries a vid, and the storage mints it", with its reason that "the entry id is the one fact about a row that never leaves the storage", and "A bare row carries neither"; decision 4, which fills the vid on every read row and every mutation row and ignores a vid on a row handed back through `observations=`; decision 5, which adds `DERIVED_FIELDS` and the `entry_key` label to the select lists of `src/vfs/storage/backends/database/reads.py`. This unit lands after that first landing: both edit `reads.py`, and decision 1 here meets the identity half of K9 criterion 3 with the vid, which must be on rows first. The vid spec's landings 2 to 4 touch nothing here.
- The deletes spec, `agents/2026-11-24-a-deleted-row-gives-up-its-path/spec.md` on the open branch `origin/a-deleted-row-gives-up-its-path`, reviewed fit to build and not built. Its decision 5, "No write brings a deleted row back", ends the revive that made a delete then a write keep the old id; with no id on any row, this spec pins no id across that sequence and needs nothing of it. Its prior-art table holds the same rule as the vid spec: "No database id leaves the storage, by the models' rule."
- Roadmap decision D55, decided on 2026-11-15 and recorded as decision 6 of [the kernel rulings spec](../../context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md): a move keeps the moved file's identity. That ruling says which stored row a move keeps; it leaves "showing it on a row" to this conversion, and decision 1 here declines to show it.
- Built on `dev`: the owner a new row takes, `owner_for` (`src/vfs/authority.py:283`), and the router's refusal of an owner that names no one (`src/vfs/base.py:2479-2480`); the rights fields every judged read fetches (`RIGHTS_FIELDS`, `src/vfs/storage/backends/database/rights.py:152`); the per-row choice between a whole row and a bare one (`observe_for`, `reads.py:280-284`).
- Read by, and not yet built: [the executable-bit spec](../2026-11-22-a-file-carries-its-executable-bit/spec.md), decision 4, which has `ls -l` and `stat` print "the owner from `owner_id`, or `root` when there is none", and roadmap story F4, criterion 1, which has `ls -l` print `owner_id`; unit 167-8 of the map carries F4's program forms.

## Terms

- **Owner.** The value of `vfs_entries.owner_id`: one subject name or nothing, set when the row is created and never changed afterwards (`docs/explanation/ownership-and-attribution.md:15`).
- **Entry id.** The ULID in `vfs_entries.entry_id`, unique within a storage. In the vid spec's words it never leaves the storage.
- **Bare row.** A row that shows only `path` and `kind`: a row the caller holds `list` on, or a directory shown only because a row the caller may name lies beneath it.
- **Servable set.** `ENTRY_OBSERVATION_FIELDS`, the `Observation` fields a read may fetch from the entries table.
- **Judged read.** A read under a caller whose rights are checked row by row, so that each fetched row carries `owner_id` and `everyone_level` for the check.

## What the code does today

| Fact | How it is known |
|---|---|
| `Observation` has neither `owner_id` nor `entry_id` (`src/vfs/models/entry.py:450-475`). | Run. |
| The servable set is eleven names and holds neither (`reads.py:100-103`). A narrow projection keeps only the names in it (`reads.py:144`), so `ls(path="/d", columns={"owner_id", "kind"})` populates `{kind, path, version}` and reports no error. | Read and run. |
| A judged read already fetches `owner_id` on every row it judges: `mappings_by_path` appends `RIGHTS_FIELDS` to its select list (`reads.py:223-224`), and the listings, traverse, grep and search add them to the set they build their list from (`listings.py:187`, `:240`, `:490`, `:559`; `traverse.py:215`, `:296`; `FETCH_RIDE` at `scope.py:70`, used at `grep.py:580` and `scope.py:327`; `search.py:522`, `:610`). | Read. |
| With `owner_id` added to the servable set at run time, `stat`, `read`, `ls` and `tree` under a named caller select `vfs_entries.owner_id AS owner_id__1` beside `owner_id`; `glob` and `grep` select it once. The system actor's statements name it once. | Run. |
| The same widening adds no statement. After one warm call: as the system actor, `stat` 1, `read` 1, `ls` 2, `tree` 2, `glob` 1, `grep` 4; as a named caller, `stat` 3, `read` 3, `ls` 4, `tree` 4, `glob` 3, `grep` 6; equal with and without `owner_id`. | Run. |
| A bare row is built by `bare_observation` with the mask `{path, kind}` (`reads.py:980-982`), a road directory by `road_observation` (`reads.py:975-977`), and a bare node of `traverse` with `{path, kind}` plus `depth` (`traverse.py:572-580`). None reads a fetched field. | Read. |
| `Entry` declares no model config (`entry.py:71`; the frozen config at `entry.py:393` is `Match`'s), so pydantic drops an unknown key. `Entry(path="/a.md", content="x", entry_id="01ABC")` and `Entry.model_validate` of the same mapping, with a ULID or with `None` as the value, construct with no such attribute, and a `write` of that entry succeeds with status `created`. | Run. |
| The models keep database identifiers out by rule: "Database identifiers never appear on these models" (`entry.py:25-26`), and an `Entry` carries neither the ids nor the version (`entry.py:82-86`). | Read. |
| Where VFS builds an `Entry` from caller input it maps `ValidationError` to `vfs.invalid` with `validation_message`: the single form of `write` (`base.py:1016-1019`) and the edit path (`src/vfs/storage/editing.py:44-48`). Neither takes a caller's mapping, so neither can carry `entry_id`. | Read. |
| A batch of entries is read once by the router, and an exception the iterable raises reaches the caller unchanged with nothing written (`base.py:986-988`, the docstring of `write`). | Read. |
| Mutation rows are built by hand from the plan, never through `Entry.to_observation`, which no module under `src/vfs` calls (`writes.py:488-501`, `trash.py:661`, `serialized.py:293-300`). | Read and searched. |
| The merge of two rows of one path fills a field by mask, left side first, and treats only `version` as a coordinate (`src/vfs/results/envelope.py:474-502`). | Read. |
| `OBSERVATION_FIELDS`, the projection vocabulary, is derived from the model (`src/vfs/results/projection.py:30`); the default text of `stat` is `path, kind, size_bytes, updated_at` (`projection.py:56`). | Read. |

## The problem

The owner of a row is stored on every row and shown on none. A caller cannot learn who owns a file without raw SQL, and the bulk-load guide says so: "Ownership is not yet exposed through a verb" (`docs/how-to/bulk-load-as-the-system-actor.md:53`). The `add` rung lets a caller change only its own rows, so a caller that cannot see the owner cannot predict what it may do. The shell's `ls -l` and `stat` need the owner for their owner column, and today a request for it is dropped with no error.

An input that names `entry_id` is accepted in silence. A pipeline that builds entries from rows it exported, or a caller that believes the id pins a file, writes by path and is told nothing. Roadmap K9 criterion 3 asks that such a write be invalid.

Two rules on record disagree on whether a row shows `entry_id`. K9 criterion 3 reads "`stat` and `ls` rows carry `entry_id`", and the roadmap's non-goal line (`context/standards/roadmap.md:51`) has `entry_id` appear on `stat` as a readable identity. The vid spec, written after them and ruled on 2026-11-23 in its own choices, keeps the id inside the storage and gives every row a `vid` in its place, and the deletes spec builds on the same rule. The consumer that wanted the id, the session stamp of story K10, now rides the vid (the vid spec, "Earlier decisions this reverses"). A build would otherwise have to pick a side.

At the reference deployment the owner rides on reads, about three verb calls in four of 150,000 a day, so it must cost no statement and nothing in proportion to the corpus.

## Decisions

### 1. No row carries `entry_id`, and the identity half of K9 criterion 3 is the vid

`Observation` gains no `entry_id` field, the servable set does not name it, and no mutation row carries it. A row that carries a version carries a `vid`, by the vid spec's decision 1, and two rows are the same entry at the same version exactly when their vids are equal. The build rewords the roadmap lines that promise the id on a row (under What the docs must say).

Reason: the models keep database identifiers out by rule (`entry.py:25-26`), the constitution's Article 3 rejects raw inode exposure (`context/standards/constitution.md:100`), and the two newest specs on the same rows, the vid spec and the deletes spec, rest on the id never leaving the storage. A field added later is additive; a field removed after the surface freezes is not. Precedent: the vid spec's decision 1 and its row "Plan 9 shows the whole qid ... The entry id, which is the qid's path, never leaves the storage" under "Prior art, and where this spec departs". This departs from K9 criterion 3 as worded and from section 3.1 of the source spec; it is choice 1.

### 2. `Observation` gains `owner_id: str | None = None`, an Entry-owned mirror, and `Entry.to_observation` projects it

The field sits directly before `created_at`, where `Entry` keeps it (`entry.py:121`). `Entry.owner_id` owns it, so `OBSERVATION_MIRROR_OWNERS` and `ENTRY_OWNED_MIRRORS` (`entry.py:545-549`) pick it up with no table edit, and the drift test `test_every_mirror_matches_its_owning_model_field_type` pins its type to `str | None`. `to_observation` passes `owner_id=self.owner_id`, as it passes every Entry-owned mirror; for an entry a caller authored that is the owner it declared, which the storage honours only for the system actor (`owner_for`).

Reason: one field, one owner, one partition, as the model already lays out every mirror. Precedent: section 3.3 of the source spec, still true at `27f3d24d`.

### 3. `owner_id` joins the servable set: it is in the default of `columns=None`, in a narrow projection only when named, and never always on

`ENTRY_OBSERVATION_FIELDS` gains `"owner_id"`. Every read that takes its fetched set from `effective_columns` then serves it: `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search` and the node rows of `traverse` (`reads.py:165`, `:184`, `:411`; `listings.py:107`, `:174`, `:233`; `grep.py:224`; `search.py:312`; the graph request at `backend.py:415`). `ALWAYS_ON_FIELDS` does not gain it, so a caller that asks for less does not carry it. A row of the trash view is built by the same functions and carries its owner like any row.

Reason: the owner is a column of the row like `size_bytes`, so it follows the column rule; the drift pin `test_entry_observation_fields_track_the_column_vocabulary` (`tests/storage/database/test_reads.py:279-283`) already requires that every `Observation` field the entries table backs is servable. Precedent: section 3.1 of the source spec.

### 4. The owner is shown at the `read` rung, and a bare row, a road directory, a bare node and a hidden row never show it

A row the caller reads comes back whole with whatever the fetched set names, `owner_id` included; a row the caller holds only `list` on, a road directory and a bare node of `traverse` keep their masks of `{path, kind}` and `{path, kind, depth}` whatever `columns=` names; a hidden row answers `not_found` as a missing one does. No code is added for this: the per-row choice already ignores the projection for a bare row (`reads.py:280-284`, `traverse.py:572-580`). `grep` and `search` return no row a caller may only list (`tests/support/grants_contract.py:1123-1141`).

Reason: POSIX `stat()` returns the owner to any caller that can reach the file, with no read permission on the file required; the `add` rung means "alter only one's own rows", so a reader needs the owner to predict its rights; and a judged read already fetches the column, so the stricter rule would add a rung check per row and a rights fetch at `read_write` on every judged listing, on the per-verb-call multiplier. Precedent: the source spec's section 3.4 lean, verified in the study's open choice 1; `docs/explanation/ownership-and-attribution.md:15`, which documents the column as a plain fact of the row. It is choice 2.

### 5. A row no one owns reports `owner_id` as `None`, with `owner_id` in its mask

A row written by the system actor with no declared owner, by a set of subjects, or by an anonymous caller stores no owner (`owner_for`, `authority.py:283-297`). Its row reports `None` and keeps `owner_id` in `populated`.

Reason: the mask says what was fetched, and a fetched null is a fact, "owned by no one", never "not asked" (the rule of Article 1.3, "A null field means not populated by this call", read through the mask). Precedent: `deleted_at`, served the same way.

### 6. A mutation row carries no `owner_id`

The rows of `write`, `edit`, `mkdir`, `delete`, `restore`, `move`, `copy` and `sweep` are unchanged by this spec.

Reason: a mutation takes no `columns=`; the owner is not in hand at every site, since a write that loses insert arbitration takes over a rival's row by its id and version alone and the snapshots of `delete`, `move` and `copy` do not select it; no consumer reads an owner off a mutation row; and a caller that wants it names it in a `stat`. Adding it later is additive. Precedent: section 3.1 of the source spec put only the id on mutation rows.

### 7. Edge rows and the answers of the grant verbs carry no owner

A `mkedge` or `rmedge` row and an edge row of `traverse` name two entries, so one owner on the row would be ambiguous (`traverse.py:583-593`). The `grants=` and `members=` answers are not observations.

Reason: the same as for the vid (the vid spec, decision 4, row "`mkedge`, `rmedge`, the grant verbs"). Precedent: section 3.1 of the source spec.

### 8. The judged point fetch selects each column once

`mappings_by_path` (`reads.py:203-229`) passes `fetched | {"deleted_at"} | RIGHTS_FIELDS` to `_entry_projection` when the read is judged, and appends nothing after it. Every other site already builds its select list from one set and needs no change.

Reason: once the servable set names `owner_id`, the appended rights columns repeat it, and SQLAlchemy labels the second copy `owner_id__1` (run, under What the code does today). Two copies cost a column per row for nothing and a reader of the mapping would depend on which copy wins. Precedent: the listings build `wanted = fetched | {"deleted_at"} | RIGHTS_FIELDS` (`listings.py:187`).

### 9. The merge of two rows keeps the owner by the mask, and at a mount point each verb reports the owner of the row that answered

`owner_id` is fillable state, not a coordinate: `Result._merge_observation` fills it from the right only where the left did not fetch it, as it does `size_bytes`. A mount point is two rows in two storages; `stat` of the mount point reports the mounted root's owner, and a listing of the parent reports the stored directory's, as each already reports its own version. The router issues no statement to reconcile them.

Reason: an owner names who made one row and says nothing of which snapshot the row is, so it cannot make a merged row claim a snapshot it is not; the coordinate rule belongs to `version` and, once the vid spec lands, to `vid` (its decision 4). Precedent: `envelope.py:474-502`.

### 10. The wire carries the owner where it is set, and no default text changes

`Result.to_payload` serializes the model, so it emits `owner_id` where set and omits a null under `exclude_none=True`; `from_payload` restores it, mask included. `OBSERVATION_FIELDS` is derived from the model, so `owner_id` becomes a valid projection name with no edit. The per-verb default projections are unchanged (`projection.py:49-61`); `all` shows the owner where a row's mask holds it.

Reason: a field added to the model reaches the wire and the renderer by derivation; changing a default text is the shell's and the renderer's own decision. Precedent: section 3.8 of the source spec.

### 11. `Entry` refuses a key `entry_id` at construction, by a named check on that key, and every other unknown key keeps today's treatment

A before-validator on `Entry` raises `ValueError` when the input is a mapping that holds the key `entry_id`, whatever its value, `None` included, so construction, `Entry.model_validate` and `Entry.model_validate_json` raise `pydantic.ValidationError`. The message is `entry_id is not an input: the id never leaves the storage, and an entry is named by its path (path='<path>')`. The key set is one private module constant, `_STORAGE_ONLY_KEYS = frozenset({"entry_id"})`, among the module constants of `src/vfs/models/entry.py`. `Entry` does not take `extra="forbid"`: `Entry(path="/a.md", content="x", flavour="y")` still constructs.

Reason: the check in the model covers every door at once, the router, a direct call on a storage, a session and a later wire adapter, and it is what `Entry` already does for every contradictory input (`_derive_identity`, `entry.py:150-209`, raises for content beside `kind="directory"` and for content at the root). A model-wide `extra="forbid"` would refuse every key a caller passes today and is not asked for. Precedent: the study's notes for the conversion, "a named check on the one key is the narrower form". It is choice 3.

### 12. Where VFS builds an `Entry` from caller input, the refusal is `vfs.invalid`, and no door on `dev` needs a change for it

Every place that catches the model's `ValidationError` already answers `vfs.invalid` with `validation_message` (`base.py:1016-1019`, `editing.py:44-48`). A caller that builds its own entries for `write(entries=)` meets the refusal on the line that built the entry, before any call; inside a generator, the exception reaches the caller through the router with nothing written (`base.py:986-988`). A door that later builds an `Entry` from a caller's mapping, as the wire adapter of unit 171-1 will, follows the same pattern.

Reason: no `Entry` can carry the key, so K9's "a `write` of an `Entry` carrying `entry_id` is `vfs.invalid`" is met one step earlier than worded, and a router gate for it would test a state the model makes unreachable. Precedent: the owner refusal, which sits at the router because an owner name is a valid model value (`base.py:2479-2480`), where `entry_id` is never one.

## Cost

Costed against the reference deployment in AGENTS.md, on SQLite and Postgres, the engines `dev` serves.

- **Per verb call, about 150,000 a day, three in four of them reads.** No statement, no round trip and no bind is added (run: the counts under What the code does today are equal with and without the column). A judged read already fetches `owner_id` on every row it judges, so it adds only the field on the `Observation`. A read without a view, the system actor's or one on an open mount, adds one `String(255)` column of a row it already reads; a subject name is short, and a null is omitted from the payload. The cost is in proportion to the rows a call returns, never to the corpus.
- **Per batch, 100 a night.** A `stat` or `read` of 10,000 paths fetches through `rows_by_path` in `ceil(n / membership_budget)` statements (`src/vfs/storage/backends/database/descent.py`); a select-list column binds nothing, so neither the chunk size nor the count changes, on either engine or on the generic floor. Writes are unchanged.
- **Per file write, about 1,050,000 a day.** Nothing. The model check of decision 11 is one key lookup in the input mapping for each `Entry` built.
- **Per index visit, about 11,000,000 a day.** Nothing. The index pass and the rebuild call neither `effective_columns` nor the servable set (searched: only `reads.py`, `listings.py`, `grep.py`, `search.py` and `backend.py` use them).
- **Per corpus.** Nothing: no column, no backfill, no format change; `SCHEMA_FORMAT_VERSION` stays.
- **Per lock.** None is taken and none is held longer; a read still waits on no writer.

The default select list was never covered by an index: it already names `content_hash`, `mime_type` and nine more columns (`reads.py:100-103`), so one more column of the same row adds no page read. The plan pins built from the servable set (`tests/support/plan_store.py:409`) referee that claim on the Postgres leg.

## Left as it is

- **`version`, `vid` and every other unknown key on an `Entry`.** They are still dropped in silence. No caller is known that believes either pins a file, and `if_version` and `if_vid` are the arguments that do. Refusing them later is one more name in `_STORAGE_ONLY_KEYS`.
- **`Edge`'s treatment of unknown keys.** It names two entries by path and has no identity of its own on any row.
- **The identity rows other stories read.** K5 criterion 1 names `data["dest"]["entry_id"]` (unit 177-1), story H4 records `(entry_id, version, content_hash)`, and F4 criterion 2 has a replacing move leave the moved file's `entry_id` at the destination (unit 167-7). Each unit restates its row without a public id: a storage-level test can read the column, and a public row has the vid.
- **The owner after a delete then a write at one path.** Today the write revives the deleted row and keeps its owner; under the deletes spec's decision 5 it makes a new row with the writer's owner. Nothing here pins either.
- **A verb that changes an owner.** None exists, and none is added.
- **What `ls -l` prints for a bare row.** A list-only row has no owner to show; the executable-bit spec's decision 4 and unit 167-8 decide the column.

## Tests

Each is written first and seen failing. Counts and states, never clocks. A row of `GrantsContract` or `StorageContract` is collected by `tests/storage/test_conformance.py` as `TestMemoryConformance`, `TestSqliteConformance` and `TestPostgresConformance`; the Postgres class runs where `VFS_TEST_POSTGRES_URL` is set, and the build runs it before its pull request, because every read select list changes.

`tests/models/test_models.py`:

- `TestConstructionValidation::test_an_entry_naming_entry_id_is_refused`: `Entry(path="/a.md", content="x", entry_id=v)` for `v` a 26-character ULID string and for `v` `None`, `Entry.model_validate` of the same mapping, and `Entry.model_validate_json` of the same object each raise `ValidationError`, and `validation_message` of it contains `entry_id`.
- `TestConstructionValidation::test_every_other_unknown_key_is_still_ignored`: `Entry(path="/a.md", content="x", flavour="y")` constructs, with `flavour` in neither its fields nor `model_fields_set`.
- `TestObservationMirrors::test_no_model_carries_an_entry_id`: `entry_id` is a field of none of `Observation`, `Entry`, `Edge`, `Version`, `Chunk` and `Match`.
- `TestEntryToObservation::test_projection_covers_every_entry_owned_mirror`, amended: its text entry is built with `owner_id="ann"`, so the new mirror is exercised. It fails first, because `to_observation` does not project the owner.

`tests/storage/database/test_reads.py`:

- `TestReadFamily::test_entry_observation_fields_track_the_column_vocabulary`, as it stands: it fails as soon as `Observation` gains the field and passes when the servable set names it.
- `TestReadFamily::test_owner_id_is_fetched_by_default_and_when_named`: over a row written by the system actor with the declared owner `carol`, and an edge to it, `read`, `stat`, `ls`, `tree`, `glob`, `grep`, `search` and the node rows of `traverse` each report `owner_id == "carol"` with `owner_id` in the mask under `columns=None` and under `columns={"owner_id"}`, and leave it out of the mask under `columns={"kind"}`; the edge row of `traverse` never holds it.
- `TestReadFamily::test_no_read_statement_names_a_column_twice`: the statements the same eight verbs issue, recorded by a `before_cursor_execute` listener under `columns=None` and `columns={"owner_id"}`, for the system actor and for a principal holding `read`, hold no select-list label ending `__1`. It fails first at `stat`, `read`, `ls` and `tree` under the principal.
- `TestReadFamily::test_the_owner_adds_no_statement`: for each of the eight verbs and both authorities, after one warm call, the statements under `columns=None` equal those under `columns={"kind"}`.
- `TestReadFamily::test_a_judged_stat_of_ten_thousand_paths_issues_the_same_chunks`, marked `slow`: a `stat` of 10,000 observations by a principal holding `read` issues the same number of statements under `columns=None` as under `columns={"kind"}`, and every row reports its owner.

`tests/support/grants_contract.py`, conformance rows:

- `GrantsContract::test_a_readable_row_reports_its_owner_to_every_reader`: a row created by a named principal reports that subject as `owner_id` to the system actor, to a principal holding `read`, and to anonymous under a `read` posture.
- `GrantsContract::test_a_bare_or_hidden_row_never_shows_its_owner`, the leak test: a principal holding only `list` gets `populated == {"path", "kind"}` from `stat`, `ls`, `tree` and `glob`, and `{"path", "kind", "depth"}` from a node of `traverse`, under `columns=None` and under `columns={"owner_id"}`; a road directory is the same; anonymous under a `list` posture is the same; `grep` and `search` return no such row; and a row hidden from the caller answers `not_found` with the message a missing path gets.

`tests/support/storage_contract.py`, conformance rows:

- `StorageContract::test_a_row_no_one_owns_reports_a_null_owner`: a row the system actor wrote with no declared owner reports `owner_id is None` with `owner_id` in the mask, and one written with the declared owner `carol` reports `carol`.
- `StorageContract::test_no_mutation_row_carries_an_owner`: the rows of `write`, `edit`, `mkdir`, `delete`, `restore`, `move` and `copy` hold no `owner_id` in their masks.

`tests/base/test_dispatch.py`:

- `test_a_write_whose_entries_name_entry_id_writes_nothing`: a generator that yields one lawful entry and then builds one naming `entry_id`, passed to `write(entries=)`, raises that `ValidationError` to the caller, and afterwards `stat` of the first entry's path is `not_found`.

`tests/results/test_results.py`:

- `TestWireContract::test_payload_round_trip_is_lossless`, as it stands, with `rich_result()` given `owner_id` on one row, so the round trip covers it.

## Scope

In: `src/vfs/models/entry.py` (the field, the projection, the check and the constant, the docstrings); `src/vfs/storage/backends/database/reads.py` (the servable set and `mappings_by_path`); `tests/lint/allowlist.py`, whose baseline for `reads.py` follows the count the build reaches; the tests above; the docs below.

Out, each with where it belongs:

- The vid and its rows, arguments and merge rule: the vid spec.
- The operation groups and the face order: [unit 181-1](../2026-11-25-every-routed-op-sits-in-one-group-and-every-face-lists-the-verbs-in-that-order/spec.md).
- `replace=` on `move` and `copy`, and the identity a replacing move keeps: [unit 167-7](../2026-11-25-move-and-copy-take-replace-and-a-move-keeps-the-moved-file/spec.md).
- `ls -l`, `stat` and their owner column in the shell: [unit 167-8](../2026-11-25-the-program-forms-set-e-and-the-never-table-answer-as-gnu-and-bash-do/spec.md) and the executable-bit spec.
- The tool schemas, the `columns` enum and the mapping of an `Entry` the adapter fails to build: [unit 171-1](../2026-11-25-the-wire-adapter-projects-a-result-to-mcp-blocks-within-budget/spec.md).
- The replayed `move`'s error data: [unit 177-1](../2026-11-25-every-mutating-verb-sent-twice-answers-as-a-pinned-replay-table-says/spec.md).
- A write at a deleted path, and `destroy`: the deletes spec.
- K9's other criteria: `run`, the groups, the frozen list and the battery's reorganisation, each its own unit.

## What the docs must say

- The `Observation` docstring, rendered on `documentation/reference/python-api/entry.md`: `owner_id` is the subject that created the row, or `None` when no one owns it; it is served at the `read` rung, by default and when named in `columns=`, and a bare row never carries it.
- The `Entry` docstring: an `entry_id` key refuses construction, because the id never leaves the storage and an entry is named by its path.
- `docs/how-to/bulk-load-as-the-system-actor.md:53`: the sentence that ownership is not exposed through a verb becomes "A `stat` of the row reports it as `owner_id`."
- `context/standards/roadmap.md`: K9 criterion 3 reads "`stat` and `ls` rows carry `owner_id` at the `read` rung and a `vid` wherever they carry a version; no row carries `entry_id`, and an `Entry` naming `entry_id` is refused as invalid input."; the non-goal line 51 has the id never leave the storage and a row's `vid` name an entry at a version, compared and never used as an address; the state row at line 129 reads "`owner_id` on rows, `OpGroup`"; and the list of what is not built at line 95 drops "`entry_id` on `stat`".
- `scripts/docs.sh check` runs, because docstrings under `src/vfs/` change.

## Earlier decisions this reverses

- Section 3 of [spec 181](../../context/specifications/archive/181-the-public-surface-regrouped-by-kernel-group/spec.md): `entry_id` on every read and mutation row, the third part of the field partition, the merge coordinate and the Article 3 deviation are not carried, by decision 1.
- Roadmap story K9, criterion 3, first half, and the non-goal line that has `entry_id` appear on `stat`: reworded as under What the docs must say.
- Decision 6 of the kernel rulings spec left showing the id to this conversion. It is not shown; the ruling's rule about which row a move keeps stands, and that spec is not edited.

## Not checked

- The Postgres leg was not run: no `VFS_TEST_POSTGRES_URL` was set. The duplicate label and the statement counts were run on SQLite in memory only.
- `search` and `traverse` were read, not run, for a duplicate column; both build their lists from one set.
- How many existing tests compare a whole default mask or a rendered `all` projection, and so gain `owner_id`.
- Whether `Entry.model_copy(update={"entry_id": ...})`, which skips validation, can place the key on an entry; no code under `src/vfs` reads such an attribute.
- The vid spec's landings 2 to 4 were not read for edits to `mappings_by_path` or the servable set; landing 1's diff leaves both as on `dev`.
- Whether the `docs/` tree is still published beside `documentation/`.
- The sibling unit specs named under Scope; some are not yet written.

## Choices to confirm

1. **Does a row show `entry_id`?** The options: (a) no row shows it, and K9 criterion 3's identity half is the vid; (b) `stat`, `ls` and every read and mutation row show it read-only, as the source spec's section 3 had it, under a numbered Article 3 deviation. The side taken is (a), because a field added after it is additive while a field removed after the freeze is not, and because the vid spec, ruled on 2026-11-23, and the deletes spec both rest on the id never leaving the storage. A ruling for (b) rewrites this spec before the build: the field, the third part of the partition, the merge coordinate and the deviation decision return.
2. **At which rung is the owner shown?** The options: (a) the `read` rung, as every other column; (b) only to a caller holding `read_write` on the row or owning it, as the `grants` verb discloses grant rows. The side taken is (a): it adds no code to the rights path, so moving to (b) later is one added check, while (b) now builds a rung check per row and a rights fetch at `read_write` on every judged listing that (a) would then delete; and no caller depends on either before the freeze. Precedent for (a): POSIX `stat()` and roadmap F4 criterion 1.
3. **Where is an `entry_id` input refused?** The options: (a) at construction of `Entry`, as `ValidationError`, mapped to `vfs.invalid` wherever VFS builds the entry; (b) the model keeps the key and the router's write gate answers a `Result` with `vfs.invalid`, the roadmap line as worded. The side taken is (a), because it covers a direct storage call that (b)'s gate would miss, it is what `Entry` does for every contradictory input, and a refusal at construction can later be loosened to one at the gate, while an entry that once constructed cannot later be made to raise without breaking its callers.

## One line

Every row a caller may read reports its owner as `owner_id`, a row it may only list reports none, no row reports the entry's database id because the vid names the entry, and an `Entry` that names `entry_id` fails to construct.
