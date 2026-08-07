# The glob language, explained

The [reference](../reference/glob-patterns.md) says what patterns match. This page says why the language is shaped the way it is, where it sits in the field of glob dialects, and where its deliberate edges are.

## One language, one authority

The same pattern can arrive at very different machinery: a SQL query filtering rows, an index narrowing grep candidates, or an in-memory filter over results you already hold. Each of those surfaces can *narrow* cheaply in its own dialect — SQL `LIKE`, trigram postings, a list comprehension — but every cheap filter is only a superset approximation. `LIKE`'s `%` crosses `/` while glob's `*` must not; an index can say "these files contain these trigrams" but not "this regex matches."

So vfs splits the roles. Prefilters everywhere are allowed only to shrink the candidate set without losing a true match; **what a pattern actually matches is decided by exactly one compiled authority**, shared by every surface. That is why a pattern behaves identically whether it runs against storage, an index tier, or chained results: there is only one definition of matching to agree with.

## The lineage: gitignore anchoring, agent-familiar wildcards

The wildcard core (`*` within a segment, `?`, `[seq]`, whole-component `**`) is the segment-aware glob that every developer tool — and every coding agent — already speaks. It is compiled through Python's standard `glob.translate`, so the semantics are the stdlib's, not a homegrown dialect.

The anchoring rule is taken from gitignore, the most widely-internalized convention in the field: **a pattern containing a slash is anchored; a slash-free pattern floats.** gitignore states it as "a separator at the beginning or middle anchors"; vfs states it as "any slash anchors." These agree everywhere both languages accept, because the one case where they would differ — a slash *only at the end*, like `foo/` — is refused by vfs outright (see below). gitignore's trailing slash means "directories only"; vfs deliberately keeps that fact out of pattern text — it is the `kind=` parameter on `glob`, a column fact selected by a parameter rather than a spelling convention.

Floating patterns match **leaf names** (`*.py` finds every Python file at any depth), and scoping a floating pattern under a root composes it spatially: scope `/src` + pattern `*.py` becomes `/src/**/*.py` — the gitignore float, spelled out. Since `**` spans zero segments, that composition still matches direct children.

## Loud refusal beats a false friend

Glob dialects disagree about malformed `**`:

- gitignore silently treats `a**b` as two ordinary stars.
- Python's stdlib silently collapses in-component `**` to `*`.
- ripgrep's globset makes it a hard error.

vfs sides with ripgrep, with a message: `a**b` and `***` are refused, because the silent readings hide a typo'd recursion — the user who wrote `src**test` almost certainly meant something with real `**` in it, and a quiet `*` would return plausible-but-wrong results. The same policy covers empty components (`/data/`, `//x`): no stored path can ever satisfy them, so matching nothing silently would be indistinguishable from "your data isn't there." A search language for agents should fail loudly at the pattern, not shrug at the results.

## Dotfiles are ordinary rows

Shells hide dotfiles; ripgrep skips hidden files by default. Both are *presentation* conventions layered on top of matching — ripgrep's hiding comes from its ignore machinery, not from its glob semantics. vfs is a database-backed namespace, not a Unix home directory: a row either matches the pattern or it doesn't, and no row is invisible. `*` matches `/.env`. Callers who want dotfiles excluded can say so in the pattern (`[!.]*`).

## Extensions ride a separate channel

`ext=("py",)` could almost be written into the pattern (`*.py`), so why a channel? Because the two compose: `ext` is a normalized, path-derived fact (`".TXT"` ≡ `"txt"`) that ANDs with *any* pattern without rewriting it, and it gives storage an exact, indexable prefilter where a pattern tail would need parsing. The extension is always derived from the path text, never trusted from a stored column — so it can never disagree with the name you see.

## How patterns meet mounts

A pattern is the *whole* query: scope roots compose into pattern text (`/src` + `*.py` → `/src/**/*.py`), and at each mount seam the router computes the pattern's **residual** — the part left over after the mount path consumes its share — and sends each backend only its own local remainder. Backends never receive scope as paths, only as pattern text. The executable walkthrough of this algebra, with the frontier printed step by step, lives in `examples/glob_residuation.ipynb`.

## The field at a glance

| Feature | vfs | ripgrep `-g` | gitignore | bash glob | Python `glob` |
|---|---|---|---|---|---|
| `*` crosses `/` | no | no | no | no | no |
| whole-component `**` | yes (zero+ segments) | yes | yes | with `globstar` | with `recursive=True` |
| in-component `**` | **refused** | error | silently two stars | treated as `*`* | silently `*` |
| `[seq]` / `[!seq]` | yes | yes | yes | yes (`[!]`/`[^]`) | yes |
| `{a,b}` alternation | yes (no nesting, 64-arm cap) | yes (no nesting) | no | yes (brace expansion) | no |
| `\` escaping | no — class notation | yes (Unix) | yes | yes | no — class notation |
| `!` negation | `globs_not=` channel | prefix `!` | prefix `!` | `extglob` | no |
| case-insensitive option | no | `--iglob` | no | `nocaseglob` | no |
| hidden files matched | always | via ignore rules | n/a | `dotglob` | `include_hidden` |
| anchoring | any slash anchors | gitignore rule | start/middle slash anchors | cwd-relative | cwd-relative |

\* bash without `globstar`.

## Where the language deliberately stops

The 2026-08 field-parity pass closed the gaps worth closing — brace alternation `{a,b}`, the exclusion channels on `glob` (`globs_not=`, `ext_not=`), and the `kind=` filter. What remains absent is absent on purpose or deliberately deferred:

1. **Case-insensitive matching** (`--iglob` equivalent) — *deferred, pending research*. It cuts semantics, not spelling: the SQL prefilters would need collation-aware case-folded variants per engine, and residuation would need a case posture at mount seams.
2. **Multiple patterns per call** — *declined*. One pattern is the verb's subject; braces express the common unions, and multiple calls (or chaining) compose the rest. The storage seam's pattern batches are dispatch plumbing, not a public contract.
3. **Backslash escapes** — *declined*. Class notation already escapes every metacharacter (now including `[{]`), and backslash-escaping would create ambiguity with names that really contain backslashes.
4. **POSIX classes** (`[[:alpha:]]`) — *declined*. No engine support in the stdlib compiler, and ranges cover the cases.
5. **Numeric ranges** (`{1..3}`) — *deferred*. bash-only in the field; `[1-3]` covers the single-digit cases.
6. **Trailing-slash directory matching** (gitignore's `foo/`) — *closed another way*: the `kind="directory"` parameter, keeping pattern text pure path algebra.
