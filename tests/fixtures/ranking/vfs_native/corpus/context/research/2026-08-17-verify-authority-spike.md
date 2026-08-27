# Verify authority spike: Python `re`, whole-text `re`, prefilter, or Rust

- **Date:** 2026-08-17
- **Question (Clay, in session):** slice C of spec 103 rewrites grep's
  verify stage — should the verify *authority* itself move to Rust's
  regex crate, or does Python `re` stay the sole authority behind a
  Rust prefilter? Optimize for speed.
- **Method:** executed benchmark — four verify-stage strategies raced
  on faithful candidate sets at linux scale (93,760 files / 1.59 GB,
  the 25 recorded benchmark rows), M-series laptop, median of 3.
  Artifacts and reproduction: `studies/2026-08-17-verify-authority-spike/`.
- **Feeds:** spec 103 §3 (read side), §4 (per-call floor), the
  bench gate (every row beats rg, recorded rg floor 3.0–3.6 s/query).

## Method

Candidate sets were reproduced in memory rather than from a rebuilt
5 GB store, using the production pieces end to end: the planner
(`build_code_gram_query`), the indexability gate (`_indexable`), the
native Rust engine (`vfs.native` postings builder), and a replica of
the ladder's rarest-4/byte-budget selection, candidate cap, and
overlay-consultation rule. Replication anchors matched the recorded
2026-08-16 run exactly: 93,760 files / 1.59 GB, 96 overlay files,
3,720 wrapped-wildcard candidates, and the same nine rows truncated at
`CANDIDATE_BUDGET`.

Strategies, all producing the `lines`-mode deliverable (matched line
slices) per candidate body:

- **S0 current** — the live `pattern_matching.grep.verify`: split into
  lines, Python `re` per line (includes Match-model construction; the
  others exclude it — a per-hit cost identical across strategies).
- **S1 whole-text re** — Python `re.finditer` over the un-split body
  (`re.MULTILINE` preserves the per-line `^`/`$` law), enclosing line
  recovered per span. Pure Python, authority unchanged.
- **S2 prefilter + line re** — §3's shape in pure Python: `str.find`
  on the row's longest guaranteed literal (folded stream for
  case-insensitive rows — the proven orbit-superset), line recovery
  per hit; **Confirmed** hits (literal == effective pattern after
  stripping wrapping `.*`) skip `re` entirely; **Candidate** lines
  pass through the authority.
- **S3 Rust** — the regex crate over raw bytes with memchr line
  recovery (single-thread and rayon), plus a memmem-prefilter variant
  mirroring S2. The str→bytes encode a pyo3 boundary pays is measured
  separately (`encode_tax`).

## Results (wall ms, median of 3; n = candidate+overlay bodies)

| row | n | S0 current | S1 whole-text | S2 prefilter | S3 regex 1t | S3 prefilter 1t | S3 regex mt | encode tax |
|---|---|---|---|---|---|---|---|---|
| zero-hit | 99 | 631 | 98 | 57 | 11.5 | 11.4 | 3.4 | 13 |
| rare literal | 160 | 643 | 90 | 59 | 11.6 | 11.7 | 3.4 | 9 |
| medium literal | 965 | 854 | 115 | 76 | 13.0 | 13.0 | 3.8 | 12 |
| medium literal 2 | 360 | 770 | 115 | 97 | 13.0 | 12.8 | 3.8 | 10 |
| medium literal 3 | 346 | 690 | 96 | 74 | 12.1 | 12.3 | 3.5 | 9 |
| hot literal | 4,393 | 1,425 | 213 | 135 | 18.4 | 18.2 | 5.3 | 18 |
| hot literal 2 | 4,241 | 1,472 | 143 | 262 | 18.1 | 17.9 | 5.4 | 23 |
| ultra-hot literal | 10,000 | 1,419 | 90 | 107 | 11.8 | 11.6 | 3.3 | 21 |
| phrase | 8,460 | 1,854 | 238 | 190 | 26.9 | 26.8 | 6.0 | 24 |
| fixed string | 10,000 | 1,706 | 97 | 177 | 14.2 | 13.7 | 3.9 | 25 |
| fixed string 2 | 10,000 | 1,858 | 213 | 150 | 16.5 | 16.4 | 4.4 | 24 |
| escaped call | 5,785 | 1,713 | 176 | 192 | 22.2 | 21.4 | 6.5 | 23 |
| regex classes | 10,000 | 1,312 | 167 | 191 | 29.4 | 14.3 | 5.2 | 19 |
| **wrapped wildcard** | 3,816 | **130,785** | **131,444** | **248** | 1,150 | **24.3** | 152 | 23 |
| folded | 10,000 | 647 | 351 | 74 | 10.4 | — | 1.8 | 6 |
| folded 2 | 1,183 | 2,758 | 2,062 | 354 | 49.6 | — | 7.2 | 14 |
| **word** | 10,000 | **4,465** | 3,140 | **262** | 16.4 | 16.1 | 4.2 | 23 |
| **word 2** | 4,899 | **5,444** | 4,457 | **269** | 21.9 | 21.9 | 6.1 | 22 |
| alternation | 5,391 | 4,459 | 2,965 | — | 65.1 | — | 9.6 | 25 |
| factored alternation | 10,000 | 1,462 | 126 | 217 | 42.9 | 17.7 | 6.1 | 20 |
| group alternation | 5,889 | 1,154 | 172 | 299 | 17.2 | 17.2 | 5.1 | 18 |
| anchored group | 10,000 | 1,030 | 1,220 | — | 31.3 | — | 6.0 | 17 |
| anchored literal | 10,000 | 1,118 | 1,156 | 52 | 11.0 | 10.6 | 2.8 | 15 |
| small class | 1,118 | 891 | 152 | 401 | 51.0 | 17.3 | 7.6 | 13 |
| rescued class | 270 | 661 | 89 | 401 | 31.6 | 11.6 | 6.0 | 10 |

**Parity:** every strategy on every row returned identical
files-with-hits and matched-line counts to S0, the live authority —
including the Rust regex crate across ~250K matched lines. (The S1/S3
"regex classes" row uses the `\n`-stripped respelling of `\s`; see
finding 6.)

## Findings

1. **The per-call floor is confirmed and cheap to delete.** S0 never
   goes below ~630 ms — the 96-file / 366 MB unindexable overlay is
   line-split and per-line-regexed on every call (§4's attribution).
   S2 puts the zero-hit row at 57 ms in pure Python; Rust at ~11 ms
   (3.4 ms threaded). The §4 target (zero-hit ≤ 25 ms) is met by the
   Rust path and near-met by pure Python.

2. **The wildcard pathology dies to the effective-literal reduction,
   not to Rust.** Whole-text S1 does *not* fix it (131 s — the
   leading-`.*` backtracks per position exactly as per-line `re`
   does), and even the Rust regex crate scans it at 1,150 ms because
   the crate does not strip wrapping `.*` (its lazy DFA walks every
   byte). Stripping to the Confirmed literal `alloc_page` gives 248 ms
   in pure Python and 24 ms in Rust. §3's reduction is mandatory in
   both worlds.

3. **Verify-heavy rows collapse under the prefilter shape.** Word
   rows: 4.5–5.4 s → ~265 ms pure Python → ~16–22 ms Rust. The
   authority-on-candidate-lines cost is small because hit lines are
   sparse relative to scanned bytes — Python `re` on the ~38K hit
   lines of the hottest word row is within ~250 ms even in the pure
   path.

4. **Pure Python meets the bench gate on 23 of 25 rows with wide
   margin, thin on two.** With S2 (literal-bearing rows) and S1
   (no-single-literal rows), every row lands ≤ ~400 ms except
   `TODO|FIXME` (2,965 ms) and the anchored group (1,220 ms) — still
   under rg's 3.0–3.6 s floor, but by only ~1.2× on the alternation.
   Rust clears every row by 50–300× (≤ 65 ms single-thread + 6–25 ms
   encode tax; ≤ 10 ms threaded).

5. **The pyo3 boundary tax is the same order as the Rust scan
   itself.** Encoding candidate bodies str→bytes costs 6–25 ms per
   query (230–660 MB) — unavoidable while content lives as Python
   `str` (pyo3's `&str`/`&[u8]` extraction encodes). It bounds any
   Rust verify at ~10–50 ms per query total: trivially inside the
   gate, but worth recording — a future content-bytes-at-rest design
   would delete it.

6. **Whole-text scanning needs the `\n`-exclusion law.** `\s` (and
   any negated class admitting `\n`) can match across lines in
   whole-text mode, which the per-line authority never does. rg
   solves this by transforming the pattern's HIR to remove `\n` from
   classes; the regex crate exposes the machinery (`regex-syntax`).
   Python `re` cannot do this generically — a pure-Python whole-text
   scan is only sound for patterns a `sre_parse` walk proves
   `\n`-free, else the fallback stays line-split.

7. **Soundness needs no Rust/Python semantics parity.** The raced
   Rust strategies matched the authority empirically, but the design
   below never relies on it: Rust only *discovers candidate lines*
   (a necessary condition), and Python `re` stays the authority on
   them. The known crate gaps — no backreferences, no lookarounds,
   no possessive/atomic groups (compile-time detectable) — route to
   the fallback tier; the case-insensitive orbit gap (the crate's
   simple fold lacks sre's Turkic-i extras) is closed by discovering
   on the folded stream (the proven orbit superset), or equivalently
   by unioning lines containing the two Turkic codepoints (UTF-8
   `C4 B0`/`C4 B1` memmem — rare, ~free) into the Candidate set.

## Recommendation for slice C

**Keep the law: Python `re` remains the sole match authority. Move
line *discovery* to Rust, with the Confirmed shortcut.** Concretely:

- The planner's guaranteed-literal variants (landed in spec 100 —
  every indexable pattern has them; that is what `is_any()` refuses)
  become the discovery needles: memmem for one literal, Aho-Corasick
  or the regex crate for variant sets, folded stream for
  case-insensitive patterns, raw for case-exact. GIL released,
  parallel across entries.
- Per hit, recover the enclosing line; **Confirmed** hits (literal ==
  effective pattern, case-exact verified on the raw slice) skip the
  authority; **Candidate** lines run through Python `re` exactly as
  today. Findings 2–3 show this meets every row with two orders of
  margin without asking Rust to *be* the authority — so no orbit
  parity burden, no translatable-subset contract, no drift risk.
- The pure-Python fallback engine adopts the same shape (S2, with S1
  whole-text only where a `sre_parse` walk proves the pattern
  `\n`-free): the fallback leg then also beats rg on 23 of 25 rows,
  and its two thin rows stay correct — the fallback's contract.
- Full-Rust authority (the crate as matcher for a translatable
  subset) stays available if a future need appears — this spike's
  parity evidence (25/25 rows, ~250K lines) and divergence catalog
  (finding 7) are the groundwork — but nothing in the bench gate
  requires it, and it would buy ~100–250 ms only on the two
  no-literal Python-fallback rows while adding a permanent parity
  obligation.

## Residuals

- `invert_match` and the `allow_scan` tier (GramAny patterns, no
  literals) keep the line-split authority shape — scan-shaped by
  construction, wall-bounded; untouched by this spike.
- The S0 wildcard row measured 130.8 s here vs 102 s in the recorded
  pipeline run: production tripped the 10 s wall mid-verify and
  truncated; the spike verifies the full candidate set. Same order,
  same attribution.
- Numbers are relative to this machine (M-series laptop); the bench
  gate re-baselines rg per machine, per spec 103.
