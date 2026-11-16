# vfs cannot honestly claim 100% certainty, because no tool proves its SQL and every proof trusts its own statement; what it can claim is a proved rights model tested against all five engines, Kani-checked Rust kernels, and a published claim-by-claim account of how hard it tried to break itself, while the seals within reach say who built the wheel and how the project is run, never what the code does

On 2026-11-12 Clay asked: "can you research code verifiability? I would like to be able to state, with 100% certainty, that vfs does what it says it does. What does that actually look like? What tools could I use and what projects should I research? As well, how could I get a seal to show, you can trust this project." Four researchers worked in parallel. Each was a fresh agent with no knowledge of the coordinator's reasoning, and each had a 45-minute box. Their four questions were: what can be proven and with what tools; what evidence short of proof the most trusted software publishes; what seals exist and what each one attests; and what vfs claims about itself today and what pins each claim. All four finished inside the box, in 19, 25, 19 and 23 minutes. The brief, the four studies and their experiments are under [the studies folder](studies/2026-11-12-how-far-vfs-can-prove-it-does-what-it-says/). There is no intention: this memo answers a direct question from the owner. It commits to nothing. The specs that follow decide.

Labels: EXECUTED means a command ran in this study, run by a researcher or by the coordinator, and the claim reports its output. READ means the claim was read in a page or file, or in one of the four studies, each of which cites its own sources by URL and read date or by clone path and commit. INFERRED means this memo's own reasoning from the two.

## Sources

The four studies, each with its own `## Sources`:

- [01, what can be proven and with what](studies/2026-11-12-how-far-vfs-can-prove-it-does-what-it-says/01-what-can-be-proven-and-with-what.md). It covers the Kani, Verus, Creusot, Prusti, Aeneas, Flux, CrossHair, deal, Nagini, TLA+, Apalache, Quint, P, Alloy and Lean documentation and release metadata, the seL4, CompCert, ShardStore and Cedar publications, the `cedar` clone at `4e8231e3` (Apache-2.0), and the `cedar-spec` clone at `86da7cb1` (Apache-2.0, shallow-cloned for that study).
- [02, evidence short of proof](studies/2026-11-12-how-far-vfs-can-prove-it-does-what-it-says/02-evidence-short-of-proof.md). It covers sqlite.org/testing.html, the FoundationDB, TigerBeetle, Antithesis, Elle, Jepsen, Csmith, SQLancer, SQLsmith, mutmut, cargo-mutants, Atheris, OSS-Fuzz, ClusterFuzzLite, Hypothesis, proptest, coverage.py and cargo-llvm-cov pages, the Just et al. 2014 and Petrović et al. 2021 papers, the `sqlite` clone at `3d17c3f9` (public domain) and the `turso` clone at `80ead541` (MIT).
- [03, seals and what each attests](studies/2026-11-12-how-far-vfs-can-prove-it-does-what-it-says/03-seals-and-what-each-attests.md). It covers SLSA v1.1 and v1.2, the GitHub artifact attestation documentation, the PyPI attestation documentation and PEP 740, Sigstore's security model, reproducible-builds.org, maturin's SBOM support, cargo-vet, cargo-crev, OSS-Fuzz admission, the OpenSSF Best Practices criteria at every level, the Scorecard checks and source, Regulation (EU) 2024/2847, the AICPA SOC 2 page, NIST's CMVP pages, OSTIF, Trail of Bits and Cure53 reports, and PyPI's and GitHub's public APIs. No clone was used.
- [04, what vfs claims and what pins each claim](studies/2026-11-12-how-far-vfs-can-prove-it-does-what-it-says/04-what-vfs-claims-and-what-pins-each-claim.md). It covers the vfs tree alone.

vfs at `3ea2465e` on `main`, with the working tree's uncommitted changes as they stood on 2026-11-12. The executed experiments:

- Study 01 ran Kani 0.68.0, CrossHair 0.0.113 and deal 4.24.6 on toys shaped like vfs functions.
- Study 02 ran mutmut 3.8.1, cargo-mutants 27.1.0, cargo-fuzz and Hypothesis 6.170.15 on a three-function toy in Python and Rust, plus one branch-coverage run of the whole vfs suite.
- Study 03 ran OpenSSF Scorecard v5.6.0 locally, verified a PEP 740 attestation, built the vfs wheel twice to compare bytes, and split the lockfile audit by audience.
- Study 04 ran four Hypothesis and fixture experiments against vfs itself.
- The coordinator reproduced study 04's broken identity law at the command line.

## 1. The answer in one paragraph

"100% certainty that vfs does what it says" cannot be stated honestly, by vfs or by anyone. Three things are always trusted and never proved: the statement of what the code should do, the tool that checks it, and whatever sits between the checked thing and the shipped thing. For vfs that third gap is the widest, because its central claim, that every call is judged against row-level rights, is carried out partly by SQL that Postgres, SQL Server, Oracle, MariaDB and SQLite evaluate, and no verifier reaches inside a SQL engine (READ, study 01). What vfs can honestly reach is the strongest sentence any comparable project makes. It is the sentence Cedar, AWS's authorization language, makes about itself: "the rules are proved, and the shipped implementation is tested against the proved rules." For vfs that means three things. First, a small Lean model of the grant rules with machine-checked theorems such as "deny by default" and "a rule on `/a` never governs `/a-b`". Second, the existing random-world parity tests, run with fresh generated inputs on every engine, comparing the real SQL with that model. Third, Kani bounded proofs that the Rust kernels never panic or overflow. Around that core sits a published, counted account of how hard the project tries to break itself, claim by claim. That account is the honest "seal" for behaviour, because no badge attests behaviour (READ, study 03). The badges and signatures vfs can carry attest something else: who built the wheel and how (PEP 740 attestations and SLSA provenance, each one workflow step away), and how the project is run (Scorecard, which gives vfs 3.2 of 10 today, and the OpenSSF Best Practices badge, whose passing level is within reach for a solo maintainer and whose gold level cannot be reached by one) (EXECUTED and READ, study 03). The research also found that vfs's evidence today is weaker than "100% coverage" suggests:

- The coverage gate measures lines only (READ, study 04).
- About 1% of branches are partial (EXECUTED, study 02).
- The 117 Rust tests run in no gate (EXECUTED, study 04).
- No test generates fresh inputs (EXECUTED, studies 02 and 04).
- The first generated test anyone wrote found a broken algebraic law in about nine seconds (EXECUTED, study 04, reproduced by the coordinator).

## 2. What "certainty" can mean, as a ladder (READ and INFERRED)

The four studies grade evidence on one ladder. Each rung is a stronger sentence a stranger can be told, and each rung still trusts something.

| Rung | The sentence | What it trusts | Where vfs stands |
|---|---|---|---|
| Stated | "The docstring says so." | The author | Host-access isolation, the four-question order, the Rust tests staying green (study 04, C8, C15, C16) |
| Linted | "A check refuses the shape that would break it." | That the shape is the claim | The import ladder, the adapter's isolation (C18) |
| Chosen examples | "These inputs give these answers on five engines." | That the examples are the hard cases | Most claims, including batch-size bounds and unknown dialects (C5, C6) |
| Generated inputs | "No counterexample among N generated cases, shrunk on failure." | The generator's reach | Partly reached: 33 fixed-seed generators, no shrinking, the same inputs every run (C3, C7, C9) |
| Mutation-checked | "Every planted bug of these shapes was caught." | The mutation operators | A hand ledger of 84 rows, replayed during review campaigns |
| Bounded proof | "For every input up to size N, it holds." | The checker, the bound | Not yet |
| Proof against a model | "For every input, the model satisfies these theorems, and the code agrees with the model on every generated case." | The theorems mean what users mean; the generator's reach | Not yet: the Cedar pattern |
| End-to-end proof | "The binary satisfies the specification." | The specification, the hardware | Out of reach. seL4 spent about 25 person-years on 8,700 lines of C; vfs's Python alone is about four times that (READ, study 01) |

The honest target for vfs's central claim is the second rung from the top. The honest target for everything else is "generated inputs" plus "mutation-checked". Each rung is worth something only if the project publishes what it trusted. INFERRED.

## 3. Proofs: what reaches vfs and what does not (READ and EXECUTED, study 01)

The Rust kernels can be proved, but the binding cannot. Kani, a bounded model checker for Rust, proved a fixed midpoint correct for all 2^64 input pairs in 0.02 s and refuted the overflowing version in 0.02 s. A ten-line posting-list intersection that allocates a `Vec` took 153 s and 13.5 GB of memory, and only for two-element inputs. So Kani fits arithmetic, indexing and the two `unsafe` `align_to` views in `python.rs`, over small fixed-size inputs. It does not fit whole heap-heavy kernels (EXECUTED). No Rust verifier can follow a `#[pyfunction]` into libpython, so a harness must target the pure kernel behind each binding (INFERRED). Verus and Creusot prove full functional correctness, but they mean rewriting a kernel in their dialect or annotating it heavily. Prusti has not released since August 2023 (READ).

Python can be searched, not proved. CrossHair found the sibling-prefix bug class (a rule on `/a` also governing `/a-b`) in about 36 s. On the correct function it printed "Not confirmed", which means no bug found and no proof either. Its contract also restated the implementation, so even a proof would have proved a tautology (EXECUTED). Nagini proves things, but only about a statically typed subset that excludes async SQLAlchemy code, pydantic and the native extension (READ).

SQL cannot be proved, only tested. A proof about the clauses `rights.py` compiles would need a trusted formal semantics of five SQL dialects, including their NULL handling, collation and `LIKE` escaping. No such tool exists that a library could gate on (INFERRED). The bridge Cedar uses for its own Rust is the one vfs can use for its SQL: differential random testing against a proved model.

Cedar is the case to copy. Its Lean specification is 2,239 lines, with about 97,000 lines of proof, 1,693 theorems and no `sorry` (an unfinished proof) anywhere. Its authorization theorems are `forbid_trumps_permit`, `default_deny`, `allowed_only_if_explicitly_permitted` and `order_and_dup_independent` (EXECUTED and READ). Nothing proves Cedar's Rust. Instead, `cedar-drt` runs 18 differential targets and about 30 property targets that compare the Rust with the compiled Lean model. The proofs found 4 bugs. The differential and property testing found 21 (READ). Its largest single proof took 18 person-days (READ). vfs's grant semantics fit in five bullet points in the 93-line oracle `tests/support/oracles/grants.py`, and `tests/storage/database/test_rights.py` already plays Cedar's differential role on SQLite (READ). So the missing half is a Lean model of perhaps a few hundred lines, plus the same random worlds run on every engine leg (INFERRED).

Design models catch what no code-level tool sees. TLA+ with Apalache, Quint and P check interleavings in a model of the design. They fit the write gate under concurrent writers and the fifteen-minute partial index pass with its daily fold. They prove nothing about `base.py` itself; the link to the code is a trace or a test (READ and INFERRED).

## 4. Evidence short of proof: what the trusted projects publish (READ and EXECUTED, study 02)

SQLite, FoundationDB, TigerBeetle and Turso do not claim correctness. They publish counts of effort:

- SQLite has about 590 times as much test code as library code, 100% MC/DC coverage of the core, fault injection at every allocation and I/O call, and 7.2 million queries compared against four other engines (READ). MC/DC means each condition in each decision was shown by a test to change the outcome on its own.
- FoundationDB and TigerBeetle run deterministic simulation: the whole system on one seeded clock and scheduler, with faults injected and every failure replayable.
- Turso, the closest relative to vfs, layers a shrinking simulator, swarm runs, Elle, SQLancer, Antithesis and a differential oracle against SQLite, all in CI (READ, the `turso` clone).

The toy experiment shows why coverage is the weakest of these measures. A three-function toy sat at 100% line and branch coverage, yet its permission check could be replaced with `return True` and all five example tests still passed (EXECUTED). cargo-mutants generated that "always allow" mutant and reported it missed. mutmut never generated it, so a mutation score is a claim about the tool's operators, not the code (EXECUTED). Three Hypothesis properties killed it and cut mutmut's survivors from 6 to 2, and both of the 2 were equivalent mutants (EXECUTED). A differential fuzz target found a planted prefix bug in about 780 runs, then ran 6.9 million inputs on the correct code with nothing found. Nothing found in what was tried is what a pass is worth (EXECUTED).

vfs's own 100% is line coverage, and its branch coverage is about 99%. With branch measurement on, which needs the C tracer and greenlet concurrency on Python 3.13 because the `sysmon` core cannot measure branches before 3.14, the suite covered every line but left 40 of 4,296 branches partial. Three are in `rights.py`, among them the group walk reaching `MAX_GROUP_DEPTH`, which no test drives (EXECUTED). MC/DC is not reachable for Rust today, because rustc removed its instrumentation in 2025 (READ).

## 5. What vfs claims and what pins each claim (READ and EXECUTED, study 04)

Study 04 lists 22 claims a stranger would rely on, and grades the pin on each one. A pin is the test, lint or gate that would fail if the claim stopped being true. The permission claims have the best pins in the tree. The read-only gate is enumerated over every mutating op and asserts the child storage saw no call at all (READ). Even so, no claim outside a few closed vocabularies is proven for every input. Four experiments raised pins and found the following:

- **The rights resolver held.** 20,000 freshly drawn Hypothesis worlds agreed with the oracle, against the suite's 400 from one seed (EXECUTED).
- **The batch-size promise held.** With SQLite's bind budget squeezed to 999, the widest statement across seven verbs carried 982 binds at 100, 1,000 and 5,000 files. The statement count grew with the batch; the widest statement did not (EXECUTED). Nothing pins this on every statement today. One fixture in `tests/conftest.py` would.
- **Unknown dialects need one more stated fact.** The conformance contract had never run on the `GENERIC` floor. Run there, the core verbs passed and `search` was withheld (308 passed, 36 skipped). The one failure traced to a fact no profile field states: `engine.py` installs pysqlite's transaction fix only when `profile.name == "sqlite"`. An unknown driver with the same flaw would lose batch atomicity silently (EXECUTED and READ).
- **The `Result` identity law is false.** `Result() | a` deduplicates `a`'s errors and `a | Result()` does not, because `_combined_errors` in `src/vfs/results/envelope.py` drops repeats only from the right-hand side (EXECUTED by Hypothesis in about nine seconds; reproduced by the coordinator: with two equal errors, `a | Result()` held 2 and `Result() | a` held 1). The suite's identity test passes because its one example holds a single error (READ).

Study 04 also found claims held by nothing at all:

- **The Rust tests.** The crate's 117 `#[test]` functions run in no step of `scripts/ci.sh` or any workflow. They pass when run by hand (EXECUTED).
- **Host access.** "The kernel has no access to the host" is true by grep today and pinned by no lint (EXECUTED).
- **The new `documentation/` folder.** It sits outside the Sybil docs gate. Its tutorial calls `fs.cli("ls")`, which does not exist (EXECUTED).

Smaller drift:

- The README's test count is stale: it says 4,564 and 6,449 are collected (EXECUTED).
- The overview's "Is the caller identified?" contradicts the README's note that anonymous callers may read and write on a fresh store (READ).
- The engine-leg workflow does not start for a change confined to the router or the Rust crate (READ).

## 6. Seals: what each one attests (READ and EXECUTED, study 03)

Seals answer three different questions, and none of them answers the owner's.

| Kind | The question it answers | Seals | vfs today |
|---|---|---|---|
| Built and delivered | Did these bytes come from that source, through that pipeline? | PyPI Trusted Publishing, PEP 740 attestations, GitHub artifact attestations and SLSA build levels, reproducible builds, an SBOM (an inventory) | Trusted Publishing is done. There are no attestations: `uv publish` uploads them but does not create them, and PyPI's provenance API returns 404 for the one release. The SBOM is already embedded by maturin. The compiled engine rebuilds byte-identically from two paths; the wheel differs only by an absolute path in the SBOM |
| How the project is run | Does the project follow good practice? | OpenSSF Best Practices badge, OpenSSF Scorecard, cargo-vet, OSS-Fuzz membership | Scorecard 3.2 of 10 locally. No badge registered. OSS-Fuzz not eligible before there is a user base |
| What the code does | Does it behave as claimed? | None of the badges. A security audit (OSTIF quotes $30,000 to $200,000) is a time-boxed search of one commit that states it is not exhaustive | None |

The verification was real. A PEP 740 attestation passed against the right repository and failed by name against a wrong one (EXECUTED). polars, orjson and rpds-py, maturin-built Rust-extension wheels like vfs's, already carry PEP 740 attestations (EXECUTED).

Scorecard's zeros are small to fix. The workflows lack `permissions:` blocks, actions are pinned by tag rather than SHA, and there is no Dependabot, no `SECURITY.md` and no CodeQL. Its Fuzzing check counts Atheris and cargo-fuzz but not Hypothesis (EXECUTED and READ). The 126 known vulnerabilities sit only on pins for the optional extras and the dev group; the core runtime dependencies are clean (EXECUTED).

The badge levels split on people. The OpenSSF badge's passing level needs no second person. Silver's `access_continuity` does. Gold's `bus_factor`, `contributors_unassociated` and `two_person_review` cannot be met solo by construction. Only curl and the Linux kernel hold gold among the projects checked, and pydantic, cryptography, SQLAlchemy and ruff hold no badge at all (READ).

The organisational frames don't attach to a library:

- SOC 2 and ISO 27001 attach to organisations running services.
- FIPS 140-3 attaches to cryptographic modules. vfs is neither (READ).
- The EU Cyber Resilience Act places no duty on a free, non-monetised project by one natural person. A steward must be a legal person. The duties fall on the enterprise that ships vfs inside a product, and that enterprise's due diligence will ask for a `SECURITY.md`, an SBOM and verifiable provenance (READ).

## 7. Synthesis: what vfs could honestly claim, and the order to earn it (INFERRED)

This section is the coordinator's reasoning from sections 2 to 6. It recommends; the specs decide.

The one sentence worth earning is: **"vfs's rights rules are proved in Lean, its Rust kernels are proved free of panics and overflow for bounded inputs, every claim it makes is listed with the test that pins it and that test's grade, and every release is signed back to the commit that built it."** Each clause is true when its work is done, and each names what it trusts. "100% certainty" is not true and never will be. This sentence is the honest replacement for it.

Ranked by what each buys per unit of cost:

1. **Close the gaps where a stated claim has no pin.** Gate `cargo test -p vfs-core` in `scripts/ci.sh` and `test.yml`. Bring `documentation/**/*.md` under the Sybil gate. Lint the host-access imports. Fix the `_combined_errors` identity law and pin it. Each is a one-list or one-step change. These come first because a published account of claims cannot list a claim nothing checks.
2. **Generated inputs with shrinking.** Add Hypothesis to the dev group. Convert the 33 fixed-seed generators, starting with `test_grants.py`, `test_rights.py` and `test_result_laws.py`. Then build one stateful machine over the verbs (write, edit, delete, move, grant, read, ls, glob, grep) with the grant oracle as its model, run on SQLite in the inner loop and on every engine leg. That machine is the differential half of the Cedar pattern, and both studies 02 and 04 rank it first among new tests.
3. **Suite-wide universal pins.** Add a bind-width fixture on every statement the suite issues, add a generic-floor conformance class, and state the transaction-control fact the floor relies on as a declared profile field.
4. **The seals that cost one step.** Add PEP 740 attestations through `astral-sh/attest-action` before `uv publish`, GitHub build provenance in the wheel jobs (SLSA Build L2), and a `SECURITY.md`. Then do the Scorecard hygiene: `permissions:` blocks, SHA pins, Dependabot, CodeQL and the scorecard action publishing a score. Then register for the passing badge. Together these are an afternoon of work that tells a buyer who built the wheel and how the project behaves.
5. **The Lean model of the rights algebra.** Mount permissions and row grants, with theorems for default deny, weakest-member subject sets, prefix boundaries, subtree refusal and trash judged at its origin, compiled and fed the stateful machine's worlds. This is the step that turns "tested" into "proved, and tested against the proof" for the claim a stranger relies on most. It is ranked fifth only because steps 2 and 3 build the differential harness it needs.
6. **Bounded proofs and mutation for the engine.** Kani harnesses on the `align_to` views and the arithmetic in `postings.rs`, `chunk.rs` and `vectors.rs`. cargo-mutants and mutmut on the functions each change touches, with the hand ledger kept as the curated set. cargo-fuzz targets on the parsing kernels through ClusterFuzzLite, which also scores on Scorecard.
7. **Stronger coverage measures.** Branch coverage on and gated, closing the 40 partial branches, with the `\.\.\.` exclusion narrowed as the placeholder memo on it proposes. Fault-injection tests that fail the Nth statement of a chunked 10,000-file batch and assert whole-or-classified.
8. **Later, and only with cause.** Quint or TLA+ models of the write gate and the index fold, written beside their specs. Elle histories, once vfs states what each verb promises under concurrency. An independent audit funded through OSTIF, Alpha-Omega or the Sovereign Tech Agency, once the rights and SQL-building paths stop moving. Antithesis when vfs runs at a customer. Silver and gold badges when there is a second maintainer.

Not recommended: Nagini, whose subset excludes vfs's control plane; Prusti, with no release since 2023; seL4-scale end-to-end proof; and SOC 2, ISO 27001 or FIPS 140-3, which do not attach to a library (READ, studies 01 and 03).

**The seal the owner asked for is the claims page itself.** No badge attests behaviour. The nearest honest thing is a generated, published page listing every claim vfs makes, the pin that holds it, the pin's grade on the ladder in section 2, and the counts behind it: worlds generated, engines run, mutants killed, theorems proved. Beside it go the signed provenance and the Scorecard badge for the build and the practice. That page is what OpenSSF silver calls an `assurance_case` (READ, study 03). It is also what SQLite, TigerBeetle and Cedar actually show strangers: not a percentage, but an account of what was tried that a stranger can check (READ, study 02).

## What this memo does not settle

- **The Lean model's cost for vfs.** It rests on Cedar's published figures, not a trial. The experiment: write the five grant rules and two theorems in Lean and measure the time.
- **Kani's reach over the real kernels inside a CI budget.** The experiment: one harness on each of `postings.rs` decode and the `align_to` views, timed on a CI runner.
- **mutmut on vfs's async, xdist-parallel suite.** Whether its forked children work there, and how many mutants survive in `rights.py` and `membership.py`, are unmeasured. The experiment: one mutmut run scoped to those two modules.
- **Whether any verb can return two value-equal errors in one envelope.** This decides whether the identity-law bug is reachable from the public verbs or only from a hand-built `Result`. The experiment: a Hypothesis search over verb calls that asserts no duplicate errors.
- **Scorecard's checks that need GitHub's API.** Branch protection, code review, maintained and signed releases were not run, because that would query GitHub about the project. The experiment: the `ossf/scorecard-action` on the repository itself.
- **Reproducibility on other platforms.** It was shown on one macOS machine only. The experiment: two CI builds of one tag on the Linux runners, compared by hash with the SBOM path normalised.
- **The real-engine legs.** None was run in this research, so "green on five engines" is graded from the workflow, not from a run. The `db_test` skill runs them.

## One line

Certainty that vfs does what it says has to be earned claim by claim, not stamped on. The strongest honest claim is Cedar's: rights rules proved in Lean and the real SQL tested against them on every engine, Kani for the Rust kernels, and a published page of every claim with its pin and grade. The seals within reach only say who built the wheel and how the project is run, so they belong beside that page, not in place of it.
