# A line has a verb budget, a host sets the shell's budgets, and a cli call may only tighten them

A draft, written on 2026-11-21 from a staff review of the shell before its pull request, the spec review's L8 of `agents/2026-11-21-the-shell-speaks-bash/reviews/spec-review.md`, and roadmap F7.4. It is not reviewed, and nothing is built.

Ruled on 2026-11-22: this lands before `0.1.0b1`, when the public surface is frozen, not in the `0.1.0` gate after it.

## The outcome wanted

A line that would make 100,000 verb calls ends on a budget of its own, not on its deadline; a host sets the shell's budgets once, at construction; and a caller of `cli`, which an agent reaches over MCP, can lower a budget and never raise one.

## Builds on

The budgets of `vfs.shell.run_line` (`LIMITS`, `fuel`, `deadline`) and the machine's `Limits`.

## The problem

- Requests and bytes written are bounded only by the 30-second deadline: the prior-art memo ran 100,000 `touch` and 400,000 `cat` calls in under a second on memory storage.
- `cli` takes no budget, and a parameter that took the same names as `run_line` would let a caller raise its own fuel.
- Nothing bounds how many lines run at once on one router, and each may hold 256 MiB of module memory, 64 MiB of bodies and 16 MiB of output.
- One caller's lines can make another caller's lines wait. Measured by the second structural review (`agents/2026-11-21-the-shell-speaks-bash/reviews/structural-review-2.md`): 32 lines at once, each in a slow pattern match, made a concurrent `echo hi` wait 6.0 seconds, while reads and writes beside them stayed under 150 ms. A pattern match cannot yield, so its slice holds a worker of the shared offload pool, one thread a core, until its fuel runs out.

## Decisions

1. `VERB_CALL_BUDGET`, 10,000 verb calls a line, counted by the machine for every request it sends; the line ends with status 137 at the budget.
2. `AsyncVirtualFileSystem(shell_budgets=…)` sets the budgets for every line on that router.
3. `cli(…, limits=…)` may lower any of them; a higher value is `invalid`.
4. A bound on concurrent lines per router, with a declared default, and a line that waits for its turn under its own deadline.
5. The shell's slices run on a pool of their own, beside the offload pool, so a line can delay only other lines and never another caller's verbs.

## Tests

A counted loop ends at exactly the verb budget; a `cli` call that raises a budget is `invalid`; the concurrent bound is held with a counted test.

## Scope

The machine's limits, the vfs host, `cli` on all four faces.

## Not checked

The concurrent bound's default against the reference deployment's 20 calls a second at peak.

## Choices to confirm

The verb budget's default; the concurrent bound's default.

## One line

A host decides how much a line may do, and a caller can only ask for less.
