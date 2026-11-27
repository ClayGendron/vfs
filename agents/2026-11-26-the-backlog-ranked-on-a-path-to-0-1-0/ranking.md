# The backlog under `agents/` ranked on a path to 0.1.0: land what is built, repair Postgres and grep, settle the names, serve over MCP, then approvals and tools

Written on 2026-11-26 against `dev` at `1a5c247f`. It is a ranking and an argument for an order, not a spec and not a decision: nothing in it is ruled, nothing was built, and no file outside this work directory was changed. It rests on a skim of every work directory under `agents/`, and "Not checked" says what a skim does not establish. The ranked table of every item is [ranked-list.md](ranked-list.md); the data behind it is `records.json` and `plan.json`.

## The outcome wanted

One ordered list of everything outstanding, with a reason beside each item, so that the path to 0.1.0 can be argued over item by item and ruled on. The lens given for the ranking: an extremely compelling product, with a great argument for agent builders and for enterprises, biased toward getting more done where each piece adds value. [The roadmap](../../context/standards/roadmap.md) is the baseline: its gates are kept where they hold and challenged where they do not, and each challenge is marked.

## Terms

- **Item.** One work directory under `agents/`, or one gap.
- **Gap.** Work the roadmap requires for 0.1.0 that has no spec in a work directory on `dev`. Eleven are listed so they can be ranked with everything else.
- **Tier.** `must`: 0.1.0 is not credible or not safe without it, or it changes a public name and so precedes the freeze. `should`: clear value, and it fits. `could`: cheap and useful. `later`: after 0.1.0. `fold`: the behaviour is kept and the separate spec is closed. `done` and `ref`: built, or reference material.
- **Wave.** One of six ordered groups, each ending in a claim that can be made to a buyer once the wave has landed.
- **Move.** Where the ranking departs from the roadmap: sooner, later, folded, or not on the roadmap at all.
- **Size.** Effort on the roadmap's scale: S a day or less, M two to four days, L one to two weeks, XL more than two weeks. Sums use 1, 3, 7.5 and 15 agent-days.

## How it was made

The 146 work directories were sorted into eleven batches by theme and each was skimmed: the first 40 to 60 lines of the spec, its decision headings, its problem, scope, cost and choices sections, and its closing line. Each skim wrote one record with the same 25 fields: the outcome in plain words, the technical change, the roadmap story and gate, the state, the review state, what it depends on and unblocks, a size, a risk, the choices it leaves, and a value from 1 to 5 against the lens. Whether an item is built was read from its status line and confirmed by a search of `src/` or `tests/` for the main public name it adds, and from its row in [the backlog's state page](../2026-11-25-the-backlog-converted/state-on-dev.md) where it has one.

The tier, the wave, the order inside a wave and the reason were then decided once, over all the records together, with the roadmap's sections 1 to 3 and 14 to 16 and [the backlog's unit map](../2026-11-25-the-backlog-converted/units.md) read in full. Three facts the ranking leans on were checked directly: the unmerged branches form one linear stack (seven branches are each an ancestor of the eighth, `origin/the-kernel-writes-records-behind-and-sweeps-them`); that stack is 56 commits and 85 files under `src`, `tests` and `crates` ahead of `dev`; and the deletes specs exist on `origin/a-deleted-row-gives-up-its-path`.

## What was found

### 1. The constraint is review and merge, not design or build

122 specs wait to be built. 111 of them have never been reviewed, and 11 are reviewed fit to build. Meanwhile finished work is not on `dev`:

- [A row carries a vid](../2026-11-22-a-row-carries-a-vid-and-a-change-can-require-it/) and [the kernel keeps records of its own](../2026-11-22-the-kernel-keeps-records-of-its-own/) are built in eight landings, each with a review that says it lands, on a stack of eight branches from `origin/every-row-carries-a-vid` to `origin/the-kernel-writes-records-behind-and-sweeps-them`.
- More than twenty other items name one of the two as something they need first, among them the integrity read, the answer store, `serve`, the Python guest, the history verb and seven of the nine jobs and sessions specs.
- The stack removes `if_version` and `if_versions`, which reached `dev` on 2026-11-20. Each day it waits, more specs are written against names about to change.
- The deletes design, four specs dated 2026-11-24, is reviewed fit to build on a branch of its own. The backlog's unit map still calls it "not yet written", and five items wait on it.

A pull request is merged by a person, always. So the pace of 0.1.0 is set by how fast work is reviewed and merged, and the order below is built around that.

### 2. Some items the roadmap does not rank are production defects

The roadmap was last trued on 2026-11-22, and most of these specs were written after it. Several describe measured faults:

- About 1 in 70 single-file writes is refused when 32 sessions write at once on Postgres ([concurrent writes on Postgres outlive their retries](../2026-11-21-concurrent-writes-on-postgres-outlive-their-retries/)).
- Every subtree read on Postgres scans the whole table ([Postgres reads a subtree by its range](../2026-11-21-postgres-reads-a-subtree-by-its-range/)).
- Grep silently drops matches: `\<kmalloc` finds 6 files where ripgrep finds 421, and `[[:alpha:]]_count` finds none of 751 ([grep reads a pattern as its matcher does](../2026-11-21-grep-reads-a-pattern-as-its-matcher-does/)).
- A host whose Postgres driver is psycopg 3 cannot write at all ([the bulk insert path follows the driver](../2026-11-25-the-bulk-insert-path-follows-the-driver-on-the-connection/)).
- A shell line given a 0.3 second deadline was measured ending at 4.06 seconds, and a line can report success after an interpreter limit has run out ([shell runtime termination](../2026-11-22-shell-runtime-termination/)).
- A mutation takes the topology lock as its first statement, against the rule that a lock other callers need is held for the length of a commit ([the topology lock is held for a commit](../2026-11-21-the-topology-lock-is-held-for-a-commit/)).

These are wave 1. Each protects a claim vfs already makes.

### 3. The specs are not the whole road, and the roadmap is not the whole backlog

Eleven pieces 0.1.0 needs have no spec in a work directory on `dev`; "Work with no spec" lists them. In the other direction, 25 items ranked must or should are on no roadmap story. The two documents have drifted apart, and a ruling on this ranking is also the occasion to true the roadmap.

### 4. Serving can come before tools

The roadmap's critical path of 2026-11-22 is tools, then mounted MCP servers, then the MCP front, then the durable run. The specs show the front needs nine items, about eight agent-weeks, and none waits on tools: two renderer units, the verb budget, the wire adapter, the door token, the token edge, `serve`, the `cli` tool and the `vfs serve` command. Over stdio a host can supply a named authority itself, so even the token edge is needed only for HTTP.

## The argument 0.1.0 has to win

Each row is a sentence worth being able to say. The agent-builder argument is mostly waves 3 and 5, and the enterprise argument is mostly waves 1, 2 and 4.

| To | The claim | True |
|---|---|---|
| An agent builder | The agent already knows the interface: `ls`, `cat`, `grep`, pipes, loops, functions. The shell passes 3,218 of 3,339 recorded bash cases. | today |
| An agent builder | Grep across a 94,000-file tree ran 28 patterns in 3.1 seconds on local SQLite, where ripgrep took 84. | today; complete as well as fast after wave 1 |
| An agent builder | Any MCP client connects with one line; every verb is a tool and one `cli` tool takes a bash line. | wave 3 |
| An agent builder | The agent cannot overwrite a file it has not read, and a whole turn can be undone. | wave 4 |
| An agent builder | A Python function registered once is a file with a manual; a thousand tools, none in the context window. | wave 5 |
| An agent builder | pandas runs in a sandbox whose only disk is vfs and whose every call is judged as the caller. | wave 5 |
| An enterprise | Every read, search and write is judged against row-level rights, on the Postgres already in use. | today in process; with a verified identity on the wire after wave 3 |
| An enterprise | It holds at production concurrency: no spurious refusal, no table scan per call, no lock held past a commit. | wave 1 |
| An enterprise | A retried call applies once, and a file changed behind vfs is refused, never served as good. | wave 2 |
| An enterprise | A risky action stops for a person, and every call is a row: who, what, how many, how long. | wave 4 |
| An enterprise | Every version of a file can be listed and read back, with who wrote it. | wave 6 |
| An enterprise | A threat model, a disclosure policy, a versioning promise and an upgrade path exist. | wave 6 |

## The six waves

| Wave | Name | Items | Must | Agent-days in series | The claim it makes true |
|---|---|---|---|---|---|
| 1 | Truth in the core | 14 | 11 | 41 | Nothing vfs returns is silently wrong, and it holds up on Postgres with many writers at once. |
| 2 | Complete the surface | 25 | 12 | 113.5 | A retried call is safe, a damaged file never reads as success, a large file reads in slices, and the names do not change afterwards. |
| 3 | Serve it | 9 | 9 | 38.5 | Any MCP client connects to the database with one line, and every call is judged as the caller who made it. |
| 4 | Human in the loop | 10 | 5 | 73.5 | An agent cannot overwrite what it has not read, cannot run a risky step without approval, and everything it did is in a table the operator owns. |
| 5 | Tools as files | 10 | 4 | 56 | One permission structure governs a file and a tool alike, and the tool catalogue stays out of the context window. |
| 6 | Proof, docs and release | 43 | 4 | 164.5 | The evidence exists: the pins, the benchmark, the threat model and a beta that held for two weeks. |

The waves are an order of first starts, not a strict sequence. Wave 1 comes first because everything else stands on the merged stack. Wave 2 is the long kernel wave and most of its items are independent. Waves 3, 4 and 5 are three lanes: the front needs only the two renderer units, the policy and job specs need only wave 1, and tools need the executable bit and the standing program table from wave 2. Most of wave 6 can start beside any of them; it is last because the freeze paperwork and the proof from the published wheel can only close at the end.

Inside wave 5, mounted MCP servers are built last and are the first cut. Inside wave 4, the first three landings of the policy spec and the first three of the job spec are the smallest set that lets a host stop a risky call and ask a person; sessions and shell lines are not needed for that.

## Where the ranking departs from the roadmap

Where the roadmap gates an item before the freeze because it renames or removes a public name, that gate is kept every time. The departures are four.

- **Order.** Serving over MCP moves ahead of tools (finding 4).
- **Not on the roadmap.** 25 items the roadmap does not place are ranked must or should. Eight are must: the Postgres retries, the subtree range, the topology lock, the grep pattern reading, the paged served grep, shell runtime termination, the shell's file reads and the executable bit.
- **Sooner.** Three items the roadmap gates late or after 0.1.0 are pulled in: the history verb is must, because every body change is promised versioned and nothing reads a version back; the trash retention pass, because it holds a mount-wide lock for a corpus-sized transaction; and a small binary write that renders before it returns (choice 10).
- **Later.** Six items move out or lose their hold on the freeze: the JavaScript guest, attested provenance, the derived verbs for a thin backend and crash injection move past 0.1.0; the conformance battery's split touches no public name and follows the freeze; and the shell acting as bash where it refused stays in the plan but, being additive, does not hold the freeze.

Three specs are folded: the catalogue posture into the host-tool and `serve` specs, as it proposes itself; the engine's byte slice into the ranged read; and the twenty-second SQLite refusal, whose built sibling settled all but one choice.

Three places where the roadmap's wording is out of date and needs a ruling rather than a ranking: three newer specs decide that no row carries `entry_id`, against story K9; the catalogue seam is `holds_all`, where story I3a says `rungs_at`; and the reviewed multi-mount spec bounds a mount with `timeout=`, where story H6 gives a call `deadline=`.

## Work with no spec

| Gap | Roadmap story | Tier, wave | Size | Why it matters |
|---|---|---|---|---|
| The four deletes specs, on a branch and not on `dev` | F4, D55 to D57 | must, 2 | L | Five items wait on them, and they are fit to build. |
| The action log | H0 | must, 4 | L | The audit answer for an enterprise; the run record waits on it. |
| The `vfs serve` command | M2 | must, 3 | M | The five-minute demonstration. |
| Schema lifecycle | D2 | must, 6 | M | After 0.1.0 an upgrade can no longer answer "re-provision". |
| Tutorials, how-tos and reference pages | X3 to X5, D1, D7 | must, 6 | L | A product nobody can learn is not compelling. |
| Release proof and trust documents | R2 to R5, R8, R9 | must, 6 | L | No green publish dry run; `SECURITY.md`, `THREAT_MODEL.md` and `versioning.md` do not exist. |
| Interrupts, jobs and sessions over MCP | M3, D51 | should, 4 | M | Agents over MCP are the first audience and would miss both headline features. |
| Ranked search over the tool catalogue | none | should, 5 | M | The main recommendation of the code-mode study, carried by no spec. |
| Search defaults and pins | E1 to E5 | should, 6 | L | A slow embedding provider never converges today. |
| A 10,000-entry count pin for every verb | D4 | should, 6 | M | The batch contract is pinned for one verb. |
| Nine mount defects from the naming review | none | could, 6 | S | Recorded in a task file that no longer exists. |

## Choices for the owner

Each choice changes the order or the size of the plan. The option the ranking takes until it is ruled on is named first.

1. **Which capability ships first after the kernel is settled.** Taken: serve over MCP first, human in the loop beside it, tools third. The others: the roadmap's order, or human in the loop first.
2. **Whether the built vid and kernel-records stack lands before anything else.** Taken: it is reviewed and merged first, in stack order. The others: hold it until the sessions design is reviewed, or read the stack in full first because the vid design is in doubt.
3. **Whether 0.1.0 waits for other MCP servers mounted as directories.** Taken: in 0.1.0 as ruled on 2026-11-15, built last, and the first thing cut if the freeze is waiting on it. The others: the freeze waits for it, or it moves to 0.2 now.
4. **Whether the JavaScript guest is in 0.1.0.** Taken: after 0.1.0, with the one-afternoon spike run now and the extra's name reserved. This reverses the ruling of 2026-10-28. The others: the spike decides, or both guests before the freeze as ruled.
5. **How much of sessions belongs in 0.1.0.** Taken: all five specs, including turns, fork and file rewind, about four agent-weeks beyond the freeze-critical pair. The others: stop at turns, or only stored sessions and read memory.
6. **What the action log is, given that it has no spec.** Taken: a spec is written now, with every call a row, on by default, 30 days kept and a documented table, as roadmap decisions D52 and D53 lean. The others: mutations and tool calls only, or the log moves to 0.2.
7. **Whether the tool design the drafted specs converged on is accepted.** Taken: roadmap decisions D63 to D65 are ruled as all nine tool specs have them: `run` stays, one `/.vfs/bin`, no shipped `ask_user`. The others: ship an `ask_user` tool, or walk through the host-tool API first.
8. **Whether `entry_id` is public.** Taken: no row carries it and a vid is the public identity, as the three newer specs decide. The other: `stat` carries it, as the roadmap has it.
9. **How a caller bounds a slow call.** Taken: a timeout on each mount, as the reviewed spec has it. The others: a deadline on each call, or both.
10. **Whether a small binary write is readable at once.** Taken: pulled into 0.1.0, late in wave 6. The other: it stays in 0.2 and the gap is documented.

## Size

| Tier | Items | Agent-days left | Agent-weeks |
|---|---|---|---|
| must | 45 | 231.5 | about 46 |
| should | 49 | 226.5 | about 45 |
| could | 17 | 29 | about 6 |
| after 0.1.0 | 21 | 140.5 | about 28 |

The must tier alone is about 46 agent-weeks in series, and about 92 with the should tier. The roadmap's own estimate of what remained on 2026-11-22 was two thirds of 34 to 62 weeks, so 23 to 41: the backlog has grown past the plan, mostly by the 25 unplaced items and the eleven gaps. Run as three lanes after wave 2, with wave 6 beside them, agent effort stops being the limit and review and merge become it, which is finding 1 again.

## Not checked

- Every size, state and dependency is from a skim. No spec over about 20 KB was read whole, and the nine jobs and sessions specs, 90 to 150 KB each, were read at their tops, headings, cost sections and choices only.
- "Built" means the main public name is in `src/` or `tests/` on this checkout, or the status line says so and a search agrees. No test was run and no behaviour was exercised.
- The measured defects of finding 2 are quoted from the specs and their studies. None was run again.
- The four deletes specs on their branch and the seven specs still under `context/specifications/active/` were not read. Their sizes here are guesses.
- The nine shell contracts written from the review of 2026-11-22 are recorded as fit to build from that review's verdict; they were amended after it.
- The count of items waiting on the unmerged stack is a search of each record's dependencies for the stack's names, not a reading of each spec.
- Nothing about Postgres was run. Where a spec says a claim about Postgres was not checked, that still holds.

## The interactive form

The same ranking is published as a private page at https://claude.ai/artifact/NupGpEfz3aL1UDSGxBXkmS, where each item takes a vote (agree, sooner, later, cut) and a note, and each of the ten choices takes an answer. What is marked there is the input to the next revision of `records.json` and `plan.json`; `tools/render.py` then writes `ranked-list.md` again.

## One line

Merge what is built, repair what is wrong on Postgres and in grep, settle the kernel's names, serve it over MCP, then add approvals and tools on top, and write the documents an enterprise asks for; 45 items are must, about 46 agent-weeks in series, and the pace is set by review and merge.
