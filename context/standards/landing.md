# Landing: how a change reaches main

This page says how a built change becomes one commit on `main`. It is the last stage of [the development process](../specifications/active/2026-10-29-the-development-process.md): the spec was reviewed, the tests were written first, the code was reviewed, and now it lands. It expands the "Git workflow" section of [CLAUDE.md](../../CLAUDE.md) and never contradicts it: commit to the current branch, `main` included; push only when Clay asks; no worktrees; no restore-shaped command on a file that carries uncommitted work. The two reviews it names are described in [the reviews README](../reviews/README.md); the coding patterns the diff is held to are in [how we code](how-we-code.md); the release that follows a run of landings is [release.md](release.md).

Terms. A **landing** is the commit that puts a change on `main`. A **trailer** is a `Key: value` line at the end of a commit message that git reads by key (`git log --format='%(trailers:key=Spec,valueonly)'`). The **landing notes** are the spec's own section of that name, filled in at the landing. The **standing verdict** of a review is the last line of its Verdict section that begins with a date, or the section's first line when no line does.

## The commit

One commit by default. It carries the code, its tests, the docs it changes, both review files, the landing notes, the `git mv` of the spec to `context/specifications/archive/`, and the architecture page. One `git show` is then the whole record, and `git bisect` lands on a spec, not on a slice of one.

### The subject

`type(scope): words`, at most 72 characters. The type is one of `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `ci`, `build`. The scope is the top-level module or folder the change touches (`storage`, `base`, `results`, `context`, `standards`); it is left out when the change spans several. The words name the change in plain language, lower-case after the colon, no full stop. The subject carries no number and no `(spec …)` suffix: the spec is a trailer, not a subject. An em dash is allowed; the half after the dash is the first thing to cut when the cap bites.

### The body

Wrapped at 72 columns. Paragraphs in this order, each present only when it has content:

1. The problem, or what was missing, in the present tense. One to three sentences.
2. What the change does and by what mechanism.
3. What was decided at the build and flagged to Clay.
4. "Also carried:" what rode along (a fresh oracle, a conformance family, a redrawn page).
5. What did not run, said plainly ("The engine legs did not run; no Docker on this machine.").

The body never restates the diff and never names a spec by number. It may name the spec by path in prose when that helps a sentence; the trailer carries the path in every case.

### The trailers

Four, in this order, each a line git reads by key:

- `Spec:` the spec's path after this commit, under `context/specifications/archive/`, because the commit moves it there.
- `Spec-review:` the spec review file under `context/reviews/`.
- `Code-review:` the code review file under `context/reviews/`, whose standing verdict begins "Lands".
- `Co-Authored-By:` the model that wrote the change, not the session that briefed it. A sub-agent's commit names the sub-agent's model.

A commit that lands no spec (a docs fix, a CI change) carries no `Spec:` trailer and no review trailers. A commit that lands a spec carries all four.

### One example

The example is a shape, not a prediction; the paths follow the naming rules and nothing else about it is a fact.

```
feat(storage): the guarded append and the write preconditions

Twenty concurrent read-append-write loops each kept one line and every
one reported success: a write has no way to say "only if the row is
still at the revision I read". The write path now takes three
preconditions, if_revision, if_absent and append, judged inside the row
lock in the pinned statement order, and answers precondition_failed as
a Result row, never an exception. append is a server-side concatenation
in one statement, so a 10,000-file batch issues no extra round trip.

Decided at the build: a precondition on a tombstoned row is judged as
on an absent row; flagged to Clay in the landing notes.

Also carried: the write-path conformance family gains the precondition
rows on every dialect; the write-path architecture page is redrawn
with the precondition step.

The engine legs ran on Postgres and SQL Server; MariaDB and Oracle did
not run on this machine.

Spec: context/specifications/archive/2026-11-03-the-guarded-append.md
Spec-review: context/reviews/2026-11-03-the-guarded-append-spec-review.md
Code-review: context/reviews/2026-11-06-the-guarded-append-code-review.md
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

## The landing checklist

In order. "Green" means every step passes with nothing skipped by hand.

1. **`scripts/ci.sh` is green** on the tree as it will be committed: lint, format, types, the suite at 100 % coverage with `tests/lint` collected, the docs fences, the wheel budget. Run it last, after every edit below, because the lint tests read `context/`.
2. **The engine legs ran** when the change touched `storage/backends/database/`, `models/rows.py`, a dialect profile, a builder or a loop over batch input: the [db_test](../../.claude/skills/db_test/SKILL.md) cycle over Postgres, MariaDB, SQL Server and Oracle. A leg that could not run is named in the commit body and in the landing notes, never reported as clean.
3. **The code review file is present** at `context/reviews/YYYY-MM-DD-<spec-slug>-code-review.md`, written by a reviewer who did not write the change, with a standing verdict beginning "Lands"; the spec review file is present beside it. A standing verdict that does not begin "Lands" stops the checklist here. What follows is a code fix and the reviewer's re-read, never a verdict written by the author.
4. **The landing notes are written** in the spec's Landing notes section: what landed per acceptance criterion, the numbers reproduced (statement counts, row counts, test counts), each deviation from the spec with its reason, what was flagged to Clay, what did not run. They link both review files by relative path. They end with one line `**Changelog:** Added — …` (or Changed, Fixed, Security, or `**Changelog:** None — internal`); the release assembles `CHANGELOG.md` from these lines.
5. **The spec moves** with `git mv context/specifications/active/<name>.md context/specifications/archive/<name>.md`, so the move is one rename in the diff and history follows the file. Links to the active path keep resolving: the lint counts a link to `specifications/active/<name>` as resolved when `specifications/archive/<name>` exists.
6. **The architecture page is touched** when the spec's diagram changed what a page under [context/architecture/](../architecture/README.md) draws: the diagram redrawn, the page dated against this commit, the glossary updated. When no page changed, the landing notes say "Architecture pages: unchanged." in one line.
7. **The docs are updated**: README claims, the `docs/` pages, and the doc fences `scripts/ci.sh` runs. The README ships in the wheel, so a README claim is a product claim.
8. **`git diff --cached --stat` is read** before the commit. The staged set is the code, its tests, the docs, the two review files, the spec move, the landing notes and the architecture page, and nothing else.
9. **One landing commit** in the format above, with the three path trailers and the model trailer. Slices are allowed only when each is green on its own; then the last slice is the landing commit, carries the trailers, the review files and the context moves, and the code review reads the whole set.
10. **Push when Clay asks.** The commit sits on `main` locally until then; nothing in this checklist moves `main` on GitHub by itself. After the push, `test.yml` runs the four-leg matrix on a code change and `lint.yml` runs the lint package on a context change; a red leg on `main` is fixed forward in the next commit the same day.

## The review file never lands after the code

A code review signs a specific tree. The review's opening paragraph names what it read: the local commits `<base>..<tip>`, or the working tree over `HEAD` at a named commit. The review file rides in the landing commit that carries that code, or, with slices, in the last slice. It never gets a commit of its own after the code: a code commit on `main` with no review in the tree is the window the process forbids. A code change made after the review's tip is unreviewed; it needs the reviewer's re-read and a new dated signature line before it lands. A change that touches only `context/` after the review leaves the signature standing.

## Commit only what you mean

Read `git diff --cached --stat` before every commit. A `git mv` or an earlier `git add` stays staged and rides along with whatever comes next; a scratch file or an experiment output is never part of a landing. A commit on `main` is green on its own, so `scripts/ci.sh` runs on the tree that will be committed, not on the tree as it was an hour ago. Never run `git checkout --`, `git restore` or `git stash` on a file that carries uncommitted work without first copying it to the session scratchpad, as CLAUDE.md requires.

## The security-audit skill

The code review's Security section and the release's full audit use Cloudflare's security-audit skill, installed unchanged at [.claude/skills/security-audit/](../../.claude/skills/security-audit/SKILL.md). Licence: MIT, copyright 2025-2026 Cloudflare, Inc.; source `cloudflare/security-audit-skill`. Installed with `npx skills add https://github.com/cloudflare/security-audit-skill --skill security-audit -a claude-code` at the repository root, which also writes [skills-lock.json](../../skills-lock.json). It is pinned twice: by the lock file's `computedHash`, which `npx skills check` reads at a release, and by the lint's own SHA-256 over the folder in [tests/lint/test_code_shape.py](../../tests/lint/test_code_shape.py). A change to the folder fails the gate; an upstream update is taken with `npx skills update` and a new constant in the test, in a commit of its own.

## One line

A change lands as one green commit to `main` whose subject names it in words, whose body says the problem and the mechanism, whose trailers link the archived spec and its two reviews, and whose staged set was read before it was committed.
