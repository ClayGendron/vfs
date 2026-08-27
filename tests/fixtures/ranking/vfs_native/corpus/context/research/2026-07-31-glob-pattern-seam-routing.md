# Glob patterns at the mount seam — prior art and the residuation spike

- **Status:** complete — feeds the pattern-seam ADR (namespace vs
  entry-local patterns) and spec 091
- **Date:** 2026-07-31
- **Owner:** Clay Gendron (research executed in-session with Claude)
- **Method:** five read-only prior-art studies over reference clones
  (fsspec, pyfilesystem2, ripgrep's globset/ignore, zoekt, codesearch,
  plan9/plan9port, linux, libfuse, git, language-server-protocol,
  postgres; Bazel via public docs) plus an executed property spike,
  `studies/2026-07-31-glob-residuation/verify_residuation.py`. Studies
  cite and describe; no code was copied.

## The question

vfs routes scope anchors across the mount seam (rebased to entry
coordinates) but passes glob patterns verbatim, so each mount matches
the pattern against entry-relative rows. Executed repro (mount at
`/data` holding `a.txt`): unscoped `glob("/data/*.txt")` returns empty
success — the mount's rows never start with `/data/`. No ADR, spec, or
router test pins the seam behavior; the verb docstring ("match against
the namespace") contradicts it. The fork: **(a)** entry-local patterns
(ratify + refuse), **(b)** namespace patterns (router computes each
mount's residual pattern and routes on it), **(c)** stage a then b.
This memo asks: who else pushes a pattern across a namespace boundary,
and how?

## Headline findings

1. **No studied system transmits a pattern across a mount, server, or
   repository boundary.** The field splits into caller-side
   enumeration (A), per-container scoped patterns (B), and pattern
   analysis that routes or prunes (C) — but C is everywhere applied
   inside one container or one index, never across a mount table.
   Residual routing at the mount seam is a genuine gap in the field,
   with all of its ingredients separately well-precedented.
2. **git documents residuation as its missing primitive.** At a
   submodule boundary git keeps one superproject-rooted pathspec,
   lifts every inner *name* into that frame, and — in an in-tree
   comment (`dir.c:472-489`) — admits it would need "a wildmatch to
   check if `name` can be matched as a directory (or a prefix)
   against the pathspec," lacks it, and therefore descends
   unconditionally on any wildcard pathspec, recovering correctness
   by post-filtering lifted names. It also *disables* its only
   pattern-derived pruning when recursing submodules
   (`builtin/ls-files.c:737-748`) rather than translate it across the
   boundary. The operation git names and lacks is exactly the
   residual computation the spike verifies.
3. **The one credible alternative is "rebase the path, not the
   pattern."** ripgrep's ignore crate compiles each container's
   patterns once in that container's own coordinates and, at match
   time, rebases the *candidate path* into each matcher's frame
   (`gitignore.rs:210`, `:286-315`); N matchers perform N independent
   path rebases, zero pattern rewriting. vfs cannot adopt this shape
   for glob: the LIKE prefilter must run inside the backend's SQL
   against entry-local path columns, and storage is deliberately
   mount-agnostic — the row would have to travel to the router before
   the pattern could see it, which is the enumerate-everything family
   at 10k-batch scale. Recorded as the considered-and-rejected
   alternative, with the caution that ignore's rebase is a lenient
   byte-prefix strip (`pathutil.rs:96-119`) — a router residual must
   validate component boundaries instead.

## Family A — caller-side enumeration (the dominant family)

- **Plan 9 rc** expands globs shell-side, and `globdir()`
  (`rc/glob.c:47-83`) is a literal residuation-by-segment machine:
  hoist the literal prefix without enumeration, open the one
  directory holding the first metacharacter, match entries against
  the current segment only, recurse with the residual pattern. rc's
  grammar confines every metacharacter to one component (`match`
  stops at `/`), which *forces* per-segment evaluation. The pattern
  never reaches the kernel.
- **9P/Twalk** carries only literal names (≤16 per RPC), and the
  kernel's `walk()` (`port/chan.c:965`) crosses mount points by
  truncating the batch at each boundary and re-issuing the residual
  name list to the new server — segment-wise residuation of a
  *literal* path, minus wildcards. Union directories retry the same
  names branch-by-branch (`chan.c:1027-1042`).
- **Linux** walks literal components only (`fs/namei.c:2574` ff.);
  glob(3) is glibc userspace over readdir. **FUSE** has no protocol
  slot for a pattern at all (`fuse_kernel.h:613-673` — lookup takes
  one literal name; readdir is offset-cursored enumeration).

Lesson: the classic stack dodges the fork entirely by never letting a
pattern near a boundary — viable only where enumeration is cheap and
local. vfs's production posture (server-side SQL prefilters, 10k+
batches) forecloses this family, but rc's `globdir` and 9P's
batch-truncating walk are the structural ancestors of the residual
loop.

## Family B — per-container scoped patterns (formalized option (a))

- **LSP/VS Code** formalize scope-anchor-plus-pattern as a type:
  `GlobPattern = Pattern | RelativePattern` where `RelativePattern =
  {baseUri: WorkspaceFolder | URI, pattern}`
  (`lsp/3.18/types/patterns.md`), used by file watchers and document
  filters, gated by a negotiated client capability
  (`relativePatternSupport`). The anchor is a mount-handle-or-raw-URI
  discriminated union — the exact shape of "entry-local pattern
  scoped by `paths`" as a wire contract.
- **Bazel** globs deliberately never cross package boundaries
  (`**/*.cc` in `x` excludes `x/y/z.cc` when `x/y` is a package),
  because a BUILD file is an ownership claim and no file may belong
  to two packages; crossing requires a *different primitive*
  (`subpackages()`) returning container handles, not files. The
  recorded counter-choice: boundary-opaque patterns are right when
  containers are ownership claims. vfs mounts are composition, not
  ownership — Article 1's one-namespace posture points the other way.
- **fsspec's `DirFileSystem`** rebases the pattern into one wrapped
  child and rebases results back (`dirfs.py:285-290`) — option (b)
  mechanics, but for exactly one container; and fsspec URL chains
  collapse to a single fs instance before glob runs, so no fsspec
  glob ever spans two instances. **pyfilesystem2's MountFS** is the
  mirror image: the walk unifies the namespace (mount table
  re-resolved per `scandir`), the pattern only ever sees full virtual
  paths, and no backend can optimize anything.

## Family C — pattern analysis that routes or prunes

- **fsspec** cuts the pattern at the last `/` before the first
  wildcard and roots its one `find` there (`spec.py:627-633`); the
  async variant pushes the stem server-side as a listing `prefix=`
  (`asyn.py:809-834`). Prefix extraction as enumeration rooting —
  C-lite, single container.
- **globset (ripgrep)** runs a fixed-priority ladder of extractors
  (`glob.rs:49-67`): whole-path literal, basename literal, extension,
  prefix, suffix, *required* extension, regex fallback — each
  returning a fact only when its soundness precondition holds (every
  one bails under case-insensitivity; `prefix()` refuses when
  `literal_separator` breaks prefix⇒match). Two fact grades matter:
  *sufficient* facts decide matches; *necessary* facts
  (`RequiredExtension`) only prune, with the full matcher still run.
  A mount-residual is a necessary fact and should carry that posture.
- **zoekt** prunes in three tiers, with a three-valued core
  (`hasReposForPredicate` → any/all, `search/shards.go:398`): a
  predicate false for a whole shard drops it; true for *all* repos in
  a shard is **discharged** — rewritten `Const{true}` and folded
  away, so the shard evaluates a *simpler residual query*
  (`shards.go:494-513`). Inside a shard, a required ngram with
  frequency zero kills the tree before any document is scanned
  (`indexdata.go:445-455`, `matchtree.go:1345`). Negative result:
  shard *selection* is driven by repo identity, never by file-path
  patterns. The discharge move maps directly onto residuation: a
  residual of `**` means "everything under this mount matches the
  path constraint" and can dispatch as an unscoped simpler call.
- **codesearch** derives a trigram query from the regex with an
  explicit dead marker (`QNone`) and an escape hatch when nothing can
  be guaranteed (`andTrigrams` returns the query unchanged for
  <3-char strings). Negative result: the `-f` path filter never
  touches the index — pure post-filter over materialized candidates
  (`csearch.go:101-139`).
- **postgres** derives `x >= 'abc' AND x < 'abd'` from
  `LIKE 'abc%'` (`like_support.c`) with a graceful ladder (exact →
  native prefix op → two-sided range → half-open → nothing) and
  refuses under nondeterministic or non-C collations. But partition
  pruning deliberately does not consume it: pruning accepts only
  partition-opfamily operators (`partprune.c:1993`), so
  `LIKE 'BC%'` prunes nothing (`partition_prune.sql:364-370`). The
  two-layer lesson: the derivation is cheap, sound, and
  well-understood; whether the container-elimination path consumes it
  is a separate, deliberate choice — postgres declined because its
  consumer (index scans) tolerates approximation-plus-recheck.

## The residuation spike

`studies/2026-07-31-glob-residuation/verify_residuation.py` implements
the candidate seam contract — 073's anchoring rule plus segment-wise
residuation (literal/wildcard components consume matching mount
segments; `**` both survives consumption and may match zero; empty
result = dead mount, skipped; empty tuple = bind-point match, owned by
the parent) — and checks **exact equality** (soundness and tightness,
stronger than 073's superset-only spike): full-pattern matches over
the unified namespace == union of entry-local residual matches per
mount. Five mount tables (nested three deep, bind-point rows modeled
as parent rows, shadowed placements excluded) × ~5,600 patterns
covering the full 14-case seam table.

Results (2026-07-31, under the revised gitignore-exact anchoring):

- **5,590 cases, zero failures** — the law holds exactly.
- **5,766 dead-mount skips** — pattern-driven routing eliminates
  dispatches constantly; the routing payoff is real.
- **261 multi-residual dispatches, max residual-set size 2** — the
  ambiguous-consumption case (`**` may or may not have eaten a
  segment) yields tiny sets; N-calls-per-mount needs no protocol
  change.
- Mutation audit: disabling the `**`-survives arm or the
  `**`-matches-zero arm produces 230 and 135 failures respectively —
  the harness detects broken residuation.

## Backward flow already applied

The ripgrep/ignore study corrected the anchoring evidence mid-stream:
gitignore floats only slash-free patterns and root-anchors anything
containing a `/` (`gitignore.rs:490-525`). Spec 073's unanchored-
pattern resolution was revised same day from float to gitignore-exact
(decision trail recorded in the spec); the spike was re-run green
under the revised rule.

## Consequences for the pattern-seam ADR

1. **Namespace patterns with residual routing are viable and now
   verified** — exact, cheap, and the only design that makes the
   glob docstring's "match against the namespace" true over mounts.
   git independently names the residual as the primitive it lacks.
2. **Dispatch shape:** multiple residuals per mount are rare and
   bounded tiny (≤2 observed; adjacent-`**` structure bounds it) —
   dispatch N entry-local calls and merge with existing fan-out
   machinery; no `SupportsPatternSearch` change.
3. **Treat the residual as a necessary fact** (globset's
   `RequiredExtension` posture): it routes and prunes; the backend's
   authoritative verify still runs. Component-aligned rebasing must
   be validated, not byte-sliced (ignore's leniency is the recorded
   anti-pattern).
4. **Optional discharge optimization** (zoekt): residual `**` ⇒
   dispatch unscoped with no path constraint.
5. **The alternatives are real and recorded:** rebase-the-path
   (ignore) fails vfs's pushdown requirement; boundary-opaque
   patterns (Bazel) encode ownership semantics vfs mounts don't
   have; caller-side enumeration (plan9/FUSE) fails at production
   scale. Postgres is the precedent for *declining* consumption —
   the honest counter-position if the ADR chooses (a) over (b).
