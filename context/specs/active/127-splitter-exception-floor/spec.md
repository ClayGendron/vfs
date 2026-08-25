# 127 — the splitter's exception floor: no admitted shape raises

- **Status: draft, 2026-08-25.**
- **Born from** the remediation-round landing review
  (`../../../research/2026-08-25-remediation-round-landing-review.md`),
  findings F3 (deep-nested `.ipynb` JSON → raw `RecursionError`) and
  F4 (lone-surrogate JSON escape → raw `UnicodeEncodeError`), both
  wedging every `reindex()` until the file is deleted, both
  reproduced end-to-end on both engines. Posture ruled in the
  2026-08-25 decision pass: **degrade at the splitter** — the write
  contract stays untouched.
- **Date:** 2026-08-25
- **Owner:** Clay Gendron
- **Kind:** robustness fix in the chunking model. Well-formed
  content splits identically before and after; the change is what
  pathological admitted bodies do (chunk, instead of raise).
- **Depends on:** spec 123 (whose law this widens from "no shape the
  JSON parse admits raises" to the full exception floor), the
  native/pure parity pin (`tests/test_native.py` — the two engines
  must keep agreeing on every new shape).
- **Relates to:** F4 falsifies the prior review memo's §4 refutation
  ("the surrogate escape is unreachable past the write gate") — that
  record is corrected by this spec's landing note, not silently.

## Intent

1. **The floor has two holes, one per exception family.**
   `split_notebook` guards its `json.loads` with
   `except (ValueError, KeyError, TypeError)` — and `RecursionError`
   subclasses `RuntimeError`, outside the tuple. A writable ~10 KB
   body of `"["*10000 + "]"*10000` (depth 9,999 on CPython 3.13)
   writes fine, then every `reindex()` raises raw for the whole
   store, healthy files included, until the file is deleted (F3).
2. **The second hole is downstream of the parse and reachable
   through the write gate.** The gate refuses only *direct*
   surrogate strs; a pure-ASCII notebook whose JSON carries a
   `\ud800` escape has its surrogate *manufactured by* `json.loads`,
   and the unguarded `content.encode("utf-8")` in `split_code_batch`
   raises raw `UnicodeEncodeError` (F4). Routing to the recursive
   fallback cannot close this class: the fallback's own
   `normalize_content` encodes the same way and raises identically —
   the fix must make the encode sites total, not re-route around
   them.
3. **The law, restated whole:** any body the write gate admits
   either splits by its route or degrades to a coarser split — no
   exception class escapes the splitter, `RecursionError` and
   `UnicodeEncodeError` included. Spec 123 stated this for notebook
   metadata; this spec makes it the floor for the module.

Laws that bind the slices:

1. **No admitted shape raises out of the splitter** — the docstring
   contract, now true for the parse, the cell walk, the encode
   sites, and the fallback path alike.
2. **Well-formed content is untouched:** the committed chunking
   fixtures referee that every current split is byte-identical.
3. **Native and pure agree:** every new pathological shape is pinned
   equal across both engines (`test_native.py`'s convention) — a
   degradation policy that only one engine applies is a parity bug,
   not a fix.
4. **Batch and single stay pinned equal** across the new shapes,
   per the existing parity convention.

## Shape

- **§1 The parse guard widens.** `split_notebook`'s parse guard
  catches `RecursionError` explicitly beside the declared tuple and
  routes to the recursive fallback, per the existing fallback
  contract. (Note: the fallback must be safe for the same body —
  which §2 guarantees, since the deep-nested body is pure ASCII.)
- **§2 The encode sites take a surrogate policy.** The splitter's
  encode boundaries (`split_code_batch`'s `content.encode("utf-8")`,
  `normalize_content`) stop being partial: surrogates degrade
  explicitly (the `errors=`-policy shape `pattern_matching/grep.py`
  already uses) rather than raising. The slice decides the exact
  policy — scrub to U+FFFD or surrogatepass-and-fold — against two
  referees: the Rust engine must produce the identical answer for
  the identical input (law 3), and grep over the resulting chunks
  must not desynchronize offsets from the stored content. State the
  chosen policy in the module docstring.
- **§3 The sweep.** F3/F4 are instances of a class: sweep
  `models/chunking.py` for any other raise reachable from an
  admitted body outside a declared contract — `split_code`'s
  tree-sitter path, `split_with_line_ranges`, the span assembly.
  Every hole found is fixed under the same law; the sweep's clean
  verdict is recorded in the landing note either way.
- **§4 The pins.** A deep-nest battery (the F3 body at and beyond
  the bisected threshold); a surrogate battery (markdown-cell and
  code-cell carriers, the raw manufactured-surrogate string on the
  splitter directly); one end-to-end row per family — the wedging
  body written into a store, `reindex()` completes, the body chunked
  and its content served; parity rows on both engines and both
  split forms. Ledger rows land with their executed reverted-shape
  mutants under safe-restore, one per family.

## Slices

- **A** — §1 + §4's deep-nest half: the parse floor.
- **B** — §2 + §3 + §4's surrogate half and the sweep: the encode
  floor.

Gates: `scripts/ci.sh 3.13` at 100 % coverage; `cargo test` plus
`uv sync --reinstall-package vfs-py` if the Rust seam needs the
policy mirrored; engine legs only if the end-to-end rows touch
engine-specific paths (models-layer change — the sqlite legs are
expected to carry it, per spec 123's precedent).

## Landing note (2026-08-25)

- **Policy ruled (§2):** scrub to U+FFFD, applied once at
  `split_code_batch`'s door (`_scrub_unstorable`) before the encode
  and the engine seam — one character for one, so boundaries and
  line ranges never move and both engines see the identical
  scrubbed body. `normalize_content` becomes total via
  `surrogatepass` — the byte-domain backstop that keeps its
  index-stream-equals-verify-stream law exact (grep's verify uses
  the same spelling), covering the recursive fallback and the gram
  planner's pattern literals. The Rust seam needed no mirroring:
  the scrub runs in Python pre-seam, so no `cargo`/reinstall gate
  applied.
- **The sweep (§3) found one more hole, same class:** a JSON
  `\u0000` escape manufactures a null byte in a cell source, and
  the chunk model's null-byte validator raised it out of the
  splitter (executed: `ValidationError` from `Chunk.split`). Fixed
  by the same scrub — NUL degrades to U+FFFD beside the
  surrogates. Direct null bytes and direct surrogates are both
  refused by the write gate (verified executed), so the class is
  manufactured-only. Beyond that, the sweep is clean: the engine
  seam is declared-total (`None` on any decline), span assembly
  decodes with `replace`, and the recursive splitter's
  `ValueError`s are caller-contract, unreachable from any body.
- **Ledger rows:** P18 (parse guard loses its recursion arm,
  3 kills) and P19 (encode floor falls, both directions: scrub
  deleted, 8 kills; strict `normalize_content`, 2 kills), executed
  under safe-restore.
- **Record correction:** the prior campaign memo's §4 refutation
  ("the surrogate escape is unreachable past the write gate") is
  corrected in place in
  `2026-08-25-chunking-arc-landing-review.md`, dated, per the
  amendment pattern.
