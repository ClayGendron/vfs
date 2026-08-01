# 091 — Plan: residual routing, tests first

Implements `spec.md`'s pinned shape as three slices, each landing
green. **Gated behind 073** — slice 1 consumes 073's `glob_patterns.py`
chokepoint and anchoring rule; do not start until 073's endgame
closes. Drafted 2026-07-31.

**Working discipline (owner's call): tests first.** Every slice
opens by writing its test rows red against the not-yet-written
surface, then implements to green. The residuation reference
implementation already exists and is verified
(`context/research/studies/2026-07-31-glob-residuation/verify_residuation.py`,
5,590 cases exact, mutation-audited) — implementation here is
porting a proven algorithm under pre-written tests, not invention.

## Decisions pinned here (the spec delegated mechanics to plan.md)

1. **`glob_patterns.py` API.** (module renamed from the drafted
   `patterns.py` to `glob_patterns.py` at implementation, owner call.) Two pure additions beside 073's
   chokepoint, mirroring the spike's reference:

   ```python
   def effective_pattern(root: Path, pattern: str) -> str: ...
   def residuals(pattern: str, mount_path: Path) -> frozenset[tuple[str, ...]]: ...
   ```

   `effective_pattern` composes ADR 030 §6: name-arm patterns return
   unchanged (coordinate-free); a path-arm pattern is anchored
   (073's gitignore-exact rule, relative to the *root* rather than
   `/`) and joined under the root — `effective_pattern("/data",
   "src/*.py") == "/data/src/*.py"`, and for root `/` it reduces to
   073's own anchoring. `residuals` takes an anchored effective
   pattern and derives component-tuples; rendering back to an
   entry-local pattern string is `"/" + "/".join(comps)`.
   `glob_defect` (073) runs before either — invalid patterns refuse
   before any routing.
2. **Hook point in `base.py`.** Residuation is a glob-only step in
   the fan-out path: where `_route_fanout` builds each binding's
   dispatch today, glob's route computes the effective pattern per
   scope root, then per candidate binding the residual set, and
   builds **one dispatch coroutine per live residual** with
   `pattern=<rendered residual>` in that binding's kwargs. The
   generic machinery — `_classify_fanout_scopes`, merge pinning,
   `row_cap`, skips, hop budget, `observations` shortcut — is
   untouched; grep/glean routes are untouched (grep picks this up in
   Pass C). Mechanically this is a thin wrapper or op-conditional
   around the existing coroutine-building loop, not a new routing
   shape.
3. **Multi-residual mechanics.** N residuals for one binding → N
   coroutines, dispatched in sorted rendered order (determinism),
   all carrying their binding's pin class (a caller-named binding
   merges loud whether it received one residual or two). Overlapping
   rows dedupe in the merge by the envelope's value identity —
   pinned by a test, not re-implemented.
4. **The assertion channel flows as today.** Scoped calls keep
   passing entry-relative anchors (`paths=rels`) to owning entries —
   miss errors, file-anchor semantics, and region expansion are
   byte-for-byte the current behavior. Residuation only substitutes
   the `pattern` kwarg. Unscoped calls keep `paths=()`.
5. **Dead residuals are silent by design** — no dispatch, no skip
   record. The distinction pinned in tests: capability skips (entry
   can't glob) still mint info records; residual-dead mounts mint
   nothing.

## Slice 1 — residuation primitives in `glob_patterns.py` (pure, test-first)

1. **Tests first**: `tests/test_glob_patterns.py` grows a unit table —
   every row of the 14-case seam table plus the spike's edge cases
   (adjacent `**` from anchoring, class-consumes-segment,
   wildcard-consumes-mount-name, exhaustion-at-bind-point, dead
   prefix, nested-mount partial consumption yielding a 2-set) — red
   against the unwritten functions. `effective_pattern` rows pin
   name-arm passthrough, root joining, leading-`/`-anchors-at-root,
   and the root-`/` reduction to 073's rule.
2. Port the reference implementation from the spike (same algorithm,
   house style; the spike keeps its own copy for claim history).
3. Re-point `verify_residuation.py` to import the landed functions
   and run it — all cases green is the slice gate. Record the run in
   the spike's docstring.

## Slice 2 — router wiring in `base.py` (test-first, doubles only)

1. **Tests first**: `tests/base/test_dispatch.py` grows a residual-
   routing block using the existing double pattern (call-recording
   storages) — red:
   - per-mount received patterns for the worked example
     (`/data/**/*.txt` → `/data` gets `/**/*.txt`; root gets the
     full pattern);
   - dead mount never called, and **no** skip record minted
     (contrast row: capability skip still records);
   - multi-residual double-dispatch (`/data/**/api/*.txt` @
     `/data/api` → two calls, sorted order) and merged dedup;
   - scoped composition (`src/*.py` + `paths=("/data",)` ≡ unscoped
     `/data/src/*.py` at the dispatch level);
   - assertion preservation (missing root error; named-entry loud
     merge; file anchor) — pinned unchanged;
   - name-arm broadcast verbatim; `observations=` path untouched;
     `row_cap` applied post-merge across multi-residual dispatches.
2. Implement per decisions 2–5. `glob`'s docstring gains the seam
   line; `ops.py`/`params.py` surface text states pattern
   coordinates once.

## Slice 3 — conformance, invariance, and true-ups

1. **Tests first**: router-level conformance rows over real
   `DatabaseStorage` mounts — the spec's acceptance list: the
   headline repro flip, the placement-invariance battery (same
   logical tree as plain dirs vs. mount, byte-identical results),
   root-relative scoping rows including the deliberate contract
   change (`/x/*.py` scoped reads root-relative), `**`-spanning into
   a nested mount, the bind-point row served by the parent.
2. Green the battery (expected: no code changes beyond slice 2 —
   this slice is proof, not features). Run the four Docker legs via
   `db_test`.
3. True-ups: `open-questions.md` seam entry gains the landed
   pointer; `STATUS.md`; spec status → landed; the residuation spike
   stays in `research/studies/` as the permanent acceptance harness,
   noted in the spec's verification section.

## Risks and non-changes

- **Backends untouched** — no storage, schema, dialect, or protocol
  edits; the four engine legs exercise only the new router behavior
  over unchanged backends.
- **Grep untouched** — filters residuate in Pass C (obligation
  recorded in spec §7); routing for grep today still passes filters
  verbatim to a stub.
- **Cost** — residuation is O(pattern components × mount-table
  segments) string work per glob call, trivial next to one dispatch;
  no caching built (revisit only with profile evidence).
- **The contract change is deliberate and narrow**: scoped path-arm
  patterns read root-relative (ADR 030 §6). The old
  mount-root-coordinate idiom appears only in tests; the conformance
  migration is part of slice 3's battery.
- **Hop budget, busy guard, permission gates** — all upstream of the
  dispatch loop and untouched.
