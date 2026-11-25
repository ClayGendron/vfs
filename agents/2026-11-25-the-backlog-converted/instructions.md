# The backlog conversion is finished in seven steps, in this order, and ends with one pull request to dev

This page is the whole procedure for finishing the work of this directory. It is written so that it can be followed with no other account of the work. Where it and `AGENTS.md` disagree, `AGENTS.md` wins and this page is corrected. It is deleted in the commit that opens the pull request, since nothing is left for it to say.

## What done means

The request this work answers: every spec of the backlog is either removed, or converted to the structure under `agents/` and made fit to build, and the work ends with a pull request to `dev`.

Done is all of these, each one checkable:

1. `uv run python agents/2026-11-25-the-backlog-converted/tools/state.py` prints `missing 0` and `unreviewed 0`.
2. Every unit it counts under `not_yet` is named in the pull request with the findings still open.
3. `uv run python agents/2026-11-25-the-backlog-converted/check_shape.py agents/2026-11-25-*/spec.md agents/2026-11-25-*/reviews/*.md` prints nothing.
4. `uv run pytest tests/lint -q -n0 -p no:cacheprovider`, `scripts/ci.sh` and `scripts/docs.sh check` pass on the last commit.
5. The work branch holds all of `origin/dev`, the tree is clean, and `git worktree list` shows one checkout.
6. One pull request from the work branch to `dev` is open, with the body step 7 gives, and it is not merged.

## Where the work stands on 2026-11-25

- The work branch is `claude/dreamy-brahmagupta-y1wphu`. It holds all of `dev` at `27f3d24d`.
- [state-on-dev.md](state-on-dev.md) lists all 88 units. 16 owe no spec. Of the 72 that do, 36 are written and none is reviewed, and 36 are not written.
- The 36 unwritten specs stopped at a weekly usage limit that resets on 2026-12-01 at 02:00 UTC.
- The thirty numbered specs are archived under `context/specifications/archive/`, each with a disposition line and a line giving its state against `dev`. That part is finished.
- Of the eight dated specs under `context/specifications/active/`, one is withdrawn and five are amended to `dev`. Step 5 says what each still owes.
- `scripts/ci.sh` and `scripts/docs.sh check` have never been run on this branch.

## The files of this directory

- [state-on-dev.md](state-on-dev.md): every unit, its gate, its verdict against `dev`, and the state of its spec. Generated; never edited by hand.
- `tools/state.py`: writes `state-on-dev.md` from `tools/units.json` and the files on disk.
- `tools/units.json`: the 88 units. `spec_owed` says whether a spec is written for the unit; `dev_holds` says what `dev` already has of it.
- `tools/tasks.json`: the 72 units that owe a spec, each with what remains on `dev`, what covers the rest, the specs it builds on (`deps_dirs`) and its `layer` in the build order.
- `tools/prompt.py`: prints the full instructions for one task on one unit. Its five tasks are `write`, `check`, `review`, `answer` and `reread`.
- `check_shape.py`: checks a spec or a review against the templates.
- `reassessment/`: ten files, one section per unit, giving the unit's state against `dev` with citations. `dated-1.md` and `dated-2.md` do the same for the dated specs.
- [dev-index.md](dev-index.md): the work directories of `dev` and the open branches of `origin` that `dev` does not hold.
- [units.md](units.md), `studies/`, `decisions/`: the first sort, made against `main` at `0ed462f`. Background only. Nothing in them is used until it is checked against `dev`.
- [the spec template](../templates/spec.md) and [the review template](../templates/review.md): the two shapes.

## Rules that hold through every step

1. **One context writes, another reviews.** A spec is written by one fresh context, reviewed by a second and amended by a third, which may be the first. The context that reviews or re-reads a spec has never seen it written or amended. The coordinating session writes no spec and no review itself; it starts the contexts, reads what they return, runs the checks and commits.
2. **A context is given the output of `tools/prompt.py` and nothing else.** No summary, no reasoning, no expected verdict is added. A context is started on the most capable model the session can use.
3. **Parallelism.** Up to twelve contexts run at once on a four-CPU container. Contexts in one batch never share a file: one unit, one context. A workflow tool that caps a run at two contexts is used as six runs side by side.
4. **A usage limit is a stop, not a failure to route around.** When a context is refused for a limit, the batch is finished with what returned, the state is saved by step 2's closing commands, and the work waits for the reset. No spec is written in the coordinating session to save time.
5. **Every shell command gets a timeout** of about twice its estimate. Everything runs through `uv`.
6. **No test suite, no `uv sync` and no state-changing git command runs inside a writing or reviewing context.** The coordinating session alone commits.
7. **Voice.** Every file under `agents/` is impersonal: no name, no "I", "we" or "you", nothing about who did what. `check_shape.py` reports a breach.
8. **Nothing built or specified by `dev` is edited.** The only directories this work writes under `agents/` are those dated `2026-11-25` and `agents/templates/`.
9. **A save is a commit and a push.** Decided 2026-11-25: a push of this work to the work branch needs no further question. Each batch ends with a commit whose subject says what was written in words, then `git push -u origin claude/dreamy-brahmagupta-y1wphu`, retried up to four times on a network error. A push that is rejected because the remote holds commits is answered by `git fetch origin claude/dreamy-brahmagupta-y1wphu` and `git merge --no-edit FETCH_HEAD`, never by a forced push.
10. **Commit messages** say what changed and what was not done, carry no model name in the text, and end with the attribution lines the session supplies.
11. **A session confined to another branch** starts that branch from `origin/claude/dreamy-brahmagupta-y1wphu`, works there, and opens the pull request from it; the pull request says which branch holds the work.

## Step 0. Read where the branches stand, and set up

Run, with a 120 second timeout:

```bash
git fetch origin
git log --oneline -1 origin/main && git log --oneline -1 origin/dev && git log --oneline -1 HEAD
git rev-list --left-right --count HEAD...origin/dev
git log --oneline HEAD..origin/dev
git status --short | wc -l
git worktree list
```

State the finding in one line: how many commits `dev` holds that the branch does not.

If `dev` holds any, in this order:

1. `git merge --no-edit origin/dev`. A conflict in a file of `dev`'s is resolved to `dev`'s side. A conflict in a file of this work keeps this work's text and takes any fact `dev` changed.
2. `git diff --stat 27f3d24d origin/dev -- agents/ src/ context/standards/roadmap.md` and `git log --oneline 27f3d24d..origin/dev`. For each work directory `dev` gained or changed and each roadmap ruling it recorded, find the units of `tools/tasks.json` it touches by reading the titles in `state-on-dev.md`.
3. A unit that `dev` now builds or specifies whole: in `tools/units.json` set its `verdict` to `built-on-dev` or `specified-on-dev`, `spec_owed` to `false` and `dev_holds` to the work directory's path; delete its entry from `tools/tasks.json`; and `git rm -r` its directory if one was written.
4. A unit that `dev` now covers in part: rewrite its `covered_by` and `remaining` in `tools/tasks.json`, and if its spec is written, delete the spec so that it is written again.
5. Replace `27f3d24d` in step 0 of this page and in the second bullet of "Where the work stands" with the new commit of `dev`.

Then set up the environment, with a 600 second timeout, about three minutes:

```bash
rustup target add wasm32-unknown-unknown
uv sync --all-extras --group dev --reinstall-package vfs-py
uv run python agents/2026-11-25-the-backlog-converted/tools/state.py
```

Docker is not assumed. A Postgres leg result is never written as produced unless it ran.

## Step 1. Three choices are taken as written here before any spec is written

1. **All 36 unwritten specs are written, in gate order.** 21 serve gate `b`, 8 serve gate `f`, 5 serve `0.2` and 2 are unplaced. 0.1.0 needs the first 29. The other 7 are written last: 169-4, 169-5, 180-3, 180-5, 180-6, 179-8 and 179-9. If a ruling removes them from this work, each is set to `spec_owed: false` in `tools/units.json` with `dev_holds` reading "deferred past 0.1.0 by a ruling of <date>", and deleted from `tools/tasks.json`.
2. **The five tool and view units follow the roadmap's leans.** Units 169-2, 169-3, 170-2, 170-3 and 170-4 were first designed around `/.vfs/tools` and a retired `run`. The roadmap on `dev` leans the other way in decisions D63 and D64: `run` is kept as the one verb that runs a tool, and tools are files in a served `/.vfs/bin` found through `PATH`. The design is drafted on the open branch `origin/a-call-is-interrupted-and-the-host-asks`. These five specs are written on the leans, cite that branch's spec by decision number, and list each lean under Choices to confirm with the side taken. 169-2 and 170-2 stay two specs: 169-2 owns the views and the lookup, 170-2 owns registering a host function.
3. **A choice with no reversible side stops that one spec, not the work.** Its writer lists it as one the build waits for; the spec is still written, reviewed, and reported in the pull request under "Waits for a ruling".

## Step 2. Write the 36 specs, a layer at a time

A layer holds the units whose dependencies are all in earlier layers. A layer is finished before the next begins, so that each writer reads the specs it builds on.

| Layer | Units to write (gate) |
|---|---|
| 1 | 149-2 (b), 170-1 (b), 175-2 (b), 177-3 (b), 178-2 (b), 179-6 (f), 180-1 (f), 179-8 (unplaced), 180-5 (0.2) |
| 2 | 167-8 (b), 175-3 (b), 177-4 (b), 178-3 (b), 179-7 (f), 180-2 (f), 179-9 (unplaced) |
| 3 | 167-9 (b), 169-2 (b), 171-1 (b), 168-3 (f), 179-10 (f), 180-3 (0.2) |
| 4 | 169-3 (b), 171-2 (b), 172-1 (b), 167-10 (f), 180-6 (0.2) |
| 5 | 149-3 (b), 170-2 (b), 171-3 (b), 172-3 (b), 169-4 (0.2) |
| 6 | 170-3 (b), 169-5 (0.2) |
| 7 | 170-4 (b) |
| 8 | 170-5 (f) |

The `0.2` and unplaced units of a layer may be left until layer 8 is written, since nothing at gate `b` or `f` builds on them.

For each layer:

1. For each unit of the layer, start one fresh context with the output of `uv run python agents/2026-11-25-the-backlog-converted/tools/prompt.py write <key>`, all of the layer's units at once.
2. When all have returned, run `uv run python agents/2026-11-25-the-backlog-converted/check_shape.py <each spec written>`. The only fault allowed is `dead link` to a spec that `state-on-dev.md` lists as not written. Any other fault goes back to a fresh context with the `write` instructions and the fault lines appended under the heading "Faults to fix in the existing file".
3. Read the first paragraph and the `Choices to confirm` section of each spec returned. Keep a list, in the session, of every choice a writer said the build waits for; it goes into the pull request.
4. A unit whose context returned nothing, or was refused, is run once more. A second failure for a limit ends the batch under rule 4.
5. Close the layer:

```bash
uv run python agents/2026-11-25-the-backlog-converted/tools/state.py
uv run pytest tests/lint -q -n0 -p no:cacheprovider
git add -A agents/ && git commit    # subject: docs(agents): layer N of the backlog specs written against dev
git push -u origin claude/dreamy-brahmagupta-y1wphu
```

Step 2 is finished when `tools/state.py` prints `missing 0`.

## Step 3. Check every spec against the specs it builds on

The 36 specs written first quote sibling specs that did not exist then. Each of the 72 is now checked once, lowest layer first, the `layer` field of `tools/tasks.json` giving the order.

1. For each unit of a layer, start one fresh context with the output of `tools/prompt.py check <key>`, a layer at a time.
2. After the last layer, run `check_shape.py` over `agents/2026-11-25-*/spec.md`. It prints nothing. A dead link that remains points at a directory this work no longer plans: the two known are `2026-11-25-the-dead-run-verb-leaves-every-face` (unit 167-1, moot because `run` is kept) and `2026-11-25-chaining-moves-onto-the-result-and-the-query-verbs-lose-rows-in-hand` (unit 181-3, moot because `dev` kept and extended rows in hand). The `check` instructions say how each is replaced.
3. Close with the same four commands as a layer of step 2, with the subject `docs(agents): the backlog specs agree with the specs they build on`.

## Step 4. Review every spec until it is fit to build or its open findings are named

Each of the 72 specs goes through the rounds of [the review template](../templates/review.md). Gate `b` units go first, then `f`, then the rest; within a gate, lowest layer first. A batch is twelve units.

For each unit:

1. **Review.** A fresh context is given `tools/prompt.py review <key>`. It writes `<unit directory>/reviews/<date>-spec-review.md` and edits nothing else.
2. **If the verdict begins "Fit to build" and the review holds no Low**, the unit is done.
3. **Answer.** Otherwise a second fresh context is given `tools/prompt.py answer <key>`. It amends the spec and fills the review's Disposition.
4. **Re-read.** A third fresh context, never the one that answered, is given `tools/prompt.py reread <key>`. It confirms each Disposition line and adds the dated verdict line.
5. **A second round, once.** If the dated line begins "Not yet", steps 3 and 4 are run one more time. If the second dated line still begins "Not yet", the unit stops there and is reported in the pull request with the findings its last line names. No third round is run.
6. A spec amended in step 3 may have changed a shape another spec quotes. After a batch, every unit whose `deps_dirs` holds a directory amended in that batch is given `tools/prompt.py check <key>` again, unless it is already fit to build, in which case its review gains one more `reread`.

Each batch closes with the four commands of step 2, with the subject `docs(agents): N backlog specs reviewed, M fit to build`.

Step 4 is finished when `tools/state.py` prints `unreviewed 0` and every unit under `not_yet` has had two rounds.

## Step 5. The dated specs under context/

These eight finish under the earlier pipeline: [context/README.md](../../context/README.md) and `context/reviews/README.md` give their shapes, `tests/lint/` enforces them, and the `spec_review` skill is the review procedure, writing to `context/reviews/`. The reviewer is a fresh context, as in rule 1.

| Spec, by its date and first words | State | What is done in this work |
|---|---|---|
| 2026-11-15, on SQL Server a read never waits | withdrawn and archived | nothing |
| 2026-11-07, the release audit is a review | built on `dev` | nothing; listed in the pull request as built, with its landing paperwork owed |
| 2026-11-15, the kernel's public names are ruled | built on `dev` | nothing; listed the same way |
| 2026-11-14, a miss beneath a row | amended to `dev`; its 2026-11-25 review is answered and not re-read | one re-read of that review's Disposition, adding the dated verdict line; one further answer and re-read if it is "Not yet" |
| 2026-11-14, the docs site is a Svelte app | amended to `dev`; its 2026-11-25 review is answered and not re-read | the same |
| 2026-11-14, the rights compile is the same at every world size | amended to `dev`; its standing review signed a draft from before the merge | one fresh spec review with the `spec_review` skill, then at most two rounds |
| 2026-11-15, lint finds what is broken | amended to `dev`; never reviewed | if its first paragraph says it waits on an experiment, nothing, and it is listed as waiting; otherwise one fresh spec review with the security lens, then at most two rounds |
| 2026-11-14, a release or a manual run deploys the docs | a placeholder that waits on its memo and on the DNS zone | nothing; listed as waiting on both |

Close with the lint tier, a commit with the subject `docs(context): the dated specs re-read against dev`, and a push.

## Step 6. The gates

Run in this order, each with the timeout given, on a clean tree:

```bash
git fetch origin && git rev-list --left-right --count HEAD...origin/dev          # 60 s; the second number is 0, else step 0 again
uv run python agents/2026-11-25-the-backlog-converted/tools/state.py             # 60 s
uv run python agents/2026-11-25-the-backlog-converted/check_shape.py agents/2026-11-25-*/spec.md agents/2026-11-25-*/reviews/*.md   # 120 s; prints nothing
uv run pytest tests/lint -q -n0 -p no:cacheprovider                              # 120 s
scripts/ci.sh                                                                    # 900 s; about a minute warm, several cold
scripts/docs.sh check                                                            # 900 s; needs bun
git worktree list                                                                # one line
```

`scripts/ci.sh` is owed because the branch changes `tests/lint/allowlist.py`. `scripts/docs.sh check` is owed because it changes `documentation/maintainers/how-we-work.md`. A gate that fails on a file this work changed is fixed. A gate that fails on a file this work did not change is run once on `origin/dev` in a worktree under the session's scratch directory, removed afterwards: if it fails there too, the failure is `dev`'s and is reported in the pull request with its output, not fixed here. A timeout that fires is diagnosed, never raised and run again.

## Step 7. The pull request

1. `git rm agents/2026-11-25-the-backlog-converted/instructions.md`, remove the sentence of `tools/state.py`'s header that links to it, run `tools/state.py`, commit with the subject `docs(agents): the backlog conversion's procedure is removed, its work done`, and push.
2. Confirm that the repository still holds no pull request template (`.github/` held only `workflows/` on 2026-11-25). If one exists, its headings are used and the sections below are fitted under them.
3. Open one pull request with the GitHub tools: base `dev`, head the work branch, not a draft. It is never merged from the session.
4. Title: `The backlog is sorted against dev: thirty numbered specs archived, N specs written, M fit to build`.
5. Body, with every number read from the last output of `tools/state.py` and never from memory:

```markdown
## What this changes

- The thirty numbered specs under `context/specifications/active/` are archived, each with a line saying what became of it.
- The backlog they held is 88 units, each one spec and one pull request. Sorted against `dev`: <none> owe no spec because `dev` built it, specified it or removed its ground; <owed> owe one.
- <written> specs are written under `agents/2026-11-25-*/`, in the shape `dev`'s specs share, now written down in `agents/templates/spec.md` and `agents/templates/review.md`.
- AGENTS.md and How we work gain one rule: read where `main` and `dev` stand before work starts and before each push.
- One dated spec is withdrawn (SQL Server is no longer served) and five are amended to `dev`.

No file under `src/` or `crates/` changes. The one change under `tests/` is the path of the archived specs in `tests/lint/allowlist.py`.

## State of the specs

| State | Count |
|---|---|
| Fit to build | <fit> |
| Reviewed, not yet fit | <not_yet> |
| No spec owed | <none> |

The list of all 88 is `agents/2026-11-25-the-backlog-converted/state-on-dev.md`.

## Not yet fit, with what is open

<one line per unit: key, title, the findings its last verdict line names; or "None.">

## Waits for a ruling

<one line per choice the build waits for: unit, the choice, the options; or "None.">

## Choices taken that a ruling can overturn

<the two of step 1, then one line per unit that holds a Choices to confirm section, naming the unit and how many entries it holds>

## The dated specs

<one line per row of step 5's table, with its state after step 5>

## What ran, and what did not

- `scripts/ci.sh`: <passed, or the failing lines>
- `scripts/docs.sh check`: <passed, or the failing lines>
- The lint tier: <N passed>
- No engine leg ran. No spec's Postgres claim was executed; each spec says so under Not checked.
- Every spec was reviewed by a context that did not write it. No spec has been read by a person.
```

6. The body ends with the attribution lines the session supplies. After the pull request is open, the question whether to watch it is put once.

## What is never done in this work

- No code under `src/`, `crates/` or `docs-app/` is written. A spec that seems to need a probe of behaviour gets a read-only script in the session's scratch directory.
- No spec is marked fit to build by the context that wrote or amended it, or by the coordinating session.
- No verdict line of a review is edited after it is written; a later reading adds a dated line.
- No unit is dropped, merged or split without the change being made in `tools/units.json` and `tools/tasks.json` and named in the pull request.
- No file of `dev`'s own work directories, no archived spec and no standard is edited after step 0.
- No pull request is merged, and no branch but the work branch is pushed.
