# A narrowed authority can do no more than before, and a path it hides answers as absent before any lookup

A draft, written on 2026-11-25. It is not reviewed, and nothing is built. It was checked against `dev` at `27f3d24d`. It serves gate 0.2 and no roadmap story: the roadmap's table of work after 0.1.0 holds the row "Narrowing with content, child sessions (spec 148 §1–4) | 0.2" (`context/standards/roadmap.md:1188`). It is unit 148-2 of [the conversion map](../2026-11-25-the-backlog-converted/units.md), converted from sections 1 to 3 and 6 of [the archived spec 148](../../context/specifications/archive/148-sessions-narrowing-and-pending/spec.md), in the smaller form [the reassessment](../2026-11-25-the-backlog-converted/reassessment/kernels-sessions-and-deadline.md) leaves of it in its section 148-2: narrowing with content on `Authority`, not a `session.narrow` method, with the verb deny dropped because session policies carry it. It rests on [the study of the source](../2026-11-25-the-backlog-converted/studies/051-162/148-sessions-narrowing-and-pending.md), re-checked here against `dev`, and on two probes run on 2026-11-25 with `uv run python -I` against this tree, cited as EXECUTED where they are used.

## The outcome wanted

A host that hands an agent part of a caller's rights writes `authority.narrow(Narrowing.of(within=["/work"], hide=["/work/.env"], caps={"/work/contracts": "read"}))` and makes every call, or asks for a session, with the result. The narrowed authority can do no more than the authority it came from, at any path, through any verb. A path it hides answers exactly as a path that does not exist, before any storage looks for it, and no listing, search, walk, page key or error names it. A step it caps below what the verb needs is refused under its own kind, `vfs.permission_denied.narrowing`, which a caller tells apart from a missing grant without reading prose. Narrowing twice only narrows further. A session handle made with a narrowed authority, and every fork of it, carries the narrowing, the subjects and the source identity of the authority it was made with. It is seen in the answers: a narrowed `ls /` shows only the road to `/work`, and a narrowed `grep` over `/` never matches inside a hidden file.

## Builds on

- **Landed: [spec 058](../../context/specifications/archive/058-row-level-permission-grants/spec.md), row-level grants, built on `dev`.** The compiled rights (`src/vfs/storage/grants.py:404-528`), their pushdown into every statement (`src/vfs/storage/backends/database/rights.py:480-507`, `src/vfs/storage/backends/database/ranges.py:86-143`), the road of bare directory names (`rights.py:615-645`), and the rule that a hidden row reads exactly as a missing one (`tests/support/grants_contract.py:175`). This spec adds one field to the compiled rights and uses the rest unchanged.
- **Built on `dev`: the holes of a posture relabel.** A region whose labels cannot be trusted is a hole, in which only the caller's own spans and its owner floor admit a row (`grants.py:416-421`, `:485-498`). Both pushdowns already compile holes: the clause fan cuts the everyone leg around them (`rights.py:1312-1331`) and the range join excludes them through `hole_free` (`ranges.py:104`, `:122-143`). Decision 14 makes a narrowing's cut a hole.
- **Built on `dev`: the listing cursor,** [the listing spec](../2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md). A row the kernel adds itself obeys the page key like any other row, and a key is always a row that was shown. Decision 11 filters the kernel's own rows before the page is cut.
- **Specified on `dev`, not built: [spec 2, the stored session](../2026-11-22-a-session-is-stored-named-and-forked/spec.md),** which replaces landed spec 070's session facade. Shapes relied on: decision 3, "The handle holds eight values, and only its current turn ever changes", whose list says "No method replaces `authority`, `id`, `strict` or `policies`"; decision 5, "A session stores no right, and every call is judged on the handle's authority at the time of the call"; decision 6, the owner key, which says `narrowing` "does not change whose session it is"; decision 9, "A subject set that changes is another owner, so the conversation gets a new and empty session". Decision 18 here departs from decision 6.
- **Specified on `dev`, not built: [spec 4, turns and forks](../2026-11-22-a-session-works-in-turns-and-rewinds-or-forks-at-one/spec.md).** Decision 16, "`fork(id, before=turn)` makes a new session of the same owner", whose handle "carries the source handle's authority, `strict` and policies"; decision 19, "A fork records its parent and its fork point, and nothing reads through them", under which "Removing or expiring the parent changes nothing in the fork".
- **Specified on `dev`, not built: [spec 6, policies](../2026-11-22-a-policy-judges-each-step/spec.md).** Decision 17, "A session's policies are asked after the file system's and can only add", carries the verb deny of the source. Decision 14 gives the shape a refusal of a rule takes, `vfs.permission_denied.policy`, which decision 9 here follows. Decision 10 places `_admit` after the kernel's gate, so a policy is never asked about a step this spec's gate refuses.
- **Specified on `dev`, not built: [spec 7, jobs](../2026-11-22-a-job-is-interrupted-and-resumed/spec.md),** whose `vfs_jobs.caller` column holds the caller's authority as JSON, "the narrowing" included (`spec.md:141`). Decision 19 gives that column the narrowing's form.
- **A unit of this conversion, written and not built: [149-1, the door token](../2026-11-25-a-bare-authority-constructor-is-closed-by-a-door-token/spec.md).** Its decision 11 says every later door lives in `vfs.authority`, passes `door=_DOOR` and adds its name to `_DOORS`, and names "the narrowing door of 148-2" among them. Decision 5 here is that door.
- **Build order.** This spec stands on built code alone and lands as one pull request (decision 23). The owner-key line of decision 18 lands with whichever of this spec and spec 2 is built second; the fork test of decision 17 with whichever of this spec and spec 4 is built second; the door of decision 5 with whichever of this spec and 149-1 is built second; the payload of decision 19 is read by spec 7 when it is built.

## Terms

- **Narrowing.** The value an authority carries that takes rights away. It never adds one.
- **Cap.** A pair of a path prefix and a rung: at that path and beneath it, the authority holds no rung above that one. A cap whose rung is `none` hides its subtree.
- **Within.** An optional set of path prefixes: when it is set, every path not at or beneath one of them is hidden, apart from the road to them.
- **Ceiling.** The highest rung a narrowing allows at one path.
- **Hidden path.** A path whose ceiling is `none` and which is not a road path.
- **Road path.** A strict ancestor of a within path that is itself not within. It may be named, as a bare directory, so a caller can walk down to what it may use.
- **Cut.** For one rung, the set of paths at which the ceiling is below that rung, as a range set.
- **Rung.** A step of the permission ladder, `none`, `list`, `read`, `add`, `contribute`, `read_write` (`src/vfs/ops.py:125-133`).

## What the code does today

| Fact | How it is known |
|---|---|
| `Narrowing` is an `Enum` with one member, `NONE`, documented "Opaque here: the only value is *nothing*". | Read, `src/vfs/authority.py:68-71`; EXECUTED, `list(Narrowing)` prints `[<Narrowing.NONE: 'none'>]`. |
| `Authority` is a frozen dataclass of `subjects`, `actor`, `provenance`, `narrowing` and `source_identity`, built through four classmethod doors. | Read, `src/vfs/authority.py:118-189`. |
| No code in `src/` reads `narrowing`. | EXECUTED, `grep -rn narrowing src/vfs`: the field, the export, and unrelated uses of the word in `traverse.py` and `scope.py`. |
| `vfs.authority`, `vfs.ops` and `vfs.paths` share rung 1 of the layer ladder, and units on one rung may not import each other. | Read, `tests/lint/test_code_shape.py:44-69`. |
| The covering algebra, `Covering`, `covers`, `tree_key`, `minimise` and `meet`, lives in `src/vfs/storage/grants.py` on rung 6. | Read, `grants.py:115`, `:150-153`, `:182-236`. |
| `Rights.admits` passes a row by its everyone label unless the path is in a hole, else by the spans, else by the owner floor; `reaches`, which judges a creation, reads the label and the spans and not the holes. | Read, `grants.py:477-498`. |
| A cached resolution is keyed by the subject names, their stamps and the relabels in flight, and the system actor skips resolution. | Read, `rights.py:231-237`, `:332-388`. |
| A read of a missing path, a read under a directory the caller cannot see, an `ls` of such a directory, and a write under it each answer `vfs.not_found`, message `Not found`, at the first missing or hidden ancestor, with `data["vfs.target"]` the addressed path when it differs, and `source` the mount. | EXECUTED, a probe on `InMemoryStorage` with `Authority.of(Principal("ada"))` under the private default posture. |
| The kernel's checks before a storage is called are `_busy_guard` and `_gate_entry`, at seven sites, one for each shape of dispatch; a refusal in a batch fails the whole call before any storage is asked. | Read, `src/vfs/base.py:1857-1866`, `:1908-1922`, `:1963`, `:2111`, `:2359-2373`, `:2482`, `:2591`. |
| A verb that acts beneath its path is a cascading delete, a move, a copy and a sweep outside a trash view. | Read, `base.py:3079-3090`. |
| Every storage call passes through `_call_storage`, which resolves the caller with `caller_for`. | Read, `base.py:2852-2881`. |
| A storage declares eight traits, and none concerns narrowing. | Read, `src/vfs/storage/protocol.py:78-99`; EXECUTED, `InMemoryStorage().traits()`. |
| `ErrorKind` has one member in the `vfs.permission_denied` family. | EXECUTED. Read, `src/vfs/results/kinds.py:73-75`. |
| `base.py` and `rights.py` are held at 3,090 and 1,539 lines; any other module may grow to 1,000. | Read, `tests/lint/allowlist.py:26-33`, `tests/lint/test_code_shape.py:76`. |
| SQLite and Postgres each serve a set of path pieces as one bound value through a range source; the generic floor spells the pieces literally, inside an `IN`-list budget of 1,000. | Read, `src/vfs/storage/backends/database/dialects.py:363`, `:398`, `:416`, `:439`, `:452`; `ranges.py:122-143`. |

## The problem

A host that starts a sub-agent for a narrow task can give it only what the caller holds. Grants only widen (`grants.py:1-10`), so nothing in a call can take a right away. The roadmap's answer at 0.1.0 is a second session, and a second session holds the same rights. A sub-agent told to edit `/work` can therefore read `/hr`, overwrite `/contracts`, and grant itself or anyone what its caller holds.

A narrowing that filtered rows after they were fetched would not do. A listing would pay for rows it cannot return, a page could come back empty while more rows follow, and a search would rank against bodies it then drops. At the reference deployment a verb call is about 150,000 a day, and a read must cost in proportion to what it returns: a filter after the fetch turns a page of `/` over 10,000,000 files into a scan of whatever the hidden region holds. The narrowing has to be judged in the statement, as rights are.

A narrowing judged only by the storage would not do either. The kernel answers some calls itself: a mount point is `busy`, a mount that lacks a verb is `unsupported`, and a listing shows the directory above a mount point as a bare row. Each of those names a path the storage never sees.

## Decisions

### 1. `Narrowing` becomes a frozen value of caps and a within set, and `Narrowing.NONE` is its empty value and the default

```python
class Cap(NamedTuple):
    prefix: Path
    rung: Rung

@dataclass(frozen=True, slots=True)
class Narrowing:
    caps: tuple[Cap, ...] = ()
    within: tuple[Path, ...] | None = None
    NONE: ClassVar[Narrowing]

    @classmethod
    def of(cls, *, within: Iterable[str] | None = None, hide: Iterable[str] = (), caps: Mapping[str, Rung] | None = None) -> Narrowing: ...
    def meet(self, other: Narrowing) -> Narrowing: ...
    def ceiling(self, path: str) -> Rung: ...
    def is_road(self, path: str) -> bool: ...
    def without_mount(self, mount: str) -> Narrowing: ...
    def to_payload(self) -> NarrowingPayload | None: ...
    @classmethod
    def from_payload(cls, payload: NarrowingPayload | None) -> Narrowing: ...
    @property
    def is_none(self) -> bool: ...
```

Both stay in `src/vfs/authority.py`, beside the one field that holds a `Narrowing`, and both are exported from `vfs`; `Cap` is public because a public field names it (`documentation/maintainers/how-we-name.md`, "Public and private"). `Narrowing.NONE` is `Narrowing()`, set once after the class, so every existing `Narrowing.NONE` reads the same. `hide=[p]` is the cap `(p, "none")`. The name `Cap` and not `Limit`, because `limit=` already names a page size on `ls`, `tree` and `glob`, and one word has one meaning. Reason: a cap is a grant row (`GrantRow`, `grants.py:137`) with its sign reversed, a prefix and a level, so it rides the same range algebra; the within set is the one subtractive form that confines an agent to a subtree, where caps alone would have to name every sibling and would leave a sibling made later in view.

### 2. The ceiling at a path is `none` outside the within set and otherwise the lowest rung of every cap that covers it

- Outside the within set, and on a road path, the ceiling is `none`.
- Otherwise it is the minimum over every cap whose prefix covers the path, at the prefix or beneath it, and `read_write` where no cap covers it.
- A deeper cap never raises what a shallower cap allows. No rule of a narrowing can widen, so a narrowing needs no refusal for a widening and has none.

Reason: each rule only takes away, so the rules compose by the most restrictive, as permission maps do across layers (`src/vfs/permissions.py:1-10`, `check_writable_composed` at `:261`). This departs from the source's resolution by anchor depth, deepest rule first (source, section 2). Depth ranks rules that disagree, and rules that only subtract do not disagree.

### 3. A narrowing is held in one canonical form, and an unlawful one is refused at construction

- **Paths.** Each prefix and each within path is absolute and is normalised by `normalize_path` (`src/vfs/paths.py:523`). A relative path, a path `validate_path` refuses, or a path in the reserved `.vfs` space (`check_reserved_path`, `paths.py:875`) raises `ValueError`. A trash view is judged at the paths it shows, by decision 8.
- **Rungs.** A rung not on the ladder raises `ValueError`; a value of the wrong type raises `TypeError`.
- **Within.** `within=None` confines nothing. An empty iterable raises `ValueError`, "within names at least one path; pass None to confine nothing", because an empty set that meant "everything" would invert a host's intent. The set is minimised, so a path beneath another is dropped.
- **Caps.** A cap at `read_write` is dropped. A cap beneath a cap of an equal or lower rung is dropped. A cap at a path that is hidden by the within set is dropped. Where `hide` and `caps` name one prefix, the lower rung stays.
- **Order.** Caps and within paths are kept in tree order (`tree_key`, `grants.py:182`), so two narrowings that allow the same paths are equal values with equal hashes.
- **Bounds.** At most `MAX_CAPS: Final = 64` caps and `MAX_WITHIN: Final = 64` within paths after canonicalisation; more raises `ValueError`.

`__post_init__` puts the fields in this form with `object.__setattr__`, as `Rights.__post_init__` does (`grants.py:432-435`), so a narrowing built through its constructor and one built through `of` are the same value. Reason for the bound: each rule adds at most two pieces to every statement of every call the authority makes, and `MAX_SUBJECTS = 64` bounds a subject set for the same reason (`authority.py:63-65`). Choice 4 holds the number.

### 4. `meet` intersects two narrowings, and the result never allows more than either

- The within set of the meet is the covering `meet` of the two (`grants.py:201-223`), or the one that is set when only one is. Two within sets that share no path give `Narrowing(caps=(Cap("/", "none"),))`, which hides everything.
- The caps of the meet are the caps of both, put in canonical form, so the ceiling of the meet at every path is the lower of the two ceilings.
- `meet` is commutative, associative and idempotent, and `x.meet(Narrowing.NONE) == x`.

Reason: an intersection cannot widen by construction, so `narrow` needs no subset test. Rule 1 of the retired record on sessions asks for one (spec 2, "Earlier decisions this reverses"); the intersection is that test made unconditional.

### 5. `Authority.narrow(narrowing)` returns the authority whose narrowing is the meet, and nothing else changes

```python
def narrow(self, narrowing: Narrowing) -> Authority: ...
```

- Subjects, actor, provenance and source identity are carried unchanged.
- `Authority.system().narrow(...)` raises `ValueError`: "the system authority is narrowed by nothing; narrow a named authority". `__post_init__` gains the shape rule that the system actor carries `Narrowing.NONE`.
- The anonymous authority may be narrowed.
- A value of `narrowing` that is no `Narrowing` raises `TypeError`.
- `narrow` is a door in the sense of 149-1: it passes `door=_DOOR` and its name, `Authority.narrow`, joins `_DOORS`, by 149-1's decision 11. Until 149-1 lands it calls `dataclasses.replace`.

The name is the bare verb of the naming page, for a method whose action is the verb (`how-we-name.md`, "Methods"); choice 7 holds it. Reason for the system rule: the system actor skips the rights resolution and every policy (`rights.py:360-361`; spec 6, decision 18), so a narrowing on it would need a second path through every gate. A host that wants a narrowed bulk load names a principal for it.

### 6. `vfs.authority` takes a rung of its own, and the covering algebra moves down to `vfs.paths`

- In `LAYERS` (`tests/lint/test_code_shape.py:46-69`), `vfs.authority` leaves rung 1 for a new rung directly above it, so it may import `Rung` from `vfs.ops` and `Path` from `vfs.paths`. Nothing on rung 1 imports `vfs.authority` (EXECUTED, `grep` of `ops.py` and `paths.py`), so the move breaks no import.
- `Covering`, `covers`, `tree_key`, `minimise` and `meet` move from `src/vfs/storage/grants.py` to `src/vfs/paths.py`, and `grants.py` imports them from there. `paths.py` holds 944 lines and stays under the ceiling of 1,000.

Reason: a narrowing needs the same prefix algebra grants use, and a second copy of it would be duplicated code that the parity tests would have to pin twice.

### 7. Two layers judge a narrowing: the kernel judges every path a call names, and the storage judges every row a statement finds

The kernel's rule (decision 8) runs before any lookup and costs no statement. The storage's cut (decision 14) runs inside the statement that finds the rows. Neither is trusted in place of the other: the kernel cannot see the rows a listing finds, and the storage cannot see a mount point or a kernel refusal. Reason: the same split the rights already have, where the kernel's permission maps judge a named path and the storage judges rows (`base.py:2705-2735`).

### 8. The kernel judges each named path by one rule, before any other check that can name the path

For each path a call names, with the rung the verb needs there at the least (its `create` rung where the verb declares one, else its `primary` rung, and its `passing` rung for a path it only passes: a copy's source, an edge's target; `src/vfs/ops.py:136-178`):

| The path is | The answer |
|---|---|
| hidden | `vfs.not_found`, message `Not found`, at the shallowest hidden path on its chain, with `data["vfs.target"]` the named path when it differs and `source` the mount that holds it, for every verb, a mutation included |
| a road path | a read verb goes on to the storage, which shows the road; a mutation is refused with `vfs.permission_denied.narrowing` at the named path |
| capped below the rung | `vfs.permission_denied.narrowing` at the named path |
| named by a verb that acts beneath it, with a cap strictly beneath whose rung is below the verb's `primary` rung, or a within path strictly beneath | `vfs.permission_denied.narrowing` at the named path |
| anything else | the call goes on |

- The verbs that act beneath their path are those `_reaches_beneath` names (`base.py:3079-3090`), and `grant`, `revoke` and `set_posture`, whose rows hold at and below their prefix (`grants.py:1-3`). A delete that does not cascade and a restore are judged at their own path, as the permission maps judge them.
- A path inside a trash view is judged at the path it shows, through `strip_trash_head` (`paths.py:811`), because a tombstone is judged at its own path (`rights.py:58-66`).
- The rule is the first check after the path is parsed: before `_busy_guard` and before `_gate_entry`, at each of the seven sites of the table above. So a hidden path is never `busy`, `unsupported` or `read_only`.
- A batch refused at one path is refused whole, and no storage is asked, as `_gate_entry` refuses one today (`base.py:2482-2484`).
- The caller is resolved as `caller_for` resolves it, without its log record, so a kernel's `default_authority` carries its narrowing too.

Reason for the hidden answer: the probe shows that a write under a directory the caller cannot see answers `not_found` at that directory (EXECUTED), and a hidden path is a path that is not in the caller's namespace, as on Plan 9 (constitution, article 3). An answer of the same shape tells the caller nothing a missing path would not. Reason for a separate kind elsewhere: a capped step's answer depends only on the authority, so it leaks nothing about the store, and the caller learns that a grant would not help.

### 9. A capped step is refused under one new kind, `vfs.permission_denied.narrowing`

`ErrorKind` gains `narrowing_denied = "vfs.permission_denied.narrowing"`. Its row in `KIND_CONTRACTS`:

| Field | Value |
|---|---|
| Phrase | `Refused by the narrowing` |
| Retry class | `never` |
| Hint | `This caller's authority is narrowed so that it may not take this step here. A grant will not change that; work within the paths it may use.` |
| What `path` means | `the path the call named` |

- The detail never names a cap's prefix or a within path. It is "the authority's narrowing does not allow <verb> here", or "... beneath here" for a verb that acts beneath its path.
- A caller that raises on failure gets what `permission_denied` raises, `WriteConflictError`, by the family rule (`src/vfs/exceptions.py:72-100`).
- `_HOST_ERROR` in `src/vfs/shell/host.py:94` gains the kind, mapped to `permission_denied`, so a command prints "Permission denied" and exits non-zero.

Reason: the shape of spec 6's decision 14, for the same reason it gives there: `vfs.permission_denied` itself hints "request access", which is not what is missing, and article 2 of the constitution closes the taxonomy, so the refusal is a child of the family "the caller is known and may not". A reader that does not know the child falls back to the parent, which is true.

### 10. A narrowed authority makes no mount change and no membership change

- `add_mount`, `update_mount` and `remove_mount` called with a narrowed authority raise `MountError` carrying one fact of the kind `vfs.permission_denied.narrowing`, before `_require_mount_rights` (`base.py:2779`) asks any storage.
- `add_member` and `remove_member` with a narrowed authority answer that kind and ask no storage.

Reason: a mount moved or added could put a hidden subtree at a path the narrowing leaves open, which is the bypass Plan 9's `RFNOMNT` exists to close, and which the source's section 6 asks for. A membership change alters a group's rights at every prefix the group holds, so no path bounds it, and the rule of decision 8 cannot judge it. Choice 6 holds both.

### 11. The kernel drops its own rows at hidden paths, bares its rows at road paths, and never calls a mount the narrowing closes

- In `MountListing` (`src/vfs/listing.py:106-128`), where the rows a deeper mount hides are dropped, a row the kernel made itself (a mount point's head, a road to a mount point, a probed root) is dropped when its path is hidden, and is reduced to its path and kind when its path is a road path. This runs before the cursor cuts the page, so a page key is never a hidden row.
- A fan-out never calls a mount whose path is not a road path and whose ceiling is below the verb's rung, because nothing in that mount could be returned.

Reason: the kernel's rows name paths no storage judges, and the listing spec's rule that a key is always a row that was shown.

### 12. Each storage receives the narrowing in its own coordinates

`_call_storage` passes the storage the authority whose narrowing is `narrowing.without_mount(mount.path)`:

- A within path at or above the mount path confines nothing inside the mount, so the rebased within set is `None`; a within path beneath it is rebased; a mount that no within path reaches is given the cap `("/", "none")`.
- A cap at or above the mount path becomes a cap at `/`; a cap beneath it is rebased; any other cap is dropped.

Reason: a storage judges paths in its own coordinates, as a permission map's rules are mount-relative (`permissions.py:15-19`) and the page key is rebased by `local_after` (`paths.py:368`).

### 13. A storage declares that it judges a narrowing, and a narrowed call to one that does not is refused

`TraitKey` gains `narrowing` with the one value `statement` in `TRAIT_VALUES` (`protocol.py:78-99`). `DatabaseStorage` declares it. A narrowed call that reaches a mount whose storage does not declare it is answered `vfs.unsupported` at the mount path, detail "the storage mounted here does not judge a narrowed authority", and the storage is not called. A mount at a hidden path never gets that far, by decision 8. Reason: article 4 of the constitution forbids a silent partial implementation, and a storage that ignored the field would show what the narrowing hides. Choice 5 holds the refusal against a kernel-side filter.

### 14. In the database storage a narrowing is a cut on each compiled rung, and the cut rides the holes into every statement

- `Rights` gains one field, `cut: RangeSet = NO_SPANS`.
- `Resolution.narrowed(narrowing)` returns, for each grantable rung `L`, the rights whose `cut` is the cover of every cap with a rung below `L`, joined with everything outside the within set's cover. Its spans are the old spans less the cut, its holes are the old holes joined with the cut, each owner arm's owned set is less the cut, and its roots are worked out again by `_roots` (`grants.py:708-714`) over the new spans, with the within paths among the candidates.
- `admits`, `reaches`, `covers` and `covers_subtree` answer `False` for a path in the cut, first.
- The pushdown needs no new SQL. A hole already cuts the everyone leg in the clause fan (`rights.py:1312-1331`) and in the range join (`ranges.py:104`), and with the cut taken out of the spans and the owned sets, nothing admits a row inside it. The road's two searches already honour holes (`rights.py:1381`).
- `resolve_authority` applies the narrowing after the cache, at its two returns. The cache keeps the resolution of the subjects alone, so two narrowings of one caller share one compile.
- A narrowed resolution with a cut at any rung is not `whole`, so every site that skips the predicate for a whole resolution judges rows (`backend.py:846`, `:889`, `:1237`; `authorized.py:185`, `:266`, `:356`).
- `Resolution` and its new method move from `rights.py` to a new module, `src/vfs/storage/backends/database/resolution.py`, so `rights.py` stays at or under its baseline of 1,539 lines.

Reason: a hole is the tree's existing statement of "only the caller's own pieces admit here", and the cut is "nothing admits here", which is a hole with the pieces taken away. Reusing it keeps the narrowing inside the statement on both engines, with the budgets the holes already respect.

### 15. The write gate classifies a refusal the narrowing causes as the narrowing's kind

Where the write gate refuses a path whose ceiling is below the rung it judged, the refusal is `vfs.permission_denied.narrowing` at that path, not `permission_denied`. The gate is built with the rebased narrowing. The case it serves: a `write` under a cap at `add` passes the kernel's rule, which judges the `create` rung, and meets an existing file, which needs `contribute` (`ops.py:160`). Reason: the caller must be told the same thing whether the kernel or the storage found the cap.

### 16. A within set's road is the storage's own road, so a hidden directory never appears on it

With `within=["/work"]`, `ls /` shows `/work` as a bare directory when a row beneath it is one the caller may name, by the road's existing rule that every root of the rights is named and its ancestors are on the road (`rights.py:615-645`). No hidden directory is on the road, because the cut is a hole and the road's searches exclude holes. Reason: an agent confined to `/work` must be able to walk to it from `/`, and the road already says how much a caller learns by walking.

### 17. A session handle and a fork carry the narrowing of their authority, and nothing more is built for a child session

- A handle holds the authority it was made with (spec 2, decision 3), and every call through it is judged on that authority (spec 2, decision 5), so a handle made with a narrowed authority is narrowed.
- A fork's handle carries its source handle's authority (spec 4, decision 16), so it carries the narrowing, the subjects and the source identity.
- A host makes a narrowed child as `fs.session(handle.authority.narrow(profile), child_id)`. `narrow` keeps the subjects and the source identity (decision 5).
- A child does not end with its parent. Spec 4 rules that removing or expiring a parent changes nothing in a fork (its decision 19), and spec 2 gives a session no end but its removal or its expiry. The source's "ends with its parent" has nothing to attach to and is dropped.
- A child with more subjects is another authority from a new proof, and another owner (spec 2, decision 9); `narrow` changes no subject.

Reason: spec 2's handle offers no change of rights (its decision 3), so a `session.narrow` method would be a second way to make an authority, outside the doors.

### 18. A narrowed authority owns sessions apart from the authority it was narrowed from

When spec 2's `owner_key` lands, the payload of an authority whose narrowing is not `Narrowing.NONE` gains a fourth item, `narrowing.to_payload()`: `[OWNER_KEY_DOMAIN, actor, names, payload]`, encoded as spec 2 encodes the first three, with `sort_keys=True`. An authority with no narrowing keeps spec 2's three-item payload, so its key is unchanged. Reason: spec 2's own decision 9, that state shown under one set of rights must not be put before a caller with fewer. A session's stamps and shell variables may hold what the narrowing hides, and a narrowed handle on the same session would see them. This departs from spec 2's decision 6, where "`narrowing` ... does not change whose session it is"; choice 2 holds it.

### 19. A narrowing has one JSON form, for every record that stores an authority

`to_payload()` returns `None` for `Narrowing.NONE`, and otherwise `{"within": [path, ...] or None, "caps": [[prefix, rung], ...]}` in canonical order. `from_payload` builds the narrowing back through the constructor, so a malformed payload raises `ValueError`. Spec 7's `caller` column and decision 18's owner key both use it. Reason: one form keeps two stored records from disagreeing about one value; precedent `PermissionMap.to_payload` (`permissions.py:188`).

### 20. The source's verb deny, show globs, `narrow` and `child` methods are not built

- **Verb deny.** Spec 6's session policies carry it: a session's policies only add (its decision 17), and a denial has its own kind (its decision 14).
- **Show globs.** A show rule is the one rule that could widen. The within set confines without one.
- **`session.narrow` and `session.child`.** Decision 17.
- **A refusal for a profile that would widen.** No narrowing can widen (decision 4).

### 21. A policy sees the narrowed authority, and is never asked about a step the narrowing refuses

Decision 8's rule runs before `_gate_entry`, and spec 6's `_admit` runs after it (its decision 10), so a step the narrowing refuses is shown to no policy. A step that passes carries the narrowed authority as `step.authority`. Nothing in spec 6 changes.

### 22. The kernel's rule lives in a new module, and `base.py` stays at its baseline

`src/vfs/gates.py` holds decision 8's rule, decision 11's row filter, and the two pure checks it needs from `base.py`: `_reaches_beneath`, moved as `reaches_beneath`, and `_busy_guard`, moved as `busy_refusal` taking the mounts beneath as an argument. `LAYERS` places `vfs.gates` on the rung of `vfs.permissions`. `base.py` keeps seven one-line calls and ends at or under 3,090 lines. Reason: the size baseline grows for no module, and the listing landing kept it the same way, by moving a self-contained group out (the listing spec, "What was built").

### 23. One landing

The value, the kernel's rule, the storage's cut, the kind and the trait land in one pull request. Reason: the kernel's rule without the cut would leave every listing's rows unjudged, and the cut without the rule would leave mount points and kernel refusals naming hidden paths; either half alone is a leak.

## Cost

| What is added | Multiplier | Arithmetic | Bound |
|---|---|---|---|
| The kernel's rule over each named path | per verb call, about 150,000 a day | at most 15 ancestors of a path, each a lookup among at most 64 caps and 64 within paths, in Python | `MAX_CAPS`, `MAX_WITHIN`; no statement |
| The same rule over a batch | per batch, 100 a night | 10,000 paths × 15 ancestors, about 150,000 lookups | no statement; a refusal dispatches nothing |
| The narrowed resolution | per verb call | one pass per grantable rung, five, over the caller's spans and at most 257 cut pieces (2 per cap, 2 per within path plus 1) | the two declared bounds |
| The cut in a statement, SQLite and Postgres | per verb call | the holes are one bound value through the range source, so no bind is added | the statement count of an unnarrowed call, pinned by test |
| The cut in a statement, the generic floor | per verb call | at most 257 pieces at 2 binds is 514 binds for the hole test; the everyone units of the clause fan at most 258 × 3 = 774 binds | half the membership budget, 500 on the floor, so at most 2 clauses where the unnarrowed call has 1 |
| Rows visited inside the cut | per verb call | the everyone leg's index seek on `(everyone_level, path)` still visits rows inside a hidden region that everyone may see, and drops them by the hole test inside the engine; none reaches Python | not bounded by the page; see below |

No row is written and no statement is added for a write, a batch, an index pass or the daily rebuild: a narrowing is read at the gate and never stored with a file. No lock is taken. The rights cache holds the same entries as before.

The last row is the honest profile. A page of `tree /` under `hide=["/archive"]`, where everyone may read `/archive`'s million rows, seeks through those rows in the index to fill the page. The same holds today for a relabel hole, which is short-lived; a narrowing's cut is not. The future direction is to split the everyone leg's range around the cut's spans, one seek per gap, as `visible_entries` already does for the caller's own pieces. It is not a declared limit, and the docstring of `Resolution.narrowed` states it.

## Left as it is

- **The version row's attribution.** It records actor, subjects, provenance and source identity (`src/vfs/models/version.py:157-159`), and not the narrowing, which limits a call and does not say who made it.
- **Search statistics.** Corpus statistics for ranking count rows a narrowing hides, as they count rows a grant hides today.
- **A narrowing on the wire.** `authority` never crosses the wire (`src/vfs/params.py:50`). A door that builds a narrowed authority from a token is 149-2's to decide.
- **Copying a session to a narrowed owner.** Spec 2 leaves a copy to another owner undesigned ("Left as it is"), and decision 18 makes a narrowed authority another owner.

## Tests

Each is written and seen failing before the code. Counts and states, never clocks. A statement count is of the statements a `before_cursor_execute` listener records, leaving out the statistics statements (`tests/support/statements.py`).

`tests/test_authority.py`:

- `test_narrowing_none_is_the_default_and_the_empty_value`: `Authority.of(p).narrowing is Narrowing.NONE`, `Narrowing() == Narrowing.NONE`, `Narrowing.NONE.is_none`.
- `test_hide_is_a_cap_at_none`: `Narrowing.of(hide=["/a"]) == Narrowing.of(caps={"/a": "none"})`.
- `test_an_unlawful_narrowing_is_refused`, one case each: a relative path, a path under `.vfs`, a rung off the ladder, an empty `within`, 65 caps, 65 within paths raise `ValueError`; an integer path and a `bytes` rung raise `TypeError`.
- `test_a_narrowing_is_held_in_canonical_form`: a `read_write` cap, a cap beneath an equal cap, a cap outside the within set and a within path beneath another are dropped; two narrowings built in different orders are equal and hash equal.
- `test_the_ceiling_is_the_lowest_covering_cap_and_none_outside_within`: a table of eight paths over one narrowing with three caps and two within paths.
- `test_a_road_is_a_strict_ancestor_of_a_within_path`.
- `test_meet_never_widens`: seeded, 500 pairs of random narrowings over a tree of 40 paths; at every path the meet's ceiling equals the lower of the two; `meet` is commutative, associative and idempotent.
- `test_narrow_keeps_everything_but_the_narrowing`: subjects, actor, provenance and source identity are equal before and after.
- `test_the_system_authority_cannot_be_narrowed`: `ValueError`, and the shape rule refuses a system actor built with a narrowing.
- `test_without_mount_rebases_caps_and_within`: a case for a within path above, at, beneath and beside the mount, and for a cap above, beneath and beside it.
- `test_a_narrowing_round_trips_its_payload`: `from_payload(to_payload(x)) == x` over the seeded set, and `to_payload(Narrowing.NONE) is None`.

`tests/storage/test_grants.py`:

- `test_a_cut_admits_no_row_by_spans_owner_or_label`: a row in the cut with a label of `read_write`, an owner equal to the caller, and a grant on its prefix is admitted at no rung.
- `test_reaches_refuses_a_creation_in_a_cut`.
- `test_narrowed_rights_agree_with_a_brute_force_oracle`: seeded, 200 narrowings over the grants world of `tests/support/grant_worlds.py`; `admits` on each row at each rung equals the oracle's `holds and ceiling >= rung`.
- `test_the_roots_of_narrowed_rights_name_the_within_paths_the_grants_cover`.

`tests/storage/database/test_rights.py`:

- `test_a_narrowed_resolution_leaves_the_cache_unchanged`: two calls under two narrowings of one caller issue one compile, and the cached entry equals the unnarrowed resolution.
- `test_a_narrowed_call_issues_the_statements_an_unnarrowed_call_issues`: on SQLite, for `read`, `ls`, a `tree` page, `glob`, `grep`, `search` and a `write` of 10,000 entries (marked `slow`), the count under a narrowing of 64 caps and 64 within paths equals the count with none.
- `test_the_largest_narrowing_fits_two_clauses_on_the_generic_floor`: through the floor dialect of `tests/support/floor_dialect.py`, no statement carries more than the floor's budget, and the clause count is at most 2.

`tests/support/narrowing_contract.py`, a `NarrowingContract` mixed into `TestMemoryConformance`, `TestSqliteConformance` and `TestPostgresConformance` in `tests/storage/test_conformance.py`, so it runs on the Postgres leg; where unit 179-1 has landed first, the family is `NarrowingRows` in `tests/support/contract/narrowing.py`, composed into `StorageContract`, and no leg's class line is edited (its decision 17):

- `test_ls_tree_and_glob_never_name_a_cut_row`.
- `test_grep_and_search_never_match_inside_a_cut_row`, through the scan and through the index.
- `test_a_row_everyone_may_read_is_hidden_inside_a_cut`.
- `test_an_owned_row_is_hidden_inside_a_cut`.
- `test_a_within_path_is_reached_by_a_road_of_bare_names`.
- `test_a_list_cap_shows_names_and_no_bodies`.
- `test_an_overwrite_under_an_add_cap_is_refused_with_the_narrowing_kind`, and a new file there is written.
- `test_the_trash_view_hides_a_cut_tombstone`.
- `test_traverse_never_names_a_cut_target`.
- `test_pages_of_a_narrowed_tree_drain_to_the_whole_narrowed_tree`: ten pages at `limit=10` equal the listing asked whole, and no `next_after` names a cut row.
- `test_no_answer_names_a_hidden_path`, the leak test: seeded, 100 narrowings over the grants world, every verb of `VERB_RUNGS` at every path of the world; no row path, error path, `data` value, message or `next_after` lies in a hidden region, and every row at a road path carries only its path and kind.

`tests/base/test_narrowing.py`, the kernel, with the doubles of `tests/support/base_doubles.py`:

- `test_a_hidden_path_answers_as_a_missing_one_and_calls_no_storage`: for `read`, `stat`, `ls`, `write` and `delete`, the error equals the storage's own answer for a directory the caller cannot see in kind, message, path, `data` and `source`, and `RecorderStorage` records 0 calls.
- `test_a_step_above_the_ceiling_is_refused_before_any_storage`: parametrised over every verb of `VERB_RUNGS` and each of the seven dispatch shapes; one error of `vfs.permission_denied.narrowing`, 0 storage calls.
- `test_a_verb_that_acts_beneath_is_refused_over_a_cap_beneath`: cascading `delete`, `move`, `copy`, `sweep`, `grant`, `revoke` and `set_posture`; a non-cascading `delete` and a `restore` at a path with a cap beneath pass.
- `test_the_refusal_names_no_cap_and_no_within_path`.
- `test_a_batch_with_one_hidden_entry_is_refused_whole`: 10,000 entries, one hidden; 0 storage calls. Marked `slow`.
- `test_the_narrowing_is_judged_before_busy_unsupported_and_read_only`: a hidden mount point answers `not_found`, not `busy`; a hidden path on a mount without the verb answers `not_found`, not `unsupported`.
- `test_a_hidden_mount_is_never_called_by_a_fan_out`.
- `test_a_hidden_mount_point_is_not_listed_and_a_road_mount_point_is_bare`.
- `test_each_storage_receives_the_narrowing_in_its_own_coordinates`: the recorded authority of a call to a mount at `/data` carries the rebased narrowing.
- `test_a_storage_without_the_trait_refuses_a_narrowed_call_as_unsupported`, and an unnarrowed call to it passes.
- `test_mount_and_membership_changes_by_a_narrowed_authority_are_refused`.
- `test_a_trash_address_is_judged_at_the_path_it_shows`.
- `test_a_default_authority_carries_its_narrowing`.

Elsewhere:

- `tests/results/test_facts.py::test_the_narrowing_kind_is_a_never_retried_child_of_permission_denied`.
- `tests/storage/test_protocol.py::test_trait_vocabulary_is_total_and_keyed` gains the `narrowing` key.
- `tests/shell/test_host.py::test_a_narrowing_refusal_exits_as_permission_denied`.
- `tests/test_sessions.py::test_a_narrowed_authority_owns_a_session_apart_from_its_source`, with whichever of this spec and spec 2 is built second: the same id under `a` and under `a.narrow(n)` names two sessions, and `a`'s key is spec 2's three-item key.
- `tests/session/test_fork.py::test_a_fork_carries_the_narrowing_of_its_source`, with whichever of this spec and spec 4 is built second.

## Scope

In: `src/vfs/authority.py` (`Narrowing`, `Cap`, `Authority.narrow`, the system rule); `src/vfs/paths.py` (the covering algebra, moved); `src/vfs/__init__.py` (the exports); `src/vfs/gates.py` (new); `src/vfs/base.py` (seven calls, the rebase in `_call_storage`, the mount and membership refusals); `src/vfs/listing.py` (the row filter and the fan-out skip); `src/vfs/storage/protocol.py` (the trait); `src/vfs/storage/grants.py` (`Rights.cut`); `src/vfs/storage/backends/database/resolution.py` (new, `Resolution` moved, `narrowed`); `src/vfs/storage/backends/database/rights.py` (`resolve_authority`, the write gate's kind); `src/vfs/storage/backends/database/backend.py` (the trait declared); `src/vfs/results/kinds.py` (the kind and its contract); `src/vfs/shell/host.py` (one row); `tests/lint/test_code_shape.py` (two rungs); the tests above.

Out:

- The owner-key line and the fork test: with spec 2 and spec 4, by the build order.
- A narrowing built from a token: 149-2.
- Splitting the everyone leg around the cut: the future direction under Cost.
- A per-verb deny: spec 6's session policies.
- Join and the leak notice: 148-3, which the reassessment finds moot.

## What the docs must say

- The docstrings of `Narrowing`, `Cap` and `Authority.narrow`, which `scripts/docs.sh check` exports to `documentation/reference/python-api/authority.md`; the module docstring of `vfs.authority`, where narrowing is "the narrowing the session has given up" (`authority.py:5`), becomes "the narrowing it carries".
- `documentation/reference/python-api/index.md:50`, whose line for `Narrowing` reads "what a session has given up", reads "what an authority may not do, whatever its grants".
- `documentation/reference/glossary.md` gains "narrowing", "cap" and "within".
- `documentation/reference/access-levels.md` gains a section, "Narrowing an Authority", with the example of the outcome and the rule that a hidden path answers as a missing one.
- `documentation/how-to/keep-a-session-for-each-conversation.md` gains one sentence: a sub-agent is given `fs.session(authority.narrow(profile), its_own_id)`, which starts empty.
- `Resolution.narrowed`'s docstring states the rows-visited profile and its future direction, under Cost.

## Earlier decisions this reverses

- **Spec 2's decision 6,** "`narrowing`: it limits what a call may do ... and does not change whose session it is", and its following paragraph, which leaves the host to give a narrowed part an id of its own. Reversed by decision 18 for a narrowing that is not `Narrowing.NONE`. Spec 2 is not built.
- **The source's section 2,** rules resolved by anchor depth. Replaced by decision 2.
- **The source's section 3,** a child session that ends with its parent and may add subjects. Dropped by decision 17.

## Not checked

- **Postgres.** No test was run on a server. The contract of decision 14 is inferred from reading the hole code, which the grants contract already runs on the Postgres leg.
- **Rows visited inside a cut.** The profile under Cost is read from `ranges.py:104-105`, not measured with `EXPLAIN` on either engine.
- **That every site that reads rights reads them through `admits`, `reaches`, `covers`, `covers_subtree` or the two pushdowns.** The sites listed in decision 14 were found by `grep` for `.whole`, `.clauses(`, `.entries(` and `visible_entries`; `traverse.py` and `trash.py` were not read line by line.
- **The line counts after the moves of decisions 6, 14 and 22.** Each is an estimate from the size of what moves.
- **Specs 2, 4, 6 and 7 and the unit 149-1.** None is built; each shape quoted is as its draft stands on `dev` at `27f3d24d`.
- **Whether a kernel row made by the cursor rather than by `MountListing` exists.** Decision 11 assumes every kernel row passes through `MountListing.called`, as `src/vfs/listing.py` reads; `src/vfs/cursor.py` was read for its storage wrap only.

## Choices to confirm

1. **Hide by glob as well as by path.** Taken: paths only. A glob cannot be compiled into a statement exactly: the tree's glob pushdown over-approximates and re-checks each survivor in Python (`src/vfs/storage/backends/database/pathterms.py:11-21`), and an exclusion built on an over-approximation would hide too much. Adding globs later, with a Python check on fetched rows and its cost stated, is an addition.
2. **A narrowed authority is another owner of sessions.** Taken: yes, decision 18, departing from spec 2's decision 6. It is additive: an unnarrowed key is unchanged, and no narrowed session can exist before this spec lands. The other side keeps spec 2's rule and leaves a host to choose a separate id.
3. **The system authority cannot be narrowed.** Taken: it raises. Allowing it later is an addition; refusing it later would break callers.
4. **The bounds of 64 caps and 64 within paths.** Taken: 64 each, as `MAX_SUBJECTS`. Raising a bound later is an addition.
5. **A storage without the trait.** Taken: a narrowed call to it is refused `vfs.unsupported`. The other side is a kernel filter of its rows after the fetch, which costs what the problem section rejects; it can be added later.
6. **Mount and membership changes by a narrowed authority.** Taken: refused outright. Judging a mount change by its paths and a membership change by the group's prefixes can be added later.
7. **The name of the method.** Taken: `Authority.narrow`, the bare verb. The other is `narrowed`, after the frozen-value convention; a rename before the release is cheap.

## One line

`Authority.narrow(Narrowing.of(within=, hide=, caps=))` takes rights away by a profile that can only intersect, the kernel answers a hidden path as a missing one before any lookup and refuses a capped step as `vfs.permission_denied.narrowing`, the database storage cuts the same paths inside every statement through the holes it already compiles, and a session or a fork carries the narrowing of the authority it was made with.
