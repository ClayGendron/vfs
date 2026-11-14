# Spec review: The rights compile is the same at every world size: two worlds ten times apart pin one compile and one set of statements, a posture change's chunks and the read between them are pinned to their law, and the generic floor's road stops outgrowing its statement in a relabel window

I am an agent (Claude Opus 5.5), a fresh sub-agent of the author's session; not the author. I reviewed [the spec](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md) as an untracked draft on branch `lane/pins` at `e90ec653`, SHA-256 beginning `4e0dfb5951dc`, with its two placeholder memos, [the in-flight memo](../research/2026-11-14-a-posture-change-in-flight-compiles-every-posture-row-beneath-it.md) and [the road memo](../research/2026-11-14-a-listing-pays-a-road-check-per-hidden-child-directory.md), their studies folders, the author's scratch probes (read, not edited), [AGENTS.md](../../AGENTS.md), [the pipeline](../README.md), [how we code](../standards/how-we-code.md), [testing](../standards/testing.md), [the mutant ledger](../standards/mutant-ledger.md), [landing](../standards/landing.md) and [the roadmap](../standards/roadmap.md). I was given the session lead's list of what to check, as questions; I was not given the author's summary, transcript, reasoning or an expected verdict. Probes, all mine, in the session scratchpad under `review/pins-spec/`, run from the worktree through `uv run`, counting statements, binds, rows and pieces, never time: `p_law.py` (the compile law on ten caller shapes), `p_relabel_edge.py` (the relabel record at R = 249, 250, 251, 996 and 2,001 under a cap of 250), `p_hole.py` (the floor's window road reproduced, decision 11's design built in scratch and checked against the pointwise test on nine hole shapes, and the window road run through it), `p_blind.py` and `p_scanmutant.py` (what criteria 1 and 3 can and cannot see, under Q1 and two mutants of my own, on copies of the state check's 100- and 1,000-user worlds), `p_identity.py` (criterion 3 at the spec's own sizes for all seven callers), `p_stuck.py` (the stuck window and what clears it), `p_builder.py` (decision 2's bulk build against the same world written through the verbs), `p_opens.py` and `p_relabel_depth.py` (the share of open ranges in a relabel chunk), and a re-run of the studies folder's `probe_floors.py`, whose output matched its recorded `.out` byte for byte. The box is 45 minutes, because the spec touches the storage backend and rights; I ran past it to finish the executed checks the brief asked for, and every step below was reached. Labels: EXECUTED means I ran it; READ means I read the file cited; INFERRED means my reasoning.

## The author's questions, answered first

1. The laws (a). The compile law re-derives from `resolve` (`src/vfs/storage/grants.py:595-643`, READ): the arms are `pieces(cover_all(minimised prefixes))`, and a single member's owner arm is the complement of the spans, so the compile reads only the caller's own and its groups' rows plus pending posture rows. EXECUTED (`p_law.py`): the law holds for disjoint siblings (c = 34), names with `.`, `-`, space, `%`, `_` and non-ASCII beside `/`, a grant on an ancestor of the home (minimised to c = 1), one group granted on 5,000 paths (c = 5,000, arms 5,000 and 5,000, owner 5,001 and 10,001), 2,000 narrower postures beneath a grant outside a window (no hole, c = 1), mixed depths, and a `read_write` row beneath a `read` row. It breaks for byte-adjacent prefixes `p` and `p0` (`/h/u1` beside `/h/u10`: owner arm 2 points and 4 opens for c = 2; 100 unpadded users: 91 and 191, not 101 and 201), which stays caller-sized but falsifies the stated formula (L5). Ownership never enters the compile (READ: `resolve` takes closures and rows only). No caller shape made the compile grow with anything outside the caller's own rows, groups and pending marks. The relabel law re-derives from `_batched` and `_boundary` (`labels.py:438-466`, `labels.py:340-355`, READ) and held at every size I ran (EXECUTED, `p_relabel_edge.py`), except the regime R = `relabel_rows`, which the roadmap text misstates (L4).

2. Identity at two sizes (b). The two worlds differ tenfold in users, homes, posture rows and memberships, but hold the mount's groups (50), shared folders (100) and every group grant row fixed, so a compile that reads every group's rows on the mount passes every pin (M1, EXECUTED). Criterion 3 compares text, binds, bound bytes and count, so it would see growth in binds or statements; it cannot see a statement whose text and binds are fixed but whose rows read grow, and its stated killer Q1 is exactly that (L2, EXECUTED). Criterion 1 spies the rows read and does catch Q1 (EXECUTED: 246 against 1,146 rows).

3. The fix (c). EXECUTED: the failure reproduces (400 homes on the floor emulation: `unavailable`, "Expression tree is too large", a statement of 2,007 binds; 100 homes and SQLite's own profile answer `/h/u00007`). Decision 11's design, built in scratch, admits exactly the rows outside the hole on all nine shapes I tried (empty, the whole mount, a hole at `/`, the first prefix, the last prefix, adjacent `/h/u1` and `/h/u10`, a nested hole, 1,000 siblings, non-ASCII), at most 100 binds a test, one `hole_free` on each of the five range-source profiles; through it the floor's window `ls /h` answers `/h/u00007` at 400 homes in 46 statements of at most 503 binds and at 1,000 homes in 135 of at most 1,000. It sits correctly on the layer ladder (`vfs.storage.backends` over `vfs.storage`, `tests/lint/test_code_shape.py:43`, READ). Nothing else on a tuned profile or the floor builds one statement that grows with posture rows, grants or groups past a declared budget: the fan, the scan groups, the subtree hole chunks (`rights.py:808-813`, bounded by `arm_budget`) and the road's owner tests are all bounded (READ; EXECUTED by the floors re-run). Two edges remain: the relabel's literal `OR` is chunked by `in_list_budget` pieces, not by the depth budget, and a lawful shape fills a 1,000-piece chunk with 996 open ranges (L12); and the hole's single bound value on the range-source engines grows with the posture rows beneath a mark (L13).

4. The world builder (d). EXECUTED (`p_builder.py`): a five-user world bulk-inserted as decision 2 says and the same world written through `posture`, `grant` and `add_member` agree in `vfs_grants` (principal, prefix, level, `granted_by`), `vfs_memberships`, `vfs_relabels` and every entry's path, kind, owner and label; ann's compile and her statements are equal. They differ in `vfs_principal_revisions`: 0 rows bulk against 14 through the verbs, a state the verbs never produce, harmless to these pins and unguarded by the spec (L15).

5. The criteria (e). One line each below. Q1 to Q9's anchors exist in the tree as quoted (READ); criteria 2 and 3 and decision 5's admin and system pin have no ledger row that kills them (L2, L3, L8).

6. The memos (f). The stuck window reproduces (EXECUTED, `p_stuck.py`): after a failed first chunk the mark stands through a close and reopen, a system write, a grant, `rebuild` and a refused `posture`, and ann's `grep` costs 14 statements against 7; the next successful `posture` on an unrelated path clears it. Leaving the High out is right for this spec: no pin asserts an in-window count, criterion 8 and 13 assert answers and per-statement bounds only, so nothing here blesses the window's cost (READ). Both memos are executed research with undecided candidate directions and a deciding experiment; both lack the research's time box in the first paragraph (L11). The roadmap replacement text misstates two laws (L4, L5) and one qualifier (L14).

7. The premortem (g) is in its section. No pin rests on a line count or an anchor the refresh landing moves, except `rights.py`'s 1,540, which refresh does not touch (READ: its file list).

## Decisions, one line each

1. Decision 1 holds for the dimensions that vary: users, homes, posture rows, memberships and the ten-user draws all move tenfold (READ, the plan). It does not hold for the dimensions it keeps fixed, groups and shared folders, where identity at two sizes hides a dependence (M1, EXECUTED).

2. Decision 2 holds: the bulk world equals the verbs' world in every table the compile and the reads touch, but for the stamps (EXECUTED, L15). Its reason ("the verbs' own rows are pinned elsewhere") pins the verbs, not the equality; a guard node is the evidence.

3. Decision 3 holds: each caller exercises a distinct branch of `resolve` and `resolve_authority` (READ, `rights.py:360-388`, `grants.py:621-643`).

4. Decision 4 holds for the world's callers (EXECUTED via the state check's worlds) with the law's qualifier missing (L5). Replacing the story's 64 ranges and 4 KiB is reasoned and ruled.

5. Decision 5 holds (EXECUTED, `p_identity.py`: all twenty calls of all seven callers identical at 100 and 1,000 users, admin's and the system actor's counts identical with no rights term); its admin and system pin has no criterion node (L8).

6. Decision 6 holds on SQLite (READ: `range_hints.ranges` is empty there). On Oracle the `CARDINALITY({source} {count})` hint (`dialects.py:629`, READ) puts the piece count in the text, so the docstring's promise is per-profile; the pin is SQLite-only and says so implicitly (a note).

7. Decision 7 holds: the formula re-derives from `_owned_beneath` and `_open_beneath` (`rights.py:1320`, `rights.py:1341`, READ) and gives criterion 5's 4, 8, 8 and 16; its "exactly" depends on no owner test naming a candidate (L14).

8. Decision 8 holds for the regimes it states (EXECUTED at R = 996 and 2,001: 6 and 10 transactions, 10 and 18 statements); its law leaves R = `relabel_rows` to the Design's `expected_relabel`, and the roadmap text gets that regime wrong (L4, EXECUTED: 2 transactions, the text says 3).

9. Decision 9 holds: `_settled` awaits `relabel:after-chunk` once per successful chunk, the last included (`backend.py:1356-1363`, READ; EXECUTED: 6 firings at R = 1,001 and cap 250 in the state check's probe shape, and firings equal transactions at every R in `p_relabel_edge.py`).

10. Decision 10 holds (EXECUTED: the floors probe re-ran identical to its record); compiling is the right referee for binds and SQLite for depth.

11. Decision 11 holds in design and placement (EXECUTED, `p_hole.py`), with one edge to name (L6) and a duplicated constant (L7). Holding `rights.py` at 1,540 is feasible: `_open_beneath` is 18 lines today and the change is a comprehension and a reserve (INFERRED), and L7 frees two lines.

12. Decision 12 holds: the window's cost is a design question with four measured-cost directions, and no pin here asserts its size (READ).

13. Decision 13 holds: the legs run the identity and the relabel law through the suite's `ENGINE_LEGS` and `profile_for` idioms (`tests/support/server_schemas.py:60`, `tests/storage/database/test_engine.py:106`, READ); the R = 201 numbers re-derive (6, 10, 202).

14. Decision 14's counts re-derive from the plan: 408 and 2,208 files, about 5,400 grant rows, 5,600 memberships, 159 admin verb calls, 4,095 relabel files and 23 chunk transactions (INFERRED from the Design's constants).

15. Decision 15 holds as a rule; its rows miss killers for criteria 2 and 3 (L2, L3).

16. Decision 16 holds: D4's law is in the batch width, this one's in the world size (READ, roadmap).

## Acceptance criteria, countable as written

1. Criterion 1 is countable and present (EXECUTED: compile statements identical, 7 and 7; rows identical, 41 and 41); red under Q1 (EXECUTED: 246 against 1,146 rows). Green under mutant G, which reads every group's rows on the mount (M1).

2. Criterion 2 is countable and present for the world's callers (EXECUTED via `p_law.py`'s sibling shape); no ledger row kills it (L3).

3. Criterion 3 is countable and present (EXECUTED at 100 and 1,000 for all seven callers). "Red under Q1" is false (EXECUTED: 148 statements identical at both sizes under Q1); a mutant that drops the scan tier's view kills it (EXECUTED: answers 708 against 2,508 rows, a leak) (L2).

4. Criterion 4 is countable and present; red under Q2 (INFERRED: the fan carries no `visible` alias and its clause count differs across callers).

5. Criterion 5 is countable and present; the numbers re-derive (READ). Red under Q3 and Q4 (INFERRED from `_beneath` and `_open_beneath`).

6. Criterion 6 is countable and present (EXECUTED, the floors re-run); red under Q8 on SQL Server (INFERRED: owner units of 101 binds pack past 1,000 under a 2,099 cap).

7. Criterion 7 is countable and present (EXECUTED: 102, 997 and 2,002 rows; 2, 10 and 18 statements; 1, 6 and 10 transactions at my own runs); it does not hold the R = cap regime (L4). Red under Q5 and Q6 (INFERRED).

8. Criterion 8 is countable and present; red under Q7 (INFERRED: the first firing follows the `/big` point chunk, with every file's label still stale).

9. Criterion 9 is countable (READ: the three named tests exist).

10. Criterion 10 is countable; red today as stated (READ: no `hole_tests`); my scratch build of it gave 41 tests of at most 100 binds for the 3,002-piece hole (EXECUTED). It leaves the whole-mount hole unpinned (L6).

11. Criterion 11 is countable, deselected without its URL; not run (no Docker in this review).

12. Criterion 12 is countable; its numbers re-derive from the law (INFERRED); not run.

13. Criterion 13 is countable; red today exactly as stated (EXECUTED: `unavailable`, the depth error, 2,007 binds); green through decision 11's design in scratch (EXECUTED: `/h/u00007`, at most 503 binds).

14. Criterion 14 is countable (READ: `rights.py` is 1,540 lines and its allowlist entry 1,540).

## The diagram and the scope

The diagram: no page to redraw (the architecture folder is retired; READ, `context/` has none); every touched component is shown, built solid and planned dashed; the retiring class uses `stroke-dasharray: 2 2` where the house dialect is `2 3` (L10); it agrees with the Design.

The scope: one landing, green at every step: pins of present behaviour first, then the two red criteria, then the fix (READ, "Order of work").

The dependencies: none unlanded (READ); the active refresh spec touches none of this spec's files but `test_rights.py`'s neighbours, and none of its line anchors (READ).

## Scale and the production posture

Every statement the fix adds is bounded by a declared budget: a hole test is at most 50 pieces and 100 binds, and the candidate chunk keeps `membership_budget − 103` on the floor (EXECUTED: at most 1,000 binds at 1,000 homes). The count of statements on the floor inside a window grows with the hole, `ceil(3D / 50)` per candidate chunk, named honestly as decision 12's memo's subject (READ). The pins add no statement to `src/`. The slow tier gains two worlds and four relabel subtrees, fewer rows than one 10,000-file pin (INFERRED from decision 14). No designed cap is introduced; refusing a posture change above a count is set aside in the memo for that reason (READ).

## Constitution and CLAUDE.md checks

Article 1: the spec composes Entry (rows, labels) and Mount (the posture and grant rows, the relabel) through Namespace verbs; no sixth thing (READ). No numpy, no pure-Python fallback, no clock in any criterion, imports at the top in the Design; `hole_free`'s new `assert` narrows an invariant no caller can break, as `visible_entries`'s does (READ, `ranges.py:112`). No document name enters code.

## Premortem

1. The world builder's population draw raises `TypeError` on its first run: `random.Random((SEED, users))` is refused on every supported Python (EXECUTED on 3.13.11) (L1).

2. A node reads a world copy without its WAL and sees an older or empty database, flaky by worker order: the Design's `open_world_copies` copies "the files" without saying the builder's storage is closed first or the `-wal` and `-shm` files go with them; the author's probe copies the side files (READ) (L9).

3. Three weeks on, a change makes the compile read every group's grant rows for its cache key or a prefetch, and every pin stays green because the worlds hold the groups fixed (EXECUTED, mutant G) (M1).

4. Checked and found clean: a pin's number moving when an unrelated landing adds a statement. Criteria 1, 3, 4 and 11 compare two sizes, criteria 5, 7 and 12 compute their numbers from a law beside the test, criterion 5 counts only statements reading `vfs_entries AS d`, and criteria 6, 10 and 13 assert per-statement bounds (READ).

## Findings, most severe first

M1. [Decisions 1 and 2](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#decisions) hold the mount's 50 groups, 100 shared folders and every group grant row the same in both worlds, so a compile that reads the rows of every group on the mount is identical at both sizes and passes every pin. EXECUTED (`p_blind.py`, mutant G: `_grant_rows` also reads every group named in `vfs_memberships`): 401 rows at both sizes against 41, compile statements identical (8 and 8), verb statements identical (149 and 149), answers identical. Consequence: the Intent's "never what the mount holds" is not evidenced for the mount's groups, which grow with its people at the reference deployment. Fix text for decision 2: "The population also holds groups and folders of its own that grow with N: `N // 2` population groups `group:pNNNNN`, each granted `read` on two population folders `/teams/tNNNNN` of `N // 10`, every population user a member of two, drawn from the population seed; the named callers' 50 groups and 100 shared folders stay fixed, and `/teams` lies outside every path the ten verbs read." And a ledger row: "Q10 | the compile reads every group on the mount: `_grant_rows`'s ids in `resolve_authority` become `[*ids, *every group in vfs_memberships]` | `rights.py` | `tests/storage/database/test_rights.py` | criterion 1's rows-read assertion". Evidence that closes it: the amended world, and Q10 recorded red on criterion 1.

L1. [The Design](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#design) seeds the population draw with `random.Random((SEED, users))`, which raises `TypeError` on Python 3.11 and later (EXECUTED). Fix text: "the population draw takes `random.Random(f"{SEED}-{users}")`".

L2. [Criterion 3](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#acceptance-criteria) says "red under Q1 on the first call's spied rows", but it spies nothing, and under Q1 its statements are identical at both sizes (EXECUTED, 148 and 148); no ledger row kills it. EXECUTED (`p_scanmutant.py`): with `entries_for_scan` given `view=None`, ann's `grep` answers 708 rows at 100 users and 2,508 at 1,000, so criterion 3 fails. Fix text: criterion 3 ends "Present; red under Q11." and the ledger gains "Q11 | the scan tier stops pushing the caller's rights: `entries_for_scan`'s `view` parameter is discarded, its first statement `view = None` | `src/vfs/storage/backends/database/scope.py` | `tests/storage/database/` | criterion 3 (the answers differ by size)".

L3. [Criterion 2](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#acceptance-criteria) has no ledger row. Fix text: "Q12 | the owner arm is not trimmed by the spans: `subtract(cover_all(arm.prefixes), self.spans)` in `Rights.__post_init__` becomes `cover_all(arm.prefixes)` | `src/vfs/storage/grants.py` | `tests/storage/database/test_rights.py` | criterion 2 (one point and one open range, not c + 1 and 2c + 1)" (INFERRED: a single member's arm prefix is the root, so its owned set becomes the whole mount).

L4. [The roadmap edit](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#scope), line 3, gives 3 transactions at R = `relabel_rows`, where the planner takes 2 and 2 statements (EXECUTED: R = 250 under a cap of 250 records rows 251, statements 2, transactions 2, two firings). Fix text for line 3: "…runs in one transaction when R + 1 ≤ `relabel_rows`, in two when R = `relabel_rows`, and otherwise in `2 + floor(R / (relabel_rows − 1))` transactions…", the same in decision 8, and criterion 7 gains `[249]`: rows 251, statements 2, transactions 2.

L5. [The problem's line 1](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#the-problem) and roadmap line 1 state the law for any disjoint siblings, and it breaks for a prefix beside its byte successor `p0` (EXECUTED: `/h/u1` and `/h/u10` give an owner arm of 2 points and 4 opens; 100 unpadded users 91 and 191). Fix text: "a single-member caller with c disjoint covered prefixes, no one of them another's byte successor `p0`, compiles to c points and c open ranges plus one owner arm of c + 1 points and 2c + 1 open ranges; each such adjacent pair takes one point and one open range from the owner arm".

L6. [Decision 11](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#11-the-generic-floors-road-in-a-relabel-window-is-fixed-in-this-spec-the-hole-becomes-bounded-positive-tests-and-hole_free-keeps-only-its-bound-value-arm) names `[true()]` for no hole but not the whole-mount hole, whose complement is empty, so the floor returns no test (EXECUTED: a narrowing at `/` with nothing beneath gives 0 tests, and that is the exact answer). Fix text for decision 11 and criterion 10: "a hole that covers the whole mount returns no test, and the road's label leg then names nothing".

L7. [The Design](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#design) adds `HOLE_TEST_PIECES: Final = 50` beside `rights.py`'s `_OWNER_PIECES_PER_UNIT: Final = 50` (`rights.py:160`, READ), one bound under two names. Fix text: "`ranges.py`'s one constant `PIECES_PER_TEST: Final = 50` bounds both the owner tests and the hole tests; `rights.py`'s `_OWNER_PIECES_PER_UNIT` is retired and imported in its place, two lines toward the 1,540".

L8. [Decision 5](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#5-ten-verbs-are-pinned-identical-at-both-sizes-for-every-caller-whose-answer-is-the-same-at-both-and-admin-and-the-system-actor-are-pinned-by-their-counts-and-the-absence-of-any-rights-term) pins admin and the system actor, and no criterion names that node. EXECUTED: their counts are identical and no statement holds a rights term at 100 and 1,000. Fix text: criterion 3 adds `[admin]` and `[system]`, "for which each verb's statement count is identical at both sizes and no statement holds a rights term".

L9. [The Design](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#design)'s `open_world_copies` does not say how a SQLite file is copied whole. Fix text: "`build_world_files` closes each storage before it returns, so its file is checkpointed, and `open_world_copies` copies the database with any `-wal` and `-shm` beside it".

L10. [The diagram](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#architecture) declares `classDef retiring stroke-dasharray: 2 2;`; the house dialect is `2 3`. Fix text: `classDef retiring stroke-dasharray: 2 3;`.

L11. Both memos' first paragraphs give the box so far, where [the research README](../research/README.md) asks for the time box the research will have. Fix text, in each: "The research will have one working session per engine leg, run through the `db_test` cycle, counting statements, binds and the engines' own row counters."

L12. [The problem's line 4](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#the-problem) infers that a relabel chunk never holds more than about two thirds of its cap as `OR` terms; a lawful region of siblings named `c0`, `c00`, … holds 99.5% open ranges (EXECUTED, `p_opens.py`), and the floor's relabel then issued an `UPDATE` of 996 `OR` terms, which SQLite accepted, past the floor's declared 936 depth units (EXECUTED, `p_relabel_depth.py`). Fix text: replace the inference with "a chunk's literal `OR` is bounded by `in_list_budget` pieces, not by the depth budget: two thirds of the cap for ordinary siblings, 996 terms for a pathological run of names `c0`, `c00`, …, which SQLite still accepted; bounding it by the depth budget belongs to the in-flight memo".

L13. [The in-flight memo](../research/2026-11-14-a-posture-change-in-flight-compiles-every-posture-row-beneath-it.md)'s item 4 records the hole's one bound value growing linearly (870,025 bytes at 10,000 posture rows, EXECUTED by the re-run) and names no engine cap it meets. Fix text for its experiment: "and the posture-row count at which the hole's bound value meets each engine's packet cap, MariaDB's `max_allowed_packet` first (16 MiB by default, about 190,000 posture rows beneath the mark at 87 bytes each, INFERRED)".

L14. Roadmap line 2's "exactly" holds when no owner test names a candidate, since each owner arm's hits leave the next test's candidates (`rights.py:635-640`, READ). Fix text: "…issues exactly `ceil(P / 50) × ceil(H / (B − 103)) + ceil(H / (B − 3))` road statements when the road names none of them, P the caller's owner pieces and B the membership budget".

L15. [Decision 2](../specifications/active/2026-11-14-the-rights-compile-is-the-same-at-every-world-size.md#2-the-world-is-the-state-checks-with-two-files-a-shared-folder-the-populations-rows-go-in-by-bulk-insert-the-named-callers-rows-through-the-verbs-every-entry-through-write)'s bulk insert writes no `vfs_principal_revisions` rows, which every verb writes (EXECUTED: 0 against 14 rows on a five-user world; every other table equal, ann's compile and statements equal). Fix text: "The bulk insert also stamps every principal it names in `vfs_principal_revisions` at revision 1, and `TestScale::test_the_bulk_world_is_the_verbs_world` builds a five-user world both ways and asserts equal `vfs_grants` (principal, prefix, level, `granted_by`), `vfs_memberships`, `vfs_principal_revisions` ids, `vfs_relabels`, entry (path, kind, owner, label) and ann's compile; not slow."

## Checked and found clean

The generic floor's defect is real and the fix's design is exact: reproduced red at 400 postures, green at 100 and on SQLite's own spelling, and the scratch design exact on nine shapes including adjacent, nested, empty, first, last and whole-mount holes (EXECUTED).

The floors probe re-ran identical to its recorded output, every fan clause at most half the membership budget on each profile, every scan group inside its engine cap, SQLite's parser accepting every group (EXECUTED).

Criterion 3 holds at the spec's own sizes, 100 and 1,000, where the state check ran only 1,000 and 10,000 (EXECUTED, all seven callers, twenty calls each).

The relabel law at R = 249, 251, 996 and 2,001, the transaction count equal to the seam's firings at every R, and the `R + 1` rows (EXECUTED).

The stuck window: the mark survives a reopen, a write, a grant, `rebuild` and a refused `posture`; the next successful `posture` anywhere clears it; nothing in `src/` calls `rebuild_labels` (EXECUTED; READ, `labels.py:388`).

Q1 to Q9's anchors exist verbatim in the tree, and Q1's killer, criterion 1, fails under it (READ; EXECUTED for Q1).

Every test the spec cites as present exists at the path named; no test drives `relabel:after-chunk` today; the ledger has no Q row (READ).

The fix's module and import direction pass the ladder; `rights.py` stands at its allowlist's 1,540 (READ).

Neither memo hides a choice: each lists its directions with costs and risks and chooses none, and sets aside only the designed cap the production posture forbids (READ).

Note: on Oracle, `tree`'s visibility statement carries the piece count in its `CARDINALITY` hint, so its text does change with the caller's grants there; criterion 4 is a SQLite pin and holds (READ, `dialects.py:629`).

## Disposition

Awaits the author.

## Verdict

Not yet: M1, the worlds hold the mount's groups and shared folders fixed, so a compile that reads every group on the mount passes every pin.
