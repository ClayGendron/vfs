# Fan-out channel typing — how the field carries a per-target rewritten predicate beside pass-through options

- **Date:** 2026-08-19
- **Provenance:** commissioned during the glob/grep teaching walkthrough
  (Stop 1, the router's `_route_fanout`), where Clay flagged the
  `patterns=arms` / `not_arms=globs_not` smuggling through the
  `**kwargs` bag as incoherent naming and asked for prior art before a
  rename. Four read-only studies of the reference checkouts, run
  2026-08-19: ripgrep (`crates/ignore`, `crates/core/flags`), zoekt
  (`search/shards.go`, `index/eval.go`, `query/query.go`), fsspec +
  SQLAlchemy (`fsspec/spec.py`, `dirfs.py`; `engine/base.py`,
  `doc/build/changelog/migration_20.rst`), opendal + pyfilesystem2
  (`core/core/src/raw/ops.rs`, `layers/*`; `fs/mountfs.py`,
  `fs/base.py`, `fs/walk.py`). Studies cite and describe; no code was
  copied.
- **Headline:** every studied system that fans one request out to many
  targets **types the one argument it rewrites per target and leaves
  the rest a flat, read-only bag it never touches**. The two
  `**kwargs`-passthrough systems (fsspec, pyfilesystem2's `MountFS`)
  carry exactly vfs's smell — `kwargs.pop("detail")` before a call
  that hardcodes `detail=True` — and a git trail of collision and
  drift bugs from it. The rename is therefore not cosmetic: the router
  should carry glob's/grep's pattern channels as one named, typed
  value (`admissions`, `exclusions`) and forward `**kwargs` verbatim.

## The problem in the live tree

`VirtualFileSystem._route_fanout` (`src/vfs/base.py`) is the generic
fan-out for every namespace-wide verb and forwards `**kwargs` to
storage. Glob and grep cannot forward verbatim — their pattern
channels are composed under each scope root and residuated per mount —
so they smuggle the channels into the bag under ad-hoc keys and
`_route_fanout` fishes them out:

| verb | put in kwargs | recovered by | crosses the seam as |
|---|---|---|---|
| glob | `patterns=arms` | `kwargs.get("patterns")`, stripped from `rest` | `patterns=<residuals>` |
| glob | `not_arms=globs_not` | `kwargs.get("not_arms")`, stripped | `globs_not=<composed>` |
| grep | `globs=`, `globs_not=` | `.get()` both, both stripped | same names, rewritten |

Three incoherences: `patterns` names two different objects (caller
arms in the bag, the residuated storage batch at the seam);
`not_arms` is renamed purely to dodge a duplicate-keyword collision
while `patterns` dodges the same collision by stripping; and
`op == "glob" and isinstance(patterns, tuple)` sniffs a type to
recover a fact the caller knew.

## Findings per system

### ripgrep — one named type for the include/exclude pair, built once

`crates/ignore/src/overrides.rs:47` — `pub struct Override(Gitignore);`
holds both channels; polarity lives in the glob token (`!`) and the
matcher's verdict is inverted once (`overrides.rs:97-110`). The
invariant "an include glob exists ⇒ unlisted files are excluded" is in
the type, not re-derived by callers. `HiArgs` collapses the two loose
CLI `Vec<String>`s (`lowargs.rs:59,64`) into one `Override` exactly
once (`hiargs.rs:1246-1267`) and stores it under the *role* name
`globs` (`hiargs.rs:57`); `WalkBuilder::overrides` (`walk.rs:833`)
forwards it, and every directory matcher holds `Arc<Override>`
(`dir.rs:126`) — the same policy reaches every target structurally.
The verdict is a tri-state `Match::{None, Ignore, Whitelist}`
(`lib.rs:416-425`) carrying its evidence.

### zoekt — typed predicate with algebra; flat options never rewritten

The same `(ctx, q query.Q, opts *SearchOptions)` signature repeats at
the API (`api.go:911`), the shard fan-out (`search/shards.go:536`), the
per-shard worker (`:952`), and the leaf (`index/eval.go:138`). `q` is
a typed AST with `Map`/`Simplify`/`Const`; `opts` is a flat struct
passed by pointer and only ever read (the leaf copies before
`SetDefaults`, `eval.go:141`). Per-target rewriting is a type-switch
inside `query.Map`, non-mutating (`slices.Clone` before assignment,
`shards.go:504`), conservative (returns the original query when it
cannot prove the rewrite, `:490-500`), and the fan-out **co-returns
the narrowed target set and the narrowed predicate** —
`shards, q = selectRepoSet(shards, q)` (`shards.go:674-696`) — so the
two cannot drift. Naming: the per-target predicate is still `q`; the
distinction lives in function names (`selectRepoSet`, `simplify`).

### fsspec — the kwargs bag, and its bug trail

`spec.py:613-614` pops `detail`/`withdirs` because `:628-630`
hardcodes them in `self.find(..., detail=True, **kwargs)` — the exact
shape of vfs's `rest = {k: v … if key not in (…)}`. The idiom must be
repeated at every forwarding site and is invisible in the signature;
`spec.py:1215` (`expand_path`) forgot it and raises on
`detail=True`. `DirFileSystem` (`dirfs.py:285-291`) must `.get`
(not `.pop`) `detail` because the wrapper needs it *and* the wrappee
does. History: `cfb7a25` (async `_glob` dropped the caller's
`withdirs`), `#1911`, `#1242`, `#1422`, `#1316`, `#1391` — each a bag
not forwarded or forwarded to something that chokes.

### SQLAlchemy 2.0 — the bag deleted on purpose

`migration_20.rst:949-953`: `*args`/`**kwargs` removed from `execute`
"to remove the complexity of guessing what kind of arguments were
passed … as well as to make room for other options". Result
(`engine/base.py:1404-1410`): `execute(statement, parameters, *,
execution_options)` — data and behaviour as distinct keyword-only
channels; options are an immutable mapping layered by `merge_with`/
`union` (`base.py:1474,1626,1783`), never `pop`ped. Known keys are a
`TypedDict` the ORM extends by subclassing (`orm/_typing.py:86-97`).

### opendal / pyfilesystem2 — typed per-op structs; keep `path` outside

opendal's accessor signature is `(ctx, path: &str, args: OpList)`
(`raw/accessor.rs:197`): `path` is deliberately *not* a field of the
op struct, so a rebasing layer touches one positional arg and forwards
`args` untouched — pass-through layers are one line per op
(`layers/complete.rs:82-124`). pyfilesystem2's `MountFS` restates
every signature and forwards by hand (~25 bodies); `openbin`
(`mountfs.py:163-168`) hardcodes `buffering=-1`, dropping the
caller's value — the hand-plumbing bug class. Its include/exclude
pair is named two ways in one library (`files`/`exclude_files` in
`base.py:539`, `filter`/`exclude` in `walk.py:53-64`).

## What transfers to vfs

1. **Type the rewritten argument; leave the bag flat and untouched.**
   The router rewrites exactly one thing per entry — the pattern
   channels. Give them one named value and forward `**kwargs`
   verbatim, with no strip and no sniff (zoekt, ripgrep, SQLAlchemy).
2. **One vocabulary for the pair, already in the tree:**
   `admissions` / `exclusions` (`_grep_admissions`,
   `database/grep.py`). Not `patterns`/`not_arms`/`globs` in three
   spellings (pyfilesystem2's two-vocabulary trap).
3. **`paths=` stays a separate argument** (opendal's `path` outside
   the op struct) — already true in vfs and worth keeping explicit.
4. **The seam names (`patterns=`, `globs=`, `globs_not=`) appear only
   where the storage call is built**, so "patterns" means the
   residuated storage batch and nothing else.
5. **Build the typed value once at the boundary** — in `glob()` /
   `grep()` right after brace expansion (ripgrep's `HiArgs`).

Refinement at landing (Clay, 2026-08-19): the typed value widened
from the two rewritten glob channels to the **four-channel filter
law** the pattern layer already states (`passes_filters` /
`filter_candidates`: admissions, exclusions, ext, ext_not) — ext is a
path-derived fact, the same subject as the globs, and the probe gate
had been reconstructing that law from bag peeks. The two ext channels
are forwarded verbatim; only the glob channels are rewritten. `kind`
and `columns` stay in the bag (row fact and projection, glob-only).
Landed as `_PathFilters` in `src/vfs/base.py`.

Not adopted: zoekt's co-return shape (`_glob_dispatches` already
returns the dispatch triples as one unit) and ripgrep's polarity-in-
token (`!glob`) — vfs's two-channel protocol is the wire contract and
is not changing here.

## Addendum (same day): who owns pattern admission vs the channel label

A second question from the same walkthrough — `_expanded_arms(op, label,
pattern)` took `op` only to stamp its refusal — prompted three more
read-only studies (ripgrep's `globset`/`ignore`; zoekt's `query/parse.go`,
codesearch's trigram planner, SQLAlchemy's `exc.py`; nushell/elvish/
PowerShell glob and brace handling).

- **globset/ignore**: the library owns *identity* and *diagnosis* as
  separate fields (`Error{glob, kind}`, `globset/src/lib.rs:157-163`),
  validate+compile is one `GlobBuilder::build` call, and the caller
  (`ignore`) adds *provenance* (file, line) as wrapper variants
  (`ignore/src/lib.rs:263-284`) — it deliberately re-prefixes with
  `err.kind()` so the user's *original* glob is named after a rewrite
  (`gitignore.rs:526-536`). The library never learns that `.gitignore`
  files exist. Nesting is supported and there is no expansion cap,
  because alternation lowers to a regex `|`, never a textual product
  (`glob.rs:743-759`).
- **zoekt**: `Parse` hardcodes a `"query: "` prefix (`parse.go:122`)
  that is wrong at the JSON API where the field is `Q` — the library
  owning the prefix is exactly what blocked the caller from owning it.
  Errors are `fmt.Errorf` strings nobody can classify.
- **codesearch**: `maxExact = 7`, `maxSet = 20` are library-owned named
  constants with written rationale (`index/regexp.go:359-378`), and the
  planner `RegexpQuery(*syntax.Regexp)` cannot fail because parsing
  happened at the type boundary upstream.
- **SQLAlchemy**: each layer appends its own context (`StatementError
  .statement/.params/.orig`, `Session.add_detail`) without the lower
  layer knowing the caller.
- **Shells**: none caps expansion width (nushell's dc_glob never
  materializes the product; elvish expands at the language level, not in
  the glob library); structured errors survive only until the first
  `to_string()` — nushell flattens `bracoxide`'s rich enum into a
  constant title four times, copy-pasted (`nu-engine/src/glob_from.rs:
  128,147,158,167`); PowerShell validates lazily at first match, in
  whichever backend runs first.

**What transferred.** `expand_pattern` became the one admission call
(defect gate, brace expansion, arm cap) raising `PatternError` with
identity + diagnosis and no label; `expand_channel(channel, patterns)`
prefixes the channel's one label — `GLOB_CHANNEL_LABELS` already lived
in the pattern layer, so only the channel *choice* crosses in; the verb
stamps `op` once, as a literal, at the `except`. The router's
`_expanded_arms`/`_expanded_channel` were deleted. The storage seam
(`glob_rows`, `grep_rows`) calls the same function and uses the arms,
so a brace pattern arriving unexpanded now alternates — previously it
passed `glob_defect` and then matched *literally* in `compile_filter`
(the PowerShell shape: admissibility judged in one place, matching in
another). The cap value stays in the pattern layer as a declared
constant (codesearch's posture; ADR 037 §3 records the number).
`PatternError` moved to `glob.py`, the root of the package's one-way
dependency, and serves both languages.
