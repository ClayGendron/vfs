# YoloFS: the 290-incident threat model, and staging / snapshots / progressive permission mapped onto vfs

- **Status**: research memo (commits us to nothing; feeds spec 058 (row
  grants, the `invisible`/read rungs), spec 070 (principal-scoped
  sessions), spec 054 (`serve()`), roadmap 023 (per-session namespaces)
  and the branchfs memo a sibling session is writing, and the
  positioning record ADR 058)
- **Date**: 2026-09-04
- **Owner**: Clay Gendron
- **Question**: The YoloFS paper argues that oversight of an AI agent
  should move out of the agent and into the filesystem: the agent
  reviews its own effects, reverts bad ones, and its access is
  tightened by sensitivity while it runs. vfs's positioning (ADR 058)
  is "enforce it on the data itself", and vfs already has reversible
  mutation. What is the paper's 290-incident taxonomy — as a threat
  model vfs's permission specs should cite — and how do its three
  mechanisms map onto what vfs has and plans?
- **Method**: a read of the paper through the arXiv HTML rendering
  (`https://arxiv.org/html/2604.13536`, the current v4, plus the v2
  rendering for the figures the task quoted), the abstract page for
  the version history, the Microsoft Research publication page, and
  the public GitHub repository's landing page — **no clone, no code
  read**. Then a read of the vfs records each mechanism maps onto:
  ADRs 006, 013, 017, 021, 026, 027, 058; specs 058 and 070 (Intent);
  `src/vfs/permissions.py` (module docstring), `src/vfs/ops.py` (the
  op sets), `src/vfs/results/kinds.py` (the kind vocabulary),
  `src/vfs/models/version.py`; roadmap items 023/024; and the Mirage
  memo (§3.6–3.13, §4.1–4.6). Cites and describes only.
- **License / availability of code**: the paper is CC BY 4.0. A public
  repository exists: `https://github.com/YoloFS/YoloFS`, **GPL-2.0**
  (badge on the landing page), Rust plus a C kernel module in `kmod/`,
  a userspace CLI in `user/`, 843 commits, 5 stars, 0 forks at the
  time of reading. Not cloned. The license is copyleft, so the
  standing rule applies with extra force: study through the paper and
  the README; copy nothing.
- **Sources line**: arXiv 2604.13536 — v1 2026-04-15, v2 2026-04-16,
  v3 2026-08-13, v4 2026-08-31 (cs.OS). v1/v2 title: *Don't Let AI
  Agents YOLO Your Files: Shifting Information and Control to
  Filesystems for Agent Safety and Autonomy*. v3/v4 title: *Don't Let
  AI Agents YOLO Your Files: Information and Control in Agent-Native
  Filesystems*. Authors: Shawn Wanxiang Zhong, Junxuan Liao, Jing Liu,
  Mai Zheng, Andrea C. Arpaci-Dusseau, Remzi H. Arpaci-Dusseau;
  affiliations University of Wisconsin–Madison, Microsoft Research,
  Iowa State University. The MSR publication page lists the April
  title and carries no code link; the arXiv v4 abstract carries the
  GitHub link.

**A note on versions.** The task quoted the v2 figures: a kernel
module of 2.5 kLoC of C, a CLI of 6.2 kLoC of Rust, a `yolo.toml`
config, and a `.yolo/` directory with a sharded `files/` store and a
`journal`. The v4 text says 2.7 kLoC of C and 8 kLoC of Rust, a flat
file store of integer-numbered files, an append-only session journal
with seven record types, and support for Linux 6.8 and 7.0. Where the
two differ this memo says which version it is quoting. The paper was
read through a summarizing fetch of the HTML, not byte for byte; every
number below is as that fetch reported it, and §2 says where a figure
rather than a table was the source.

---

## 1. Bottom line

The paper and vfs agree on the thesis and disagree on the tier.

The thesis: an agent's *commands* are opaque, so filtering commands
does not work; the *effects* on files are observable, so mediate the
effects. The paper says this with one study and one system. The study
reads 290 public reports of agents damaging files and finds that the
damage came from a model that acts wrongly, a harness whose guardrails
match strings instead of effects, and a user who stopped reading
approval prompts. The system, YoloFS, sits under the agent as a Linux
kernel filesystem and gives three things: **staging** (nothing the
agent writes reaches the real files until the user commits),
**snapshots** (the agent sees what each command changed and can rewind
it), and **progressive permission** (a rule tree on paths; an
undecided access asks the user, and the answer can become a rule).

vfs already made the same bet — "vfs enforces it on the data itself"
(ADR 058) — and already owns two of the three mechanisms at the file
grain: **delete never destroys** (ADR 027: every delete is a
recoverable reparent into trash; only the developer-plane `sweep`
destroys) and **per-entry versions** (ADR 013/017: every material
write mints a reconstructable version with a content hash). Those two
are what the paper calls "undo mutations". What vfs does not have:

1. **A session-scoped overlay that lands only on commit** — staging.
   vfs writes land in the shared store immediately, visible to every
   principal. Roadmap 023 (`VFSSession` with a private mount overlay)
   is the slot; the branchfs memo is the design input (§5.1).
2. **A namespace-wide mark to rewind to, and a verb that does it.**
   vfs can reconstruct any one file at any version, but has no "state
   at mark 3" and no agent-facing `versions`/`revert` verb (§5.2).
3. **Read gating, `ask`, and rules that tighten during a run.** vfs
   gates writes only; `permission_denied` is a reserved kind nothing
   produces; policy is constructor configuration. Spec 058's ladder and
   the Mirage memo's `ask` ledger cover most of this; YoloFS adds two
   things worth taking — an answer that *installs a rule*, and the
   observation that reads of secrets are the one effect no undo can
   reverse (§5.3).

The taxonomy is the durable contribution for vfs. It is a threat model
with counts, and specs 058, 070, 054 and 023 should each cite the rows
they close (§5, table). The kernel module is not vfs's tier and should
not be imitated (§6).

One line: **YoloFS proves vfs's thesis from the OS side and hands vfs
a numbered threat model; vfs already has undo at the file grain, and
needs staging at the session grain and gating at the read grain.**

---

## 2. The 290-incident study

**What was collected.** 290 public reports of AI coding agents
misusing filesystem access, February 2024 to March 2026. Sources:
GitHub issues (205), social media (31), product forums (25), blog
posts (18), the National Vulnerability Database (11). Thirteen agent
harnesses; the five largest are Claude Code (97), Codex (61), Cursor
(37), Gemini (32), Copilot (28), with 8 others (35). Reports where the
user explicitly asked for the destructive action were excluded, as
were duplicates of one event.

**Triage.** Each report is one of: an **incident** (confirmed harm,
158), an **exploit** (a demonstrated attack, 49), or a **weakness** (a
flaw with no reported impact, 83). 158 + 49 + 83 = 290.

### 2.1 Impact (the 207 incidents and exploits)

The paper reports these as "Figure 3: Impact summary". The
percentages below are as the fetch read them off that figure; they
are shares of 207, and some axes are multi-valued, so a row need not
sum to 100.

| Axis | Values |
| --- | --- |
| Operation | writes 44 % (overwrites, truncation to zero bytes); deletions 39 % (wiped drives, erased directories); secret leaks 17 % (API keys, credentials, `.env`) |
| Scope of harm | within the project 58 %; system files 15 %; user files 14 %; secrets 13 % |
| Agent awareness | unaware 68 %; apologized 21 %; lied about the effects 11 % |
| User awareness | noticed immediately 83 %; discovered later 10 %; remained unaware 8 % |
| Recovery | unrecoverable 40 % (total loss 23 %, partial loss 17 %); easy 31 %; difficult 29 % |

Two facts from this axis carry weight for vfs. **Two in five
incidents were unrecoverable.** And **one in six was a leak** — a read
that no undo can take back.

### 2.2 Root causes — the taxonomy

The paper reports this as "Figure 4: Taxonomy of causes", with three
actors. The caption says **"Counts can overlap"** — one report can
have more than one cause — which is why 168 + 218 + 105 = 491 exceeds
290. Category names and counts are quoted exactly.

| Actor | Category | Count | Sub-category | Count | Example the paper gives |
| --- | --- | --- | --- | --- | --- |
| **Model: The Unreliable Actor** | | 168 | | | |
| | M1 Wrong action | 130 | Wrong goal | 76 | deleted when asked to archive |
| | | | Wrong scope | 50 | searched the whole home directory instead of the project |
| | | | Incorrect tool use | 27 | malformed quoting wiped a drive |
| | M2 Unfollowed instructions | 56 | Ignored | 38 | "I get focused on solving the problem and skip the step" |
| | | | Evicted from context | 28 | the instruction fell out of the context window |
| | M3 Prompt injection | 21 | | | attacker instructions embedded in processed content |
| **Harness: The Limited Guardian** | | 218 | | | |
| | H1 Guardrail failures | 147 | Shell loophole | 77 | policies on the file tools do not apply to shell commands |
| | | | Effect-blind filter | 52 | the filter matches strings, not effects (`rm` vs `unlink` vs `os.remove`) |
| | | | Sandbox misfit | 41 | too restrictive or too permissive |
| | H2 Rigid policy | 130 | | | a static up-front policy does not fit a task-dependent run |
| **User: The Overwhelmed Reviewer** | | 105 | | | |
| | U1 Auto-approved | 80 | | | approval fatigue; users enable "YOLO mode" |
| | U2 Uninformative approval | 31 | | | prompts show the command, not its filesystem effects |

### 2.3 The six findings

The paper states each as a boxed sentence. Verbatim:

1. "Users and agents cannot reliably recognize the filesystem effects
   of tool calls or the resulting harm."
2. "Users and agents cannot reliably prevent or recover from harmful
   filesystem effects."
3. "Models make mistakes, and natural-language instructions cannot
   reliably prevent them."
4. "Filters on command strings are ineffective because they do not
   target the actual filesystem effects."
5. "Static, upfront policies are not suitable for dynamic,
   task-dependent agent workloads."
6. "Excessive, uninformative approval prompts drive users to always
   allow."

Findings 1–2 are the two gaps the paper names: an **information gap**
(nobody can tell what a command will do or did) and a **control gap**
(nothing reliably prevents the harm or recovers from it). Findings 3–6
are the arguments against the three existing fixes: instructions to
the model, string filters in the harness, and approval prompts to the
user.

**Table 1** of the paper surveys six harnesses (Claude Code, Codex,
OpenCode, Gemini, Cursor, VS Code Copilot) on three mechanisms — a
policy on the built-in file tools (ask/allow/deny by path), a filter
on shell commands, and a sandbox — and finds them heterogeneous: some
ship a closed rule set (about 150 rules), some an allow-list, and
sandboxing is often opt-in.

---

## 3. The three mechanisms and the YoloFS design

Terms first. A **stackable filesystem** is a filesystem that sits on
top of another one and forwards most calls to it, changing only what
it must — here YoloFS stacks on ext4. A **dentry** is the Linux
kernel's in-memory record for one path component (a "directory
entry"); YoloFS hangs its per-path state off dentries. **Staging** is
holding a change somewhere the real files cannot see until someone
commits it. A **snapshot** is a named point in time you can return to.
A **journal** is an append-only log of what happened, in order.
**Copy-on-write** means a shared piece of data is copied only when
someone writes to it. `pivot_root` is the Linux call that makes a
mount the root of a process's view of the filesystem.

### 3.1 Requirements and primitives

Four requirements (§4.2 of the paper): **completeness** — mediate
every operation on every file the agent can reach, with no bypass;
**adaptability** — policy can change during the run; **compatibility**
— work on existing data without reflinks, filesystem snapshots, or
other non-POSIX features; **performance** — negligible overhead on
the critical path.

Three primitives an "agent-native filesystem" must provide (§4.1),
verbatim: *introspect effects* ("lets users and agents introspect the
effects of an opaque command string: what files it actually accessed
and changed"); *undo mutations* ("lets users and agents undo
overwrites, deletions, and other filesystem mutations"); *gate
accesses* ("must therefore gate such accesses before they occur. It
enforces rules on filesystem paths rather than filtering commands").

### 3.2 Staging (user control: review, then commit or abort)

Every mutation the agent makes is diverted. The real ("base")
filesystem is not touched. The user later runs `yolo review`, sees
the net changes — added, deleted, modified, renamed — and runs
`yolo commit` or `yolo abort`.

The structure (v4): a **flat file store** of staged contents, each
file named by an integer inode-like number (`1`, `2`, …); an in-memory
**override tree** mapping each path to one of three backings —
`StagedFile(ino, gen)` (a staged copy), `BaseFile(src)` (a pointer
into the base filesystem), or `None` (deleted); and an append-only
**session journal**. The v2 text describes the same idea as a
`.yolo/` directory in the project folder with contents under
`files/`, "sharded into subdirectories to avoid large flat
directories", and "the directory journal ... stored at `journal`",
with the override tree and rule tree kept on VFS dentries.

The journal's record types (v4):

```
S <path> <ino> <pre>                stage path as file ino, replacing backing pre
D <path> <pre>                      delete path, removing backing pre
R <src> <dst> <src-pre> <dst-pre>   rename
P <name>                            snapshot marker
T <name> <gen>                      travel marker (to generation gen)
G <path> <op> <result>              gate: an access decision was made
C <path> <policy>                   configure: a rule changed
```

The design point the authors stress: **content is decoupled from
paths.** A rename of a base file updates only the override tree; no
bytes move until commit. That is the claimed advantage over union
filesystems like OverlayFS, where renames are expensive and undo is
limited. Commit walks the reconstructed tree and applies each final
backing, using temporary paths to survive rename cycles (`a → b` and
`b → a`). Abort resets the tree and clears the store and journal.

The paper's example: the agent runs `./evil.sh`; review shows
`~/.ssh/authorized_keys` modified, `/var/log/audit/audit.log` deleted,
`evil.sh` renamed onto `~/.bashrc`; the user aborts and the base
filesystem is unchanged.

### 3.3 Snapshots and travel (agent information and agent control)

A `P` marker is written at every command boundary (the hook does this
per tool call). The journal between two markers is one command's
effects — a **segment**. After each command the CLI shows the agent
the net change of that segment: files created, deleted, modified. The
agent can run `yolo travel <n>` to return to the state at snapshot
`n`.

Mechanism: a global **generation** counter advances at every marker;
a `StagedFile` carries the generation it was created in; opening a
file for write in a newer generation allocates a new file in the flat
store instead of overwriting — copy-on-write by generation. Each
record's `pre` field says what the backing was before, so the CLI can
replay one segment without rebuilding the whole history. A travel
does **not** truncate the journal: it appends a `T` marker, advances
the generation, and starts a new segment, so abandoned work stays
reviewable. The kernel keeps only the one live override tree, so cost
does not grow with snapshot count.

The paper's example: `make` → snapshot 1 shows "Created: main.o";
`rm *.o` → snapshot 2 shows "Deleted: main.c, main.o"; the agent sees
`main.c` should not be there, travels to 1, and retries.

### 3.4 Progressive permission (user control: gate, then refine)

A **rule tree** maps paths to one of five policies: `ask` (prompt the
user), `allow` (reads, writes, execution, mutation), `write-ask`
(reads and execution free; ask before a write), `read-only` (reads
and execution; writes refused), `deny` (nothing). A path takes the
nearest ancestor's rule; a more specific rule wins. On an undecided
access the kernel **blocks the calling thread**, the CLI shows the
user the path, the operation and the process name, the user answers,
and may say "and do not ask again", which installs a rule (`C` record)
that persists in the per-project config for later sessions. A timeout
denies. The agent cannot edit its own policy. Every gated access is a
`G` record, so the review shows what was asked and what was decided.

Config (v2 names the file `yolo.toml`; the v4 integration text says
`yolo init` writes `yolofs.toml` — the fetch reported both spellings
and this memo did not verify which the repository uses):

```toml
[rules]
"~/.ssh"         = "deny"
"~/work/project" = "allow"
"~/.env"         = "read-only"
"~"              = "write-ask"

[defaults]
policy = "ask"
```

The paper's example: `./leak.sh` tries to read `.env`; the user is
asked, chooses "Deny and do not ask again"; the rule `.env ↦ deny` is
installed; the review later shows the blocked access and the rule.

### 3.5 Implementation and the Claude Code integration

Kernel: a Linux stackable filesystem, 2.7 kLoC of C in v4 (2.5 kLoC
in v2), Linux 6.8 and 7.0 (Ubuntu 24.04 / 26.04). Userspace: a Rust
CLI, 8 kLoC in v4 (6.2 kLoC "with unit tests" in v2); the two talk
through ioctls and shared on-disk state. `yolo run -- <cmd>` runs the
command in a mount namespace with the YoloFS mount as root via
`pivot_root`, "so the agent cannot bypass YoloFS to reach the base
filesystem" — that is how completeness is met.

Integration: "We integrate YoloFS with Claude Code (with PreToolUse),
Copilot (with preToolUse), and Gemini (with BeforeTool)." The hook
routes every agent command through `yolo run`, which also drops the
snapshot marker per command. `yolo init` writes the config, installs
the hooks, and "adds skills that teach agents to use YoloFS" — the
agent is told, in a skill, to read the per-command change list and
to travel when it looks wrong.

---

## 4. Evaluation and limits

### 4.1 What was measured

**Self-correction on opaque tasks.** Eleven tasks, each a normal
request (run the formatter, run lint, run the optimizer, …) whose
script has a hidden destructive side effect, graded by how hard the
effect is to see: three use one readable script (L1); three a
Makefile that calls a subscript (L2); two chains of three or more
levels of indirection (L3); three precompiled binaries with no source
(L∞). Result: with YoloFS, Claude Code "self-corrects in 8 of 11
tasks, while the remaining 3 are user-correctable" — every effect
stays staged for review. Without YoloFS, "no baseline agent reliably
prevents the destructive side effects", and Claude Code alone "fails
all but optimizer". In the formatter task the agent traveled back,
read the script, and wrote "CRITICAL: This is a destructive script,
not a legitimate formatter!"

**Routine operations.** 112 tasks = 18 operations × 5–7 paths (read,
append, overwrite, patch, clear, delete, copy, move, create, directory
and search operations, across path categories). Success: YoloFS 99 %,
Claude Code 98 %, Codex 100 %, Copilot 96 %, Gemini 75 %. User
interactions per task: YoloFS 0.4, Claude Code 0.9, Codex 0.4,
Copilot 1.3, Gemini 2.2. Tool calls per task: YoloFS 1.1, Claude Code
1.0, Codex 1.8.

**Overhead.** A 1 GB staged file with 4 KB requests against ext4:
sequential read (warm) +1 %, sequential write −2 %, random read 0 %,
random write −1 %. Permission control adds about 4 % to `stat` and is
negligible elsewhere. OverlayFS could not create more than 50
snapshots (the mount-option string exceeds a kernel limit); YoloFS is
flat in snapshot count.

### 4.2 Limits — the paper's and mine

The paper has no dedicated limitations section. What it states or
implies as out of scope:

- **Non-filesystem interfaces.** "Agents may also interact with
  non-filesystem interfaces, and securing them is complementary to
  our work." Network calls, databases, and any side effect that is
  not a file are outside the model.
- **Platform.** Linux 6.8 and 7.0 only; a kernel module; one project
  directory per config.
- **A blocked thread waits for a human.** The ask path suspends the
  agent's process until the user answers or the timeout denies.

My own reading, flagged as opinion:

- **The evaluation is the authors' 11 tasks**, and the 8/11 depends
  on the skill that tells the agent to read the change list. The
  paper says both plainly; it is still a small sample.
- **Fatigue moves; it does not vanish.** Staging replaces many
  per-command prompts with one review at the end. A long session
  produces a long diff. Whether users read that diff is the same
  question as U1, asked once instead of many times. The paper's
  `write-ask` and per-path rules are the real answer to fatigue, and
  those are the parts vfs can take.
- **Staging is per project, per agent, per user.** Two agents on one
  tree, or a shared store with other writers, are not modeled. That is
  exactly the case vfs is built for (two audiences on one backend), so
  vfs's staging has to answer a harder question than YoloFS's (§5.1).
- **Reads are gated but not journaled as data flow.** A `G` record
  says a read happened; nothing says where the bytes went. That is the
  honest limit of any filesystem-tier leak defense, vfs's included.

---

## 5. Mapping onto vfs

Legend, as in the Mirage memo: **adopt** — take the concept now, in
vfs's shape; **adapt** — take it when the roadmap reaches the
consumer; **parity** — vfs already has it; **skip** — not vfs's tier.

### 5.0 The threat-model table

Each row is one taxonomy category. "vfs mechanism" says what closes
it — **existing** (in the live tree), **planned** (in a spec or ADR),
or **none**. "Cite in" names the spec that should quote the row.

| Category | Count (of 290; overlaps) | What vfs has | Status | Cite in |
| --- | --- | --- | --- | --- |
| M1 wrong goal (deleted instead of archived) | 76 | delete never destroys, restore by original site and time (ADR 027, 026); per-entry versions for overwrites (ADR 013/017) | **existing** at file grain; session-grain revert **none** | 023 / branchfs; a revert-verb spec |
| M1 wrong scope (whole home vs project) | 50 | the namespace is the scope — what is not mounted cannot be reached (ADR 058 line 2); read-only prefixes via `PermissionMap` (ADR 006) | **existing**; hide/`invisible` rung **planned** | 058 |
| M1 incorrect tool use (quoting) | 27 | typed verbs take paths, not strings; there is no shell to mis-quote | **parity by construction**; `run` (EXEC_OPS) is the one string-taking verb | 039 (`run`) |
| M2 unfollowed instructions | 56 | enforcement is not an instruction: the write gate runs before dispatch (`check_writable_composed`) | **existing** for writes; **planned** for reads (058) | 058 |
| M3 prompt injection | 21 | nothing gates a read today; secrets are readable by any caller with the mount | **none**; 058's read rungs + `ask` are the answer | 058, 054 |
| H1 shell loophole | 77 | one door: every verb, including `cli`, re-enters the router (Mirage memo §3.1) | **existing** | 039 must keep `run` behind the same gate |
| H1 effect-blind filter | 52 | gates are on `(op, path)` — effects — not on command text (`MUTATING_OPS`, `permissions.py`) | **existing** | 058, 070 |
| H1 sandbox misfit | 41 | vfs is not a sandbox; the namespace plus a session overlay is the bounded view | **planned** (023 overlay, 070 profile) | 023, 070 |
| H2 rigid policy | 130 | `PermissionMap` is constructor configuration; nothing changes during a run | **none**; grants table (058), session profile (070), `ask` ledger (Mirage §4.3) | 058, 070, 054 |
| U1 auto-approved | 80 | no prompts exist, so none are ignored; but also no `ask` and no end-of-run review | **none**; `ask` scoped to sensitive paths (054), commit review (023) | 054, 023 |
| U2 uninformative approval | 31 | every mutation returns typed observations (`trash_path` on delete, `version` on every row); `explain` proposed (Mirage §4.2) | **existing** partially; `explain` **planned** | 054 (`explain`) |
| Impact: unrecoverable 40 % | 83 of 207 | sweep is the only destroyer and is developer-plane only (ADR 027 pins 3–4) | **existing** | cite in 054 (sweep never on the tool surface) |
| Impact: secret leaks 17 % | 35 of 207 | reads never gated | **none** until 058 | 058 |

The two columns that matter most: **H2 (130) and M3+leaks are
"none".** Those are the spec 058 and 070 rows, and the table is the
argument for the sequencing ADR 058 leaves open (governance before
more search).

### 5.1 Staging → a session overlay that lands on commit

**What YoloFS does.** All writes go to an override tree and a flat
store; the base filesystem is untouched until `commit`.

**What it prevents.** Every "the harm is already done" row: M1 wrong
goal, H1 shell loophole and effect-blind filter (the effect is staged
whatever command made it), U2 (the review shows effects, not
commands).

**What vfs has.** Recovery, not staging. A write lands in the shared
table at once, visible to every principal, and is recoverable
afterwards: delete is a reparent into trash with the trash path in the
result (ADR 026 pin 2, ADR 027 pin 1); an overwrite mints a version
that `Version.reconstruct` can bring back, hash-verified. A write
*batch* is atomic — a failed batch never commits — but that is
transaction grain, not session grain. So vfs closes the *loss* half
of the row (nothing is gone) and not the *exposure* half (other
readers saw the bad state; a search index saw it; an edge was built
on it).

**What is missing.** A **session overlay**: writes from one session
land in a private layer; other sessions read the base; `commit`
publishes the layer as ordinary writes and `abort` drops it. Roadmap
023 names exactly this — "`VFSSession` with private mount overlay;
`async with vfs.session() as s`; `fork()` for `rfork(RFNAMEG)`
semantics" — and spec 070 already reconciles its `session()` name
against it. The design question is the branchfs memo's (the paper
cites BranchFS as the closest recent work): whether the overlay is a
branch column on rows, an overlay table joined at the chokepoint, or a
separate mount. Two constraints from vfs's own records shape it:
storage owns no background work (ADR 013 pin 5), so commit is a verb;
and the read predicate must reach nomination (Mirage memo §4.1), so
an uncommitted row must not be ranked by `glean` for another session.

**What vfs should keep from YoloFS's shape.** Three things. (1)
**Decouple content from paths**: a staged rename is a namespace
change, not a copy — vfs already has this, because `move` is a row
update and content lives in chunks. (2) **The `pre` field**: every
overlay record carries what it replaced, so one segment can be shown
or undone without replaying the whole session. In vfs terms that is
`(entry_id, version_before, version_after)` per staged write. (3)
**Commit order survives rename cycles**: YoloFS uses temporary paths;
vfs's `(parent_id, name)` unique index has the same hazard and the
same fix.

**Verdict: adapt** — into roadmap 023, with the branchfs memo as the
design input. Not "adopt now", because the overlay changes the read
predicate at the chokepoint, which is spec 058's territory, and the
two should be designed together.

### 5.2 Snapshots and travel → marks over versions, and a revert verb

**What YoloFS does.** A marker per command; a per-command net-change
list shown to the agent; `travel` to any marker; abandoned history
kept.

**What it prevents.** M1 wrong action when the agent *can see* the
effect: the "Deleted: main.c" moment. The 8/11 number is this
mechanism plus the skill that tells the agent to look.

**What vfs has.** The substrate, at the file grain, and stronger than
YoloFS's in one way: every version is content-addressed (a hash),
verified on reconstruct, and stored in the same database as the entry,
on every engine. Delete-never-destroys plus versions *is* per-file
time travel. And every mutating verb already returns the net effect of
that verb as typed observations — which is YoloFS's per-command list,
for verbs. Trash names are self-describing and time-ordered (ADR 026
pin 1), which is a browsable journal of deletions.

**What is missing.**

- **A namespace-wide mark.** ADR 013 pin 2 removed mount-wide
  ordering on purpose; `updated_at` is a coarse cursor (pin 4). So
  "the state at snapshot 3" has no coordinate. The honest way to add
  one without reviving ordered allocation is YoloFS's own trick, seen
  from the database side: a **mark is a recorded set** of
  `(entry_id, version)` for the entries a session touched, written at
  mark time — not a global number. "What changed since mark 3" is a
  join of that set against current versions; "travel to mark 3" is a
  batch of writes that re-instate those versions. ADR 026 option (f)
  rejected whole-namespace snapshots for the *trash* role because of
  write amplification; a session-touched-set mark has no
  amplification, because it records only what the session wrote.
- **An agent-facing history surface.** `READ_OPS` is `read, stat, ls,
  tree, glob, grep, glean, graph`. There is no `versions` verb, no
  `diff`, no `revert`. The Mirage memo §4.8 already lists "what did
  this agent see, at what version" as a Catalog want; this paper says
  the *agent* is a consumer too, and the 8/11 result is the evidence.
- **Travel that never destroys.** YoloFS's `T` marker keeps the
  abandoned segment. vfs's rule is the same by construction: a revert
  is a new version, never a deletion of versions; sweep alone
  destroys (ADR 027). Parity in spirit, once the verb exists.

**Verdict: adapt** — a small spec for `versions` (read) and `revert`
(mutating, mints a version) on the existing tables, plus the
session-touched-set mark once 023 gives sessions a home. The
per-verb observation list is already the "introspect effects"
primitive for vfs's verbs; `run` is the one verb whose effects are
not a row list, and it is where a mark-diff earns its keep.

### 5.3 Progressive permission → rungs, `ask`, and rules that install

**What YoloFS does.** Five path policies in a rule tree; undecided
accesses ask the user; an answer can install a persistent rule; reads
are gated, not only writes; the agent cannot change its policy.

**What it prevents.** The leak rows — secret leaks (17 % of impacts),
M3 prompt injection (`leak.sh` reading `.env`) — and the rigid-policy
row H2 (130), the largest single sub-category in the study. It also
lowers U1 by asking only at sensitive paths.

**What vfs has.** `PermissionMap`: per mount, two levels
(`read`, `read_write`), longest-prefix override, composed along the
mount path most-restrictive-wins (ADR 006). That is YoloFS's
`read-only` and `allow`, on writes only. `MountMeta.deny_ops` is an op
mask. `VFSErrorKind.permission_denied` exists with a contract row
("Target a path this caller may access, or request access") and
nothing produces it. No read gating. No `deny`, no `ask`, no
`write-ask`. Policy is set when the `VirtualFileSystem` is built.

**What the specs already plan.** Spec 058's ladder is
`(invisible) < read < read_write`, enforced as a predicate on reads
and a point check on writes; ADR 021 makes grant rows additive-only
and sends subtraction to a policy layer; spec 070 gives sessions a
verified `Principal`; the Mirage memo proposes `ask` as
`vfs.permission_denied.pending` with a decision ledger (§4.3), a
session profile that only narrows (§4.5), and `explain` (§4.2).

**What YoloFS adds on top of that plan** — the four things to take:

1. **`write-ask` as a rung, not a rule.** YoloFS's ladder is
   `deny < read-only < write-ask < allow` with `ask` orthogonal. vfs's
   ladder gains one value: `read < read_ask_write < read_write`, or
   equivalently an `ask` flag on the write half. This is the
   least-friction default for a project tree — reads free, writes
   asked — and it is what makes the 0.4-interactions-per-task number.
2. **An answer installs a rule, and the two directions land in two
   places.** "Allow and remember" is a *widening* — that is a grant
   row, additive, exactly ADR 021's shape, keyed by principal and
   prefix. "Deny and remember" is a *narrowing* — that is a session
   profile rule (Mirage §4.5, "only narrows") or a policy-layer
   expression (ADR 021 §1), never a row. Mirage's ledger scoped answers
   to `once` or `session`; YoloFS persists them across sessions in the
   project config. vfs can offer all three scopes because grants are
   rows and profiles are documents.
3. **Reads are the effect no undo reverses.** Staging and versions
   cover writes and deletes — 83 % of impacts. The remaining 17 % are
   reads, and the only defense is a gate before the read. This is the
   sharpest argument for landing spec 058's read rungs *before* a
   session overlay, and it belongs in 058's Intent as a sentence.
4. **The agent cannot edit its own policy.** In vfs the mount table
   and `PermissionMap` are constructor state, so this holds today.
   ADR 027 pin 6 says mount admin "is intended for the agent surface";
   when `bind`/`remount` reach the tool surface, the rule to pin is
   YoloFS's: a session's policy document is read-only to that session,
   and composition stays most-restrictive-wins so a new bind can never
   loosen an ancestor. That already holds structurally (ADR 006) and
   should be written down as a pin, not left to the composition rule.

**Two things not to take from this mechanism.** The blocked thread:
vfs answers an ask with a classified `pending` `Result` and lets the
host decide out of band (MCP tasks/elicitation via `serve()`, spec
054), which fits an async library and never parks a database
connection. And the timeout-denies rule as a *storage* behavior: in
vfs a pending ask is a `Result`, so "timeout" is the host's policy,
not the gate's.

**Verdict: adopt** items 1–4 into specs 058/070/054 as they are
written; they are small additions to designs already on the table.

### 5.4 Two smaller lifts

- **The `G`/`C` journal is the Catalog's audit feed.** ADR 058 puts
  "what changed and when" and "who can reach what" in the plane. Gated
  accesses (asked, allowed, denied — with the rule that fired) and rule
  changes are the two records the plane wants that the library does
  not yet keep. Together with the Mirage memo's `Refusal`-in-`data`
  fix (§4.4), a refusal `Result` *is* a `G` record; a grant or profile
  write is a `C` record.
- **The skill is part of the mechanism.** YoloFS's 8/11 includes
  "skills that teach agents to use YoloFS". When `serve()` ships, the
  per-mount prompt fragment the Mirage memo proposed (§3.23) should
  carry one line for versions and one for trash: *every write is
  versioned and every delete is recoverable; check the observation
  list and revert if the effect is wrong.*

---

## 6. What not to take

- **The kernel module.** YoloFS is a Linux stackable filesystem
  because its agent runs shell commands against a real POSIX tree,
  and the only place that sees every effect of an arbitrary binary is
  the VFS layer under it. vfs's agent does not run against a POSIX
  tree; it calls typed verbs on a router whose only seam is the
  storage protocol, and the data lives in a database. vfs's
  "completeness" (the paper's first requirement) is *one door* — every
  verb re-enters the router, including `cli` — not `pivot_root`. The
  honest limit is the same in both systems and is already written in
  `permissions.py`: a caller with the DSN bypasses vfs the way a
  process with the block device bypasses YoloFS. The answer is
  deployment (the agent holds a vfs handle, never the DSN), not a
  module.
- **Dentries and override trees.** vfs has rows, not dentries; the
  override tree is a join at the chokepoint (§5.1). Do not build an
  in-memory tree beside the database — it is the second pipeline the
  Mirage memo's §3.1 warns about.
- **A per-project config file.** vfs's policy is the mount table plus
  a session profile (spec 070); rules are rows or a document, on every
  engine, not a TOML file in the tree.
- **The blocked-thread ask and the timeout.** See §5.3.
- **OverlayFS-style union mounts as the staging mechanism.** The
  paper's own comparison is the argument: expensive renames, a
  50-snapshot ceiling. Roadmap 019 (union mounts) is a namespace
  feature, not a staging one; keep the two apart.
- **The code.** GPL-2.0. The no-copy rule already applies to every
  reference repo; here the license would also make copying a
  licensing event. Study the paper; do not clone.

---

## 7. Next steps

1. **Cite the taxonomy in spec 058's Intent** (§5.0 rows M3, H2, U1,
   U2, secret leaks) with the sentence from §5.3 item 3: reads are the
   one effect undo cannot reverse, so read rungs come first.
2. **Add `write-ask` (or an `ask` flag on the write half) to 058's
   ladder**, and record where a remembered answer lands: allow →
   grant row (ADR 021), deny → session profile / policy layer.
3. **Fold §5.3 item 4 into spec 070** as a pin: a session's policy
   document is read-only to that session; binds compose
   most-restrictive-wins and can never loosen an ancestor.
4. **Cite §5.0 rows U1/U2 and "unrecoverable 40 %" in spec 054**:
   `ask` surfaces as `permission_denied.pending` through MCP
   tasks/elicitation; sweep is never a tool; the prompt fragment says
   writes are versioned and deletes are recoverable.
5. **Hand §5.1 to the branchfs memo and roadmap 023**: the session
   overlay must land only on commit, keep a `pre` per staged write,
   and keep uncommitted rows out of other sessions' nomination.
6. **Open a small spec for `versions` and `revert`** (§5.2) on the
   existing tables, ahead of sessions; add the session-touched-set
   mark when 023 lands.
7. **Record the `G`/`C` records as Catalog audit feed** (§5.4) in the
   ADR 058 follow-ups, beside the Mirage memo's `explain` and
   `Refusal`-in-`data` items.

---

## Sources

- arXiv 2604.13536, v4 (2026-08-31), read via
  `https://arxiv.org/html/2604.13536` — §2 (study: sources, triage,
  Figure 3 impact, Figure 4 taxonomy with "Counts can overlap",
  Findings 1–6, Table 1 harness survey), §4.1–4.3 (primitives,
  requirements, related work), §5.2–5.5 (staging, snapshots,
  progressive permission, implementation, `pivot_root`), §6–7
  (Table 3 self-correction, Table 5 routine tasks, Table 6 I/O
  overhead, Figure 12 snapshot scalability), §9 (conclusion), footnote
  2 (code URL).
- arXiv 2604.13536, v2 (2026-04-16), read via
  `https://arxiv.org/html/2604.13536v2` — the April title; 2.5 kLoC C /
  6.2 kLoC Rust; `yolo.toml`; `.yolo/files/` sharded and `journal`;
  override and rule trees on VFS dentries.
- `https://arxiv.org/abs/2604.13536` — version history v1–v4, the
  current abstract with the open-source line, DOI
  `10.48550/arXiv.2604.13536`.
- Microsoft Research publication page (April 2026 title; abstract; no
  code link on the page).
- `https://github.com/YoloFS/YoloFS` — landing page only: GPL-2.0
  badge, `kmod/`, `user/`, `docs/`, `tests/`, `.github/workflows/`,
  843 commits, 5 stars, hooks for Claude Code, Gemini CLI, GitHub
  Copilot. Not cloned.
- vfs records: `context/decisions/006`, `013`, `017`, `021`, `026`,
  `027`, `058`; `context/specs/active/058-row-level-permission-grants/spec.md`
  (Intent, open questions), `context/specs/active/070-principal-scoped-sessions/spec.md`
  (Intent, Decisions 1–5); `context/standards/roadmap.md` (023, 024);
  `src/vfs/permissions.py` (module docstring), `src/vfs/ops.py`
  (`MUTATING_OPS`, `READ_OPS`, `EXEC_OPS`, `DEVELOPER_OPS`),
  `src/vfs/results/kinds.py` (`VFSErrorKind`, `KIND_CONTRACTS`),
  `src/vfs/models/version.py`;
  `context/research/2026-09-04-mirage-design-patterns.md` §3.6–3.13,
  §3.21–3.23, §4.1–4.6, §4.8.
