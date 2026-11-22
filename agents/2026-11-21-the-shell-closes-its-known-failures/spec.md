# The shell closes its known failures and counts depth by construct

A draft, written on 2026-11-21 from the shell's `progress.md` and its structural review. It is not reviewed, and nothing is built.

Ruled on 2026-11-22: this lands before `0.1.0b1`, when the public surface is frozen, not in the `0.1.0` gate after it.

## The outcome wanted

`tests/shell/known_failures.txt` is empty, 40 nested `$( )` parse as bash parses them, every node of the tree carries its span, and the Oils spec-suite rate is measured and published with its commit.

## Builds on

`agents/2026-11-21-the-shell-speaks-bash/spec.md`, whose steps 6 and 7 are done when no case is left in the known-failures list, and the differential fuzzer `scripts/shell_fuzz.py`.

## The problem

- 145 cases fail: most in `printf` (bash formats floats as `long double`), the parameter operators, `declare`, `mapfile` and redirections; four are finds under `tests/shell/cases/found/` (a backslash before a letter in a quoted default word, a variable inside an extglob group, a here-document ended by the end of input, a delimiter spelled as an expansion).
- The parse depth of 200 counts each grammar rule a construct passes through, about six for one `$( )`, so 33 nested substitutions parse and 35 do not; bash runs 40.
- Compound commands carry no span.
- The prior-art memo ran 468 Oils cases (363 agree, 39 differ, 66 skipped); the rate over the whole suite is not measured.

## Decisions

1. The parse depth counts one level for each construct a line nests (a compound command, a substitution, a subshell, a group, a function body, a `[[ ]]` or arithmetic nesting), and the stacks are sized again by measurement so the declared budgets still fire before the runtime's.
2. `printf`'s floats use an 80-bit extended format of the crate's own, so `%.20f` and `1e309` print as bash prints them.
3. Every node of the tree carries its span.
4. The Oils suite is run from a pinned commit of the sibling clone when the score is measured, outside the gate.

## Tests

The corpus ratchet itself; a law that 200 nested substitutions parse and 201 spend the depth.

## Scope

The crate.

## Not checked

How many of the 145 share a cause.

## Choices to confirm

Whether the depth counted by construct keeps the name and the default of 200.

## One line

Every recorded case passes, and the depth budget counts what a line nests.
