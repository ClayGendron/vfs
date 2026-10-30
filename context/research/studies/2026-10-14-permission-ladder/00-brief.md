# Shared brief: the permission ladder study (spec 165), 2026-10-14

## The project
vfs (`/Users/claygendron/Git/Repos/vfs`) is a virtual filesystem for AI agents over a SQL database. Live code is `src/vfs` and `tests/`; `src2/` and `tests2/` are archived and must not be run or ported. Run Python only through `uv run python ...` from the repo root. Write scripts and reports under `./`. NEVER modify files under the vfs repo. NEVER create git worktrees or branches.

## The question
Clay (2026-10-14) decided the graph verb's traversal rule — "to traverse an edge the caller must hold the walk's rung on both endpoints" — must be built on an EXPANDED permission ladder, and that this ladder lands before the graph verb. Today the ladder is `none < read < read_write` (`src/vfs/storage/grants.py`: `GrantLevel`, `LEVEL_RANK`, `POSTURE_LEVELS`). The 2026-10-07 addendum in `context/open-questions.md` (search "Addendum 2026-10-07") proposed `none < list < read < contribute < read_write < manage`:
- `list`: name and kind without contents (NFSv4 READ_ATTRIBUTES, S3 ListBucket); lets an agent say "there is a file here you cannot read, ask for access"; grep/glean score the readable set only.
- `contribute`: create and append; alter or remove only your own rows (Plan 9 append bit, NFSv4 ADD_FILE/APPEND_DATA, the sticky bit, Drive "contributor").
- `manage` is a separate parked question (see "A `manage` rung" in open-questions.md) — out of scope unless it changes the design of the other two.
- The verb→rung mapping must become ONE declared table (in `src/vfs/ops.py`). The seed spec is `context/specs/active/165-the-permission-ladder-list-and-contribute/spec.md`. Read it, and ADR 079 pin 2 (`context/decisions/079-*.md`) and spec 164 §2.4 for the traversal rule.

## What is already law (read first; it binds)
- ADRs 062–073 (`context/decisions/`): authority is subjects, actor and narrowing; a session never widens; hidden rows are absent and statistics are visible-set (065, incl. rule 5 on BM25 statistics); the subject set and the intersection law (066); the enforcement spine compiles rights to a bounded literal predicate (067); open by default (068); the road — directories on the road to a visible row show as bare names (070); a wide predicate fans into bounded clauses (071); rights travel as sorted path ranges joined to the path index (072); the everyone level lives on the row (073); trash is a tombstone on the row (074).
- Memo `context/research/2026-09-28-traverse-visibility-unix-plan9.md` (traverse vs list vs read in Unix, Plan 9, Windows, SharePoint, Drive, S3, NFSv4, mirage) — build on it, do not redo it.
- The storage half: `src/vfs/storage/grants.py` (pure resolver: `Rights`, `admits`, `ranges`, `Pieces`, holes, `compile`), `src/vfs/storage/backends/database/rights.py` (`Visibility`, `WriteGate`, `GateMode`, `resolve_authority`, `RightsCache`, `road`, `seen_kinds`), `labels.py` (`everyone_level` on the row), `ranges.py` (the three-seek predicate), `reads.py` (how `ls`/`tree` show the road; `road_observation`), `descent.py` (the descent ladder, `classify_misses`), `src/vfs/params.py` (`GRANTABLE_LEVELS`, `POSTURES`), `src/vfs/ops.py` (op sets; where a verb→rung table would live), and the tests `tests/storage/database/test_rights.py`, `tests/storage/test_grants.py`, `tests/support/grants_contract.py`, `tests/support/oracles/grants.py`.

## Rules of evidence
Reference repos under `~/Git/Repos/<name>` are READ-ONLY; cite `repo:path:line`; describe, never copy. Label every claim EXECUTED / READ / INFERRED; mark `[NOT VERIFIED: why]`. Prefer running something (a script against the live resolver, a count of sites) over asserting. Use WebSearch for vendor docs and cite the URL.

## Deliverable
A Markdown report at the path your task names: a one-paragraph summary, a findings table, evidence per source, open questions, and a "What the ADR should pin" section. Short sentences. Your final chat reply is the path plus five lines.
