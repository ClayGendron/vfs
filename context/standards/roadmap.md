# Roadmap — vfs 0.1.0: the definition of done, by domain

- **Status:** draft for Clay's review, fourth revision — 2026-10-28,
  written against `main` at `90f5883`. The fourth revision carries
  four changes Clay asked for on 2026-10-28, after reading the third:
  the shell speaks the whole bash language, not a subset (§1.3, §9,
  F7; amends ADR 081); a JavaScript guest beside the Python guest,
  both optional (T5a, T5b); a session that remembers what it read and
  guards the write for the developer (K10); and an action log of every
  call vfs makes — who, what, how many rows, how long — that is the
  analytics table and the checkpointer the durable run resumes from
  (H0, with the spike L0 that prices it). The third revision carried
  three audiences (§1.2), bash and Python in 0.1.0, the kernel stories
  as user stories (§4) and the durable run (domain B, H4). Replaces the
  "Plan 9 wave"
  roadmap (specs 015–024, all landed and archived) and the root-level
  `ROADMAP-v0.1.0.md` of 2026-05-18 (a pre-rebuild plan for a FastAPI
  service, SSO and a web console; none of it applies). Supersedes no
  ADR and no spec: where this page and a decision record disagree, the
  record wins and this page is wrong.
- **Owner:** Clay Gendron
- **Purpose:** One place that says what "0.1.0 is done" means, domain
  by domain, as stories a single developer can pick up, each with
  acceptance criteria a test can pin. It also says what 0.1.0 is *not*,
  so a slip has a pre-agreed landing place (the `0.x` lane) instead of a
  scramble.
- **Method:** eight read-only audits of the live tree, the active specs
  and the decision record, then three reviews of the first draft (a PM
  review, an acceptance-criteria review, a fact-check). All eleven
  files are in
  `../research/studies/2026-10-28-the-0-1-0-roadmap-audits/`; a fourth
  review, of the durable-run design (file 12), shaped the third
  revision. The fourth revision stands on no new study: it is Clay's
  feedback on the third, and the one measurement it needs (the cost of
  logging every call) is commissioned as L0. Every
  claim there is labelled READ, EXECUTED or INFERRED; this page repeats
  the executed findings where they bind a story. Nothing on this page
  is a decision; §16 lists the decisions Clay must make, each with a
  lean.

---

## 0. How to read this page

Short version first. The long version follows.

- **0.1.0 is a promise, not a date.** The promise is three sentences in
  §1. Every story on this page exists to make one of them true.
- **The lane is spec 166's.** Alphas now. Betas when the public
  surface stops moving. Final when a beta has held. §2 names the three
  gates and what each waits for.
- **The work is grouped by domain, §4 to §13.** Each domain opens with
  a table of what is built today, then its stories. A story has an ID
  (`K1`, `H2`, …), the spec it lands if one exists, a size, a gate, a
  short *why*, its dependencies, and acceptance criteria.
- **Gate tags.** `a` = rides any alpha, not a gate item. `b` = must land
  before the beta freeze. `f` = must land before final. `0.2` = after.
  The beta freeze is defined in §2: no rename, no removal, no change of
  meaning; *additive* names are still allowed in a beta and are listed
  under *Added* (decision D2).
- **Stories open with a user story** where the heading alone does not
  say what a person gets: "As an agent / software developer / ETL
  developer, I want …, so that …". Every kernel story (§4) and every
  human-in-the-loop story (§5) has one; the functionality enabled is
  the point, the mechanism is the *why*.
- **Sizes** are the audits' estimates of agent effort: S ≤ 1 day, M
  2–4 days, L 1–2 weeks, XL > 2 weeks. They are not commitments. §14
  adds them up.
- **Acceptance criteria count operations, never clocks.** A criterion
  names statements issued, rows fetched, calls spied, a classified
  error kind, an exit code, or an engine leg. This is the repo's own
  rule (CLAUDE.md, *Performance tests*). A criterion that is CI
  evidence rather than a test says so.
- **Engine legs.** An *engine leg* is one of the four
  `VFS_TEST_<ENGINE>_URL` legs — Postgres, MariaDB, SQL Server, Oracle
  — deselected by `tests/conftest.py` when its URL is unset. SQLite and
  the in-memory backend always run. "On SQLite and on each engine leg"
  means all five.
- **§14 is the sequencing and the capacity arithmetic. §15 is the cut
  list. §16 is the decision list.**

One line: this page turns "we are relatively close" into a checklist
with a gate on every item and a sum at the bottom.

---

## 1. What 0.1.0 is

### 1.1 The promise, in three sentences

Each sentence is written to be true on the day `0.1.0` ships. Under
each is what must land first.

1. **vfs 0.1.0 is governed data access for AI agents, with the
   interface of a file system, over the SQL database you already run —
   SQLite, Postgres, SQL Server and Oracle, with MariaDB served as a
   second tier — where every read, search and write passes one gate
   that judges the caller's rights on every row it touches, and every
   tool call is gated at its entry. On the wire and inside a guest the
   gate is a wall. In process it is a convention your host code agrees
   to; the threat model says so.**
   *True today for files on all five engines: the gate, the ladder and
   row grants are built and green. True for tools when the program
   table and the `/.vfs` views land (domains F and G). The threat model
   is R8.*
2. **Agents reach it as the interface they already know — `ls`, `cat`,
   `grep`, pipes, `for`, `if`, functions — from Python (sync or
   async), from a bash shell that speaks the whole language, from a
   Python or JavaScript program running inside vfs, or over MCP, with
   `glob`, `grep`, ranked `glean` and `graph` built in and scoped to
   what the caller may see.**
   *The search half is built. The sync facade (X1), the shell (F1–F7),
   the two guests (T5a, T5b) and `serve()` (M1–M2) are not.*
3. **Every body change is versioned and every delete is reversible. A
   session remembers what its agent read, so a write over a changed
   file is refused without the developer carrying a version. An
   action can be stopped before it happens and become a question a
   human answers — for vfs's own mutations, with a preview of what the
   world will look like if they say yes — and a run with several such
   questions picks up where it stopped, never from the top. One
   permission structure governs a file and a tool alike, and every
   call vfs makes is a row in the database you already run: who, what,
   how many rows, how long.**
   *Trash and restore are built. Version rows exist for replaced
   bodies; nothing reads them back yet (K8). The session's memory is
   K10. The stop, the preview, the durable run and the resume are
   domain B; the action log they stand on is H0. "A file and a tool
   alike" is I3.*

### 1.2 Who it is for

Three audiences, all first-class (Clay, 2026-10-28; CLAUDE.md's
*Production posture* names the first and third and is updated in R7):

- **Agents** making many small calls in a loop, many at once, through
  the shell, the verbs or MCP. They care about latency, about never
  being lied to by a result, and about a question they raise being
  answered without losing their place.
- **Software developers** building the host: the application that
  mounts storage, sets posture, registers tools, writes the policy
  hook, mounts MCP servers, runs `serve()` and embeds vfs in LangGraph
  or their own loop. They care about one small public surface, one
  approval flow for everything an agent can run, a session that
  carries read-then-write safety for them (K10), a log they can point
  a dashboard at (H0), and errors that are classified rather than
  raised. Most of domains B, C, G, H and I are for them.
- **ETL developers and pipelines** making few large calls: ten
  thousand files in one `write`, on a real engine, from a notebook or
  a scheduled job. They care about batches being bounded and atomic,
  about a sync entry point that works in a notebook, and about a long
  run that stops for an approval resuming where it stopped.

### 1.3 What 0.1.0 is not

Said once here so nobody re-argues it (details in §15):

- Not a POSIX file system. No FUSE or NFS front, no handles, no mode
  bits (ADR 087 pins 1 and 4). `entry_id` appears on `stat` as an
  identity you can read, never an address you can use. The public copy
  says "the interface of a file system", never "mount it on your
  laptop".
- Not a job-control shell, and not a host for programs vfs cannot
  gate. The shell speaks bash — the whole language: pipes, lists,
  redirects, here-documents, `for`, `while`, `if`, `case`, functions,
  arithmetic, arrays, the parameter operators, process substitution
  (Clay, 2026-10-28: "full bash, so it is an expressive language, with
  everything that could be useful to vfs in it"; this reverses the
  2026-10-15 subset and amends ADR 081 pins 4, 8 and 12 in F7). What
  is refused is only what has no meaning inside one gated call: job
  control past the call (`jobs`, `fg`, `bg`, `disown`, `nohup`),
  dynamic evaluation (`eval`), process replacement (`exec`), signals
  (`trap`). Each refusal is a classified fact that names its reason.
  Programs the host machine has and vfs does not (`git`, `docker`,
  `uv`, `sudo`, `curl`) never run and say so; `awk` and `jq` wait on
  D22. The copy says "bash" and publishes two numbers: the corpus run
  rate (F5) and the Oils spec-suite rate for the admitted constructs
  (F7).
- Not a web console, not SSO, not an OpenTelemetry exporter, not a
  managed service. Those are the product plan's, not the library's.
  The data an exporter would carry is the action log (H0); the
  exporter is 0.2.
- Not a host-side `exec`. Python and JavaScript at 0.1.0 are WASI
  guests (T5a, T5b, gate b): a static CPython with numpy and pandas
  compiled in, and QuickJS-NG, each whose only file system is vfs and
  whose every host call passes the gate as the caller. Both are in
  0.1.0 (Clay, 2026-10-28), each behind its own extra (`vfs-py[python]`,
  `vfs-py[javascript]`) so the base wheel stays small. The guests are
  for numpy, pandas and the JavaScript ecosystem's shapes, not for
  control flow; the shell has that.
- Not "MCP servers as the user" in the OAuth sense at 0.1.0. The
  credential seam (I4) is per principal with host-held credentials;
  the OAuth round trip is T7 in 0.2. The README does not use the
  phrase until then.

---

## 2. The release lane and its three gates

Spec 166 defines the lane. This section says what each gate waits for.
An **alpha** may break anything. A **beta** may fix, and may *add*
names that are listed under *Added*, but may not rename, remove or
change the meaning of a public name (decision D2; `versioning.md`, R5,
writes this down). A **final** changes nothing until `0.1.1` or
`0.2.0`.

| Gate | Enters when |
|---|---|
| **`0.1.0a1`** | This week, from the tree as it stands, decoupled from the shell. The 2026-10-15 amendment that tied a1 to spec 167 is reversed by decision D1. Carries R1–R3. |
| **`0.1.0aN`** | One alpha per landed batch, cut by hand (§14 proposes the batches). |
| **`0.1.0b1`** — *the surface is frozen* | Every `b` story has landed; the frozen surface is written down (K9); every "proposed" ADR is ratified, amended or withdrawn (R7); Clay calls the freeze with a dated line (R5). |
| **`0.1.0`** — *a beta has held* | Spec 166 decision 5's bar (one beta current ≥ 14 days with no breaking fix; the engine legs green **from the published wheel**, D6) **plus** every `f` story. Decision D2 confirms the feature gate is this list and not the bar alone. |

**The gate list, generated from the story headings.** (`a` stories are
not listed; they ride any alpha.)

| Domain | `b` (before the freeze) | `f` (before final) |
|---|---|---|
| A Kernel | K1, K2, K3, K4, K5, K6, K9, K10 | K7, K8 |
| B Human in the loop | H0, H1, H2, H3, H4, H5 | H6 |
| C Identity | I1, I2, I3a, I3b, I6 | I4 |
| D Storage | D1, D2, D3, D4 | D6, D7 |
| E Search | E1, E2, E3, E4, E5 | E6 |
| F Shell | F3, F4, F7 | F5, F6 |
| G Tools | T1, T2, T3, T4, T5a, T5b | — |
| H MCP front | M1, M2 | M3 |
| I Developer experience | X1, X2, X6, X7 | X3, X4, X5 |
| J Release and hygiene | R5, R6, R7, R8 | R4, R9 |

---

## 3. State of the tree, in one table

"Built" means on `main` with tests green. "Drafted" means a spec
exists and nothing has started. "Missing" means neither. Evidence is
from the audit set; EXECUTED unless noted.

| # | Theme | State |
|---|---|---|
| 1 | Public kernel API | **Built** as 25 async verbs behind one gate (`base.py:2835–3088`; `tests/test_ops.py:246` pins `ALL_OPS`). **None** of ADR 087's arguments exist: no cursor, no `range=`, no `if_version=`, no `replace=`, no request key, no `versions`. All three ADR 087 probes still reproduce on SQLite: twenty concurrent appends keep one line; a body changed by raw SQL reads as success; a replayed `move` is a bare `not_found` with no data. |
| 1 | Interrupts | **Missing**, and the record contradicts itself: ADR 063 rule 5 and specs 148/149 define a `pending` kind and an ask ledger; the later ADR 084 pin 4 says "no `ask` inside vfs"; spec 170 maps a server's elicitation to `unsupported`. `cancelled` and `timeout` are declared kinds with no producer in `src/`. No run ledger exists; spec 169c's `/.vfs/run` record is per process by design. |
| 2 | SQLite, Postgres, MSSQL, Oracle | **Built**, plus MariaDB and a generic floor (`dialects.py:389–561`). All four engine legs green together on 2026-10-15 (`ac5c515`). On 2026-10-28 the MSSQL leg is red at its `apt` step (run 40689014566; the tests never ran), so the five `fix(storage)` and one `perf(base)` commits of 2026-10-24 have no SQL Server evidence. No migration story: a format mismatch refuses "re-provision". |
| 3 | Embedding provider, BM25 + vector | **Built**: query-time embedding of the query, lexical and vector legs, client-side convex fusion, four providers (hashing, model2vec, OpenAI, LangChain), vectors built at `reindex` (`backend.py:554–687`, `glean.py:215–513`). ADR 060's fastembed/MiniLM default was never built. A slow provider never converges (120 s per request × 2,048-input batches). |
| 4 | Three tool kinds | **Missing**. `run` is a routed verb no storage serves. Specs 169/170 drafted. "MCP servers authenticating as the user" is undecided; spec 170 §3.1 pins the opposite (one host credential per server). |
| 5 | Sync calls, Jupyter, ETL | **Missing** sync facade. `asyncio.run` fails inside a running loop (reproduced). A 25-line thread-loop prototype works in a script and over the in-memory backend (audit 06). A 10,000-row `write` lands in 35–49 statements on SQLite depending on whether the parent exists and how the hook counts. |
| 6 | Serve vfs as MCP | **Missing**. Spec 171 drafted (verbs as tools + one `cli` tool); spec 149 (token → `Authority`) a seed. No `[project.scripts]` entry; spec 171 decision 7 says "no `vfs serve`". |
| 7 | Everything is a file, one permission structure | Ladder **built** (six rungs; every verb names its rung, `ops.py:134–160`); `/.vfs` serves only the trash view. Views, index and `rungs_at` drafted (169a, 170 §5). |
| 8 | The shell (bash) | **Missing**. Spec 167 (five slices, twenty tasks) and 168 drafted, reviewed, not started; the whole language is a sixth slice (F7) no spec yet carries. |
| — | The action log and analytics | **Missing**. No `import logging` in `src/vfs`; no table records a call; the only call-shaped record anywhere is spec 169c's per-process `/.vfs/run` ring (drafted). Elapsed time per call is stored nowhere. |
| — | Release | `0.0.22` on PyPI, none yanked; the seven-platform publish matrix has **never run**; the bump script cannot write `0.1.0a1`. |

Counts to keep in view: 31 active specs (4 built but not archived, 3
overtaken); 10 ADRs "proposed" (022, 058, 069, 081–087); ADR 087 with 6
leans and 2 spec forks pending Clay; 36 `[NEEDS CLARIFICATION]` markers
in specs 174–181; about 40 live open questions; 5,780 tests at 100%
coverage; 24 error kinds.

---

## 4. Domain A — The kernel and the public API

**Goal.** The kernel is the gate and everything under it (ADR 087).
Its public surface is 24 verbs (25 minus `run`) with the four argument
families a file protocol needs — cursor, range, preconditions, replace
— and three promises written down and pinned: the atomic unit, the
fault model, replay. The three live defects are closed.

**Why this is the spine.** Every other domain is a facet over it. The
shell's `>>`, the guest's write-back, the MCP tool's `idempotentHint`,
the sync facade's signatures and the human-in-the-loop resume all stand
on arguments that do not exist today.

### State today

| Piece | State |
|---|---|
| One gate, 25 routed verbs, `Result` envelope, 24 error kinds | built |
| `ls`/`tree`/`glob` paging | missing (constitution Art. 2 §3 is violated) |
| `read(range=)` | missing |
| `write(if_version=, if_absent=, append=)` | missing (probe 1 live) |
| verify `content_hash` on read | missing (probe 2 live) |
| replay table, `request_key` | missing (probe 3 live) |
| `move`/`copy(replace=)` | missing; specs 167/169/171 say `overwrite=`, ADR 087 and spec 181 say `replace=` |
| `versions(path)`, `read(version=)` | missing |
| `entry_id` on `stat`/`ls`, `OpGroup` | missing |
| `run`, `SupportsRun` | live but dead; retired on paper by ADR 082 pin 12 |

### Stories

#### K1 — Ratify ADR 087 and resolve its six leans · ADR 087 · S · gate b

*Story.* As a software developer, I want the kernel's public names and argument families decided and written down once, so that the code I write against `0.1.0b1` keeps working at `0.1.0` and nothing I depend on is renamed under me.
*Why.* Eight specs stand on a proposed ADR. Six pins carry a lean Clay
has not confirmed; two change public names (pin 3, pin 16). Nothing in
K2–K9 can freeze until they are decided.
*Depends on.* Nothing. Decisions D4–D8.
*Acceptance.*
1. ADR 087's status line reads "accepted" with a date; *Pending Clay*
   records each of the six pins and the two spec forks as resolved.
2. Specs 167, 169 and 171 say `replace=`; a grep over
   `context/specs/active` for `overwrite=` finds only spec 174's
   removal note.
3. Architecture page 02's *Open* list is empty.

#### K2 — Write preconditions and the guarded append · spec 174 · L · gate b

*Story.* As an agent, I want `write` to refuse when the file has changed since I read it, and `>>` to append without clobbering a neighbour's line, so that two of us editing one file cannot silently lose each other's work; as an ETL developer, I want a 10,000-row batch with stale rows to write nothing rather than some.
*Why.* Probe 1 is live data loss on every engine. Constitution Art. 5
forbids silent clobbering. `if_version=` is what `edit`, the shell's
`>>`, the guest's write-back and the resume (H3) need.
*Depends on.* K1.
*Acceptance.*
1. `write(path, content, if_version=N)` against a row at version N+1
   returns `vfs.conflict` with `data["version"] == N+1` and issues zero
   mutation statements, on SQLite and on each engine leg.
2. `append=True` sits at rung `add`: a caller holding `read` on the
   row gets `vfs.permission_denied` with zero mutation statements;
   under `posture(p, "add")` anonymous may append and a `write(
   if_version=)` of an existing row by anonymous is
   `vfs.unauthenticated`. Twenty concurrent appends of one line each
   leave twenty lines; each commits exactly one version row; a guard
   miss on a `reprobe` dialect classifies `conflict` and on a
   `redrive` dialect reruns from a fresh snapshot (retry counter).
3. `write(if_absent=True)` on a live occupant is `vfs.exists`; on a
   tombstone it revives, judged at `read_write` or own (ADR 080 pin 3),
   and reports `created`; a `contribute` caller who does not own the
   tombstone is `permission_denied`.
4. A 10,000-entry batch with `if_versions={...}` and one stale row
   writes zero rows; statements grow by at most one chunked select per
   `membership_budget`.
5. An identical rewrite reports `unchanged`, leaves `version` untouched
   and issues no content insert.
6. `overwrite=` is removed from `write` (D7); the params drift test and
   `Session.write` agree.

#### K3 — Integrity: verify on read, hash on every written row · spec 175 A–C · M · gate b

*Story.* As an ETL developer whose other jobs touch the same database with raw SQL, I want `read` to tell me when a body no longer matches the hash vfs stored, so that a corrupted or out-of-band-edited file is a classified error and never served as a success.
*Why.* Probe 2: an out-of-band writer (an ETL job with SQL credentials)
can change or delete a body and `read` serves it as success. The hash
is stored and never compared.
*Depends on.* K1 (D8 names the kind).
*Acceptance.*
1. After a raw `UPDATE vfs_content SET content='ROTTEN'`, the next
   `read` returns no content and one `vfs.unavailable.integrity` error
   (D8; spec 175's lean, retry class `never`) at the entry's path;
   `success is False`; on SQLite and on each engine leg.
2. A fault is reported only when two reads agree; the second read is
   exactly one extra statement.
3. Every row that `write`, `edit`, `copy` or `move` returns carries
   `content_hash == sha256(body)`.
4. Hashing is offloaded per call (spec 175 §1.3): a batch whose bodies
   sum below `MEASURE_OFFLOAD_BYTES` makes zero offload calls; one
   that sums above it makes exactly `len(byte_chunked(items,
   BLOB_PAGE_BYTES))` calls; a single 16 MB body makes one.

#### K4 — The listing cursor · spec 176 · M · gate b

*Story.* As an agent, I want `ls`, `tree` and `glob` over a 10,000-child directory to come back a page at a time with a key for the next page, so that a listing never floods my context and the shell's `ls | head` closes after one page.
*Why.* `ls` of a 10,000-child directory returns all 10,000 rows with no
limit or cursor. The MCP tools, the shell's `ls` and `find`, and later
`scrub` and the bounded `sweep` page on this key.
*Depends on.* K1 (D6: the key as a `Result` field).
*Acceptance.*
1. `ls(path, limit=1000)` over 10,000 children returns 1,000 rows and
   `next_after == rows[-1].path`; ten pages visit each child exactly
   once; the keyset statement returns at most `limit + 1` rows per
   page with tombstones excluded by the predicate (rows fetched
   counted); with 500 tombstones between children 1,000 and 1,001,
   page two still returns ≤ 1,001 rows and starts at the first live
   child. On SQLite and on each engine leg.
2. `tree` and `glob` page on the same path key; a fan-out over three
   mounts merges pages and emits one key.
3. `Result | Result` clears the key; `with_mount` rebases it; the
   renderer prints `more: after=…` only when set.
4. Anonymous `ls(limit=)` under a `list` posture pages the same key;
   under `none` it is `unauthenticated` at the first page.

#### K5 — Replay: the per-verb contract and `request_key` · spec 177 · L · gate b

*Story.* As a software developer whose host lost the reply to a `move`, I want to send the same call again with the same key and get the first answer back, so that a retry is always safe and the same key can later carry a human's approval.
*Why.* Probe 3: a client that lost the reply to `move` cannot tell
"already moved" from "never existed". The request key is also the
resumption token for H3; one value serves replay and resume.
*Depends on.* K2 (the `unchanged` row).
*Acceptance.*
1. A replayed `move` returns `not_found` at the source with
   `vfs.target` the destination and `data["dest"]["entry_id"]` the
   occupant's id (spec 177 §1.3); a move of a path that never existed
   carries neither.
2. Every mutating verb sent twice matches a pinned replay table, one
   row per verb, on the memory and SQLite legs.
3. `write(..., request_key=k)` sent twice issues, the second time,
   exactly one replay-store select and zero mutation statements, and
   returns a `Result` equal to the first with a `vfs.replayed` info
   record.
4. A keyed call to a mount without the `replay` trait is
   `vfs.unsupported`.
5. A 10,000-row keyed `write` stores its answer paged by
   `BLOB_PAGE_BYTES`; `sweep` deletes replay rows older than the TTL
   (rows counted) with the two whole statements spec 177 §4 names
   until spec 180's bounded sweep lands; it does not page.
6. A fault at the `mutate:after-commit` seam answers
   `vfs.unavailable.in_doubt` (retry class `refresh`); one inside the
   statement answers `vfs.unavailable.backend` (retryable).

#### K6 — The ranged read · spec 178 · S · gate b

*Story.* As an agent, I want `head` and `sed -n 1,20p` on a 4 MB file to read only the bytes I asked for, so that looking at the top of a big file costs what the top costs.
*Why.* `head` and `sed -n 1,20p` on a 4 MB body read the whole body.
*Depends on.* K3.
*Acceptance.*
1. `read(path, range=(0, 4096))` on a 4 MB body binds and fetches at
   most 4,096 body bytes, on SQLite and on each engine leg.
2. The row says which slice it carries; `size_bytes` is the whole
   body's.
3. A range whose offset is at or past `size_bytes` answers an empty
   slice with `success is True`; a negative or non-integer offset is
   `vfs.invalid`; a range on a directory is `vfs.wrong_kind`.
4. A 10,000-path ranged read (the batch form spec 178 chooses) binds at
   most `10,000 × length` body bytes and issues
   `ceil(10000 / membership_budget)` statements.

#### K7 — The storage seam as the kernel: atomic unit, crash points, engine error · spec 179 (slices) · L · gate f

*Story.* As an ETL developer, I want a 10,000-row batch to commit all or nothing and every crash to leave the tables consistent, and as a software developer I want the engine's own error code on every backend failure, so that I can trust a batch result and route a failure without parsing a message.
*Why.* ADR 087 pins 7 and 8 state the atomic unit and the fault model;
nothing pins them.
*Depends on.* K2–K5.
*Acceptance.*
1. On SQLite and on each engine leg: 10,000 good rows plus one bad in
   one `write` commits zero rows; 10,000 good rows commit under one
   `COMMIT` (counted on the statement hook).
2. A fault injected at each mutating statement of `write`, `move`,
   `delete` and `restore` (the `seams` injector) leaves every table
   consistent with the oracle, on SQLite and on each engine leg.
3. `classify_failure` sets `data["vfs.engine_error"] = {sqlstate,
   code, driver}` from driver attributes, never from the message; a
   forced deadlock on each leg carries the engine's code.
4. `traits()` declares the atomic unit (`whole_batch` / `resumable`)
   per verb; a drift test pins the table to ADR 087 pin 7. (An
   additive trait; allowed in a beta.)
5. The seam's `features()` exists and the kernel derives `tree`, `edit`
   and `rmdir` for a backend that lacks them (served, more statements,
   correct).

#### K8 — The history read side: `versions(path)` and `read(version=)` · spec 180 (read slice) · M · gate f

*Story.* As an agent, I want to list a file's versions and read any one of them with who changed it and when, so that "what did this say yesterday" and "who changed this" have answers.
*Why.* The promise says "every body change is versioned"; today version
rows exist for replaced bodies and nothing reads them back. Without a
read side, "who changed this" has no answer. `pack` and the bounded
`sweep` (the rest of spec 180) are 0.2.
*Depends on.* K1 (the verb's name, lean `versions`), K4.
*Acceptance.*
1. `versions(path)` at rung `read` returns the version rows for the
   path with `actor`, `provenance`, `source_identity`, `subjects`,
   `grant_revision`, `created_at`, paged on the K4 key; a hidden path
   is `not_found`; a `list`-only path is `permission_denied`.
2. `read(path, version=N)` returns body N with its hash verified (K3).
3. The v1 version row of every entry carries the creator's `actor`,
   including `anon` and `system` (spec 180 gains the mint-on-create
   rule; a `created_by` column is D36's alternative).
4. `versions` on 10,000 paths issues `ceil(10000 / membership_budget)`
   entry statements and one chunked subjects statement per slice.
5. `versions` registers in the `OpGroup` table as `history` and, once
   M1 exists, as a tool (the tool count moves from 21 to 22 and the
   M1 pin is updated in this story).

#### K9 — Retire `run`, the kernel groups, `entry_id`, the frozen surface · spec 167 A (the `run` task) + spec 181 · M · gate b

*Story.* As a software developer, I want one published list of every public name, argument, result field and protocol the beta freezes, so that I know exactly what I may build on.
*Why.* `run` is retired on paper and live in code; the surface is
counted three ways; beta entry needs a written list of what is frozen.
*Depends on.* K1; K4, K6 (the arguments the list documents).
*Acceptance.*
1. `run` is absent from `Op`, `EXEC_OPS`, `VERB_RUNGS`, `PARAMS`,
   `base.py`, `session.py`, `SupportsRun`, `README.md`; `ALL_OPS` has
   24 members at this landing.
2. `OpGroup` assigns every op exactly one of `filesystem | query |
   history | rights | derived`; its drift test is the one place later
   verbs register (`cli` → `derived`, `versions` → `history`); each
   later story updates that one table.
3. `stat` and `ls` rows carry `entry_id`; a `write` of an `Entry`
   carrying `entry_id` is `vfs.invalid`.
4. `docs/reference/api.md` lists every public name, signature,
   `Result` field, storage protocol and `SCHEMA_FORMAT_VERSION` the
   beta freezes; an import test asserts the frozen list is a subset of
   the live surface (additions allowed, removals and renames not).
5. The conformance battery is reorganised by kernel operation with no
   test lost (count before equals count after).

#### K10 — The session remembers what it read: automatic write preconditions · new spec · M · gate b

*Story.* As a software developer, I want the session my agent works in
to remember the version of every file it read, so that a later `write`
or `edit` through that session is refused if the file changed
underneath it, without my code carrying `if_version=` from the read to
the write; as an agent, I want "read, think, write" to be safe by
default.
*Why.* Clay's request of 2026-10-28. K2 gives the kernel the
precondition; today the caller must remember the version between two
calls. The host loop is the one place that saw both calls, and the
largest client cache is a model's context window, which no server can
invalidate (ADR 087 pin 6). A `Session` already binds one authority to
one conversation and holds no connection; it is the right owner of a
small, bounded memory of what the conversation observed. A developer
who uses sessions gets the guard for free; a developer who calls the
router directly keeps today's behaviour. Precedent: eve's read stamp,
Anthropic's `content_sha256` precondition, MongoDB's `IfMatch`, and
the read-before-edit rule every coding agent enforces in its own
loop.
*The rule, in plain words.* Every result a session hands back that
names a path and a version leaves a *stamp* in the session: the
path's `entry_id`, `version` and `content_hash`. When the same session
later writes, edits, moves or deletes that path and the caller gave no
precondition of its own, the session fills in `if_version=` from the
stamp. If the row moved on, the kernel answers `vfs.conflict` and
writes nothing, exactly as K2 does for an explicit version. A
successful mutation refreshes the stamp from its own result, so a
session reads its own writes. An explicit `if_version=` always wins.
A path the session never read writes unguarded by default (D50), or
is refused when the session was opened `strict=True`. The memory is
bounded by a declared constant; the stamps come off results the
session already returned, so the guard costs no statement and no
connection.
*Depends on.* K2 (the precondition), K3 (the hash on every row). F3
(`Session.cli` shares the stamps, so `sed -i` and `cp` over a read
file are guarded without the shell carrying versions) and X1
(`SyncSession` shares the shape) consume it.
*Acceptance.*
1. `s = fs.session(alice)`; `s.read("/a")`; bob writes `/a` through a
   second session; `s.write(path="/a", content=…)` returns
   `vfs.conflict` with `data["version"]` equal to bob's version and
   zero mutation statements; the same call through
   `fs.write(..., authority=alice)` with no session succeeds; on
   SQLite and on each engine leg.
2. `s.read("/a")` then `s.write("/a")` twice succeeds both times (the
   stamp follows the write); `s.edit` likewise; a stamp is refreshed
   by `read`, `stat`, `ls`, `tree`, `glob`, `grep` and `glean` rows
   that carry `version` (one parametrized case per read verb) and
   never by a row without one.
3. An explicit `if_version=` on a stamped path reaches storage
   unchanged (spied); a 10,000-entry `s.write(entries=)` carries
   `if_versions=` for exactly the stamped paths and issues the same
   statements as K2's batch pin.
4. A path never read in the session writes unguarded by default (D50);
   `fs.session(alice, strict=True)` refuses it `vfs.invalid` naming the
   read-before-write rule with zero mutation statements; under
   `strict=True`, `delete` and `move` need a stamp on the source and
   `copy` needs none.
5. Bounded memory: `SESSION_STAMPS` (lean 4,096) is a declared
   constant; the 4,097th stamped path evicts the least recently
   touched one (evictions counted) and an evicted path is unstamped;
   each stamp is at most `STAMP_BYTES` (declared) and the test asserts
   the table's size in entries and bytes, never a clock;
   `Session.close()` drops the stamps.
6. `Session.cli("cat f")` then `Session.cli("sed -i s/a/b/ f")` passes
   the stamp as `if_version=` (spied); `echo x >> f` stays
   `write(append=True)` and consults no stamp.
7. `SyncSession` and `Session` share one stamp implementation; X1's
   parity test covers `strict=`; `strict` and `SESSION_STAMPS` join
   K9's frozen list.
8. Stamps never cross the wire: `to_payload` of a session's `Result`
   carries no stamp; whether `serve()` keeps a bounded per-principal
   stamp table so agents over MCP get the same guard is D51.

---

## 5. Domain B — Human in the loop: the action log, policy, preview, `pending`, the durable run

**Goal.** Every call vfs makes is a row in the database you already
run — who called, what verb, which paths, how many rows, how long —
and that one table is the operator's analytics, the Catalog's first
introspection surface, and the memory a stopped run resumes from. On
top of it, a host can run vfs with a human in the loop the way
LangChain runs tools with `interrupt()` and `Command(resume=)`. An
action can be stopped before it happens, described exactly, handed to
a human, and resumed with the human's answer. For vfs's own mutations
the description includes a preview of the world after. A run that has
several questions in it — some at the same time, some one after
another — stops at each, keeps what it has done, and picks up where it
left off; it is never re-run from the top. This works for kernel
verbs, host tools, mounted MCP servers, Python guests and shell lines,
in process and over MCP.

**The idea, in plain words.** vfs never asks a person a question. vfs
never waits for a person either. What vfs does is *stop*.

A call comes in. Before vfs changes anything, it checks whether this
call needs a human. If it does, vfs stops. It changes nothing. It
returns a normal `Result` that says "stopped, waiting for a human",
with a ticket. That result kind is called `pending`.

The host program sees the `pending` result. The host asks the human
however it likes. When the human answers, the host tells vfs to
continue. vfs checks the stopped step from the top again, as if it
were new, and runs it once. Nothing was held open in memory while the
human was thinking.

So vfs provides the stop, the description of what would happen, and a
way to say yes. The host provides the asking. This is LangGraph's
split (`interrupt()` stops a node; `Command(resume=)` continues it).
Operating systems do the same: Linux's seccomp user notification and
fanotify permission events let a supervisor outside the kernel answer
for a stopped call; Plan 9's factotum blocks a process on `needkey`
and lets a user agent answer by writing a file. The kernel never asks.
It stops, describes, and takes the answer as a new call.

**The run.** A shell line is not one call. It is a *run* of many
steps: every kernel verb, every tool call and every guest call the
line makes. Picture a line with five questions in it. Two come at the
same time, because `xargs -P 2` is converting two files at once and
each conversion asks. Three come one after another, because a later
stage asks once per file. Clay's rule (2026-10-28): vfs does not re-run
that line from the top after each answer. It picks up where it left
off.

Here is how. As a run goes, vfs writes down each step as it finishes —
which step, what it returned — in the root mount's database. The
table it writes to is the action log (H0): the same rows every call
already leaves behind for analytics, with the step's result pages
beside them. When a step needs a human, vfs lets everything that
can finish without the answer finish, writes down every open question,
and stops. The `Result` says: this run, stopped, these questions open.
The host asks. Answers can arrive one at a time, from different people,
from a different process, tomorrow. `resume(run_id)` walks the line
again, but every finished step is served from the ledger — no
statement issued, no tool entered, no guest instruction executed for
vfs's account — and only the unfinished steps run. So the second
question is asked after the first answer, the two parallel questions
are surfaced together, and the line reaches its end having done each
thing exactly once.

The walk must be the same walk each time. That is the one rule the
run model needs: the shell numbers every call it makes (stage, ordinal
within the stage) and the numbering is a function of the parsed line
and the recorded inputs, never of timing. ADR 081's static grammar and
ADR 084's static parse already make the shell deterministic; this rule
names it and pins it (F3). Two things could break the walk, and both
are handled. A consumer that closes early (`head`) can leave a
producer's last read either issued or not, so the law is stated up to
the point the consumer consumed. And some reads *are* inputs to the
walk — a `glob` decides how many operands a stage has, a `$( )`
becomes an argument — so those reads are always recorded, whatever
the budget, and a read that is re-executed on resume is checked
against the hash that was recorded; if the world moved, the run says
so instead of walking a different line.

Three more rules keep it honest. A resumed step runs as the authority
that started the run, re-judged by the gate; an approver can let a
run continue, never lend it their rights. An effectful step is
claimed in the ledger before it is entered, so a crash in the middle
of a tool call leaves a row that says "in doubt", and the resume asks
the host instead of entering the tool again. And code vfs does not
own — a host tool, a Python guest — is re-entered from the start, with
the vfs calls it already made served from the ledger as long as they
are the same calls; if the code took a different path, the differing
call is made fresh and marked, never answered with a stale result.

This is how durable-workflow engines work. Temporal replays a workflow
from its event history and never re-runs a completed activity; DBOS
checkpoints each step's output in Postgres and resumes from the last
completed step; LangGraph resumes by re-running the node, with
`interrupt()` returning the saved answer in order, and warns that side
effects placed before an `interrupt()` run again. Unix job control is
the small-scale version: a background job that needs the terminal is
stopped with `SIGTTIN` and `fg` continues it where it stopped. Unix
keeps the stopped job in memory. A vfs run must outlive the process,
so its memory is the database you already run. (The LangGraph, Temporal
and DBOS behaviour here is from the assistant's knowledge; the two doc
sites were outside this session's network. H1's ADR cites them with
versions.)

**The preview.** Clay's second requirement: when a call would change
files, show what the world will look like if it is approved, the way
Claude Code shows a diff before asking. vfs is well placed for this.
The database write path already works plan-then-execute: it stages
every change against an in-memory plan and applies the plan only when
it has no errors (`writes.py`, `_finish` then `_apply`). The preview is
that plan, rendered, with no commit. The preview records each row's
version. The resumed step carries those versions as preconditions
(K2), so an approval can only apply to the world the human looked at.
That is the piece a plain diff approval lacks and Terraform's
plan-then-apply has. A preview exists for vfs's own mutations only. A
host tool or a mounted server describes its own question; vfs cannot
preview code that runs elsewhere.

**What this amends.** ADR 084 pin 4 ("no `ask` inside vfs") keeps its
letter and gains one sentence: *vfs never asks; a policy hook, a tool,
a server or a grant check may suspend a step into a `pending` `Result`
that a host answers through the ledger, and a run resumes from its
ledger.* ADR 063 rule 5 and spec 148 §5 already say the first half.
Spec 169c's per-process `/.vfs/run` record becomes rows. H1 lists
every record that changes.

One line: vfs stops and describes; the host asks; the run continues
from where it stopped, and nothing runs twice.

### State today

| Piece | State |
|---|---|
| An action log: one row per call with actor, verb, paths, rows, statements, elapsed time, outcome | missing (no table, no logger; spec 169c's per-process ring is the only call-shaped record anywhere) |
| `pending` kind, ticket, ledger, resume | missing (spec 148 seed; ADR 063 rule 5 accepted) |
| A dry-run form on any verb | missing (the plan seam exists inside `writes.py`) |
| A host policy hook before dispatch | missing |
| A run ledger: steps recorded, stop, resume | missing (becomes a view over the action log's rows plus a result-page table; spec 177's replay store is the neighbouring table) |
| `cancelled`, `timeout` kinds | declared, no producer in `src/` |
| Deadline on fan-out | missing (spec 051, a stale draft since July) |

### Stories

#### L0 — Spike: the cost of logging every call · new study · S · gate a

*Story.* As the owner of 0.1.0, I want to know what one log row per
call costs an agent-sized call and a 10,000-row batch before H0 is
specified, so that the log's write discipline is a measured choice
and not a guess.
*Why.* Clay asked for the spike (2026-10-28) and said analytics is a
must for 0.1.0; the question is not whether to log but how. CLAUDE.md
puts wall-clock in a memo, never a test; this is that memo, and H0's
acceptance then counts statements only.
*Depends on.* Nothing. Runs through public APIs; lands nothing in
`src/`.
*Acceptance.*
1. A dated memo under `context/research/` reports, on SQLite and on
   Postgres, for one `read`, one `grep`, one `write` and a
   10,000-entry `write`, under 1 and under 32 concurrent sessions:
   statements issued and wall time with no log, with one synchronous
   row per call, and with write-behind read rows plus synchronous
   effect rows.
2. The memo states the bar H0 inherits — write-behind adds zero
   synchronous statements to a read and the effect path adds exactly
   two — and the measured overhead against it, with a GO or a NO-GO
   and, on NO-GO, the shape it recommends instead.
3. The spike's scripts live under the study directory and use public
   APIs only; nothing is merged into `src/`.

#### H0 — The action log: every call vfs makes is a row, with who, what, how many and how long · new spec · L · gate b

*Story.* As a software developer running many agents, I want every
call vfs makes — every verb, tool call, guest door call and shell line
— recorded in the database I already run, with the caller, the verb,
the paths, the rows touched, the outcome and the time it took, so that
I can see what my agents did, meter and tune the platform with the SQL
tools I already have, and resume a stopped run from the same record.
*Why.* Clay's rule of 2026-10-28: analytics is a must for 0.1.0, the
elapsed time of every call is a must, and the log is the checkpointer.
One table serves three readers. The operator reads it for analytics.
The durable run (H4) reads it to resume: a run's steps are its rows.
The Catalog (ADR 058 pin 5) reads it as vfs's first introspection
surface. Precedent: DBOS checkpoints each step's output in Postgres
and replays from it; Temporal's event history is both the audit and
the replay source; Postgres's statement statistics and OpenTelemetry
spans carry duration as data. vfs's version rows (ADR 064) are the
write-side audit already; the log extends attribution to reads and
calls.
*The rules the criteria pin.* (i) **One row per call**, never per row
touched: a 10,000-entry `write` is one row with `rows = 10000`. (ii)
**What a row holds.** `call_id`; `run_id` and `parent_call_id` (a
tool's `Fs` calls nest under the tool's row; a `cli` line's stages
nest under the line's); `started_at`; `elapsed_ns` from a monotonic
clock; actor, subjects and provenance; the verb or program name; the
first `LOG_PATHS` paths (lean 16) and the full count; rows touched;
statements issued; bytes moved; the outcome (`ok`, or the first fatal
`ErrorKind`); the mount. Never a body, never a credential, never a
token: X7's rule, pinned by the same test. (iii) **Two write
disciplines.** An *effect* row — a mutating verb, a host tool call, a
`tools/call`, a guest's effectful door call — is claimed before the
effect is entered and completed after it, synchronously, in the root
binding's storage (spec 177's claim-first shape; H4 rule iii). A
*read* row goes to a bounded write-behind buffer flushed every
`LOG_FLUSH_ROWS` (lean 256) rows or at `close()`, so a read adds zero
synchronous statements. A crash loses at most one buffer of read rows
and no effect row. (iv) **Where.** The root binding's storage, beside
the replay store; a root without the `replay` trait logs in process
only and `traits()` says so. (v) **Retention.** `LOG_RETENTION_DAYS`
on the router (lean 30; the run and ask rows keep their own 24 h),
reclaimed by the sweep arm in chunks; `VirtualFileSystem(log=False)`
turns the log off for a host that will not pay for it (D52). (vi)
**The read side at 0.1.0.** The table schema is documented and
frozen, so Postgres, SQL Server, Oracle and SQLite tooling reads it
directly — the point of "the database you already run" — and
`fs.calls(since=, until=, actor=, verb=, outcome=, limit=, after=)`
is a management method on the developer plane, paged on K4's key
(D53). `/.vfs/jobs` (H4) is a view over the same rows.
*Depends on.* L0 (its GO), K4 (the page key), K5 (the claim-first
shape), X7 (the no-secrets pin). H3, H4 and T2 build on it.
*Acceptance.*
1. After one `read`, one `grep` and one `write`, `fs.calls()` as the
   system actor returns three rows carrying actor, verb, paths,
   `rows`, `statements`, `elapsed_ns`, `outcome` and `started_at`; the
   test asserts every field is present, that `statements` equals the
   statement hook's count and that `elapsed_ns` is a positive integer,
   never its value; on SQLite and on each engine leg as the root.
2. A `read` issues no statement beyond its own until the buffer
   flushes: 255 reads issue exactly their own statements, the 256th
   adds exactly one insert carrying 256 rows (bind count under the
   dialect budget, pages counted); `close()` flushes the remainder
   (rows counted).
3. A `write` issues exactly one claim insert before its first mutation
   statement and one completion update after its commit (statement
   order asserted on the hook); a fault injected between the two (the
   `seams` injector) leaves a row whose outcome is `running`, which
   `fs.calls(outcome="running")` returns.
4. A 10,000-entry `write` is one row with `rows == 10000`; a `cli` line
   of five stages is one line row and five child rows with
   `parent_call_id` set (rows counted); a host tool's `Fs` calls nest
   under the tool's row; a guest's door calls nest under the guest's.
5. No log row ever carries a body, a credential or a token: X7's
   corpus of secret bytes is grepped across every log row the whole
   suite writes (zero hits); paths past `LOG_PATHS` are a count.
6. `sweep` reclaims rows older than `LOG_RETENTION_DAYS` in chunks of
   `membership_budget` (rows and statements counted);
   `VirtualFileSystem(log=False)` writes zero log rows (counted) and
   `fs.calls()` answers `vfs.unsupported`.
7. `fs.calls` is the system actor's: any other authority is
   `vfs.permission_denied` with zero statements; it is never a served
   tool and never a program name (T1's and M1's pins gain the
   assertion); it joins K9's frozen list and the management allowlist.
8. `docs/reference/analytics.md` carries the table schema and three
   example queries — calls per actor per day, the 95th percentile of
   `elapsed_ns` per verb, conflicts per path — each run by the docs
   gate against SQLite.

#### H1 — The interrupt ADR: reconcile ask and no-ask, name the kind, place the ledger · new ADR · S · gate b

*Story.* As a software developer embedding vfs in an agent host, I want
one written rule for how vfs stops, describes and resumes an action,
so that every tool kind, the shell and the wire behave the same way
and I can build the asking once.
*Why.* Two records contradict each other, and every story in this
domain and in domains G and H depends on which wins. This ADR lands
before specs 170 and 171 are built, or both are reopened.
*Depends on.* Nothing. Decisions D9–D11, D40–D46.
*Acceptance.*
1. The ADR is accepted and lists its amendments: ADR 084 pin 4 and pin
   9's kind list; ADR 084 pin 1 (the hook judges the static parse,
   never the command text, and may only deny or suspend, never widen);
   ADR 063 rule 5 (a ledger row's expiry is judged at answer time and
   its reclamation by `sweep` is garbage collection, not a verdict);
   spec 148 §5; spec 149 §5; spec 169a's head table (`jobs` served)
   and 169c (records as rows); spec 170 §4's failure table; spec 171's scope; spec 172 (every host import
   is a step); the glossary line; architecture page 11.
2. `ErrorKind` gains exactly one new core kind for the suspended step
   (lean `vfs.pending`, severity error, derived retry class `resume`);
   `KIND_CONTRACTS` carries its phrase, hint and `path` referent; the
   result-laws test round-trips it.
3. A table in the ADR says, per producer — the policy hook, a gate
   refusal a principal could lift, a host tool, a mounted server's
   elicitation, a guest's door call, a shell stage — whether the step
   suspends and what the ticket carries.
4. The ADR states the one model: a kernel call is never held open
   across an interrupt. A *run* — a bare verb, a `cli` line, a tool
   body, a guest — is durable: each step is recorded in the mount as
   it completes, a stop records every open ask, and a resume re-walks
   the run serving recorded steps from the ledger and executing only
   what has not run. The ADR names the determinism law (F3), the
   drain-then-stop rule (D40), what is recorded (D41), how a guest or
   tool resumes (D42), where the ledger lives and its budget and TTL
   (D43), whose authority a resume runs under (D45) and what a crash
   leaves behind (D46).
5. The run ledger is the action log (H0): a run's steps are its rows,
   with a result-page table beside them for the recorded `Result`s;
   the ask ledger is a table of its own beside both, in the *root
   binding's* schema, swept by the replay store's arm, so a resume can
   arrive at a different process. Step rows keep failed `Result`s and
   their pages may carry bodies, which the replay store never does
   (spec 177 §3), and the ADR says so; the ADR names the TTL of the
   run and ask rows (lean 24 h, spec 177's) apart from the log's own
   retention (H0, D52).

#### H2 — `plan=`: every mutating verb can preview the world after · new spec · M · gate b

*Story.* As an agent, or a human approving an agent, I want to see
what a `write`, `delete` or `move` would do to the files — the diff,
the rows tombstoned, the path that would be replaced — before it
happens, so that approval means approving a change and not a verb
name.
*Why.* The preview Clay asked for, and the half of an interrupt that
makes an approval meaningful. A host can also call it with no
interrupt at all, like `make -n` or `terraform plan`.
*Depends on.* K2 (`if_versions` carries the preview's versions into the
apply), K3.
*Acceptance.*
1. `write`, `edit`, `delete`, `mkdir`, `move`, `copy`, `restore`,
   `mkedge`, `rmedge`, `grant`, `revoke` and `posture` accept
   `plan=True` and return the planned `Observation` rows with
   `success=True`, one `vfs.plan` info record, and zero mutation
   statements (counted), on SQLite and on each engine leg.
2. The planned rows say what changes: for `edit` and a text `write`, a
   unified diff of the current body against the planned body; for
   `delete`, every row that would be tombstoned, cascade included; for
   `move` and `copy`, the before and after paths and, with
   `replace=True`, the occupant that would be versioned; for `grant`
   and `posture`, the row that would appear and, for a relabel, the
   count of rows it would touch.
3. Every planned row carries the `version` it was computed against.
   For `write` and `edit` the apply carries `if_versions=` from the
   plan and a moved row is `vfs.conflict` with nothing written. For
   the other verbs the apply is `conflict` when a `stat` at apply time
   disagrees with the plan's versions (one extra chunked select,
   counted) and the remaining race window is documented; giving every
   verb a precondition argument is a 0.2 option (D37). On SQLite and
   on each engine leg.
4. `plan=True` under a caller who may not perform the verb answers the
   refusal the real call would (`permission_denied`, `read_only`),
   never a plan; the approver's preview for that case is H3's.
5. A 10,000-row `write(plan=True)` issues the same read statements as
   the real call's staging phase and no more (counted).
6. A plan pages on the K4 key and renders under `to_str(budget=)`
   (F1); the `vfs.plan` record carries `rows_planned` so a truncated
   preview says how much it hides.
7. The renderer prints a plan as a diff-shaped block that the shell,
   the `/.vfs/jobs` view (H4) and the MCP text block reuse unchanged.

#### H3 — The policy hook, the `pending` Result, the ask ledger and `answer` for a kernel verb · spec 148 §5 rebuilt on H1 and K5 · L · gate b

*Story.* As a software developer, I want to hand vfs one function that
looks at each call before it runs and says allow, deny or ask, and I
want a call it says "ask" about to come back as a normal result with a
ticket and a preview, so that my host can put the question to a person
with any UI and let the call through once with one more call.
*Why.* The kernel half of the interrupt, for the simplest run: one
verb, one step. Two producers: a host policy hook that may say "ask
first" about an allowed call, and a gate refusal a principal could
lift. The answer admits exactly one re-run; the re-run re-enters the
gate, so a right revoked between the question and the answer is
honoured. A bare verb is a run of one step; its ticket is its run id,
and re-sending the call with the ticket is its resume (H4 adds
`resume(run_id)` for runs of many steps).
*Depends on.* H0 (the ledger's home), H1, H2, K5.
*Acceptance.*
1. `VirtualFileSystem(policy=hook)` and `Session(policy=hook)` accept a
   callable (sync or async) that receives a `CallDescription` — verb,
   canonical arguments, paths, the rungs needed, the authority shape,
   and for `cli` the static parse of the whole line — and returns
   `allow`, `deny(kind, message)` or `pending(reason)`. The hook runs
   after the gate's structural checks and before storage: a call the
   gate would refuse never reaches it (zero hook calls on a
   `permission_denied` call, counted). The ask ledger is consulted in
   the router *ahead of* the hook: a re-send carrying an answered
   ticket skips the hook (zero hook calls, counted) and proceeds.
2. A hook answer of `pending` makes the call return `success=False`,
   one `vfs.pending` error whose `data["vfs.interrupt"]` carries
   `ticket`, `run_id` (equal to the ticket for a bare verb), `digest`,
   `expires_at`, `needs`, `producer="policy"` and the H2 plan for a
   mutating verb, with zero mutation statements.
3. A verb the ladder refuses under a `none` posture that a principal
   could allow answers `pending` with `needs="grant:<rung>@<path>"` at
   no statement beyond the refusal's own; the ledger row carries no
   plan at suspension.
4. `fs.answer(ticket, allow=True, authority=approver)` is a management
   method, not an `Op`. It computes the H2 plan *as the approver* and
   returns it before writing the allowance, so the approver sees what
   they approve (`preview=True` returns the plan and writes nothing).
   An approver below `read_write` on the ticket's path is
   `permission_denied` and the ledger gains no row. The written row is
   attributed (actor and subjects). `answer(ticket, allow=False,
   reason=)` records a denial. `Session.answer` does not exist.
5. Re-sending the identical call with `request_key=ticket` proceeds
   once and commits; a second re-send is a replay hit — the first
   answer with a `vfs.replayed` record and zero mutation statements
   (spec 177 §3) — never a second run and never `pending` again; two
   concurrent re-sends are serialised by the claim-first insert on
   the ticket row (one commit, one replay hit, counted); a changed
   argument has a different digest and is not admitted; a denied ticket answers `vfs.permission_denied` with the
   recorded reason; a ticket past its TTL is `pending` with
   `expired=True` at re-send time; `sweep` reclaims rows past the TTL
   (rows counted).
6. The ledger row is in the mount's schema: a resume from a second
   `DatabaseStorage` over the same SQLite file succeeds; on SQLite and
   on each engine leg.
7. `docs/how-to/human-in-the-loop.md` shows a LangGraph host wrapping
   `pending` with `interrupt()` and `Command(resume=)`; its fences run
   under the docs gate against the in-memory backend and skip the
   LangGraph import when the extra is absent.
8. `CallDescription` and `answer` join K9's frozen list.

#### H4 — The durable run: steps recorded, stop, `resume`, the `/.vfs/jobs` view · new spec, rewrites spec 169c · L · gate b

*Story.* As an agent running a shell line with several approvals in
it, I want the line to stop at each question, keep everything it has
already done, and continue from that point when the answer comes —
even if the answer comes from another process tomorrow — so that a
five-question line costs five answers and not five re-runs, and nothing
in it ever happens twice.
*Why.* Clay's rule of 2026-10-28. Without it a resumed line re-runs
from the top: the replay table keeps vfs's own verbs safe, but host
tools re-enter, guests re-execute, and every question before the last
is asked again. With it a run is a durable job whose memory is the
mount.
*The rules the criteria pin.* (i) **Whose run.** The run row stores
the authority that started it; every resumed step runs under *that*
authority, re-derived and re-judged by the gate. `resume(run_id,
authority=)` only decides who may continue the run: its owner, or an
approver who holds `read_write` on every path the open asks name. A
resume never widens and never narrows what the line runs as. (ii)
**What is recorded.** Every effect (a mutating verb, a tool call, a
`tools/call`), every *expansion read* the walk depends on (`glob`,
`$( )`, `find`, `cd`'s `stat`, `test`), and the identity triple
`(entry_id, version, content_hash)` of every other read. Bodies are
recorded only where a guest or a tool consumed them, within
`RUN_LEDGER_BYTES`; a pipe stage's body read is re-executed on resume
and checked against its triple (D41). (iii) **Crashes.** An effectful
step is *claimed* — its row inserted with status `running` — before
the tool is entered or the statement issued (spec 177's claim-first
shape). A resume that meets a `running` row does not re-enter it: the
step is `vfs.unavailable.in_doubt` and the run stops with that ask for
the host. So: kernel verbs at most once; host and MCP tools at most
once when stopped cleanly, in doubt after a crash, never silently
twice. (iv) **Where.** A step row *is* an action-log row (H0) keyed
`(run_id, stage, ordinal)`, with its recorded `Result` in the page
table beside the log; the run head and the ask rows are two small
tables beside both, all in the *root binding's* storage, like grants
on `/.vfs` paths; a root without the `replay` trait refuses a line's
first ask `vfs.unsupported`. (v)
**Drain, then stop** (D40), per pipeline: the stages of the pipeline
that asked run until each is finished or waiting; a suspended stage's
consumer sees neither data nor end-of-stream, so `head` neither closes
nor completes; later `;` and `&&` statements are not run.
*Depends on.* H0 (the rows), H3, F3 (the determinism law, F3
criterion 10; F7's D54 for the shell's nondeterministic words), T2,
K5 (the claim-first shape and the fingerprint).
*Acceptance.*
1. A `cli` line whose stages raise asks ends with `success=False`, one
   `vfs.pending` error whose `data["vfs.run"]` carries `run_id`,
   `status="stopped"` and `asks`: one ticket per open ask, each with
   its producer, stage, description and H2 plan. Two stages of one
   pipeline that both ask appear in one stop (`len(asks) == 2`, one
   error, one run row, counted), and every other stage of that
   pipeline has status 0 or 1, never `running`. (With F6, `xargs -P 2`
   children are the same case.)
2. The run row records the line, the starting `cwd`, `env`, `set -e`
   state and the starting authority (actor, subjects, narrowing,
   provenance). Every step completed before the stop is a row keyed
   `(run_id, stage, ordinal)` with its fingerprint (spec 177 §3.3) and
   its `Result`, successes and failures alike; a step whose packed
   `Result` exceeds `BLOB_PAGE_BYTES` is `ceil(size / BLOB_PAGE_BYTES)`
   page rows (counted); no statement's bind count grows with the body.
3. `fs.resume(run_id, authority=)` after every open ask is answered
   serves each recorded step from the ledger — zero storage statements
   for recorded effects and expansion reads, zero tool entries (spied)
   — re-executes pipe-stage body reads (statements counted equal to
   the number of such reads) and refuses `vfs.conflict` on the run
   when a re-read's `content_hash` differs; the resumed line's stdout,
   `statuses` and `exit_code` equal an uninterrupted run's byte for
   byte. A re-walk that produces a key absent from the ledger, or a
   recorded key the walk does not reach, refuses `vfs.internal` naming
   both keys with zero mutation statements. A resume with an ask still
   unanswered proceeds for the answered stages, stops again, and
   reports the unanswered ticket together with any new ones.
4. Authority: a resumed step runs as the recorded authority (spied:
   every router call carries it); an approver's resume neither adds
   the approver's rights (a step the owner could not do is
   `permission_denied`) nor loses the owner's; a right revoked between
   the stop and the resume refuses the step. `resume` by a principal
   who is neither the owner nor an approver holding `read_write` on
   every open ask's path is `vfs.permission_denied` with zero steps
   run.
5. The five-question line: a line whose first stage asks once, whose
   second pipeline has two stages that ask concurrently, and whose
   third stage asks twice in sequence stops exactly four times, issues
   exactly five tickets, enters each host tool exactly once per
   answer, issues zero `tools/call` re-sends (spied), and commits each
   mutation exactly once (version rows counted). On SQLite and on each
   engine leg as the root binding, with an in-memory submount.
6. A denied ask makes its step `vfs.permission_denied` with the
   recorded reason; the stage exits 1; `set -e` applies as F4 pins;
   the run completes rather than stopping again.
7. Crash: a process killed (the seams injector) after a tool's step
   row is claimed and before its result row lands leaves a `running`
   row; the next `resume` enters the tool zero times (spied), stops
   with one `vfs.unavailable.in_doubt` ask naming the step, and the
   host's answer (`answer(ticket, allow=True, outcome="done" |
   "redo")`) either records the step or re-enters it once.
8. Cross-process: a line stopped through one `DatabaseStorage` resumes
   through a second over the same SQLite file and through the sync
   facade (X1); a root that is `InMemoryStorage` serves asks within
   the process only and says so in `traits()`.
9. `ls /.vfs/jobs` lists the caller's stopped runs; `cat
   /.vfs/jobs/<run_id>/asks/<ticket>` renders the ask with its H2
   block; the owner sees every ask; an approver sees the asks they may
   answer and nothing else; anyone else reads `not_found`; no step row
   is served through the view at 0.1.0; a `write` into the view is
   `vfs.invalid` naming `answer`; reads make zero tool calls.
10. Budget and TTL (D43): a run whose recorded bodies exceed
    `RUN_LEDGER_BYTES` keeps recording effects, expansion reads and
    identity triples and stops recording bodies; a guest or tool input
    past the budget is re-read on resume and hash-checked as in
    criterion 3; a stopped run past its TTL answers `resume` with
    `pending` and `expired=True`; rows past the TTL are reclaimed by
    the same sweep arm as the replay store.
11. `cancel(run_id)` (H6) marks the run and every open ask; `resume`
    then answers `vfs.cancelled`.
12. `resume`, `cancel` and the `/.vfs/jobs` head join K9's frozen
    list; T1's served-heads pin gains `jobs`; `RUN_LEDGER_BYTES` is one
    declared constant with its number and its eviction direction
    (oldest run first) in the docs.

#### H5 — Interrupts for every tool kind: host tools, Python guests, MCP elicitation · amends specs 170, 171, 172 · L · gate b

*Story.* As a software developer who already has LangChain tools, an
MCP server and a Python script, I want each of them to be able to stop
and ask from inside a vfs run and continue from the same point, so
that one approval flow covers everything an agent can run, not just
vfs's own verbs.
*Why.* Theme 4 says all three tool kinds are interruptible. A host
tool raises an interrupt; a mounted server answers `input_required`; a
guest's door call asks; a shell stage stops at the step that asked.
All produce the same ask record and resume through H4. The call is
gated and can be suspended; the tool body still runs with the
authority its trust line names.
*The one rule for code vfs does not own.* A host tool and a Python
guest are re-entered from the start on resume (LangGraph's rule). The
vfs calls they make — a tool through its `Fs`, a guest through its
door — are H4 steps keyed by ordinal *within the stage* and matched by
fingerprint: a call whose fingerprint equals the recorded one is
served from the ledger; a call that differs (the tool branched on
time, the network, or `random`) is a *fresh* call, issued and counted,
with one `vfs.replay_diverged` info record naming the ordinal — never
a served wrong answer. The how-to says in one line that host-side
effects before an interrupt run again, as LangGraph's docs say of
theirs. Recording every host import of the guest (full determinism)
and snapshotting its memory are both 0.2 options (D42).
*Depends on.* H4, T3, T4, T5a, T5b, M1. Adds `cli(request_key=)` to spec
171's `cli` schema and to spec 177's verb list (an additive name).
*Acceptance.*
1. A host tool that raises `Interrupt(payload)` ends its stage with
   exactly one ask carrying `payload`, `stage`, `program`, exit code 75
   (`EX_TEMPFAIL`, D12); zero verbs ran after it in that stage. A host
   framework's own interrupt type registered as such (LangGraph's) is
   caught by the tool door and converted to the same ask with the
   framework's payload in `data`; the host re-raises its own type from
   the payload when it wants native semantics. No exception escapes
   `cli` unclassified.
2. On resume the interrupted tool is re-entered once; its `Interrupt`
   calls return the recorded answers in order; a tool that raises a
   second, new interrupt stops the run again with a new ticket; the
   `Fs` calls it made before the interrupt are served from the ledger
   (zero statements, spied) when their fingerprints match, and a
   mismatched call is issued once with one `vfs.replay_diverged`
   record (counted). The how-to line is CI evidence under the docs
   gate.
3. The guests (T5a, T5b; the Python case pinned, the JavaScript case
   parametrized over the same test): a guest stopped at a door call that asked
   is, on resume, instantiated again (spied: exactly twice for the
   pandas job with one ask in its middle); its door calls up to the
   ask are served by fingerprint with zero storage statements; the ask
   receives the recorded answer; each verb reaches storage once
   (statements counted); stdout equals an uninterrupted run's. A guest
   that diverges before the ask (a `time.time()` branch) issues its
   diverged calls fresh with `vfs.replay_diverged` records and, if it
   reaches the asking call with a different fingerprint, asks again.
   `WALL_TIME_BUDGET` and the fuel budget restart per walk and the docs
   say the guest's work before the ask runs again.
4. A mounted server on the vendored 2026-07-28 schema answering
   `input_required` yields an ask with `inputRequests` and the opaque
   `requestState`; the resume re-sends `tools/call` with
   `inputResponses` and the same `requestState` exactly once (spied);
   the interim result is never cached. Spec 170 §4's elicitation row
   flips from `vfs.unsupported` 126 to `vfs.pending` 75 and T4's pin
   is updated here.
5. A pipeline `producer | interrupting_tool | consumer` stops with the
   consumer having received exactly the bytes the producer emitted
   before the stop (byte count equal) and neither data nor
   end-of-stream after it; the producer finishes or waits (D40);
   stdout emitted before the stop is kept; `statuses` marks the
   pending stage; the resumed line's stdout equals an uninterrupted
   run's.
6. A `cli` line whose first mutating stage the policy hook suspends
   carries the H2 plan of that stage; later pipelines of the line are
   marked "not run".
7. The same five-question line as H4 criterion 5, with one host tool,
   one guest and one policy-suspended verb among its askers, stops
   four times and runs each thing once.

#### H6 — Cancellation and deadlines as kernel facts · spec 051 rewritten · M · gate f

*Story.* As a software developer running vfs over several mounts, I
want a slow or hung mount to cost me a bounded wait and a classified
error instead of a stalled query, and I want to be able to cancel a
stopped run, so that one bad backend or one abandoned question cannot
hold a host.
*Why.* `timeout` and `cancelled` are reserved and unproduced; one hung
remote mount stalls every namespace-wide query; a front that catches
cancellation has no classified shape to return.
*Depends on.* H1.
*Acceptance.*
1. `grep(pattern, deadline=…)` over one fast mount and one mount whose
   `grep` never returns yields the fast mount's rows and one
   `vfs.timeout` error at the slow mount's prefix; the slow coroutine
   is cancelled (cancelled tasks counted = 1).
2. A deadline on a mutation is refused `vfs.invalid` before any
   statement (lean), counted.
3. An outer `CancelledError` still re-raises untouched.
4. `cancel(ticket)` marks a pending ask and the next re-send is
   `vfs.cancelled`; `cancel(run_id)` marks the run (H4 criterion 11).
5. With no deadline configured, statement counts are identical to
   today on every leg.

---

## 6. Domain C — Identity, rights and the trust edge

**Goal.** In process the gate is a convention (ADR 068): any caller
can construct the system authority. On the wire it is a wall: a token
in, an `Authority` out, nothing identity-shaped as data. Tools and MCP
servers are paths the ladder governs. "MCP servers acting as the
user" has a decided shape and a seam; the OAuth round trip is 0.2.

### State today

| Piece | State |
|---|---|
| `Principal`, `Authority`, four doors, per-call `authority=`, `Session` | built |
| Ladder (six rungs), grants, posture, members, rights compiled into every statement | built, on every engine leg |
| `TokenVerifier`, `authority_from_token`, `provenance="edge"` minted only at the edge | missing (spec 149 seed; `authority.py:18` names an edge factory that does not exist) |
| `serve()` refusal on an open mount | missing; ADR 068's `open/shared/private` words were retired by ADR 080, and what rule 7's "open" means on the six-rung ladder is undecided (D15) |
| Tools as paths a grant can name (`rungs_at`) | drafted (spec 170 §5) |
| Per-principal credentials for a mounted MCP server | missing and undecided; spec 170 §3.1 pins one host credential per server |
| `manage` rung, group ownership, non-system membership admin | parked |
| 100k-user scale pins | memo only; no world above a few hundred rows in `tests/` |

### Stories

#### I1 — The trust edge: `TokenVerifier` and `authority_from_token` · spec 149 · M · gate b

*Why.* Theme 6 needs a wall between a bearer token and an `Authority`.
`provenance="edge"` is a value nobody mints today, so any caller can
forge an edge proof in the audit.
*Depends on.* Nothing. Decisions D13, D14, D35 (the JOSE library).
*Acceptance.*
1. `authority_from_token(claims) -> Authority | ResultError` is the
   fifth door and the only site in `src/` that mints
   `provenance="edge"`; the construction-site pin asserts exactly one.
2. A `TokenVerifier` protocol with one method and one shipped
   implementation over the library D35 names, behind a new
   `vfs-py[serve]` extra; the core install imports neither.
3. Over a table of twelve claim shapes: a `sub` equal to the reserved
   system name, `anon`, `*` or a `group:` prefix is `vfs.invalid`; a
   verifier failure or a missing audience is `vfs.unauthenticated`.
4. `act` present → the actor is the `act` principal and subjects are
   `{sub}`; absent → actor equals subject; `source_identity == sub` in
   both; a `groups` claim is ignored (D13).
5. The door token: a bare `Authority(...)` constructed outside
   `vfs.authority` raises `TypeError` naming the doors (a programming
   error, not a classified refusal); `copy` and `pickle` round-trip.
6. An `Authority` minted at the edge survives `to_payload` /
   `from_payload` of a `Result` it produced with `provenance ==
   "edge"` intact and never serialises the token.

#### I2 — `serve()` identity per request and the open-mount refusal · spec 171 §0 + ADR 068 rule 7 · M · gate b

*Depends on.* I1; D15.
*Acceptance.*
1. `serve(fs, transport="stdio", authority=Authority.system())` raises
   before binding a transport; so does a router whose default
   authority is the system actor.
2. A spy on `_call_storage` counts zero calls with `authority is None`
   across the whole MCP test module.
3. HTTP with no token runs as `Authority.anonymous()` judged by the
   ladder; an invalid token is HTTP 401 `vfs.unauthenticated` with zero
   storage calls.
4. `serve()` refuses to start while any bound mount's root
   everyone-level is at or above the rung D15 names unless
   `allow_open=True`; the refusal lists every such mount; with the
   flag it starts and `caplog` holds exactly one `WARNING` record per
   open mount. The `/.vfs/tools` and `/.vfs/mcp` catalogue postures
   count as mounts for this rule.
5. No served tool and no served schema names `authority`,
   `observations` or `provenance` (counted over every input schema).

#### I3a — The `rungs_at` seam · spec 170 §5.1 · S · gate b

*Why.* A catalogue entry (a tool, a server's tool) has no stored row,
so a seam must answer "what rung does this caller hold at this view
path" in one chunked statement per budget slice. T3 needs it.
*Depends on.* K9.
*Acceptance.*
1. `SupportsGrants.rungs_at(paths, *, authority)` issues exactly
   `ceil(len(paths) / membership_budget)` statements for 10,000 paths
   on SQLite and on each engine leg; its answer equals the Python
   oracle over the random grant worlds.

#### I3b — Tools and MCP tools under the ladder: catalogue posture · spec 170 §5 · S · gate b

*Why.* Theme 7. Executing a program or calling a tool is `read` on its
entry (ADR 084 pin 2); listing is `list`; installing is `write` under
the ladder.
*Depends on.* I3a, T1, T3.
*Acceptance.*
1. `grant("/.vfs/tools/deploy", "ann", "read")` is lawful and lists
   under `grants(...)`; `write`, `mkdir`, `delete`, `move` at a
   catalogue path are `vfs.invalid` with zero storage mutations.
2. With `posture("/.vfs/tools", "list")`: anonymous `ls` names every
   tool bare; `cat` of one is `permission_denied`; calling one is exit
   126 and zero host-function invocations (counted). With posture
   `none`: `ls` shows nothing and a call is 127.
3. `type deploy` and `cat /.vfs/tools/deploy` render the trust line and
   never invoke the tool (the invocation counter stays zero across the
   read family).

#### I4 — MCP servers that act as the user: the per-principal credential seam · new ADR + spec, amends spec 170 §3.1 · M · gate f

*Why.* Theme 4(b). The MCP spec forbids forwarding the client's token
upstream and audience binding would refuse it anyway; the standards
answer (token exchange, enterprise-managed authorization) has one
shipping identity provider. The 0.1.0 shape that keeps vfs free of
OAuth: the host supplies a credential resolver keyed by server and
authority; vfs opens one connection per distinct principal; the
credential never appears in a row, a result, a log line or a child's
environment. OAuth on demand is T7 (0.2).
*Depends on.* I1, T4; decision D16. Adds `CredentialResolver` as an
additive name.
*Acceptance.*
1. `add_mcp(name, server=..., credentials=...)` accepts a static
   credential (today's shape) or a `CredentialResolver` with one method
   `resolve(server, authority) -> Credential | ResultError`, called at
   most once per `tools/call` and never during `tools/list` (counted).
2. A resolver answer of `None` or an error makes the call
   `vfs.unauthenticated` at the tool's path with zero bytes sent to the
   server (transport spy).
3. One connection per `(server, principal)`: 100 calls by one principal
   issue exactly one `initialize` and one `tools/list` inside the list
   floor; a second principal issues a second of each; two callers see
   two catalogues when the server varies its listing by bearer, with
   zero cross-caller cache hits.
4. A subject set over a per-user server is refused `vfs.invalid` at
   0.1.0 (D16).
5. The inbound HTTP bearer token never appears in any outbound request
   to a mounted server; the credential never appears in any `Result`,
   row, log line or stdio child's environment (a test greps every
   captured output for the secret bytes).

#### I5 — Scale pins for the rights compile · M · gate a (slow tier)

*Depends on.* Nothing.
*Acceptance.*
1. A generated world (10,000 users, one private home each, 100 shared
   folders, 50 groups, five per user): an ordinary caller's `Rights`
   compiles to ≤ 64 path ranges with a bound value ≤ 4 KiB, and the
   same bound holds at 1,000 users.
2. `ls /` for that caller issues one visibility statement whose text is
   identical to the 1,000-user world's.
3. A posture change on a 100,000-row subtree runs in
   `ceil(rows / profile.relabel_rows)` statements; a read held midway
   agrees with the oracle.
4. The pins run on SQLite by default and on each engine leg.

#### I6 — Validate declared owners; the silent-escalation guard · S · gate b

*Why.* The system actor stamps any declared `owner_id` unchecked, and a
host whose `default_authority` is the system actor turns every
forgotten `authority=` into a system write.
*Depends on.* Nothing. D17.
*Acceptance.*
1. A declared `owner_id` of `*`, `anon`, `system` or a `group:` prefix
   is `vfs.invalid` on `write`, `mkdir`, `copy`, `restore`.
2. `VirtualFileSystem(default_authority=…, loud=True)` emits exactly
   one `WARNING` record (X7's logger) per call that fell back to the
   default; `cli` and `serve()` refuse the system actor regardless.

---

## 7. Domain D — Storage engines

**Goal.** "Supported" has a published meaning: a tuned dialect profile,
a cosine distance function (ADR 059), a Docker leg in CI, a row in a
matrix the README carries and a test pins. A host can provision on its
own Postgres or SQL Server without hand-made schemas. A format bump
never strands a database silently. Every verb is bounded at 10,000 rows
on every engine, and the pins say so.

### State today

| Piece | State |
|---|---|
| Five tuned profiles + the generic floor; every op on all five; the floor withholds `glean` only | built (CLAUDE.md, architecture 01, the glossary and spec 171 still say "`glean` and `graph`") |
| Every `IN` list chunked by `membership()` | built (nine raw `.in_()` sites, all bounded) |
| Four engine legs in CI (`test-dialects.yml`) | built; MSSQL leg red on 2026-10-28 at the `apt` step |
| Schema lifecycle | refuse-and-re-provision only; `SCHEMA_FORMAT_VERSION = 23` vs ADR 020's "stays 1" |
| `CREATE SCHEMA` for host apps, bulk path by driver, privilege refusals classified | missing (spec 157 draft) |
| `install_extensions` | built on the storage; not reachable from the router |
| 10k count pins | write, edges, glob, delete/restore, tombstoned read, graph; none for move, copy, mkdir, sweep, grep, glean, grants |
| Pool configuration | none; a borrowed MSSQL factory skips `use_setinputsizes=False` |
| MariaDB guarded updates | per-row round trips (spec 080 researched) |
| ANN index provisioned | Postgres only; MariaDB and Oracle profiles say `ann`, run exact |

### Stories

#### D1 — The engine support matrix is a published, tested page · S · gate b

*Depends on.* D3 (MariaDB's tier), D18 (Oracle naming).
*Acceptance.*
1. `README.md` carries one row per `PROFILES` entry plus "any other
   SQLAlchemy dialect": driver extra, minimum server version, verbs
   served, vector tier, ANN index provisioned, arbitration, isolation
   pins, known caps (Oracle `IN` 1,000; SQL Server `membership_budget`
   = min(2,000, the bind budget); MariaDB packet and row limits;
   pgvector's dimension cap).
2. A docs-fence test asserts the matrix's dialect names equal
   `set(PROFILES) | {"generic"}` and each row's arbitration and vector
   cells equal the profile's fields.
3. CLAUDE.md, `architecture/01`, the glossary and spec 171 say `glean`
   alone is withheld on the floor; `docker/README.md` and the
   `db_test` skill cite `tests/storage/test_conformance.py`; the dead
   `scripts/mssql_*.sh` are deleted.

#### D2 — Schema lifecycle: directional mismatch, a corruption kind, the migration registry · amends ADR 020 · M · gate b

*Why.* Every format bump today strands a real database. 0.1.0 is the
commitment point ADR 020 named. The minimum honest story: the refusal
says which side is older; a garbage version row is corruption, not
mismatch; a registry exists so the first post-0.1.0 bump must ship a
path or fail a test. Full `ALTER` migrations are 0.2. The alpha
changelog template says that an alpha may bump the format and that a
host moving between alphas re-provisions.
*Depends on.* D19.
*Acceptance.*
1. A meta row at `SCHEMA_FORMAT_VERSION + 1` refuses `schema_mismatch`
   with `data["direction"] == "store_newer"`; at `− 1`, `"store_older"`
   naming the remedy; on SQLite and on each engine leg.
2. A meta table present with no row, or a non-integer version,
   classifies `vfs.unavailable.corrupt` (D19 lean), never
   `schema_mismatch`.
3. A migration registry of `(from, to, statements)` exists; a
   `SCHEMA_FORMAT_VERSION` bump without a matching entry fails a unit
   test; `migrate()` on a store one version behind applies the entry
   and the next first touch adopts (DDL statements counted per bump).
4. ADR 020 is amended to record the pre-release bumps (1 → 23) and
   that the commitment point is `0.1.0b1`.
5. `docs/reference/storage.md` states the contract.

#### D3 — Provisioning for host apps · spec 157 · M · gate b

*Why.* The first three things a production host hit: `schema="vfs"`
needs a hand-made schema; a psycopg session factory crashes on the
first bulk insert; a role without `CREATE` gets `internal`.
*Depends on.* D2.
*Acceptance.*
1. `DatabaseStorage(url=postgres, schema="vfs_demo")` on a database
   with no such schema serves its first `write`; same on the SQL Server
   leg; on SQLite, MariaDB and Oracle first touch issues no schema
   statement (counted).
2. Through a role without `CREATE`, first touch refuses
   `vfs.unavailable` (spec 157 §2; `retryable=False`) with
   `data["schema"]` and `data["privilege"] == "CREATE"`, never a
   traceback.
3. The bulk path is chosen by driver (spec 157's proposed
   `bulk_insert_mode`; today's helper is `dialects.bulk_insert`):
   `"copy"` only when the driver is asyncpg; a `postgresql+psycopg://`
   leg runs the conformance contract and a 10,000-file write lands in
   `"core"` with ≥ 2 insert pages counted.
4. A borrowed `mssql+aioodbc` factory without `use_setinputsizes=False`
   is refused `vfs.invalid` at first touch naming the kwarg (lean),
   pinned with a non-Latin1 path round-trip on the MSSQL leg.
5. `fs.install_extensions(path)` runs the storage's install for one
   mount: a no-op success on SQLite, the real install on Postgres; the
   name joins the management allowlist.

#### D4 — Every verb has a 10k count pin, parametrized over the engine legs · M · gate b

*Depends on.* Nothing.
*Acceptance.*
1. For each of `mkdir`, `move`, `copy`, `sweep`, `grep` (scoped),
   `glean` (scoped), `grant`, `revoke`, a `slow` test writes 10,000
   entries and asserts the verb's statement count equals a named
   formula beside the test (`EXPECTED_STATEMENTS[verb]`) with the chunk
   count from `membership_budget`; X2's router-level `write` pin is the
   same family.
2. `ENGINE_LEGS` is promoted to a shared fixture in `tests/conftest.py`
   and each pin is parametrized over it with the real budgets (Oracle
   1,000; SQL Server 2,000).
3. Under a monkeypatched `parameter_budget = 48`, every verb still
   returns the correct result.
4. The MariaDB leg records the per-row `UPDATE` count of a 10k
   overwrite as a known number, so spec 080 landing is a visible delta.

#### D5 — MariaDB set-based guarded updates · spec 080 · M · gate 0.2 (gate b if D3 makes MariaDB first tier)

*Acceptance.* Spec 080 slice B: `ceil(N / rows_per_statement)`
statements counted; `CLIENT_FOUND_ROWS` asserted at first touch; the
conformance observations byte-identical; the other engines' counts
unchanged.

#### D6 — The SQL Server leg is reliable and the four legs run from the published wheel · spec 166 decision 5 · M · gate f

*Depends on.* R1, R2.
*Acceptance.*
1. The MSSQL job pins `ubuntu-24.04` or derives the package list from
   the runner's release; the next storage push is green on all four
   legs with per-leg pass counts in the commit body (CI evidence).
2. A `workflow_dispatch` input runs any leg against `pip install
   vfs-py==<version>` in a clean venv with no Rust and no C compiler
   on the runner.
3. The run against the last beta is recorded in the `0.1.0` release
   notes (CI evidence).

#### D7 — Pool and borrowed-host posture, per-engine how-tos · M · gate f

*Depends on.* D3. Adds `pool=` as an additive constructor argument.
*Acceptance.*
1. `DatabaseStorage(url, pool=PoolConfig(size=, max_overflow=,
   pre_ping=, recycle=))`; the params drift test lists the four fields;
   the `:memory:` path ignores them and keeps `StaticPool`.
2. A test kills the connection between two ops on each engine leg and
   asserts the next op succeeds after exactly one `backend_unavailable`
   retry (retry spy).
3. `docs/how-to/` gains one page each for SQLite, Postgres, SQL Server
   and Oracle (URL, extra, provisioning privilege, the first-touch
   refusal when the vector function is absent), fence-tested where
   SQLite suffices.

---

## 8. Domain E — Search: glean, providers, renderers, graph

**Goal.** `glean` fuses BM25 and vector at query time on every
supported engine, with a zero-config local embedder, two hosted
adapters, one spelling for configuring a provider from Python, a
config file or the command line, and quality pins on every engine leg.
The query side is built; this domain is about defaults, truth-telling
and pins.

### State today

| Piece | State |
|---|---|
| Lexical leg (block postings scored in Rust) + vector leg (in-engine cosine per dialect) + client-side convex fusion | built on all five engines |
| Query-time embedding of the query string, 256-entry cache | built |
| Embed step at `reindex`: keyset pages, bounded batches, identity on the meta row, re-embed on model change at equal width | built |
| Without a provider: lexical-only with an info record; stale identity: lexical-only with `conflict`; embed failure: retryable `unavailable` | built |
| Default local model | model2vec potion shipped; ADR 060 says fastembed/MiniLM; no fastembed anywhere |
| Slow-provider convergence | broken: never converges under ~17 chunks/s |
| Provider by name/URL/env | missing |
| Width change on a native column | refuses "re-provision" |
| Ordered hybrid top-10 pin | SQLite and memory only |
| ADR 065 statistics-leak regression test | missing |
| `glean_staleness` trait | says `overlay` for both legs; true for BM25 only |
| Renderers pdf/docx/pptx/xlsx; failures as row states | built; images (152 C) and render-at-write (159) planned |
| `graph`: frontier walk, four methods, rights per hop; `fs` and markdown `links` edges | built; `imports` edges (147) planned |
| `docs/reference/api.md` glean content | none |

### Stories

#### E1 — Settle the default local embedder · amends ADR 060 · S (amend) or M (build fastembed) · gate b

*Depends on.* D20.
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

#### E2 — The embed step converges for slow providers · M · gate b

*Depends on.* Nothing.
*Acceptance.*
1. A scripted provider that raises `TimeoutError` for any batch above
   N inputs (no clock) finishes `reindex` with `unembedded == 0`;
   requests issued equal `ceil(pages / N)` plus the retries below.
2. A batch that times out is retried at a smaller size at most
   `log2(max_batch_inputs)` times before the step records
   `unavailable`; requests issued are pinned.
3. `LocalEmbeddingProvider.max_batch_inputs` defaults to ≤ 256 and the
   declared-caps pin is updated.
4. A timed-out local batch never leaves a worker computing past the
   next page (counted `embed_batch` calls after the timeout).

#### E3 — Provider configuration by name · S · gate b

*Depends on.* E1; M2 is the consumer.
*Acceptance.*
1. `embedder_from_spec` parses `model2vec:<model>`, `openai:<model>@<dim>`,
   `hash:<dim>` and `langchain:<dotted factory>`; an unknown scheme or
   a malformed `@dim` raises `ValueError` at construction time naming
   the schemes.
2. `openai:` resolves the key from the environment and refuses when
   absent; the test uses a fake transport.
3. The resulting provider's `model_id` equals the object form's for the
   same arguments (one parametrized test per scheme).

#### E4 — Hybrid determinism and quality pins on every engine · M · gate b

*Depends on.* Nothing.
*Acceptance.*
1. The hybrid ordered top-10 pin is parametrized over `ENGINE_LEGS`
   with the 64-d hashing embedder; deselected when the URL is unset.
2. A fused-arm gate on the native golden set: `ndcg@10(fused) ≥
   ndcg@10(bm25) − 0.005` (the harness's existing BM25 gate) with the
   local model cached; skips with a printed reason otherwise.
3. The vector-leg referee runs on each engine leg: the engine's
   top-`depth` order equals the Rust kernel's over the same rows (rows
   compared counted).
4. The `legs` extra's `tier` equals `f"native_{profile.vector_distance}"`
   on each leg.

#### E5 — Close ADR 065's paperwork: the leak regression test and the honest staleness trait · S · gate b

*Depends on.* Nothing.
*Acceptance.*
1. A test hides half a corpus from `bob` and asserts every probe term's
   `df` and every visible row's score are identical whether the hidden
   half exists or has been deleted; the same holds under the generic
   floor's clause fan.
2. `traits()` says `glean_staleness` is `overlay` for the lexical leg
   and `reindex` for the vector leg; the protocol vocabulary and its
   drift test agree.

#### E6 — glean reference docs and the embedder how-to · S · gate f

*Acceptance.* `api.md` documents `glean`'s parameters, the records
(`no_provider`, `stale_identity`, `embed_failed`, `truncated`), the
`legs` and `lexical_stats` extras, `Ranker`/`Convex`/`RRF`/`Signal`
and `install_extensions`; the how-to covers SQLite (nothing to
install), Postgres (`install_extensions`), SQL Server 2025 and Oracle
23.4+ prerequisites; every fence runs under the docs gate.

#### E7 — Width change is a migration, not a re-provision · M · gate 0.2

ADR 054 promised "reindex is the migration"; at a new width on a native
column first touch refuses. Engine-specific DDL under the reindex
lease, after D2's registry.

#### E8 — Render at write (159), images (152 C), `imports` edges (147), tuned fusion defaults · gate 0.2

Independent of theme 3. Render at write moves up if D21 says so.

---

## 9. Domain F — The shell

**Goal.** An agent types `grep -rn mfa /enterprise | head -20`, or
`for f in *.md; do grep -q TODO "$f" && echo "$f"; done`, through
`VirtualFileSystem.cli` or `Session.cli`, and every verb passes the
gate. The grammar is bash — the whole language, parsed statically to
an AST before anything runs (ADR 081 pin 1 holds; pins 4, 8 and 12 are
amended by F7). What is refused is only what has no meaning inside one
gated call (D47, D48), each refusal a classified
`unsupported.construct` naming the construct, its position and its
reason. The README publishes two numbers with their denominators:
spec 167's harness run rate on the synthesized corpus (F5) and the
Oils spec-suite pass rate for the admitted constructs (F7).

**What "bash" means here, honestly** (Clay, 2026-10-28: full bash, as
an expressive language, with everything that could be useful to vfs in
it). The language is in: pipes (74% of the 12,627 measured calls),
`&&` (44%), redirects, here-documents, variables and every parameter
operator, `$( )`, `for`, `while`, `until`, `if`, `case`, functions,
arithmetic, arrays, `[[ ]]`, process substitution, here-strings. The
grammar is not where the shell runs out; programs are. Every program
keeps its Unix name and GNU flag semantics; the nine commands that
make 86% of pipeline segments land first (F3, F4) and the text kernels
follow (F6). `awk` (the largest hole, 331 measured uses) needs a wasm
host and is out of 0.1.0 unless D22 says otherwise. `git`, `docker`,
`uv`, `sudo`, `curl` never run and say so. Job control past the call
(`jobs`, `fg`, `bg`, `disown`, `nohup`), `eval`, `exec` and `trap`
are refused with a hint; `cmd &` inside a line and `wait` are
concurrency bounded by the call (D47). The shell is also the executor
of the durable run (H4): it numbers every call it makes, and that
numbering is what lets a stopped line continue where it stopped; a
loop's iterations and a function's calls are numbered the same way.

### State today

Nothing is built. `vfs.shell` does not exist; `crates/vfs-core` has no
`shell` module. Three live-tree gaps the shell depends on: a bytes row
renders empty, `to_payload` inlines base64 without bound, and the dead
`run` verb sits where `cli` goes.

### Stories

#### F1 — The renderer gaps and the vocabulary · spec 167 A · M · gate a

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

#### F2 — The parser: the whole grammar · spec 167 B (widened) · L · gate a

*Story.* As an agent, I want every bash construct I type to parse to
an AST before anything runs, so that a refused word is refused up
front with its reason and nothing I wrote is half-executed.
*Why.* Clay, 2026-10-28: the whole language. The parser is where that
decision costs the least and matters the most: a static parse of
`for`, functions and arithmetic is what keeps ADR 081 pin 1 and the
pre-execution summary of ADR 084 pin 1 true once F7 runs them. The
measured corpus already parsed 100 of 100 under mvdan-sh's bash
dialect; vfs's parser is held to the same corpus.
*Depends on.* Nothing. Decisions D47, D48.
*Acceptance.*
1. The weighted 100-command corpus parses 100 of 100 to an AST; the
   Oils spec-suite scripts for the constructs F7 admits parse (count
   published beside F7's run rate); every refusal is one of D47's and
   D48's words, classified `vfs.unsupported.construct` with `line`,
   `column`, `construct` and the reason in the hint.
2. Each malformed case (unclosed quote, unclosed here-document,
   trailing `|`, `&& &&`, stray `)`, `if` without `fi`, `done` without
   `do`) is `vfs.invalid.syntax` with `line`, `column`, `offset`,
   `expected`, `incomplete`; exactly one error per call; a caret in
   the display.
3. The four parser budgets each classify `vfs.budget_exhausted` on a
   counted input (1 MiB + 1 byte; 100,001 tokens; depth 201; a brace
   expansion over `ITERATION_BUDGET`).
4. `cmd &` parses as a job inside the list (D47); `time -p` parses as
   a builtin; `source lib.sh` of a literal path is resolved and parsed
   before the line runs and a computed path is refused (D48).

#### F3 — The pipe, the ABI and `cli` with the minimal programs · spec 167 C · XL · gate b

*Depends on.* F1, F2, K2 (`>>` is `write(append=True)`; `touch` is
`write(if_absent=True)`).
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
4. `cli` under the system actor is `vfs.invalid`; a 65-stage line is
   `invalid`; `sweep` and `posture` are `vfs.unrecognized` 127; `curl`
   is `vfs.unsupported` 126 with the network hint.
5. `cat img.png | wc -c` prints `size_bytes`; `cat a.png > b.png`
   leaves equal hashes; `cat img.png` alone prints one placeholder
   line.
6. `echo x >> f` issues one `write(append=True)` call (spied); twenty
   concurrent lines leave twenty.
7. `Session.cli` keeps `cwd` across calls; `VirtualFileSystem.cli`
   starts at `/` each call; `history` holds at most 1,000 entries.
8. `MANAGEMENT_METHODS` moves from `tests/test_ops.py` to `ops.py`
   and `cli` registers in `OpGroup` as `derived`.
9. The slice-C battery is parametrized over the engine legs.
10. The determinism law (H4's seam): the executor keys every kernel
    call and tool call it makes as `(stage, ordinal)` with spec 177's
    fingerprint; for a line with no early-closing consumer, two
    executions over the same world produce equal per-stage key lists
    (recorded by a spy, compared as lists); for `cat a b c | head -1`
    the recorded sequence is a prefix of the uninterrupted one; a key
    never carries a timestamp, a task id or a queue position (a grep
    over the key type).

#### F4 — The program forms, `replace=`, `glob(case_mode=)`, `set -e`, the never table · spec 167 D · L · gate b

*Depends on.* F3; K1 (pin 17).
*Acceptance.*
1. Every row of 167 §4.1 has a test against a committed GNU fixture;
   `ls -l` prints `kind size_bytes updated_at owner_id version`, never
   mode bits.
2. `move(src, dest, replace=True)` onto a file keeps the destination's
   `entry_id`, versions the replaced body and tombstones the source; a
   directory over a directory is `vfs.exists`; on SQLite and on each
   engine leg.
3. `glob(case_mode="insensitive")` matches a case-folded Python filter
   on SQLite and each engine leg in one statement per mount.
4. `set -e` stops at the first failing statement; the exemptions
   pinned are the left side of `&&`/`||`, a `!`-negated pipeline, a
   pipeline whose last stage succeeds, and a subshell's inner failure.
5. Each never-class name returns its kind, exit code and hint;
   `grant`, `revoke` and `grants` gain shell spellings (D34).
6. `rm -rf /` at a bind site is `vfs.busy`; elsewhere it tombstones
   with exactly one `delete(cascade=True)` call.

#### F7 — The language runs: control flow, functions, arithmetic, arrays, the parameter operators · spec 167 F (new slice), amends ADR 081 · L · gate b

*Story.* As an agent, I want to write the bash I already write —
`for f in *.md; do …; done`, `if grep -q x f; then …; fi`, `while read
-r line; do …; done`, a function, `$(( n + 1 ))`, an array — and have
it run inside vfs with every verb gated, so that the shell is a
language I can think in and not a list of one-liners.
*Why.* Clay, 2026-10-28: full bash, as an expressive language, with
everything useful to vfs in it. This reverses the 2026-10-15 subset:
ADR 081's slices 2 and 3 land in 0.1.0 and its pin 8 shrinks to the
constructs that have no meaning inside one gated call (D47, D48). The
static parse holds (F2), so the pre-execution summary still names
every program, verb and literal path; a loop over a glob names the
glob. Control flow is the shell's job; the guests (T5a, T5b) are for
numpy, pandas and the JavaScript world. The durable run (H4) numbers
loop iterations and function calls as it numbers stages, and the
shell's few nondeterministic words are recorded as expansion reads
(D54).
*Depends on.* F2, F4; K2. H4 consumes criterion 7.
*Acceptance.*
1. `for`, `while`, `until`, `if`/`elif`/`else`, `case` with `;;` and
   `;&`, `break`, `continue`, `[[ ]]` with `=~` and pattern matching:
   each has a spec-test file (script in; stdout, stderr and status
   out) against committed bash fixtures from the pinned-image script;
   `while read -r line` over a pipe consumes it in `ROWS_PER_CHUNK`
   chunks at queue depth ≤ 2 (counted) and `read` is a builtin that
   never leaves the shell.
2. Functions in both spellings, `local`, `return`, `shift`, `getopts`,
   `declare`, `readonly`, `unset -f`; recursion to
   `FUNCTION_DEPTH_BUDGET` (lean 256) and then `vfs.budget_exhausted`
   exit 137 (depth counted); `$(( ))`, `(( ))`, `let` and every
   arithmetic operator, including `$RANDOM`.
3. Arrays and associative arrays, `${x/a/b}`, `${x:1:2}`, `${!x}`,
   `${x@Q}`, `${x,,}`, `${x^^}`, `${#a[@]}`, extended globs under
   `shopt -s extglob`, here-strings `<<<`, `|&`, process substitution
   `<( )` and `>( )` as seams of the pipe (ADR 083: one shape per
   chunk, bounded queues).
4. `LOOP_ITERATION_BUDGET` (lean 1,000,000) and `FUNCTION_DEPTH_BUDGET`
   are declared constants; `while true; do :; done` ends with
   `vfs.budget_exhausted` exit 137 after exactly the budget's
   iterations (counted), inside `WALL_TIME_BUDGET`; a loop that calls
   a verb per iteration counts each call against `VERB_CALL_BUDGET`.
5. The Oils bash spec-suite files for the admitted constructs run
   under F5's harness and the pass rate is published beside F5's
   number (bashkit publishes 97.3%); `KNOWN_DELTAS` lists every
   deliberate difference and the test asserts the list is exhaustive
   (every failing case is named).
6. The refusals (D47, D48): `jobs`, `fg`, `bg`, `disown`, `nohup`,
   `eval`, `exec`, `trap`, `coproc`, `ulimit`, `umask`, and `source` of
   a computed path are `vfs.unsupported.construct` or `vfs.unrecognized`
   with a hint naming why; `a & b & wait` runs `a` and `b` concurrently
   (two tasks counted) and the call returns when both have run, with
   both statuses in the list; `source lib.sh` of a literal path reads
   the file through the gate (one `read`, spied) and parses it before
   the line runs.
7. The durable run (H4, D54): `$RANDOM`, `$SECONDS`, `$EPOCHSECONDS`,
   `$EPOCHREALTIME`, `$BASHPID`, `$$` and the `date` builtin are
   expansion reads recorded in the ledger; a resumed loop replays them
   from the ledger (zero fresh values, counted) and the resumed line's
   stdout equals an uninterrupted run's byte for byte.
8. ADR 081 pins 4, 8 and 12 are amended (no v1 arithmetic exclusion;
   the refused list is D47's and D48's; slices 2 and 3 are landed and
   slice 4 is the long tail); ADR 084 pin 1's summary is restated for
   loops (programs, verbs and literal paths named; a glob named as a
   glob); the glossary and architecture page 11 say "bash".

#### F5 — The coverage harness and `docs/reference/shell.md` · spec 167 E · M · gate f

*Depends on.* F4, F7; H5 and F6 for exit rows 75 and 123.
*Acceptance.*
1. The harness reports parse, resolve, flag and run rates on the
   synthesized corpus; the in-scope run rate is at least 85%; the
   README prints the harness's measured rate with its denominator
   beside F7's Oils rate with its own.
2. Fixtures come from one pinned-image script and are committed; tests
   never run bash.
3. `docs/reference/shell.md` lists the grammar (the whole language and
   the D47/D48 refusals), every program with its forms, the exit-code
   table (0, 1, 2, 75, 123, 124, 126, 127, 130, 134, 137), the budgets
   (F7 criterion 4 included) and the refusal table.

#### F6 — Text kernels: `sort uniq tr tee` (168a), `xargs` and `find -exec` (168b) · M + M · gate f

*Why.* Adds the four most-used missing text programs and the one
rows-to-verb form. If capacity binds, 168a ships as Python transforms
inside F4 and the Rust port is 0.1.x (§15); no name changes either
way.
*Depends on.* F4.
*Acceptance.*
1. Parity tests pass for `head tail wc cut nl sed` against the slice-D
   Python transforms as oracles.
2. Every new kernel passes its GNU fixtures and the split law (whole,
   one byte at a time, random boundaries).
3. `cat f | sort | uniq -c | sort -rn | head -5` over 10,000 lines
   feeds 10 chunks, materializes each `sort` once, keeps queue depth
   ≤ 2 and reports the second `sort` cancelled (counted).
4. `find . -name '*.py' | xargs -n 10 grep -l TODO` over 25 files calls
   `VirtualFileSystem.grep` 3 times (spied); `xargs` returns 123 when a
   child exits 1.
5. `awk` and `jq` are `vfs.unrecognized` 127 with their hints; `cargo
   test -p vfs-core` green; the wheel budget holds.

---

## 10. Domain G — Tools: three kinds, one ABI, one permission structure

**Goal.** Clay's three kinds map onto ADR 082's six:

| Clay's kind | ADR 082 kind | Lands in | Runs as | Gated by |
|---|---|---|---|---|
| (a) host-program tools, LangChain-shaped | **tool** | T3 | the host's authority (ADR 084 pin 3's one exception); receives the caller's `Fs` only if it declares one | `read` on `/.vfs/tools/<name>` |
| (b) mounted MCP servers | **MCP tool** | T4, I4 | the credential the resolver returns for the caller | `read` on `/.vfs/mcp/<server>/tools/<tool>` |
| (c) CLI tools embedded or installed | **verb builtin**, **text program** (F3–F7); **skill** (read only, T1); **program** (`.wasm`, T6 in 0.2); the `python` and `javascript` kinds (T5a, T5b) | F3–F7, T1, T5a, T5b | the caller, never more | the verb's own gate; `read` on the entry; install is `add` on the directory |

Every tool is a *path* an agent can see, grant and call. `cat` of a
tool shows its manifest and never runs it (the mcpfs lesson: `stat`
never executes). A tool runs only when typed as a command. The call is
gated and can be suspended (H5); the tool body runs with the authority
its trust line names. At 0.1.0 the installable kinds are skills and
host tools; the Python and JavaScript guests (T5a, T5b) are in 0.1.0,
each behind its own extra (Clay, 2026-10-28); generic wasm programs
are 0.2.

### State today

Nothing is built. `/.agents` and `skills.py` exist and are retired by
ADR 082 pin 6. Spec 170's "one small study" (a supervisor spike on 3.11
and 3.13, a real-server schema census, a legacy-server probe) is an
afternoon each and becomes T4's first tasks.

### Stories

#### T1 — The `/.vfs` views, the index, union resolution, install rules · spec 169a · L · gate b

*Depends on.* F3, F4.
*Acceptance.*
1. `ls /.vfs` lists exactly the served heads plus `trash`: `{bin,
   skills, trash}` at this landing; T2, T3 and T4 each add one head and
   update the same pin; a reserved, unserved head is `not_found` on
   read and `vfs.invalid` on write. At a mount, `ls /data/.vfs` lists
   `trash`.
2. `write`, `mkdir`, `move`, `copy` into any view path are
   `vfs.invalid` naming the writable index directories;
   `fs.sweep("/.vfs/trash")` succeeds; `fs.posture("/.vfs/bin",
   "list")` writes one row in the root binding's grants table.
3. An unscoped `glob **` and `grep -r /` make zero calls into any view
   (spied); `mounts()` lists no view. (A `/.vfs/mounts` view is D38;
   lean no, `mounts()` is the API.)
4. The first resolution mints `/opt/bin` once as the system actor at
   posture `read` (one `mkdir`, one `posture`); an agent's write there
   is `permission_denied` without an `add` grant and `created` with
   one.
5. Resolving a name over a 10,000-file program directory is one `stat`
   dispatch per mount and zero `ls`; a masked name is `vfs.unsupported`
   126; a kernel name may not be shadowed unless in `prefer_stored`.
6. `/.agents` names are gone from `src/`; the battery is parametrized
   over the engine legs.

#### T2 — The `/.vfs/run` record, as rows · spec 169c rewritten · M · gate b

*Why.* Spec 169c's per-process ring would be thrown away by H4 on the
critical path; land the record as rows in the root binding's storage
from the start (the review's call). A run record is an action-log row
(H0) plus the program's output rows; H4 adds the steps and asks to the
same tables.
*Depends on.* T1, F3, H0 (the row), K5 (the claim-first shape).
*Acceptance.* After `cat a.txt | upper`, `read /.vfs/run/<id>/stdout`
returns the output and `…/status` names the program and
`content_hash`; the rows are in the root binding's schema and a read
from a second `DatabaseStorage` over the same SQLite file resolves;
another authority's read is `not_found`; eviction by count (64 per
principal) and bytes (64 MiB, oldest first) is counted; on SQLite and
on each engine leg as the root.

#### T3 — Host tools as files: `ToolView`, the schema-to-flags table, `_invoke` · spec 170 §1–2 · L · gate b

*Depends on.* T1, T2, I3a.
*Acceptance.*
1. A registered function (plain, async, and a LangChain `BaseTool` by
   shape — `name`, `description`, `args_schema`, `ainvoke` — without
   importing `langchain_core` outside its extra) appears at
   `/.vfs/tools/<name>` and in `/.vfs/bin` with `callable_kind=tool`;
   `<name> --x 1` calls it once (spied); `str` → one text row, `bytes`
   → one bytes row, `dict` → one JSON row, `None` → no row, a `Result`
   passes through.
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
   write is `permission_denied` (spied: the router call carries the
   caller's authority).
6. The same tool is callable from Python (`fs.cli("name --x 1")`), the
   shell and the MCP front with one result shape.
7. A catalogue of 10,000 registered functions lists in
   `ceil(10000 / membership_budget)` `rungs_at` statements and
   `ls /.vfs/tools | head -1` closes after one chunk.

#### T4 — MCP servers as views: `McpView`, the inbound block table, the supervisor · spec 170 §3–4, §7 · L · gate b

*Depends on.* T3, I3b; M1's inbound adapter (or land it here).
*Acceptance.*
1. A connected in-process server appears under `/.vfs/mcp/<name>/`;
   one call yields a text row, a media row, a link row, an embedded
   text row and an unknown-block row under `/.vfs/run/<id>/<i>`;
   `isError` is exit 1 with its text on stderr and no minted kind; a
   server-supplied description renders as data and the trust line
   names the server.
2. Every row of the failure map produces its kind and exit: `-32602` →
   `vfs.invalid` 2; `-32601` → `vfs.not_found` 127; transport →
   `vfs.unavailable.backend` 1; wall → `vfs.timeout` 124; elicitation →
   `vfs.unsupported` 126 at this landing (spec 170 §4); H5 flips that
   row to `vfs.pending` 75 and updates this pin.
3. `ls /.vfs/bin` twice in one `cli` call issues one `tools/list` per
   server (per server and principal once I4 lands); inside the list
   floor, zero (counted).
4. A stdio server killed mid-session: the call is
   `unavailable.backend` and the next call respawns exactly once; a
   call cancelled by the wall budget is issued once, never retried.
5. `VirtualFileSystem.close()` closes every view with no cross-task
   error on every matrix Python; `import vfs` works without the `mcp`
   extra.
6. Credentials never appear in the environment of a spawned stdio
   server.

#### T5a — The Python guest over wasi-python · spec 172 rewritten, ADR 086 amended · M · gate b

*Story.* As an agent, I want to run a Python script — with numpy and
pandas — over the files I can see, as me, with every file call passing
the gate, so that numeric and tabular work has a home inside vfs and a
script cannot reach anything the shell cannot.
*Why.* Python is in 0.1.0 (Clay, 2026-10-28; D23 decided). The
mechanism is proven twice (spike 173; the 2026-10-23 memo ran
wasi-python 0.1.0 over a vfs `Session` through public APIs only). What
remains is a thin adapter behind `vfs-py[python]`, and the step
recording H5 needs: every host import is one call through one door.
*Depends on.* F3, F4, T1; ADR 086 pins 1, 2, 4, 6, 7 rewritten from the
memo. H5 adds the guest's asks. T5b reuses the adapter.
*Acceptance.*
1. `python3 -c "import numpy, pandas"` runs with zero host preopens
   beyond the runner's stdlib zip and zero vfs grants.
2. The pandas CSV job completes with exit 0 in at most 21 verbs (the
   measured 17 `stat`, 2 `read`, 2 `write`; a stat cache lowers the
   bound and the test pins the new number).
3. A guest write on a read-only mount raises `EROFS` in the guest and
   the stage reports one `vfs.read_only` error although the guest
   exited 0; `open("/.vfs/trash")` is `ENOENT` with zero verbs.
4. The same script as Alice (no grant) and Bob (`read` on `/secret`)
   gives `FileNotFoundError` and the body respectively.
5. `trapped == "deadline"` → 124; fuel or file-call exhaustion → 137;
   any other trap → 134.
6. `WASI_ERRNO` has one entry per `ErrorKind` (drift test); the guest
   tests are `slow`.

#### T5b — The JavaScript guest over QuickJS-NG · spec 172 §6 rewritten, ADR 086 pin 9 · M (plus an S spike) · gate b

*Story.* As an agent, I want to run a JavaScript program over the
files I can see, as me, with every file call passing the gate, so that
JSON work and the scripts I already write in JavaScript have the same
home Python has.
*Why.* Clay, 2026-10-28: Python and JavaScript, both optional extras.
ADR 086 pin 9 already names QuickJS-NG "under the same host, with the
same door". The open question is the host. wasi-python's runner hosts
the Python guest; whether it hosts a generic `wasm32-wasip1` module
over the same mount and tool protocols is unknown (the 2026-10-23
memo's Q2). D49 decides: ask the `wasi_python` project to host a
generic module (lean), or pull 169b's host (T6) forward for QuickJS
alone. A one-afternoon spike (gate a, S) answers the question before
the story is sized final.
*Depends on.* T5a (its adapter is the template), D49 and its spike;
F3, F4, T1.
*Acceptance.*
1. `qjs script.js` runs a QuickJS-NG guest with zero host preopens
   beyond the artifact and zero vfs grants; `node` resolves to the
   same kind and `type node` says "QuickJS-NG, not Node: no npm, no
   network, no native modules" (ADR 082 pin 14: trust shown).
2. A script that reads a JSON row, transforms it and writes a sibling
   completes with exit 0 in a counted number of verbs (the test pins
   the measured number as T5a criterion 2 does).
3. A guest write on a read-only mount raises the guest's `EROFS` and
   the stage reports one `vfs.read_only` error although the guest
   exited 0; `/.vfs` is `ENOENT` with zero verbs; the same script as
   Alice (no grant) and Bob (`read` on `/secret`) fails and succeeds
   respectively, through the one provider.
4. `trapped == "deadline"` → 124; fuel or file-call exhaustion → 137;
   any other trap → 134; `WASI_ERRNO` is the one table both guests
   share (drift test).
5. `import vfs` works without `vfs-py[javascript]`; the extra pins the
   QuickJS-NG artifact by hash; the artifact rides the extra's wheel,
   never vfs's own, so the wheel budget is untouched; the guest tests
   are `slow`.
6. Both guests register as rows of one guest table in the program
   table (`python`, `javascript`), share one host adapter class and
   one door, and H5's resume rule (re-enter, match door calls by
   fingerprint) is pinned for both.

#### T6 — The generic wasm host, `/opt/bin` programs, `awk`, `jq`, uutils · spec 169b · XL · gate 0.2

The only road to `awk` and to running arbitrary installed programs; it
duplicates a preview1 host wasi-python's runner already owns. D22. If
D49 finds that runner cannot host QuickJS-NG, the host half of this
story moves up for T5b and the program-install half stays here.

#### T7 — OAuth on demand for mounted servers · extends I4 · L · gate 0.2

A caller with no credential for a server that returns 401 gets
`pending` carrying the authorization URL; completing the ledger entry
with the callback's code mints the token record for that principal.
An interrupt by construction; after H5 and I4.

---

## 11. Domain H — Serving vfs as an MCP server

**Goal.** One command starts a server. Every agent-facing verb is a
tool, plus one `cli` tool. Rows cross the wire as MCP's five content
blocks and nothing else; `structuredContent` is the `Result` payload
without bytes. A token in, an `Authority` out. `pending` maps to the
protocol's `input_required`.

### State today

Nothing is built. Spec 171 is drafted and reviewed. Spec 171 decision 7
says "`serve()` only, no `vfs serve`" because nothing says how to build
a router from a URL; D24 reverses that. `docs/how-to/expose-over-mcp.md`
is a six-line stub.

### Stories

#### M1 — The MCP adapter and `serve()` · spec 171 · L · gate b

*Depends on.* F1, F3, I1, I2; T2 for links to program output (degrades
to placeholders without it). Names below marked *(proposed)* are spec
171's and do not exist yet.
*Acceptance.*
1. `tools/list` names exactly the agent-facing verbs (spec 171's
   `AGENT_OPS` *(proposed)*) in `fs.capabilities()` plus `cli`: 21 on
   the default router, 20 on an unknown dialect (`glean` withheld;
   spec 171's "19" is stale, D1), 1 with `tools={"cli"}`; K8 raises
   the count to 22 and updates this pin; no schema names `authority`,
   `observations` or `provenance`.
2. Over the `ls` tool on 10,000 files: the text block is at most
   32,768 characters plus the marker; `structuredContent` holds exactly
   the rows the text showed plus one `truncated` warning with the
   elided count; a 10,000-image result yields at most 8 typed blocks,
   4 MiB raw, 64 links; `structuredContent` carries no bytes and
   validates against the payload schema (`ResultPayload`,
   *proposed*).
3. `isError == not structuredContent["success"]`; `cli('grep nomatch
   f')` and `cli('false')` are `isError: false` with `exit_code == 1`;
   `cli('cd /notes')` then `cli('pwd')` prints `/`; `timeout_ms` above
   10,000 leaves the deadline at 10 s.
4. `resources/read` returns a blob with `mimeType` for a bytes row and
   the exact text for a text row; a row over 12 MiB is refused
   `-32603` after one `stat` and zero body bytes bound; `vfs:///` URIs
   round-trip a space, `#`, `?`, `%` and a non-ASCII letter.
5. The wire validates against the vendored 2025-06-18, 2025-11-25 and
   2026-07-28 schemas; an older client gets links and audio flattened
   to placeholder text, never a refusal; the core install imports
   nothing from `mcp`.
6. `readOnlyHint`, `destructiveHint` and `idempotentHint` are derived
   from `ops.py` (`IDEMPOTENT_OPS`) and K5's replay table; a verb with
   one non-idempotent form withholds the hint (D11).
7. Two tenants, end to end: two principals over one served tree with
   different grants see different `ls`, `grep` and `glean` answers
   over HTTP, and a hidden row never appears in the other's `glean`
   statistics or `graph` walk (the E5 assertion run through the wire).
8. HTTP with no token under a `read` posture serves `tools/list` and
   `ls` as `Authority.anonymous()`; `write` is `vfs.unauthenticated`
   with zero mutation statements.

#### M2 — The one-line entry point: `vfs serve` and `python -m vfs.mcp` · new · M · gate b

*Why.* "Easy to serve" means a line a Claude Desktop, Codex or
LangGraph config can name. It needs a router-from-URL constructor,
which is small: a URL, an embedder spec (E3), a workdir, an authority
or a verifier.
*Depends on.* M1, E3, D3; D24.
*Acceptance.*
1. `vfs.mcp.router_from_url(url, *, embedder=None, workdir="/",
   authority=None, verifier=None) -> VirtualFileSystem` is the one
   constructor `serve`, `sh` and `reindex` share; a drift test pins its
   signature.
2. `[project.scripts] vfs = "vfs.cli:main"`; `vfs serve --url
   sqlite+aiosqlite:///x.db --transport stdio --as me` and `python -m
   vfs.mcp …` start a server whose `tools/list` equals M1's;
   `--embedder openai:text-embedding-3-small@1024` configures the
   mount.
3. Starting against an open mount exits 78 (`EX_CONFIG`) naming every
   open mount unless `--allow-open`; `--as system` exits 64
   (`EX_USAGE`) before binding; both print to stderr and start no
   transport (spied).
4. `vfs --help` works without the `mcp` extra (import-graph test); the
   subcommands at 0.1.0 are `serve`, `sh` (one `cli` line or a REPL
   over a URL) and `reindex`.
5. `docs/how-to/expose-over-mcp.md` has the steps and a Claude Desktop
   config block; the fences pass.

#### M3 — `pending` on the wire · amends spec 171 scope · M · gate f

*Depends on.* H3, H4, H5, M1.
*Acceptance.*
1. `serve()` surfaces `pending` as the protocol's `input_required`
   with a `requestState` signed by the server's key (HMAC) carrying
   the `run_id`, the principal digest of the run's recorded authority,
   the TTL and the digest; the text content is H2's diff-shaped block
   when a plan exists; a one-byte change is refused `vfs.invalid` with
   zero handler calls (spied); a `requestState` whose principal digest
   differs from the run row's is `vfs.permission_denied` with zero
   steps run; a client on a
   revision without `input_required` gets the `pending` text and
   payload as a `complete` error result.
2. A resumed `tools/call` with `inputResponses` resumes the run (H4):
   recorded steps are served from the ledger and the stopped step
   re-enters the gate and runs once.
3. `answer` and `resume` are exposed as two tools carrying the
   request's principal (I2), so a run stopped over the wire can be
   continued over the wire by an authorised approver.
4. A suspended `cli` line does not become an MCP task at 0.1.0 (D25);
   the client polls `/.vfs/jobs`.

---

## 12. Domain I — Developer experience: sync, Jupyter, ETL, docs

**Goal.** A notebook cell and a plain script use vfs with sync calls
and no event-loop ceremony. One import gets an ETL developer `Entry`, a
storage and a file system. A 10,000-row batch is one call, atomic,
bounded, pinned at the router. The docs have one tutorial, the how-tos
a host and a pipeline need, and reference pages for `Result`, every
verb and storage. Nothing under `examples/` imports a dead name.

### State today

| Piece | State |
|---|---|
| Every public verb `async def`; no sync facade | missing; a 25-line thread-loop prototype works in a script and over the in-memory backend (audit 06; the real-ipykernel run is the audit's, not re-verified) |
| Top-level exports | `VirtualFileSystem` only |
| 10,000-row `write(entries=)` | works, 35–49 statements on SQLite; pinned at storage level only |
| Docs | 29 pages, 38 Sybil fences pass; 8 stub pages; `api.md` covers identity and graph only; 5 pages off the nav |
| Examples | 6 of 9 import dead names (`DatabaseFileSystem`, `VFSClient`, `grover.*`); none run in CI |
| Logging | no `import logging` anywhere in `src/vfs` |
| Install | `pip install vfs-py` gives 0.0.22; CONTRIBUTING and CLAUDE.md disagree on the setup recipe |

### Stories

#### X1 — `vfs.sync`: a synchronous facade for notebooks and scripts · new spec · M · gate b

*Why.* The smallest correct design is a facade that owns a private
event loop on a daemon thread and forwards every verb to the one gate
through `run_coroutine_threadsafe`: about 100 lines, no new dependency,
no kernel change, a fourth front in ADR 087's sense. Greenlet
(SQLAlchemy's bridge) is the inverse direction and would mean a kernel
rewrite; `anyio`'s portal is the same design plus a core dependency;
unasync codegen needs a whole sync storage path. The facade constructs
the `VirtualFileSystem` itself so first touch lands on its loop (the
asyncpg loop-affinity case); wrapping an already-awaited file system
is documented as SQLite-only until pinned.
*Depends on.* Nothing. D26, D27.
*Acceptance.*
1. `with SyncVirtualFileSystem(storage=InMemoryStorage()) as fs:
   fs.write(path="/a.txt", content="x"); fs.read("/a.txt")` returns
   `Result`s with `success is True` in a plain `python -c` with no
   running loop.
2. The same cells executed through a real ipykernel succeed while the
   kernel loop is running; no `RuntimeError`, no `nest_asyncio`.
3. A parity test asserts, for every verb in `ALL_OPS` and every name in
   the management allowlist (`MANAGEMENT_METHODS`, promoted to `ops.py`
   here if F3 has not yet), that the sync signature equals the async
   one, and `SyncSession` matches `Session`; the parity test is the
   one place later verbs (`cli`, `versions`, `answer`, `resume`,
   `cancel`, `calls`) and arguments (`strict=`) must pass, so it
   fails loudly when a verb joins `Session` without a sync twin.
4. A sync call issued from the facade's own loop thread returns a
   classified `vfs.invalid` naming the deadlock, never hangs.
5. `close()` and `__exit__` stop the loop thread (no `vfs-sync-loop`
   thread remains); a verb after close returns
   `vfs.unavailable.backend` (detail: the filesystem is closed), never
   raises.
6. On the Postgres leg, a `SyncVirtualFileSystem` over an asyncpg URL
   serves `write` then `read` from a script whose main thread runs its
   own `asyncio.run` in between.
7. A 10,000-entry `fs.write(entries=...)` through the facade issues the
   same statement count as the async path; loop and thread creations
   are counted: one per facade, not per call.
8. `serve()` stays async-native.

#### X2 — ETL ergonomics: top-level exports, iterables, a router-level 10k pin · S · gate b

*Depends on.* X1. D28.
*Acceptance.*
1. `from vfs import Entry, DatabaseStorage, InMemoryStorage,
   SyncVirtualFileSystem` imports; `__all__` lists them; the dependency
   walk still loads no numpy.
2. `fs.write(entries=(Entry(...) for _ in range(10_000)),
   parents=True)` (a generator) succeeds with the same statement count
   as a list.
3. A router-level pin counts statements for a 10k `write` through
   `VirtualFileSystem`, parents walk included, and asserts the count is
   independent of N beyond chunk arithmetic (the same family as D4).

#### X3 — Getting-started tutorial, notebook how-to, pipeline how-to, human-in-the-loop how-to · M · gate f

*Acceptance.*
1. `docs/tutorials/getting-started.md`: install → construct → write →
   `glob`/`grep`/`glean` → one rendered `Result`, every step a fence
   Sybil runs, no Postgres needed; the README's quick-start block is
   fence-tested too.
2. `docs/how-to/use-vfs-in-a-notebook.md` shows the sync and the
   `await` paths side by side and names the two `RuntimeError`s a user
   sees from `asyncio.run`.
3. `docs/how-to/bulk-load-from-a-pipeline.md`: a 10k batch from an
   iterable, the whole-batch-atomic rule, `reindex()` after binary
   writes and its `conflict` retry.
4. `docs/how-to/human-in-the-loop.md` (H3's example).
5. A test asserts every `docs/**/*.md` is referenced by the mkdocs nav;
   `mkdocs build --strict` passes.

#### X4 — Reference pages: `Result`, every verb, storage · M · gate f

*Acceptance.*
1. `docs/reference/result.md`: `Result`, `Observation`, `ResultError`,
   the `ErrorKind` table generated from the enum (a test asserts every
   kind appears), `|` merging, `to_payload`/`from_payload`.
2. `docs/reference/api.md` (K9) is the one signature page; a narrative
   page per verb family links to it; the import test runs against
   `api.md` only.
3. `docs/reference/storage.md`: constructor parameters, built vs
   borrowed, `install_extensions`, the schema contract (D2).
4. No page under `docs/` is a heading with no body.

#### X5 — Install page and the one setup recipe · S · gate f

*Acceptance.* `docs/how-to/install.md` lists the extras (a test asserts
every `pyproject.toml` extra appears), the wheel platforms from
`publish.yml`, "no Rust toolchain on a listed platform", Python
3.11–3.14, and the Alpine note; `CONTRIBUTING.md` and
`docs/contributing.md` are one source using `uv sync --all-extras
--group dev`.

#### X6 — Examples: delete the dead, run the live · S · gate b

*Acceptance.* `cli_query_demo.py`, `demo_dbfs.py`,
`postgres_backend_playground.ipynb`, `postgres_repo_glob_grep.ipynb`,
`repo_postgres_cli_smoke.ipynb` and `story_001_demo.ipynb` are removed
(D29); `main.py` is removed or ported; `glean_walkthrough.ipynb` is
executed in CI via nbclient against the live tree; `glob_residuation.ipynb`
uses public names or is removed; a test asserts no file under
`examples/` imports `vfs.backends`, `vfs.client`, `vfs.query`,
`sqlmodel` or `grover`.

#### X7 — One named logger · S · gate b

*Why.* `src/vfs` has no `import logging`, yet I2 and I6 want warning
records and an operator needs somewhere to look. The logger name is
public surface.
*Depends on.* Nothing.
*Acceptance.*
1. One logger, `vfs`, with child names per package; no `print` in
   `src/`.
2. A test asserts no log record ever contains a body, a credential or
   a token (a corpus of secret bytes grepped across `caplog` over the
   whole suite).
3. The levels used and what each carries are listed in
   `docs/reference/storage.md`.

---

## 13. Domain J — Release engineering and repository hygiene

**Goal.** The lane runs: a version that can be a pre-release, a
publish matrix that has been dry-run, yanked dead numbers, a changelog
that starts over, a README that tells the truth, standards that
describe the tree that exists, and an active-spec set that equals the
0.1.0 work.

### State today

| Piece | State |
|---|---|
| `test.yml` (3.11–3.14; lint, format, types, 100% coverage, docs fences on 3.13) | green on `main` 2026-10-28 |
| `test-dialects.yml` (four engines from `docker/compose.test.yml`) | MSSQL red at the `apt` step |
| `publish.yml` seven-platform matrix | never run; no `workflow_dispatch`; no tag check; `macos-13` (retired) |
| PyPI | 0.0.20–0.0.22 present, none yanked; `pyproject` 0.0.22; `__init__` a literal copy; `uv.lock` 0.0.22 |
| `scripts/bump_version.py` | cannot emit `0.1.0a1` |
| `CHANGELOG.md` `[Unreleased]` | pre-rebuild residue |
| README lines 19 and 135 | say PyPI ships the previous-generation API |
| Standards | `tooling.md`, `testing.md` *Running*, `release.md`, this page's predecessor all describe a tree that no longer exists; `versioning.md` pending since the constitution; the constitution itself names `Candidate`, `VFSResult`, `if_revision` and seven kinds |
| `SECURITY.md`, `THREAT_MODEL.md` | absent |
| Root-level strays | `ROADMAP-v0.1.0.md`, `write-pipeline.md`, `pr_description.md`, a SQLModel issue write-up, `coverage.json` (tracked, 2026-04-23), `grep_glob research/`, `business/`, `vfs-app/`, `vfs-brand/`, `logos/` |
| Context pipeline | 31 active specs; 165, 162, 152 A/B, 173 built but not archived; 161, 051, 102 overtaken; `STATUS.md` 1,168 lines and stale on 162 |

### Stories

Spec 166's *Scope* items are numbered: 1 the version source, 2 the bump
script, 3 the publish dispatch and tag check, 4 the maturin floor, 5
the changelog, 6 the README, 7 the matrix dry run, 8 the yank, 9 the
cut. Its *decision* 5 is the final bar.

#### R1 — Release plumbing · spec 166 scope 1–4 · S · gate a

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

#### R2 — Dry-run the matrix, fix the MSSQL leg, decide musl · spec 166 scope 7 · S · gate a

*Acceptance (CI evidence).*
1. A dispatched `publish.yml` run from `main` is green on all eight
   jobs; its run id and per-wheel sizes are in spec 166's landing notes.
2. The MSSQL leg installs the ODBC driver on the current runner; the
   next storage push is green on all four legs.
3. musllinux is decided (D30).
4. Trusted publishing is confirmed configured (a note in `release.md`).

#### R3 — Cut `0.1.0a1` from the tree as it stands · spec 166 scope 5, 6, 8, 9 · S · gate a

*Acceptance.*
1. `CHANGELOG.md` has no pre-rebuild `[Unreleased]` content;
   `[0.1.0a1] — <date>` lists the verbs, backends, dialects, the ladder,
   the graph walk, trash-as-tombstone, binary bodies, with a *Breaking*
   group saying nothing from 0.0.x carries over, and the alpha template
   line about schema bumps (D2).
2. README lines 19 and 135 no longer say PyPI ships the old API; pin
   guidance reads `vfs-py>=0.1.0a1,<0.2` with the one-line reason; the
   Alpine note is present.
3. 0.0.20, 0.0.21, 0.0.22 are yanked on PyPI with spec 166's reason;
   the three GitHub release bodies carry the same line (CI evidence).
4. On `python:3.13-slim` x86_64 and aarch64: `pip install vfs-py`
   installs `0.1.0a1` and `import vfs, vfs.native` works; `pip install
   "vfs-py<0.2"` fails with no matching distribution; `==0.0.22`
   installs with a yank warning (CI evidence).

#### R4 — The engine legs from the published wheel · S · gate f

D6's items 2–3; listed here because it is the lane's final gate.

#### R5 — Freeze the surface: the beta-entry decision · S · gate b

*Acceptance.*
1. K9's list exists and `docs/reference/api.md` matches it.
2. ADR 087's pins 3, 12, 16, 17 and spec 174's `overwrite=` question are
   resolved (K1).
3. Every active spec is tagged `0.1.0` or `0.2.0+`; none tagged
   `0.2.0+` renames or removes a frozen name.
4. Clay's freeze call is a dated line in `release.md` and in the
   `[0.1.0b1]` changelog section; the classifier reads Beta.
5. `context/standards/versioning.md` exists: the beta rule (no rename,
   no removal, no change of meaning; additions listed under *Added*),
   what a breaking change is in `0.x`, the deprecation window, what
   the changelog's *Breaking* group must say.
6. The constitution's Art. 1.2, 1.3, 1.5 and 2 §1 are amended to the
   frozen names (`Entry`, `Observation`, `Result`, `version` and
   `if_version`, the `ErrorKind` enum) in the same landing.
7. Every README and docs claim is re-checked against ADR 058 pin 7 at
   b1.

#### R6 — Repository hygiene · S · gate b

*Acceptance.*
1. The root holds only `CHANGELOG.md CLAUDE.md CONTRIBUTING.md
   Cargo.lock Cargo.toml LICENSE README.md SECURITY.md
   THREAT_MODEL.md conftest.py mkdocs.yml pyproject.toml uv.lock` plus
   dot-files and directories. Dispositions (D31): delete
   `ROADMAP-v0.1.0.md`, `write-pipeline.md`, `pr_description.md`, the
   SQLModel write-up, `coverage.json` (and ignore it); move `grep_glob
   research/` to `context/research/2026-04-24-grep-glob-pushdown/`;
   move `business/` under `context/product/` or to a sibling repo;
   move `vfs-app/`, `vfs-brand/` and `logos/` to their own repo.
2. `tooling.md`, `testing.md` *Running*, `release.md`, `CONTRIBUTING.md`
   and `tests/conftest.py`'s docstring describe the maturin / `uv
   sync` / env-URL tree.
3. `src2/` and `tests2/` are deleted or shrunk with a dated note of
   what remains unmined (D32).
4. The headlines are reconciled to ADR 075's line everywhere a reader
   lands: README ("Governed data access for AI agents"),
   `docs/index.md` ("Agentic Search on your Database"), `mission.md`
   ("the agentic filesystem", and its "local disk" promise is
   re-worded to 0.2).
5. The README gains a one-paragraph "when not to use vfs" (ADR 069 pin
   6).

#### R7 — Context-pipeline true-up · S · gate b

*Depends on.* K1, H1.
*Acceptance.*
1. Specs 165, 162, 152 (A/B closed; C/D re-cut or tagged 0.2), 173 move
   to `specs/archive/` with landing notes; their stale "uncommitted"
   lines are corrected first.
2. Spec 161 is dropped (its write half landed with the tombstone
   mint; its read half is K8); spec 051 is replaced by H6; spec 102 is
   closed as overtaken by the tombstone delete or re-cut against
   `move`/`copy` at 10k; spec 080 is tagged per D3.
3. `STATUS.md` is replaced by a table of at most 60 lines (spec,
   status, gate, landing commit) regenerated from the spec status
   lines; the history moves to a dated research memo or is deleted.
4. The ten proposed ADRs (022, 058, 069, 081–087) are each ratified,
   amended or withdrawn; pending leans are zero before `0.1.0b1`.
5. `open-questions.md` entries resolved by landed work move to the
   archive; the "what makes 0.1.0 final" entry is answered by D2.
6. CLAUDE.md's *Production posture* names three audiences — agents,
   software developers building the host, ETL developers — in the
   words of §1.2; `spec 051` is replaced by H6.

#### R8 — `SECURITY.md` and `THREAT_MODEL.md` · S · gate b

*Why.* The headline is "governed"; ADR 068 ships `read_write` for
anonymous by default in process; every security-review buyer looks for
a disclosure policy. A threat model is its own small document, not a
sub-bullet of hygiene.
*Depends on.* Nothing.
*Acceptance.*
1. `SECURITY.md`: how to report, the supported versions line, the
   response window.
2. `THREAT_MODEL.md`: ADR 087's three trust tiers (in process a
   convention; on the wire and in a guest a wall); the out-of-band SQL
   writer and what K3 catches; the system actor; the open default and
   `serve()`'s refusal; prompt injection through file bodies into
   tools; what is and is not logged (X7); which rows of the YoloFS
   incident taxonomy vfs closes.
3. The promise in §1.1 links to it.

#### R9 — One benchmark memo with 0.1.0 · S · gate f

*Why.* Wall-clock belongs in a bench memo, never a test (CLAUDE.md);
the README needs a number and the product plan's first gate lists one.
*Acceptance.* A dated memo under `context/research/` records
agent-sized call latency (one `read`, one `grep`, one `write`) and the
10k-batch wall time on SQLite and each engine leg from the published
wheel, with the statement counts beside each number; the README links
it.

---

## 14. Sequencing: alpha batches, the dependency chain, the arithmetic

The order is dependency-driven, then harm-driven. Stories within a
batch are independent unless an arrow says otherwise.

| Alpha | Carries | Why this order |
|---|---|---|
| **a1** (this week) | R1, R2, R3 | The lane must exist before anything rides it. |
| **a2** — the three defects, the two ADRs, the spike | K1, H1 → K2, K3, K5; F1, F2; L0; I6; X7; R8; K1, H1 → R6, R7 | The ADRs first: eight specs and every interrupt story stand on them. K2/K3/K5 close the three live defects. F2 is now the whole grammar. L0 prices the log before H0 is shaped. |
| **a3** — the filesystem arguments, the session's memory, the lifecycle, the facade | K4, K6 → K9; K2, K3 → K10; H2; I3a; D1, D2 → D3; D4; E1, E2, E3, E5; X1 → X2; X6; I5 | Cursor, range, the regroup and the freeze list. The session stamps. `plan=` rides the write seam. Storage lifecycle and the matrix. Search defaults. The sync facade. |
| **a4** — the log, the interrupt and the shell | L0, K4, K5 → H0 → H3; F3 → F4 → F7; I1; E4 | The action log first: H3's ledger lives in it. H3 then depends on H0, H1, H2 and K5, so Clay's first theme lands here, not last. The pipe, the forms and the language are the long pole. |
| **a5** — tools, the guests and the front | T1 → T2 → T3 → I3b → T4; T1 → T5a → T5b (after D49's spike); I2; M1 → M2 | Views, host tools, servers, the two guests, the adapter, the one-line serve. |
| **a6** — the durable run and interrupts for every kind | H4 → H5 → M3; I4; H6 | The run ledger over the log; then tools, guests and the wire stop and resume through it. |
| **b1** — freeze | R5 (after every `b` story above) | Nothing after b1 renames or removes a public name. |
| **beta → final** | K7, K8; D6/R4, D7; E6; F5, F6; X3, X4, X5; R9 | Proof on every leg, docs, the bench. |
| **0.1.0** | A beta held ≥ 14 days; D6/R4 green from the wheel; every `f` story landed. | |

**Critical path, in one line:** K1 → K2 → F3 → F4 → F7 → T1 → T3 →
I3b → T4 → M1 → H4 → H5. Ten L or XL items in series; H0 sits beside
F3 in a4 and gates H3, H4 and T2 but not the shell.

**The arithmetic.** On the page's own scale (S ≤ 1 day, M 2–4 days, L
1–2 weeks, XL > 2 weeks), the batches sum to about:

| Batch | Composition | Effort |
|---|---|---|
| a1 | 3 S | ~3 days |
| a2 | 3 L, 2 M, 8 S | 5.5–9.5 weeks (F2 is now L; L0 added) |
| a3 | 10 M, 8 S | 5.5–10 weeks (K10 added) |
| a4 | 1 XL, 4 L, 2 M | 7–13+ weeks, F3 → F4 → F7 serial; H0 beside them |
| a5 | 4 L, 5 M, 2 S | 6.5–12.5 weeks, mostly serial (T5b and its spike added) |
| a6 | 2 L, 3 M | 3–6.5 weeks, H4 → H5 serial |
| beta → final | 1 L, 8 M, 4 S | 5.5–10 weeks |
| **Total** | | **about 34–62 weeks** |

The fourth revision added two L stories (F7, H0), two M stories (K10,
T5b), two S spikes (L0, D49's) and widened F2 from M to L: roughly
four to seven weeks on the page's scale. None of the four is a cut
candidate (Clay, 2026-10-28); the cut order below is unchanged and
the structural option (D2 item iii) is the lever that absorbs them.

Measured throughput from the spec archive (status lines "landed
2026-MM"): July 20, August 44, September 8, October 7 specs a month.
The pace fell about five-fold as specs became kernel-sized. At the
autumn rate the page's seventy-odd stories are eight to ten months; on
the effort scale, eight to fourteen. The product plan's own finding
was that every plan exceeded solo capacity three to four times. This
page does not pretend otherwise; it gives Clay the cut order below and
one structural option (D2).

**Cut order if capacity binds** (first cut first; each keeps a promise
sentence true or moves a half-deferred theme whole):

1. F6's Rust port → 0.1.x; ship `sort uniq tr tee` and `xargs` as
   Python transforms inside F4. No name changes.
2. H6 → 0.2 except `cancel(ticket)` and `cancel(run_id)` (S).
3. M3's `input_required` mapping → 0.2; ship only its fallback (the
   `pending` text and payload as a `complete` error result) and the
   `answer`/`resume` tools. H3's LangGraph host does not need the wire
   mapping.
4. K7 → keep the atomic-unit pin (criterion 1, as a D4 pin) and the
   trait; move crash injection, `engine_error` and `features()` to
   0.1.x.
5. D7 → 0.1.x; document `engine_kwargs` pass-through in D3's how-to.
6. H5's MCP-elicitation leg → 0.2; keep the host-tool interrupt, the
   guest's asks and the shell stage.
7. T4's supervisor and respawn → 0.1.x; in-process and plain stdio
   only.
8. T5's numpy/pandas bundle → 0.1.x; ship the stdlib-only guest first.
   The guest's shape and the door do not change.
9. **The structural option (D2, lean):** ship 0.1.0 with the shell core
   (F3, F4, F7), host tools (T3) and the two guests (T5a, T5b), and make MCP
   servers as views (T4), the credential seam (I4) and OAuth on demand
   (T7) the headline of 0.2, where "acting as the user" can be done
   whole instead of half. This removes an L from the serial chain and
   the hardest cross-process piece. Theme 4(b) then moves to 0.2
   cleanly rather than shipping as "one host credential per server"
   and being called "as the user". The durable run (H4) is not a cut
   candidate: it is what Clay's interrupt requirement means.

**Where the kernel specs and the shell specs touch.** Spec 167 as
drafted ships a racy `>>` and a `stat`-then-`write` `touch`; spec 174
replaces both. K2 lands before F3 (D33). The one flag name is
`replace=`.

---

## 15. Deliberately not in 0.1.0

| Item | Where it goes | Why not now |
|---|---|---|
| `pack`, the bounded `sweep`, the garbage gauge (spec 180's rest) | 0.2 | Correct without them; the full history is kept. |
| `scrub` (spec 175 D) | 0.2 | Report-only; nobody is asking yet. |
| Actor- and time-keyed history queries (`versions(since=, actor=)`); versioning of grant and posture changes | 0.2 | The Catalog's prerequisite; named here so its plan does not assume it. |
| A precondition argument on every mutating verb (H2's full form) | 0.2 | `write`/`edit` carry `if_versions`; the rest check at apply (D37). |
| The generic wasm host, `awk`, `jq`, uutils (T6) | 0.2 unless D22 | XL; duplicates a host wasi-python owns. |
| OAuth on demand for mounted servers (T7); token exchange; enterprise-managed authorization | 0.2 | One shipping IdP; I4's seam is the honest 0.1.0 shape. |
| `manage` rung, group ownership, non-system membership admin | 0.2 | Parked; not needed to serve one organisation. |
| Narrowing with content, child sessions (spec 148 §1–4) | 0.2 | `Narrowing.NONE` is honest; sub-agents can use a second `Session`. |
| Width-change migration (E7), tuned fusion defaults, render at write (159), images (152 C), `imports` edges (147), signals on by default | 0.2 unless D21 | Independent of theme 3. |
| MCP tasks for long `cli` lines; a `/.vfs/mounts` view | 0.2 | A stopped run is polled through `/.vfs/jobs` at 0.1.0 (D25). |
| Recording every host import of a guest (full determinism), or a memory snapshot of a stopped guest | 0.2 | Re-entry with fingerprint-matched door calls is correct and simpler (D42). |
| `/.vfs/jobs/<run>/steps` | 0.2 | Asks are the only view a person needs at 0.1.0; step rows hold bodies. |
| Answering an ask by writing a file under `/.vfs/jobs` | 0.2 | `answer` is the one door at 0.1.0; the views stay read-only (T1). |
| A per-call statement and timing counter *on `Result`* | 0.2 | The counts and the elapsed time land in the action log (H0), where an operator reads them; a host-facing field on the envelope is a later seam. |
| An OpenTelemetry exporter; a `/.vfs/log` view; log rows readable by a non-system principal | 0.2 | The action log (H0) is the data; the exporter and the agent-facing view read it later. At 0.1.0 the schema is documented and the system actor pages it (D53). |
| A local-disk storage backend; a change feed; an object-store data plane; reference adapters for host frameworks | 0.2+ | The wedge is "the database you already run"; adapters need `serve()` first. |
| Stamps over the wire (a per-principal session table in `serve()`) | 0.1.0 if D51 says so, else 0.2 | Spec 171 decided no sessions on the wire; K10's guard over MCP needs one bounded table per principal. |
| `eval`, job control past the call (`jobs`, `fg`, `bg`), `exec`, `trap` | later, if ever | No meaning inside one gated call (D47, D48); `/.vfs/jobs` and the durable run are the job model. |
| FUSE or NFS fronts | later | A facet by ADR 087; the copy never promises it. |
| Diff/cmp kernels (168c); the Rust port of 168a if cut | 0.1.x | Can slip without changing a name. |

---

## 16. Decisions Clay must make

A lean is the assistant's recommendation, not a decision.

| # | Decision | Lean | Needed by |
|---|---|---|---|
| D1 | `0.1.0a1` ships the tree as it stands, decoupled from spec 167? | Yes; the shell is a4. | a1 |
| D2 | What makes `0.1.0` final, and what does the beta freeze forbid? Options: (i) the held-beta bar alone; (ii) the bar plus the full `f` gate on this page; (iii) the bar plus the gate with the structural cut of §14 item 9 (shell core, host tools and the Python guest in; MCP servers as views, the credential seam and OAuth to 0.2). The freeze: no rename, removal or change of meaning; additions allowed and listed. | (iii), with the additive freeze rule. | before b1 |
| D3 | MariaDB: first tier, second tier (served, in CI, no ANN, per-row updates documented), or dropped? | Second tier. | D1 |
| D4 | ADR 087 pin 3: keep `delete`/`move`, or rename `remove`/`rename`? | Keep. | K1 |
| D5 | ADR 087 pin 16: flat names, or kernel groups as namespaces? | Flat. | K1 |
| D6 | ADR 087 pin 12: the resumption key as a `Result` field, or a separate return? | A field. | K1, K4 |
| D7 | Spec 174: `overwrite=` leaves `write`? | Yes. | K2 |
| D8 | ADR 087 pin 9: the integrity kind. The first draft leaned a top-level `vfs.integrity`; spec 175 leans the child `vfs.unavailable.integrity` so old consumers degrade to EIO. Keep the 100 KB offload threshold. | The child kind, as spec 175 says. | K3 |
| D9 | Amend ADR 084 pin 4 so vfs *carries* `pending` (never asks, never blocks)? | Yes. | H1 |
| D10 | `pending`'s shape: top-level `vfs.pending` with a derived retry class `resume`, or a child of `permission_denied`? Ledger in the mount's schema? TTL? | Top-level; the mount's schema; 24 h. | H1 |
| D11 | ADR 087 pin 10: withhold `idempotentHint` from a tool whose verb has one non-idempotent form? | Withhold. | K5, M1 |
| D12 | The exit code for a suspended shell stage (this page's proposal; no spec carries it). | 75 (`EX_TEMPFAIL`). | H5 |
| D13 | Spec 149: ignore a `groups` claim? | Ignore. | I1 |
| D14 | Spec 149: add an `attested` provenance? | Add it. | I1 |
| D15 | What "open" means on the ladder for `serve()`'s refusal (ADR 068 rule 7, after ADR 080 retired the old words). | Refuse when any mount's root everyone-level is `add` or above. | I2 |
| D16 | MCP servers as the user: host-supplied resolver (a), vfs-owned store (b), token exchange at the edge (c)? Subject sets over a per-user server? | (a) at 0.1.0 (or 0.2 under D2 (iii)); never (c) inside `Authority`; refuse subject sets. | I4 |
| D17 | Validate declared owners; keep group ownership parked; a `loud=` flag for the default-authority fallback? | Yes to all. | I6 |
| D18 | Oracle naming in the matrix. The compose image is `gvenzl/oracle-free:23-slim`; the vector type arrived in 23.4. | Name the floor 23.4+ and the image tag. | D1 |
| D19 | Schema lifecycle from `0.1.0b1`: D2 as written? A corrupt version row as `vfs.unavailable.corrupt`? | Yes; yes. | D2 |
| D20 | Default local embedder: amend ADR 060 to model2vec potion, or build fastembed/MiniLM? | Amend; keep fastembed as a documented LangChain route. | E1 |
| D21 | Render at write (159) in 0.1.0? | No, unless the first served pilot hits it. | E8 |
| D22 | A generic wasm host for `awk`, or ship without? | Ship without; refuse with a hint; ask wasi_python in parallel (D49's spike asks the same project). | T6 |
| D23 | The guests: gate, stretch, or 0.2? | **Decided** (Clay, 2026-10-28): Python and JavaScript both in 0.1.0, gate b, behind `vfs-py[python]` and `vfs-py[javascript]`. | — |
| D24 | Reverse spec 171 decision 7: ship `vfs serve` and `python -m vfs.mcp`? | Yes. | M2 |
| D25 | A suspended `cli` line as an MCP task at 0.1.0? | No. | M3 |
| D26 | Sync facade: thread-loop (no dependency) or `anyio` portal? | Thread-loop. | X1 |
| D27 | May the facade wrap an already-awaited file system? | Yes, documented SQLite-only until pinned. | X1 |
| D28 | Top-level exports `Entry`, `DatabaseStorage`, `InMemoryStorage`, `SyncVirtualFileSystem`? | Yes. | X2 |
| D29 | Stale examples: delete, or archive beside `src2/`? | Delete. | X6 |
| D30 | musllinux wheels: keep or drop the two jobs? | Drop; note it. | R2 |
| D31 | Where `business/`, `vfs-app/`, `vfs-brand/`, `logos/` live. | Sibling repos; `business/` under `context/product/` if it must stay. | R6 |
| D32 | Delete `src2/` and `tests2/`, or keep shrinking? | Delete what `MINING.md` marks mined; list the rest. | R6 |
| D33 | K2 (174) before F3 (167 C)? | Yes. | a2 |
| D34 | The 0.1.0 program table: all of 167, 168a and 168b in; 168c, `awk`, `jq` out; shell spellings for `grant`/`revoke`/`grants`? | As stated; add the three spellings in F4. | F4 |
| D35 | The JOSE library behind `vfs-py[serve]`. | `joserfc`. | I1 |
| D36 | Creation attribution: the v1 version row carries the creator (K8 as written), or a `created_by` column on the entry row? | The version row. | K8 |
| D37 | A precondition argument on every mutating verb now (H2 full form, size L) or stat-at-apply with a documented window? | Stat-at-apply at 0.1.0. | H2 |
| D38 | A `/.vfs/mounts` view? | No; `mounts()` is the API. | T1 |
| D39 | This page lives at `context/standards/roadmap.md` and the root `ROADMAP-v0.1.0.md` is deleted? | Yes. | R6 |
| D40 | When one step asks, does the run stop at once, or drain first — let the other stages of that pipeline finish or reach their own ask, so asks raised together are surfaced together? | Drain, then stop, per pipeline; a suspended stage's consumer sees neither data nor end-of-stream; later statements of the line are not run. | H4 |
| D41 | What a run records: every step (reads too), or effects plus the reads the walk depends on? | Effects, expansion reads (`glob`, `$( )`, `find`, `stat`, `test`) and every read's identity triple always; bodies only where a guest or tool consumed them, within `RUN_LEDGER_BYTES`; a re-executed read is hash-checked. | H4 |
| D42 | How a stopped Python guest or host tool resumes: re-enter from the start with its vfs calls served by fingerprint (a diverging call is made fresh and marked), record every host import for full determinism, or snapshot the guest's memory? | Re-enter and match by fingerprint at 0.1.0; the other two in 0.2. | H5 |
| D43 | Where the run ledger lives, its budget and TTL. | The root binding's storage; `RUN_LEDGER_BYTES` = 64 MiB per run (spec 169c's number), oldest run evicted first; TTL 24 h, the same sweep arm as the replay store. | H4 |
| D45 | Whose authority a resumed step runs under, and who may resume. | The run's recorded authority, always, re-judged by the gate; `resume` is allowed to the owner or to an approver holding `read_write` on every open ask's path. | H4, M3 |
| D46 | A step left `running` by a crash: refuse it in doubt and ask the host, or re-enter it? | In doubt; the host answers `done` or `redo`. | H4 |
| D44 | The API shape: `answer(ticket, …)` per ask plus `resume(run_id)` per run (answers can arrive one at a time, from different approvers, from different processes), or one `resume(run_id, answers={…})`? | `answer` per ask and `resume` per run; a bare verb's ticket is its run id, so `request_key=ticket` stays as the one-step resume. | H3, H4 |
| D47 | `&` in the full language: refuse it forever (ADR 081 pin 8 as written), or admit `cmd &` and `wait` as concurrency bounded by the call — the line waits for every job at its end, so the call never returns early — with `jobs`, `fg`, `bg`, `disown` and `nohup` refused? | Admit the bounded form; refuse job control past the call. The durable run and `/.vfs/jobs` are the background model. | F2, F7 |
| D48 | `source`/`.` and `eval`: admit `source` of a literal path (read through the gate and parsed before the line runs; a computed path refused) and refuse `eval` as the one construct that defeats the pre-execution summary? | Yes to both. | F2, F7 |
| D49 | Who hosts the QuickJS-NG guest: ask the `wasi_python` project to host a generic `wasm32-wasip1` module over its mount and tool protocols, or pull 169b's host (T6) forward for QuickJS alone? A one-afternoon spike answers whether the runner can. | Ask `wasi_python`; the spike first; T6's host only if the answer is no. | T5b |
| D50 | K10: a write through a session to a path the session never read — proceed unguarded (today's behaviour), or refuse until read? | Proceed by default; `Session(strict=True)` refuses `vfs.invalid` naming the rule. | K10 |
| D51 | K10 over MCP: spec 171 decided no sessions on the wire. Keep a bounded per-principal stamp table inside `serve()` (process-local, `SESSION_STAMPS` per principal, swept with the connection), or leave the guard to the host at 0.1.0? | Keep the table: agents over MCP are the first audience and the guard is the point. Amends spec 171's "no sessions" to "no session *handles*". | M1, K10 |
| D52 | H0: the action log on by default with `LOG_RETENTION_DAYS = 30` and a `log=False` escape, or opt-in? Run and ask rows keep their own 24 h. | On by default; analytics is a 0.1.0 must (Clay). | H0 |
| D53 | H0's read side at 0.1.0: a documented, frozen table schema plus `fs.calls(...)` on the developer plane for the system actor, with a `/.vfs/log` view and agent-readable rows in 0.2? | As stated; the database you already run is the analytics surface. | H0 |
| D54 | The shell's nondeterministic words under the durable run (`$RANDOM`, `$SECONDS`, `$EPOCHSECONDS`, `$EPOCHREALTIME`, `$BASHPID`, `$$`, `date`): record each as an expansion read (D41) and replay it on resume, or refuse them in a line that may ask? | Record and replay. | F7, H4 |

---

## 17. One-line version

Ship `0.1.0a1` this week from the tree as it is; ratify the kernel and
the interrupt; close the three live defects; land the cursor, the
range, the preconditions, the session that remembers what it read, and
`plan=`; log every call vfs makes — who, what, how many, how long —
and make the interrupt real and the run durable over that log, so a
stopped line continues where it stopped; build the shell as the whole
bash language, then the tools and the two guests, then the front;
freeze when every public name is written down; call it `0.1.0` when a
beta has held and the engines pass from the wheel — and decide now
whether MCP servers as views ride 0.1.0 or lead 0.2.
