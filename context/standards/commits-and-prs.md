# Commits and pull requests

## Branching

- Branch from `main`. PR back into `main`.
- Branch names are short and descriptive. If the work has a story (`NNN-slug`), the branch name matches the story slug.
- Don't push directly to `main` — even small changes go through a PR for the CI gate.

## One commit per logical change

- Each commit leaves the repo in a fully working state: lint clean, format clean, types clean, tests passing.
- No `WIP` commits on shared branches. Squash locally before pushing if needed.
- Prefer creating a new commit over `--amend` once a commit has been pushed. Amending pushed history forces collaborators to recover.

## Commit messages

Concise and descriptive. Focus on the **why**, not the **what** (the diff already shows the what).

Format:

```
Short imperative subject — under 70 chars

Optional body explaining the why, the constraint, or the prior incident
this fixes. Wrap at 72.
```

Good:

```
Fix version reconstruction when snapshot is at boundary

The snapshot interval check was off-by-one, causing reconstruction
to miss the boundary snapshot and fall back to a stale one.
```

Bad:

```
Updated database.py
```

Don't reference issue numbers in the subject unless the issue is the entire context. Save those for the PR description.

## Pre-push checklist

In order:

1. `uvx ruff format src/ tests/`
2. `uvx ruff check src/ tests/`
3. `uvx ty check src/`
4. `uv run pytest`
5. `git push`

CI runs `ruff format --check`. Skipping step 1 has cost real CI time and forced fixup commits — don't.

## Pull requests

- Title: imperative, under 70 chars, mirrors the leading commit subject.
- Description: a `## Summary` (1–3 bullets) and a `## Test plan` (what was checked).
- Link to the relevant story (`context/stories/NNN-slug/`) or decision (`context/decisions/NNN-slug.md`) if one exists.
- Don't open PRs you wouldn't review yourself. Read the diff before assigning a reviewer.

## Review

- Sub-agent review with real integration tests is the standard for non-trivial changes — not a self-approval.
- Reviewer's job: check the why is sound, the tests cover the change, the architectural patterns hold, and the public surface still composes.
- Architectural drift goes back for revision. Style nits are inline suggestions; don't block on them.
