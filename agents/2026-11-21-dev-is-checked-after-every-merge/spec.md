# `dev` is checked after every merge

A draft, written on 2026-11-21. It is not reviewed, and nothing is built.

## The outcome wanted

A morning's green pull requests are reviewed and merged one after another, in order, with no wait for CI between merges. `dev` is checked once the merges are done, a red `dev` is seen within one run, and it is made green by a follow-up pull request. A merge is never blocked by a check on `dev`.

## The problem

On 2026-11-21 nine pull requests, 19 to 27, merged into `dev` within fifteen minutes. Each had passed its checks alone. Before most merges, `dev` was merged into the branch with GitHub's "Update branch", which started a new run, and the pull request was merged while that run was still going or after it had failed. Nothing ran on `dev` afterwards, so `dev` stayed red with no check saying so.

Three tests were red. Two were the line ratchet in `tests/lint/test_code_shape.py`: it refuses a file that holds fewer lines than its entry in `tests/lint/allowlist.py`, and several branches each shrank `base.py`, `backend.py` and `engine.py` and each lowered or kept the same entry, so once all had merged, the files were below their entries. The third was a real clash: the cancellation sweep of pull request 27 wrote the same body at every cut, and pull request 22 made such a write `unchanged`. The branch `dev-is-green-after-the-merges` fixes all three.

Three facts make this happen.

- **No workflow runs on a push to `dev`.** `test.yml`, `test-dialects.yml`, `lint.yml` and `docs-site.yml` run on a push to `main` and on a pull request.
- **No workflow cancels a run that a newer commit replaces.** None has a `concurrency` group.
- **The ratchet fails when two branches each shrink one file.** Pull requests 23 and 24 both said that whichever landed second "needs a one-line rebase". With ten branches open, that is the most likely red.

Gating every merge on the state of `dev` is not taken. A rule that a branch be up to date with `dev` before it merges makes each of ten merges wait for one more full run, about forty minutes of waiting for a morning's ten. GitHub's merge queue, which tests the combined state without a person waiting, serves repositories that belong to an organization, and this one belongs to a user.

## Decisions

1. **Every workflow that runs on a pull request also runs on a push to `dev`,** with the same `paths` filter.
2. **The push runs on `dev` share a `concurrency` group that cancels a run in progress.** Ten merges in a row then run the suite in full once, on the last of them, and not ten times. A red run names the commit it ran on, and the follow-up finds which merge broke it.
3. **A pull request is merged when its own checks are green when it is reviewed.** "Update branch" is pressed only when GitHub reports a conflict. A run on a branch that `dev` was merged into is not waited for.
4. **A red `dev` is fixed by a follow-up pull request,** and nothing else is merged on top of a red `dev` that the fix would conflict with. The fix is the first work of the next session, guided or autonomous.
5. **The line ratchet refuses only growth.** A file below its entry passes. The entry is lowered by whichever change wants the room back, or by the follow-up of decision 4. This is a change to what the lint holds, and it is a choice below.
6. **Pull requests are squashed,** as `how-we-work.md` already says. On 2026-11-21 they were merged as merge commits, so `dev` holds the branches' save points and the merges of `dev` into each branch.

## Cost

One full run of each workflow per batch of merges, cancelled down from one per merge. A red `dev` lasts from the last merge of a batch until the follow-up lands, which on 2026-11-21 would have been one small pull request.

## Tests

The workflows have no test in `tests/`. The check is by hand, once: three trivial pull requests merged in a row start three push runs on `dev`, the first two are cancelled, and the third runs to its end. For decision 5, the test of `size_faults` that expects "lower the entry" is changed first, and seen failing against today's rule.

## Scope

In: the `on:` and `concurrency:` blocks of the four workflows, `size_faults` and its test in `tests/lint/test_code_shape.py`, and the "Branches" section of `documentation/maintainers/how-we-work.md`. Out: `main`, the publish and deploy workflows, and any rule on merging.

## What the docs must say

`how-we-work.md`, under "Branches": a pull request is merged when its own checks are green, in the order it was reviewed, without "Update branch" unless there is a conflict; every push to `dev` runs the checks, and a newer push cancels an older run; a red `dev` is fixed by a follow-up pull request before anything that conflicts with the fix is merged.

## Not checked

- Whether GitHub can be told to notify the owner of a failed push run on `dev` only, and not of the cancelled ones.

## Choices to confirm

1. **Decision 5: does the ratchet refuse only growth?** Recommended: yes. Alternative: keep the strict rule. Its cost: two branches that shrink the same file make `dev` red each time both land, as on 2026-11-21.
2. **Decision 6: squash?** Recommended: yes, as `how-we-work.md` already says.

## One line

Green pull requests are merged in order with no wait, every push to `dev` runs the checks once per batch, and a red `dev` is fixed by a follow-up.
