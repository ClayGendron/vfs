# `dev` is checked after every merge

A draft, written on 2026-11-21. It is not reviewed, and nothing is built.

## The outcome wanted

`dev` is never red without a check saying so. A pull request merges only when its checks have passed on the commit that merges, and every push to `dev` runs the same checks a pull request runs.

## The problem

On 2026-11-21 nine pull requests, 19 to 27, merged into `dev` within fifteen minutes. Each had passed its checks alone. Before each merge, `dev` was merged into its branch, and the checks on that merge commit were still running, or had failed, when the pull request was merged. Pull request 19 failed Lint and Tests on `c437d494`, and pull request 27 failed Lint on `d445a8ef`. Nothing ran on `dev` afterwards.

`dev` was left red, by three tests. The line baselines in `tests/lint/allowlist.py` for `base.py`, `backend.py` and `engine.py` were higher than the files once all nine had merged, and the ratchet test refuses a baseline that is higher than its file. The cancellation sweep of pull request 27 wrote the same body at every cut, and pull request 22 made such a write `unchanged`, so the sweep's expected version was wrong. Each change was correct on its own branch. The branch `dev-is-green-after-the-merges` fixes all three.

Two facts allow this.

- **No workflow runs on a push to `dev`.** `test.yml`, `test-dialects.yml`, `lint.yml` and `docs-site.yml` run on a push to `main` and on a pull request. A merge into `dev` is a push to `dev`, so it runs nothing.
- **`dev` has no branch protection and no ruleset.** A pull request can merge with its checks red or still running, and nothing requires a branch to be up to date with `dev` before it merges.

Two runs of the engine legs were left undone on 2026-11-19. The SQL Server leg could not run on the laptop used: every test failed before any statement was sent, because the ODBC driver could not load OpenSSL, which Homebrew installed and did not link. And the other legs ran against containers that had been up for three days, not fresh ones. The Dialect tests workflow builds fresh containers on every run, so a required Dialect check on `dev` answers the second. The first is answered by `agents/2026-11-20-vfs-serves-sqlite-and-postgres-only/spec.md` on the branch `vfs-serves-sqlite-and-postgres-only`, if it is taken, since SQL Server then leaves the supported engines.

## Decisions

1. **Every workflow that runs on a pull request also runs on a push to `dev`,** with the same `paths` filter. A red `dev` is then visible within one run of the merge that made it.
2. **A ruleset on `dev` requires the checks to pass before a merge,** and requires the branch to be up to date with `dev`. The required checks are the Tests job's matrix legs, Lint and Docs site. The Dialect tests are required too while they run on every pull request that touches storage.
3. **Merges stay a person's act.** The ruleset adds no automatic merge and no merge queue. A merge queue is the later step if several pull requests often land within an hour.

## Cost

The push runs double the CI minutes of each landing, about four minutes of Tests and two of Dialect tests each. The up-to-date rule makes the second of two pull requests that land together wait for one more run of its checks after the first merges. On 2026-11-21 that is eight more runs, which is the price of finding today's three failures before the merge and not after.

## Tests

The workflows have no test in `tests/`. The check is by hand: a branch whose merge with `dev` fails the ratchet shows a red required check, and its merge button stays disabled.

## Scope

In: the `on:` blocks of the four workflows, and the ruleset on `dev`, which is set in the repository's settings or with `gh api`. Out: `main`, which a release moves, and the publish and deploy workflows.

## What the docs must say

`documentation/maintainers/how-we-work.md`, under "Branches", says that a pull request merges only on green required checks and with `dev` merged in, and that every push to `dev` runs the checks.

## Not checked

- Whether the account's plan allows a ruleset on a private repository.
- Which job names GitHub reports for the matrix legs, which a ruleset names exactly.

## Choices to confirm

1. **Are the Dialect tests a required check?** Recommended: yes. Alternative: no, since a dialect leg is the slowest and the most likely to fail for a reason outside the change. Its cost: a storage change can land red on an engine.
2. **Is the up-to-date rule taken?** Recommended: yes. Alternative: no, and rely on the push run to show a red `dev` after the fact. Its cost: a red `dev` until someone fixes it, as on 2026-11-21.

## One line

Every push to `dev` runs the checks, and a pull request merges only when its checks have passed with `dev` merged in.
