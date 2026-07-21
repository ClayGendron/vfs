# gbrain: architecture learnings and enterprise positioning for vfs

> Date: 2026-07-21
> Source: shallow clone of [garrytan/gbrain](https://github.com/garrytan/gbrain)
> at `~/Git/Repos/gbrain` (read-only reference checkout), studied via five
> parallel deep-dive passes (storage, MCP surface, retrieval, knowledge model,
> enterprise/PMF) plus direct reads of README, DESIGN, and architecture docs.
> Scope: what gbrain is, which of its mechanisms vfs should adopt, and whether
> vfs should replicate the product or position as infrastructure beneath it.
> Status: snapshot of gbrain at v0.43-era master, July 2026. File/line
> references are to that checkout and will drift.

## If only one sentence survives

gbrain is the strongest existence proof yet for vfs's thesis — a production
"brain layer" over Postgres serving agents via MCP, built by the CEO of YC and
pointed at YC's own "company brain" RFS — and it deliberately punts on exactly
the four things vfs is building (cross-dialect SQL, engine-enforced tenant
isolation, a durable DB system of record, one scoping chokepoint for agents
*and* pipelines), so the answer to "replicate or underpin?" is **underpin:
steal its mechanisms liberally, do not become it**.

---

## Part 1 — What gbrain is

An MIT-licensed TypeScript/Bun agent-memory system by Garry Tan (YC CEO), run
in production against his own data: ~147K pages, 24.5K people, 5.3K companies,
66 cron jobs. The pitch: not search but *synthesis* — "search gives you raw
pages, GBrain gives you the answer," with citations and explicit gap analysis
("here's what the brain doesn't know"). Two headline differentiators:

- **A self-wiring knowledge graph**: every page write extracts entity refs and
  creates typed edges (`works_at`, `invested_in`, `attended`, …) with zero LLM
  calls. Benchmarked at +31.4 points P@5 over its graph-disabled variant.
- **A 24/7 "dream cycle"**: cron-driven overnight enrichment — dedup, citation
  fixing, contradiction detection, fact consolidation, re-embedding.

Shape of the system:

- **Engines**: PGLite (Postgres 17 in WASM, embedded, zero-config, ~50K-page
  ceiling) and real Postgres/Supabase — both behind one `BrainEngine`
  interface (~37 methods). **There is no SQLite backend**; a planned one was
  abandoned specifically to avoid maintaining a second SQL dialect.
- **System of record**: a git repo of markdown files. The DB is an explicitly
  rebuildable derived index ("we do not back up the database — we rebuild it
  from the repo").
- **Two organizational axes**: a *brain* is a database (mountable, many per
  user); a *source* is a named repo inside a brain (every row carries
  `source_id`; slugs unique per source). Both axes resolve through identical
  layered precedence chains (flag → env → dotfile → longest-prefix path match
  → config default → fallback).
- **Agent surface**: ~102 operations in one contract-first registry projected
  into CLI, stdio MCP, and HTTP MCP (OAuth 2.1) simultaneously, plus 43
  markdown "skills" (prose instructions, never code) routed by frontmatter
  triggers.
- **Retrieval**: five-arm hybrid (chunk FTS, page-title FTS, pgvector HNSW,
  typed-edge relational fanout, image vectors) fused with RRF, then a stack of
  fail-open multiplicative boosts, cross-encoder rerank, and score-cliff
  autocut — with a continuous eval harness wired into CI as a hard gate.

A structural observation worth keeping in mind throughout: **gbrain and vfs
are mirror images.** gbrain treats files (git markdown) as the source of truth
and the database as a derived cache; vfs treats the database as the durable
substrate and the filesystem as the interface. Both converge on "database as
substrate, filesystem as namespace" — from opposite directions. Most of
gbrain's enterprise weaknesses (§3) trace directly to its choice of direction.

---

## Part 2 — Mechanisms worth learning from

Organized by vfs concern. "Adopt" means the idea transfers directly; "study"
means the principle transfers but the mechanism is Postgres- or
product-specific.

### 2.1 Storage and dialects

**The dialect counter-bet (study, and take seriously).** gbrain's single most
consequential storage decision was killing its SQLite engine and adopting
PGLite so that *both* engines speak literal Postgres — same `tsvector`, same
pgvector, same recursive CTEs. They concluded a second dialect (FTS5,
sqlite-vss) wasn't worth maintaining. vfs makes the opposite bet (SQLAlchemy
across Postgres/SQLite/Oracle/SQL Server), which is the harder and more
valuable position — but gbrain is a warning about the real cost: their
`BrainEngine` "abstraction" never actually had to reconcile dialects. Every
cross-dialect seam vfs owns (FTS, pagination, type casts, bind limits) is a
seam gbrain refused to pay for. That is both the moat and the bill.

**Embedded engines mask production bugs (adopt the discipline).** Their
JSONB double-encoding bug (#2339) produced silently-wrong rows on real
Postgres while **PGLite hid it** (it parses text→jsonb natively). Their
response: parity tests forced onto real Postgres, plus CI grep/AST guards
pinning the safe pattern. The vfs analog is exact — SQLite's generous limits
hide exactly the Oracle/SQL Server failures vfs designs against. Behavioral
parity tests against real engines for every write-builder pattern should be a
standing requirement, not an aspiration.

**One structured parameter instead of N binds (study).** Bulk writes pass the
entire batch as *one JSONB document* expanded server-side via
`jsonb_to_recordset`, dodging the 65,535-param cap and array-literal escaping
bugs in one move. Postgres-specific, but the principle — collapse per-row
binds into one engine-native structured value where the dialect supports it —
is a legitimate per-dialect fast path above vfs's portable `chunked()` floor.
Their sanitization policy is the subtle part worth copying: free-prose fields
get NUL/lone-surrogate scrubbed to U+FFFD, but **identity fields are
deliberately left unsanitized** so junk in a key errors the batch instead of
silently retargeting a row.

**The db-pacer (adopt the concept).** A composable backpressure primitive for
bulk writes sharing a pool with latency-sensitive work — vfs's two audiences
exactly. Three mechanisms: a counting-semaphore concurrency cap (bounds pooler
slots held), an EWMA latency signal fed from the work's *own* queries (never
an out-of-band probe), and cooperative jittered sleep between safe points.
Contracts: abort while waiting *throws* (a cancel can never fall through into
a DB call); the pacer itself fails open (a pacer bug must never kill a
backfill); single-process engines get a no-op pacer. A 10k-file ETL ingest
running beside agent read loops needs precisely this.

**Pooler-specific production lessons (adopt where applicable).**
- Advisory locks die under PgBouncer transaction pooling (session-scoped), so
  cross-process coordination uses a **plain row with a TTL** in a locks table
  — crashed holders auto-release on expiry, and it survives any pooler.
- Session GUCs (`statement_timeout` etc.) are delivered as **connection
  startup parameters**, because transaction-mode poolers strip session `SET`s.
- Port 6543 auto-disables prepared statements.
- Pool teardown is wrapped in a hard timeout so shutdown can't hang on a stuck
  pooler socket.

**The generation-clock war story (file away).** A per-row trigger bumping a
single counter row turned a 73K-row batch delete into 73K contended updates;
the fix was a statement-level trigger plus a sequence (`nextval()` takes a
microsecond LWLock, not a transaction-length row lock). A concrete reminder
that "one global counter row" is a scaling bug in any hot write path.

**Migration hygiene (adopt selectively).** Append-only embedded migrations
with per-engine SQL variants; **post-migration verify hooks** that probe the
post-condition and re-run idempotent migrations or raise drift errors (a
defense against partially-committed DDL on flaky poolers); and a self-heal
pass for the merge-renumbering reality of append-only migration arrays.

### 2.2 MCP and the agent surface

**One operation registry, many projections (adopt — highest-leverage pattern
in the repo).** Every operation declares name, description, param schema,
scope, and handler once; CLI, stdio MCP, and HTTP MCP are *generated* from it,
and stdio/HTTP share one dispatch function so they cannot drift. For vfs,
whose Python API, CLI, and MCP tools must expose the same verbs, this is the
architecture: the MCP tool list should be a projection of the same contract
the library exposes, never a hand-maintained parallel surface.

**A type-enforced trust axis (adopt).** Every operation context carries
`remote: boolean` as a *required* field, consumers fail closed (anything not
strictly `false` is untrusted), and the same op behaves differently by caller
trust — visibility filters, path confinement, outright refusal. vfs's dual
audience (trusted in-process ETL vs. remote MCP agents) wants this exact
spine rather than two codepaths.

**Tool descriptions as a tested routing surface (adopt).** Descriptions live
in a dedicated constants module, pinned by tests, and are written to a
formula: one sentence of function, explicit "use this when the user asks…"
triggers, blunt anti-triggers ("Do NOT run a semantic search for these"), and
**an inline example response shape** so agents don't burn a call discovering
the schema. Routing changes ship as reviewable data.

**Proactive context injection via `_meta` (study).** After every successful
tool call, a hook attaches relevant "hot memory" to the MCP-spec `_meta` slot
— best-effort (a throwing hook never fails the call), visibility-filtered,
cached, suppressed on the recall ops themselves. Most MCP servers are purely
pull; this is a genuinely novel push channel vfs could use for things like
"the file you just read has 3 inbound edges and a newer version."

**Destructive-op posture (adopt).** Three layers: always show an impact
preview / blast radius first; a confirmation gate; soft-delete with a 72h TTL
tombstone before any hard purge, with the hard-delete primitive admin-scoped
and *not exposed over remote MCP at all*. This aligns with vfs's
versioning-as-wedge story and is worth matching verb-for-verb.

**Two-channel leak sealing (file away for multi-tenant reads).** Their
private-data filtering happens in SQL *and* in free-text: a `holder = ANY(…)`
filter on the structured query, plus stripping the corresponding markdown
fence out of page bodies for remote callers — because structured data leaks
through the prose field too. Any vfs metadata that is both queryable and
embedded in file content has the same two channels.

**Where gbrain is thin — vfs should do better (opportunity).** No first-class
cursor pagination in the agent-facing contract (hard cap of 100 + filters;
cursors exist only internally) and no truncation signal in responses
(explicitly deferred). vfs's result envelope should treat both as first-class
from day one; this is a concrete surface where vfs can be visibly better for
large SQL result sets.

**Thin harness, fat skills (adopt the doctrine).** Their ethos doc names the
anti-pattern precisely: "a fat harness with thin skills: 40+ tool definitions
eating half the context window… REST wrappers that turn every endpoint into a
tool." Deterministic lookups become tools; judgment becomes markdown skills
that call those same tools. vfs's four-verbs-not-forty surface is already
aligned; the decision table ("same input same output → code; needs judgment →
prose") is worth writing into vfs standards. Their skills-over-MCP bridge
(`list_skills`/`get_skill` returning prose with an instructions envelope, and
a hard "display, never auto-execute" supply-chain rule) is a good template for
shipping a vfs Agent Skill.

### 2.3 Search and retrieval

**The title arm (adopt the insight).** Chunk-grain FTS structurally *cannot*
retrieve exact-title matches — the title isn't in any chunk's vector — so
page-title search is a separate candidate generator fused as its own RRF arm.
Generalizes to any chunked corpus: vfs's glean design needs a name/path arm
distinct from the content arm, or `grep`-shaped queries for a file the user
can name will lose to content noise.

**Provenance-signature staleness (adopt).** Every embedded page is stamped
`<provider:model>:<dims>`; re-embed targets signature drift; pre-feature rows
carry NULL and are *never* flagged (grandfathering, so an upgrade doesn't
trigger a corpus-wide re-embed); a content-addressed generation hash covers
the contextualization mode, model, and wrapper format so changing *any* of
them invalidates cleanly. This is the complete, incremental answer to "which
rows need re-embedding after a change" and vfs's glean machinery should copy
it nearly verbatim.

**Floor-gated, fail-open, attributed boosts (adopt the discipline).** All
post-fusion boosts are multiplicative, individually fail-open (a boost error
never breaks search), share a single floor-ratio gate computed once (metadata
boosts can never lift a weak page past a strong primary hit), and stamp
attribution so `--explain` shows every stage that fired and what it
multiplied. The explainability posture matters as much as the ranking math —
an agent (and a debugging human) can see *why* a result surfaced.

**Content-class recency decay (study).** Per-slug-prefix hyperbolic decay
with longest-prefix match: daily notes decay fast, entity pages slowly,
concept pages never. Maps naturally onto vfs paths. Their parser fails loud
on malformed config — a deliberate reaction to a predecessor that silently
skipped bad entries "for years."

**Autocut on reranker scores only (file away).** They measured that the
RRF/cosine gap between rank 1 and 2 is mechanically identical whether rank 1
is right or wrong, so score-cliff result sizing runs only on cross-encoder
scores. Empirically-grounded top-K instead of a fixed constant.

**Eval as a CI gate (adopt the posture).** Production queries are captured
(PII-scrubbed) into eval tables; benchmarks replay against a bare
deterministic pipeline; incident-derived query families (title-substring,
alias, multi-chunk-dilution…) are *hard* CI gates with thresholds; telemetry
tracks a rank-1 score-drift signal in coarse bands as a cheap production
quality canary; counters store sums-and-counts (never pre-averaged) with
`ON CONFLICT DO UPDATE` addition so concurrent processes accumulate
lock-free. vfs's glean/grep quality story should grow this skeleton early —
retrieval regressions are otherwise invisible until a user notices.

### 2.4 Graph and knowledge model

**Two-table resolved/unresolved edges (adopt — directly relevant).** Code
edges live in two tables: resolved (both endpoints are known chunk IDs) and
unresolved (target known only by qualified name). Readers UNION both; a
resumable backfill promotes as targets appear; there is no blocking
resolution step. This is the right shape for vfs typed file-edges, where an
edge's target may not have been ingested yet — dangling edges become a
first-class queryable state instead of an error.

**Open provenance tags over closed enums (adopt).** `link_source` is an open
kebab-case-regex CHECK with a handful of reserved managed built-ins that
carry reconciliation semantics; external derivers stamp their own tag with no
migration. Plus a PG15 `NULLS NOT DISTINCT` unique constraint so NULL-origin
edges collide correctly. vfs edge provenance should start open.

**Zero-LLM auto-linking as the default graph builder (adopt the stance).**
The +31.4-point graph lift comes from *pattern-matched* wikilinks and typed
refs on every write — deterministic, free, synchronous. LLM extraction exists
but runs in background enrichment. For vfs: the write path should extract
cheap deterministic edges inline; anything requiring judgment is a pipeline.

**Detection never auto-remediates (adopt the posture).** Contradiction
detection emits calibrated evidence (Wilson 95% CIs, small-sample gating at
n<30, severity rubric) plus *paste-ready remediation commands* — and a
grep-guard-enforced invariant that the probe never mutates data. The general
principle for vfs: background analyzers write findings and suggested
commands, never silent fixes.

**Content-addressed idempotency everywhere (adopt).** Deterministic slugs
keyed on source-date (not run-date) make re-extraction upsert instead of
duplicate; idempotency keys hash canonical-JSON params; caches key on
`(content hashes, model, prompt_version, policy)`. Every vfs pipeline stage
should be re-runnable by construction.

**Rate leases (adopt for pipelines).** Concurrency caps on outbound providers
are **owner-tagged DB rows with `expires_at`**, not counters — counters leak
capacity when a worker crashes mid-call; expiring leases make crash recovery
free. Acquisition is check-then-insert under a transaction-scoped advisory
lock; leases FK to their owning job `ON DELETE CASCADE` so cancellation frees
capacity automatically. Reject-don't-queue on saturation. The through-line of
their whole background layer: **coordination state lives in the database as
TTL rows and content hashes, never in process memory** — the correct
instinct for any multi-process, crash-prone pipeline fleet, i.e. vfs's ETL
audience.

**The doctor pattern (study for later).** ~90 self-diagnosis checks, each
returning status + remediation, cause-ranked, with a read-only
`--remediation-plan` (topologically ordered, cost-estimated, targets a health
score) separated from `--remediate` execution under dollar/job budget guards.
Ratio-based thresholds, not absolutes (an absolute orphan-count threshold
caused a warn-storm respawn loop). A `vfs doctor` with even a dozen checks
(dangling edges ratio, stale index watermarks, orphaned chunks, mount health)
would be a disproportionate trust win for an infra product.

---

## Part 3 — Enterprise reality and where the value sits

### What gbrain actually is today

A superb *single-power-user* product: a technically sophisticated founder,
VC, or exec running their own agent stack over a large personal
relationship-intelligence graph (people/companies/deals/meetings — the
default schema literally ships a `yc/` directory). The 10–50-person "company
brain" is documented and demoed but early — revealingly, the tutorial's
"database-enforced isolation" model (Model A) is *not* what Garry runs in
production; his deployment uses Model B, directory-convention scoping where
"the agent itself enforces" boundaries.

### What breaks first under an enterprise review

1. **Tenant isolation is app-code, not engine-enforced.** The "zero leaks"
   guarantee is `WHERE source_id = ANY(…)` threaded through every read path.
   The code's own comment is candid: app-layer filters are "layer 1" and
   *mandatory*; Postgres RLS is an opt-in env-var "layer 2" whose policies the
   operator must hand-write. The RLS that is on by default merely blocks the
   Supabase anon role. One new read path that forgets the filter is a
   cross-teammate leak — the class of guarantee that erodes as surfaces
   multiply. (Their own P0 history proves it: `list_pages` shipped ignoring
   source scope.)
2. **A single-process Bun daemon + overnight cron cycle.** No horizontal
   scaling; the README's troubleshooting section is a running log of the
   dream cycle straining at one user's 82–146K-page brain (cron timeouts,
   silently lost link rows on pooler blips, wedged syncs).
3. **Git-as-system-of-record with company data on laptops.** DR is "wipe the
   DB and rebuild from the repo"; multi-writer concurrency is "git handles it
   the way git handles it"; HR/legal/board markdown gets cloned to developer
   machines. No RPO, retention, legal hold, or DLP story.
4. **Identity and ops.** No SSO/SCIM/MFA; long-lived bearer secrets in laptop
   config files; manual per-teammate OAuth registration and a 45-minute
   onboarding ritual per seat.

None of this is incompetence — SECURITY.md is unusually honest — it is the
consistent consequence of "bring-your-own-everything, MIT-licensed, built for
myself first." The business posture confirms it: no hosted offering, no
pricing, and an explicit platform pitch tied to YC's company-brain RFS — "if
you're building in that space, you might as well build on this."

### Replicate, or underpin? Underpin.

The market signal is strongly positive for vfs: the CEO of YC built,
productionized, and open-sourced a system whose architecture summary —
database as substrate, filesystem-shaped namespace, MCP surface, hybrid
search plus typed-edge graph, agents as first-class users — is vfs's thesis,
and YC has an RFS pointed at the category. But the right response is not to
build gbrain's synthesis/enrichment layer into vfs:

- **The layers are genuinely different.** gbrain's value is opinionated
  *application* logic: a personal-CRM data model, LLM extraction pipelines,
  voice-gated prose, calibration scoring. vfs's value is *infrastructure*:
  namespace, verbs, isolation, durability, scale over enterprise SQL.
  Bundling the former would compromise the latter's neutrality (vfs serves
  ETL pipelines that want no LLM in the loop) and put vfs in competition with
  every brain-layer app instead of underneath them.
- **Every enterprise gap in §3 is a vfs feature, verbatim.** A gbrain-like
  product sitting on vfs would inherit: engine-enforced per-principal
  visibility as the *primary* layer (the datastore refuses cross-tenant
  reads whether or not the app remembered to filter); a durable SQL system
  of record with backup/PITR/retention where the org already has governance;
  **one enforcement chokepoint serving both the MCP path and the pipeline
  path** — collapsing gbrain's N-read-paths-must-all-be-correct problem into
  one auditable seam; and direct governed access to operational enterprise
  data (the CRM, the ticket system) that gbrain's people/companies/deals
  model wants but has no clean pipe to.
- **gbrain also validates the demand side of vfs's own audiences.** Its ETL
  is hand-rolled per-source ingestion scripts plus cron; its agents fight
  the same batch/pooler/backpressure problems vfs solves as a contract.

Concretely, the positioning: **vfs is to a company brain what Postgres is to
gbrain — except vfs makes the enterprise-blocking parts (isolation,
durability, dual-audience scoping) properties of the substrate rather than
disciplines of the app.** A "brain layer on vfs" is a natural flagship
demo/vertical (and the OpenClaw wedge memo's reversibility story composes
with it: gbrain has soft-delete, but vfs versions every write by
construction), whether built first-party as a showcase or left to the
ecosystem the RFS is summoning.

### What this changes about vfs priorities

Mostly it *confirms* the June direction memo (vertical slice of the four
verbs over Postgres via MCP; OSS core + paid isolation/SSO/audit layer), and
sharpens three things:

1. **Isolation as substrate is the enterprise wedge.** gbrain hands vfs the
   argument: even the best-engineered app-layer scoping ships P0 leaks. The
   paid-layer roadmap (RBAC/audit) should be framed as "the layer gbrain
   tells you to build yourself."
2. **The dual-audience contract is rarer than assumed.** gbrain — a genuinely
   sophisticated system — has no unified answer for "agents and bulk
   pipelines against one store"; it re-solves pacing, retries, and scoping
   per subsystem. vfs's write/read builders + single chokepoint design is
   differentiated infrastructure, not table stakes.
3. **Agent-facing polish is cheap and load-bearing.** Tested tool
   descriptions with inline response shapes, truncation signals, explain
   attribution, llms.txt, a SKILL.md — gbrain shows these are what make
   agents *effective* users, and most are small work items for vfs's MCP
   milestone.

---

## Appendix — shortlist of adoptable mechanisms

Priority-ordered for vfs, from Part 2:

1. One operation registry projected into library/CLI/MCP; shared dispatch.
2. Required `remote`/trust axis on every operation context, fail-closed.
3. Real-engine parity tests + lint guards for every write-builder pattern
   (the embedded-engine-masks-bugs lesson).
4. Provenance-signature staleness + grandfathering for all derived indexes
   (embeddings first, but the pattern covers trigram/FTS rebuilds too).
5. Two-table resolved/unresolved typed edges with UNION reads and resumable
   backfill; open kebab-case edge provenance tags.
6. db-pacer-style backpressure (semaphore + in-band EWMA + cooperative
   jittered sleep; fail-open; abort-throws) on bulk write paths.
7. TTL-row locks and lease-based (expiring-row) concurrency caps for
   pipeline coordination; content-addressed idempotency keys throughout.
8. Destructive-op ladder: impact preview → confirm → soft-delete TTL →
   admin-only local-only purge.
9. Result envelope with first-class truncation signal and cursor pagination
   (gbrain's acknowledged gap — do better).
10. Tool descriptions as tested data with triggers, anti-triggers, and inline
    response shapes; llms.txt + a vfs Agent Skill at launch.
11. Retrieval eval harness as a CI hard gate + sums-not-averages telemetry
    with a rank-1 drift canary, once glean lands.
12. `vfs doctor` with ratio-based checks and a read-only remediation plan,
    as the ops-trust surface.

## Source notes

All gbrain claims trace to the local checkout: `src/core/operations.ts`,
`src/mcp/{dispatch,server,tool-defs}.ts`, `src/core/{postgres,pglite}-engine.ts`,
`src/core/db-pacer.ts`, `src/core/batch-rows.ts`, `src/core/migrate.ts`,
`src/core/search/hybrid.ts`, `src/core/minions/rate-leases.ts`, `src/schema.sql`,
`docs/ENGINES.md`, `docs/architecture/{brains-and-sources,system-of-record,
topologies}.md`, `docs/storage-tiering.md`, `docs/takes-vs-facts.md`,
`docs/ethos/THIN_HARNESS_FAT_SKILLS.md`, `docs/tutorials/company-brain.md`,
`SECURITY.md`, `README.md`. Benchmark numbers (P@5 lift, LongMemEval recall,
"zero leaks" fuzzing, 146K-page production scale) are the project's own
claims, not independently reproduced — treat as directional. The isolation
assessment rests on the code's own comments (`postgres-engine.ts:195-197`,
`schema.sql:24,1387-1443`) and the company-brain tutorial's Model A/Model B
distinction.
