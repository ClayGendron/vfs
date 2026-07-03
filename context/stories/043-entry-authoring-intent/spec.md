# 043 — Entry Authoring Honors Caller Intent: Content Is Never Silently Dropped

- **Status:** draft
- **Date:** 2026-07-03
- **Owner:** Clay Gendron
- **Kind:** fix (silent data loss at the entry-creation chokepoint) +
  hygiene (validator purity, docstring drift)
- **Depends on:** 031 (unified entry creation — `Entry` is the one
  authoring chokepoint this hardens), 032 (path gate — `parse_kind` is
  the heuristic being fenced)
- **Enables:** the `write` verb impl (the database backend will construct
  entries from `write(path, content)` — it must not inherit this hazard)

## Intent

Constructing an `Entry` with explicit content must never destroy that
content. Today it can:

```python
Entry(path="/notes/journal", content="hello world")
# → kind="directory", content=None        (verified at 06cf551; repro.py)
```

The chain: `_derive_identity` (`models2.py:189`) fills an omitted `kind`
from `parse_kind`'s extensionless heuristic — `journal` has no dot and is
not on the `EXTENSIONLESS_FILES` allowlist (`paths.py:48`), so it reads as
a directory — and then `_derive_and_measure` enforces "directories carry
no content" by nulling the field (`models2.py:244-245`). **The caller said
two things (`path`, `content`) and the model silently discarded one of
them based on a name heuristic.** No error, no signal; the entry
validates, persists, and the content is gone.

The rule this story pins: **explicit content is a statement of kind.** A
caller who passes real content has told us the object is content-bearing;
the heuristic exists only to classify paths *in the absence of* stronger
evidence. Conflicts between two *explicit* statements raise; a heuristic
never overrides an explicit statement.

## Why

- The heuristic is unfixable as a heuristic. `EXTENSIONLESS_FILES` is an
  allowlist of famous names — `TODO` is on it, `journal` is not, and no
  finite list makes agent-authored extensionless files safe. The fix is
  not a longer list; it is refusing to let the list outrank the caller.
- The `write` verb is next. `write(path, content)` at the router
  (`base2.py:1059`) will construct an `Entry` in the backend impl; if the
  impl forwards content and omits kind — the natural way to write it —
  every extensionless write silently becomes an empty directory. Pinning
  the contract now means the impl cannot be written wrong.
- Story 031 named `Entry` construction the *chokepoint* where dependent
  invariants are enforced. A chokepoint that destroys caller input on a
  guess is enforcing the wrong invariant.

## Design

### D1 — content forces `file` when kind is inferred

In `_derive_identity` (mode=before — the only place raw caller intent is
readable, per the `model_fields_set` contract in the class docstring):
when the caller supplies non-`None` `content` and no `kind`, derive
`kind="file"`, not `parse_kind(path)`. The path heuristic keeps deciding
for content-free constructions (`ls`-style synthesis, directory rows,
hydration paths that always pass `kind` explicitly anyway).

### D2 — explicit content-free kind + explicit content raises

`Entry(path=..., kind="directory", content="...")` — two explicit,
contradictory statements — raises `ValueError` naming both, instead of
today's silent null. Same for `tool` and `skill`. The check reads the raw
dict in `_derive_identity` (before injection muddies `model_fields_set`);
the silent-null branch in `_derive_and_measure` (`models2.py:244-245`)
then only ever fires on `content=None`/omitted — it becomes normalization
of absence, never destruction of presence.

Hydration is unaffected: the repository stores `content=None` for
directories, so rows re-validate clean. `with_content` already raises on
content-free kinds (`models2.py:342-344`) — D2 makes construction agree
with it.

The conflict *raises* rather than returning a classified rejection, and
that is settled: `Entry` is in-process authoring (story 031's
chokepoint), not the router boundary — the values-in/`Result`-out rule
(037) governs verbs, and the router maps constructor `ValueError`s at
its own seam.

### D3 — validators do not mutate the caller's mapping

`_derive_identity` writes into the dict it receives (`models2.py:207-212`),
so `Entry.model_validate(d)` mutates `d` — verified: after the call the
caller's dict has grown `kind` and `name` keys. Copy before injecting
(`data = dict(data)`). Pure hygiene; no behavior change for `Entry(**kw)`
callers.

### D4 — module docstring drift

`models2.py:10` advertises `plan_file_write` and `set_version`; neither
exists (the real surface is `chunk`, `with_content`, `with_version`,
`create_version_row`, `to_observation`, version reconstruction). Fix the
list — the docstring is the module's contract statement and it currently
names phantom methods.

## Out of scope

- Changing `parse_kind` or the `EXTENSIONLESS_FILES` list — the heuristic
  stays as-is for content-free classification; this story only fences its
  authority.
- The `write` verb impl itself — it lands with the database backend
  story; this story is what makes its natural implementation correct.
- Any change to `Observation` (read-side rows carry whatever the backend
  returns; no inference runs there).

## Test plan

1. **Regression pin (the repro):** `Entry(path="/notes/journal",
   content="hello world")` → `kind == "file"`, content intact, metrics
   measured from it.
2. **Heuristic still owns absence:** `Entry(path="/notes/journal")` →
   `kind == "directory"`, content `None`; `Entry(path="/notes/todo")`
   (allowlisted name) → `file` — unchanged.
3. **Explicit conflict raises:** `kind="directory"` (and `tool`, `skill`)
   with non-`None` content → `ValueError` naming both fields; with
   `content=None` explicit → constructs clean (explicit absence is not a
   conflict).
4. **Explicit kind still wins over the path:** `Entry(path="/a/b.md",
   kind="directory")` stays a directory (no content in play — D1 must not
   widen into second-guessing explicit kinds).
5. **Caller mapping untouched:** `d = {"path": "/a/b.md"};
   Entry.model_validate(d)` leaves `d` with exactly one key.
6. **Chokepoint downstream:** an entry built as `write` will build it
   (path + content only) round-trips through `to_observation` with
   content intact — the shape the backend impl will rely on.

## Open questions

None — the raise-vs-classified question is settled in D2.
