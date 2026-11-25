# A bare `Authority(...)` built outside `vfs.authority` raises `TypeError` naming the doors, while `copy` and `pickle` round-trip

A draft, written on 2026-11-25 and checked against `dev` at `27f3d24d`. It is not reviewed, and nothing is built. It serves story I1 of [the roadmap](../../context/standards/roadmap.md), gate b, by its criterion 5 alone (`context/standards/roadmap.md:420`). It is converted from the door-token paragraph of [the archived spec 149](../../context/specifications/archive/149-serve-auth-token-to-authority/spec.md) (`spec.md:35`), the only part of that source this unit carries; the rest goes to the units named under Scope. It rests on [the study of the source](../2026-11-25-the-backlog-converted/studies/051-162/149-serve-auth-token-to-authority.md), on [the reassessment against dev](../2026-11-25-the-backlog-converted/reassessment/mcp-guests-and-identity.md), section 149-1, and on probes run on 2026-11-25 against a changed copy of `src/vfs/authority.py` in a scratch directory, cited as EXECUTED where they are used.

## The outcome wanted

A host, a test or a module of vfs that writes `Authority(...)`, `dataclasses.replace(authority, ...)` or, on Python 3.13 and later, `copy.replace(authority, ...)` gets a `TypeError` whose message names every door, whatever fields it passed. A forged `provenance="edge"` therefore never constructs, so the value means something once 149-2 mints it. A caller of `Authority.of`, `Authority.on_behalf_of`, `Authority.system` or `Authority.anonymous` sees no change: the same values, equal and hashable as before. An authority still survives `copy.copy`, `copy.deepcopy` and `pickle` unchanged, so a host can hand one to a worker process or keep one in a cache. The reference page for `Authority` shows the constructor ending `*, door: InitVar[object] = None` and says the constructor is not for callers.

## Builds on

- [Spec 070](../../context/specifications/archive/070-principal-scoped-sessions/spec.md), built on `dev`: the `Authority` type, its four doors and the construction-site text pin (`src/vfs/authority.py:118-189`; `tests/base/test_authority.py:336-349`).
- [The jobs spec](../2026-11-22-a-job-is-interrupted-and-resumed/spec.md), specified on `dev` and not built. Three of its shapes touch this unit. Its `vfs_jobs.caller` column holds "the caller's authority in full, as JSON", provenance and narrowing included (its section on the table, `spec.md:141`). The saved step is rebuilt "with the authority the `caller` column holds" (`spec.md:165`). Its decision 28 gives `Principal` a keyword-only `name` outside equality and gives `Authority.system` a `name=` argument (`spec.md:687`). Once the constructor is closed, that rebuild is a construction and needs a door; decisions 11 and 12 say what that door must be. Build order: neither waits for the other. Whichever lands second adds the other's piece, as decision 11 says.
- 149-2, [`authority_from_token`](../2026-11-25-a-verified-token-becomes-an-authority-at-the-edge-and-nowhere-else/spec.md), a unit of this conversion, not written. It depends on this unit: it passes the token from inside `vfs.authority` (decision 2) and adds its name to the tuple of doors (decision 4). Build order: this unit, then 149-2.

## Terms

- **Door.** A function in `src/vfs/authority.py` that returns an `Authority`. There are four on `dev`, all classmethods.
- **Door token.** One private object of that module, `_DOOR`, which a door passes to the constructor and nothing else holds by design.
- **Bare construction.** A call of the constructor that does not pass the token: `Authority(...)` written out, or the call `dataclasses.replace` or `copy.replace` makes.

## What the code does today

- `Authority` is a frozen, slotted dataclass of five fields, `subjects`, `actor`, `provenance`, `narrowing` and `source_identity`, with the constructor a dataclass generates (READ, `src/vfs/authority.py:118-131`). No `InitVar` or `KW_ONLY` is in the module (EXECUTED, `grep`).
- `__post_init__` checks six shape rules and raises `ValueError` on each; none can tell who called (READ, `src/vfs/authority.py:133-152`).
- The four doors call `cls(...)` at `:157`, `:173`, `:183` and `:189`. Three pass `provenance="constructed"` and one `"system"`; none passes `"edge"`, which the `Provenance` literal lists (READ, `:43`).
- A bare `Authority(subjects=frozenset({Principal('alice')}), actor=Principal('alice'), provenance='edge')` constructs, and so does `dataclasses.replace(Authority.of(Principal('bob')), provenance='edge')` (EXECUTED, on the unchanged module).
- Every version row stores the provenance of the authority that wrote it: the field at `src/vfs/models/version.py:110`, set at `:181` and at `src/vfs/storage/backends/database/versions.py:184`, into `vfs_versions.provenance` (READ, `src/vfs/models/rows.py:497`). A forged `edge` is a false line in stored history. The reassessment's `rows.py:573` is the `provenance` column of `vfs_edges`, an edge's origin, and is unrelated.
- The only bare constructions outside `authority.py` are `tests/test_authority.py:134` and `:136` (EXECUTED, `git grep -n "[^.A-Za-z_]Authority(" -- src tests scripts crates`). One shape they build, a user actor with `provenance="system"`, no door produces.
- The only guard is a text pin over `src/vfs` for a bare `Authority(` or a reserved-kind `Principal(` outside `authority.py` (READ, `tests/base/test_authority.py:336-349`). Its comment still says "The three classmethods and the edge factory" (`:337-339`). It cannot see a host's code or `dataclasses.replace`.
- vfs builds four authorities of its own, all at import and all through a door: `src/vfs/mounts.py:39`, `src/vfs/base.py:154`, `src/vfs/storage/backends/database/backend.py:108` and `src/vfs/authority.py:219`. No code in `src/` or `tests/` calls `replace` on an authority (EXECUTED, `git grep`).
- The name `door` in `src/` is a field of `ShareLock` (READ, `src/vfs/storage/backends/database/dialects.py:112`, used at `:419`), unrelated. `_DOOR` appears nowhere in `src`, `tests`, `crates` or `scripts` (EXECUTED).
- The module docstring names "the edge factory that turns a verified token into an authority", which does not exist (READ, `src/vfs/authority.py:18-19`). The test module's docstring and banner say "three construction doors" (READ, `tests/test_authority.py:1`, `:63`).
- The published explanation says "Python has no private constructor" and that a module-private token "is planned for the day the edge factory exists" (READ, `docs/explanation/identity-is-a-value.md:53`, `:59`); the glossary says "The bare constructor is not a door" (READ, `docs/reference/glossary.md:21`). `docs/**` still drives the deploy (READ, `.github/workflows/deploy-docs.yml:6-8`).

## The problem

Once 149-2 mints `edge`, the value is a claim that only the function that verified a token can make, and no check of the five fields can confirm who made it. While any caller can write `Authority(..., provenance="edge")`, every version row that says `edge` is worth no more than one that says `constructed`. At the reference deployment that is about 1,050,000 file writes a day, each a version row whose provenance an auditor reads, so a provenance anyone can forge corrupts the audit of the whole estate. The constructor has to refuse every caller but the doors before `edge` means anything. A second gap opens with the jobs spec: its rebuild of a stored caller is a construction too, and without a rule it would either stay a bare call, which this unit breaks, or grow a door outside the module, which the pin exists to prevent.

## Decisions

### 1. A construction that does not pass the door token raises `TypeError`, wherever the call is written.

The check is on the token, not on the caller's module, so it refuses a host, a test and a forgetful line inside `vfs.authority` alike; a door that forgets the token fails its first test. The roadmap says "outside `vfs.authority`"; this is the same rule, slightly stricter. It is a raise and not a classified `Result`, because no request can cause it: it is a mistake in the calling program, as the shape rules already are (`src/vfs/authority.py:20-22`). It departs from one landed line: `context/standards/how-we-code.md:24` says a constructor argument raises `ValueError`. The type here is `TypeError`, because the fault is the call itself and not a value out of range, and because roadmap I1 criterion 5 names it.

### 2. The token is a module-private `_DOOR: Final = object()`, passed through a keyword-only `InitVar` named `door` whose default is `None`.

An `InitVar` is a constructor parameter that is not a field, so the token is absent from `dataclasses.fields`, `repr`, equality, the hash, `__slots__` and pickled state (EXECUTED: `fields` and `__slots__` list the same five names). It is keyword-only by a `_: KW_ONLY` marker, so a sixth positional argument cannot land in it (EXECUTED: Python's own arity `TypeError`). The default `None` lets a bare call reach `__post_init__` and the message of decision 4; with no default Python would raise "missing 1 required keyword-only argument" and name no door. `None` is never the token, so `door=None` and `door=object()` are refused like no argument (EXECUTED). One artefact is accepted: `Authority.door` reads as the class default `None`; no instance stores a token (EXECUTED). `ruff check`, `ruff format --check` and `ty check` pass on the changed copy (EXECUTED). Precedent: the source's paragraph, "a module-private sentinel passed as an `InitVar` (`door`)".

### 3. The token is checked as the first statement of `__post_init__`, before the six shape rules.

A bare call with an illegal shape raises `TypeError`, never `ValueError` (EXECUTED). The caller's first mistake is calling the constructor, and the message that names the doors is the one that helps; a shape message would invite a second bare attempt with the shape corrected. A fixed order is also what lets one test hold criterion 5 whatever the fields are.

### 4. The message names every door, and the names come from one tuple, `_DOORS`.

`_DOORS: Final = ("Authority.of", "Authority.on_behalf_of", "Authority.system", "Authority.anonymous")`, and the message is `f"an Authority is built through a door, never by its constructor: {', '.join(_DOORS)}"`, built only on the failing path. One tuple, so a later door adds one entry and the message cannot fall behind the code. An entry is the name a caller writes: `Authority.<name>` for a classmethod, the bare function name for a module function such as 149-2's `authority_from_token`. Tests match on the type and on each door's name, never on the whole sentence. `_DOOR` and `_DOORS` sit under the "The authority" banner directly above the class, since a private constant lives beside what it supports (AGENTS.md, "File organization").

### 5. `dataclasses.replace` and `copy.replace` on an authority raise the same `TypeError` from every module, and this unit adds no door that changes one field.

Both call the constructor with the default for `door`, so each is a bare construction (EXECUTED on 3.11 to 3.14 for `dataclasses.replace`, with a change and with none; on 3.13 and 3.14 for `copy.replace`). Inside `vfs.authority` a door may write `dataclasses.replace(authority, ..., door=_DOOR)` (EXECUTED), which is how a door that derives one authority from another is written. No caller uses `replace` on an authority today, so nothing breaks. Precedent: the source, "This also retires `dataclasses.replace` from outside the module".

### 6. `copy.copy`, `copy.deepcopy` and `pickle` return an equal authority with no code written for them, and a restore checks neither the token nor the shape rules.

A frozen, slotted dataclass restores its state field by field through the `__getstate__` and `__setstate__` that `dataclasses` generates and never calls `__init__`, so the token is neither asked for nor stored. EXECUTED on the changed copy under CPython 3.11.18, 3.12.3, 3.13.18 and 3.14.6, the four versions CI runs: for an authority from each door and a two-subject one with a scoped service actor and a source identity, every copy and every pickle protocol from 0 to 5 returns a value equal to the original, with the same hash and of type `Authority`. No `__reduce__`, `__copy__` or `__deepcopy__` is written. Precedent: the source, "`copy`/`pickle` keep working", repeated by I1 criterion 5.

### 7. The token guards against a mistake and is not a wall inside the process, and the documentation says so.

Three ways to hold an authority no door built remain open: unpickling bytes written by hand, `object.__new__` with `object.__setattr__`, and importing `_DOOR`. Each takes deliberate work a reviewer can see, where a bare `Authority(...)` looked like ordinary use. Code in the process already holds the database credentials and can call `Authority.system()`, so a wall there would protect nothing. The wall is the wire, where an authority is never accepted as data: 149-2 and the units after it. Precedent: "In process the gate is a convention ... any caller can construct the system authority" (`context/standards/roadmap.md:396`), and the published page makes the same case (`docs/explanation/identity-is-a-value.md:55`).

### 8. `Principal`'s constructor stays open, with the jobs spec's `name` field or without it.

A principal is a name, not a proof. Callers build one for every door call, and its own rules refuse the reserved names and kinds (READ, `src/vfs/authority.py:91-102`). The jobs spec's `name` is display data outside equality and grants no right (its decision 28), so it adds nothing a forger could use. The existing pin on a reserved-kind `Principal(` in `src/vfs` stays as it is. I1 criterion 5 names `Authority` alone, and closing `Principal` would break every caller's first line.

### 9. A test that needs a shape no door produces imports `_DOOR` and passes it; no helper is added to `src/` or `tests/support/`.

The two constructions at `tests/test_authority.py:134` and `:136` gain `door=_DOOR` and keep their assertions. The first shape, a user actor with `provenance="system"`, is reachable through no door, and the token is the only way a test reaches its rule. A helper in `src/` would be a fifth door for tests alone; one in `tests/support/` would hide one import behind one function. Precedent: tests already import private names from the module under test (READ, `tests/storage/database/test_trash.py:53-54`), and spec 070 lists tests among the sanctioned construction sites (`context/specifications/archive/070-principal-scoped-sessions/spec.md:52`).

### 10. The text pin also refuses the name `_DOOR` under `src/vfs` outside `authority.py`, and a second pin counts one token site per entry of `_DOORS`.

The pattern at `tests/base/test_authority.py:341` gains the alternative `\b_DOOR\b`. The name is searched for, not `door=`, because `ShareLock(door=True)` is legitimate (`dialects.py:419`). A pin on absence can pass for the wrong reason, so a second test counts presence: for each entry of `_DOORS`, the source of the function it names holds `door=_DOOR` exactly once, and the module holds it exactly `len(_DOORS)` times (EXECUTED: 1 for each of the four, 4 in all). The count is read from the tuple and not written as four, so a door added by 149-2, the jobs spec or the narrowing unit adds one entry and one site and the pin holds. The run-time check makes a bare `Authority(` in `src/` fail on its first call; the text pin stays because it fails without the line ever running.

### 11. Every later door lives in `vfs.authority`, passes `door=_DOOR` once and adds its name to `_DOORS`; the jobs spec's rebuild of a stored caller is such a door.

Three are known: 149-2's `authority_from_token`, the jobs spec's rebuild of the `caller` column, and the narrowing door of [148-2](../2026-11-25-a-session-narrows-by-a-subtractive-profile-and-a-child-session-inherits-it/spec.md). The jobs code parses its JSON into principals and fields and calls the rebuild door; the door, its name and its signature are the jobs spec's to set. The jobs spec's `Authority.system(name=)` is the system door with one more argument, not a new door, so `_DOORS` does not change for it. Whichever of this unit and the jobs build lands second makes the two agree: if the jobs build lands first, this unit's build adds the token and the entry to its rebuild door; if this unit lands first, the jobs build does. A door outside the module would have to import `_DOOR`, which decision 10's pin refuses, so this placement is the only one the tree admits.

### 12. A door that rebuilds a stored authority keeps the stored provenance, `edge` included, and the shape rules run on it.

The `caller` column is written by the kernel from an authority a door built when the call was made, so its provenance records how the caller was proven at that moment. A resumed step runs as that caller and writes version rows; writing them as `constructed` would make the audit say something false in the other direction, and the fact that the caller came in at the edge would be lost. Keeping it adds no forgery path: code that can write a `vfs_jobs` row holds the database credentials and could write `vfs_versions.provenance` directly (decision 7). The rule of I1 criterion 1, that `authority_from_token` is "the only site in `src/` that mints `provenance=\"edge\"`", is read as the one site that turns an outside proof into `edge`; a rebuild passes a value vfs wrote, and the pin of criterion 1 counts the literal `provenance="edge"`, which a rebuild does not write. The shape rules run because the rebuild goes through the constructor, so a stored `edge` on a system actor is still refused with `ValueError`. This is choice 1 below.

### 13. The docstrings and three pages under `docs/` state the closed constructor, and the sentence that names an edge factory leaves the module docstring.

A docstring under `src/vfs/` is a page's content (AGENTS.md, "Tooling"), so it states the tree as it is: four doors, a constructor that raises `TypeError`, and no factory that does not exist; 149-2 writes its own sentence when its function exists. The older site built from `docs/` is still the one deployed, so the three statements this change makes false are corrected in the same pull request. `_DOOR` gets no page: the naming rule places a private object's documentation on a Maintainers page if it has one (`documentation/maintainers/how-we-name.md:40`), and the class docstring already says what a reader needs.

### 14. This unit adds no door and lands as its own pull request before 149-2.

The token matters only once something mints `edge`, and the mint needs the token to exist, so the order is this unit, then 149-2 (the map of units gives this unit no dependency and makes 149-2 depend on it, `agents/2026-11-25-the-backlog-converted/units.md:70-71`). Between the two landings the tree is green and stricter than before, with nothing half-built: the four doors behave as they did.

## Cost

Nothing grows with input. The change adds one identity comparison to each construction, one module-level tuple of four strings and one object. The multiplier is per verb call: vfs builds its four authorities at import and none per call, so vfs adds nothing per call. A host that builds one authority for each verb call pays about 150,000 comparisons a day at the reference deployment, about 20 a second at peak. The subject set stays bounded by `MAX_SUBJECTS`, 64 (`src/vfs/authority.py:63`). No statement is issued, so no engine budget applies on SQLite or Postgres; no lock is taken, so no read waits.

## Tests

Written before the code. Counts and states, never clocks. The behaviour lives in one module, so every test is at the unit layer beside the existing ones; no storage changes, so no Postgres leg runs. No rights judgement changes, so no leak test is added; the forged-edge case of the first test is the guard that the change exists for.

- `tests/test_authority.py::test_a_bare_authority_raises_a_type_error_naming_every_door`: four bare calls (keyword arguments with `provenance="edge"`, three positional arguments, `door=None`, `door=object()`) each raise `TypeError` whose message holds every entry of `_DOORS`; and the set of public classmethods of `Authority` (read as every name in `vars(Authority)` that is a `classmethod` and does not start with `_`) equals the set of `Authority.`-prefixed entries of `_DOORS`. Seen failing at `27f3d24d`: nothing is raised.
- `tests/test_authority.py::test_the_door_is_checked_before_the_shape`: a bare call with a user actor and `provenance="system"` raises `TypeError`, not `ValueError`. Seen failing.
- `tests/test_authority.py::test_replace_is_refused_like_a_bare_construction`: `dataclasses.replace(Authority.of(ALICE), source_identity="x")` and `dataclasses.replace(Authority.of(ALICE))` each raise `TypeError` naming the doors. Seen failing.
- `tests/test_authority.py::test_copy_replace_is_refused_like_a_bare_construction`, marked `skipif(sys.version_info < (3, 13))`: `copy.replace(Authority.of(ALICE))` raises `TypeError`.
- `tests/test_authority.py::test_copy_and_pickle_round_trip_every_door`: for five authorities, one from each door and one `on_behalf_of` with two subjects, a scoped service actor and a source identity, `copy.copy`, `copy.deepcopy` and `pickle` at every protocol from 0 to `pickle.HIGHEST_PROTOCOL` return a value equal to the original, with the same hash and of type `Authority`: 40 round trips at a highest protocol of 5. It passes before and after the change; it pins what the change must not break.
- `tests/test_authority.py::test_the_door_is_not_a_field`: the names of `dataclasses.fields(Authority)` and `Authority.__slots__` are exactly `subjects`, `actor`, `provenance`, `narrowing`, `source_identity`, and `repr(Authority.system())` does not hold `door`. Passes before and after.
- `tests/test_authority.py::test_the_system_provenance_goes_with_the_system_actor_and_nothing_else`, rewritten: with `door=_DOOR` passed, the two shapes still raise `ValueError` matching "system provenance".
- `tests/test_authority.py::test_of_is_a_subject_acting_as_itself`, `::test_on_behalf_of_is_a_set_with_an_actor`, `::test_system_is_the_marked_exception`, `::test_anonymous_is_nobody_by_name` and `::test_an_authority_is_hashable_and_equal_by_value` pass with no edit.
- `tests/base/test_authority.py::test_only_the_authority_module_constructs_the_types_bare`, extended: zero lines under `src/vfs` outside `authority.py` match a bare `Authority(`, a `Principal(` of kind `system` or `anonymous`, or `\b_DOOR\b`.
- `tests/base/test_authority.py::test_each_door_passes_the_token_at_exactly_one_site`: for each entry of `_DOORS`, `inspect.getsource` of the function it names holds `door=_DOOR` exactly once, and `src/vfs/authority.py` holds it exactly `len(_DOORS)` times. Seen failing with a count of zero.
- `tests/scripts/test_docs_export.py::test_the_authority_page_says_the_constructor_is_closed`, on the module's `real_export` fixture (`:119-122`): the signature of `Authority` ends `*, door: InitVar[object] = None) -> None`, no member is named `door`, and its docstring holds `TypeError` and the names `of`, `on_behalf_of`, `system` and `anonymous`. Seen failing on the signature, which today ends `source_identity: str | None = None) -> None` (EXECUTED).
- The fence under "Construction" in `docs/reference/authority.md`, run by the `docs examples` step of `scripts/ci.sh` (`pytest docs`, `scripts/ci.sh:79-80`): a bare `Authority(...)` raises `TypeError` and the message holds `Authority.of`.

The gates are `scripts/ci.sh`, because `src/` and `tests/` change, and `scripts/docs.sh check`, because a docstring under `src/vfs/` changes. No engine leg, no `cargo test` and no reinstall of the extension: no storage code and no Rust is touched.

## Scope

In: `src/vfs/authority.py` (the import at `:28` gains `KW_ONLY` and `InitVar`; `_DOOR` and `_DOORS` above the class; `_: KW_ONLY` and `door: InitVar[object] = None` after `source_identity`; `__post_init__(self, door: object)` opening with the check; `door=_DOOR` in the four `cls(...)` calls; the module docstring at `:18-22` and the class docstring); `tests/test_authority.py` (the import at `:10-21` gains `_DOOR`, the docstring at `:1-2` and the banner at `:63` say four doors, a banner "The door" after "Invariants at construction", the tests above); `tests/base/test_authority.py` (the pattern, the comment at `:337-339`, the counting test); `tests/scripts/test_docs_export.py` (one test); `docs/explanation/identity-is-a-value.md`; `docs/reference/authority.md`; `docs/reference/glossary.md`.

Out, with where each belongs.

- `authority_from_token`, the `TokenVerifier`, the extra, the mint of `provenance="edge"` and the fifth entry of `_DOORS`: [149-2](../2026-11-25-a-verified-token-becomes-an-authority-at-the-edge-and-nowhere-else/spec.md).
- The `attested` provenance and the member list a trusted subsystem names: [149-3](../2026-11-25-a-trusted-subsystem-names-the-members-of-a-room-and-the-authority-says-attested/spec.md).
- The door that rebuilds an authority from the `caller` column, `Principal.name` and `Authority.system(name=)`: [the jobs spec](../2026-11-22-a-job-is-interrupted-and-resumed/spec.md), held to decisions 11 and 12 here.
- A door that returns a narrowed authority: [148-2](../2026-11-25-a-session-narrows-by-a-subtractive-profile-and-a-child-session-inherits-it/spec.md), which adds it in `vfs.authority` under decision 11.
- The rest of the source: its rule 3 and the open-mount refusal go to [171-2](../2026-11-25-serve-answers-each-request-under-its-own-authority-and-refuses-an-open-mount/spec.md), its rule 4 to [170-5](../2026-11-25-a-mounted-server-is-called-with-the-credential-the-host-resolves-for-the-caller/spec.md), and its rule 5 to roadmap story M3, which has no spec.
- Checking the token or the shape rules on unpickling, and closing the three ways of decision 7: not planned, by decision 7.
- Closing `Principal`'s constructor: decision 8.
- Moving the identity pages from `docs/` into `documentation/`: the docs deployment work.

## What the docs must say

- The module docstring of `src/vfs/authority.py`, `:18-22`: four doors, the classmethods above; the constructor demands the module's own token and raises `TypeError` naming the doors when called without it; `copy` and `pickle` keep working; the six shape rules raise `ValueError`. The sentence naming an edge factory goes.
- The class docstring of `Authority`: one sentence that the constructor is not for callers and raises `TypeError`, and that `door` is the module's own token and no caller's argument. `documentation/reference/python-api/authority.md` draws from it and needs no edit: the export of the changed copy shows the new signature and no `door` member (EXECUTED).
- `docs/explanation/identity-is-a-value.md`: the paragraph at `:49` says the constructor refuses and the scan remains; the paragraph at `:53` says a bare call raises `TypeError` and lists the three ways of decision 7 that remain; the paragraph at `:55` stands; the paragraph at `:59` is removed.
- `docs/reference/authority.md`: a section "Construction" before "Doors" states the `TypeError`, with one runnable fence; the line at `:73` says each shape rule raises `ValueError` when a door builds an authority.
- `docs/reference/glossary.md:21`: "The bare constructor is not a door and raises `TypeError`."

## Earlier decisions this reverses

- The source's deferral, "Judged overkill before the edge exists" (`context/specifications/archive/149-serve-auth-token-to-authority/spec.md:35`), which roadmap I1 criterion 5 already overturned.
- The published statement that the doors cannot stop a bare call (`docs/explanation/identity-is-a-value.md:53`).

## Not checked

- `scripts/ci.sh` and `scripts/docs.sh check` were not run; the changed module was linted, formatted, type-checked and exported in a scratch copy, not in the tree.
- Whether Griffe renders `InitVar[object]` on the docs-app page as the export prints it; the export was run, the site was not built.
- The jobs spec's JSON shape of the `caller` column, beyond its table row, and how its code will call the rebuild door; neither is written.
- Whether a host's code outside the repository calls the bare constructor or `dataclasses.replace` on an authority; nothing published has been released, so no caller is known.

## Choices to confirm

1. **Does a rebuilt authority keep a stored `edge`?** Taken: yes, decision 12, because a downgrade to `constructed` loses the fact for good while keeping it can be undone for later resumes by one change in the rebuild door, and because a writer of the job row can already write version rows. The other answer has the rebuild door write `constructed` for a stored `edge`, so that `authority_from_token` is the only code that ever returns `edge`. The ruling belongs with the jobs spec's build as much as with this one, and either spec can carry it.
2. **Is the error a `TypeError`?** Taken: yes, decision 1, because roadmap I1 criterion 5 names it. The other answer is `ValueError`, which `context/standards/how-we-code.md:24` gives every construction fault; taking it would change one word in the check and the tests.

## One line

The constructor of `Authority` demands a private token that only the doors inside `vfs.authority` pass, so a bare `Authority(...)` or a `replace` raises `TypeError` naming the doors, `copy` and `pickle` still return an equal value, and every later door, the jobs spec's rebuild included, lives in the module and is counted by the pin.
