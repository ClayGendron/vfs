# Verify-stage prior art: how zoekt, codesearch, and ripgrep reject candidates before regex

- **Status**: research memo — slice A of the Rust-core story (spec
  103); design input for the read-side §3 shape (literal prefilter,
  line recovery, authority regex)
- **Date**: 2026-08-16
- **Owner**: Clay Gendron
- **Question**: After an index (or nothing) narrows to candidate
  files, how do the field tools spend as little as possible before
  the authoritative matcher runs — and what should a Rust read-path
  core borrow?
- **Evidence gathered**: line-level read-only studies of the three
  reference checkouts (licenses re-confirmed: zoekt Apache-2.0,
  codesearch BSD-3, ripgrep MIT/Unlicense), driven by the questions
  the profiling memo raised
  (`2026-08-16-grep-read-path-profile.md`: verify is 82–99.7% of
  every query at linux scale). Cites and describes only — every
  line of vfs code stays ours.

---

## 1. The cross-cutting law: lines are presentation, not matching

All three tools refuse to split content into lines before matching.
The matching loop is offset-oriented; line boundaries are derived
from match offsets, never the reverse:

- **ripgrep**'s fast path scans the raw buffer with an accelerated
  literal/regex search and recovers the enclosing line per hit with
  `memrchr`/`memchr` (searcher `core.rs:475-517`,
  `lines.rs:135-147`); per-line iteration exists only as a
  documented compatibility fallback (`core.rs:673-708`).
- **codesearch** streams each candidate file through a byte-DFA with
  line semantics baked into the automaton (reset-at-`\n`,
  match-state-at-`\n` returns the line end — `regexp/match.go:283-313`);
  line *starts* are found by scanning backward from the hit
  (`match.go:484`) and newlines are counted only when output needs
  numbers (`match.go:489-491`).
- **zoekt** goes further: its postings store rune offsets into the
  shard, so verification is a direct string comparison *at each
  candidate offset* (`index/matchiter.go:50-68`) — content is never
  scanned for the substring core at all — and a precomputed per-file
  newline table is consulted only around hits
  (`contentprovider.go:460-489`).

vfs today does the reverse (split every candidate's content, regex
every line) — the profiling memo measured what that costs.

## 2. The three mechanisms worth borrowing

**Inner-literal prefilter with a Confirmed/Candidate split
(ripgrep).** grep-regex extracts a *required* literal from the
pattern's HIR — including from the middle of it — and scans for that
first; a hit locates the line, and the authoritative regex runs on
that one line slice (`crates/regex/src/literal.rs:11-92`). The hit
kind is two-valued (`LineMatchKind`,
`crates/matcher/src/lib.rs:517-531`): `Candidate` needs the regex,
`Confirmed` does not — when the literal *is* the effective pattern
(leading/trailing `.*` stripped), the prefilter alone decides. The
soundness contract is stated in ripgrep's own docs: false positives
allowed, false negatives never — exactly the gram planner's law, one
level down. Validity boundary to respect: the trick assumes
single-line semantics; multiline patterns must fall back to
whole-content spans (`literal.rs:56-63`).

**Two-rarest-trigrams + verify-by-comparison (zoekt).** Zoekt reads
only the two lowest-frequency trigrams' posting lists
(`indexdata.go:342-384`), leapfrogs them at their exact distance
(`hititer.go:39-93`), and string-compares the *whole* substring at
each surviving offset — the other trigrams are never fetched.
Case-insensitive comparison folds runes at the offset
(`bits.go:62-78`; the Kelvin-sign comment at `matchiter.go:57-63`
warns off ASCII shortcuts — the same orbit discipline our fold test
pins). Cost-staged evaluation (`eval.go:276-289`) orders doc
intersection → literal compare → full regex so every file dies at
the cheapest stage that can decide it. Zoekt also discards
leading/trailing `.*` during decomposition (`eval.go:686-689`) — the
`.*alloc_page.*` shape reduces to its literal core there too.

**Line-aware byte-DFA streaming (codesearch).** The floor design:
no offsets, no prefilter, but O(1)-per-byte scanning with lazy line
recovery — proof that even the no-index-help path never needs
per-line regex calls.

## 3. Implications for the Rust core (spec 103 §3)

1. **Scan bytes, recover lines around hits**: memmem for the
   planner's longest guaranteed run over the full content buffer;
   per hit, `memrchr`/`memchr` for the line; authority regex on that
   line slice only; jump to line end.
2. **Model Confirmed vs Candidate**: when the folded literal is the
   whole effective pattern, skip Python `re` entirely (case-exact
   patterns still verify case on the raw slice). This alone deletes
   the 102 s pathology — 3,720 candidate files reduce to memmem plus
   418 line recoveries.
3. **Lazy line numbers**: count `\n` only up to emitted matches; a
   per-file newline offset table is the zoekt-shaped upgrade if
   result assembly ever dominates.
4. **Rarest-first is already right at doc grain**: the ladder's
   rarest-gram ordering matches zoekt's frequency discipline;
   positional postings (offsets, not doc ids) are the recorded
   long-term ceiling, not this story's scope.
5. **Case folding at the verify boundary must keep the orbit
   invariant** — fold-compare at offsets like zoekt, never
   ASCII-lowercase; the exhaustive orbit test extends to the Rust
   comparator.
6. **Deadline checks belong inside the hit loop** (per hit / per N
   bytes), which discharges the batch-granularity gap the profile
   found.

## 4. Limitations

Versions studied are the local checkouts as of 2026-08-16; ripgrep's
literal heuristics (`Extractor` limits, Teddy's 4-byte truncation)
are implementation details that drift — the borrowed *shape* is the
Confirmed/Candidate contract and match-first-lines-second order, not
the constants. Zoekt's offset postings assume a shard format vfs
does not have; only its verify discipline transfers today.
