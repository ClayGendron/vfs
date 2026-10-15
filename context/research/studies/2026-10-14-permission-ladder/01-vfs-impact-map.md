# L1 — What `list` and `contribute` touch inside vfs (impact map, measured on the live tree)

Date: 2026-10-14. Researcher L1 (internal impact). Repo at `main` (`e8b8d9a`), working tree as found.
Evidence labels: EXECUTED (a script or grep ran), READ (file read, cited `file:line`), INFERRED (my reasoning).
Scripts and outputs beside this file: `l1_road_baseline.py` / `.out`, `l1_compile_cost.py` / `.out`.

## Summary

The ladder is one `Literal` and one rank dict in `src/vfs/storage/grants.py`, and the pure resolver is generic over it: `resolve`, `inflight_regions`, `posture_regions`, `Rights.need` and `admits` all compare by rank and never name a level (READ). The addendum's "one `LEVEL_RANK` entry per rung" is true for that module. It is not true for the storage half. There, the ladder is assumed to have exactly two non-`none` rungs in six places: `Resolution` has two fixed fields `read` and `write` (`rights.py:160-165`), `resolve_authority` compiles exactly those two (`rights.py:318-322`), `weight` sums exactly those two (`rights.py:258`), `WriteGate.targets`/`subtrees`/`row` pick between them with `== "read"` / `== "read_write"` literals (`rights.py:543,581,629`), the grant verbs refuse any level but those two (`rights.py:1132-1133`), and `params.GRANTABLE_LEVELS` is the hand-written set `{"read","read_write"}` (`params.py:54`). The verb gates in `backend.py` carry eleven level literals (counted, EXECUTED). The row label is an integer rank: inserting `list` below `read` renumbers every stored label, so the landing needs a `rebuild_labels` pass and a `SCHEMA_FORMAT_VERSION` bump (`rows.py:139`; `engine.py:562` refuses a mismatched mount). `contribute` costs almost nothing new: the write gate already splits create from modify, and the owner floor is already an arm of the `read_write` compile. `list` is the one rung needing new machinery, exactly as the addendum said: `Visibility.admits` returns a bool and every read verb treats a row as whole-or-absent; the road (`reads.py:624-627`, `ROAD_FIELDS`) already has the bare-row shape `list` needs, and the baseline script shows it working today for `ls`, `tree`, `stat`, `glob` (EXECUTED).

## 1. Inventory: every site keyed on a grant level

Method (EXECUTED): `grep -rn -E 'GrantLevel|LEVEL_RANK|GRANT_LEVELS|GRANTABLE_LEVELS|POSTURE_LEVELS|POSTURES\b|GateMode|everyone_level|\.need\b|"read_write"|Posture\b|root_level|resolution\.(read|write)|\.(write|read)\.admits|\.reaches\('` over `src/vfs` and `tests/`. 164 hits in `tests/` across 26 files; the `src/vfs` hits are classified below. `"read_write"` as a literal: 30 in `src/vfs`, 69 in `tests/`. Note `src/vfs/permissions.py` (`Permission = Literal["read","read_write"]`, `permissions.py:97`) is the **mount-binding** permission axis of `base.py`, not the grant ladder; it shares the two words but is a separate plane (router-side, no `none`, no rows). It is listed once and then left alone.

| # | Site | What it assumes about the ladder today | What changes for `list` | What changes for `contribute` |
|---|---|---|---|---|
| 1 | `grants.py:76-85` `GrantLevel`, `GRANT_LEVELS`, `LEVEL_RANK` | The order is the dict; `GRANT_LEVELS` derives from the Literal. Ranks are dense ints 0,1,2 | Add the word; ranks renumber (`list`=1, `read`=2, ...) | Add the word (`contribute`=3, `read_write`=4) |
| 2 | `grants.py:87-90` `Posture`, `POSTURE_LEVELS` | Three posture words, hand-written map | `listed → list` | `inbox → contribute` |
| 3 | `grants.py:296` `posture_regions` | Iterates `get_args(GrantLevel)` — generic | nothing | nothing |
| 4 | `grants.py:322` `inflight_regions` | `LEVEL_RANK[...] >= need` — by rank | nothing | nothing |
| 5 | `grants.py:370-373,399-404` `Rights.level`, `need`, `reaches`, `admits` | Compare by rank; one `Rights` is one level | nothing in the type; see §4 for a per-row level | nothing |
| 6 | `grants.py:531` `resolve` row filter `LEVEL_RANK[row.level] >= need` | Total order: a row admits at every level at or below its own | A `list` row admits only at need=`list`; `read`+ rows admit at `list` | A `contribute` row admits at `list`, `read`, `contribute`; not at `read_write` |
| 7 | `rights.py:160-165` `Resolution(read, write, root_level)` | **Exactly two non-none levels**, named fields | Needs a `list` compile: third field or a map | Needs a `contribute` compile: fourth |
| 8 | `rights.py:293` system actor `Resolution(everything("read"), everything("read_write"), "read_write")` | two fields | add `everything("list")` | add `everything("contribute")` |
| 9 | `rights.py:318-322` `resolve_authority` compiles `"read"` and `"read_write"` | two compiles per miss | +1 compile | +1 compile |
| 10 | `rights.py:258` `weight` iterates `(resolution.read, resolution.write)` | two fields | sum over all compiles | same |
| 11 | `rights.py:328-332` `posture_refusal` compares `LEVEL_RANK[root_level] >= LEVEL_RANK[level]` | by rank — generic | nothing | nothing |
| 12 | `rights.py:543` `WriteGate.targets`: `rights = read if mode == "read" else write` | the mode picks one of two compiles | a `GateMode` cannot ask for `list` | create/upsert must pick `contribute`; modify picks `read_write` |
| 13 | `rights.py:568-581` `WriteGate.subtrees(level)`: `read if level == "read" else write` | two-way literal switch | n/a | must address `contribute` compile when a cascade is judged at `contribute` (it is not — see §6) |
| 14 | `rights.py:621-631` `WriteGate.row(..., level)`: `if level == "read_write" and not write.admits` | `read` is a no-op branch | n/a | same |
| 15 | `rights.py:647-695` `_decide` | `write = resolution.write` for both create and modify; `creating = mode in ("create","upsert")` | road rule (`key in road → denied`) stays; a `list`-level target must still refuse every write | the creation legs (`write.reaches` at 676, 693) must read the `contribute` compile; the occupied-path leg (690) keeps `read_write` |
| 16 | `rights.py:1132-1133` `_grant_refusal`: `level not in ("read","read_write")` | hand-written two-element check | accept `list` | accept `contribute` |
| 17 | `rights.py:751` `revoke_rows` passes `"read"` as a dummy level; `rights.py:834` `set_posture` passes `"read_write"` | dummy literal | nothing | nothing |
| 18 | `rights.py:838,927` `POSTURE_LEVELS[posture]` | map lookup — generic | nothing | nothing |
| 19 | `rights.py:141` `RIGHTS_FIELDS = {owner_id, everyone_level}`; `judged_columns` | the row carries one label | nothing | nothing |
| 20 | `rights.py:379-399` `Visibility(rights)`, `admits → bool` | **one level per view; a row is admitted or absent** | the new machinery (§4): two needs or a per-row level | nothing |
| 21 | `rights.py:437-479` `Visibility.road`, `seen_kinds` | road derived after the fetch from `rights.roots` + owner probes + everyone probe at `rights.need` | see §5 | nothing |
| 22 | `rights.py:1020` `_units`: `everyone_level >= rights.need` | by rank | nothing | nothing |
| 23 | `ranges.py:115,122-123` three-seek predicate: `everyone_level >= need`, `< need` | by rank | nothing (§2) | nothing |
| 24 | `labels.py:1-9` docstring "``0`` none, ``1`` read, ``2`` read_write" | documents the dense numbering | docstring + renumbering | same |
| 25 | `labels.py:154-156` `label_of = LEVEL_RANK[level_at(...)]` | by rank | nothing | nothing |
| 26 | `labels.py:273,378,381` `Relabeller._planned`, `rebuild_labels` | by rank, iterate regions — generic | one more region per rung (a loop) | same |
| 27 | `rows.py:475,489` `everyone_level SmallInteger NOT NULL`, index `(everyone_level, path)` | an integer; domain not CHECKed | nothing in DDL; stored values renumber | same |
| 28 | `rows.py:139` `SCHEMA_FORMAT_VERSION = 22`; `engine.py:562-569` refuses a mismatch | labels are part of the format | **bump + rebuild** (renumbering) | same bump |
| 29 | `engine.py:536` root row minted with `LEVEL_RANK[POSTURE_LEVELS[self.posture]]`; `engine.py:136,159` `posture: Posture = "open"` | generic | nothing | nothing |
| 30 | `topology.py:315,370,453` move/restore relabel via `label_of` | generic | nothing | nothing |
| 31 | `writes.py:1190,1206` mint stamps `everyone_level` from `labels_for`; `trash.py:106` tombstone keeps it | generic | nothing | nothing |
| 32 | `backend.py:1417,1456` `_resolution(level)`, `_gate(level="read_write")` | the level is only the posture-refusal threshold | gates that need `list`/`contribute` pass that word | same |
| 33 | `backend.py:628` write `"upsert"`; `:660` edit `"modify"`; `:689-691` delete `"modify"` + `subtrees("read_write")`; `:749-751` restore `row(.., "read_write")` + `subtrees`; `:787-790` sweep; `:820` mkdir `"create"`; `:865-866` mkedge source `"modify"` target `"read"`; `:894` rmedge `"modify"`; `:979` grants `level="read"`; `:1569-1580` transfer `need = "read_write" if move else "read"`, sources `modify`/`read`, dests `"create"` | **eleven literals** spread over the verbs (EXECUTED count) | none of these yields a bare row | the create legs become `contribute`; everything else stays |
| 34 | `backend.py:1440-1445` `_viewed`: `Visibility(resolution.read, ...)` for every read verb | one view at `read` | the view must carry `list` too | nothing |
| 35 | `reads.py:96-98` `ROAD_FIELDS = {path, kind}`; `:624-627` `road_observation`; `:629-674` `_screen`; `:795-848` `_children_by_parent`; `:246-274` tree; `:356-365` glob; `:557-574` `_point_rows` (stat) | a bare row exists only for a road **directory** | the same projection serves a `list`-level **file or directory** | nothing |
| 36 | `grep.py:261,303` `view.admits(mapping)` post-filter | whole-or-absent | `list` rows excluded (they are not `read`) | nothing |
| 37 | `glean.py:297-315,380,574,646-651,699+` `_visible_lexicon`, `view.clauses()`, `view.admits` | statistics over the `read`-visible set | `list` rows excluded from statistics and candidates | nothing |
| 38 | `params.py:54-55` `GRANTABLE_LEVELS = {"read","read_write"}`, `POSTURES = get_args(Posture)` | hand-written set | add `list` (or derive from `GRANT_LEVELS - {"none"}`) | add `contribute` |
| 39 | `params.py:301,315` `ParamSpec("level", choices=GRANTABLE_LEVELS)`, `("posture", choices=POSTURES)` | derived | nothing | nothing |
| 40 | `base.py:1548-1600`, `session.py:373-388`, `protocol.py:370-393` grant/posture signatures typed `GrantLevel`/`Posture` | the Literal | nothing beyond the Literal | same |
| 41 | `ops.py` | no verb→rung mapping at all; `MUTATING_OPS`, `READ_OPS` etc. are routing classes | the table (§7) | the table |
| 42 | `tests/support/oracles/grants.py:74-88` `everyone_rank`, `subject_rank` (owner floor = `LEVEL_RANK["read_write"]`) | by rank; owner floor word hard-coded | nothing | owner floor stays `read_write` |
| 43 | `tests/support/grant_worlds.py:76-77` `_NAMED_LEVELS = ("read","read_write")`, `_ALL_LEVELS` | enumerates the rungs | add `list` to both tuples so random worlds exercise it | add `contribute` |
| 44 | `tests/storage/test_grants.py:66,215,336,428` parametrise over `("read","read_write")`; assert `posture_regions({}) == {none, read, read_write}`; `need == 1` / `== 2` | enumerates rungs; asserts dense ranks | ranks and the region dict change | same |
| 45 | `tests/storage/database/test_rights.py:72` `_POSTURE_OF`; `:166,201` loop over two levels; `:233,423` `"everyone_level >= 1"` in SQL; `:634,650,872` `Resolution(read, write, "none")` | two fields; rank 1 = read | `>= 1` becomes the `list` rank; `Resolution` ctor sites | same |
| 46 | `tests/storage/database/test_labels.py:131,172,203,307` `everyone_level=2`, `stale == {0,1}` | dense ranks | renumber | same |
| 47 | `tests/storage/database/test_coherence.py` (9), `test_races.py:449`, `test_trash.py:1300`, `test_reads.py:78`, `test_engine.py:235`, `test_dialects.py:633`, `tests/models/test_rows.py:441` — raw `everyone_level=2` in inserted rows | 2 = read_write | the literal becomes the new `read_write` rank (one constant would fix all 15) | same |
| 48 | `tests/support/grants_contract.py` (13 sites), `test_grant_routing.py:171`, `test_trash.py:932,963` call `grant(level="read"/"read_write")` | the words | unchanged; new tests for `list` | new tests for `contribute` |

READ for every row; the counts are EXECUTED.

## 2. The row label under a five-rung ladder

- **Domain.** `everyone_level` is `SmallInteger NOT NULL` with no CHECK (`rows.py:475`). The domain is whatever `LEVEL_RANK` says (`labels.py:156`). Nothing in SQL assumes three values. The index `(everyone_level, path)` (`rows.py:489`) is agnostic.
- **The renumbering is the real cost.** `LEVEL_RANK` is dense: `none=0, read=1, read_write=2` (`grants.py:83`). `list` sits between `none` and `read`, so `read` becomes 2, `contribute` 3, `read_write` 4. Every stored label written as 1 or 2 is then wrong. There is no "insert a rung without renumbering" with dense integers. `rebuild_labels` (`labels.py:359-384`) recomputes every row from the posture rows — the exact tool — and ADR 020 rule 2 says an incompatible change to stored values bumps `SCHEMA_FORMAT_VERSION` (`rows.py:139`; the refusal at `engine.py:562-569` says "upgrade or re-provision"). INFERRED: the landing is "bump the format; first touch of an old mount refuses; a repair path (or re-provision) runs `rebuild_labels`". An alternative is sparse ranks (`none=0, list=10, read=20, ...`) so a future rung needs no renumber — it still renumbers *this* time, so it buys only future insurance.
- **The relabel.** `Relabeller` and `relabel_spans` take a `rank: int` (`labels.py:273,329-335`) and `rebuild_labels` loops over `posture_regions` (`labels.py:377-381`), which iterates `get_args(GrantLevel)` (`grants.py:296`). Two more rungs mean two more (usually empty) regions in the rebuild loop. Nothing else changes.
- **The three-seek everyone leg.** `everyone_level >= :need` (`ranges.py:115`) and the disjoint `< :need` on the piece branches (`ranges.py:122-123`) are rank comparisons; a view at need=`list` passes rows labelled `list` or above, a view at need=`read` passes `read` or above. The predicate shape does not change. The **count** of distinct `need` values a single verb issues does (§4): a `ls` that wants both the bare set and the readable set either runs the statement at need=`list` and sorts rows by label in Python, or runs two statements.
- **Anything that assumes exactly three values?** In `src/vfs`: only the `labels.py:1-9` docstring and the `rights.py:160` `Resolution` shape (two rights, not three labels). In tests: `test_grants.py:215` (`posture_regions({}) == {"none": (), "read": (), "read_write": ()}`), `test_labels.py:203` (`stale == {0, 1}`), and the 15 raw `everyone_level=2` inserts (#47). The oracle (`oracles/grants.py`) is by rank and survives.

## 3. Rights compile per level

- `Resolution` is a `NamedTuple(read, write, root_level)` (`rights.py:160-165`). `resolve_authority` builds it with exactly two `resolve(...)` calls (`rights.py:318-322`); the system actor gets two `Rights.everything` (`:293`). `weight` iterates the two fields by name (`:258`). `WriteGate` reads `.read`/`.write` by name (`:543,581,629,670`), `Visibility` is built from `.read` (`:531`, `backend.py:1445`), `list_grants` and `_grant_refusal` read `.read.reaches` / `.write.reaches` (`:801-803,1136-1138`).
- **The cache key does not care.** `RightsKey = (subjects, stamp, marks)` (`rights.py:168-173`); the value is whatever `Resolution` is. `_Cached` stores `weight(resolution)`. Adding fields to `Resolution` touches no key logic. The invalidation rule (a grant stamps its grantee, a membership write its member, a posture change nobody) is level-agnostic. INFERRED: the right shape is `Resolution(rights: Mapping[GrantLevel, Rights], root_level)` with an `at(level)` accessor, so `weight`, the system path and the gate stop naming fields; or keep named fields `list/read/contribute/write` — four names in six places versus one map.
- **What a third and fourth compile cost, measured** (EXECUTED, `l1_compile_cost.py`): two `resolve` calls over 20 / 400 / 4,000 grant rows take 0.2 / 1.4 / 14.3 ms together; the `read` compile weighs 6.7 KB / 111 KB / 1.1 MB and the `read_write` compile 2.6 KB / 29 KB / 275 KB (it holds fewer rows). Four compiles roughly double both numbers in the worst case. **But** the script also shows the dedupe: `Rights` at level L depends only on the rows with rank >= L (`grants.py:531`), so when no row carries exactly `list`, `Rights(list) == Rights(read)`, and when none carries exactly `contribute`, `Rights(contribute) == Rights(read_write)` — equality held in every trial. The compile can test "any row at exactly this level, or any pending posture at it" and alias the neighbouring `Rights` object; `weight` must then count each distinct object once. With that, the cache weight grows only for principals who actually hold a `list` or `contribute` row.
- The `RIGHTS_CACHE_BYTES` docstring ("an ordinary caller at a hundred thousand users weighs some 56 KB", `rights.py:133-139`) is written for two compiles and should be re-measured after the landing.

## 4. The `list` rung's new machinery: visible row, hidden body

Today (READ): `Visibility.admits(mapping) -> bool` (`rights.py:398-399`); every read verb either shows the whole row (`_observe`, `reads.py:872`) or treats it as a miss, and only a hidden **directory** on the road gets the bare `road_observation` (`reads.py:624-627`, `ROAD_FIELDS = {path, kind}`, `:96-98`). The baseline run (`l1_road_baseline.out`, EXECUTED) shows that shape in `ls`, `tree`, `stat` and `glob` for `/projects` and `/projects/alpha`: `populated=['kind','path']`.

Which verbs project a `list`-level row bare, which exclude it (INFERRED from each verb's code path):

| Verb | Code path | Under `list` |
|---|---|---|
| `ls` | `ls_rows` → `_screen` + `_children_by_parent` (`reads.py:179-222, 795-848`) | the target and each child at `list`: bare. Listing a `list` directory shows its `list`+ children, like a road directory today (ADR 070 rule 3) |
| `tree` | `tree_rows` → `_visible_rows` + bare ancestors (`reads.py:224-286`) | `list` rows in the subtree: bare; the fetch runs at need=`list` |
| `glob` | `glob_rows` → `view.admits` then `view.road` for hidden directories (`reads.py:356-365`) | `list` matches: bare; `kind=` filter still applies (kind is in the bare set) |
| `stat` | `_point_rows` (`reads.py:544-574`) | bare, as a road directory answers today |
| `read` | `read_rows` (`reads.py:139`) | excluded: `permission_denied` for a file the caller can name (it is visible), **not** `not_found`. This is the one place a `list` row answers differently from a hidden one — and it is the spec's acceptance criterion. A `list` directory answers `wrong_kind` as a road directory does today (baseline: `read /projects → wrong_kind`) |
| `grep` | `grep.py:261,303` post-filter | excluded; the candidate budget should count `read`-visible candidates (open-questions gap 1 is unchanged) |
| `glean` | `glean.py:297-315` visible lexicon, `:380,574,651` admits | excluded from candidates **and** from statistics. "Visible set" in ADR 065 rule 5 must be read as "the `read` set": a `list` row has a name but no body, and names carry no term statistics. The bare set must not move `N` or `df` |
| `graph` (spec 164) | not landed | a `list` node is traversed and returned bare (path, kind, depth); its `columns` are not populated; edges touching it are returned |
| `grants` | `list_grants` (`rights.py:801`) uses `read.reaches` | INFERRED: a `list` path should answer the same as a road path — `not_found` — or the spec decides it is visible enough to list one's own rows. Pin it |
| mutations | `_decide` (`rights.py:683-694`) | a `list` target behaves as a road directory: `denied`, not `not_found` (the gate already does this for the road via `key in road`) |

How `Visibility` carries two needs — the two options:

- **(A) Two compiles, one view.** `Visibility` holds `Rights` at `list` and at `read` (both from `Resolution`). `admits(mapping)` returns the **rung the caller holds on the row** — `"none" | "list" | "read"` (or a `Rank`) — by trying the higher compile first (two bisects at most). The pushdown (`narrow`/`entries`/`clauses`) runs at the lower need (`list`) for the listing verbs and at `read` for `read`/`grep`/`glean`. The road check stays as it is (§5). Cost: one more compile per miss (§3), two bisects per row on the listing verbs, zero change to the predicate shape.
- **(B) One compile at `list` with per-row levels inside `Rights`.** `Rights` would need the level of each span (a `list` span versus a `read` span) — the range algebra today is a flat `RangeSet` with no per-span payload (`grants.py:100-108`), and the meet across members would become a min over levels per span. That is a rewrite of the pure resolver and the three-seek predicate. Not worth it: (A) is strictly less code and keeps ADR 072/073 untouched.

Recommendation: (A). `admits` returns a level (a `Rank`), and the callers compare: `>= need_of(verb)`. The seven in-tree `admits` callers (EXECUTED count: `reads.py` 6, `glean.py` 5, `grep.py` 2, `rights.py` 7, `backend.py` 1, `grants.py` 4 — 25 call sites in `src/vfs`) each state the rung they need, which is exactly the table of §7 flowing down.

## 5. The road and `list`

What the road is today (READ): `Visibility.road(candidates)` (`rights.py:437-464`) answers, for hidden directory paths the verb already fetched, whether a visible row lies beneath — from three sources: ancestors of existing `rights.roots` (`_existing_roots`), one `EXISTS` probe per owner arm (`_owned_beneath`), one `EXISTS` on the everyone label at `rights.need` (`_open_beneath`). `seen_kinds` (`:466-479`) folds the road into the descent map so a hidden ancestor reads as missing. The road is **not** in `Rights`: `Rights.roots` (`grants.py:375,689-697`) is the covered prefixes whose parent is not covered — the *input* to the road, not the road. `_roots` is computed at compile time; the road directories are found per call, from rows, after the fetch. So the addendum's note is right: the road is not compiled into the caller's pieces.

Is the road "derived `list`"? Yes, semantically: a road directory already shows exactly the `list` projection and already refuses every write as `denied` (`rights.py:683-685`, ADR 070 rule 4). The baseline run confirms (`mkdir /projects/gamma → permission_denied`). So the ADR can state: *a directory is at `list` to a caller when a grant says so or when a row the caller holds `list` or more on lies beneath it.* Note the recursion: with a `list` rung, the road is derived from `list`-visible rows, not only `read`-visible ones — `_open_beneath` probes at `rights.need`, so it must probe at the `list` compile's need, and `_owned_beneath` at the `list` compile's owner arms. One code change, no new statement shape.

Unify or keep separate?

- **Unify (compute the road into `Rights` at compile time).** Would require knowing, at compile time, which ancestor directories of the caller's roots and owned rows *exist* — the road is "computed from rows that exist, never from grant prefixes alone" (ADR 070 rule 1). The owner-arm part depends on which rows the caller owns, which changes on every write and is unbounded (a member may own rows anywhere under an arm). So the compile would be invalidated by ordinary writes, which today never touch the cache (the key is grant/membership stamps + marks, `rights.py:168-173`). Cost: a new invalidation class, a compile that reads the entries table, and ancestor spans added to `Rights.spans` at a `list` level — i.e. option (B) of §4 through the back door. Not recommended.
- **Keep separate (the road stays a per-call derivation; `list` is a grant).** Cost: the listing verbs do what they do now — one `road` probe for the hidden directories among their candidates — plus the `list` compile. The two sources meet in one place: `seen_kinds`/`_screen` already merge "admitted" and "road" into one map; with (A) they merge "level >= list" and "road" into one map, and the bare projection is one function. INFERRED: the only semantic seam is a **file** on the road — files are never on the road (the road is directories, `rights.py:438`), and a file at `list` is a new case that `_screen`'s `doors` filter (`reads.py:667`, directories only) does not need to change for, because a `list` file is admitted by the compile, not by the road.

Recommendation: keep them separate; state in the ADR that the road is derived `list` (same projection, same refusals) so the two are one *contract* with two *sources*.

## 6. `contribute` against the write gate, verb by verb

The gate today (READ, `rights.py:539-566, 647-695`): `targets(mode)` picks `resolution.read` for `mode == "read"` else `resolution.write`; `_decide` treats `create` and `upsert` as `creating`; an **occupied, visible** target under `upsert`/`modify` is judged by `write.admits(row)` — which carries the owner floor as an owner arm (`grants.py:389-391, 414-418`); a **fresh** target is judged by `write.reaches(key, label)` (spans or everyone label, no owner — a creation has no owner yet); a road parent refuses. So the addendum's sentence is **confirmed with one correction**: it is not "`GateMode.create` passes" as a mode, it is *the creation branch* (`creating` and the target is absent) that must consult the `contribute` compile, while *the occupied branch* (`key in seen`, line 686-690) keeps consulting `read_write`, where the owner floor lives. `upsert` is one mode that lands in either branch depending on the row, which is exactly the shape `contribute` wants.

Also relevant: an overwrite **clobbers `owner_id`** (`writes.py:97-121`, `_CLOBBER_COLUMNS` includes `owner_id`) and `edit` keeps the row's owner (`writes.py:274`). So under `contribute` a write over another principal's file must be refused at the gate — and it will be, because that path is the occupied branch at `read_write`.

| Verb | Gate today | Under `contribute` (INFERRED from the gate's branches) |
|---|---|---|
| `write` (new path) | `upsert`, fresh → `write.reaches` (`:693`) | passes at `contribute` |
| `write` (existing path, `overwrite=True`) | occupied → `write.admits` (`:690`) | own row: passes (owner arm); another's row: `denied` |
| `write` (existing, `overwrite=False`) | gate passes; `already_exists` from `writes.py:632` | unchanged (the gate is before the exists check — a `contribute` caller still learns the name is taken, which it may: the row is visible to it at `read`) |
| `write(parents=True)` minting ancestors | `minted and write.reaches(ancestor)` (`:675-676`) | the minted ancestors are creations: `contribute` on the chain |
| `edit` | `modify` (`backend.py:660`) → occupied → `write.admits` | own row only. "Append" as an edit that only adds: **not expressible** — `edit` is a replace list (`EditOperation`, `writes.py:255-277`) with no add-only mode; the gate cannot see what the edit does. So "append" for `contribute` means *create a new file* (write to a fresh path) and nothing else, unless the spec adds an append verb or an `edit(append=...)` form. Say so in the ADR |
| `mkdir` | `create` (`backend.py:820`) | passes at `contribute`; `parents=True` as write |
| `delete` | `modify` + `subtrees(.., "read_write")` if cascade (`:689-691`) | own row only; a cascade over a directory requires `read_write` on every row beneath — i.e. a contributor deletes its own files, not folders holding others' rows. `subtrees` pages at `rights.need` — unchanged |
| `restore` | `row(.., "read_write")` + `subtrees` (`:749-751`) | own tombstone only (the owner floor stands in the trash, `rights.py:54-58`) |
| `move` | sources `modify` + `subtrees("read_write")`, dests `create` (`backend.py:1569-1580`) | source: own row; dest: `contribute`. INFERRED: a move out of a contribute prefix is "remove your own row" — allowed |
| `copy` | sources `read` + `subtrees("read")`, dests `create` | dest at `contribute`; source needs `read` (a `list` source refuses) |
| `mkedge` | source `modify`, target `read` (`:865-866`); edges carry no owner (`edges.py:144`) | source must be the caller's own row (edges are "part of" the source row). Target `read` |
| `rmedge` | source `modify` (`:894`) | own source row only |
| `sweep` | developer plane; `read_write` whole | unchanged (needs `read_write`/`manage`) |
| `grant`/`revoke`/`posture` | `_grant_refusal` needs `write.reaches` (`:1136`) | unchanged: `read_write` (no self-grant at `contribute`) |
| `grants` | `read.reaches` else `not_found`; all rows only at `write.reaches` (`:801-805`) | a contributor sees its own rows, like a reader |

One subtlety for the spec: `_decide` judges *creation* by `reaches` = spans ∪ everyone label (`grants.py:384-386`), with **no** owner leg (nothing to own yet). Under `contribute` the owner floor plays no role in creation; it plays its role only on the occupied branch. That is the right split and it already exists.

## 7. The verb-to-rung table in `ops.py`

Today `ops.py` carries routing classes only (`MUTATING_OPS`, `READ_OPS`, `GRANT_OPS`, ... `ops.py:61-101`) and no rung. The gates carry eleven literals in `backend.py` (§1 #33) and three in `rights.py` (#12-14). Proposed shape (READ constraints: `Op` is a `Literal` at `ops.py:33-59`; some verbs judge two paths; some judge a creation and a modification in one call):

```python
# ops.py — after the op sets
Rung = Literal["none", "list", "read", "contribute", "read_write"]   # the ladder's words, re-exported by grants.py


class Needs(NamedTuple):
    """The rungs one verb needs: on the rows it returns or changes, and on the rows it only passes through."""

    primary: Rung                # the target: what it reads, or the row it modifies
    create: Rung | None = None   # a fresh target (write, mkdir, copy/move dest, minted parents)
    traverse: Rung | None = None # an intermediate node a walk passes (graph), or a source it only reads (copy, mkedge target)


VERB_RUNGS: Final[dict[Op, Needs]] = {
    "read":   Needs("read"),
    "stat":   Needs("list"),
    "ls":     Needs("list"),
    "tree":   Needs("list"),
    "glob":   Needs("list"),
    "grep":   Needs("read"),
    "glean":  Needs("read"),
    "graph":  Needs("read", traverse="list"),         # spec 164: read on returned contents, list on the path
    "write":  Needs("read_write", create="contribute"),
    "edit":   Needs("read_write"),
    "mkdir":  Needs("read_write", create="contribute"),
    "delete": Needs("read_write"),
    "restore": Needs("read_write"),
    "sweep":  Needs("read_write"),
    "move":   Needs("read_write", create="contribute"),
    "copy":   Needs("read", create="contribute"),
    "mkedge": Needs("read_write", traverse="read"),   # source modify, target read
    "rmedge": Needs("read_write"),
    "run":    Needs("read"),                          # today: no write gate; its own axis is parked
    "grant":  Needs("read_write"),
    "revoke": Needs("read_write"),
    "grants": Needs("read"),
    "posture": Needs("read_write"),
    "add_member": Needs("read_write"),                # system actor only; the rung is moot but the row exists
    "remove_member": Needs("read_write"),
}
```

How the gates read it instead of their literals:

- `backend.py:1440-1445` `_viewed(op, ...)`: `Visibility(resolution, need=VERB_RUNGS[op].primary, ...)` — the view carries the rung the verb returns rows at; with (A) the listing verbs pass `list` and project a row bare when `admits(row) < "read"`.
- `rights.py:543` `WriteGate.targets(targets, mode)`: `mode == "read"` → `needs.traverse or needs.primary`; `creating` → the creation legs (`:676,693`) use `resolution.at(needs.create)`, the occupied leg (`:690`) `resolution.at(needs.primary)`.
- `backend.py:691,751,790,1580` `subtrees(level)`: `needs.primary` for move/delete/restore/sweep, `needs.traverse` for copy.
- `backend.py:979` `grants` passes `level="read"` to `_gate` → `VERB_RUNGS["grants"].primary`.
- `_resolution(level)` for the posture refusal → `VERB_RUNGS[op].primary` (anonymous needs the root to give everyone at least the verb's rung).

Drift test sketch (`tests/test_ops.py`, beside the existing `ALL_OPS` drift test the module docstring mentions):

```python
def test_every_op_names_its_rungs() -> None:
    assert set(VERB_RUNGS) == set(get_args(Op))                     # one entry per verb, no strays
    for op, needs in VERB_RUNGS.items():
        assert needs.primary in GRANT_LEVELS and needs.primary != "none"
        assert needs.create in (None, *GRANT_LEVELS) and needs.traverse in (None, *GRANT_LEVELS)
        if op in MUTATING_OPS - {"copy"}:
            assert LEVEL_RANK[needs.primary] >= LEVEL_RANK["contribute"]   # a mutation never sits below contribute
        if op in READ_OPS:
            assert needs.create is None                                     # a read never mints
        if needs.create is not None:
            assert LEVEL_RANK[needs.create] <= LEVEL_RANK[needs.primary]    # creating is never harder than modifying
    assert VERB_RUNGS["graph"].traverse == "list"                           # the pin spec 165 flips


def test_the_gates_read_the_table(monkeypatch) -> None:
    # Mutation testing in the small: flip one entry and the corresponding verb's refusal must change.
    ...
```

A second drift test should grep-pin that `backend.py` and `rights.py` contain no `"read_write"`/`"read"` literal passed to `_gate`, `targets`, `subtrees` or `row` — a source-level pin is crude but is how the repo already pins the router's public surface to `ALL_OPS`.

## 8. Posture words

- Validation: `Posture = Literal["open","shared","private"]` (`grants.py:87`); `POSTURE_LEVELS` (`:90`); `params.POSTURES = get_args(Posture)` (`params.py:55`) feeds `ParamSpec("posture", choices=POSTURES)` (`:315`) which the router's `_gate_params` runs first on every verb (`base.py:2780-2795`). The storage `posture` verb takes a `Posture` (`backend.py:945`, `protocol.py:393`, `session.py:388`, `base.py:1587`) and `set_posture` maps it with `POSTURE_LEVELS[posture]` (`rights.py:838`). `posture_row` for first touch (`:922-931`) and `engine.py:136,159,536` use the same map.
- Relabel path: `set_posture` writes the everyone row with the mapped level, marks the relabel, and `Relabeller` rewrites the subtree to `LEVEL_RANK[level_at(...)]` (`labels.py:273`). Level-agnostic.
- Cost of `listed` and `inbox`: two Literal members, two map entries, two docstring sentences (`base.py:1588-1592`, `backend.py:946`), the test map `_POSTURE_OF` (`test_rights.py:72`) and `grant_worlds._ALL_LEVELS`. "Everyone capped at `read_write`" is already structural: `POSTURE_LEVELS` is the only writer of everyone rows (`_grant_refusal` refuses `principal is None` only through `set_posture`, and `*` is in `RESERVED_PRINCIPALS`, `rights.py:144-146`), so no posture word can map above `read_write` unless someone adds one. The `manage` question does not touch this.
- One wrinkle (INFERRED): an `inbox` posture means *everyone may create here*, and an anonymous caller is "everyone". `posture_refusal` (`rights.py:328-332`) admits an anonymous call when the root posture rank >= the verb's rung; with `write` at `create="contribute"` an anonymous `write` under an `inbox` root passes the posture refusal and then the gate. That is the feature (a drop box), but ADR 068 ("anonymous is a name, loud at the edge") should say so explicitly.

## 9. The baseline the `list` rung must preserve (EXECUTED)

`l1_road_baseline.py`: posture `private`; files under `/projects/alpha`, `/projects/beta`, `/pub`; `ann` holds `read` on `/projects/alpha/notes.md` only. Output (`l1_road_baseline.out`):

| Call as `ann` | Result |
|---|---|
| `ls /` | `/projects` bare (`populated=['kind','path']`); `/pub` absent |
| `ls /projects` | `/projects/alpha` bare; `/projects/beta` absent |
| `ls /projects/alpha` | `notes.md` full row; `other.md` absent |
| `tree /` | `/projects` bare → `/projects/alpha` bare → `notes.md` full |
| `stat /projects` | bare directory |
| `stat /projects/beta`, `stat /projects/alpha/other.md` | `not_found` |
| `read /projects` | `wrong_kind: directory` (the ordinary directory answer) |
| `glob **` | the three rows above, same projections |
| `grep alpha` | `notes.md` only |
| `mkdir /projects/gamma` | `permission_denied` (decided on the road parent) |
| `write /projects/alpha/notes.md` | `permission_denied` (visible, read-only) |
| `ls /` as system | `/projects`, `/pub`, full rows |

This is exactly the `list` projection applied to directories by derivation. A granted `list` on `/projects/beta` should make `ls /projects` show `beta` bare and `ls /projects/beta` show `secret.md` bare, `read /projects/beta/secret.md` answer `permission_denied` (not `not_found`), and leave every other line of this table unchanged. That table is the regression pin for the landing.

## Open questions

1. **`grants` on a `list` path** — `not_found` (as the road today) or the caller's own rows? (§4 table.)
2. **Append.** vfs has no append verb and `edit` cannot be classified as add-only at the gate. Does `contribute` mean "create only" (my reading), or does the spec add an append form?
3. **Anonymous `write` under an `inbox` posture** passes the posture refusal by construction (§8). Intended?
4. **Rank numbering**: dense renumber (0..4) with a format bump, or sparse ranks (0,10,20,30,40) to spare the next rung a renumber?
5. **`Resolution` shape**: a `Mapping[GrantLevel, Rights]` with aliasing of equal compiles (§3), or four named fields?
6. **Trash view.** A `list`-level tombstoned row: visible bare under `/.vfs/trash` or absent? Today a tombstoned row the caller may see answers `not_found` with the trashed hint (`rights.py:59-63`); a bare row has no hint field.

## What the ADR should pin

1. The ladder is `none < list < read < contribute < read_write` with dense ranks 0..4; `everyone_level` stores the rank; the landing bumps `SCHEMA_FORMAT_VERSION` and rebuilds labels (`rebuild_labels`).
2. `Rights` at level L is the rows at rank >= L (already `grants.py:531`); a `Resolution` holds one compile per rung a verb can need and may alias equal compiles.
3. `admits` answers a rung, not a bool; a verb compares it with its own entry in the table.
4. The `list` projection is `ROAD_FIELDS` (`path`, `kind`); it serves granted `list` rows and derived road directories alike; a `list` row answers `permission_denied` to `read` and to every mutation, never `not_found`.
5. The road is *derived `list`*: a directory is at `list` when a row the caller holds `list` or more on lies beneath it; the road stays a per-call derivation, not a compiled span.
6. `grep` and `glean` nominate, score and compute statistics over the `read` set; ADR 065 rule 5's "visible set" means the `read` set.
7. `contribute` = the creation branch of the write gate at `contribute`, the occupied branch unchanged at `read_write` (the owner floor stays an owner arm there); "append" is "create a new row"; overwrite of another's row is refused because overwrite clobbers `owner_id`.
8. One table `VERB_RUNGS: dict[Op, Needs]` in `ops.py`; the gates and `_viewed` read it; a drift test pins every `Op` has an entry and the invariants of §7.
9. Posture words `listed → list`, `inbox → contribute`; everyone stays capped at `read_write` by construction; anonymous creation under `inbox` is stated as intended or refused.
10. `graph` traverses at `list` and returns contents at `read` (`Needs("read", traverse="list")`), flipping spec 164's one entry.

## What the spec must list (file by file)

| File | Change |
|---|---|
| `src/vfs/storage/grants.py` | `GrantLevel` + `LEVEL_RANK` (five entries, renumbered); `Posture` + `POSTURE_LEVELS` (+`listed`, `inbox`); docstrings (`:76-90`); nothing in the algebra |
| `src/vfs/ops.py` | `Rung`, `Needs`, `VERB_RUNGS` |
| `src/vfs/params.py` | `GRANTABLE_LEVELS` derived from `GRANT_LEVELS - {"none"}` (`:54`) |
| `src/vfs/models/rows.py` | `SCHEMA_FORMAT_VERSION` bump (`:139`); label comment (`:473-475`) |
| `src/vfs/storage/backends/database/rights.py` | `Resolution` shape + `at(level)` (`:160-165`); system path (`:293`); `resolve_authority` compiles per rung (`:318-322`); `weight` (`:258`); `Visibility(need=...)`, `admits → Rank` (`:379-399`); `road`/`_open_beneath`/`_owned_beneath` at the `list` compile (`:437-464, 1045-1083`); `seen_kinds` (`:466-479`); `WriteGate.targets/subtrees/row/_decide` read `Needs` (`:539-695`); `_grant_refusal` level check (`:1132-1133`); `list_grants` rule for `list` paths (`:801`); docstrings (`:14-16`, `:47-52`) |
| `src/vfs/storage/backends/database/backend.py` | `_viewed` passes the verb's rung (`:1440-1445`); `_gate`/`_resolution` default level from the table (`:1417,1456`); the eleven literals at `:628,660,689-691,749-751,787-790,820,865-866,894,979,1569-1580` replaced by table reads; `posture` docstring (`:946`) |
| `src/vfs/storage/backends/database/reads.py` | `_screen`, `_children_by_parent`, `tree_rows`, `glob_rows`, `_point_rows`, `_visible_rows` project bare when `admits(row) < read` (`:179-365, 544-574, 629-674, 715-725, 795-848`); `ROAD_FIELDS` renamed or documented as the `list` projection (`:96-98`); `read_rows` answers `permission_denied` on a `list` row (`:139`) |
| `src/vfs/storage/backends/database/grep.py` | post-filter at `read` (`:261,303`); candidate statements narrowed at `read` (open-questions gap 1) |
| `src/vfs/storage/backends/database/glean.py` | `_visible_lexicon`, candidates and `clauses()` at `read` (`:297-315, 380, 574, 646-651, 699+`) |
| `src/vfs/storage/backends/database/labels.py` | docstring numbering (`:1-9`); nothing else (`rebuild_labels` loops the regions) |
| `src/vfs/storage/backends/database/engine.py` | first-touch refusal text unchanged; a repair path that runs `rebuild_labels` on an old format (`:505, 562-569`) — or the spec declares re-provision |
| `src/vfs/base.py`, `src/vfs/session.py`, `src/vfs/storage/protocol.py` | signatures already typed by the Literals; docstrings for `grant` and `posture` (`base.py:1552-1556, 1588-1592`) |
| `src/vfs/storage/backends/database/edges.py` | none now; spec 164's `graph` reads `VERB_RUNGS["graph"]` |
| `context/decisions/068`, `070`, `073` | amendments: anonymous under `inbox`; the road is derived `list`; the label domain is five ranks |
| `tests/support/grant_worlds.py` | `_NAMED_LEVELS`, `_ALL_LEVELS` (+`list`, `contribute`) so parity sweeps cover them (`:76-77`) |
| `tests/support/oracles/grants.py` | unchanged (by rank); add a `list`-projection oracle if the parity test asserts projections |
| `tests/storage/test_grants.py` | level parametrisation (`:66`), `posture_regions({})` (`:215`), `need ==` literals (`:428`), inflight tests (`:334-348`) |
| `tests/storage/database/test_rights.py` | `_POSTURE_OF` (`:72`), two-level loops (`:166,201`), SQL `>= 1` pins (`:233,423`), `Resolution(...)` ctor (`:634,650,872`), new tests: `list` grant projection in ls/tree/stat/glob, `read` on a `list` row, `contribute` create-yes/modify-others-no, cache aliasing |
| `tests/storage/database/test_labels.py`, `test_coherence.py`, `test_races.py`, `test_trash.py`, `test_reads.py`, `test_engine.py`, `test_dialects.py`, `tests/models/test_rows.py` | the raw `everyone_level=2` (15 sites) and `{0,1}` pins become `LEVEL_RANK[...]` |
| `tests/support/grants_contract.py` | contract tests for `list` and `contribute` on both backends; the anonymous table (`:78-96`) gains the `inbox` case |
| `tests/test_ops.py` (or wherever `ALL_OPS` is pinned) | the `VERB_RUNGS` drift test |
| `documentation/`, `README` | the ladder, the posture words, the table |
