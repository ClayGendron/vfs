# 035. Python Floor 3.11+, Target 3.13: A Recorded Floor with Named Reversal Triggers

- **Status:** accepted 2026-08-11 — decided by Clay from the research
  memo's three-option evaluation
  (`../research/2026-08-11-python-version-floor.md`), recommendation
  confirmed. Records what was never a decision: `requires-python =
  ">=3.13"` landed in the scaffolding commit (`4730a04`, 2026-02-06)
  before any code existed, and drifted from `standards/tooling.md`'s
  "3.12 minimum, 3.13 target". Annotates ADR 032 (the compile
  chokepoint's translation vehicle is now in-house; semantics
  unchanged).
- **Date:** 2026-08-11
- **Deciders:** Clay Gendron
- **Context source:** a teaching session on the grep/glob landing asked
  whether the `re._parser` binding forced the 3.13 floor. The audit
  answered no — the one 3.13-only dependency was stdlib
  `glob.translate` inside the ADR 032 chokepoint — and surfaced the
  pyproject/tooling.md drift. The floor question then ran the research
  pipeline: executed code-cost legs at 3.10/3.11/3.12 (ty sweeps, uv
  resolutions, a full suite run on CPython 3.11.14 in a scratch copy)
  and an ecosystem sweep (CPython EOL, LTS distros, Databricks, AWS
  Lambda/Glue, pypistats shares, peer floors), all in the memo.

## The deciding argument

vfs is an agent-facing library, and its floor is an adoption surface,
not a style preference. The environments its users actually run —
every current AWS Glue version (5.0/5.1, Python 3.11), Databricks
15.4 LTS (3.11, supported to 2027-08), Debian 12, Lambda python3.11
(to 2027-06) — plus ~20–24% of live PyPI traffic sit on 3.11, and
every agent-ecosystem peer (langchain-core, langgraph, mcp, fastmcp)
declares ≥3.10. Against that reach, the measured cost of a 3.11 floor
is two `TypeVar` spellings, one extra CI leg, and holding numpy at its
2.4.x line — proven green end to end before deciding. 3.10 fails on
the evidence (numpy resolution fails, 130 diagnostics across
load-bearing contracts, EOL 2026-10-31); 3.12 walks away from a third
of live traffic to simplify nothing but two generic signatures. A
floor is only honest if tested and only durable if its exit is named:
CI carries the floor, and the reversal triggers below make the next
raise a scheduled event rather than a debate.

## Decisions

### 1. The floor is 3.11; the target stays 3.13

`requires-python = ">=3.11"`. The dev/CI target interpreter remains
3.13 (`.python-version`), where the 100%-coverage gate runs.
`standards/tooling.md` reads "3.11 minimum, 3.13 target".

### 2. Tooling checks the floor, not the target

`ruff target-version = "py311"` and `ty python-version = "3.11"` — both
settings mean *minimum supported*, so the toolchain structurally
rejects floor-breaking syntax and stdlib use (this gate is how the
`glob.translate` dependency was caught). The two `dialects.py` generics
are spelled with `TypeVar` until the floor reaches 3.12.

### 3. CI tests every floor it claims

The test matrix runs 3.11, 3.12, 3.13, and 3.14. An untested floor is
fictional. Coverage stays pinned to the 3.13 leg, where the stdlib
parity test (decision 4) runs.

### 4. The glob translation vehicle is in-house; ADR 032 semantics unchanged

ADR 032's compile chokepoint is unchanged in meaning but no longer
compiled through stdlib `glob.translate` (3.13-only): `_translate` in
`pattern_matching/glob.py` implements the same contract for the one
call shape vfs uses, byte-identical to the stdlib over the parity
corpus (`TestTranslateParity`, running wherever the stdlib function
exists). This also makes pattern semantics interpreter-independent —
previously they were implicitly "whatever the running Python's
`glob.translate` does". Swapping back is one import and two call
sites, with the parity test as proof.

### 5. Named reversal triggers

Raise the floor to 3.12 (and optionally restore the stdlib translate
path at 3.13+) when the first of these lands:

- CPython 3.11 EOL: **2027-10-31**.
- AWS Glue's current versions move past 3.11.
- Databricks 15.4 LTS end of support: **2027-08-19**.
- vfs needs a numpy ≥2.5 capability (the 2.5.x line is 3.12-only).
- The parity/backport maintenance tax exceeds its worth in practice.

## Rejected alternatives

- **3.10+** — matches the agent-ecosystem peers' floor, but the memo's
  evidence is one-sided: `uv` finds no resolution (numpy ≥2.4.2 needs
  3.11), 130 ty diagnostics spanning public contracts
  (`ExceptionGroup` fan-out, `StrEnum` error vocabulary,
  `assert_never`, `datetime.UTC`), `re._parser` absent on 3.10, two new
  backport dependencies — for an interpreter upstream stops patching
  ~2.5 months after this decision.
- **3.12+** — SPEC 0-aligned and already proven, but it excludes all
  current Glue versions, DBR 14.3/15.4 LTS, and ~33–37% of live
  traffic; the only code it simplifies is the two generic signatures.
- **Version-forked translation** (stdlib `glob.translate` on 3.13+,
  in-house below) — rejected regardless of floor: one pattern language
  with two compilers means glob results depend on the interpreter, the
  drift ADR 032's chokepoint exists to prevent.
