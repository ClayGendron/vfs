# Glob pattern reference

The complete syntax of vfs glob patterns. Every example on this page has been verified against the live implementation.

Patterns appear in three places, with identical semantics everywhere:

- `glob(pattern, ..., globs_not=(...))` — the pattern selects paths
  across the namespace; exclusion globs reject from the selection.
- `grep(..., globs=(...), globs_not=(...))` — patterns admit or exclude the files whose *content* is searched.
- `ext=` / `ext_not=` — a companion channel that filters by path-derived extension (see [The ext channel](#the-ext-channel)); not a pattern itself, but it composes with one. `glob` also takes `kind=` (`"file"` or `"directory"`), an exact row-kind filter that needs no pattern spelling.

## Quick reference

| Construct | Matches | Example |
|---|---|---|
| `abc` | literal text, case-sensitive | `/READ*` matches `/README` |
| `*` | zero or more characters **within one segment** | `/src/*` matches `/src/a`, not `/src/a/b` |
| `?` | exactly one character, never `/` | `a?c` matches `abc`, not `ac` |
| `[seq]` | one character from a set or range | `/v[0-9]` matches `/v3` |
| `[!seq]` | one character *not* in the set | `/v[!0-9]` matches `/vX` |
| `**` | any number of whole segments, including zero | `/a/**/b` matches `/a/b` and `/a/x/y/b` |
| `{a,b}` | alternation — either alternative, cross-producted | `*.{ts,tsx}` matches `a.ts` and `a.tsx` |
| no `/` in pattern | leaf **names** at any depth | `*.py` matches `/deep/nested/a.py` |
| any `/` in pattern | anchored at the root | `src/*.py` ≡ `/src/*.py` |

## Literal text

Anything that is not a metacharacter matches itself, always case-sensitively:

- `/READ*` matches `/README`; `/readme` does **not** match `/README`.
- `*.PY` does **not** match `/a.py`.

There is no case-folding option for glob patterns. (Content search has one — `grep`'s `case_mode` — but it applies to the text being searched, never to path patterns.)

## `*` — within one segment

`*` matches zero or more characters but never crosses a `/`:

- `/src/*` matches `/src/a` and `/src/.env` — but not `/src/a/b`
  (two segments) and not `/src` itself.
- `/src/a*` matches `/src/a` — zero characters is a valid match.
- `/src/*.py` matches `/src/.py` — the `*` matched nothing and the
  name is the literal `.py`.

A pattern that is *only* name-shaped (no `/` anywhere) matches leaf names at any depth — see [Anchoring](#anchoring).

## `?` — exactly one character

`?` matches exactly one character and never matches `/`:

- `a?c` matches `abc`; it does not match `ac` (too few) or `abbc` (too many).
- `?env` matches `.env` — a leading dot is an ordinary character.

## `[seq]` — character classes

One character from a set, a range, or a mix:

- `/v[0-9]` matches `/v3`, not `/vX`.
- `/v[a-cx]` matches `/vb` (range `a-c` plus the single character `x`).
- `/v[!0-9]` negates: matches `/vX`, not `/v3`. (`[^0-9]` also works; prefer `[!...]`, the glob spelling.)

Class edge cases, all verified:

- A `]` as the **first** character of a class is literal: `/f[]]`
  matches `/f]`.
- `[[]` matches a literal `[`.
- An unmatched `[` is treated as a literal character: `/a[x` matches
  the path `/a[x`.

Character classes are also the escape mechanism — see [Matching literal metacharacters](#matching-literal-metacharacters).

## `**` — any number of segments

`**` must stand alone as a whole path component. It matches any number of segments, **including zero**:

- Bare `**` matches every path in the namespace, the root included.
- Leading `**/x.py` matches `/x.py` and `/a/b/x.py` — any depth.
- Middle `/a/**/b` matches `/a/b` (zero segments), `/a/x/b`, `/a/x/y/b`.
- Trailing `/src/**` matches everything strictly *inside* `/src` — `/src/a`, `/src/a/b/c`, `/src/.hidden/x` — but **not** `/src` itself.

Adjacent `**` components are collapsed before matching: `/a/**/**/b` behaves exactly like `/a/**/b`.

A `**` glued to other characters inside a component (`a**b`, `***`, `**a`) is **refused**, not silently reinterpreted — see [Refused patterns](#refused-patterns).

## `{a,b}` — alternation

`{a,b}` matches either alternative; each alternative is arbitrary pattern text (wildcards, classes, and `/` included), and multiple groups take the cross-product:

- `*.{ts,tsx}` matches `a.ts` and `a.tsx` at any depth.
- `{src,docs}/**/*.md` anchors both alternatives: `/src/**/*.md` or `/docs/**/*.md`.
- `{a,b}/{c,d}` expands to four patterns.
- An empty alternative is legal: `x{a,}` matches `xa` and `x`. A single-alternative group `{a}` is just `a`.
- Mixed anchoring is legal: `{src/a,b}` has one anchored alternative and one floating one, each behaving by its own [anchoring rule](#anchoring).

Two bounds, both refused loudly rather than silently mangled:

- **Nesting is not supported**: `{a,{b,c}}` is refused.
- **Expansion is capped at 64 distinct patterns** per call — a wider alternation refuses with a message naming the cap.

Braces are metacharacters everywhere outside a character class: malformed braces (unclosed `{`, bare `}`, empty `{}`) are refused, and a literal brace is matched with class notation (`[{]` and `[}]` — see [Matching literal metacharacters](#matching-literal-metacharacters)).

## Anchoring

Where a pattern applies is decided by one rule: **any `/` anchors the pattern at the root; a slash-free pattern floats.**

| Pattern | Behavior | Verified examples |
|---|---|---|
| `*.py` (no slash) | matches leaf **names** at any depth | matches `/a.py` and `/deep/nested/a.py`; not `/deep/a.py.txt` |
| `src/*.py` | anchored — identical to `/src/*.py` | matches `/src/a.py`; not `/x/src/a.py` |
| `/src/*.py` | anchored (leading `/` optional but welcome) | matches `/src/a.py` |
| `*/x.py` | anchored with depth pinned to one | matches `/a/x.py`; not `/x.py` (too shallow) or `/a/b/x.py` (too deep) |

To search a floating name **under a specific place**, either scope the call (`paths=("/src",)` with pattern `*.py`) or spell the float: `/src/**/*.py`.

## Dotfiles

Dotfiles are ordinary rows. There is no hidden-file rule anywhere in the language:

- `*` matches `/.env`; `/src/*` matches `/src/.env`.
- `?env` matches `.env`; `*.py` matches `/.py`.
- `/src/**` descends through `/src/.hidden/x`.

If you want dotfiles excluded, say so in the pattern (e.g. `[!.]*` for names not starting with a dot).

## Refused patterns

Three malformed families are refused loudly (the call classifies as invalid and touches no rows) instead of matching something you didn't mean:

| Pattern | Refusal |
|---|---|
| `a**b`, `***`, `**a`, `a**` | `'**' inside a component — use '**' as a whole path segment` |
| `/data/` (trailing `/`), `//x`, `x//y`, `/`, `` (empty) | `empty component — every '/' must separate non-empty segments` |
| `{a,b` / `a}b` / `x{}y` / `{a,{b,c}}` | unclosed `{` / unmatched `}` / empty group / nested braces |

All would otherwise be silent false friends: other glob dialects quietly downgrade an in-component `**` to `*`, hiding a typo'd recursion; a trailing-slash pattern can never match any stored path; and a half-typed brace group would silently match a literal brace-named file. Brace patterns are gated twice — the raw text, then every expansion arm: `x/{a,}` refuses naming the empty-component arm `x/` it would have manufactured.

## Matching literal metacharacters

There is no backslash escaping — a `\` in a pattern is a literal character (`/a\*.py` matches the path `/a\x.py`, where the name really contains a backslash). Escape metacharacters with **class notation**:

| To match a literal | Write | Verified |
|---|---|---|
| `*` | `[*]` | `/f[*]` matches `/f*`, not `/fx` |
| `?` | `[?]` | `/f[?]` matches `/f?` |
| `[` | `[[]` | `/f[[]` matches `/f[` |
| `{` / `}` | `[{]` / `[}]` | `/[{]a,b[}].txt` matches `/{a,b}.txt` |

Constructs from other glob dialects that are **plain literal text** here:

- `!` has no negating power inside a pattern: `/a!b` matches `/a!b`. Exclusion is a separate channel (`globs_not=` on both `glob` and `grep`).

## The ext channel

`ext=` and `ext_not=` (both verbs carry both) filter by the **path-derived** extension — the text after the last dot of the leaf name, never a stored column. They combine with the pattern as an AND. Entries are normalized: a leading dot is dropped and case is folded, so `ext=("py", ".TXT")` accepts both `/a.py` and `/b.txt`:

- `ext=("py", ".TXT")` with pattern `*`: matches `/a.py` and `/b.txt`; rejects `/c.rs` and `/noext` (an extensionless name never passes a non-empty ext filter).
- `ext_not=(".TXT",)` drops `.txt` rows; an extensionless row is never `ext_not`'s business and passes.

## Differences from ripgrep globs at a glance

For readers arriving from `rg -g`:

| Feature | ripgrep (`-g`) | vfs |
|---|---|---|
| `{a,b}` alternation | supported (no nesting) | supported (no nesting; 64-arm cap) |
| `\` escapes | supported (Unix) | literal character — use `[*]`-style classes |
| `!pattern` exclusion | supported as prefix | separate `globs_not=` channel on both verbs |
| case-insensitive flag | `--iglob` | not available |
| in-component `**` (`a**b`) | error | refused with a message |
| hidden files | hidden by default (ignore rules) | always ordinary rows |
| anchoring | gitignore rule (slash at start/middle anchors) | same rule — any slash anchors (trailing slash is refused, so the rules agree everywhere both accept) |

See [The glob language, explained](../explanation/glob-language.md) for why these choices were made.
