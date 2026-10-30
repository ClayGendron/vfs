# Study 7: the commit — how a change lands on main

This is a study for [the development-process memo](../../2026-10-29-the-development-process-seven-studies-and-what-they-recommend.md), owned by Clay Gendron. Its question: what is the commit message format? What does the landing step do, in order? What gate holds it when there is no pull request? Should vfs adopt a news-file or changelog convention? Its method: read vfs's own history (`git log` over the last sixty commits, five full messages, two archived specs' status lines and landing notes, the archive-move commits), the standards (`commits-and-prs.md`, `release.md`, `contributing.md`), `scripts/ci.sh`, the two workflows, and [the intention](../../../intentions/2026-10-29-the-development-process.md); read the sibling project wasi-python read-only at `1431ba6f` (2026-10-28, Apache-2.0), thirty subjects, three full messages, AGENTS.md's commit rules and steps 5 to 9 of "Working autonomously", `context/changes/README.md`, one news file, constitution §5.4; read five online sources. Nothing was copied; every line here is described in our words. No git command that changes state was run.

## Sources

- vfs at `1198d92` (2026-10-29).
- wasi-python at `1431ba6f` (2026-10-28), `~/Git/Repos/wasi_python`, Apache-2.0.
- Conventional Commits 1.0.0, https://www.conventionalcommits.org/en/v1.0.0/ (read 2026-10-29).
- Chris Beams, "How to Write a Git Commit Message", https://cbea.ms/git-commit/ (read 2026-10-29).
- Linux kernel, "Submitting patches", https://www.kernel.org/doc/html/latest/process/submitting-patches.html (read 2026-10-29).
- Git, "SubmittingPatches", https://git-scm.com/docs/SubmittingPatches (read 2026-10-29).
- towncrier tutorial, https://towncrier.readthedocs.io/en/stable/tutorial.html (read 2026-10-29).
- changesets README, https://github.com/changesets/changesets (read 2026-10-29).
- Keep a Changelog 1.1.0, https://keepachangelog.com/en/1.1.0/ (read 2026-10-29).
- The owner's ruling of 2026-10-29, relayed mid-study: no numbers in document file names; a subject names the change in words; the body cites the spec by its relative path.

Two terms used throughout. A **landing** is the moment a change becomes part of `main`. A **trailer** is a `Key: value` line at the end of a commit message that git can read by key (`git log --format='%(trailers:key=Spec)'`).

## What vfs does today

### The commit subject (EXECUTED: `git log --format='%h %s' -60`)

Every one of the last sixty subjects has the shape `type(scope): words`. The types seen are `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `ci`. The scope is a module or a folder (`storage`, `base`, `results`, `grants`, `context`, `standards`, `readme`, `dialects`) and is sometimes omitted (`test:`, `ci:`). The words after the colon are a sentence, lower-case, no full stop, often with an em dash. Examples:

- `feat(storage): graph traversal as a frontier walk — inbound, outbound, neighborhood and meet on every dialect (spec 164, ADR 079)`
- `fix(storage): a create clears no body rows, because a row minted in this batch has none`
- `docs(context): six landed specs move to the archive`
- `ci: the local gate is the 3.13 leg, on coverage's sys.monitoring core`

Subjects are long. Many run 90 to 130 characters. Twenty-one of the sixty carry a parenthesised reference at the end: `(spec 164, ADR 079)`, `(spec 163, slice 4)`, `(spec 152, slice B)`. The owner's ruling of today ends this: a subject names the change in words, never a number.

### The body and the trailer (EXECUTED: `git show -s --format=%B` on five commits)

A code landing's body is two to four paragraphs. The first says what the change does and the mechanism, in the present tense. The second records the review that preceded it, where there was one (`ac5c515`: the spec "scored 48/100 as drafted" and "nine amendments were folded in before a line was written"). A third, headed "Also carried:", lists what rode along (fresh oracles, amended ADRs, a conformance family). The last line of prose states what did not run ("Engine legs not run here.", "The engine legs have not run."). Every one of the five ends with one trailer, `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. No commit carries a `Spec:` or `Reviewed-by:` trailer; the spec is named only in the subject's suffix and in prose.

### The landing was two commits, sometimes three (EXECUTED: `git log --grep=archive -i`)

Today the code lands in one commit and the record lands in another, later. Spec 163 landed as six slice commits (`49ca62e` to `38069e4`), then `6025af2 docs(context): spec 163 built — landing notes, STATUS, skill counts`, then `78e4085 docs(context): six landed specs move to the archive`. The archive move came ten days after the code for some specs. Between the code commit and the archive move, the spec sat in `active/` with a status line saying "built" and no landing notes. That is the drift the intention closes.

### How landing is recorded in a spec (READ: two archived specs)

The status line of `context/specs/archive/163-the-one-minute-test-run/spec.md` reads: "landed and archived 2026-10-10 — six slice commits `2bf0138` … `b648082`, the amendment … `12a8f39`, and `b446c76` … not yet mined." The status line of spec 164 reads "**landed 2026-10-14** (ADR 079 accepted the same day; the four slices built in one landing, see *Landing notes*). Reviewed …" and the spec carries a section "Amendments from the pre-build review (2026-10-14)" that describes the review inline. Its "Landing notes" section (line 617) lists what landed per slice, the measured statement counts, two decisions flagged to Clay, and "Engine legs: not run in this landing (no Docker here)". No landing note today cites a review *file*, because the reviews were written into the spec or into a study, not into a file of their own. The landing commits cite the spec by number, not by path.

### The gate and the changelog (READ)

`scripts/ci.sh` is the local gate: sync, `ruff check`, `ruff format --check`, `ty`, pytest at 100 % coverage, the docs fences (`pytest docs README.md`), the wheel under 50 MB. It mirrors the 3.13 leg of `test.yml`. `test.yml` runs on push to `main` and on pull requests, but only when `src/`, `tests/`, `crates/`, the two Cargo files, `pyproject.toml` or the workflows change. A commit that touches only `context/` runs no CI at all. `publish.yml` runs on a published GitHub release and runs no tests.

`CHANGELOG.md` exists. Its `[Unreleased]` section is from the previous generation (`VFSObject`, `DatabaseFileSystem`, story links); `release.md` already says the first v2 section "is written fresh, not renamed". Its last dated section is 0.0.22, 2026-04-22. Nobody has updated it in the rebuild. The standards still say to branch, open a pull request, and never push `main` (`commits-and-prs.md` lines 5 to 7); the live rule in CLAUDE.md is the opposite.

## What the sources say

### wasi-python (READ, `1431ba6f`)

wasi-python runs the flow vfs will not: pull requests into `dev`, a squash merge, a post-merge acceptance job, a release as a pull request from `dev` to `main`. Its subject is `NNN: words (#PR)`, the number first; the owner's ruling today removes numbers from vfs's names, so that shape does not transfer. Its body is a self-check list (the author named, every new check seen failing first, the Windows legs read, the news file present), then the mechanism, then the owner's rulings, then "Reviews:" naming the two review files by path and the verdict, then local verification counts, then the numbered differences from the spec. The acceptance commit (`Accepted: …`) is written by CI and carries the growth claims. Its rules:

- **"Commit only what you mean"**: read `git diff --cached --stat` before every commit, because a `git mv` or an earlier `git add` stays staged and rides along; a commit on `main` is green on its own. This survives without pull requests unchanged. It matters more for vfs, where the landing commit carries a `git mv` of the spec into `archive/` beside the code.
- **"A commit's trailer names the model that wrote it"**: a sub-agent's commit carries its own model's `Co-Authored-By`, not the orchestrator's; the orchestrator checks the trailers before the first push. Survives unchanged; vfs already writes this trailer.
- **Step 5, the news file**: one file per change under `context/changes/`, holding the CHANGELOG lines, package rows and a claim block for the acceptance ledger; CI refuses a pull request without one. The claim block does not transfer (vfs has no fuel ledger). The CHANGELOG-lines half is the changelog question below.
- **Step 6, the run chosen by paths**: CI on the pull request is the judge. Does not transfer; there is no pull request to run it on.
- **Step 7, "one review, its file committed last"**: the review file is the branch's last commit so its push re-uses the green run. The reason is a CI-reuse reason. Without pull requests the reason is gone, and the question becomes whether the review rides in the landing commit (answered below).
- **Step 8, merge when green and the review says "Lands"**: the verdict word transfers. The merge does not; vfs commits.
- **Step 9, the post-merge acceptance**: does not transfer.
- **Constitution §5.4 "Small, finished, verified"**: a landing is one pull request carrying one to three specifications, green, with its landing notes written and its numbers reproduced; half-built work is reported as half-built, not landed. The sentence transfers with "pull request" replaced by "commit".

### Conventional Commits 1.0.0 (READ)

Header `type(scope): description`, blank line, body, footers. `feat` and `fix` are required types; others are free. A breaking change is `!` before the colon or a `BREAKING CHANGE:` footer. `fix` maps to a patch bump, `feat` to minor, breaking to major. The FAQ says to write commits as if the product were already released. vfs already follows the header shape; the footers are git trailers, which is what the recommendation below uses.

### Chris Beams (READ)

Seven rules: blank line after the subject; subject about 50 characters, 72 the ceiling; capitalise; no full stop; imperative mood; wrap the body at 72; the body says what and why, not how. vfs breaks three today: subjects well past 72, lower-case after the colon (deliberate, matches git's own "do not capitalise after the area prefix"), and a declarative rather than imperative mood ("a create clears no body rows"). The declarative is a house choice and reads well in `git log`; the length is not a choice, it is drift.

### Linux kernel and git (READ)

Both: one logical change per commit, each commit builds and runs on its own so `git bisect` works; an area or subsystem prefix on the subject; the body states the problem first, then the change, in plain words, standing alone years later; cite another commit by twelve hex characters plus its subject. Both use trailers: `Signed-off-by` (the certificate of origin), `Reviewed-by` (only the reviewer may add it), `Tested-by`, `Fixes:`, `Link:`. The kernel now has an `Assisted-by:` tag for AI tooling (INFERRED: the page names it; vfs's harness already writes `Co-Authored-By`, which carries the same fact). The lesson for vfs: the review and the spec belong in trailers, so a tool can read them, not in prose or in the subject.

### towncrier, changesets, Keep a Changelog (READ)

towncrier keeps one fragment file per change in a folder, named by ticket and category; `build` assembles them under a version heading and deletes them. changesets keeps one markdown file per change declaring the bump and a summary; `version` consumes them into CHANGELOGs and bumps versions. Both exist to let many branches add changelog lines without conflicting on one file, and to record release intent at change time rather than at release time. Keep a Changelog: sections Added, Changed, Deprecated, Removed, Fixed, Security; an Unreleased section on top; newest first; ISO dates; written for people; and, in its own words, a commit log is not a changelog, because commits record every step while a changelog summarises what a user sees.

## The recommended commit format

Keep the house shape. Change three things: the subject loses its number suffix and gets a length cap; the body gains a fixed order; the spec and the two reviews move into trailers.

**Subject.** `type(scope): words`. Type is one of `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `ci`, `build`. Scope is the top-level module or folder touched (`storage`, `base`, `results`, `context`, `standards`), omitted when the change spans several. The words name the change in plain language, lower-case after the colon, no full stop, no number, no `(spec …)` suffix. Hard cap 72 characters, because that is where every tool truncates (GitHub, `git log --oneline`, `git shortlog`). The em dash stays allowed; the second half after the dash is the first thing to cut when the cap bites.

**Body.** Wrapped at 72. Paragraphs in this order, each present only when it has content:

1. The problem, or what was missing, in the present tense. One to three sentences.
2. What the change does and by what mechanism. This is the paragraph `ac5c515` writes well.
3. What was decided at the build and flagged to Clay.
4. "Also carried:" what rode along.
5. What did not run, said plainly ("The engine legs did not run; no Docker on this machine.").

The body never restates the diff. It never names a spec by number. It may name the spec by path in prose when the path helps the sentence; the trailer carries it in every case.

**Trailers.** Four, in this order, each a line git can read by key:

- `Spec: context/specs/archive/<date>-<slug>/spec.md` — the path the spec has *after* this commit, since the commit moves it.
- `Spec-review: context/reviews/<date>-<slug>-spec.md` — the pre-build review file.
- `Code-review: context/reviews/<date>-<slug>-code.md` — the code review file, verdict "Lands".
- `Co-Authored-By: <model> <noreply@anthropic.com>` — the model that wrote the change, not the session that briefed it (wasi-python's rule, kept).

A `docs(context)` commit that lands no spec carries no `Spec:` trailer. A commit that lands a spec carries all three. The file-name shapes for reviews are the review study's to settle; the trailer carries whatever path exists.

**One commit or several?** The default is one. The landing commit carries the code, its tests, the docs it changes, the review file, the landing notes, the archive move and the architecture page: one `git show` is the whole record, and `git bisect` lands on a spec, not a slice. A spec may land as several commits when every one is green on its own (spec 163's six slices were). Then the last commit of the set is the landing commit, carries the trailers and the context moves, and the review file reads the whole set. The review file rides in the landing commit; it does not get a commit of its own. wasi-python committed it last to re-use a CI run on a branch; vfs has no branch and no run to re-use, and a review that lands one commit after the code leaves a window where the code is on `main` with no review in the tree, which is the thing the intention forbids.

How a reviewer names what it reviewed when there is no commit yet: the review file names the base commit (`git rev-parse HEAD`) and the tree it read (`git add -A && git write-tree`, a forty-character id of the working tree's content). If only `context/` files change after the review, the code the landing commit carries is the tree reviewed. A later lint rule could check this; it is not needed on day one.

```
feat(storage): the guarded append and the write preconditions

Twenty concurrent read-append-writes kept one line and all reported
success: a write has no way to say "only if the row is still at the
version I read". The kernel's write path takes three preconditions,
if_version, if_absent and append, judged inside the row lock in the
pinned statement order, and answers precondition_failed as a Result
row, never an exception. append is a server-side concatenation, one
statement, so a 10,000-file batch issues no extra round trip.

Decided at the build: a precondition on a tombstoned row is judged as
on an absent row, flagged to Clay in the landing notes.

Also carried: the write-path conformance family gains the
precondition rows on every dialect; the write-path architecture page
is redrawn with the precondition step.

The engine legs ran on Postgres and SQL Server; MariaDB and Oracle did
not run on this machine.

Spec: context/specs/archive/2026-10-30-write-preconditions-and-the-guarded-append/spec.md
Spec-review: context/reviews/2026-10-30-write-preconditions-and-the-guarded-append-spec.md
Code-review: context/reviews/2026-11-02-write-preconditions-and-the-guarded-append-code.md
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

The example is a shape, not a prediction; the paths follow today's ruling and the review study may rename them.

## The landing checklist

In order. "Green" means every step passes with nothing skipped by hand.

1. **`scripts/ci.sh` is green** on the working tree as it will be committed. Lint, format, types, the suite at 100 % coverage, the docs fences, the wheel budget. Run it last, after every edit, including the context edits below, because the lint tests in step 9 read `context/`.
2. **The engine legs ran** when the change touched `storage/`, `models/rows.py`, a dialect profile or a migration: the `db_test` skill (Postgres, MariaDB, SQL Server, Oracle). When a leg could not run, the commit body says which and why; the landing notes say the same.
3. **The code review file exists** at its path under `context/reviews/`, written by a reviewer that did not write the change, its `Reviewer:` line filled, its verdict line beginning "Lands". A verdict that does not begin "Lands" stops the checklist here; the fix is a code change and a re-read, not a new verdict.
4. **The landing notes are written** as the last section of the spec: what landed per acceptance criterion, the numbers reproduced (statement counts, row counts, test counts), every deviation from the spec with its reason, what was flagged to Clay, what did not run. The notes cite both review files by relative path. The status line becomes "landed YYYY-MM-DD" and names nothing by number.
5. **The spec moves** from `context/specs/active/<date>-<slug>/` to `context/specs/archive/<date>-<slug>/` with `git mv`, so the move is one rename in the diff and history follows the file.
6. **The architecture page is touched** when the spec's diagram changed what the page draws: the page's status line gets today's date and the commit it is drawn against, the diagram is redrawn, the glossary gains or changes any term. When the page did not change, the landing notes say so in one line.
7. **The docs are updated**: README claims, `docs/` pages and the doc fences that `scripts/ci.sh` runs. `release.md`'s rule that the README ships in the wheel means a README claim is a product claim.
8. **The changelog line is written** in the landing notes (one line under Added, Changed, Fixed or Security, or "None, internal"). See the changelog question below.
9. **`git diff --cached --stat` is read** before the commit (wasi-python's "commit only what you mean"): the staged set is the code, its tests, the docs, the review file, the spec move, the architecture page, and nothing else. A stray earlier `git add` or an unrelated scratch file is unstaged.
10. **Commit**, in the format above, with the three path trailers and the model trailer. The `Spec:` path is the archive path.
11. **Push when asked.** The commit sits on `main` locally until Clay says push. Nothing in the checklist moves `main` on GitHub by itself.

What happens after the push: `test.yml` runs the four-leg matrix if the commit touched code. A red leg on `main` is fixed forward in the next commit the same day; there is no revert-by-default, because there is no second branch to protect.

## What gate holds it without CI on a pull request

The gate is `scripts/ci.sh`, run on the laptop before the commit. CI on push is a second reading of the same gate after `main` has already moved. That order is the cost of no pull requests, and it is a real cost: CI cannot refuse a landing, only report one. The intention accepts the cost and asks the local gate to carry the process rules too, as lint tests. A **lint test** here is a pytest test in `tests/` that reads files under `context/` and asserts their shape; it runs inside `uv run pytest`, so it runs inside `scripts/ci.sh` and inside CI's test job with no new workflow.

What the lint tests can hold, each a cheap file read:

- Every file under `context/intentions/`, `context/specs/*/`, `context/reviews/` is named `YYYY-MM-DD-slug` and the date parses; no file name starts with a bare number.
- Every spec has the header lines (status, date, owner, intention) and the required sections, including the diagram section.
- No active spec holds `[NEEDS CLARIFICATION` or an "Open questions" section with content.
- Every spec under `archive/` has a "Landing notes" section, and that section names two review paths that exist in the tree.
- Every spec under `active/` has no "Landing notes" section and no status line beginning "landed".
- Every review file has a `Reviewer:` line that is not the author's name on the spec, and a verdict line; a code review's verdict begins "Lands" or "Does not land".
- The landed spec's `Spec:` trailer in `git log` points at a path that exists (this one needs `git`, so it reads `git log -1` only; it holds the latest commit, not history).

What the lint tests cannot hold:

- That the reviewer actually did not write the change. A file can claim a name. The trailer check (`git log --format='%(trailers:key=Co-Authored-By)'`) and the `Reviewer:` line are claims; the honest signal is the `Reviewer:` line naming a different session URL, as wasi-python does.
- That the engine legs ran. They need Docker; `scripts/ci.sh` does not start it. The commit body and the landing notes say whether they ran, and the lint test can only hold that the sentence is present.
- That the code review's findings were answered. The lint test holds the verdict word, not the judgment.
- Anything about a context-only commit, in CI. `test.yml`'s path filter skips `context/`. Two fixes, pick one: add `context/**` to the filter and pay a four-leg matrix per docs commit (about three minutes), or add a small `lint.yml` that runs `uv run pytest tests/lint -n 0` on `context/**` changes in under a minute. The second is the recommendation. Without one of them, a spec landed with a bad shape in a docs-only commit is caught only by the next code push.

Where the lint tests live: a new `tests/lint/` package, `test_context_shape.py` first. They touch no `src/` module, so they change no coverage number. They are the "done when 3" of the intention.

## The changelog question

Three choices: news files (towncrier, changesets, wasi-python's `context/changes/`), a hand-written `CHANGELOG.md`, or nothing until a release.

News files solve a problem vfs does not have. They exist so many branches can each add a changelog line without touching one shared file, and so the line is written when the change is fresh. vfs has one branch, one committer, and a per-change document already: the spec's landing notes. wasi-python's news files also carry the claim block its acceptance ledger reads; vfs has no such ledger. A news file here would be a second file saying what the landing notes say.

Nothing is wrong, but weak. Keep a Changelog's point stands: a commit log is a record of steps, and a user wants a record of differences. At 0.1.0 somebody will have to write that record, and writing it from sixty subjects is slow and lossy.

The recommendation is the middle: **the landing notes carry the changelog line, and the release writes the CHANGELOG from them.**

- Every landed spec's landing notes end with one labelled line: `**Changelog:** Added — …` (or Changed, Fixed, Security, or `None — internal`). The lint test holds that the line is present on every archived spec landed after this process starts.
- `CHANGELOG.md` stays, in Keep a Changelog shape. It is written at release, not per commit: the release step lists the specs archived since the last tag (`git log <tag>..HEAD --format='%(trailers:key=Spec,valueonly)'`), copies each `Changelog:` line under its heading, and writes the version section by hand from them. The stale `[Unreleased]` section is deleted when 0.1.0's section is written, as `release.md` already says.
- No `[Unreleased]` section is maintained between releases. The landing notes are the unreleased changelog, and `git log` with the `Spec:` trailer is the index into them.

Why this for a pre-0.1.0 library: no user is reading a changelog yet, so the per-change cost should be one line, not one file. The line lives where the reviewer already reads. The release still gets a human-written record, not a commit log. If vfs ever takes outside contributors on branches, towncrier's folder is the upgrade path and the `Changelog:` lines move into it with no loss.

## Where the standards are stale and what replaces them

`context/standards/commits-and-prs.md` is wrong on its first page and most of the rest:

- Lines 5 to 7: branch from `main`, pull request back, never push `main`. The live rule (CLAUDE.md "Git workflow", the intention) is the opposite: commit to `main` as-is, push when asked.
- Lines 19 to 26: "Short imperative subject"; the house writes `type(scope): words` in the declarative, and has for sixty commits.
- Line 43: "Don't reference issue numbers in the subject … save those for the PR description." There is no PR description; the trailer is the replacement.
- Lines 45 to 55: a four-command pre-push checklist. `scripts/ci.sh` replaced it (commit `d791d18`).
- Lines 61 to 72: the pull-request and review sections. There are no pull requests; the review is a file with its own standard.

Replace it with `context/standards/landing.md`: the commit format (subject, body order, the four trailers), the landing checklist above, the gate, the changelog line. Delete `commits-and-prs.md`; the name itself is stale.

`context/standards/contributing.md` is older still: "Do not treat the repo as greenfield" contradicts CLAUDE.md's first section; it names `VFSResult`, `Entry`, `MSSQLFileSystem` and stories; it points at `commits-and-prs.md`. Its one durable part, the "reusable best practices" (portable baseline, push-down without changing the API, no request-path provisioning, tests at the layer changed, prove equivalence), is the seed of the named-patterns standard the intention asks for. Move those into that standard, rewritten against the live tree, and delete the rest.

`context/standards/release.md`: step 0 says `uvx ruff format` (the standard elsewhere forbids `uvx`); step 1 says "land on main via PR"; step 2 waits on CI; step 4 edits CHANGELOG by hand with no source. Rewrite steps 0 to 5 as: `scripts/ci.sh` green on `main`; the four CI legs green on the last push; the version bump; the CHANGELOG section assembled from the `Changelog:` lines of the specs archived since the last tag; one commit `build: release X.Y.Z`; the release created with `gh release create`. The "Before the first v2 release" facts stay as they are.

CLAUDE.md "Git workflow" stays as written; it is the rule the new standard expands.

## Where the study stood at the time box

All three method steps were done. Not done: a count of subject lengths across the sixty commits (eyeballed, not measured); reading the review study's file-name decision, which the trailer paths above assume; a check of whether `git interpret-trailers` accepts `Spec-review` as a key (it accepts any `Token:` line, INFERRED from the kernel's and git's free use of custom tokens).

## One line

A change lands as one commit to `main` whose subject names the change in words, whose body says the problem and the mechanism, whose trailers point at the spec and its two review files by path, gated by `scripts/ci.sh` with lint tests that hold the shape, and whose landing notes carry the one changelog line the release assembles.
