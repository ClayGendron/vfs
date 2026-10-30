# Review of spec 165 — the permission ladder (`list`, `add`, `contribute`)

Reviewer: senior review, 2026-10-14. Tree at `main` (`e8b8d9a`), working tree as found; nothing under the repo was modified. Evidence labels: **EXECUTED** (a script ran; outputs beside this file), **READ** (file read, `file:line`), **INFERRED** (my reasoning from the two).

## Verdict

The spec is not ready to build. Its direction is right and most of the machinery already exists in the write gate, but two gaps would ship a body leak (the gate's read leg consults no compile, so `copy` of a `list` file passes) and an anonymous gate the spec describes with a mechanism that does not exist (`resolve` never computes the everyone level at a path). Before slice A can land green, the rank renumbering must carry its test and docs constants with it, and the format-repair door must be decided, because today `rebuild_labels` has no caller and the format refusal fires before any verb.

## Findings, most severe first

### 1. The gate's read/traverse leg consults no compile: `copy` from a `list` source leaks the body — **blocks the build**

- **Evidence.** READ `rights.py:686-688`: for `mode in ("create", "read")` and a key in `seen`, `_decide` returns `None` without touching any `Rights`. READ `rights.py:543`: the only compile the read leg touches is `rights.whole`. READ `backend.py:1576`: copy's sources go through this leg; `subtrees` (`rights.py:581-600`) skips a file source (`known["kind"] != "directory"`). EXECUTED `gate_legs_probe.out` §B: today a `read` holder copies `/team/plan.md` into `/mine` and reads the copy — lawful today because `read` is the only visibility rung; the leg itself never compared a level.
- **Scenario.** Spec as written: the gate's view runs at `list` (it must, for pin 2's `permission_denied` on a `list` row). bob holds `list` on `/team` and `add` on `/mine`. `copy("/team/plan.md" → "/mine/plan.md")`: source in `seen` (list) → read leg passes; dest fresh → `add` passes; `transfer_rows` copies the body; `read("/mine/plan.md")` returns it. A body-class fact crosses the `list` rung.
- **Fix (spec text).** "`_decide`'s `read` leg refuses `denied(target)` when `view.admits(row) < needs.traverse`; the gate's `Visibility` runs at `list`, and every leg that passes a seen row compares the row's rung with its slot of `Needs` (`traverse` for copy sources and edge targets, `create` for occupied creations, `primary` for the occupied branch)." Add the test: `copy` from a `list` file and from a `list` directory is `permission_denied`.

### 2. The anonymous gate: the spec's mechanism does not exist, and the verb shapes are undefined — **blocks the build**

- **Evidence.** Spec §2: anonymous is judged by "the everyone level at the addressed path — the deepest posture row covering it, which `resolve` already computes". READ `grants.py:597-599`: "An everyone row is ignored — the everyone level is read off each entry row instead"; `resolve` returns spans and arms, never a level at a path. READ `rights.py:318-322`: `root_level` is a separate one-row read (`_root_level`, `rights.py:996-1001`), not a `resolve` output. READ `backend.py:1416-1428`: `posture_refusal` runs inside `_resolution`, which has no path — before `_viewed`/`_gate` see a target. EXECUTED `gate_legs_probe.out` §C: today every anonymous call under a `none` root is `unauthenticated` with `path=None`, including `write /scratch/hello.txt` under an `open` `/scratch`; a named nobody (`zed`) creates the file and sees `/scratch` on the road.
- **What is undefined.** (a) The per-path level must come from the posture rows on the chain (`label_of(posture_rows(prefixes))`, as `_decide` already does for creations, `rights.py:559,676,693`) — never the stored label, which lags during a relabel (`Rights.holes`); the spec does not say which. (b) "The verb's rung" is ambiguous for `write` and `mkdir`: `Needs("contribute", create="add")` — judged at `primary`, criterion 4 ("an `add` posture gives anonymous create") fails; judged at `create`, an anonymous overwrite under an `add` posture passes the edge and is then denied by the gate (fine, but say so). (c) No verb shape is named: a batch (per target — ADR 068 rule 6 covers this), `move`/`copy` (each path at its own slot), `glob`/`grep`/`glean` (a pattern scope has no addressed path), `tree /` and `ls /` (judged at `/` → `unauthenticated` even when `/scratch` is open beneath, while `zed` gets `/scratch` bare), `grants("/")`.
- **Fix (spec text).** "The `unauthenticated` refusal moves out of `_resolution` into the gate and the view: for each target, the level the posture rows on its chain give everyone (`label_of(posture_rows(...))`, one chunked read, never the row label) is compared with the lowest rung the verb can need at that target (`create` on a fresh name, `traverse` for a source it only reads, `primary` otherwise); a pattern scope is judged at the literal prefix of each pattern; `tree`, `ls`, `stat` at the path named; two-path verbs at each path. Anonymous never derives the road." Pin the `/scratch` cases for every shape in the acceptance criteria, not only `write`. (Product choice on the road: see questions.)

### 3. The `rmedge` fix as written produces two shapes, and the batch outcome re-opens the leak — **must fix before slice B**

- **Evidence.** EXECUTED `rmedge_leak.out`. Leak confirmed: bob (read_write on `d.md`) removes the system edge to hidden `/priv/secret.md` → `status=deleted`; a second call → `not_found`. The absent-path shape is: batch `success=True`, one **warning** `not_found` on **the source path** with `data={'edge_type': 'cites', 'vfs.target': '/priv/nope.md'}` and message "Not found: no cites edge to the target" (READ `edges.py:216-228`). The gate's miss shape (the `mkedge` read leg) is: batch `success=False`, an **error** `not_found` on **the target path**, `data={}`, message "Not found" (READ `rights.py:633-645`, `descent.py:92-116`). In a mixed batch the absent target warns while the good edge deletes (`rmedge_leak.out`, last block); a gate refusal would fail the batch whole (`backend.py:894-895`).
- **Scenario.** Spec §2 says both "gates its targets at `list` before the edge lookup" (the gate shape) and "in the absent-path shape" (the `rmedge_rows` shape). Built as a `gate.targets(..., "list")` call: `rmedge([good_edge, edge_to_hidden])` fails whole; `rmedge([good_edge, edge_to_absent])` commits with a warning. The pair of batch outcomes reveals the hidden row — the leak moves up one level.
- **Fix (spec text).** Pin one shape. "A target the caller does not hold `list` on — hidden or absent alike — is folded into `rmedge_rows`' own per-row record: `not_found`, warning severity, `path` = the source, `target` = the target, `data = {edge_type, vfs.target}`, the message `no {edge_type} edge to the target`; the batch commits what it found. The `list` check runs per target before `_endpoint_ids` and never climbs the descent ladder (an ancestor name must not surface)." If instead absent targets are to fail the batch, say so as a contract change and update the `rmedge` docstring and its tests.

### 4. The trashed hint carries `deleted_at` to a `list` caller on the live side — **must fix before slice B**

- **Evidence.** READ `descent.py:113-122`: a miss at a tombstone the view admits carries `{trashed: True, deleted_at: <iso>}`. READ `reads.py:696-701` and `rights.py:481-486`: `tombstones = view.tombstones(chain)` admits by the view's rung. READ `rights.py:551`: the gate reads the same map to judge a revive. Pin 11 and spec §2 close `deleted_at` only in the trash view.
- **Scenario.** bob holds `list` on `/team`; `/team/old.md` is tombstoned. `stat("/team/old.md")` → `not_found` with `deleted_at=2026-10-14T…` — a time, a read-class fact under pin 2.
- **Fix (spec text).** "`Visibility.tombstones(rows, need)` takes the rung: the gate asks at `list` (an occupied path is judged, pin 2), the descent ladder asks at `read` (the hint rides only on a tombstone the caller may read). A tombstoned `list` row answers a plain `not_found` on the live side and shows bare in the trash view."

### 5. Slice A is not landable green as sequenced — **must fix before slice A**

- **Evidence.** EXECUTED: `docs/how-to/share-a-folder-with-grants.md:31` runs `fs.posture("/", "private", …)` and `scripts/ci.sh:70` executes the docs fences (`pytest docs README.md`); retiring the word in task 1 breaks the gate while the docs change sits in task 16 (slice C). READ `test_labels.py:203` (`stale == {0, 1}`), the fifteen raw `everyone_level=2` inserts (study 01 #47), `test_rights.py:72` (`_POSTURE_OF`), `test_rights.py:233,423` (`everyone_level >= 1`), `grant_worlds.py:76-77`, `engine.py:136` and `backend.py:195` (`posture: Posture = "open"`): all decode the old ranks or words; tasks 14–15 put their updates in slice C.
- **Scenario.** Task 1 lands `LEVEL_RANK` dense 0..5; `everyone_level=2` now means `read`; every test that inserted "read_write" rows asserts the wrong visibility; `uv run pytest` is red at the end of task 1.
- **Fix (tasks).** Move into task 1: the raw-rank constants (`LEVEL_RANK[...]` at the fifteen sites), `_POSTURE_OF`, `grant_worlds` tuples, `test_grants.py:215,428`, the two constructor defaults, and the one docs line; keep the new-rung *tests* in C. State in the plan that A changes test support files.

### 6. The format repair is undecided and has no door — **must fix before slice A**

- **Evidence.** EXECUTED grep: `rebuild_labels` is called only from `tests/storage/database/test_labels.py:132,305`. READ `engine.py:562-569`: `_adopt` refuses a format mismatch at first touch, before any verb or admin method runs. READ `labels.py:359-366`: `rebuild_labels` is "a whole-corpus write" in "the caller's one transaction" — chunked statements, one transaction. Spec §1: "a repair path runs `rebuild_labels`, or the docs say re-provision"; criterion 6 assumes the repair exists; plan risk says it "must be bounded like `rebuild_labels` already is" (it is bounded per statement, not per transaction).
- **Scenario.** A 10-million-row Postgres mount at format 22 is opened by the new build: every verb answers `schema_mismatch`; there is no method that both skips `_adopt` and rewrites labels; the operator re-provisions and loses the corpus, or the developer invents the door during slice A.
- **Fix (spec text).** Decide. If repair: "an admin method beside `install_extensions` and `reindex` (`upgrade_format`) that adopts a mount whose stored format is exactly 22, rewrites every label through the `Relabeller`'s per-chunk transactions (`_settled`), then stamps 23; `_adopt` keeps refusing every other mismatch." Say the transaction profile honestly in the docstring. If re-provision: say it in criterion 6 and the refusal text, and drop "repair path".

### 7. `Resolution` aliasing as written cannot work; the study's measurement was vacuous — **must fix before slice B**

- **Evidence.** EXECUTED `aliasing_probe.out` (b): with no row at exactly `list`, `Rights(list) == Rights(read)` is **False** although spans and owner arms are equal — `level` is a compared field and `need` differs (1 vs 2). (c): `Rights(list).admits(row labelled list) = True`, `Rights(read).admits(same) = False`; an `at("list")` that hands back the `read` object hides every row a posture labels `list`. READ `l1_compile_cost.py:20-24`: the "equality held" trial compared `resolve(rows, "read")` with `resolve(rows, "read")`. (d): a pending posture at exactly `list` makes the spans differ (`holes` on the `read` compile only); at any other rank the alias holds — the spec's aliasing *condition* is right, the *object* is wrong.
- **Fix (spec text).** "Aliasing shares the compiled pieces, not the `Rights`: when no row and no pending posture sits at exactly rung L, `at(L)` is a `Rights` at level L built on the same `spans`, `owner_arms`, `roots`, `holes` and the same `ranges()` object as `at(L+1)`; `weight` counts a `ranges()` object once." Add a test that `at("list").admits` passes a `list`-labelled row while `at("read")` refuses it.

### 8. `_decide`'s `create` leg passes an occupied visible target with no compile; pin 2 says otherwise — **should fix**

- **Evidence.** READ `rights.py:686-688`. EXECUTED `gate_legs_probe.out` §A: a `read`-only holder's `mkdir("/team", exist_ok=True)` → `success`, `status=unchanged`; `mkdir("/team")` → `exists`; `mkdir` at a visible tombstone → `not_found` (ADR 074 rule 9) while `write` at it → `permission_denied`.
- **Scenario.** Under the ladder the same leg passes a `list` directory, so a `list` holder's `mkdir(exist_ok=True)` succeeds and its `mkdir` answers `exists` — not `permission_denied`, contradicting pin 2 "every mutation on a `list` row is `permission_denied`". No leak (the row is visible), a contract hole.
- **Fix (spec text).** Either "the occupied-creation leg compares `view.admits(row) >= needs.create`" (then `mkdir(exist_ok=True)` on a `list` directory is denied), or amend pin 2: "a creation at an occupied visible name is answered by the write (`exists`, `unchanged`) at the row's `list` visibility, as `stat` would." Pick one and test it.

### 9. `mkedge` to a road directory stays `permission_denied` — **should fix**

- **Evidence.** READ `rights.py:683-685`: `if key in road: return denied(target)` runs before the read leg for every mode. ADR 080 rule 7 and study 03 §7 ("`mkedge` to a road directory flips from `permission_denied` to pass") say the edge verbs now pass a road directory as a `list` node. Spec §2 is silent.
- **Fix (spec text).** "The road refusal in `_decide` applies to legs needing more than `list`; a leg whose slot is `list` (edge targets) passes a road directory." Test it alongside `mkedge`'s target-at-`list` case, which slice C also omits.

### 10. A `write` at another principal's tombstone un-trashes it at `contribute` — **should fix (product choice)**

- **Evidence.** READ `rights.py:686-690`: a visible tombstone under `upsert` is judged on the occupied leg; ADR 074 rule 5: a write revives, keeps the entry id, clears the flag; ADR 080 pin 3: `contribute` may not restore another's row. The spec routes the occupied leg to `contribute` and says nothing about revives.
- **Scenario.** carol trashes `/inbox/plan.md`; bob (contribute on `/inbox`) `write("/inbox/plan.md")`: gate passes at `contribute`; the row is live again under carol's ownership with bob's body. `restore` of the same row by bob is refused.
- **Fix.** Pin the revive's rung: see question 1. My proposal: "a `write` at a tombstoned row is judged as `restore` (`read_write` or own)."

### 11. "`grep`'s candidate budget counts readable candidates" is a second project in one clause — **should fix**

- **Evidence.** READ `grep.py:254-262, 288-306`: `nominated_count` is taken before `view.admits`; the nominators (`_entries_for_docs`, `entries_for_scan`) do not join `Visibility.narrow` — open-questions "grep's candidate budget counts hidden candidates" (`open-questions.md:305,345`). Spec §2 commits to it; no task, no test, no design.
- **Fix.** Either scope it ("the nominators narrow by the `read` view; a `list` row never enters the budget") with a task and an operation-count pin, or strike it and leave the open question open with `list` named.

### 12. `VERB_RUNGS` entries the spec leaves unnamed or contradicts — **should fix**

- **Evidence.** Spec §1 says "the entries of ADR 080 pin 9"; pin 9 names no entry for `run` ("its own axis"), `sweep`, `posture`, `add_member`, `remove_member`, and puts `grants` at `read_write`, while READ `backend.py:979` gates `grants` at `read` and spec §2 keeps `list_grants`' "own rows at `read`, all rows at `read_write`" (`rights.py:801-805`). The drift test demands one entry per `Op` (25).
- **Fix.** Write the full table in the spec (the study's §7 sketch is a start): `grants: Needs("read")`, `run: Needs("read")` with a note that its axis is parked, developer-plane verbs at `read_write`.

### 13. Acceptance criteria with no test, and a listed test that pins a false claim — **should fix**

- **Criterion 3** (`grep`/`glean` never return, count or rank a `list` row; `glob` bare): no test in slice C. `glean` exports `lexical_stats` (READ `glean.py:295,431`) and `N`/`df` come from `_visible_lexicon` — a `list` row's body in `N` is a leak with no pin. **Criterion 5**: listed (task 9). **Criterion 6**: the repair half has no door (finding 6). **Criterion 8**: only the `write` shape is tested (finding 2).
- **Missing tests** the matrix implies: `copy` from a `list` source (finding 1); `mkedge` target at `list` and on a road directory (finding 9); the trash view's bare tombstone (task 12 lists no test); `grants` on a `list` path → `not_found`; `restore`/`delete` of own rows under `add` and under no grant at all; `glob` with `kind=`/`ext=` over `list` rows; `tree` of a `list` directory lists only `list`+ children; the anonymous `add`/`contribute` postures (criterion 4's second sentence).
- **"cache aliasing"** as listed pins finding 7's false claim; rewrite it per the fix there.
- **Road baseline (study 01 §9).** Reproducible: `l1_road_baseline.py` runs on `InMemoryStorage` with inline fixtures; no `tests/` fixture has that world yet (the contract suite's road tests use the `/eng`/`/pub`/`/hr` world, `grants_contract.py:181-215,385-400`). Port the script's world into `test_rights.py` as the pin, as the spec intends.

### 14. ADR 080 pin 3's "sets … do not hold" the floor is not what the resolver does — **should fix (wording)**

- **Evidence.** EXECUTED `aliasing_probe.out` (e): set `{ann: contribute, bob: add}` at `contribute` → `spans=()`, `owner_arms=[('bob', ('/inbox',))]` — the set may edit bob's own rows there, because every other member holds the rung by grant and bob holds it by the floor (ADR 064/066); at `read_write` the arms are empty. The oracle's `set_rank` (min of member ranks with floors, `oracles/grants.py:86-93`) agrees. The pin's sentence would make a reader expect no arm.
- **Fix.** "A set holds a member's floor on that member's own rows wherever every other member holds the rung by grant; anonymous holds none." Add the set row to the `add`/`contribute` matrix.

### 15. Nits (one list)

- Acceptance criteria are numbered 1–6, 8, 7.
- "Twenty-five `admits` call sites" (EXECUTED: 25 greps, four are docstring examples in `grants.py:48-51`; 21 code sites). Only `Visibility.admits` changes type; `Rights.admits` at `rights.py:615,629,690` stays a bool — say so, or the drift test's "no bool admits" pin misfires.
- Plan still carries the one-rung wording: "**`contribute` means create.** … `GateMode.create` passes", "the `contribute` matrix" (plan §3, tasks 15), "Dense ranks and a format bump (pending the clarification)" (resolved).
- `Posture`: "`POSTURE_LEVELS` is the identity (or goes)" — pick (it has four readers: `rights.py:838,927`, `engine.py:536`, `params.py`).
- `Rung` is declared in `ops.py` and `GrantLevel` in `grants.py`; say which imports which (`ops.py` imports nothing today; `grants.py` can import `ops`, not the reverse) so the drift test's `LEVEL_RANK` import has no cycle.
- `RIGHTS_CACHE_BYTES`' "56 KB" docstring (`rights.py:133-139`) is for two compiles; re-measure or reword.
- `labels.py:1-5` docstring numbering; `ROAD_FIELDS` name — the spec says "documented", the study said "renamed"; the road and `list` share it, so a name like `LIST_FIELDS` with `ROAD_FIELDS` kept as an alias would read better.
- `grep`/`glob` `max_count`/`truncated` warnings count `list` rows for `glob` (visible, fine) and must not for `grep` (finding 11); say it.
- The renderer's "NOTE: … not populated" line (`render.py:129-157`) will fire on every `ls` holding a bare row; today it already does for road rows — acceptable, but the docs should show it.
- Spec 164: its text "every row passing `admits`" (164 spec lines 193, 229) becomes a rung comparison; `Visibility`'s public surface 164 consumes (`need`, `admits → Rung`, `narrow` at need, `at(rung)`) should be stated in 165 so 164 is a wording change only. Nothing in 165's table or view shape forces a 164 rewrite otherwise.

## What the spec gets right

- Two compiles in the view and a flat range algebra: ADR 072/073 stay untouched, and the executed probe (d) confirms the aliasing *condition* (equal pieces unless a row or a pending posture sits at exactly the rung).
- Creation judged at `add` through `reaches` (no owner leg) and the occupied branch at the verb's rung with the floor riding: `_decide` already has exactly that split (`rights.py:676,690,693`), and probe (f) shows the floor admits own rows on every compile.
- Posture words equal to the rungs with an identity map; the grants table stores words (`rows.py:811`), so a relabel from posture rows is complete and the relabel also covers tombstones (no liveness term in `labels.py`).
- The road as derived `list` sharing one projection and one set of refusals, with the executed baseline as the regression pin.
- Closing `rmedge` here, and the eleven-literal count (EXECUTED: 11 grant-level literals in `backend.py` gates) and the chunked gate shapes (`rows_by_path`, `_beneath`) keep every new statement bounded.

## Questions only Clay can answer

1. **A `write` at another principal's tombstone under `contribute`** (finding 10): is a revive an overwrite (passes at `contribute`, every version recoverable) or a restore (`read_write` or own)? Proposed: restore's rung, since pin 3 names restore as the thing `contribute` lacks.
2. **Anonymous and the road** (finding 2): under `posture("/", "none")` with `posture("/scratch", "read_write")`, does anonymous `ls /` answer `unauthenticated` (judged at `/`) while a named nobody sees `/scratch` bare? Proposed: yes — anonymous never derives the road; the edge stays loud; the docs show `ls /scratch`.
3. **`rmedge`'s absent-path contract** (finding 3): keep "absent is a per-row warning, the batch commits" and fold hidden targets into it (proposed), or make both fail the batch?

## Executed scripts

- `./experiments/rmedge_leak.py` → `rmedge_leak.out` (the leak; the three answer shapes; the mixed batch).
- `./experiments/aliasing_probe.py` → `aliasing_probe.out` (six-rung ladder monkeypatched in-process: Literal not enforced at runtime, `KeyError` from `LEVEL_RANK` is the only check; aliasing; `admits` through an aliased object; pending-posture holes; the meet over a set; the floor on every compile).
- `./experiments/gate_legs_probe.py` → `gate_legs_probe.out` (the `create` and `read` legs on occupied visible targets; anonymous under a `none` root with an open child; the named-nobody comparison). Section D's seed step failed on my own setup (a reader cannot create under `shared`) and is not used above.
- Grep counts run inline (recorded in the findings): `.admits(` = 25 hits in `src/vfs` (21 code, 4 docstring); grant-level literals in `backend.py` gates = 11; `rebuild_labels` callers = tests only; docs fences carrying a posture word = 1 (`docs/how-to/share-a-folder-with-grants.md:31`).
