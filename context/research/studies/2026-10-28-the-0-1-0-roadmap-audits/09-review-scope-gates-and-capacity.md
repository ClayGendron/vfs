# PM review of `context/standards/roadmap.md` (vfs 0.1.0) — 2026-10-28

Reviewer hat: principal PM, read-only. Evidence is quoted from the roadmap
(section and story IDs) and checked against the repo (`README.md`,
`business/product-plan-2026-08.md`, ADRs 058/069/075/084/087, specs
166/167/170/171, `src/`, `.github/workflows`, the spec archive).

Short version. The page is the best plan this repo has had: every story has
a gate and countable acceptance. It has five real problems. (1) The
"definition of done" does not make promise 3 true and over-states promise 1.
(2) The beta "freeze" is nominal: 8 of the 15 `f` stories add public names
after the freeze. (3) The §2 gate list and the story tags disagree on five
stories. (4) §14 sums to roughly 26–48 weeks of effort and never says so,
while actual spec throughput has fallen to 7–8 landings a month. (5) The
preview promise contradicts H2's own acceptance for the "refused action"
case. Details and fixes below, in the order asked.

---

## 1. Does the definition of done make the three sentences true?

**Verdict: sentence 2 becomes true; sentence 1 is over-claimed for tools and
for in-process use; sentence 3 stays false in two of its five clauses even
after every `b`/`f` story lands.**

### Sentence 1 — "every read, search, write and tool call passes one gate that judges the caller's rights on every row"

- **Over-claim for host tools.** §10's table says a host tool "runs as: the
  host's authority (ADR 084 pin 3's one exception); receives the caller's
  `Fs` only if it declares one". T3 ac 5 pins caller-scoped rights *only*
  for a tool that declares an `Fs` parameter. So after T3 lands, a host tool
  that does not declare `Fs` runs with the host's full authority; the gate
  judges the *call* (`read` on `/.vfs/tools/<name>`, I3), not "every row"
  the tool touches. The sentence says rows. The gate list cannot make this
  true because ADR 084 pin 3 forbids it by design.
  *Fix:* "...passes one gate that judges the caller's rights on every row
  it reads or writes through vfs; a tool call is gated at its entry, and a
  tool runs with the authority its trust line names."
- **Over-claim for in-process use.** ADR 087 pin 5: "In process the gate is
  a convention: any caller can construct the system authority and reach
  the storage object (ADR 068, by design)." ADR 075's own consequences:
  "'Governed' is a claim the peers make in full and vfs makes in part".
  The promise never says which tier it is true in. ADR 087 pin 5 asks that
  this be said "in one place"; the promise is the place a buyer reads.
  *Fix:* add one clause: "on the wire and in the guest the gate is a wall;
  in process it is a convention your host code agrees to (THREAT_MODEL)".
  R6 ac 5 already asks for the file; the promise should point at it.
- **Minor:** "a governed file system" contradicts §1.3 ("the public copy
  says 'filesystem-shaped kernel'") and ADR 069 pin 6 ("vfs is not a
  filesystem emulation"). Use ADR 075's headline words: "governed data
  access ... with the interface of a file system".

### Sentence 2 — "`ls`, `cat`, `grep`, pipes — from Python (sync or async), from an agent shell, or over MCP"

- Becomes true with F3 (`cli`), X1 (sync), M1/M2 (MCP). **One hole:** X1
  ac 3 says the facade "exposes exactly `ALL_OPS` plus
  `MANAGEMENT_METHODS`". `cli` is a method on `VirtualFileSystem` (F3),
  not an `Op` in `ALL_OPS` (K9 ac 1 fixes `ALL_OPS` at 24 verbs). Unless
  `cli` is in `MANAGEMENT_METHODS`, the sync path has no pipes, and
  "from Python (sync ...) ... pipes" is false for the notebook user.
  *Fix:* X1 ac 3 names `cli` (and `Session.cli`) explicitly.

### Sentence 3 — "Every change is versioned and reversible, a refused or risky action can become a question ... with a preview ... and one permission structure governs a file and a tool alike"

- **"Every change is versioned" stays false.** §1.1's own footnote:
  "Version rows exist for replaced bodies only". K8 (the only history
  story in the gate) adds a *read side* for those rows plus `created_by`.
  Nothing in K1–K9 mints a version row for `move`, `mkdir`, `grant`,
  `revoke`, `posture`, `mkedge` or `rmedge`. R7 ac 2 *drops* spec 161
  ("every mutation mints a version row"): "write half landed in 162;
  read half is K8" — but 162 is "trash as a tombstone", not a version
  per mutation. ADR 069's consequence is explicit: "Until then public
  copy says 'reversible delete,' not 'every mutation is versioned.'"
  *Fix:* either (a) re-cut the write half of spec 161 as a `b` story
  (a schema change; it must precede the freeze), or (b) rewrite the
  sentence: "Every body change is versioned and every delete is
  reversible".
- **"reversible" has no revert verb.** K8 gives `read(path, version=N)`.
  Reverting a bad edit is `read(version=)` then `write(if_version=)` by
  hand. That is reversible in the way a tape backup is. Fine for 0.1.0,
  but say it: "reversible: any version can be read back and written
  again under a precondition".
- **"a refused ... action can become a question ... with a preview" is
  self-contradicted.** H3 ac 3 makes a liftable refusal `pending` with
  `needs="grant:<rung>@<path>"`. H2 ac 4 says `plan=True` "under a caller
  who may not perform the verb answers the same refusal the real call
  would ... never a plan." So the refused case — the one the sentence
  leads with — carries no preview. Only the policy-hook case (H3 ac 2)
  does. See §2 below for the fix.
- **"one permission structure governs a file and a tool alike"** becomes
  true with I3 (`rungs_at`, catalogue posture). Good.

### The §2 gate list drifts from the story tags

§2's "feature gate, in one list" omits five stories that carry a `b` or
`f` tag in their own heading:

| Story | Tag in heading | In §2 list? |
|---|---|---|
| K1 ratify ADR 087 | b | no (Kernel row starts at K2) |
| K7 storage seam / atomic unit | f | no |
| I6 validate owners / loud fallback | b | no (Identity row lists I1–I4) |
| E5 leak regression test + staleness trait | b | no (Search row lists E1–E4, E6) |
| D7 pool posture | f | no (Storage row lists D1–D4, D6) |

A reader who treats §2 as the gate (its title says it is) ships without
K1, which K2–K9 all depend on. *Fix:* generate §2 from the headings, or
drop the §2 list and make the tag in the heading the only source.

---

## 2. Are Clay's eight themes covered, and is the preview carried?

| # | Theme | Stories (gate) | Covered? | Gap |
|---|---|---|---|---|
| 1 | Kernel API, interrupts, preview | K1–K9 (b/f), H1–H3 (b), H4/H5 (f) | yes | preview gaps below |
| 2 | SQLite/Postgres/MSSQL/Oracle | D1–D7 | yes | MSSQL leg red today; D6 is `f`, fine |
| 3 | Embedder; BM25+vector at query time | E1–E6 | yes (built) | none |
| 4 | Three tool kinds, interruptible | T3, T4, F3–F6, H4; I4 (f) | partly | (c) "installed" programs need T6 (0.2); "as the user" needs T7 (0.2) — see §7 |
| 5 | Sync for Jupyter/ETL | X1, X2, X3 | yes | `cli` on the sync facade (above) |
| 6 | Serve as MCP | M1–M3 | yes | none |
| 7 | Everything is a file, one ladder | T1, T2, I3 | yes | none |
| 8 | Bash-like CLI | F1–F6 | yes | `awk` out (D22); fine if published |

### The preview/diff requirement — carried, with four holes

Carried: H2 (`plan=`, b) depends on K2/K3 and feeds H3 ac 2 (the
`pending` record "carries ... the H2 plan for a mutating verb"), H4 ac 5
(a suspended `cli` line "carries the H2 plan of that stage"), H2 ac 6
(one renderer "the shell and the MCP text block reuse"). The
`if_versions` tie-back (H2 ac 3) is the right design and is the one thing
Claude Code's diff lacks. Good work.

Holes:

1. **The refused-but-liftable case has no preview** (H2 ac 4 vs H3 ac 3,
   quoted in §1). *Fix:* add to H3 ac 3: "the ledger row carries no plan
   at suspension; `fs.answer(ticket, allow=True, authority=approver)`
   computes the plan *as the approver* and returns it before writing the
   allowance, so the approver sees what they are approving." Or scope the
   promise to the policy-hook case.
2. **The preview is unbounded.** H2 ac 1 returns "the planned
   `Observation` rows"; ac 2 adds a unified diff per row; ac 5 counts read
   statements only. A `delete(cascade=True)` on a 10,000-child directory
   returns 10,000 planned rows. Nothing pages or budgets the plan. *Fix:*
   H2 ac 7: "a plan pages on the K4 key and renders under `to_str(budget=)`
   (F1 ac 3); the `vfs.plan` record carries `rows_planned` so a truncated
   preview says how much it hides."
3. **M3 does not name the plan.** M3 ac 1 maps `pending` to
   `input_required` with "the `pending` text and payload". The diff block
   of H2 ac 6 should be named as the text content of that result, or an
   MCP client shows a bare ticket. *Fix:* one clause in M3 ac 1.
4. **Host tools and MCP tools cannot preview, and the page should say
   so.** H4's interrupt for a host tool carries `payload` from the tool;
   there is no "world after" for code that runs on the host. The promise
   sentence ("a refused or risky action ... with a preview") reads as if
   every interrupt has one. *Fix:* in §5's "The preview" paragraph add:
   "A preview exists for vfs's own mutations. A host tool or a mounted
   server describes its own question; vfs cannot preview it."

### Theme 4's half-deferrals are honest but buried

- "(c) CLI tools ... installed in vfs": T1 ac 4 lets an agent write to
  `/opt/bin`, but nothing executes a stored program until T6 (gate 0.2).
  At 0.1.0 an "installed tool" is a file nobody can run. §10's table says
  "program (`.wasm`, T6 in 0.2)" in a cell; the theme summary in §3 row 4
  does not. *Fix:* one sentence in §10's goal: "At 0.1.0 the installable
  kinds are skills (read-only) and host tools; wasm programs are 0.2."
- "(b) MCP servers authenticating as the user": I4 (gate `f`) is a
  host-supplied credential resolver; the OAuth round trip is T7 (0.2).
  See §7 on the wording.

---

## 3. Is the gate assignment coherent?

**No. The beta freeze is nominal: 8 of 15 `f` stories change a public name,
signature, protocol or wire shape, and land in batch b1 *after* "Nothing
after b1 changes a public name" (§14).** Spec 166 decision 3: beta allows
"bugs only". Spec 166 decision 4 defines the frozen surface as "verbs and
their signatures, the `Result` shapes, the storage protocols, the row
schema, and the MCP surface".

| Story | Tag | What it changes | Should be |
|---|---|---|---|
| K7 | f | `traits()` gains the atomic unit; a new `features()` seam; `data["vfs.engine_error"]` — storage **protocol** and `Result` data | b (protocol + data keys); crash-injection ac 2 can stay f |
| K8 | f | new verb `versions()`, new `read(version=)` argument, `created_by` column with a **schema bump** | b — it is the most surface-changing story on the page |
| H4 | f | new public `Interrupt` type, exit code 75, pass-through registration of host interrupt types | b (names and exit codes are the shell's surface, F5 ac 3) |
| H5 | f | `grep(deadline=)` argument; `cancel(ticket)` verb | b for the signatures; the fan-out mechanics can be f |
| I4 | f | `add_mcp(credentials=CredentialResolver)` protocol | b (a protocol a host implements is frozen surface) |
| M3 | f | `pending` → `input_required` on the wire | b if "the MCP surface if it exists by then" is frozen (spec 166 d.4) |
| D7 | f | pool kwargs on `DatabaseStorage` | b for the constructor; the kill-connection pin can be f |
| F6 | f | six new program names; Rust seam version bump | b for the program table (D34 calls it "the 0.1.0 program table"); the Rust port is f |

The clean split: a `b` story is "the name/shape exists and is pinned"; an
`f` story is "the behaviour behind it is proven on every leg / documented".
K7, K8, H4, H5, I4, D7, F6 each split that way into a small `b` half and
an `f` half. Doing that keeps b1 honest.

The reverse case — `b` stories that change no surface and could move to
`f` or `a` to lighten the freeze batch:

| Story | Tag | Changes a name? | Could be |
|---|---|---|---|
| D4 10k count pins | b | no (tests only) | f |
| E4 hybrid pins on every engine | b | no | f |
| E2 slow-provider convergence | b | `max_batch_inputs` default only | f |
| X6 delete dead examples | b | no | a |
| R6 hygiene | b | no (R6 ac 4/5 are docs) | a |
| R7 context true-up | b | no | f (except ac 4, ADR ratification, which K1/H1 already carry) |
| I5 scale pins | a | no | fine |

Two further oddities: D5 is tagged "0.2 (or b if D3 ...)" — a conditional
gate is not a gate; resolve D3 first (it is "needed by D1", i.e. a1). T5
is "gate a (stretch; not a final gate)" and then appears in b1 "(if
ready)"; pick one.

---

## 4. Is §14 honest about capacity?

**It is honest about each estimate and silent about the sum.** The page
says sizes "are not commitments" and never adds them up, names no date,
and never cites the product plan's finding ("every plan exceeded solo
capacity 3–4x", `business/product-plan-2026-08.md` §6). The plan also
said "0.1.0 ... lands before the October talks"; today is 2026-10-28 and
a1 is "this week".

Summing the page's own sizes (S ≤ 1 d, M 2–4 d, L 1–2 w, XL > 2 w):

| Batch | Stories | Composition | Effort (page's own scale) |
|---|---|---|---|
| a1 | 3 | 3 S | ~3 days |
| a2 | 10 | 2 L, 3 M, 5 S | 3–6.5 weeks |
| a3 | 16 | 9 M, 7 S | 5–8.5 weeks — the widest batch |
| a4 | 4 | 1 XL, 1 L, 2 M | 4–6+ weeks; F3→F4 serial |
| a5 | 8 | 4 L, 3 M, 1 S | 5.5–10.5 weeks; T1→T2→T3→T4→M1→M2 serial |
| a6 | 5 | 2 L, 3 M | 3–6.5 weeks; H3→H4 serial |
| b1 | 13 | 1 L, 9 M (F6 counts twice), 3 S | 5–9.5 weeks — the second-heaviest batch, after the "freeze" |
| **Total** | **59** | | **~26–48 weeks** |

Measured throughput from the spec archive (status lines "landed
2026-MM"): **July 20, August 44, September 8, October 7.** The pace fell
about five-fold as specs became kernel-sized. At the September–October
rate, 59 stories is 7–8 months; at the page's own effort scale it is
6–11 months. Neither is "a beta held by year end".

The critical path line is also wrong in one link: "M1 → H3 → H4". H3
depends on H1, H2 and K5 (its own *Depends on*), not on M1. H3 — Clay's
first theme and the differentiator — can ride a3 or a4; the page parks
it in a6, last.

**Overloaded batches:** a3 (16 stories, every domain at once), a5 (four
L stories in series), b1 (13 stories after the freeze).

**Cut order to 0.2 / 0.1.x, first cut first** (each keeps a promise
sentence true or is already half-deferred):

1. **T5** out of b1 entirely (already "not a gate").
2. **F6's Rust port** → 0.1.x. Ship `sort uniq tr tee` as Python
   transforms inside F4; keep `xargs` (the one rows-to-verb form) in
   Python too. No name changes, so this is a free cut.
3. **H5** → 0.2 except `cancel(ticket)` (S). `grep(deadline=)` is spec
   051's stale draft wearing a new tag.
4. **I4** → 0.2 with T7. Ship spec 170 §3.1 as drafted (one host
   credential per server) and say so. "Acts as the user" is then one
   theme deferred cleanly instead of half-built.
5. **M3's `input_required` mapping** → 0.2; ship the fallback branch
   of M3 ac 1 (`pending` as a complete error result with the ticket).
   The LangGraph host (H3 ac 7) does not need the wire mapping.
6. **K7** → keep ac 1 (atomic unit, as a D4 pin) and ac 4 (the trait);
   move ac 2 (crash injection), ac 3 (`engine_error`), ac 5
   (`features()` derivation) to 0.1.x.
7. **D7** → 0.1.x; document kwargs pass-through to
   `create_async_engine` in D3's how-to.
8. **H4's MCP-elicitation leg (ac 3)** → 0.2; keep `unsupported` (spec
   170 §4 as drafted). Keep the host-tool `Interrupt` and the shell
   stage.
9. **T4's supervisor/respawn (ac 4)** → 0.1.x; in-process and plain
   stdio only at 0.1.0.
10. **E4 ac 2 (nDCG gate)** and **D4 for `grant`/`revoke`** → slow tier
    0.1.x.

With cuts 1–10 the b1 batch shrinks to R5, K8, F5, D6, E6, X3–X5 and
the total drops to roughly 18–32 weeks. Still long. The next lever is
the one the page does not take: ship **0.1.0 with the shell core only
(F3) and host tools (T3)**, and make T4 (MCP servers as views) the
headline of 0.2. That removes an L from the serial chain and the hardest
cross-process piece. The page should at least show that option in §15.

---

## 5. What a PM would expect — present or absent?

| Item | Present? | Where | Is the absence right? |
|---|---|---|---|
| Migration / upgrade story | partly | D2: directional mismatch, corruption kind, registry; full `ALTER` → 0.2; "commitment point is `0.1.0b1`" | Right. One gap: three alphas each bump the schema (specs 176/177/180, ADR 087 landing note); a host on a2 moving to a4 gets refuse-and-re-provision. Say so in the alpha changelog template (R3 ac 1). |
| Console script | yes | M2: `[project.scripts] vfs`, `serve`/`sh`/`reindex` | — |
| Threat model | weak | R6 ac 5: "a short `THREAT_MODEL.md` stating ADR 087's three trust tiers" — a sub-bullet of a hygiene story | **Wrong weighting.** The headline is "governed"; ADR 068 ships `read_write` for anonymous by default; `src/` has credential-leak pins only inside I4/T4. Make it its own `b` story: trust tiers, the out-of-band SQL writer, the system actor, the open default, prompt-injection via file bodies into tools, what is and is not logged. |
| Vulnerability disclosure (`SECURITY.md`) | absent | no file in repo | **Wrong.** One paragraph; GitHub surfaces it; every security-review buyer (ADR 058 pin 8) looks for it. Add to R6. |
| When-not-to-use | yes | R6 ac 5 (ADR 069 pin 6) | — |
| Docs bar | yes | X3–X5: tutorial, how-tos, reference, nav test, `--strict`, fence tests; `deploy-docs.yml` exists | Good. Add: the README's quickstart block is fence-tested (R3 touches it; nothing runs it). |
| Multi-tenant proof | partial | I5 (scale pins, `a`), E5 (leak test), I2 ac 3 (HTTP anon vs token), F3 ac 3 (two sessions see different `ls`) | **Add one end-to-end story**: two principals over a served vfs, one tree, different `ls`/`grep`/`glean`, hidden rows never leak through `glean` stats or `graph`. This is the demo the product plan needs ("I share a wiki page with a grant; my agent reads it through the same grant") and the proof of ADR 069 differentiator 3. |
| Audit read side | partial | K8 `versions(path)` with actor/subjects, paged | **Absent:** any actor- or time-keyed read ("what did agent X change since T"). Grant/posture changes are not versioned at all. The product plan's invoice is "every audited action"; ADR 058 names "C7 introspection" as the Catalog's prerequisite. Either add `since=`/`actor=` filters to K8 (M) or name the gap in §15 so the Catalog plan does not assume it. |
| Observability | absent | `grep -rn "import logging" src/vfs` → 0 files; §15 defers OpenTelemetry | **Partly wrong.** OTel can wait. But I2 ac 4 "logs one warning per open mount" and I6 ac 2 "logs one line per call" assume a logger that does not exist. Add an S-size `b` story: one named logger `vfs`, what is logged at which level, and the rule "never a body, never a credential" pinned by a test. The logger name is public surface. |
| Statement/metrics hook for hosts | absent | "the statement hook" in H2 ac 1 is test tooling | Right to defer; note it in §15. |
| Local-disk mount | deferred | §15 "0.2+" | Right (the wedge is the DB). But `mission.md` line 8 still promises "local disk" first; R6 ac 4 must cover it. |
| Change feed | deferred | §15 | Right. |
| Benchmark publication | absent | product plan Gate 1 lists "benchmark"; CLAUDE.md says wall-clock "belongs in a bench or a research memo" | Add an `f` story: one bench memo (agent-sized call latency, 10k batch on each engine) published with 0.1.0. Cheap and the README needs a number. |
| Copy audit at each gate | partial | R3 ac 2, R6 ac 4 | Add one line to R5: "every README/docs claim re-checked against ADR 058 pin 7 at b1". |
| Deprecation policy | yes | R5 ac 5 (`versioning.md`) | — |
| Platform matrix | yes | X5; publish.yml has linux/musl/macos/windows | — |
| MCP tool-description poisoning | partial | T3 ac 3, I3 ac 4 (trust line, `cat` never runs) | Add to T4: a server-supplied description renders as data; the trust line names the server. |
| Rate limits / quotas | absent | — | Right for a library at 0.1.0. |

One more: the roadmap's **Method** says the eight audits "live in the
session scratchpad". CLAUDE.md: "All project knowledge lives in this repo
— never outside it." Executed findings that bind stories are research by
the repo's own definition. Move them to `context/research/` before they
evaporate.

---

## 6. Readability for Clay

The frame is right: §0 says how to read it, §17 is the one-line version,
each story has *Why / Depends on / Acceptance*. The body does not follow
"short sentences, one idea per sentence, define every term". Most
paragraphs pack three to five ideas, and terms (`redrive`, `reprobe`,
keyset, `EX_TEMPFAIL`, RFC 8707, greenlet, convex fusion) are never
defined.

### The five densest passages

1. **§5 "The idea, said plainly"** — the paragraph is 180 words, cites
   LangGraph, seccomp user notification, fanotify and Plan 9's factotum
   in one breath, and the title promises the opposite. Rewrite below.
2. **§5 "The preview"** — "the database write path already works
   plan-then-execute: it stages every change against an in-memory plan
   and only applies the plan when it has no errors (`writes.py`,
   `_finish` → `_apply`)... That is the piece a plain diff approval lacks
   and Terraform's plan-then-apply has." Internal function names and two
   analogies in one sentence.
3. **§3 table, row 1** — "none of ADR 087's arguments exist (no cursor,
   no `range=`, no `if_version=`, no `replace=`, no request key, no
   `versions`). All three ADR 087 probes still reproduce: twenty
   concurrent appends keep one line; a body rotted by raw SQL reads as
   success; a replayed `move` is a bare `not_found`." Six missing
   arguments and three defects in one cell.
4. **I4 *Why*** — "The MCP spec forbids forwarding the client's token
   upstream and RFC 8707 audience binding would refuse it anyway; the
   standards answer (token exchange, enterprise-managed authorization)
   has one shipping identity provider." Three standards, none defined.
5. **X1 *Why*** — "Greenlet (SQLAlchemy's bridge) is the inverse
   direction and would mean a kernel rewrite; `anyio`'s portal is the
   same design plus a core dependency; unasync codegen needs a whole sync
   storage path. The facade constructs the `VirtualFileSystem` itself so
   first touch lands on its loop (the asyncpg loop-affinity case)." Four
   rejected designs and a driver quirk in two sentences.

Runners-up: H1 ac 4, H4 ac 4's parenthetical ("asyncio queues, Rust
kernel state and wasm instances are not serialisable"), K5 ac 6.

### Plain rewrite of passage 1

> **The idea, said plainly.** vfs never asks a person a question. vfs
> never waits for a person either. What vfs does is stop.
>
> Here is how it works. A call comes in. Before vfs changes anything, it
> checks whether this call needs a human. If it does, vfs stops. It does
> not change anything. It returns a normal `Result` that says "stopped,
> waiting for a human", with a ticket number. We call that result kind
> `pending`.
>
> The host program — your agent loop — sees the `pending` result. The host
> asks the human, however it likes. When the human answers, the host sends
> the *same call again*, with the ticket. vfs checks the call from the top
> again, as if it were new, then runs it once. Nothing was held open in
> memory while the human thought about it.
>
> So: vfs provides the stop, the description of what would happen, and a
> way to say yes. The host provides the asking. This is the same split
> LangGraph uses (`interrupt()` stops a node; `Command(resume=)` re-runs
> it). Operating systems do it too: Linux's seccomp and fanotify let a
> supervisor outside the kernel answer for a stopped call. The kernel
> never asks; it stops and waits for the answer to come back as a new
> call.
>
> One line: vfs stops and describes; the host asks; the answer is a
> re-send.

### Is it too long? Yes — 1,797 lines, 64 stories, 35 decisions.

What to move without losing actionability:

- **Keep as the page (≈ 400 lines):** §0, §1, §2 (generated from tags),
  §3, one table per domain with *story · gate · size · one-line
  "done when"*, §14, §15, §17.
- **Move per-story acceptance criteria into the spec each story names.**
  Every `b`/`f` story already cites a spec or says "new spec"; acceptance
  belongs there (that is the pipeline: research → decide → specify →
  code). The roadmap keeps one countable line per story.
- **Move the "State today" tables** into the 60-line `STATUS.md`
  replacement R7 ac 3 already asks for. They are the same data.
- **Move §16 (35 decisions)** into `context/open-questions.md`, one entry
  each with the lean, and keep a 35-row index here (ID · needed by).
- **Move the prior-art paragraphs** (seccomp, fanotify, factotum,
  Terraform, mcpfs) into H1's ADR, where they are evidence.
- **Delete the duplication:** R4 repeats D6 ("Same as D6's items 2–3");
  §1.3 repeats §15; the kernel pieces are listed in §3, §4's table and
  §2.

---

## 7. Positioning risks — does the copy over-claim?

| Phrase | Where | Risk | Fix |
|---|---|---|---|
| "a governed file system for AI agents" | §1.1 s.1 | §1.3 forbids "file system" unqualified; ADR 069 pin 6 "not a filesystem emulation"; the Arize critique is aimed at exactly this phrase | Use ADR 075: "Governed data access for AI agents" + "the interface of a file system" |
| "true file system" | R6 ac 4 | The phrase exists nowhere in the repo except the roadmap (`grep -rn "true file system"` outside `src2/`: only `roadmap.md`). The story asks to reconcile a headline that is not there. | Drop it, or name the real site (likely `vfs-app/` or `logos/` copy, which R6 moves out anyway) |
| "runs 87% of what agents actually type ... (ADR 081)" | §1.3 | ADR 081 has 74% (pipes), 44% (`&&`), no 87%. The 87% is in the 2026-10-15 research memo and spec 167 and is "87% of *segments*", not calls. F5 ac 1 then promises "in-scope run rate at least 85%" on a *synthesized* corpus — a third denominator. | Publish one number with its denominator; cite the memo, not the ADR |
| "governed ... one gate that judges the caller's rights on every row" | §1.1 s.1 | ADR 087 pin 5: in process the gate is a convention. ADR 075: vfs makes the claim "in part". | Add the tier clause (see §1) |
| "MCP servers that act as the user" / theme 4 "authenticating as the user" | I4 title, §6 goal | With a host-held resolver the server sees whatever credential the *host* chose. It is per-principal, not "as the user", until T7 (OAuth, 0.2). | Internal copy is honest ("a seam"); keep the phrase out of README/PyPI until T7 |
| "All three kinds interrupt the same way" + "one permission structure governs a file and a tool alike" | §10, §1.1 s.3 | Reads as "tools are governed/sandboxed". A host tool body runs on the host with the host's authority (T3 ac 3); its interrupt is one the tool *chooses* to raise (H4 ac 1). A tool that never raises is never stopped. | Say: "the call is gated and can be suspended; the tool body runs with the authority its trust line names" |
| H4 ac 1: a registered host interrupt type "propagates unwrapped, never classified" | §5 | Contradicts README: "A raw exception always means a bug, never a bad input." A LangGraph `GraphInterrupt` escaping `cli` is a designed raw exception. | Either classify it and let the host re-raise from `data`, or amend the README rule to name the one registered exception |
| "Every change is versioned and reversible" | §1.1 s.3 | See §1. ADR 069 consequence forbids this wording until a write path mints a row per mutation. | "Every body change is versioned; every delete is reversible" |
| "SQLite, Postgres, SQL Server and Oracle" | §1.1 s.1 | MariaDB is served and in CI; a reader who runs MariaDB does not know if it is supported. D3 leans "second tier". | Name the tier in D1's matrix and say "and MariaDB (second tier)" |
| "Not a POSIX file system ... no inodes" | §1.3 | Fine — but K9 ac 3 exposes `entry_id` on `stat`/`ls`. A reader will call that an inode. | One sentence: "`entry_id` is an identity you can read, never an address you can use" (ADR 087 pin 4) |

Nothing in the page says "interruptible = secure" outright; §5 is careful.
The risk is in §10's table and the promise sentence, where "governs ...
a tool alike" and "interrupt the same way" sit next to "governed" and
will be read as sandboxing by the buyer ADR 058 pin 8 chose.

---

## One-line version

The page is the right shape and the right rigor; fix the five structural
problems — promise 3's "every change", the eight surface-changing `f`
stories, the five-story drift between §2 and the headings, the unsummed
26–48 weeks against a 7-a-month landing rate, and the refused-action
preview that H2 ac 4 forbids — then cut it to a 400-line page with the
acceptance criteria living in the specs.
