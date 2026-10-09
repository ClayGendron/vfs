# 154 — Error text states the cause: no mount-local path in `message`, no Python keyword in a hint

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** fix (results envelope contract; ~17 producer sites and one
  hint table)
- **Depends on:** the envelope's rebase law as built
  (`src/vfs/results/envelope.py`: seams touch `path`/`source`/`data`,
  never `message`) and the render line in `results/render.py`.
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
   The locus is `path` (and `data["target"]` where a producer sets it),
   and the renderer already prints `SEVERITY <path>: <message>`.
   Where the message needs to name a *second* entry (a move whose
   destination parent is missing), the second entry goes in `data`
   under a named key and the message says "destination parent not
   found".
2. **A hint names no language.** Replace every `pass X=True` and
   `kwarg` wording in `KIND_CONTRACTS` and in producer messages with
   caller-neutral phrasing: "or request the scan tier (`allow_scan`)",
   naming the parameter in backticks as a parameter, not as Python.
3. **The edit refusal on a binary body says what to do.** Its message
   reads `Binary body; replace it through write` so the verb to use is
   in the text an agent sees.

## Scope

- Audit every `f"...{path}"` message in `results/envelope.py`,
  `results/kinds.py`, `editing.py`, `permissions.py`, `base.py`, and
  the database backend's `topology`, `edges`, `staging`, `writes`,
  `rights` and `descent` modules (the memo counted ~26 sites; a grep
  for `Not found|Already exists|Is a directory` with an f-string brace
  finds 17 today). Strip the path, keep the cause.
- Rewrite the `unindexable_pattern` contract hint and the grep
  producer's message.
- A test under `tests/results/` that renders each classified kind
  through a mount at `/m` and asserts the message contains no `/`-led
  path token.
- Out of scope: the renderer's layout (155), the `message` law itself
  (unchanged).

## Acceptance criteria

- Reading a missing `/mine/missing.md` through a mount renders
  `ERROR /mine/missing.md: Not found — Check the path with ls or glob, or create the entry first. (retry: never)`.
- No `message` produced in `src/` contains a path; the new test pins
  it for every kind a storage produces.
- No hint or message in `src/` contains `=True` or the word `kwarg`.
- `scripts/ci.sh 3.13` green.
