# Roadmap — vfs 0.1.0: the definition of done, by domain

- **Status:** draft for Clay's review — 2026-10-28, written against `main`
  at `90f5883`. Replaces the "Plan 9 wave" roadmap (specs 015–024, all
  landed and archived) and the root-level `ROADMAP-v0.1.0.md` of
  2026-05-18 (a pre-rebuild plan for a FastAPI service, SSO and a web
  console; none of it applies). Supersedes neither an ADR nor a spec:
  where this page and a decision record disagree, the record wins and
  this page is wrong.
- **Owner:** Clay Gendron
- **Purpose:** One place that says what "0.1.0 is done" means, domain
  by domain, as stories a single developer can pick up, each with
  acceptance criteria a test can pin. It also says what 0.1.0 is *not*,
  so a slip has a pre-agreed landing place (the `0.x` lane) instead of a
  scramble.
- **Method:** eight read-only audits of the live tree, the active specs
  and the decision record (kernel API, storage, search, shell and tools,
  identity, developer experience, release engineering, industry
  positioning), each labelling claims READ / EXECUTED / INFERRED. The
  audits live in the session scratchpad and their executed findings are
  repeated here where they bind a story. Nothing in this page is a
  decision; §9 lists the decisions Clay must make, each with a lean.

---

## 0. How to read this page

Short version first. The long version is below it.

- **0.1.0 is a promise, not a date.** The promise is in §1, three
  sentences. Every story on this page exists to make one of those
  sentences true.
- **The release lane is spec 166's:** alphas now, betas when the public
  surface stops moving, final when a beta has held. §2 names the three
  gates and what each one needs.
- **The work is grouped by domain, §4 to §13.** Each domain has one
  table that says what is built today and one list of stories. A story
  has an ID (`K1`, `H2`, …), the spec it lands (if one exists), a size
  (S, M, L, XL), the gate it belongs to (`a` = any alpha, `b` = needed
  before the beta freeze, `f` = needed before final, `0.2` = after),
  a one-paragraph *why*, its dependencies, and acceptance criteria.
- **Acceptance criteria count operations, never clocks.** A criterion
  names statements issued, rows visited, calls spied, a classified
  error kind, an exit code, or an engine leg. This is the repo's own
  rule (CLAUDE.md, *Performance tests*).
- **§14 is the sequencing**: which stories ride which alpha, and the
  dependency chain through the shell and the MCP front.
- **§15 is the cut list**: what is deliberately not in 0.1.0.
- **§16 is the decision list** for Clay. Nothing here is decided until
  it is.

One line: this page turns "we are relatively close" into a checklist
with a gate on every item.

---

## 1. What 0.1.0 is

### 1.1 The promise, in three sentences

Each sentence is written to be true on the day `0.1.0` ships. Under
each one is what must land first.

1. **vfs 0.1.0 is a governed file system for AI agents over the SQL
   database you already run — SQLite, Postgres, SQL Server and Oracle —
   where every read, search, write and tool call passes one gate that
   judges the caller's rights on every row.**
   *True today for files on all four engines (the gate, the ladder and
   row grants are built and green). True for tools only when the
   program table and the `/.vfs` views land (domains F and G).*
2. **Agents reach it as the interface they already know — `ls`, `cat`,
   `grep`, pipes — from Python (sync or async), from an agent shell, or
   over MCP, with `glob`, `grep`, ranked `glean` and `graph` built in
   and scoped to what the caller may see.**
   *The search half is built. The sync facade (X1), the shell (F1–F5)
   and `serve()` (M1–M3) are not.*
3. **Every change is versioned and reversible, a refused or risky action
   can become a question a human answers — with a preview of what the
   world will look like if they say yes — and then resumes safely, and
   one permission structure governs a file and a tool alike.**
   *Trash and restore are built. Version rows exist for replaced bodies
   only; nothing reads them back yet (K8). The question, the preview and
   the resume are domain B. "A file and a tool alike" is domain G.*

### 1.2 Who it is for

Two audiences, both first-class (CLAUDE.md, *Production posture*):

- **Agents** making many small calls: a read, an edit, a write, a
  search, in a loop, many at once. They care about latency and about
  never being lied to by a result.
- **ETL developers and pipelines** making few large calls: ten
  thousand files in one `write`, on a real engine. They care about
  batches being bounded and atomic, and about a sync entry point that
  works in a notebook.

A third party sits beside them: the **host application** that mounts
storage, sets posture, registers tools, and runs `serve()`. Most of
domain G, H and I is for the host.

### 1.3 What 0.1.0 is not

Said once here so nobody has to re-argue it (details in §15):

- Not a POSIX file system. No FUSE or NFS front, no handles, no inodes,
  no mode bits (ADR 087 pin 4). The public copy says "filesystem-shaped
  kernel", never "mount it on your laptop".
- Not bash. A static, bash-shaped subset that runs 87% of what agents
  actually type and refuses the rest with a named reason (ADR 081). The
  copy publishes the coverage number and never says "bash" unqualified.
- Not a web console, not SSO into anything, not OpenTelemetry, not a
  managed service. Those are the product plan's, not the library's.
- Not a general Python sandbox. The WASI Python guest is a stretch item
  behind an extra (T5), not a gate.

---

## 2. The release lane and its three gates

Spec 166 defines the lane; this section only says what each gate waits
for. Terms: an **alpha** may break anything; a **beta** may only fix; a
**final** changes nothing until `0.1.1` or `0.2.0`.

| Gate | Enters when | Stories tagged |
|---|---|---|
| **`0.1.0a1`** | This week, from the tree as it stands, decoupled from the shell (R1–R3). The 2026-10-15 amendment that tied a1 to spec 167 is reversed by decision D1. | `a` |
| **`0.1.0aN`** | One alpha per landed batch, cut by hand (§14 proposes the batches). | `a` |
| **`0.1.0b1`** — *the surface is frozen* | Every `b`-tagged story has landed; the frozen surface is written down (K9, R5); every "proposed" ADR is ratified, amended or withdrawn; Clay calls the freeze with a dated line. | `b` |
| **`0.1.0`** — *a beta has held* | The spec 166 bar (one beta current ≥ 14 days with no breaking fix; the engine legs green **from the published wheel**) **plus** every `f`-tagged story. Decision D2 confirms that the feature gate is this list and not the bar alone. | `f` |

The feature gate, in one list (the `b` and `f` stories, by domain):

- **Kernel:** preconditions and append (K2), integrity on read (K3),
  the listing cursor (K4), replay and the request key (K5), the ranged
  read (K6), the versions read side (K8), `run` retired and the
  surface regrouped (K9).
- **Human in the loop:** the ADR (H1), `plan=` previews (H2), the
  `pending` Result and resume (H3), cancellation (H5).
- **Identity:** the trust edge (I1), serve-time refusals (I2), tools
  under the ladder (I3), the credential seam (I4).
- **Storage:** the engine matrix (D1), schema lifecycle (D2), host
  provisioning (D3), 10k pins on every verb (D4), legs from the wheel
  (D6).
- **Search:** the default embedder settled (E1), slow providers
  converge (E2), provider by name (E3), hybrid pins on every engine
  (E4), docs (E6).
- **Shell:** 167 A–E (F1–F5) and 168 a–b (F6).
- **Tools:** views and index (T1), `/.vfs/run` (T2), host tools (T3),
  MCP servers as views (T4), tool interrupts (H4).
- **MCP front:** the adapter and `serve()` (M1), the one-line entry
  point (M2), `pending` on the wire (M3).
- **Developer experience:** the sync facade (X1), exports (X2),
  tutorial and how-tos (X3–X5), examples (X6).
- **Release and hygiene:** R1–R7.

---

## 3. State of the tree, in one table

What is built, what is drafted, what is missing, per theme Clay named.
"Built" means on `main` with tests green; "drafted" means a spec
exists and nothing has started; "missing" means neither.

| # | Theme | State | Evidence (audit, EXECUTED unless noted) |
|---|---|---|---|
| 1 | Public kernel API | **Built** as 25 async verbs behind one gate; **none** of ADR 087's arguments exist (no cursor, no `range=`, no `if_version=`, no `replace=`, no request key, no `versions`). All three ADR 087 probes still reproduce: twenty concurrent appends keep one line; a body rotted by raw SQL reads as success; a replayed `move` is a bare `not_found`. | `base.py:2835–3088`; `tests/test_ops.py:246` pins `ALL_OPS` = 25 |
| 1 | Interrupts / human in the loop | **Missing**, and the record contradicts itself: ADR 063 rule 5 and specs 148/149 define a `pending` kind and an ask ledger; the later ADR 084 pin 4 says "no `ask` inside vfs"; spec 170 maps a server's elicitation to `unsupported`. No producer of `cancelled` or `timeout` exists in `src/`. | grep of `src/` for `pending`, `elicit`, `interrupt`: none |
| 2 | SQLite, Postgres, MSSQL, Oracle | **Built**, plus MariaDB and a generic floor; all four engine legs were green together on 2026-10-15 (`ac5c515`). On 2026-10-28 the MSSQL leg is red at an `apt` step (an Ubuntu 24.04 package list on a 26.04 runner); the six 2026-10-24 storage fixes have no SQL Server evidence. No migration story: a format mismatch refuses "re-provision". | `dialects.py:379–561`; run 40689014566 |
| 3 | Embedding provider, BM25 + vector at query time | **Built**: query-time embedding of the query, lexical and vector legs, client-side convex fusion, four providers (hashing, model2vec, OpenAI, LangChain), vectors built at `reindex`. ADR 060's fastembed/MiniLM default was never built; a slow provider never converges (120 s timeout × 2,048-input batches). | `backend.py:554–687`, `glean.py:215–513`; 95 tests green |
| 4 | Three tool kinds | **Missing**. `run` is a routed verb no storage serves. Specs 169/170 drafted. "MCP servers authenticating as the user" is undecided and spec 170 §3.1 pins the opposite (one host credential per server). | `vfs.shell`, `vfs.mcp`: `ModuleNotFoundError` |
| 5 | Sync calls, Jupyter, ETL | **Missing** sync facade; `asyncio.run` fails in a running kernel (reproduced through a real ipykernel). A 25-line thread-loop prototype works in a script, in Jupyter, and over the in-memory backend. The 10,000-row `write` lands in 49 statements. | audit `dx`, scripts under `scratchpad/dx/` |
| 6 | Serve vfs as MCP | **Missing**; spec 171 drafted (verbs as tools + one `cli` tool), spec 149 (token → `Authority`) a seed. No `[project.scripts]` entry; spec 171 decision 7 says "no `vfs serve`". | `pyproject.toml` |
| 7 | Everything is a file, one permission structure | Ladder **built** (six rungs, every verb names its rung); `/.vfs` has only the trash view; `ls /.vfs/mounts` is `not_found`. Views, index and `rungs_at` drafted (169a, 170 §5). | `ops.py:134–160`; shell memo §12 |
| 8 | Bash-like CLI | **Missing**; spec 167 (five slices, 20 tasks) and 168 drafted, reviewed, not started. | — |
| — | Release | `0.0.22` on PyPI, none yanked; the seven-platform publish matrix has **never run**; the bump script cannot write `0.1.0a1`. | `gh run list` on `publish.yml` |

Counts worth keeping in view: 31 active specs (4 built-not-archived, 3
overtaken), 10 ADRs "proposed" (022, 058, 069, 081–087), ADR 087 with 6
leans and 2 spec forks pending Clay, 36 `[NEEDS CLARIFICATION]` markers
in specs 174–181, about 40 live open questions, 5,780 tests at 100%
coverage.

---

## 4. Domain A — The kernel and the public API

**Goal at 0.1.0.** The kernel is the gate and everything under it (ADR
087). Its public surface is the 24 verbs (25 minus `run`) with the four
argument families a file protocol needs — cursor, range,
preconditions, replace — and three promises written down and pinned:
the atomic unit, the fault model, and replay. The three live defects the
OSTEP probes found are closed.

**Why this is the spine.** Every other domain is a facet over this one.
The shell's `>>`, the WASI guest's write-back, the MCP tool's
`idempotentHint`, the sync facade's signatures, and the human-in-the-loop
resume all stand on arguments that do not exist today.

### State today

| Piece | State |
|---|---|
| One gate, 25 routed verbs, `Result` envelope, 23 error kinds | built |
| `ls`/`tree`/`glob` paging | missing (constitution Art. 2 §3 violated) |
| `read(range=)` | missing |
| `write(if_version=, if_absent=, append=)` | missing (probe 1 live) |
| verify `content_hash` on read | missing (probe 2 live) |
| replay table, `request_key` | missing (probe 3 live) |
| `move`/`copy(replace=)` | missing (spec 167 says `overwrite=`; ADR 087 says `replace=`) |
| `versions(path)`, `read(version=)`, `created_by` | missing |
| `entry_id` on `stat`/`ls`, `OpGroup` | missing |
| `run` verb, `SupportsRun` | live but dead (retired on paper by ADR 082 pin 12) |

### Stories

#### K1 — Ratify ADR 087 and resolve its six leans · spec: ADR 087 · size S · gate b

*Why.* Eight specs stand on a proposed ADR. Six pins carry a lean Clay
has not confirmed, and two of them change public names (pin 3:
`delete`/`move` vs `remove`/`rename`; pin 16: flat names vs
`vfs.query.grep`). Nothing in K2–K9 can freeze until they are decided.
*Depends on.* Nothing. Decisions D4–D8.
*Acceptance.*
1. ADR 087's status line reads "accepted" with a date; its *Pending
   Clay* section records each of the six pins and the two spec forks as
   resolved, with the choice.
2. Spec 167 and 169 say `replace=`, not `overwrite=`, wherever the
   argument appears (a grep over `context/specs/active` for `overwrite=`
   finds only spec 174's removal note).
3. Architecture pages 01, 02 and the glossary no longer list the three
   open pins under *Open*.

#### K2 — Write preconditions and the guarded append · spec 174 · size L · gate b

*Why.* Probe 1 is a live data-loss defect on every engine: twenty
concurrent read-then-write appends to one file all report success and
one line survives. Constitution Art. 5 forbids silent clobbering.
`if_version=` is also what `edit`, the shell's `>>`, the WASI write-back
and the human-in-the-loop resume (H3) need.
*Depends on.* K1.
*Acceptance.*
1. `write(path, content, if_version=N)` against a row at version N+1
   returns `conflict` with `data["version"] == N+1` and issues zero
   mutation statements, on SQLite, Postgres, SQL Server and Oracle.
2. Twenty concurrent `write(append=True)` of one line each leave twenty
   lines; each call commits exactly one version row; a guard miss on a
   `reprobe` dialect classifies `conflict` and on a `redrive` dialect
   reruns from a fresh snapshot (counted on the retry counter).
3. `write(if_absent=True)` on a live occupant is `exists`; on a
   tombstone it revives and reports `created`.
4. A 10,000-entry batch with `if_versions={...}` and one stale row
   writes zero rows; statements grow by at most one chunked select per
   `membership_budget`.
5. An identical rewrite reports `unchanged`, leaves `version` untouched
   and issues no content insert.
6. `overwrite=` leaves `write` (or stays, per D7); the params drift test
   and `Session.write` agree.

#### K3 — Integrity: verify on read, hash on every written row · spec 175 slices A–C · size M · gate b

*Why.* Probe 2: an out-of-band writer (an ETL job with SQL credentials)
can change or delete a body and `read` serves it as success. The hash
is stored and never compared.
*Depends on.* K1 (the kind's name: its own, or `unavailable`; D8).
*Acceptance.*
1. After a raw `UPDATE vfs_content SET content='ROTTEN'` the next
   `read` returns no content and one error of the chosen kind at the
   entry's path; `success is False`; on all four engine legs.
2. A fault is reported only when two reads agree; the second read is
   exactly one extra statement.
3. Every row that `write`, `edit`, `copy` or `move` returns carries
   `content_hash == sha256(body)`.
4. Bodies at or above the offload threshold hash on a worker thread:
   `to_thread` calls equal the number of large bodies in the batch,
   zero for small ones.

#### K4 — The listing cursor · spec 176 · size M · gate b

*Why.* `ls` of a 10,000-child directory returns all 10,000 rows with no
limit, cursor or warning. The MCP tool surface, the shell's `ls` and
`find`, `scrub` and the bounded `sweep` all page on this key.
*Depends on.* K1 (pin 12: the key as a `Result` field, D6).
*Acceptance.*
1. `ls(path, limit=1000)` over 10,000 children returns 1,000 rows and
   `next_after == rows[-1].path`; ten pages visit each child exactly
   once; rows visited per page ≤ 1,001 on every engine (counted on the
   keyset statement).
2. A tombstone between two pages is never emitted and never stalls the
   key.
3. `tree` and `glob` page on the same path key; a fan-out over three
   mounts merges pages and emits one key.
4. `Result | Result` clears the key; `with_mount` rebases it; the
   renderer prints `more: after=…` only when set.

#### K5 — Replay: the per-verb contract and `request_key` · spec 177 · size L · gate b

*Why.* Probe 3: a client that lost the reply to `move` cannot tell
"already moved" from "never existed". The request key is also the
resumption token for H3; one value serves replay and resume.
*Depends on.* K2 (the `unchanged` row), K4 (the sweep arm).
*Acceptance.*
1. A replayed `move` returns `not_found` with `data["vfs.occupant"]`
   naming the destination and its `entry_id`; a move of a path that
   never existed carries no occupant.
2. Every mutating verb sent twice matches a pinned replay table, one
   row per verb, on the memory and SQLite legs.
3. `write(..., request_key=k)` sent twice issues, the second time,
   exactly one replay-store select and zero mutation statements, and
   returns a `Result` equal to the first.
4. A keyed call to a mount without the `replay` trait is `unsupported`.
5. A 10,000-row keyed `write` stores its answer under the dialect's
   byte budget; `sweep` reclaims replay rows older than the TTL (rows
   counted).
6. A connection lost during `COMMIT` classifies apart from one lost
   before it.

#### K6 — The ranged read · spec 178 · size S · gate b

*Why.* `head` and `sed -n 1,20p` on a 4 MB body read the whole body
today. The dialect's substring serves the slice.
*Depends on.* K3 (a ranged row says its slice and carries no hash
mismatch claim it cannot check).
*Acceptance.*
1. `read(path, range=(0, 4096))` on a 4 MB body moves at most 4,096
   body bytes over the wire (counted on the bound and fetched values),
   on every engine.
2. The row says which slice it carries; `size_bytes` is the whole body's.
3. A range past the end is `invalid` naming the length; a range on a
   directory is `wrong_kind`.

#### K7 — The storage seam as the kernel: atomic unit, crash points, engine error · spec 179 (slices) · size L · gate f

*Why.* ADR 087 pins 7 and 8 state the atomic unit and the fault model;
nothing pins them. A mixed good-and-bad 10,000-row batch must write
zero rows, and a crash at each mutating statement must leave the mount
whole, on every engine. The engine's own error code must travel as a
field, never as message text.
*Depends on.* K2–K5 landed (the seam regroup covers their arguments).
*Acceptance.*
1. On each engine leg: 10,000 good rows plus one bad in one `write`
   commits zero rows; 10,000 good rows commit in one transaction
   (transactions counted).
2. A fault injected at each mutating statement of `write`, `move`,
   `delete` and `restore` (the `seams` injector) leaves every table
   consistent with the oracle, on SQLite and on each engine leg.
3. `classify_failure` sets `data["vfs.engine_error"] =
   {sqlstate, code, driver}` from driver attributes, never from the
   message; a forced deadlock on each leg carries the engine's code.
4. `traits()` declares the atomic unit (`whole_batch` / `resumable`)
   per verb; a drift test pins the table to ADR 087 pin 7.
5. The seam's `features()` exists and the kernel derives `tree`,
   `edit` and `rmdir` for a backend that lacks them (served, counted
   as more statements, correct).

#### K8 — The history read side: `versions(path)`, `read(version=)`, `created_by` · spec 180 (read slice only) + ADR 064 · size M · gate f

*Why.* The headline says "every change is versioned and reversible";
today version rows exist for replaced bodies only, creates record no
creator, and nothing reads a version back. Without a read side, "who
changed this" has no answer. `pack` and the bounded `sweep` (the rest
of spec 180) are 0.2 (§15).
*Depends on.* K1 (the verb's name, lean `versions`), K4 (the cursor).
*Acceptance.*
1. `versions(path)` at rung `read` returns the version rows for the
   path with `actor`, `provenance`, `source_identity`, `subjects`,
   `grant_revision`, `created_at`, paged on the K4 key; a hidden path
   is `not_found`; a `list`-only path is `permission_denied`.
2. `read(path, version=N)` returns body N with its hash verified (K3).
3. A `created_by` column on the entry row is stamped on every mint,
   including `anon` and `system`; the schema format version bumps.
4. `versions` on 10,000 paths issues `ceil(10000 / membership_budget)`
   entry statements and one chunked subjects statement per slice.

#### K9 — Retire `run`, the kernel groups, `entry_id`, the frozen surface · spec 167 A (the `run` task) + spec 181 · size M · gate b

*Why.* `run` is retired on paper and live in code; `ALL_OPS`, ADR 087
and spec 181 count the surface three different ways; and beta entry
needs a written list of what is frozen. This story writes it.
*Depends on.* K2–K6 (the arguments the list documents), K1.
*Acceptance.*
1. `run` is absent from `Op`, `EXEC_OPS`, `VERB_RUNGS`, `PARAMS`,
   `base.py`, `session.py`, `SupportsRun`, `README.md`; `ALL_OPS` has
   24 members.
2. `OpGroup` assigns every op exactly one of `filesystem | query |
   history | rights | derived`; a drift test pins the five sets.
3. `stat` and `ls` rows carry `entry_id`; a `write` of an `Entry`
   carrying `entry_id` is `invalid`.
4. `docs/reference/api.md` lists every public name, signature, `Result`
   field, storage protocol and `SCHEMA_FORMAT_VERSION` the beta
   freezes; an import test asserts the list equals the live surface.
5. The conformance battery is reorganised by kernel operation with no
   test lost (count before equals count after).

---

## 5. Domain B — Human in the loop: policy, preview, `pending`, resume, cancel

**Goal at 0.1.0.** A host can run vfs with a human in the loop the way
LangChain runs tools with `interrupt()` and `Command(resume=)`: an
action can be stopped before it happens, described exactly — including
what the world will look like after — handed to a human, and resumed
safely with the human's answer. This works for kernel verbs, for host
tools, for mounted MCP servers and for shell lines, in process and over
MCP.

**The idea, said plainly.** vfs never asks a human anything. vfs never
blocks a call waiting for one. What vfs does is *suspend*: it stops
before the side effect, returns a classified, resumable `Result` called
`pending`, and lets the host do the asking. When the host comes back
with an answer, the same call is re-sent with the ticket, re-enters the
gate from the top, and runs once. Nothing is ever held open in memory.
This is LangGraph's model (the node re-runs on resume), and it is the
precedent Clay asked about: Linux's seccomp user notification suspends
a syscall and lets a supervisor outside the kernel answer; fanotify's
permission events do the same for file opens; Plan 9's factotum blocks a
process on `needkey` and lets a user agent answer by writing a file.
None of them puts the asking in the kernel. The kernel provides the
suspension point, the description and the decision channel.

**The preview.** Clay's second requirement: when a call would change
files, show "what the world will look like if this is approved", the
way Claude Code shows a diff before asking. vfs is well placed for this
because the database write path already works plan-then-execute: it
stages every change against an in-memory plan and only applies the
plan when it has no errors (`writes.py`, `_finish` → `_apply`). The
preview is that plan, rendered, with no commit. The preview records each
row's version, and the resumed call carries those versions as
`if_version` preconditions (K2), so an approval can only apply to the
world the human actually looked at. That is the piece a plain diff
approval lacks and Terraform's plan-then-apply has.

**What this amends.** ADR 084 pin 4 ("no `ask` inside vfs") stays true
in its letter and gains one sentence: *vfs never asks; a policy hook, a
tool, a server or a grant check may suspend a call into a `pending`
`Result` that a host answers through the ledger.* ADR 063 rule 5 and
spec 148 §5 already say this. Spec 149 rule 5 ("complete-only until an
ask rung exists"), spec 170 §4 (elicitation → `unsupported`) and spec
171's scope (tasks and MRTR out) are amended by H1.

### State today

| Piece | State |
|---|---|
| `pending` kind, ticket, ledger, `resume` | missing (spec 148 seed; ADR 063 rule 5 accepted) |
| A dry-run / plan form on any verb | missing (the plan seam exists inside `writes.py`) |
| A host policy hook before dispatch | missing |
| `cancelled`, `timeout` kinds | declared, **no producer** in `src/` |
| Deadline on fan-out | missing (spec 051, stale draft since July) |
| Progress reporting | missing; in-process may omit it (constitution Art. 5) |

### Stories

#### H1 — The interrupt ADR: reconcile ask and no-ask, name the kind, place the ledger · new ADR · size S · gate b

*Why.* Two accepted and proposed records contradict each other and
every story in this domain, in domain G and in domain H depends on
which one wins. This ADR must land before specs 170 and 171 are built,
or both are reopened.
*Depends on.* Nothing. Decisions D9–D11.
*Acceptance.*
1. The ADR is accepted and lists its amendments: ADR 084 pin 4 and pin
   9's kind list, spec 148 §5, spec 149 §5, spec 170 §4's failure
   table, spec 171's scope, the glossary line and architecture page 11.
2. `ErrorKind` gains exactly one new core kind for the suspended call
   (lean `vfs.pending`, severity error, a new `RetryClass.resume`) and
   `KIND_CONTRACTS` carries its phrase, hint and `path` referent; the
   result-laws test round-trips it through `to_payload`/`from_payload`.
3. A table in the ADR says, per producer — the policy hook, a gate
   refusal a principal could lift, a host tool, a mounted server's
   elicitation, a shell line — whether the call suspends and what the
   ticket carries.
4. The ADR states the one model: a kernel call is never held open
   across an interrupt; it is refused with a ticket and re-driven; a
   tool that is interrupted is restarted, never resumed mid-body; a
   tool that cannot restart keeps its own checkpoint as a file under
   `/.vfs/jobs/<ticket>`.
5. The ledger lives in the mount's schema beside the replay store (one
   table, swept with the trash), so a resume can arrive at a different
   process. The ADR says so and names the TTL (lean: spec 177's 24 h).

#### H2 — `plan=`: every mutating verb can preview the world after · new spec · size M · gate b

*Why.* The preview Clay asked for, and the half of an interrupt that
makes approval meaningful. A host can also call it with no interrupt at
all, as Unix's `-n` and Terraform's `plan`.
*Depends on.* K2 (`if_version` carries the preview's versions into the
apply), K3 (the preview's rows carry the hash they were computed
against).
*Acceptance.*
1. `write`, `edit`, `delete`, `mkdir`, `move`, `copy`, `restore`,
   `mkedge`, `rmedge`, `grant`, `revoke` and `posture` accept
   `plan=True` and return the planned `Observation` rows with
   `success=True`, a `vfs.plan` info record, and **zero** mutation
   statements (counted on the statement hook), on every engine leg.
2. The planned rows say what changes: for `edit` and a text `write`, a
   unified diff of the current body against the planned body rides the
   row; for `delete`, every row that would be tombstoned, cascade
   included; for `move` and `copy`, the before and after paths and, with
   `replace=True`, the occupant that would be versioned; for `grant`
   and `posture`, the grant row that would appear.
3. Every planned row carries the `version` it was computed against;
   re-sending the call with `plan=False` and `if_versions=` taken from
   the plan applies it; if any row moved in between, the apply is
   `conflict` and writes nothing.
4. `plan=True` under a caller who may not perform the verb answers the
   same refusal the real call would (`permission_denied`,
   `read_only`), never a plan.
5. A 10,000-row `write(plan=True)` issues the same read statements as
   the real call's staging phase and no more (counted).
6. The renderer prints a plan as a diff-shaped block the shell and the
   MCP text block reuse unchanged.

#### H3 — The policy hook, the `pending` Result, the ledger and resume for kernel verbs · spec 148 §5 rebuilt on H1 + K5 · size L · gate b

*Why.* The kernel half of the interrupt. Two producers at this story:
a host policy hook that may say "ask first" about an allowed call, and
a gate refusal a principal could lift. The answer admits exactly one
re-run; the re-run re-enters the gate, so a right revoked between the
question and the answer is honoured.
*Depends on.* H1, H2, K5 (the ticket is a `request_key`).
*Acceptance.*
1. `VirtualFileSystem(policy=hook)` and `Session(policy=hook)` accept a
   callable (sync or async) that receives a `CallDescription` — verb,
   canonical arguments, paths, the rungs needed, the authority shape,
   and for `cli` the static parse of the whole line — and returns
   `allow`, `deny(kind, message)` or `pending(reason)`; the hook is
   called after the gate's structural checks and before storage, so a
   call the gate would refuse never reaches it (counted: zero hook
   calls on a `permission_denied` call).
2. A hook answer of `pending` makes the call return `success=False`,
   one `vfs.pending` error whose `data["vfs.interrupt"]` carries
   `ticket`, `digest`, `expires_at`, `needs`, `producer="policy"` and
   the H2 plan for a mutating verb, with zero mutation statements.
3. A verb the ladder refuses under a `none` posture that a principal
   could allow answers `pending` with `needs="grant:<rung>@<path>"`
   (spec 148's case) at no statement beyond the refusal's own.
4. `fs.answer(ticket, allow=True, authority=approver)` writes one
   attributed ledger row (actor and subjects, ADR 064) and no entry
   row; an approver without the right is `permission_denied` and the
   ledger gains no row; `Session.answer` does not exist (the answer
   channel is the grant channel).
5. Re-sending the identical call with `request_key=ticket` proceeds
   once and commits; a second re-send is `pending` again (one-shot
   spent); a changed argument has a different digest and is not
   admitted; an expired ticket is `pending` with `expired=True`;
   `sweep` reclaims expired rows (counted).
6. The ledger row is in the mount's schema: a resume from a second
   `DatabaseStorage` over the same SQLite file succeeds.
7. A LangGraph example in `docs/how-to/human-in-the-loop.md` wraps
   `pending` with `interrupt()` and `Command(resume=)`, and its fences
   run under the docs gate against the in-memory backend (the LangGraph
   import is skipped when the extra is absent).

#### H4 — Interrupts for every tool kind: host tools, MCP elicitation, shell lines · amends specs 170 and 171 · size L · gate f

*Why.* Theme 4 says all three tool kinds are interruptible. A host tool
raises an interrupt; a mounted server answers `input_required`; a shell
line stops at the stage that asked. All three produce the same
`pending` record, and all three resume the same way.
*Depends on.* H3, T3, T4, F3, M1.
*Acceptance.*
1. A host tool that raises `Interrupt(payload)` ends its stage with
   exactly one `vfs.pending` error carrying `payload`, `stage` and
   `program`, exit code 75 (`EX_TEMPFAIL`; D12), `success is False`;
   the tool was entered exactly once (spied); zero verbs ran after it.
   A tool that raises a host framework's own interrupt type registered
   as pass-through (LangGraph's) propagates unwrapped, never
   classified.
2. Re-issuing the same line with a live allowance runs the tool once
   more with the answer as its resume value; a spent allowance is
   `pending` again.
3. A mounted 2026-07-28 server answering `input_required` yields
   `pending` with `inputRequests` and the opaque `requestState`; the
   resume re-sends `tools/call` with `inputResponses` and the same
   `requestState` exactly once (spied); the interim result is never
   cached.
4. A pipeline `producer | interrupting_tool | consumer` ends with the
   consumer having received zero chunks, the producer cancelled with
   `vfs.cancelled` at info severity, stdout emitted before the stop
   kept, and `statuses` marking the pending stage; a resumed line
   re-runs from the start, which spec 177's replay table makes safe
   for vfs's own verbs. (The pipe cannot checkpoint: asyncio queues,
   Rust kernel state and wasm instances are not serialisable, and the
   wire's `cli` is stateless by decision.)
5. A `cli` line whose first mutating stage the policy hook suspends
   carries the H2 plan of that stage and marks later stages "not run".

#### H5 — Cancellation and deadlines as kernel facts · spec 051 rewritten · size M · gate f

*Why.* `timeout` and `cancelled` are reserved and unproduced; one hung
remote mount stalls every namespace-wide query; a front that catches
cancellation has no classified shape to return. Constitution Art. 5
asks MCP surfaces to carry cancellation.
*Depends on.* H1 (the producer lives in the kernel, not in a facet).
*Acceptance.*
1. `grep(pattern, deadline=…)` over one fast mount and one mount whose
   `grep` never returns yields the fast mount's rows and one `timeout`
   error at the slow mount's prefix; the slow coroutine is cancelled
   (cancelled tasks counted = 1).
2. A deadline on a mutation is refused `invalid` or classifies the
   in-doubt kind, one of the two, pinned.
3. An outer `CancelledError` still re-raises untouched.
4. `cancel(ticket)` marks a pending ledger row and the next re-send is
   `cancelled`; on the wire this is the MCP tasks extension's cancel
   when M3 lets tasks in.
5. With no deadline configured, statement counts are identical to
   today on every leg.

---

## 6. Domain C — Identity, rights and the trust edge

**Goal at 0.1.0.** In process the gate is a convention (ADR 068): any
caller can construct the system authority. On the wire it is a wall: a
token in, an `Authority` out, nothing identity-shaped as data. Tools and
MCP servers are rows the ladder governs. "MCP servers authenticating as
the user" has a decided shape and a seam, even where the full OAuth
round trip is 0.2.

### State today

| Piece | State |
|---|---|
| `Principal`, `Authority`, four doors, per-call `authority=`, `Session` | built |
| Ladder (six rungs), grants, posture, members, rights compiled into every statement | built, on every engine leg |
| `TokenVerifier`, `authority_from_token`, `provenance="edge"` minted only at the edge | missing (spec 149 seed; the docstring claims an edge factory that does not exist) |
| `serve()` refusal on an open mount; what "open" means on the ladder | missing; "open/shared/private" (ADR 068) vs six rungs (code) is unresolved |
| Tools as rows a grant can name (`rungs_at`) | drafted (spec 170 §5) |
| Per-principal credentials for a mounted MCP server | missing and **undecided**; spec 170 §3.1 pins one host credential per server |
| `created_by`, a history read | missing (K8) |
| `manage` rung, group ownership, non-system membership admin | parked open questions |
| 100k-user scale pins | memo only; no world above a few hundred rows in `tests/` |

### Stories

#### I1 — The trust edge: `TokenVerifier` and `authority_from_token` · spec 149 · size M · gate b

*Why.* Theme 6 needs a wall between a bearer token and an `Authority`.
`provenance="edge"` is a value nobody mints today, so any caller can
forge an edge proof in the audit.
*Depends on.* Nothing in code. Decisions D13, D14.
*Acceptance.*
1. `authority_from_token(claims) -> Authority | ResultError` is the
   fifth door and the only site in `src/` that mints
   `provenance="edge"`; the construction-site pin asserts exactly one
   such site.
2. A `TokenVerifier` protocol with one method and one shipped
   implementation over a JOSE library behind a new `vfs-py[serve]`
   extra; the core install imports neither.
3. Over a table of twelve claim shapes: `sub` equal to the reserved
   system name, `anon`, `*` or a `group:` prefix is `invalid`; a
   verifier failure or a missing audience is `unauthenticated`.
4. `act` present → actor is the `act` principal, subjects `{sub}`;
   absent → actor equals subject; `source_identity == sub` in both;
   a `groups` claim is ignored (D13).
5. The door token: a bare `Authority(...)` constructed outside
   `vfs.authority` raises `TypeError` naming the doors; `copy` and
   `pickle` still round-trip.

#### I2 — `serve()` identity per request and the open-mount refusal · spec 171 §0 + ADR 068 rule 7 · size M · gate b

*Why.* The identity half of the MCP front: HTTP derives an authority
per request from the token, stdio takes one authority, the system actor
is refused, a handler never reaches the gate with `None`, and the edge
is loud about an open mount.
*Depends on.* I1; decision D15 (what "open" means on the ladder).
*Acceptance.*
1. `serve(fs, transport="stdio", authority=Authority.system())` raises
   before binding a transport; so does a router whose default
   authority is the system actor.
2. A spy on `_call_storage` counts zero calls with `authority is None`
   across the whole MCP test module.
3. HTTP with no token runs as `Authority.anonymous()` and is judged by
   the ladder; an invalid token is HTTP 401 `vfs.unauthenticated` with
   zero storage calls.
4. `serve()` refuses to start while any bound mount's root
   everyone-level is at or above the rung D15 names unless
   `allow_open=True`; the refusal lists every such mount; with the
   flag it starts and logs one warning per open mount. The
   `/.vfs/tools` and `/.vfs/mcp` catalogue postures count as mounts for
   this rule.
5. No served tool and no served schema names `authority`,
   `observations` or `provenance` (counted over every input schema).

#### I3 — Tools and MCP tools under the ladder: `rungs_at` and catalogue posture · spec 170 §5 · size M · gate b

*Why.* Theme 7. Executing a program or calling a tool is `read` on its
entry (ADR 084 pin 2); listing is `list`; installing is `write` under
the ladder. A catalogue entry has no stored row, so a new seam answers
"what rung does this caller hold at this view path" in one chunked
statement per budget slice.
*Depends on.* T1, T3 (the catalogues); K9 (`run` gone).
*Acceptance.*
1. `SupportsGrants.rungs_at(paths, *, authority)` issues exactly
   `ceil(len(paths) / membership_budget)` statements for 10,000 paths
   on SQLite and on each engine leg; its answer equals the Python
   oracle over the random grant worlds.
2. `grant("/.vfs/tools/deploy", "ann", "read")` is lawful and lists
   under `grants(...)`; `write`, `mkdir`, `delete`, `move` at a
   catalogue path are `invalid` with zero storage mutations.
3. With `posture("/.vfs/tools", "list")`: anonymous `ls` names every
   tool bare; `cat` of one is `permission_denied`; calling one is exit
   126 and zero host-function invocations (counted). With posture
   `none`: `ls` shows nothing and a call is 127.
4. `type deploy` and `cat /.vfs/tools/deploy` render the trust line
   and never invoke the tool (invocation counter stays zero across the
   read family).

#### I4 — MCP servers that act as the user: the per-principal credential seam · new ADR + spec, amends spec 170 §3.1 · size M · gate f

*Why.* Theme 4(b). The MCP spec forbids forwarding the client's token
upstream and RFC 8707 audience binding would refuse it anyway; the
standards answer (token exchange, enterprise-managed authorization) has
one shipping identity provider. The 0.1.0 shape that keeps vfs free of
OAuth and still "acts as the user": the host supplies a credential
resolver keyed by server and authority; vfs opens one connection per
distinct principal; the credential never appears in a row, a result, a
log line or a child's environment. The OAuth-on-demand round trip
(which is itself an interrupt) is T6 in 0.2.
*Depends on.* I1 (`source_identity` is the key), T4, decision D16.
*Acceptance.*
1. `add_mcp(name, server=..., credentials=...)` accepts a static
   credential (today's shape) or a `CredentialResolver` with one method
   `resolve(server, authority) -> Credential | ResultError`, called at
   most once per `tools/call` and never during `tools/list` (counted).
2. A resolver answer of `None` or an error makes the call
   `unauthenticated` at the tool's path with zero bytes sent to the
   server (transport spy).
3. One MCP connection per `(server, principal)`: 100 calls by one
   principal issue exactly one `initialize`; a second principal issues
   a second; two callers see two `tools/list` results when the server
   varies its catalogue by bearer, with zero cross-caller cache hits.
4. A subject set over a per-user server is refused `invalid` at 0.1.0
   (D16).
5. The inbound HTTP bearer token never appears in any outbound request
   to a mounted server; the credential never appears in any `Result`,
   row, log line or stdio child's environment (a test greps every
   captured output for the secret bytes).

#### I5 — Scale pins for the rights compile · size M · gate a (slow tier)

*Why.* The 100k-user memo measured caller-sized compiles and both fixes
landed, but `tests/` holds no world above a few hundred rows; a
regression to a world-sized compile would pass CI. Counts, never clocks.
*Depends on.* Nothing; `slow`-marked.
*Acceptance.*
1. A generated world (10,000 users, one private home each, 100 shared
   folders, 50 groups, five per user): an ordinary caller's `Rights` at
   `read` holds ≤ 64 pieces and ≤ 4 KiB of bind bytes, and the same
   bound holds at 1,000 users.
2. `ls /` for that caller issues one visibility statement whose text is
   identical to the 1,000-user world's.
3. A posture change on a 100,000-row subtree runs in
   `ceil(rows / RELABEL_CHUNK)` statements; a read held midway agrees
   with the oracle.
4. The pins run on SQLite by default and on each engine leg when the
   URL is set.

#### I6 — Validate declared owners; the silent-escalation guard · size S · gate b

*Why.* The system actor stamps any declared `owner_id` unchecked, so a
batch loader can mint a row owned by `*`, `anon` or `group:x`; and a
host whose `default_authority` is the system actor turns every
forgotten `authority=` into a system write.
*Depends on.* Nothing. Decision D17 (group ownership stays parked).
*Acceptance.*
1. A declared `owner_id` of `*`, `anon`, `system` or a `group:` prefix
   is `invalid` on `write`, `mkdir`, `copy`, `restore`; a plain
   principal name is stamped.
2. `VirtualFileSystem(default_authority=Authority.system(),
   loud=True)` (or the equivalent flag D17 names) logs one line per
   call that fell back to the default; the shell's `cli` and `serve()`
   refuse the system actor regardless.

---

## 7. Domain D — Storage engines: SQLite, Postgres, SQL Server, Oracle (and MariaDB)

**Goal at 0.1.0.** "Supported" has a published meaning: a tuned
dialect profile, a cosine distance function (ADR 059), a Docker leg in
CI, a row in a matrix the README carries and a test pins. A host app
can provision on its own Postgres or SQL Server without hand-made
schemas. A format bump never strands a database silently. Every verb is
bounded at 10,000 rows on every engine, and the pins say so.

### State today

| Piece | State |
|---|---|
| Five tuned profiles + the generic floor; every op on all five; the floor withholds `glean` only | built (CLAUDE.md and architecture 01 still say "`glean` and `graph`" — stale) |
| Every `IN` list chunked by `membership()`; no statement grows with batch size | built (nine raw `.in_()` sites, all bounded) |
| Four engine legs in CI (`test-dialects.yml`, push and PR on storage paths) | built; MSSQL leg red on 2026-10-28 at the `apt` step |
| Schema lifecycle | refuse-and-re-provision only; `SCHEMA_FORMAT_VERSION = 23` vs ADR 020's "stays 1" |
| `CREATE SCHEMA` for host apps, bulk path by driver, privilege refusals classified | missing (spec 157 draft) |
| `install_extensions` | built (storage only; not reachable from the router) |
| 10k count pins | write, edges, glob, delete/restore, tombstoned read, graph; **none** for move, copy, mkdir, sweep, grep, glean, grants |
| Pool configuration | none; borrowed MSSQL factories skip `use_setinputsizes=False` |
| MariaDB guarded updates | per-row round trips (spec 080 researched) |
| ANN index provisioned | Postgres only; MariaDB/Oracle profiles say `ann`, run exact |

### Stories

#### D1 — The engine support matrix is a published, tested page · size S · gate b

*Why.* No page says what "supported" means, which versions, which
extras, which caps. A 0.1.0 host picks an engine off this table, so it
must be pinned to `PROFILES` and cannot drift.
*Depends on.* Decision D3 (MariaDB's tier), D18 (Oracle naming).
*Acceptance.*
1. `README.md` carries one row per `PROFILES` entry plus "any other
   SQLAlchemy dialect": driver extra, minimum server version, verbs
   served, vector tier (`ann`/`exact`), ANN index provisioned,
   arbitration, isolation pins, known caps (Oracle `IN` 1,000; SQL
   Server 2,100 binds and the 2,000 lock budget; MariaDB packet and row
   limits; pgvector 2,000 dims).
2. A docs-fence test asserts the matrix's dialect names equal
   `set(PROFILES) | {"generic"}` and each row's arbitration and vector
   cells equal the profile's fields.
3. CLAUDE.md and `architecture/01` say `glean` alone is withheld on the
   floor; `docker/README.md` and the `db_test` skill cite
   `tests/storage/test_conformance.py`; the dead `scripts/mssql_*.sh`
   are deleted.

#### D2 — Schema lifecycle: directional mismatch, a corruption kind, the migration registry · amends ADR 020 · size M · gate b

*Why.* Every format bump today strands any real database. 0.1.0 is
the commitment point ADR 020 named. The minimum honest story: the
refusal says which side is older; a garbage version row is corruption,
not mismatch; a registry exists so the first post-0.1.0 bump must ship
a path or fail a test. Full `ALTER` migrations are 0.2.
*Depends on.* Decision D19.
*Acceptance.*
1. A meta row at `SCHEMA_FORMAT_VERSION + 1` refuses `schema_mismatch`
   with `data["direction"] == "store_newer"`; at `− 1`, `"store_older"`
   naming the remedy; pinned on SQLite and every engine leg.
2. A meta table present with no row, or a non-integer version,
   classifies a corruption kind (D19), never `schema_mismatch`.
3. A migration registry of `(from, to, statements)` exists; a
   `SCHEMA_FORMAT_VERSION` bump without a matching entry fails a unit
   test; `migrate()` on a store one version behind applies the entry
   and the next first-touch adopts (DDL statements counted per bump).
4. ADR 020 is amended to record the pre-release bumps (1 → 23) and
   that the commitment point is `0.1.0b1`.
5. `docs/reference/storage.md` states the contract.

#### D3 — Provisioning for host apps · spec 157 · size M · gate b

*Why.* The first three things a production host hit (the SmartOwl
memo): `schema="vfs"` needs a hand-made schema; a psycopg session
factory crashes on the first bulk insert; a role without `CREATE` gets
`internal`.
*Depends on.* D2 (the vocabulary).
*Acceptance.*
1. `DatabaseStorage(url=postgres, schema="vfs_demo")` on a database
   with no such schema serves its first `write`; same on the SQL Server
   leg; on SQLite, MariaDB and Oracle first touch issues no schema
   statement (counted).
2. Through a role without `CREATE`, first touch refuses a classified
   kind with `data["schema"]` and `data["privilege"] == "CREATE"`,
   never a traceback.
3. `bulk_insert_mode(profile, dialect)` returns `"copy"` only when the
   driver is asyncpg; a `postgresql+psycopg://` leg runs the
   conformance contract and a 10,000-file write lands in `"core"` with
   ≥ 2 insert pages counted.
4. A borrowed `mssql+aioodbc` factory without `use_setinputsizes=False`
   is refused `invalid` at first touch naming the kwarg, or the host
   applies it; one of the two, pinned with a non-Latin1 path
   round-trip.
5. `fs.install_extensions(path)` (or an equivalent admin reach from the
   router) runs the storage's install for one mount; a no-op success
   on SQLite, the real install on Postgres.

#### D4 — Every verb has a 10k count pin, parametrized over the engine legs · size M · gate b

*Why.* The ETL contract is "10,000+ files in one call on every
dialect". Pins exist for six verbs; none for `move`, `copy`, `mkdir`,
`sweep`, `grep`, `glean`, `grant`, `revoke`. A count pin per verb is
the only thing that catches a builder regressing to per-row statements.
*Depends on.* Nothing.
*Acceptance.*
1. For each unpinned verb a `slow` test writes 10,000 entries and
   asserts the verb's statement count equals a declared `O(chunks)`
   formula with the chunk count from `membership_budget`.
2. Each pin is parametrized over `ENGINE_LEGS` with the real budgets
   (Oracle 1,000; SQL Server 2,000).
3. Under a monkeypatched `parameter_budget = 48`, every verb still
   returns the correct result.
4. The MariaDB leg records the per-row `UPDATE` count of a 10k
   overwrite as a known number, so spec 080 landing is a visible delta.

#### D5 — MariaDB set-based guarded updates · spec 080 · size M · gate 0.2 (or b if D3 keeps MariaDB first-tier)

*Why.* Correct and bounded today; a 10k overwrite is about 10k round
trips inside `REPEATABLE READ`. The research is done.
*Depends on.* Decision D3; D4's pin.
*Acceptance.* As spec 080 slice B: `ceil(N / rows_per_statement)`
statements counted; `CLIENT_FOUND_ROWS` asserted at first touch; the
conformance observations byte-identical; the other four engines'
counts unchanged.

#### D6 — The SQL Server leg is reliable and the four legs run from the published wheel · spec 166 item 5 · size M · gate f

*Why.* The latest run is red at `apt-get install msodbcsql18`; spec
166's final bar requires the legs to pass from the published wheel, and
no workflow does that today.
*Depends on.* R1, R2.
*Acceptance.*
1. The MSSQL job pins `ubuntu-24.04` or derives the package list from
   the runner's release; the next storage push is green on all four
   legs with per-leg pass counts in the commit body.
2. A `workflow_dispatch` input runs any leg against
   `pip install vfs-py==<version>` into a clean venv with no Rust and no
   C compiler on the runner.
3. The run against the last beta is recorded in the `0.1.0` release
   notes.

#### D7 — Pool and borrowed-host posture, per-engine how-tos · size M · gate f

*Why.* Notebooks, ETL processes and an MCP server are long-lived; the
engine today is `create_async_engine(url)` with defaults and no
guidance for borrowed factories.
*Depends on.* D3.
*Acceptance.*
1. Pool settings (size, overflow, pre-ping, recycle) are plumbed to
   `create_async_engine`; the `:memory:` path keeps `StaticPool`.
2. A test kills the connection between two ops on each engine leg and
   asserts the next op succeeds after exactly one `backend_unavailable`
   retry (retry spy).
3. `docs/how-to/` gains one page each for SQLite, Postgres, SQL Server
   and Oracle (URL, extra, provisioning privilege, the first-touch
   refusal when the vector function is absent), fence-tested where
   SQLite suffices.

---

## 8. Domain E — Search: glean with BM25 + vector, providers, renderers, graph

**Goal at 0.1.0.** `glean` fuses BM25 and vector at query time on every
supported engine, with a zero-config local embedder, two hosted adapters,
one spelling for configuring a provider from Python, a config file or
the command line, and quality pins on every engine leg. The query side
is built; this domain is about truth-telling, defaults and pins.

### State today

| Piece | State |
|---|---|
| Lexical leg (block postings scored in Rust) + vector leg (in-engine cosine per dialect) + client-side convex fusion | built on all five engines |
| Query-time embedding of the query string, 256-entry cache | built |
| Embed step at `reindex`: keyset pages, bounded batches, identity on the meta row, re-embed on model change at equal width | built |
| Without a provider: lexical-only with an info record; stale identity: lexical-only with `conflict`; embed failure: retryable `unavailable` | built |
| Default local model | **model2vec potion** shipped; ADR 060 says fastembed/MiniLM; no fastembed anywhere |
| Slow-provider convergence (120 s × 2,048 inputs) | **broken**: never converges under ~17 chunks/s |
| Provider by name/URL/env (for `serve()`, CLI, config) | missing |
| Width change on a native column | refuses "re-provision" |
| Ordered hybrid top-10 pin | SQLite and memory only |
| ADR 065 statistics-leak regression test | missing |
| `glean_staleness` trait | says `overlay` for both legs; true for BM25 only |
| Renderers pdf/docx/pptx/xlsx; failures as row states | built; images (152 C) and render-at-write (159) planned |
| `graph`: frontier walk, four methods, rights per hop; `fs` and markdown `links` edges | built; `imports` edges (147) planned |
| `docs/reference/api.md` glean content | **zero** |

### Stories

#### E1 — Settle the default local embedder · amends ADR 060 · size S (amend) or M (build fastembed) · gate b

*Why.* The accepted decision and the shipped code disagree. Theme 3
needs one documented answer to "install this, construct that". The
study measured MiniLM about two nDCG points ahead of potion and potion
about fifteen times faster and three times lighter.
*Depends on.* Decision D20.
*Acceptance.*
1. `vfs.embedding` exports exactly the providers the ADR names;
   `pyproject.toml`'s `embed-local` lists their packages; the
   seam-satisfaction test covers each.
2. The provider's `model_id` is `provider/model@dim` and the identity
   pin records its digest; the test skips with a printed reason when
   the model is not cached and never downloads.
3. `README.md` and `docs/how-to/configure-an-embedding-provider.md`
   show the one-line opt-in, fence-tested against `InMemoryStorage`.
4. No stale "fastembed" claim remains in a living page.

#### E2 — The embed step converges for slow providers · size M · gate b

*Why.* Any provider under about seventeen chunks a second never lands
a vector and every rerun repeats the identical failure; a hosted
provider at a low tier has the same shape; and a timed-out local batch
keeps a worker thread computing.
*Depends on.* Nothing.
*Acceptance.*
1. A scripted provider whose per-input latency makes a 2,048-input
   batch exceed the timeout still finishes `reindex` with
   `unembedded == 0`; assert on request count, not the clock.
2. A batch that times out is retried at a smaller size at most
   `log2(max_batch_inputs)` times before the step records
   `unavailable`; requests issued are pinned.
3. `LocalEmbeddingProvider.max_batch_inputs` defaults to ≤ 256 and the
   declared-caps pin is updated.
4. A timed-out local batch never leaves a worker computing past the
   next page (counted `embed_batch` calls after the timeout).

#### E3 — Provider configuration by name · size S · gate b

*Why.* `serve()`, the command line and a config file cannot pass a
Python object. One spelling —
`model2vec:minishlab/potion-base-8M`, `openai:text-embedding-3-small@1024`,
`hash:64`, `langchain:<dotted factory>` — plus env-var key resolution.
*Depends on.* E1; M2 is the consumer.
*Acceptance.*
1. `embedder_from_spec` parses the four schemes; an unknown scheme or
   a malformed `@dim` raises `ValueError` naming the schemes at
   construction time.
2. `openai:` resolves the key from the environment and refuses when
   absent; the test uses a fake transport.
3. The resulting provider's `model_id` equals the object form's for the
   same arguments (one parametrized test per scheme).

#### E4 — Hybrid determinism and quality pins on every engine · size M · gate b

*Why.* ADR 051 promised byte-identical rankings on all five engines;
the ordered hybrid pin runs only where cosine is sqlite-vec's.
*Depends on.* Nothing (engine legs via the `db_test` skill).
*Acceptance.*
1. The hybrid ordered top-10 pin is parametrized over `ENGINE_LEGS`
   with the 64-d hashing embedder; deselected when the URL is unset.
2. A fused-arm gate on the native golden set: `ndcg@10(fused) ≥
   ndcg@10(bm25) − GATE` with the local model cached; skips with a
   printed reason otherwise.
3. The vector-leg referee runs on each engine leg: the engine's
   top-`depth` order equals the Rust kernel's over the same rows (rows
   compared counted).
4. Each server leg reports `tier ∈ {native_exact, native_ann}` as the
   profile declares.

#### E5 — Close ADR 065's paperwork: the leak regression test and the honest staleness trait · size S · gate b

*Why.* The visible lexicon exists but nothing asserts a hidden row
cannot move a visible score; and the trait claims an overlay the vector
leg does not have.
*Depends on.* Nothing.
*Acceptance.*
1. A test hides half a corpus from `bob` and asserts every probe term's
   `df` and every visible row's score are identical whether the hidden
   half exists or has been deleted; the same holds under the generic
   floor's clause fan.
2. `traits()` says `glean_staleness` is `overlay` for the lexical leg
   and `reindex` for the vector leg; the protocol vocabulary and its
   drift test agree.

#### E6 — glean reference docs and the embedder how-to · size S · gate f

*Acceptance.* `api.md` documents `glean`'s parameters, the records
(`no_provider`, `stale_identity`, `embed_failed`, `truncated`), the
`legs` and `lexical_stats` extras, `Ranker`/`Convex`/`RRF`/`Signal`
and `install_extensions`; the how-to covers SQLite (nothing to
install), Postgres (`install_extensions`), SQL Server 2025 and Oracle
23.4+ prerequisites; every fence runs under the docs gate.

#### E7 — Width change is a migration, not a re-provision · size M · gate 0.2

*Why.* ADR 054 promised "reindex is the migration"; at a new width on a
native column first touch refuses and names re-provisioning. Valuable,
engine-specific DDL under the reindex lease; after D2's registry.

#### E8 — Render at write (159), images (152 C), `imports` edges (147), tuned fusion defaults · gate 0.2

Independent of theme 3. Render at write is the one an MCP-served agent
notices first (a PDF uploaded through the server is not `grep`-able
until `reindex`); it moves up if D21 says so.

---

## 9. Domain F — The shell

**Goal at 0.1.0.** An agent types `grep -rn mfa /enterprise | head -20`
through `VirtualFileSystem.cli` or `Session.cli` and every verb passes
the gate. The grammar is ADR 081's static subset: pipes, lists,
redirections, here-documents, variables, command substitution, globs
and braces admitted; `if`, `for`, functions, arithmetic, process
substitution, arrays and `&` refused at parse time with a classified
`unsupported.construct` naming the construct and its position. About 25
programs cover 87% of the measured corpus of 12,627 real agent calls.
The coverage number is published.

**What "fully functional" means here, honestly.** Not bash. The nine
commands that make 86% of agent pipeline segments, pipes in 74% of
calls, `&&` in 44%, control flow under 10%. Every program keeps its
Unix name and GNU flag semantics; the corpus orders which forms land
first. `awk` (the largest hole, 371 measured uses) needs a wasm host
and is out of 0.1.0 unless D22 says otherwise. `git`, `docker`, `uv`,
`sudo` never run and say so with a hint.

### State today

Nothing is built. `vfs.shell` does not exist; `crates/vfs-core` has no
`shell` module. Three live-tree gaps the shell depends on: a bytes row
renders empty, `to_payload` inlines base64 without bound, and the dead
`run` verb sits where `cli` goes. Spec 167 is five slices and twenty
tasks, reviewed before the build (score 48/100 as drafted, every
blocking finding folded in).

### Stories

#### F1 — The renderer gaps and the vocabulary · spec 167 slice A · size M · gate a

*Depends on.* Nothing (K9 removes `run`; whichever lands first).
*Acceptance.*
1. A bytes-sourced row renders `[binary <path> <mime> <size>B
   v<version>]` byte-for-byte in every arrangement; the rendering of a
   10,000-row result of bytes rows contains zero base64.
2. `to_payload()` carries no bytes; `to_payload(include_bytes=True)`
   round-trips with equality.
3. `to_str(budget=32_768)` cuts at a line boundary with exactly one
   marker naming characters removed and rows remaining, never cutting
   the errors section.

#### F2 — The parser · spec 167 slice B · size M · gate a

*Depends on.* Nothing (parallel with F1).
*Acceptance.*
1. The weighted 100-command corpus parses 86 of 100; each of the 14
   refusals is `vfs.unsupported.construct` with `line`, `column`,
   `construct` and the slice named in the hint.
2. Each malformed case (unclosed quote, unclosed here-document,
   trailing `|`, `&& &&`, stray `)`) is `vfs.invalid.syntax` with
   `line`, `column`, `offset`, `expected`, `incomplete`; exactly one
   error per call; a caret in the display.
3. The four parser budgets each classify `vfs.budget_exhausted` on a
   counted input (1 MiB + 1 byte; 100,001 tokens; depth 201; a brace
   expansion over `ITERATION_BUDGET`).
4. `&` is refused with a hint; `time -p` parses as a builtin.

#### F3 — The pipe, the ABI and `cli` with the minimal programs · spec 167 slice C · size XL · gate b

*Depends on.* F1, F2.
*Acceptance.*
1. `ls /nope | wc -l` prints `0` with `statuses == [[1, 0]]`,
   `exit_code == 0`, `success is False`, one `not_found`; `grep zzz f`
   and `false` succeed with `exit_code == 1`.
2. A 10,000-file `ls | wc -l` prints `10000` in 10 chunks at a maximum
   queue depth of 2 (counted); `head -3` on a 10,000-row producer
   closes after one chunk and the producer reports `vfs.cancelled` at
   info severity.
3. Every `Fs` call reaches a public router method with the admitted
   authority (spied: N calls, N matches); `vfs.shell` imports nothing
   from `vfs.storage`; two sessions with different authorities see
   different `ls /` through `cli`.
4. `cli` under the system actor is `invalid`; a 65-stage line is
   `invalid`; `sweep` and `posture` are `unrecognized` 127; `curl` is
   `unsupported` 126 with the network hint.
5. `cat img.png | wc -c` prints `size_bytes`; `cat a.png > b.png`
   leaves equal hashes; `cat img.png` alone prints one placeholder
   line.
6. `Session.cli` keeps `cwd` across calls; `VirtualFileSystem.cli`
   starts at `/` each call; `history` holds at most 1,000 entries.
7. The four engine legs are green.

#### F4 — The program forms, `replace=`, `glob(case_mode=)`, `set -e`, the never table · spec 167 slice D · size L · gate b

*Depends on.* F3; K1 (pin 17: which identity survives a replace).
*Acceptance.*
1. Every row of 167 §4.1 has a test against a committed GNU fixture;
   `ls -l` prints `kind size_bytes updated_at owner_id version`, never
   mode bits.
2. `move(src, dest, replace=True)` onto a file keeps the destination's
   `entry_id`, versions the replaced body and tombstones the source; a
   directory over a directory is `exists`; on all five engine legs.
3. `glob(case_mode="insensitive")` matches a case-folded Python filter
   on all legs in one statement per mount.
4. `set -e` stops at the first failing statement with every POSIX
   exemption pinned.
5. Each never-class name returns its kind, exit code and hint.
6. `rm -rf /` at a bind site is `busy`; elsewhere it tombstones with
   exactly one `delete(cascade=True)` call.

#### F5 — The coverage harness and `docs/reference/shell.md` · spec 167 slice E · size M · gate f

*Acceptance.*
1. The harness reports parse, resolve, flag and run rates on the
   synthesized corpus; the in-scope run rate is at least 85%; the
   number is printed in the README.
2. Fixtures come from one pinned-image script and are committed; tests
   never run bash.
3. `docs/reference/shell.md` lists the grammar, every program with its
   forms, the exit-code table (0, 1, 2, 75, 123, 124, 126, 127, 130,
   134, 137) and the refusal table.

#### F6 — Text kernels in Rust: `sort uniq tr tee` (168a), `xargs` and `find -exec` (168b) · size M + M · gate f

*Why.* Moves six names off Python and adds the four most-used missing
text programs; `xargs` is the one rows-to-verb form and what makes
`find -exec` run. `diff`/`cmp` (168c) can slip.
*Depends on.* F4; the Rust seam version bump.
*Acceptance.*
1. Parity tests pass for `head tail wc cut nl sed` against the slice-D
   Python transforms as oracles.
2. Every new kernel passes its GNU fixtures and the split law (whole,
   one byte at a time, random boundaries).
3. `cat f | sort | uniq -c | sort -rn | head -5` over 10,000 lines
   feeds 10 chunks, materializes each `sort` once, keeps queue depth
   ≤ 2 and reports the second `sort` cancelled (counted).
4. `find . -name '*.py' | xargs -n 10 grep -l TODO` over 25 files calls
   the `grep` verb 3 times; `xargs` returns 123 when a child exits 1.
5. `awk` and `jq` are `unrecognized` 127 with their hints; `cargo
   test -p vfs-core` green; the wheel budget holds.

---

## 10. Domain G — Tools: three kinds, one ABI, one permission structure

**Goal at 0.1.0.** Clay's three kinds map onto ADR 082's six:

| Clay's kind | ADR 082 kind | Lands in | Runs as | Gated by |
|---|---|---|---|---|
| (a) host-program tools, LangChain-shaped | **tool** | T3 (spec 170 §1) | the host's authority (ADR 084 pin 3's one exception); receives the caller's `Fs` only if it declares one | `read` on `/.vfs/tools/<name>` |
| (b) mounted MCP servers | **MCP tool** | T4 (spec 170 §3), I4 (per-principal credentials) | the credential the resolver returns for the caller | `read` on `/.vfs/mcp/<server>/tools/<tool>` |
| (c) CLI tools embedded or installed | **verb builtin**, **text program** (F3–F6); **program** (`.wasm`, T6 in 0.2); **skill** (read only); the `python` kind (T5) | F3–F6, T1, T5 | the caller, never more | the verb's own gate; `read` on the entry; install is `add` on the directory |

Every tool is a *path* an agent can see, grant and call. `cat` of a
tool shows its manifest and never runs it (the mcpfs lesson: `stat`
never executes). A tool runs only when typed as a command. All three
kinds interrupt the same way (H4).

### State today

Nothing is built. `/.agents` and `skills.py` exist and are slated for
retirement by ADR 082 pin 6. Spec 170 "needs one small study" whose
three pieces (a supervisor spike on 3.11/3.13, a real-server schema
census, a legacy-server probe) are an afternoon each and become T4's
first tasks.

### Stories

#### T1 — The `/.vfs` views, the index, union resolution, install rules · spec 169a · size L · gate b

*Depends on.* F3, F4.
*Acceptance.*
1. On a fresh node `ls /.vfs` lists `bin skills trash`; at a mount
   `ls /data/.vfs` lists `trash`.
2. `write`, `mkdir`, `move`, `copy` into any view path are `invalid`
   naming the writable index directories; `sweep /.vfs/trash` passes;
   `posture /.vfs/bin` lands in the root binding's grants table.
3. An unscoped `glob **` and `grep -r /` make zero calls into any view
   (spied); `mounts()` lists no view; `ls /.vfs/mounts` answers the
   mount table (closing the shell memo's gap 9).
4. The first resolution mints `/opt/bin` once as the system actor at
   posture `read` (one `mkdir`, one `posture`); an agent's write there
   is `permission_denied` without an `add` grant and `created` with
   one.
5. Resolving a name over a 10,000-file program directory is one `stat`
   dispatch per mount and zero `ls`; a masked name is `unsupported`
   126; a kernel name may not be shadowed unless in `prefer_stored`.
6. `/.agents` names are gone from `src/`; the four engine legs are
   green.

#### T2 — The `/.vfs/run` record · spec 169c · size S · gate b

*Acceptance.* After `cat a.txt | upper`, `read /.vfs/run/<id>/stdout`
returns the output and `…/status` names the program and
`content_hash`; another authority's read is `not_found`; eviction by
count (64) and bytes (64 MiB) is counted. Records are per process at
0.1.0; an HTTP server with several workers documents that links may not
resolve across workers (0.2 moves them to rows).

#### T3 — Host tools as files: `ToolView`, the schema-to-flags table, `_invoke` · spec 170 §1–2 · size L · gate b

*Depends on.* T1, T2; I3 for the rungs.
*Acceptance.*
1. A registered function (plain, async, and a LangChain `BaseTool` by
   shape — `name`, `description`, `args_schema`, `ainvoke` — without
   importing `langchain_core` outside its extra) appears at
   `/.vfs/tools/<name>` and in `/.vfs/bin` with `callable_kind=tool`;
   `<name> --x 1` calls it once (spied); `str` → one text row, `dict`
   → one JSON row, `None` → no row, a `Result` passes through.
2. Each row of the flag table has one passing call and one
   `vfs.invalid` exit 2 with zero tool calls; `cat f | upload` binds
   the body parameter; `--json` is the escape hatch.
3. `cat`, `stat`, `ls -l`, `grep -r . /.vfs/tools` issue zero tool
   calls; `type <name>` prints "runs on the host, with the host's
   authority (network: yes|no)".
4. `ToolError` → exit 1 with the message on stderr; a plain exception →
   exit 1 with the generic line and no detail; a tool past its
   deadline → `vfs.timeout` 124.
5. A tool declaring a parameter typed `Fs` receives the caller's `Fs`
   and nothing wider: a `write` through it to a path the caller cannot
   write is `permission_denied` (spied: the authority on the router
   call is the caller's).
6. The same tool is callable from Python (`fs.cli("name --x 1")`), the
   shell and the MCP front with one result shape.

#### T4 — MCP servers as views: `McpView`, the inbound block table, the supervisor · spec 170 §3–4, §7 · size L · gate b

*Depends on.* T3; M1's inbound adapter (or land it here).
*Acceptance.*
1. A connected in-process server appears under `/.vfs/mcp/<name>/`;
   one call yields a text row, a media row, a link row, an embedded
   text row and an unknown-block row under `/.vfs/run/<id>/<i>`;
   `isError` is exit 1 with its text on stderr and no minted kind.
2. Every row of the failure map produces its kind and exit: `-32602` →
   `invalid` 2; `-32601` → `not_found` 127; transport →
   `unavailable.backend` 1; wall → `timeout` 124; elicitation →
   `pending` (H4) once H1 lands, `unsupported` 126 until then.
3. `ls /.vfs/bin` twice in one `cli` call issues one `tools/list` per
   server; inside the list floor, zero (counted).
4. A stdio server killed mid-session: the call is `unavailable.backend`
   and the next call respawns exactly once; a call cancelled by the
   wall budget is issued once, never retried.
5. `VirtualFileSystem.close()` closes every view with no cross-task
   error on Python 3.11 and 3.13; `import vfs` works without the `mcp`
   extra.
6. Credentials never appear in the environment of a spawned stdio
   server.

#### T5 — The Python guest over wasi-python · spec 172 rewritten, ADR 086 amended · size M · gate a (stretch; not a final gate)

*Why.* The mechanism is proven twice (spike 173; the 2026-10-23 memo
ran wasi-python 0.1.0 over a vfs `Session` through public APIs only,
40 verbs). What remains is a thin adapter behind `vfs-py[python]`.
It ships when ready and does not gate final (D23).
*Depends on.* F3, F4 (`replace=`), T1 (resolution of `python3`); ADR
086 pins 1, 2, 4, 6, 7 rewritten from the memo.
*Acceptance.*
1. `python3 -c "import numpy, pandas"` runs with zero host preopens
   beyond the runner's stdlib zip and zero vfs grants.
2. The pandas CSV job completes with exit 0 in at most 21 verbs (the
   measured 17 `stat`, 2 `read`, 2 `write`; a stat cache lowers the
   bound and the test pins the new number).
3. A guest write on a read-only mount raises `EROFS` in the guest and
   the stage reports one `read_only` error although the guest exited
   0; `open("/.vfs/trash")` is `ENOENT` with zero verbs.
4. The same script as Alice (no grant) and Bob (`read` on `/secret`)
   gives `FileNotFoundError` and the body respectively.
5. `trapped == "deadline"` → 124; fuel or file-call exhaustion → 137;
   any other trap → 134.
6. `WASI_ERRNO` has one entry per `ErrorKind` (drift test); the guest
   tests are `slow`.

#### T6 — The generic wasm host, `/opt/bin` programs, `awk`, `jq`, uutils · spec 169b · size XL · gate 0.2

The only road to `awk` and to installing arbitrary programs as files;
it duplicates a preview1 host wasi-python's runner already owns.
Decision D22.

#### T7 — OAuth-on-demand for mounted servers · extends I4 · size L · gate 0.2

A caller with no credential for a server that returns 401 gets
`pending` carrying the authorization URL; completing the ledger entry
with the callback's code mints the token record for that principal.
An interrupt by construction; after H4 and I4.

---

## 11. Domain H — Serving vfs as an MCP server

**Goal at 0.1.0.** One command starts a server. Every agent-facing verb
is a tool, plus one `cli` tool. Rows cross the wire as MCP's five
content blocks and nothing else; `structuredContent` is the `Result`
payload without bytes. A token in, an `Authority` out. `pending` maps
to the protocol's `input_required`.

### State today

Nothing is built. Spec 171 is drafted and reviewed (verbs as tools +
`cli`; 21 tools on the default router; schemas from `PARAMS`, never
from signatures; the official SDK speaking 2026-07-28 and the legacy
handshake). Spec 171 decision 7 says "`serve()` only, no `vfs serve`"
because nothing says how to build a router from a URL; D24 reverses
that for 0.1.0. `docs/how-to/expose-over-mcp.md` is a six-line stub.

### Stories

#### M1 — The MCP adapter and `serve()` · spec 171 · size L · gate b

*Depends on.* F1 (placeholder, cap, `to_payload`), F3 (`cli`), I1, I2;
T2 for links to program output (degrades to placeholders without it).
*Acceptance.*
1. `tools/list` names exactly the `AGENT_OPS` verbs in
   `fs.capabilities()` plus `cli`: 21 on the default router, 19 on an
   unknown dialect, 1 with `tools={"cli"}`; no schema names
   `authority`, `observations` or `provenance`.
2. Over the `ls` tool on 10,000 files: the text block is at most
   32,768 characters plus the marker; `structuredContent` holds exactly
   the rows the text showed plus one `truncated` warning with the
   elided count; a 10,000-image result yields at most 8 typed blocks,
   4 MiB raw, 64 links; `structuredContent` carries no bytes and
   validates against `ResultPayload`.
3. `isError == not structuredContent["success"]`; `cli('grep nomatch
   f')` and `cli('false')` are `isError: false` with `exit_code == 1`;
   `cli('cd /notes')` then `cli('pwd')` prints `/`; `timeout_ms` above
   10,000 leaves the deadline at 10 s.
4. `resources/read` returns a blob with `mimeType` for a bytes row and
   the exact text for a text row; a row over 12 MiB is refused with
   zero bytes fetched; `vfs:///` URIs round-trip a space, `#`, `?`, `%`
   and a non-ASCII letter.
5. The wire validates against the vendored 2025-06-18, 2025-11-25 and
   2026-07-28 schemas; an older client gets links and audio flattened
   to placeholder text, never a refusal; the core install imports
   nothing from `mcp`.
6. `readOnlyHint`, `destructiveHint` and `idempotentHint` are derived
   from `ops.py` and K5's replay table; a verb with one non-idempotent
   form withholds the hint (D11).

#### M2 — The one-line entry point: `vfs serve` and `python -m vfs.mcp` · new · size M · gate b

*Why.* "Easy to serve" means a line a Claude Desktop, Codex or LangGraph
config can name, not `await serve(fs, …)` in a Python file. It needs a
router-from-URL constructor, which is small: a URL, an embedder spec
(E3), a workdir, an authority or a verifier.
*Depends on.* M1, E3, D3; decision D24.
*Acceptance.*
1. `[project.scripts] vfs = "vfs.cli:main"`; `vfs serve --url
   sqlite+aiosqlite:///x.db --transport stdio --as me` and `python -m
   vfs.mcp …` start a server whose `tools/list` equals M1's; `--embedder
   openai:text-embedding-3-small@1024` configures the mount.
2. Starting against an open mount exits non-zero naming it unless
   `--allow-open`; `--as system` exits non-zero before binding.
3. `vfs --help` works without the `mcp` extra (import-graph test); the
   subcommand set at 0.1.0 is `serve`, `sh` (one `cli` line or a REPL
   over a URL), `reindex`.
4. `docs/how-to/expose-over-mcp.md` has the steps and a Claude Desktop
   config block; the fences pass.

#### M3 — `pending` on the wire and the tasks question · amends spec 171 scope · size M · gate f

*Depends on.* H3, H4, M1.
*Acceptance.*
1. `serve()` surfaces `pending` as the protocol's `input_required`
   with an integrity-protected `requestState` carrying the principal,
   the TTL and the digest; a tampered `requestState` is refused
   `invalid` with zero handler calls (spied); a client on a revision
   without it gets the `pending` text and payload as a `complete` error
   result.
2. A resumed `tools/call` with `inputResponses` re-enters the gate from
   the top and runs once.
3. Whether a suspended `cli` line becomes a task (`tasks/get`,
   `tasks/update`) at 0.1.0 is decision D25; the default is no, and the
   SDK stack question is re-verified at build.

---

## 12. Domain I — Developer experience: sync, Jupyter, ETL, docs, examples

**Goal at 0.1.0.** A notebook cell and a plain script can use vfs with
sync calls and no event-loop ceremony. One import gets an ETL developer
`Entry`, a storage and a file system. A 10,000-row batch is one call,
atomic, bounded, pinned at the router. The docs have one tutorial, the
how-tos a host and a pipeline need, and reference pages for `Result`,
every verb and storage. The examples directory contains nothing that
imports a dead name.

### State today

| Piece | State |
|---|---|
| Every public verb `async def`; no sync facade | missing; a 25-line thread-loop prototype works in a script, in a real ipykernel, and over the in-memory backend (EXECUTED) |
| Top-level exports | `VirtualFileSystem` only; `Entry`, `DatabaseStorage`, `InMemoryStorage` are three modules away |
| 10,000-row `write(entries=)` | works: 49 statements (EXECUTED); pinned at storage level, not router level |
| Docs | 29 pages, 38 Sybil fences pass; 8 stub pages with no body; `api.md` covers identity and graph only; 5 pages off the nav |
| Examples | 5 of 9 import dead names (`DatabaseFileSystem`, `VFSClient`, `grover.*`); none run in CI |
| Install | `pip install vfs-py` gives 0.0.22, the old API; CONTRIBUTING and CLAUDE.md disagree on the setup recipe |

### Stories

#### X1 — `vfs.sync`: a synchronous facade for notebooks and scripts · new spec · size M · gate b

*Why.* The smallest correct design is a facade that owns a private
event loop on a daemon thread and forwards every verb to the one gate
through `run_coroutine_threadsafe`: about 100 lines, no new dependency,
no kernel change, a fourth front in ADR 087's sense (it stores no fact).
Greenlet (SQLAlchemy's bridge) is the inverse direction and would mean
a kernel rewrite; `anyio`'s portal is the same design plus a core
dependency; unasync codegen needs a whole sync storage path. The facade
constructs the `VirtualFileSystem` itself so first touch lands on its
loop (the asyncpg loop-affinity case); wrapping an already-awaited
async file system is documented as SQLite-only until pinned.
*Depends on.* Nothing in the kernel; lands after K4/K5 so its signature
test covers the new arguments once. Decisions D26, D27.
*Acceptance.*
1. `with SyncVirtualFileSystem(storage=InMemoryStorage()) as fs:
   fs.write(path="/a.txt", content="x"); fs.read("/a.txt")` returns
   `Result`s with `success is True` in a plain `python -c` with no
   running loop.
2. The same cells executed through a real ipykernel succeed while the
   kernel loop is running; no `RuntimeError`, no `nest_asyncio`.
3. A parity test asserts, for every verb and management method, that
   the sync signature equals the async one (names, kinds, defaults,
   order), and `SyncSession` matches `Session`; the facade exposes
   exactly `ALL_OPS` plus `MANAGEMENT_METHODS`.
4. A sync call issued from the facade's own loop thread returns a
   classified `invalid` naming the deadlock, never hangs.
5. `close()` and `__exit__` stop the loop thread (no `vfs-sync-loop`
   thread remains); a verb after close returns the router's `closed`
   error, not a raised exception.
6. On the Postgres leg, `SyncVirtualFileSystem(storage=DatabaseStorage(
   url="postgresql+asyncpg://…"))` serves `write` then `read` from a
   script whose main thread runs its own `asyncio.run` in between.
7. A 10,000-entry `fs.write(entries=...)` through the facade issues the
   same statement count as the async path; loop and thread creations
   are counted: one per facade, not per call.
8. `serve()` stays async-native (the facade is not used by the MCP
   front).

#### X2 — ETL ergonomics: top-level exports, iterables, a router-level 10k pin · size S · gate b

*Depends on.* X1. Decision D28.
*Acceptance.*
1. `from vfs import Entry, DatabaseStorage, InMemoryStorage,
   SyncVirtualFileSystem` imports; `__all__` lists them; the dependency
   walk still loads no numpy.
2. `fs.write(entries=(Entry(...) for _ in range(10_000)),
   parents=True)` (a generator) succeeds with the same statement count
   as a list.
3. A router-level pin counts statements for a 10k `write` through
   `VirtualFileSystem`, parents walk included, and asserts the count is
   independent of N beyond chunk arithmetic.

#### X3 — Getting-started tutorial, notebook how-to, pipeline how-to, human-in-the-loop how-to · size M · gate f

*Acceptance.*
1. `docs/tutorials/getting-started.md`: install → construct → write →
   `glob`/`grep`/`glean` → one rendered `Result`, every step a fence
   Sybil runs, no Postgres needed.
2. `docs/how-to/use-vfs-in-a-notebook.md` shows the sync and the
   `await` paths side by side and names the two `RuntimeError`s a user
   sees from `asyncio.run`.
3. `docs/how-to/bulk-load-from-a-pipeline.md`: a 10k batch from an
   iterable, the whole-batch-atomic rule, `reindex()` after binary
   writes and its `conflict` retry.
4. `docs/how-to/human-in-the-loop.md` (H3's example).
5. A test asserts every `docs/**/*.md` is referenced by the mkdocs nav;
   `mkdocs build --strict` passes.

#### X4 — Reference pages: `Result`, every verb, storage · size M · gate f

*Acceptance.*
1. `docs/reference/result.md`: `Result`, `Observation`, `ResultError`,
   the `ErrorKind` table generated from the enum (a test asserts every
   kind appears), `|` merging, `to_payload`/`from_payload`.
2. `docs/reference/verbs.md`: every public verb with its signature; a
   test asserts the set equals the live public surface (K9's list).
3. `docs/reference/storage.md`: constructor parameters, built vs
   borrowed, `install_extensions`, the schema contract (D2).
4. No page under `docs/` is a heading with no body.

#### X5 — Install page and the one setup recipe · size S · gate f

*Acceptance.* `docs/how-to/install.md` lists the extras (a test asserts
every `pyproject.toml` extra appears), the wheel platforms from
`publish.yml`, "no Rust toolchain on a listed platform", Python
3.11–3.14, and the Alpine note; `CONTRIBUTING.md` and
`docs/contributing.md` are one source using `uv sync --all-extras
--group dev`.

#### X6 — Examples: delete the dead, run the live · size S · gate b

*Acceptance.* The five notebooks and two scripts that import dead names
are removed (D29); `glean_walkthrough.ipynb` is executed in CI via
nbclient against the live tree; a test asserts no file under
`examples/` imports `vfs.backends`, `vfs.client`, `vfs.query`,
`sqlmodel` or `grover`.

---

## 13. Domain J — Release engineering and repository hygiene

**Goal at 0.1.0.** The lane runs: a version that can be a pre-release,
a publish matrix that has been dry-run, yanked dead numbers, a changelog
that starts over, a README that tells the truth, the standards describing
the tree that exists, and an active-spec set that equals the 0.1.0 work.

### State today

| Piece | State |
|---|---|
| `test.yml` (3.11–3.14; lint, format, types, 100% coverage, docs fences on 3.13) | green on `main` 2026-10-28 |
| `test-dialects.yml` (four engines from `docker/compose.test.yml`) | MSSQL red at the `apt` step |
| `publish.yml` seven-platform matrix | never run; no `workflow_dispatch`; no tag check; `macos-13` (retired) |
| PyPI | 0.0.20–0.0.22 present, none yanked; `pyproject` 0.0.22; `__init__` a literal copy; `uv.lock` 0.0.22 |
| `scripts/bump_version.py` | `\d+\.\d+\.\d+` only; cannot emit `0.1.0a1` |
| `CHANGELOG.md` `[Unreleased]` | pre-rebuild residue |
| README lines 19 and 135 | say PyPI ships the previous-generation API |
| Standards | `tooling.md` (hatchling, `uv pip`), `testing.md` *Running* (a file that does not exist), `release.md` (no pre-release stage), `roadmap.md` (this page's predecessor) all describe a tree that no longer exists; `versioning.md` pending since the constitution |
| Root-level strays | `ROADMAP-v0.1.0.md`, `write-pipeline.md`, `pr_description.md`, a SQLModel issue write-up, `coverage.json` (tracked, 2026-04-23), `grep_glob research/`, `business/`, `vfs-app/`, `vfs-brand/`, `logos/` |
| Context pipeline | 31 active specs; 165, 162, 152 A/B, 173 built but not archived; 161, 051, 102 overtaken; `STATUS.md` 1,168 lines and stale on 162 |

### Stories

#### R1 — Release plumbing · spec 166 items 1–4, decoupled from spec 167 · size S · gate a

*Acceptance.*
1. `vfs.__version__` is read from distribution metadata; a test pins
   equality.
2. `bump_version.py` parses with `packaging.version.Version`, gains
   `--pre {a,b,rc}`, `--final`, `--set`, refuses `b → a` and `--final`
   on a final, runs `uv lock`; a test drives every transition against a
   scratch `pyproject.toml`.
3. `publish.yml` has `workflow_dispatch` (publish skipped, wheels kept
   as artifacts); every job's first step fails on a release whose tag
   is not `v` + the project version; `macos-13 → macos-15-intel`;
   `maturin>=1.8.4,<2.0`; the Cargo comment says `vfs._native`.

#### R2 — Dry-run the matrix, fix the MSSQL leg, decide musl · size S · gate a

*Acceptance.*
1. A dispatched `publish.yml` run from `main` is green on all eight
   jobs; its run id and per-wheel sizes are in spec 166's landing notes.
2. The MSSQL leg installs the ODBC driver on the current runner; the
   next storage push is green on all four legs.
3. musllinux is decided (D30): the two jobs removed with a note, or
   kept with the README's Alpine warning.
4. Trusted publishing is confirmed configured (a note in `release.md`).

#### R3 — Cut `0.1.0a1` from the tree as it stands · spec 166 items 5–9 · size S · gate a

*Acceptance.*
1. `CHANGELOG.md` has no pre-rebuild `[Unreleased]` content;
   `[0.1.0a1] — <date>` lists the verbs, backends, dialects, the ladder,
   the graph walk, trash-as-tombstone, binary bodies, with a *Breaking*
   group saying nothing from 0.0.x carries over.
2. README lines 19 and 135 no longer say PyPI ships the old API; pin
   guidance reads `vfs-py>=0.1.0a1,<0.2` with the one-line reason; the
   Alpine note is present.
3. 0.0.20, 0.0.21, 0.0.22 are yanked on PyPI with spec 166's reason;
   the three GitHub release bodies carry the same line.
4. On `python:3.13-slim` x86_64 and aarch64: `pip install vfs-py`
   installs `0.1.0a1` and `import vfs, vfs.native` works; `pip install
   "vfs-py<0.2"` fails with no matching distribution; `==0.0.22`
   installs with a yank warning.

#### R4 — The engine legs from the published wheel · size S · gate f

Same as D6's items 2–3; listed here because it is the lane's final
gate.

#### R5 — Freeze the surface: the beta-entry decision · size S · gate b

*Acceptance.*
1. K9's list exists and `docs/reference/api.md` matches it.
2. ADR 087's pins 3, 12, 16, 17 and spec 174's `overwrite=` question are
   resolved (K1).
3. Every active spec is tagged `0.1.0` or `0.2.0+`; none tagged
   `0.2.0+` changes a frozen name.
4. Clay's freeze call is a dated line in `release.md` and in the
   `[0.1.0b1]` changelog section; the classifier reads Beta.
5. `context/standards/versioning.md` exists: what a breaking change is
   in `0.x`, the deprecation window, what the changelog's *Breaking*
   group must say.

#### R6 — Repository hygiene · size S · gate b

*Acceptance.*
1. The root holds only `CHANGELOG.md CLAUDE.md CONTRIBUTING.md
   Cargo.lock Cargo.toml LICENSE README.md conftest.py mkdocs.yml
   pyproject.toml uv.lock` plus dot-files and directories.
   Dispositions (D31): delete `ROADMAP-v0.1.0.md`, `write-pipeline.md`,
   `pr_description.md`, the SQLModel write-up, `coverage.json` (and
   ignore it); move `grep_glob research/` to
   `context/research/2026-04-24-grep-glob-pushdown/`; move `business/`
   under `context/product/` or a sibling repo; move `vfs-app/`,
   `vfs-brand/` and `logos/` to their own repo or under `vfs-app/`.
2. `tooling.md`, `testing.md` *Running*, `release.md`, `CONTRIBUTING.md`
   and `tests/conftest.py`'s docstring describe the maturin / `uv
   sync` / env-URL tree.
3. `src2/` and `tests2/` are deleted or shrunk with a dated note of
   what remains unmined (D32).
4. The four headlines (README "Governed data access"; `docs/index.md`
   "Agentic Search on your Database"; `mission.md` "the agentic
   filesystem"; "true file system") are reconciled to ADR 075's line
   everywhere a reader lands.
5. The README gains a one-paragraph "when not to use vfs" (ADR 069 pin
   6) and a short `THREAT_MODEL.md` stating ADR 087's three trust
   tiers.

#### R7 — Context-pipeline true-up · size S · gate b

*Acceptance.*
1. Specs 165, 162, 152 (A/B closed; C/D re-cut or tagged 0.2), 173 move
   to `specs/archive/` with landing notes; their stale "uncommitted"
   lines are corrected first.
2. Spec 161 is dropped (write half landed in 162; read half is K8);
   spec 051 is replaced by H5; spec 102 is closed as overtaken by the
   tombstone delete or re-cut against `move`/`copy` at 10k; spec 080 is
   tagged per D3.
3. `STATUS.md` is replaced by a table of at most 60 lines (spec,
   status, gate, landing commit) regenerated from the spec status
   lines; the history moves to a dated research memo or is deleted.
4. The ten proposed ADRs (022, 058, 069, 081–087) are each ratified,
   amended or withdrawn; pending leans are zero before `0.1.0b1`.
5. `open-questions.md` entries resolved by landed work move to the
   archive; the "what makes 0.1.0 final" entry is answered by D2.

---

## 14. Sequencing: alpha batches and the dependency chain

The order is dependency-driven, then harm-driven. Stories within a
batch are independent of each other unless an arrow says otherwise.
Sizes sum per batch so Clay can see the shape; they are the audits'
estimates (S ≤ 1 day, M 2–4 days, L 1–2 weeks, XL > 2 weeks of agent
effort) and are not commitments.

| Alpha | Carries | Why this order |
|---|---|---|
| **a1** (this week) | R1, R2, R3 | The lane must exist before anything rides it. Nothing feature-shaped. |
| **a2** — the three defects | K1 → K2, K3, K5; H1; F1, F2; I6; R6, R7 | The ADRs are ratified first because eight specs and every HITL story stand on them. K2/K3/K5 close the three live defects. F1/F2 are independent and small. Hygiene clears the ground. |
| **a3** — the filesystem arguments | K4, K6, K9; H2; D1, D2, D3, D4; E1, E2, E3, E5; X1, X2, X6; I5 | Cursor, range, the regroup and the freeze list. `plan=` rides the write seam. Storage lifecycle and the engine matrix. Search defaults. The sync facade and exports. |
| **a4** — the shell | F3 → F4; I1; E4 | The pipe and the programs are the long pole (XL + L). The trust edge lands in parallel. |
| **a5** — tools and the front | T1 → T2 → T3 → T4; I2, I3; M1 → M2 | Views, host tools, MCP servers, the adapter, the one-line serve. |
| **a6** — the human in the loop, end to end | H3 → H4; I4; M3; H5 | The ledger, resume for every kind, the wire mapping, cancellation. |
| **b1** — freeze | R5; K7, K8; F5, F6; D6, D7; E6; X3, X4, X5; T5 (if ready) | Nothing after b1 changes a public name. |
| **0.1.0** | A beta held ≥ 14 days; D6/R4 green from the wheel; every `f` story landed. | |

**The critical path**, in one line: K1 → K2/K5 → F3 → F4 → T1 → T3 →
T4 → M1 → H3 → H4. Five L or XL items in series; everything else
runs beside them.

**Where the kernel specs and the shell specs touch.** Spec 167 as
drafted ships a racy `>>` and a `stat`-then-`write` `touch`; spec 174
replaces both. This page orders K2 (174) before F3 (167 C) so the shell
never ships the racy forms (D33). The one flag name is `replace=`.

---

## 15. Deliberately not in 0.1.0

Each item has a landing place so a slip is a tag change, not a scramble.

| Item | Where it goes | Why not now |
|---|---|---|
| `pack` (cold versions to deltas), the bounded `sweep`, the garbage gauge (spec 180's rest) | 0.2 | Correct without them; the full history is kept; K8's read side is what the headline needs. |
| `scrub` (spec 175 slice D) | 0.2 | Report-only; needs K4; nobody is asking yet. |
| The generic wasm host, `awk`, `jq`, uutils (T6) | 0.2 unless D22 | XL; duplicates a host wasi-python owns. |
| OAuth-on-demand for mounted servers (T7); token exchange; enterprise-managed authorization | 0.2 | One shipping IdP; I4's seam is enough to "act as the user" with host-held credentials. |
| `manage` rung, group ownership, non-system membership admin | 0.2 | Parked open questions; not needed to serve one organisation. |
| Narrowing with content, child sessions (spec 148 §1–4) | 0.2 | ADR 063 is law and `Narrowing.NONE` is honest; sub-agents can use a second `Session`. |
| Width-change migration (E7), tuned fusion defaults, render at write (159), images (152 C), `imports` edges (147), signals on by default | 0.2 unless D21 | Independent of theme 3; the matrix and the trait say what is true. |
| `/.vfs/run` records as rows; `/.vfs/jobs`; MCP tasks for long `cli` lines | 0.2 | Per-process records are honest at 0.1.0 and documented. |
| A local-disk storage backend; a change feed; OpenTelemetry spans; an object-store data plane; reference adapters for host frameworks | 0.2+ | The wedge is "the database you already run"; adapters need `serve()` first. |
| FUSE or NFS fronts | later | A facet by ADR 087; the copy never promises it at 0.1.0. |
| Diff/cmp kernels (168c) | 0.1.x | Can slip without changing a name. |
| The WASI Python guest (T5) | 0.1.x if not ready at b1 | Stretch; behind an extra; not a gate. |

---

## 16. Decisions Clay must make

Each has a lean. A lean is the assistant's recommendation, not a
decision. The gate column says when the answer is needed.

| # | Decision | Lean | Needed by |
|---|---|---|---|
| D1 | `0.1.0a1` ships the tree as it stands, decoupled from spec 167 (reversing the 2026-10-15 amendment)? | Yes; the shell is a4. | a1 |
| D2 | What makes `0.1.0` final: the held-beta bar alone, or the bar plus the `f`-tagged feature gate on this page? | The bar plus the gate: the headline needs `serve()`, the shell core, tools and the human in the loop. | before b1 |
| D3 | MariaDB: first tier (in the final gate, spec 080 lands), second tier (served, in CI, no ANN, per-row updates documented), or dropped? | Second tier. Dropping loses the only real-engine exercise of `redrive`. | D1 |
| D4 | ADR 087 pin 3: keep `delete`/`move`, or rename `remove`/`rename`? | Keep; a POSIX front spells its own names. | K1 |
| D5 | ADR 087 pin 16: flat names, or kernel groups as namespaces? | Flat. | K1 |
| D6 | ADR 087 pin 12: the resumption key as a `Result` field, or a separate return? | A field. | K1, K4 |
| D7 | Spec 174: `overwrite=` leaves `write` (since `if_absent=True` is today's `overwrite=False`)? | Yes. | K2 |
| D8 | ADR 087 pin 9: an integrity failure is its own kind or rides `unavailable`; and the 100 KB offload threshold. | Its own kind (`vfs.integrity`); keep 100 KB. | K3 |
| D9 | Amend ADR 084 pin 4 so vfs *carries* `pending` (never asks, never blocks)? | Yes. Spec 148 already designed it. | H1 |
| D10 | `pending`'s shape: top-level `vfs.pending` with `RetryClass.resume`, or a child of `permission_denied`? Ledger in the mount's schema or the router? TTL? | Top-level kind (it also covers a tool's own question); in the mount's schema beside the replay store; 24 h. | H1 |
| D11 | ADR 087 pin 10: withhold `idempotentHint` from a tool whose verb has one non-idempotent form? | Withhold. | K5, M1 |
| D12 | The exit code for a suspended shell stage. | 75 (`EX_TEMPFAIL`). | H4 |
| D13 | Spec 149: ignore a `groups` claim, or verify it against memberships? | Ignore; groups are rows. | I1 |
| D14 | Spec 149: add an `attested` provenance for a subject set a trusted subsystem names as data? | Add it. | I1 |
| D15 | What "open" means on the ladder for the `serve()` refusal. | Refuse when any mount's root everyone-level is `add` or above; `read` and `list` serve without a flag. | I2 |
| D16 | MCP servers as the user: a host-supplied credential resolver (a), a vfs-owned credential store (b), or token exchange at the edge (c)? Subject sets over a per-user server? | (a) at 0.1.0, (b) as a later reference, never (c) inside `Authority`. Refuse subject sets. | I4 |
| D17 | Validate declared owners and refuse `*`, `anon`, `system`, `group:`; keep group ownership parked; make the default-authority fallback loud? | Yes to all three. | I6 |
| D18 | Oracle naming in the matrix: "23ai" or the image's "26ai Free 23.26"; floor 23.4+. | Name the floor 23.4+ and quote the image string. | D1 |
| D19 | From `0.1.0b1`: refuse-and-re-provision with a registry (D2 as written) or a full `migrate` now? A corrupt version row is `internal` or a new `corruption` kind? | D2 as written; a new kind. | D2 |
| D20 | Default local embedder: amend ADR 060 to model2vec potion (shipped), or build fastembed/MiniLM? | Amend; keep fastembed as a documented LangChain route. | E1 |
| D21 | Render at write (159) in 0.1.0? | No, unless the first MCP-served pilot hits it. | E8 |
| D22 | Build the generic wasm host (169b) for `awk`, ask wasi_python to host generic modules, or ship without `awk`? | Ship without; refuse with a hint; ask wasi_python in parallel. | T6 |
| D23 | The Python guest (T5): a 0.1.0 gate, a stretch item, or 0.2? | Stretch behind `vfs-py[python]`; not a gate. | b1 |
| D24 | Reverse spec 171 decision 7: ship `vfs serve` and `python -m vfs.mcp` at 0.1.0? | Yes. "Easy to serve" is a theme. | M2 |
| D25 | Does a suspended `cli` line become an MCP task at 0.1.0? | No; `pending` ends the call; tasks are 0.2. | M3 |
| D26 | Sync facade: the thread-loop facade (no dependency) or `anyio`'s portal? | Thread-loop. | X1 |
| D27 | May the facade wrap an already-awaited async file system? | Yes, documented SQLite-only until the asyncpg leg pins it. | X1 |
| D28 | Top-level exports `Entry`, `DatabaseStorage`, `InMemoryStorage`, `SyncVirtualFileSystem`? | Yes. | X2 |
| D29 | Stale notebooks: delete, or archive beside `src2/`? | Delete; git keeps them. | X6 |
| D30 | musllinux wheels: keep publishing wheels that cannot install, or drop the two jobs? | Drop; note it. | R2 |
| D31 | Where `business/`, `vfs-app/`, `vfs-brand/`, `logos/` live. | Sibling repos; `business/` under `context/product/` if it must stay. | R6 |
| D32 | Delete `src2/` and `tests2/`, or keep shrinking? | Delete what `MINING.md` marks mined; list the rest with a date. | R6 |
| D33 | Order: K2 (174) before F3 (167 C), so the shell never ships the racy `>>`? | Yes. | a2 |
| D34 | The 0.1.0 program table: all of 167, 168a and 168b in; 168c, `awk`, `jq` out; shell spellings for `grant`, `edit`, `mkedge` (today `unrecognized` with a hint)? | As stated; add `grant`/`revoke`/`grants` spellings in F4 so the shell can set what tools need. | F4 |
| D35 | Where this page lives: here (`context/standards/roadmap.md`), with the root `ROADMAP-v0.1.0.md` deleted? | Yes. | R6 |

---

## 17. One-line version

Ship `0.1.0a1` this week from the tree as it is; close the three live
defects and ratify the kernel; land the cursor, the range, the
preconditions and `plan=`; build the shell, then the tools, then the
front, then the human in the loop; freeze when every public name is
written down; call it `0.1.0` when a beta has held and the four engines
pass from the wheel.
