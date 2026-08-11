# Python version floor: what 3.10+, 3.11+, and 3.12+ each cost and buy

- **Status**: research memo (commits us to nothing; feeds the version-floor
  ADR — the floor is currently an unrecorded scaffolding-commit default of
  3.13, with a working-tree change to 3.12 pending that ADR)
- **Date**: 2026-08-11
- **Owner**: Clay Gendron
- **Question**: vfs's `requires-python` floor has never been a recorded
  decision — `>=3.13` landed in the scaffolding commit (`4730a04`,
  2026-02-06) before any code existed. A teaching-session question about
  the `re._parser` import surfaced the drift between `pyproject.toml`
  (3.13) and `standards/tooling.md` ("3.12 minimum, 3.13 target"), and an
  audit found exactly one 3.13-only dependency (`glob.translate`), now
  replaced by an in-house translator with a stdlib parity pin. Which floor
  should vfs declare: 3.10+, 3.11+, or 3.12+?
- **Evidence gathered**: three executed legs, none touching the live tree.
  (1) **Code**: `ty` sweeps of `src/`+`tests/` at `python-version` 3.10,
  3.11, and 3.12; grep sweeps for version-gated stdlib; a scratch copy of
  the working tree (`scratchpad/floor311`) carrying the two required
  edits, run green under a real CPython 3.11.14 — full suite, `ruff`,
  `ty`. (2) **Dependencies**: `uv lock` resolution attempts at each floor;
  PyPI `requires_python` for latest releases of every core dependency.
  (3) **Ecosystem**: a web sweep (all sources accessed 2026-08-11) of
  CPython lifecycles, LTS distro Pythons, Databricks Runtime and AWS
  Lambda/Glue runtimes, pypistats download shares, SPEC 0, and
  agent-ecosystem peer floors.

---

## 1. What the code itself requires (executed)

### 3.12 floor — the working-tree baseline

Proven green 2026-08-10/11: full suite on 3.13 (2,180 passed) and on a
real 3.12.11 (2,179 passed + the stdlib-parity test skipping by design),
`ruff`/`ty` clean, 100% coverage. The one 3.13-only dependency the audit
found — stdlib `glob.translate` inside the ADR 032 compile chokepoint —
is replaced by an in-house `_translate` in `pattern_matching/glob.py`,
byte-identical to the stdlib's output over a 29-pattern parity corpus
(`TestTranslateParity`, runs wherever the stdlib function exists).

### 3.11 floor — two lines of syntax, then green

`ty` at `python-version = "3.11"` reports **exactly 2 diagnostics**, both
PEP 695 type-parameter syntax (3.12-only) in
`storage/backends/database/dialects.py`: `chunked[T]` (:301) and
`statement_budget[R]` (:323). Rewritten to pre-695 `TypeVar` form in the
scratch copy, the whole project is floor-clean:

- `uv lock` at `>=3.11` resolves, adding only the `tomli` backport
  (coverage.py's TOML reader on 3.11).
- `ruff` (target `py311`) and `ty` (3.11): zero findings.
- **Full suite under CPython 3.11.14: 2,179 passed, 789 skipped** — skip
  count identical to the 3.12 leg (the one extra skip everywhere is the
  stdlib-parity test, which needs 3.13's `glob.translate` to compare
  against; the translator itself is exercised by every other test).

The `re._parser`/`re._constants` binding in `models/code_grams.py` is
3.11-safe: CPython renamed the sre modules in 3.11.

### 3.10 floor — a structural rewrite

`ty` at 3.10 reports **130 diagnostics**. The tree depends on four 3.11
stdlib families, none cosmetic:

| Construct (3.11+) | Where | Rewrite cost |
|---|---|---|
| `ExceptionGroup` | `exceptions.py` fan-out contract, `base.py`, dispatch tests | No 3.10 equivalent without the `exceptiongroup` backport dep; the raise/except semantics are a public contract |
| `enum.StrEnum` | `results/kinds.py` — `VFSErrorKind`, `Severity`, `RetryClass` | The entire error vocabulary; the `str`-mixin replacement changes `format()` behavior, so every rendering surface needs re-verification |
| `datetime.UTC` | five `src/` modules, eight test modules | Mechanical (`timezone.utc`) but wide |
| `typing.assert_never` | `base.py` router exhaustiveness gate | Needs `typing_extensions` (a new dependency) |

Plus two blockers outside `ty`'s view: `re._parser` does not exist on
3.10 (the sre rename is 3.11), so `code_grams.py` would need a
version-conditional import; and dependency resolution **fails outright**
(§2).

## 2. What the dependencies allow (executed + PyPI floors)

`uv lock` at `>=3.10`: **no solution** — `numpy>=2.4.2` declares
`Python>=3.11`. Lifting it would mean pinning numpy back below 2.1,
against the current 2.5.x line.

Latest-release `requires_python` for the core dependencies (PyPI,
2026-08-11): numpy 2.5.2 **>=3.12**; sqlalchemy 2.0.52 >=3.7; pydantic
2.13.4 >=3.9; tree-sitter 0.26.0 >=3.10; tiktoken 0.13.0 >=3.9;
rustworkx 0.18.1 >=3.10.

The numpy shape matters for the 3.11 option: our `numpy>=2.4.2` pin
resolves on 3.11 (the 2.4.x line supports it), but the 2.5+ line is
3.12-only under SPEC 0. vfs uses numpy for posting-list decode —
`frombuffer`, masks, `cumsum` — nothing that needs a new numpy, so a
3.11 floor holds until vfs *wants* numpy ≥2.5, a named reversal trigger.

## 3. What the ecosystem runs (web sweep, all accessed 2026-08-11)

**CPython lifecycle** (devguide.python.org/versions, endoflife.date):
3.10 EOL **2026-10-31 (~2.5 months away)**; 3.11 EOL 2027-10-31; 3.12
EOL 2028-10-31; 3.13 EOL 2029-10-31.

**Where each floor's users live**:

| Environment | Python | Supported until |
|---|---|---|
| Ubuntu 22.04 LTS | 3.10 | 2027-04 (ESM 2032) |
| Ubuntu 24.04 LTS | 3.12 | 2029-05 |
| Ubuntu 26.04 LTS | 3.14 | 2031-04 |
| Debian 12 / 13 | 3.11 / 3.13 | LTS 2028-06 / 2030-06 |
| RHEL 9 / 10 | 3.9 default, 3.11/3.12/3.14 streams / 3.12 default | 2027-05 / 2030-05 |
| Databricks 14.3 LTS | **3.10** | 2027-02 |
| Databricks 15.4 LTS | **3.11** | 2027-08 |
| Databricks 16.4 / 17.3 / 18 LTS | 3.12 | 2028-05 / 2028-10 / 2029-06 |
| AWS Lambda python3.10 | 3.10 | deprecated **2026-10-31** |
| AWS Lambda python3.11 | 3.11 | deprecated 2027-06 |
| AWS Glue 4.0 | **3.10** | still supported |
| AWS Glue 5.0 / **5.1 (current)** | **3.11** | current |

**Download share** (pypistats, 30 days to 2026-08-10, sqlalchemy and
pydantic as proxies): 3.12 ≈ 36–39%, 3.11 ≈ 20–24%, 3.13 ≈ 12–14%,
3.10 ≈ 12–13%, 3.14 ≈ 7%. **A 3.12 floor walks away from roughly a
third of live traffic; a 3.11 floor from ~13%.**

**Policy signals, pulling opposite directions**: SPEC 0 (scientific
stack) says drop 3.11 in Q4 2025 — numpy already has. The agent
ecosystem vfs actually lives in — langchain-core 1.5.4, langgraph
1.2.11, mcp 2.0.0, fastmcp 3.4.7, all released within weeks of the
sweep — sits uniformly at **>=3.10**.

Unconfirmed facts, flagged rather than guessed: DBR 19's Python;
per-stream retirement dates of RHEL Python app streams.

## 4. Recurring maintenance cost per floor

CI (`test.yml`) currently runs 3.13 + 3.14 with the 100%-coverage gate
on 3.13 (where the stdlib-parity test runs — the gate holds). An honest
floor adds its version to the matrix — an untested floor is fictional:

- **3.12+**: one extra leg (~35 s local; already proven).
- **3.11+**: two extra legs; `tomli` in the dev lock; the two `TypeVar`
  spellings until the floor rises (ruff `py311` will not rewrite them).
- **3.10+**: three extra legs, a backport dependency (`exceptiongroup`,
  `typing_extensions`), a conditional sre import, the StrEnum rendering
  re-verification — recurring, not one-time, and for an interpreter
  upstream stops patching in October.

## 5. Synthesis

- **3.10+** buys the last ~13% of traffic, DBR 14.3 LTS, Glue 4.0, and
  Ubuntu 22.04 — for ~3 months of upstream security support, a failed
  dependency resolution, a 130-diagnostic rewrite of load-bearing
  contracts, and two new backport dependencies. The evidence is
  one-sided: not viable.
- **3.11+** costs two `TypeVar` spellings, one CI leg beyond 3.12's, and
  a numpy line held at 2.4.x — executed and green. It buys every current
  AWS Glue version, DBR 15.4 LTS, Debian 12, Lambda into 2027, ~20–24%
  of live traffic, and floor-parity with every agent-ecosystem peer.
- **3.12+** aligns with SPEC 0 and current numpy and is already proven
  in the working tree — but excludes all current Glue versions and
  ~33–37% of live traffic, for no code simplification beyond the two
  generic signatures.

Natural reversal triggers either way: 3.11's EOL (2027-10-31), Glue
moving past 3.11, DBR 15.4 LTS end (2027-08), or vfs needing numpy
≥2.5. Recording whichever floor is chosen with these triggers named
turns the next floor raise from a debate into a scheduled event.
