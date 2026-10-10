# 154 — Error text states the cause: no mount-local path in `message`, no Python keyword in a hint

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo;
  revised 2026-10-08 after a review against `0760fe9` (the real site
  count, the `target` coordinates, the acceptance line, the binary-edit
  kind, the tests that pin today's text)
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** fix (results envelope contract; ~39 storage-level producer
  sites, ~12 router-level ones, one hint table, one reclassification)
- **Depends on:** the envelope's rebase law as built
  (`src/vfs/results/envelope.py` L97–99: seams touch `path`, `source`
  and `data`, never `message`; `with_mount` at L154–189) and the error
  line in `results/render.py` (`_error_line`).
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  items 7, 8 and 23 (edit refuses binary).

## Intent

An agent reading `ERROR /mine/missing.md: Not found: /missing.md` sees
two paths and retries the wrong one. The first is the rebased locus the
renderer prints from the structured `path`; the second is the storage's
own coordinates, baked into `message` by the producer. The rebase seam
cannot fix it, by law: `message` is prose, not a field, and no seam
touches it. So the producer must stop putting the path in.

The second half is the same shape: the `unindexable_pattern` hint and
the grep message both say `pass allow_scan=True`. An agent on the CLI
or MCP has no Python keyword to pass.

One line: a message says *what went wrong*; the structured fields say
*where*; a hint says what to do in words any caller can follow.

## Decided semantics

1. **A `message` never contains a path.** `Not found`, `Already
   exists`, `Is a directory`, `Not a directory`, `Directory not empty`.
   The locus is `path`, which the seam rebases and the renderer prints
   as `SEVERITY <path>: <message>`. Where a producer names a *second*
   entry (a move whose destination parent is missing; a point read
   whose missing ancestor is the locus and the requested row is the
   second), the second entry goes in `data` under a named key and the
   message says why ("destination parent not found").
   `data["target"]` today is stored in the producer's coordinates
   (`classified()` at `envelope.py` L208–223) and `with_mount` never
   rebases it, so it is a merge discriminator, not a locus an agent can
   use. `[NEEDS CLARIFICATION: rebase `data["target"]` in `with_mount`
   (the seam may touch `data`) so the second entry reads in the
   caller's coordinates, or leave it opaque and name no second entry
   in `data`? Leaning rebase: a move error must tell the agent which
   pair failed.]`
2. **A hint names no language.** Replace every `pass X=True` and
   `kwarg` wording in `KIND_CONTRACTS` and in producer messages with
   caller-neutral phrasing: "or request the scan tier (`allow_scan`)",
   naming the parameter in backticks as a parameter, not as Python.
   This governs `ResultError.message` and `KindContract.hint`. An
   exception raised to a Python caller (`base.py` L781) may name a
   keyword; it is Python.
3. **The edit refusal on a binary body says what to do and is
   classified by kind.** Today `writes.py` L948 says `Not editable:
   {target} is a binary; its text is a rendering, and write replaces
   its bytes` under `unsupported`, a kind the `VFSErrorKind` docstring
   reserves for capability gates and whose hint ("target a mount that
   does") misleads here. It becomes `wrong_kind` with the message
   `Binary body; replace it through write`.

## Scope

- **Storage-level sites (the bug: storage-local coordinates in
  prose), 39 today.** `storage/editing.py` (1), `storage/replace.py`
  L300 (the `replace_all=True` message), and in the database backend:
  `edges.py` (1), `writes.py` (4: L519, L864, L890, L948), `descent.py`
  (3: L78–81), `rights.py` (5), `topology.py` (19), `staging.py` (5),
  and `results/envelope.py` L232, L238. Strip the path, keep the cause.
- **Router-level sites, about 12.** `permissions.py` L314, `base.py`
  (L735–740, L2346, L2469, L2658, L2677, L2829, L2877, L3032, L3122),
  `rerank.py` L227 (`{mount}`), `envelope.py` L630. These print the
  reader's own coordinates, so they are redundant rather than wrong;
  strip them too so rule 1 holds uniformly.
- Rewrite the `unindexable_pattern` contract hint (`results/kinds.py`
  L196) and the grep producer's message (`grep.py` L201).
- The `wrong_kind` reclassification of the binary edit refusal.
- **Tests that pin today's text and change with it:**
  `tests/support/grants_contract.py` L627–692 (`== f"Not found:
  {named}"`), `tests/results/test_results.py` L79–80 (`Is an edge:
  /e`, `Is a file: /f`), `tests/storage/database/test_grep.py` L75
  (`"allow_scan=True" in message`). `tests/storage/database/
  test_reads.py` L129 (`"Is a directory" in`) survives.
- A new test under `tests/results/` that renders each classified kind
  through a mount at `/mine` and asserts the message contains no
  `/`-led path token.
- Out of scope: the renderer's layout and error grouping (155 changes
  `_render_errors`, not `_error_line`; the acceptance line here is
  stable under it), the `message` law itself (unchanged).

## Acceptance criteria

- Reading a missing `/mine/missing.md` through a mount at `/mine`
  (parent present) renders
  `ERROR /mine/missing.md: Not found — Check the path with ls or glob, or create the entry first. (retry: never)`.
  When the missing entry is an ancestor, the locus is the ancestor and
  the requested row is the second entry in `data`, with no path in the
  message.
- No `ResultError.message` produced in `src/` contains a path; the new
  test pins it for every kind a storage produces.
- No `ResultError.message` or `KindContract.hint` in `src/` contains
  `=True` or the word `kwarg`.
- `edit` of a bytes body refuses `wrong_kind` with the message
  `Binary body; replace it through write`.
- `scripts/ci.sh 3.13` green.
