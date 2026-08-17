# 041. Priced Nomination, Join-Built Allow-Lists, and Passthrough Assembly

- **Status:** accepted 2026-08-17 — the record of the post-spec-104
  optimization arc (commit `1b36b4a`), written at the 104/105/106
  mining pass. Amends the *shapes* of ADR 040's §4 nomination and
  spec 104's assembly path; every contract, law, and budget of
  ADR 033/040 stands.
- **Date:** 2026-08-17
- **Deciders:** Clay Gendron (the "close the gaps to rg" directive
  and the no-numpy-in-small-set-code rule); shapes chosen from the
  arc's measured experiments.
- **Context source:** the stage-by-stage profile and four parallel
  prototype experiments run against the 2026-08-16 linux store
  (93,760 files), whose decisive numbers are recorded in the spec
  104 status record and the `1b36b4a` commit; independently
  corroborated by the overlay-probe memo
  (`../research/2026-08-17-overlay-probe-cost.md`).

## Context

With spec 104 landed, vfs still lost 6 of 12 scoped benchmark rows
to ripgrep's positional form. A stage profile located the losses:
segment allow-lists were built by shipping full per-term posting
sets to Python (36 ms for `drivers`' 40k ids, paid even when the
gram side was already narrower); the gram ladder ran even when a
tiny scope made verifying it outright cheaper (13 ms of posting
decode discarded by a 53-id allow-list); and result assembly paid a
hidden second `Path` canonicalization per row because the pydantic
schema stripped the branded subclass before its validator (58 ms of
a 116 ms row).

## Decision

1. **Allow-lists are built by one rarest-first covering-index
   self-join, seeded by a grouped COUNT.** Only the intersection
   crosses the wire. Measured alternatives rejected: `INTERSECT`
   (16.0 ms, TEMP B-TREE) and rarest-term-only nomination (widens
   the superset, costing more downstream than it saves). The COUNT
   seeding matters on sqlite (written-order joins: 17.2 vs 7.6 ms)
   and is neutral on engines with their own statistics.
2. **The gram ladder is priced before any blob is fetched.** One
   batched metadata read covers every AND-group; the ladder defers
   to the allow-list outright when the posting byte bill exceeds
   the scope's verify cost (`Σ(500 µs + 0.055 µs/byte) >
   |allow| × 75 µs`, constants measured). Deferring is lawful —
   the allow-list is a superset and the verifier stays authority.
   The naive "skip when allow < rarest gram count" rule was
   measured as a ~60 ms regression and rejected.
3. **Assembly passes branded values through instead of re-gating.**
   `Path`'s pydantic schema is a wrap-validator: branded instances
   pass through identically; raw strings and JSON still run the
   full gate. Stored paths re-brand (`Path._brand`) rather than
   re-gate — they passed the gate at write time. `model_construct`
   was measured 2.2× *slower* than pydantic's Rust `__init__` and
   rejected.
4. **SQLite session tuning is a profile fact**: `mmap_size = 8 GiB`
   and `cache_size = 256 MiB` in the SQLITE profile's session
   settings — sqlite is the local store that races rg; other
   engines are untouched.

## Consequences

- The scoped board moved from 6 losses to 10-of-12 wins in one
  landing (`copyright -i @ fs/ext4` 26.6 → 8.0 ms vs rg 11.4;
  `kzalloc @ drivers/net` 146.9 → 77.6 vs 123.6), zero unscoped
  regressions, counts identical everywhere.
- The re-brand posture trades read-side defense against out-of-band
  database edits for ~5.7 µs/row: a row edited behind vfs's back
  can now carry a non-canonical path into results unvalidated.
  Accepted knowingly; the write path remains the gate.
- The pricing constants (75 µs/candidate, 0.055 µs/posting-byte)
  are measured facts that future hardware or storage changes must
  re-derive, like ADR 039's budgets.
