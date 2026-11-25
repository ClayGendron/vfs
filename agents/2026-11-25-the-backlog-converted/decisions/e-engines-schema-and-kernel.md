# Decisions verified: engine tiers, schema lifecycle, creation attribution, preconditions

Scope: rows D3, D18, D19, D33, D36, D37 and D50 of `context/standards/roadmap.md` section 16, at HEAD 0ed462f on 2026-11-25. Each section gives the lean, the verification word, the decision a spec would carry, the reason, the precedent and the specs affected. Labels: EXECUTED (a command ran here), READ (path:line), INFERRED (reasoning).

## D3. MariaDB is served as a second-tier engine, neither first tier nor dropped

Lean: "Second tier" (READ, context/standards/roadmap.md:1075), defined there as "served, in CI, no ANN, per-row updates documented".

Verification: HOLDS-AMENDED.

Decision text: MariaDB 11.8+ is a supported, second-tier engine at 0.1.0: every verb is served on it, its leg runs the conformance contract in CI and is one of the four legs the final bar requires, so a red MariaDB leg blocks a release; what second tier withholds is performance parity, not correctness: guarded batch updates stay one statement per row (the count recorded by story D4 criterion 4), vector search runs as an exact scan with no ANN index provisioned, and set-based updates (spec 080) are a 0.2 story.

Reason: the tree already serves MariaDB as a tuned profile (READ, src/vfs/storage/backends/database/dialects.py:594-629) and AGENTS.md lists it among the dialects with a native distance function (READ, AGENTS.md:62), so dropping it would delete working, pinned code (READ, tests/storage/database/test_dialects.py:174) and the only real-engine exercise of `guard_miss="redrive"` (READ, context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/02-storage-engines-and-dialects.md:227). The reference deployment names Postgres, SQL Server and Oracle, not MariaDB (READ, AGENTS.md:87), so first-tier cost (spec 080 at gate b, every new builder tuned on a fifth engine) buys no deployment the filter names (INFERRED). The amendment pins what "second tier" means for a release; the row's wording leaves open whether a red leg blocks, and the archived release plumbing already counts four legs (READ, context/standards/roadmap.md:495-499).

Precedent: Python's PEP 11 platform tiers separate support commitment from CI presence, and its Tier 2 still blocks a release on failure (public standard, https://peps.python.org/pep-0011/; recalled, not fetched here). The per-row cost is measured, not assumed: the UNION ALL derived-table join is 3.8 to 4.1 times the per-row loop at 10,000 rows (READ, context/specifications/active/080-mysql-batch-update-statements/spec.md:3). The profile declares `vector_distance="ann"` but no ANN index is provisioned off Postgres (READ, src/vfs/storage/backends/database/backend.py:651), so "exact scan" is the honest matrix cell (READ, context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/02-storage-engines-and-dialects.md:146).

Cost at the reference deployment: none, since MariaDB is not one of its engines; a host that does choose it pays about 10,000 UPDATE round trips per 10,000-file overwrite batch, 100 batches a night, inside REPEATABLE READ (INFERRED from AGENTS.md:79 and spec 080:9).

Specs affected: 080 (tagged gate 0.2), 157 (MariaDB issues no schema statement), 171 (the matrix and the floor wording); roadmap stories D1, D4, D5.

## D18. The engine matrix names Oracle by its release floor and the CI image tag

Lean: "Name the floor 23.4+ and the image tag" (READ, context/standards/roadmap.md:1090).

Verification: HOLDS-AMENDED.

Decision text: The matrix names Oracle's floor as release 23.4 or later with `COMPATIBLE` at 23.4.0 or higher, lists the vendor names "23ai" and "26ai (release updates 23.26.x)" as names of that one line, and names the CI image as `gvenzl/oracle-free:23-slim` together with the release number the leg last reported, because the tag floats.

Reason: Oracle documents that the VECTOR type needs `COMPATIBLE` 23.4.0 or higher, and that 26ai replaced 23ai through the October 2025 release update with no upgrade (public, https://docs.oracle.com/en/database/oracle/oracle-database/26/nfcoa/vector-data-type.html and https://blogs.oracle.com/database/oracle-announces-oracle-ai-database-26ai; a web search ran here, EXECUTED). A marketing name alone is ambiguous across the rename, and a floating tag alone does not say what CI ran (INFERRED). The tree pins `gvenzl/oracle-free:23-slim` (READ, docker/compose.test.yml:110) and its docs say "23ai" (READ, docker/README.md:58, AGENTS.md:62). The fact-check audit could not confirm the image's banner string (READ, context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/11-review-fact-check.md:72).

Precedent: the release number as the floor is how the matrix states every other engine (MariaDB 11.6+ for snapshot isolation, READ, src/vfs/storage/backends/database/dialects.py:611; pgvector 0.8 for ANN, READ, src/vfs/storage/backends/database/backend.py:651). AGENTS.md's rule "read facts off the live Dialect object" (READ, AGENTS.md:61) favours the reported server version over a hardcoded name.

Found beside the row: the Oracle, MariaDB and SQL Server profiles declare no `vector_function` probe; only SQLite and Postgres do (READ, src/vfs/storage/backends/database/dialects.py:508-552, :597-657). A pre-23.4 Oracle therefore fails at DDL with no named fix rather than the classified first-touch refusal Postgres gives. Story D7 criterion 3 already names that refusal (READ, context/standards/roadmap.md:507); the conversion of the storage stories carries it, and this decision does not.

Specs affected: no numbered backlog spec carries the matrix; the spec cut for roadmap story D1, and story D7's how-to pages.

## D19. From 0.1.0b1 the schema guard is directional, classifies corruption apart, and keeps a migration registry

Lean: "Yes; yes": story D2 as written, and a corrupt version row as `vfs.unavailable.corrupt` (READ, context/standards/roadmap.md:1091).

Verification: HOLDS-AMENDED.

Decision text: From `0.1.0b1` a schema mismatch carries `data["direction"]` (`store_newer`, remedy "upgrade vfs"; `store_older`, remedy "run migrate or re-provision"); a meta row whose version is null, non-integer or below 1, and a database whose tables hold rows but no meta row, classify `vfs.unavailable.corrupt` (retry class never), never `schema_mismatch`; an empty meta table in an otherwise unprovisioned schema stays a first touch that provisions; a registry of `(from, to, statements)` exists and a `SCHEMA_FORMAT_VERSION` bump with no entry fails a unit test; the contract is recorded under `documentation/`, since ADR 020 was retired and cannot be amended.

Reason: story D2 criterion 2 calls "a meta table present with no row" corruption (READ, context/standards/roadmap.md:467), but first touch today provisions exactly that state: `create_all`, then the meta insert, with a savepoint for the designed race (READ, src/vfs/storage/backends/database/engine.py:676-686). On engines where DDL commits implicitly, a first touch interrupted between the two statements leaves that state, and the next first touch repairs it (INFERRED). Calling it corruption would strand a mount that today recovers by itself. The case that really is inconsistent, rows present and no meta row, is already refused with a plain `unavailable` (READ, src/vfs/storage/backends/database/engine.py:687-697; tests/storage/database/test_engine.py:251), and is the one to move to the new kind. Story D2 criterion 4 amends ADR 020; the ADRs were retired on 2026-10-30, so the record moves to the storage reference (INFERRED from the ground rules). The alpha release-notes sentence in story D2 (READ, context/standards/roadmap.md:465) no longer applies: no alpha release is cut (Decided 2026-11-15, READ, context/standards/roadmap.md:1073).

Precedent: the prior-art memo records that Postgres, JuiceFS and Oak all refuse rather than migrate silently, that Oak's errors are directional ("too old" against "too recent"), and that Oak classifies an impossible stored version (`<= 0`) as unrecoverable corruption apart from a window miss (READ, context/research/2026-07-21-prior-art-design-review-notes.md:23). Its line 19 records that public format numbers move only for shipped formats (READ, :19). `vfs.unavailable.schema` is already a never-retryable child of `unavailable` (READ, src/vfs/results/kinds.py:94, :279-284), and the integrity kind was decided as a child of the same family (Decided 2026-11-15, READ, context/standards/roadmap.md:1080), so a third child follows the shape the tree already uses. The registry follows the Alembic and Django migration tables (public practice, recalled, not fetched).

Cost at the reference deployment: the guard is one meta-row read per first touch. A registry entry is a per-corpus operation run once per upgrade, so its statements are held to the per-corpus and lock rules: bounded, interruptible, and never a table lock that stops reads (INFERRED from AGENTS.md's per-corpus and per-lock rules).

Specs affected: the spec cut for roadmap story D2; 157 (its refusals share the vocabulary); 179 (the fault model classifies the new kind).

## D33. The write preconditions and the guarded append (spec 174) land before the shell's pipe and programs (spec 167 slice C)

Lean: "Yes" (READ, context/standards/roadmap.md:1105).

Verification: HOLDS.

Decision text: Spec 174 lands before spec 167 slice C. The shell's `>>` is one `write(append=True)` call and its `touch` is one `write(content="", if_absent=True)` call from the first landing of `cli`. Slice C never ships the read-then-write `>>` or the `stat`-then-`write` `touch`.

Reason: spec 167 as drafted admits that its `>>` "can lose data" (READ, context/specifications/active/167-the-shell-pipeline-core/spec.md:130), and its `touch` is a `stat` then a `write` (READ, :104). Shipping either would ship a known data loss that the next spec then removes. Constitution Article 5 forbids silent clobbering (READ, context/standards/constitution.md:121). Spec 174 already states the order (READ, context/specifications/active/174-write-preconditions-and-the-guarded-append/spec.md:7), story F3 depends on K2 (READ, context/standards/roadmap.md:619), and 167's own rebase notes take 174's forms (READ, context/specifications/active/167-the-shell-pipeline-core/spec.md:239). Neither has landed: no `if_version` appears in `src/vfs` (EXECUTED, a grep returned 0 lines).

Precedent: the probe in spec 174 shows 20 concurrent read-then-write appends report success and leave 1 line, while the same 20 through `edit` keep 20 (READ, context/specifications/active/174-write-preconditions-and-the-guarded-append/spec.md:36). POSIX `write(2)` under `O_APPEND` moves the offset to the end of the file with no intervening modification, and `O_CREAT|O_EXCL` creates a file only if it is absent (public standard, POSIX.1-2017 `write` and `open`; recalled, not fetched). Those are the shell semantics `>>` and an atomic `touch` stand on.

Specs affected: 174, 167 (slice C), and 169 and 171, which spec 174 also precedes (READ, spec 174:7).

## D36. A file's creator is recorded in its history, as the attribution of version 1, not as a column on the entry row

Lean: "The version row" (READ, context/standards/roadmap.md:1108).

Verification: HOLDS-AMENDED.

Decision text: Creation attribution lives in history. Every version's attribution (actor, provenance, source identity, grant revision, subjects) names the authority that wrote that version's body. A create therefore records version 1's attribution at the create, under `anon` and `system` too. The replace-mint carries the replaced version's own author forward and never stamps the replacing authority onto the pre-image. No `created_by` column is added to the entry row.

Reason: the lean as written does not fit the landed mint. Today a create mints nothing, and a replace mints a row that holds the replaced body under the replaced version's number, with the attribution of the authority that replaced it (READ, src/vfs/storage/backends/database/versions.py:3-15). So row N carries body N and the author of N+1, and version 1's author is stored nowhere. Story K8 criterion 3 (READ, context/standards/roadmap.md:200) and spec 180's exact-row criterion, where `actor` equals the writer's actor (READ, context/specifications/active/180-history-pack-on-reindex-and-the-bounded-sweep/spec.md:491), can both be read as true only once attribution belongs to the body it produced (INFERRED). `owner_id` is not a substitute: it is empty under anonymous and multi-subject authorities and is whatever the payload declares under the system actor (READ, src/vfs/authority.py:216-227). A `created_by` column would duplicate one fact that history must hold anyway for every later version (INFERRED).

Precedent: git records each commit's author as the author of that commit's tree, and MediaWiki's revision row names the actor who wrote that revision's text. A file's first version names its creator in both, and neither keeps a creator column on the file (public practice, recalled, not fetched). POSIX keeps an owning uid and no creator (public standard, `stat`). The tree already keeps attribution on version rows only (READ, src/vfs/models/rows.py:536-566).

Cost at the reference deployment: one attribution row per create rides the write's existing bulk insert, at most one chunked statement per batch page; about 10,000,000 attribution rows as a one-time base and a few hundred thousand a day after, with no body duplicated if the live version's row holds attribution only and its body stays in the content table (INFERRED from AGENTS.md:79 and :92). Nothing reaches the rebuild path.

Specs affected: 180 (gains the mint-on-create rule and the attribution rule), 161 (its read side), 162 (the replace-mint it built); roadmap story K8.

## D37. At 0.1.0 a plan's apply is checked by a stat at apply time with a documented window, and no new precondition argument is added to every mutating verb

Lean: "Stat-at-apply at 0.1.0" (READ, context/standards/roadmap.md:1109); the full form is deferred to 0.2 (READ, :1047).

Verification: HOLDS-AMENDED.

Decision text: At 0.1.0, `write`, `edit`, `delete` and `move` take `if_version=` and, for a batch, `if_versions=` (for `move`, on the source). A plan's apply carries those versions on these verbs, and so does a session's stamp (K10). The other planned verbs (`mkdir`, `copy` without `replace=`, `restore`, `mkedge`, `rmedge`, `grant`, `revoke`, `posture`) are checked by one chunked `stat` at apply, the remaining race window is documented, and a precondition argument on those is 0.2.

Reason: the lean leaves three stories that contradict each other. Spec 174 puts `if_version` on `write` alone and lists it on `edit`, `delete` and `move` as out of scope (READ, context/specifications/active/174-write-preconditions-and-the-guarded-append/spec.md:370). Story H2 says the apply of `edit` carries `if_versions=` (READ, context/standards/roadmap.md:302). Story K10 has the session fill `if_version=` for writes, edits, moves and deletes, and criterion 4 has strict sessions need stamps on `delete` and `move` (READ, context/standards/roadmap.md:215, :219). A stamp on `delete` or `move` has no argument to travel in unless those verbs take one (INFERRED). The runtime cost is the same either way: one chunked select per `membership_budget` (READ, context/standards/roadmap.md:146, :302). So the remaining difference is build size, and AGENTS.md rules that size is not a reason to shrink a design (READ, AGENTS.md:45). The constitution lets a caller pass `if_version=X` on a write (READ, context/standards/constitution.md:75), and a documented window is still a declared conflict mode under Article 5 (READ, :121), so the stat form stays lawful for the verbs no caller guards.

Precedent: HTTP `If-Match` applies to state-changing methods including DELETE (public standard, RFC 9110 section 13.1.1). Google Cloud Storage takes `ifGenerationMatch` on delete and rewrite, Amazon S3 accepts conditional DeleteObject, and Kubernetes `DeleteOptions.preconditions` carries `resourceVersion` (public documentation, recalled, not fetched). Every one of these puts the precondition on path-addressed deletes and moves. None found for preconditions on grant or label changes; the stat form there rests on Article 5's declared-mode rule.

Cost at the reference deployment: no statement beyond the one chunked select a stat already costs, on the per-write multiplier of about 1,050,000 a day (INFERRED from AGENTS.md:92).

Specs affected: 174 (its scope widens to `edit`, `delete` and `move`), 177 (replay rows for the new preconditions), 181 (the frozen argument list), and the new specs for stories H2 and K10.

## D50. Through a session, a write to a path the session never read proceeds unguarded by default, and `strict=True` refuses it

Lean: "Proceed by default; `Session(strict=True)` refuses `vfs.invalid` naming the rule" (READ, context/standards/roadmap.md:1122).

Verification: HOLDS-AMENDED.

Decision text: By default a session writes an unstamped path unguarded, last writer wins, as the router does today. `fs.session(..., strict=True)` refuses, with `vfs.invalid` naming the read-before-write rule and with zero mutation statements, any `write`, `edit`, `delete` or `move` of a path that carries neither a stamp nor an explicit precondition. `if_absent=True` counts as an explicit precondition, so a strict session creates new files without reading them first. `copy` needs neither. Whether `serve()` opens its sessions strict is decided under D51.

Reason: both audiences share one session type, and AGENTS.md makes 10,000-file ETL batches a supported contract (READ, AGENTS.md:52-54). A refuse-by-default session would turn every first write of a pipeline into a refusal (INFERRED). An unguarded write is a declared last-writer-wins mode under Article 5 (READ, context/standards/constitution.md:121), and K10 keeps a direct router caller's behaviour unchanged (READ, context/standards/roadmap.md:215). The amendment fixes a gap: as written, strict refuses any path "never read", which would refuse a create of an absent path. A read to tell create from overwrite would cost a statement, and the guard promises none (READ, context/standards/roadmap.md:215, :220). Letting `if_absent=True` stand in for a stamp settles that case with no statement (INFERRED). Strict's `delete` and `move` rule needs those verbs to take a precondition, which D37 as amended gives them.

Precedent: coding harnesses enforce read-before-edit on existing files and let a new file be written unread; Claude Code's Edit tool refuses an unread existing file (public tool behaviour; named as precedent at READ, context/standards/roadmap.md:215). `O_CREAT|O_EXCL` is the POSIX form of a create that cannot clobber (public standard, POSIX.1-2017 `open`). `vfs.invalid` adds no kind to the closed taxonomy (READ, context/standards/constitution.md:84).

Cost at the reference deployment: none; the stamps come off results the session already returned, bounded by `SESSION_STAMPS` (READ, context/standards/roadmap.md:220).

Specs affected: the new spec for story K10; 148 (the session it extends); 171 (D51's per-principal table); 174 (the preconditions strict accepts).
