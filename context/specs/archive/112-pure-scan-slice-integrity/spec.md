# 112 — Pure-scan slice integrity: no phantom boundary matches, an honest wall record

- **Status: all slices landed 2026-08-18.**
  §1: the whole-text scan loops discard zero-width matches landing
  exactly on a non-final slice end — the `endpos`-as-end-of-string
  artifact — and the next slice judges that position with real
  context. Fabrication repro (40 non-empty lines, `^$`, budgeted):
  before `[2]` with hits on lines 17/33, after `[0]`/no hits, equal
  to unbudgeted; displacement repro (`cap=1`, genuine empty line 19):
  before returns the fabricated line-17 hit, after the genuine hit,
  both spellings; public surface (`grep("^$", allow_scan=True)` on
  the pure engine) 1 observation → 0. §2: the battery gained three
  slice-boundary bodies (anchors hitting lines 1/17/33/last, empty
  lines on both boundaries), a budgeted-equals-unbudgeted sweep over
  all CASES on the pure engine, a budgeted-pure-equals-authority
  sweep, and three targeted rows (fabrication, cap displacement,
  genuine-boundary-line served once). Guard-removal mutant killed by
  4 tests (both `^$` sweep rows, fabrication, displacement) under
  the safe-restore discipline. §3: the `_PureMatcher` docstring
  carries the measured residual (273 ms per 16-line slice of 18-char
  lines, 65 ms per 20-char line, doubling per two characters — a
  floor, not a bound), the single-check-at-entry profile of one-slice
  bodies, and the exact-results-on-overrun law; the ReDoS pin
  re-shaped from 18-char lines under a 2.0 s ceiling (~100×
  headroom) to 20-char lines (~1.05 s/slice) under 3.0 s, with the
  authority twin on the same shape. §4: the residual-bounding fork
  recorded in `open-questions.md` beside the event-loop occupancy
  fork (finer-grain interruption / complexity gate / worker-thread
  offload — one decision should settle both). Parity file 142
  passed on both engine legs; deadline-cadence spelling untouched
  (§1's rewrite never reached those guards). Full 3.13 CI leg green.
  **Mined 2026-08-19:** decision set recorded in ADR 046 alongside spec 110's (zero-width discard at slice ends, budgeted parity pins, the residual disclosed not bounded, the residual fork deferred with the offload memo's findings). Folder stays as the historical record.
- **Drafted 2026-08-18.**
  Born from the remediation-landing review
  (`../../../research/2026-08-18-remediation-landing-review.md`),
  findings 1 (fabrication + cap displacement — the arc's only
  wrong-results defect), 2 (exponential wall residual, single-slice
  exemption), 6 (the false docstring claim), and 7 (the unpinned
  anchor half of the equivalence law). All four live in the same
  file and the same slicing mechanism; they land as one change.
- **Date:** 2026-08-18
- **Owner:** Clay Gendron
- **Kind:** correctness fix plus record-truing in the pure matcher —
  the Rust engine is untouched and stays the parity oracle; the two
  engines must remain byte-identical wherever both finish.
- **Depends on:** spec 110 (the slicing this repairs), spec 103 /
  ADR 039 (the two-engine parity law and `tests/test_native.py`'s
  pins).
- **Relates to:** the event-loop occupancy fork in
  `../../../open-questions.md` (the residual-bounding fork recorded
  here is the same territory: an offloaded scan could be truly
  interrupted), spec 113 (owns the storage-seam coverage pins; this
  spec owns the matcher-level ones).

## Intent

1. **The sliced scan invents matches.** `_count_whole` and
   `_hits_whole` pass each slice's end as `endpos`
   (`finditer(text, begin, stop)`), which CPython's `re` treats as
   end-of-string — so MULTILINE `$` matches at every 16-line
   boundary, and the phantom is attributed to the following
   non-empty line. Every storage grep passes a budget, so the sliced
   path is the pure engine's default path. Uncapped, this fabricates
   hits (`grep("^$")` reports matches on lines 17 and 33 of a file
   with no empty lines); under a cap — files mode always passes
   `cap=1` — the phantom consumes the cap slot and **displaces the
   genuine match**, returning the wrong hit instead of the right
   one. `completed=True` throughout, `success=True`, zero errors.
2. **The wall budget's residual is exponential and partly
   unrecorded.** The deadline is consulted only between slices, one
   slice of `re` backtracking is exponential in line content
   (measured: doubling per two characters; a 31-byte body ran 75 s
   under a 1.0 s budget), and the `and begin` guard exempts
   single-slice bodies from any clock check at all. The results of
   an overrun are exact — this is a wall breach, not data loss, and
   the review's cap-plus-deadline probe established that flipping
   `completed` on a finished body would be wrong (the flag means
   data completeness, and the storage caller's per-batch deadline
   check already records any breach that could cost data). What the
   code owes is an honest record and a pin near the wall, plus a
   named fork for actually bounding the residual.
3. **The record contains a checkable false claim.** Spec 110's
   status and commit say the 273 ms residual floor is "recorded in
   the docstring"; no docstring carries it.
4. **The equivalence law's anchor half is unpinned.** A slicer whose
   boundaries land one character into the next line passes the whole
   pure-leg suite while changing budgeted counts; only the
   never-cut-mid-line half is (indirectly) pinned. Every
   cross-engine parity assertion runs `budget=None` — the exact
   blind spot that let §1 ship.

Laws that bind the slices:

1. **Byte-identical engines, now including budgeted paths.** A
   budgeted pure scan that completes must equal the unbudgeted scan
   and the Rust engine's answer exactly — counts, hit tuples, line
   numbers — for every pattern the gate admits. Expiry may only
   shrink the result (a lawful subset, reported incomplete), never
   grow or substitute it.
2. **`completed` means data completeness, nothing else.** A body
   fully scanned reports complete even if the wall was breached; a
   truncated body reports incomplete. No repair may convert wall
   observability into false truncation signals.
3. **Suboptimalities are recorded, never converted into limits.**
   The exponential residual is acknowledged with its measured
   magnitude and its exemption honestly named; no pattern-complexity
   refusal lands without its own decision pass.

## Shape

- **§1 The phantom fix.** The whole-text scan must never let a slice
  boundary present as end-of-string. Direction: iterate from `begin`
  against the full text (`finditer(text, begin)`) and stop consuming
  once a match starts at or past `stop` — or equivalently discard
  any zero-width match ending exactly at `stop` while `stop <
  len(text)` and let the next slice's genuine scan judge that line.
  The same-line dedup stays as-is (proven output-invisible on its
  own across a 20,000-trial fuzz). The split paths are unaffected
  (they judge whole lines) but ride the same parity sweep.
- **§2 The budgeted parity sweep.** The missing pin, at the matcher
  seam in `tests/pattern_matching/test_matcher_parity.py`: the
  existing CASES battery swept with a generous (non-expiring) budget
  and asserted byte-equal to the `budget=None` answer and to the
  Rust engine, str and bytes bodies — plus targeted rows: the
  fabrication shape (`^$` over ≥17 non-empty lines), the
  cap-displacement shape (`cap=1`, a non-matching line directly
  after the boundary, the genuine match later), and anchor shapes
  (`^`-, `$`-, `\b`-headed patterns hitting lines 1, 17, 33, and
  last). The anchor rows also kill the line-shifted slicer mutant
  (finding 7) — one sweep closes both findings.
- **§3 The honest wall record.** The `_PureMatcher` docstring names
  what is true: the residual between checks is one slice of `re`
  backtracking, exponential in line content for pathological
  patterns (the measured 273 ms figure is one recorded shape, not a
  bound; a single pathological line ran 75 s), and single-slice
  bodies pay it whole. Whether the `and begin` exemption itself
  changes is §4's fork — the record does not wait on the fork. The
  ReDoS pin is re-shaped onto lines near the measured wall (the
  landed pin's 18-char lines sit two orders of magnitude under its
  2.0 s ceiling and cannot trip).
- **§4 The residual-bounding fork, recorded not landed.** Options
  with their trade-offs, for a decision pass: finer-grain
  interruption (a wrapping scan that re-checks the clock per match
  attempt — costs per-match overhead on every budgeted scan), a
  pattern-complexity gate on the pure path (refuses shapes the gate
  already admits — collides with law 3), or offloading the scan to a
  worker thread where a true timeout is possible (the event-loop
  occupancy fork's territory — one decision should settle both).
  Record in `open-questions.md` beside its sibling.

## Slices

- **A. Fix and sweep.** §1 with §2's parity sweep and targeted rows;
  the fuzz harness's fabrication shapes re-run clean.
- **B. The record.** §3's docstring and pin re-shape, §4's fork
  recorded; spec status updated with the measured before/after on
  the fabrication and displacement repros.

## Open questions

- **§4's fork** (residual bounding) — deliberately not resolved
  here; see `open-questions.md` after slice B.
- **Deadline-cadence spelling** (review design question 2): the
  skip-first-check convention is spelled three ways, all proven
  phase-identical; spec 110's byte-cap-slicing follow-up cannot be
  expressed by the line-counting strides. If §1's rewrite touches
  those guards anyway, unifying the spelling is in scope; a
  standalone abstraction pass is not.
