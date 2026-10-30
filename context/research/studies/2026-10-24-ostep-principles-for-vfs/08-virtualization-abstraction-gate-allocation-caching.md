# Study 08: the process, the gate, address spaces, allocation and translation caches

- **Date:** 2026-10-24
- **Book section:** OSTEP v1.10, chapters 4 (the process), 6 (limited direct execution), 13 (address spaces), 17 (free-space management), read in full; chapters 18 (paging) and 19 (TLBs), skimmed for the indirection and caching ideas only.
- **Page numbers** are the chapter's own printed page numbers (OSTEP numbers each chapter from 1). The PDF ranges are: ch. 4 = PDF 52–64, ch. 6 = 80–95, ch. 13 = 152–160, ch. 17 = 200–217, ch. 18 = 218–232, ch. 19 follows.
- **vfs at:** HEAD `ac5c515` (main).
- **Executed here:** two throwaway scripts in the session scratchpad (`s08/trapcost.py` counts SQL statements per gated call; `s08/library.py` writes around the gate in process). Both ran with `uv run python -I` against SQLite. Nothing in the repo was changed.
- **Labels:** **READ** (the book, or a vfs file at `ac5c515`), **EXECUTED** (ran here), **INFERRED** (my reasoning).

These chapters are not about files. They are about how an operating system shares one machine among many programs while keeping control. This study keeps only the parts that transfer to vfs. The part that transfers best is chapter 6: it is the textbook version of the single gate that yesterday's memo puts at the centre of the vfs kernel.

---

## 1. What the chapters say

**Chapter 4, the process.** A program is dead bytes on disk. A process is that program running (READ, ch. 4 p. 1). The OS gives each process the illusion of its own CPU by switching between them (time sharing). The chapter splits OS code into two kinds. A *mechanism* answers how something is done. A *policy* answers which choice to make. Keeping them apart lets you change a policy without touching the mechanism (READ, ch. 4 p. 3). Every OS offers roughly five calls on a process: create, destroy, wait, miscellaneous control (suspend and resume) and status (READ, ch. 4 p. 3). A process moves between three main states: running, ready and blocked (READ, ch. 4 pp. 5–6). The OS keeps a small record per process, the *process control block*. In xv6 it holds the memory, the state, a process id, a parent pointer, a killed flag, the open-file table, the current directory, the saved registers and the trap frame (READ, ch. 4 p. 8). A finished process lingers as a *zombie* so its parent can collect the exit code (READ, ch. 4 p. 9).

**Chapter 6, limited direct execution.** The crux is speed with control (READ, ch. 6 p. 1). *Direct execution* means the program runs on the real CPU at full speed. *Limited* means it cannot do the dangerous things on its own. Without the limits, the OS would be nothing more than a library the program calls when it feels like it (READ, ch. 6 p. 2). The hardware gives two modes. *User mode* cannot do I/O. *Kernel mode* can (READ, ch. 6 p. 3). To ask for a privileged service, the program executes a *trap*. The trap jumps into the kernel and raises privilege in one step. *Return-from-trap* goes back and lowers privilege (READ, ch. 6 p. 4). The program cannot choose where in the kernel to land. At boot the kernel installs a *trap table*, and the program names a service only by a *system-call number* (READ, ch. 6 pp. 4–6). Installing the trap table is itself privileged (READ, ch. 6 p. 6). The kernel must treat every argument with suspicion, for example a pointer that points into kernel memory (READ, ch. 6 p. 6). Waiting for the program to call in (the *cooperative* approach) fails when it loops forever. A *timer interrupt* takes control back without the program's help (READ, ch. 6 pp. 7–9). On regaining control the OS may *context switch*: save one process's registers and restore another's (READ, ch. 6 pp. 9–11). Rebooting is a respectable recovery tool, because it returns software to a known state (READ, ch. 6 p. 10). A system call cost a few microseconds in 1996 and well under one now (READ, ch. 6 p. 13).

**Chapter 13, address spaces.** Each process sees its own private memory, the *address space*: code, heap and stack (READ, ch. 13 pp. 3–4). The addresses it sees are *virtual*. The OS and hardware translate them to *physical* addresses the program never sees (READ, ch. 13 p. 5). Any pointer a user program can print is virtual; only the OS knows the real location (READ, ch. 13 p. 7). The chapter names three goals for this illusion. *Transparency*: the program cannot tell it is virtualized. *Efficiency*: in time and in space. *Protection*: no process can touch another's memory or the OS's. Protection gives *isolation*: one part can fail without harming the others (READ, ch. 13 pp. 5–6).

**Chapter 17, free-space management.** The problem is handing out variable-sized pieces of a region and taking them back (READ, ch. 17 pp. 1–2). The enemy is *external fragmentation*: enough free bytes in total, but no single piece big enough (READ, ch. 17 p. 1). The mechanisms are *splitting* a free chunk to satisfy a smaller request, *coalescing* neighbours when a chunk is freed, and a *header* in front of each chunk holding its size (and a magic number for integrity), so that `free` needs no size argument (READ, ch. 17 pp. 3–6). The policies are best fit, worst fit, first fit and next fit. Keeping the free list sorted by address makes coalescing easy (READ, ch. 17 pp. 11–13). *Segregated lists* keep a pool per popular size; the *slab* allocator keeps those objects pre-initialized (READ, ch. 17 pp. 13–14). The *buddy* allocator splits by powers of two so the neighbour to merge with is found by one bit (READ, ch. 17 pp. 14–15). On multiprocessors, one shared allocator becomes the bottleneck, and the cited answers (Hoard, jemalloc) spread allocation out (READ, ch. 17 p. 15). No allocator is best for every workload; knowing the workload is what lets you tune it (READ, ch. 17 p. 16).

**Chapter 18, paging (skimmed).** There are two ways to manage space: variable-sized pieces, which fragment, or fixed-sized pieces, which do not (READ, ch. 18 p. 1). Paging cuts memory into fixed *pages*. A per-process *page table* maps each virtual page to a physical frame (READ, ch. 18 p. 6). Each entry carries bits: valid, protection (read, write, execute), present, dirty, and referenced (READ, ch. 18 pp. 6–7). The price is one extra memory lookup per access, which can halve speed (READ, ch. 18 pp. 8–9).

**Chapter 19, TLBs (skimmed).** The *TLB* (translation-lookaside buffer) is a small hardware cache of recent translations. The book says a better name is an address-translation cache (READ, ch. 19 p. 1). Caching works because of *locality*: recently used things are used again (temporal), and nearby things are used next (spatial) (READ, ch. 19 p. 5). A miss can be handled by hardware (the CISC style) or by a trap into the OS (the RISC style). The software way is more flexible: the OS may use any data structure it likes (READ, ch. 19 pp. 6–8). A TLB entry's valid bit means the cached entry is usable. That is a different thing from a page-table entry's valid bit, which means the page exists (READ, ch. 19 p. 8). On a context switch the TLB must either be flushed or each entry tagged with an *address-space id* (ASID), so one process never uses another's translation (READ, ch. 19 pp. 9–10). Two processes may share one physical page, for example code (READ, ch. 19 p. 10). If a program's working set is larger than the TLB covers, performance falls off a cliff (*TLB coverage*; the authors call the general warning Culler's Law) (READ, ch. 19 pp. 12–13).

---

## 2. Principles vfs should adopt

First, the map that the rest of this section leans on. It lays chapter 6's machinery onto vfs's `VirtualFileSystem` (`src/vfs/base.py`).

| Chapter 6 term | What it means | vfs today | Label |
|---|---|---|---|
| trap | the one way into the kernel | a public verb on `VirtualFileSystem` (`read`, `write`, …); over MCP, a tool call; in a WASI guest, a preview1 file call or the `host::call` import | READ (base.py; spec 172 §4) |
| argument check at the boundary | refuse bad inputs before acting | `_gate_params` runs first in every public verb against the `vfs.params` table; `resolve_path` mints the branded `Path` once | READ (base.py `_gate_params`, docstring) |
| system-call number | name a service by number, not by address | the `Op` literal in `vfs/ops.py` | READ |
| trap table | fixed map from number to handler | the `match op:` in `_call_storage`, one arm per op, ending in `assert_never` | READ (base.py `_call_storage`) |
| installing the trap table is privileged | user code cannot rewire the kernel | no dispatched verb can mutate the mount table; `bind`/`add_mount` are control-plane calls the host makes | READ (base.py module docstring) |
| user mode / kernel mode | the caller's rights vs the kernel's | the caller's `Authority` vs `_ADMIN_AUTHORITY = Authority.system()` for the router's own control-plane calls | READ (base.py constants) |
| kernel's own memory | the part of the address space users may not touch | the `/.vfs` reserved root (`check_reserved_path`); hidden entirely from a WASI guest | READ (paths.py; spec 169 §b3) |
| return-from-trap | come back with the answer, privilege lowered | a `Result`, never an exception; rebased to the caller's coordinates in `_dispatch_entry` | READ (base.py `_error`, `_dispatch_entry`) |
| timer interrupt | regain control without cooperation | the epoch deadline, fuel and the verb-call budget for wasm guests; the hop budget for routing loops | READ (spec 169 §b8; ADR 084 pin 5; base.py `_enter_hop`) |
| context switch, kernel stack | save one process's state, load another's | `contextvars.copy_context()` carries the hop budget, deadline and session path into the guest's worker; one guest per process | READ (spec 169 §b8) |

Now the principles. Each one says what the book teaches, whether vfs follows it, and the one change it implies.

1. **Run the program directly, but make every touch of a protected resource trap into one gate.** (ch. 6 pp. 1–2, p. 13)
   - *Status: follows for the WASI guest, half follows for CLI builtins, does not follow in process.*
   - The WASI guest is the textbook case. It runs at near-native speed inside wasm. Its only two ways out are the preview1 file calls and the `host::call` door, and both are gated by the caller's authority (READ, spec 172 §4; spec 169 §b4–b6). Wasm is the user mode: the guest cannot name a Python object.
   - CLI builtins get the filesystem capability as the verb set curried with the caller's `Authority` (READ, ADR 082 pin 2). For Python builtins, ADR 082 itself says this is a discipline enforced by review, not a wall (READ, ADR 082 pin 2).
   - An in-process Python caller has no wall at all. I built a router with a read-only permission map. A write through the router was refused `vfs.read_only`. A write straight to the storage object, with an `Authority.system()` I constructed myself, succeeded, and the router then served the new body (EXECUTED, `s08/library.py`). That is the book's warning in vfs form: without limits, the kernel is a library (INFERRED, from ch. 6 p. 2). This is by design: in-process code is trusted and the edge is where vfs is loud (READ, ADR 068 rules 4 and 7).
   - *Change:* the kernel ADR should name three trust tiers in plain words: in-process (the gate is a convention), the wire (the gate is a wall), the wasm guest (the gate is a wall). Today this is spread across ADRs 068, 082 and 084 (INFERRED).

2. **The caller names a service, never an entry point; the table of services is fixed.** (ch. 6 pp. 4–6)
   - *Status: follows.* Upstream code carries the op as a variable. `_call_storage` is the one place it meets a typed storage method, and `assert_never` makes a new op fail the type checker until it is routed (READ, base.py `_call_storage` docstring). `Session` is sugar over the same funnel, with no second dispatch path (READ, session.py docstring). The `cli` meta-verb parses a command into ops and re-enters the public methods, so every gate fires on the real verb (READ, ops.py docstring).
   - *Change:* none. The kernel ADR should cite `_call_storage` as the trap table and forbid a second door (INFERRED).

3. **Check every argument at the boundary, and refuse before acting.** (ch. 6 p. 6)
   - *Status: follows.* `_gate_params` runs first at every public verb, so a bad parameter reports `invalid` even on a closed table or a busy path (READ, base.py). Paths are proven once and carried as a branded type below the gate; storage never receives a bare string (READ, base.py and protocol.py docstrings). Mutations into `/.vfs` are refused by grammar (READ, paths.py `check_reserved_path`). In the WASI shim, a path that climbs above `/` is refused before any verb, and any `.vfs` segment answers `ENOENT` (READ, spec 169 §b3). This matches the book's example of a pointer into kernel memory (INFERRED).
   - *Change:* none.

4. **Rewiring the gate is itself privileged.** (ch. 6 p. 6; the TLB write instructions are privileged too, ch. 19 p. 12)
   - *Status: follows on the wire, half in process.* No dispatched verb can mutate a mount table (READ, base.py docstring). The binding is runtime state the host sets, never stored (READ, base.py `bind`). `serve()` refuses the system actor for every served call, and `cli` refuses it in process (READ, ADR 084 pin 3). Spec 148 plans the Plan 9 rule that once a session namespace is set, nothing may add or bypass a mount (READ, spec 148 item 6). In process, though, `Authority.system()` is a public constructor any caller can use (READ, authority.py; EXECUTED, `s08/library.py`).
   - *Change:* none beyond principle 1.

5. **The kernel must regain control without the program's help.** (ch. 6 pp. 7–9)
   - *Status: follows for wasm; half for everything else.* The wasm host has a real timer: the epoch deadline (exit 124), fuel (exit 137), a memory limit, and `VERB_CALL_BUDGET` 10,000 dispatches per run (READ, spec 169 §b8; ADR 084 pin 5). Routing loops are made finite by the hop budget, default 16 (READ, base.py `_enter_hop`). But the epoch deadline does not cover time spent inside a verb (READ, ADR 084 pin 5). Inside storage, grep checks a wall-clock deadline between its stages, which is the cooperative style (READ, `storage/backends/database/grep.py`). I found no engine-side statement timeout under `src/vfs` (EXECUTED, grep for `statement_timeout|lock_timeout`).
   - *Change:* a per-dialect statement timeout, set from the call's remaining deadline, would be the timer inside the kernel. It is a `DialectProfile`-style fact only if SQLAlchemy does not model it (INFERRED; spec 051's fan-out deadline is the nearest open spec).

6. **Keep mechanism and policy apart.** (ch. 4 p. 3)
   - *Status: follows.* ADR 084 pin 1 says the pinned gate order (capability, then grammar, then permission) is the execution policy. There is no second policy language over command text (READ). The mechanism is `_gate_entry`'s fixed order (READ, base.py). The policy is data: grant rows, postures and `PermissionMap`s (READ, ADR 068; base.py `_permission_layers`).
   - *Change:* none.

7. **Keep a small, named record per running thing, and keep it in the kernel.** (ch. 4 pp. 7–9)
   - *Status: half follows.* `Session` holds exactly one authority and a closed flag (READ, session.py). Spec 148's amendment adds four in-memory fields for the shell: `cwd`, `env`, `last_status` and `history` (READ, spec 148 header). A narrowed session holds no reference to a wider one, so there is deliberately no parent pointer (READ, spec 148 item 1, citing ADR 063 rule 1). The open-file table is not in the kernel: the WASI shim owns its fds per run (READ, spec 169 §b3–b5), and the memo keeps handles out of the kernel (READ, memo §4.2).
   - *Change:* write the session record down as one table, the way xv6's `struct proc` is one struct: field, owner, lifetime, and whether it crosses a wire call. Spec 148 is the place (INFERRED). Section 3 below drafts the rows.

8. **Keep the exit status after the run ends, until it is collected.** (ch. 4 p. 9)
   - *Status: follows, with eviction instead of `wait`.* The guest's exit code is recorded before `proc_exit` raises, so a trap cannot lose it (READ, spec 169 §b8). The `/.vfs/run/<call-id>/status` record keeps it, in a router-memory ring of 64 calls per authority, evicted least-recently-used, lost on restart (READ, spec 169 §c1). Only an equal `Authority` reads it (READ). This is a zombie table reaped by eviction, not by a parent's `wait` (INFERRED).
   - *Change:* none.

9. **Transparency: the program sees only virtual addresses.** (ch. 13 p. 5, p. 7)
   - *Status: follows, with honest leaks.* Every path a caller sees is in router coordinates. Storage receives terminal-relative paths (`without_mount`), and results are rebased on the way out (`with_mount`) in the one funnel (READ, base.py `_resolve_terminal`, `_dispatch_entry`; protocol.py docstring). Rows that a deeper mount shadows are dropped (`_shadow_filter`). The leaks are classified, never silent: `cross_mount` on a move or copy across mounts, `unsupported` when a mount lacks an op, and info-severity skip records in a fan-out (READ, base.py `_gate_entry`, `_skip_entry`). This is the book's goal with the leaks labelled (INFERRED).
   - *Change:* none.

10. **Efficiency: translation must not cost an extra trip.** (ch. 13 p. 5; ch. 18 pp. 8–9)
    - *Status: follows for paths.* The book's page table costs one extra memory reference per access. In vfs, path-to-row translation is folded into the data statement by the unique `path` index (READ, models/rows.py; ADR 004 keeps `path` as a regenerable cache of the `parent_id` chain). A system-actor `read` was one `SELECT` plus `BEGIN` (EXECUTED, `s08/trapcost.py`). The mount table is a linear longest-prefix scan in Python on every call, with no cache (READ, base.py `_match_mount`); mount tables are small, so this is fine (INFERRED).
    - *Change:* none for path translation. See principle 12 for the rights.

11. **Protection and isolation between the things that share the machine.** (ch. 13 pp. 5–6)
    - *Status: follows, and the gate has two halves.* Each mount gets its own table family; two mounts never share schema objects (READ, rows.py `build_vfs_tables`). `bind` refuses aliasing: one storage object, one path (READ, base.py `bind`). Permission maps compose from `/` down and can only tighten (READ, base.py `_permission_layers`). But the router's gate holds only capability, grammar and the structural maps. Grants are judged in storage, inside the statement (READ, base.py `_gate_entry` docstring; `storage/backends/database/rights.py` module docstring; ADRs 067, 072).
    - *Change:* the kernel ADR must name both halves as the one gate: the router's ingress half and storage's rights half. A front that bypassed either would bypass the gate (INFERRED).

12. **Cache the translation, and tag entries by owner instead of flushing.** (ch. 19 p. 1, pp. 9–10)
    - *Status: half follows.* vfs's TLB is the `RightsCache`: a caller's compiled rights, keyed by its subject set (the ASID of vfs), least-recently-used out past 1,024 entries or 64 MiB (READ, rights.py `RightsCache`, `RIGHTS_CACHE`, `RIGHTS_CACHE_BYTES`). Writes never touch entries. Each entry is revalidated by the stamps of the ids it read, so a stale entry simply stops matching (READ, rights.py). That is better than a flush. But a hit is not free. Counted on SQLite:

      | Call | Statements (excluding `BEGIN`) |
      |---|---|
      | `read` as the system actor | 1 |
      | `read` as alice, rights cache cold | 7 |
      | `read` as alice, rights cache warm | 3 (2 revalidation reads + the data read) |
      | `read` as anonymous on a `none` posture | 6, refused |

      (EXECUTED, `s08/trapcost.py`.) The two revalidation reads are
      `vfs_principal_revisions` and `vfs_relabels`. On a remote
      Postgres each is a round trip. The reason is real: a hardware
      TLB has one OS to send it a shootdown, while vfs is many
      processes sharing one database with no invalidation channel
      (INFERRED).
    - *Change:* fold the two revalidation reads into one statement,
      or into the data statement, and pin it with a statement count
      (INFERRED). A push channel (Postgres `LISTEN`/`NOTIFY`) is the
      shootdown alternative, but it is not portable to every dialect
      (INFERRED).

13. **Check protection on every access, even on a cache hit.** (ch. 18 p. 9; ch. 19 p. 2)
    - *Status: follows.* Every program run issues one gated `read` of the program entry, even when the compiled module is cached (READ, ADR 084 pin 2; spec 169 §b9). The cache is keyed by content hash and shared across callers, like a shared code page (INFERRED, from ch. 19 p. 10), but the right to use it is checked per caller. An `Authority` is a value and never caches a decision (READ, authority.py `Authority` docstring; session.py).
    - *Change:* none.

14. **A cache helps only while the working set fits; measure the hit rate.** (ch. 19 pp. 12–13)
    - *Status: does not follow yet.* The `RightsCache` has no hit or miss counter (READ, rights.py). An MCP server for group chats can have more than 1,024 live subject sets, because every distinct set of people in a chat is its own key (INFERRED, from ADR 066's subject set). Past that, every call is a cold compile of seven statements (EXECUTED count above).
    - *Change:* count hits, misses and evictions on the cache, as operation counts a test can pin (INFERRED; CLAUDE.md's performance-test rule).

15. **Keep the free list sorted by address and coalesce on free.** (ch. 17 pp. 3–4, p. 12; buddy, pp. 14–15)
    - *Status: follows, in an unexpected place.* vfs's rights algebra is a free-list algebra over the path address space. A `RangeSet` is spans sorted, disjoint and not touching: the address-ordered, coalesced free list (READ, `storage/grants.py` `RangeSet`, `normalise`). `subtract` cuts holes, which is splitting (READ). `minimise` keeps no root beneath another, which is the prefix-tree cousin of buddy coalescing (READ, `Covering`; INFERRED for the analogy). Every operation is one pass or one bisect, so cost follows the row count (READ).
    - *Change:* none.

16. **One shared allocator is the bottleneck under concurrency; spread allocation out.** (ch. 17 p. 15)
    - *Status: follows.* ADR 013 dropped the per-mount revision counter because it was a global mutex that collapsed writers to one per mount (READ, ADR 013 context). Ids are ULIDs minted by the writer with no coordination (READ, ADR 019; `ULID()` calls in `storage/backends/database/`). One counter remains, the grant revision, bumped only by admin writes (READ, `revision.py`), and ADR 078 moved the serialization lock off its hot row (READ).
    - *Change:* none.

17. **Keep an object's size and integrity check in a header beside it; delay the real free.** (ch. 17 pp. 5–6)
    - *Status: follows.* The narrow `vfs_entries` row holds identity, kind and metadata; bodies live in their own table, so a metadata write never rewrites content (READ, rows.py). The `content_hash` plays the magic number's integrity role (INFERRED). `delete` frees nothing: it sets a tombstone (READ, ADR 074), and `sweep` is the only destroyer (READ, ADR 027).
    - *Change:* none.

18. **Fixed-size pieces do not fragment.** (ch. 18 p. 1, p. 12)
    - *Status: follows, for statements.* A 10,000-row batch is cut into fixed-size chunks by `membership_budget` and the shared `chunked()` helper, so no batch ever needs one statement bigger than the tightest engine allows (READ, CLAUDE.md; `storage/backends/database/dialects.py`). That is paging applied to SQL statements (INFERRED).
    - *Change:* none.

19. **Restarting from a known state is a recovery tool.** (ch. 6 p. 10)
    - *Status: follows.* Each guest run gets a fresh `Linker` and `Store` (READ, spec 169 §b8). Each MCP `cli` call starts fresh at its `workdir` (READ, spec 148 amendment). Run records are lost on restart, and the docstring says so (READ, spec 169 §c1).
    - *Change:* none.

20. **Keep the gate's instruction set small and uniform; let the callers compose.** (ch. 19 p. 7, the RISC aside; p. 8, software flexibility)
    - *Status: half follows.* Yesterday's memo proposes a dozen path-keyed kernel ops, with `tree`, `edit` and `rmdir` derived from them (READ, memo §4.2, §4.4). Fronts are compilers onto the kernel; the `cli` meta-verb already is one (READ, ops.py). The query verbs are deliberately complex instructions, because only the kernel can push rights into the search (READ, memo §4.1 rule 2). The book's aside notes that the RISC/CISC fight ended with both kinds fast (READ, ch. 19 p. 7).
    - *Change:* none here. This is the kernel ADR's decision.

---

## 3. Nouns and verbs

**Adopt name** means use the book's word. **Concept** means keep the idea under vfs's own word. **Not** means vfs should deliberately not have it.

### Nouns

| Book noun (chapter) | Meaning | vfs today | Decision and reason |
|---|---|---|---|
| process (4) | a running program | a session (`Session`) for a conversation; a run (`/.vfs/run/<id>`) for a program | Concept. vfs has two lifetimes, the session and the run; one word would blur them. |
| process control block, `struct proc` (4) | the per-process record | `Session` fields; per-run state in the WASI host | Concept. Write it as one table (principle 7). |
| process list (4) | all live processes | `/.vfs/jobs` reserved; `/.vfs/run` ring | Concept, under the view names already reserved (spec 148). |
| pid (4) | the process's number | the run's call id (a ULID); no session id | Concept. A session id would also serve the audit; not proposed here. |
| parent pointer (4) | who created the process | none; a child session copies `cwd` and `env` and holds no reference to its parent | Not. A pointer to a wider session is a way back up; ADR 063 forbids it. |
| state: running, ready, blocked (4) | where a process is | a guest queued on the one-guest executor (ready), running, or waiting on a verb | Concept, not exposed. One guest per process makes ready a queue position. |
| zombie (4) | finished, exit code not yet collected | the run record with its exit code | Concept. Reaped by LRU eviction, not by `wait`. |
| open-file table (4) | per-process fds | the WASI shim's fds, per run | Not in the kernel. Fronts own handles (memo §4.2). |
| current directory (4) | per-process cwd | `Session.cwd` (spec 148 amendment) | Adopt name. It already is `cwd`. |
| mechanism / policy (4) | how vs which | `_gate_entry`'s order vs grant rows and postures | Adopt name in design docs. The split is already ADR 084 pin 1. |
| user mode / kernel mode (6) | restricted vs privileged execution | caller `Authority` vs `Authority.system()` | Concept. vfs's word is the actor, and the system actor is the right name. |
| trap (6) | the controlled jump into the kernel | a verb call through the funnel; `host::call` in a guest | Adopt as a design word for the kernel ADR. It names exactly the one door. |
| trap table (6) | fixed map from service number to handler | `match op:` in `_call_storage` | Concept. Keep the code name; cite it as the trap table. |
| system-call number (6) | service id | `Op` | Concept. |
| trap frame, kernel stack (6) | saved caller state on entry | the call's context variables (hop budget, deadline, session path) | Concept. |
| timer interrupt (6) | regain control without cooperation | epoch deadline, fuel, verb-call budget, hop budget | Concept. vfs's word is budget, and ADR 084 already names them. |
| context switch (6) | swap running process | handing context to the guest worker with `copy_context()` | Not a public noun. Internal only. |
| address space (13) | a process's private view of memory | the namespace an authority sees | Concept. The vfs phrase is what the authority sees; vfs hides rows rather than giving each caller a private copy (ADR 065). |
| virtual / physical address (13) | what the program sees vs where it lives | router path vs terminal-relative path in a mount | Concept. Router coordinates and entry coordinates are the vfs words. |
| transparency, efficiency, protection (13) | the three goals | — | Adopt names as the checklist for mounts and fronts. |
| isolation (13) | failure of one does not harm another | per-mount table families; `bind` refuses aliasing | Adopt name. |
| heap, free list (17) | managed region and its free chunks | the SQL engine's pages; vfs has none | Not. The engine allocates space (section 4). |
| header, magic number (17) | metadata beside the object | the narrow entries row; `content_hash` | Concept. |
| splitting, coalescing (17) | cut a chunk; merge neighbours | `subtract` and `normalise` on a `RangeSet` | Concept. The grants module already speaks of spans and holes. |
| external fragmentation (17) | free but unusable gaps | engine bloat from dead tuples and tombstones | Not vfs's to manage, beyond `sweep`. |
| segregated list, slab (17) | per-size pools of ready objects | `build_vfs_tables` cached per shape (`TABLE_FAMILY_CACHE` 64) | Concept. |
| buddy (17) | power-of-two split and merge | prefix coverings (`minimise`) | Concept, by analogy only. |
| page, page frame (18) | fixed-size unit of memory | a statement chunk under `membership_budget` | Concept. |
| page table (18) | per-process translation map | the `path` index (shared); the compiled rights (per authority) | Concept. vfs splits translation (shared) from protection (per caller). |
| page-table entry bits: valid, protection, dirty, referenced (18) | per-entry facts | tombstone (`deleted_at`); `everyone_level` on the row; the WASI buffer's dirty flag; none | Concept for the first three. **Not** for referenced: an access bit turns every read into a write, and vfs writes nothing on a read (ADR 072 rule 6). |
| TLB (19) | cache of translations | `RightsCache` | Concept. |
| ASID (19) | tag an entry with its owner | the subject-set key | Concept. |
| TLB valid bit vs page valid bit (19) | cache entry usable vs page exists | stamp key matches vs row not tombstoned | Concept. Worth stating in the rights docstring; the two are easy to confuse. |
| coverage (19) | how much the cache can hold | `RIGHTS_CACHE` 1,024 / 64 MiB | Adopt name in the cache docstring, with a hit counter (principle 14). |
| wired entries (19) | slots never evicted | none; the newest entry always stays | Not needed. The system actor skips the cache entirely. |

### Verbs

| Book verb (chapter) | vfs today | Decision and reason |
|---|---|---|
| create (process) (4) | `fs.session(authority)`; a `cli` call starts a run | Concept. |
| destroy / kill (4) | `Session.close()` (final); a budget kill gives exit 137 or 124 | Concept. |
| wait (4) | none; the call is awaited, and the run record is read later | Not. vfs calls return; nothing blocks on another run. |
| suspend / resume (4) | none; the `pending` kind answers instead of blocking | Not as blocking. Spec 148 says storage never blocks; `pending` is a refusal you can re-run, not a blocked state. |
| status (4) | `read /.vfs/run/<id>/status` | Concept. |
| load (4) | the gated `read` of a program entry, then a compile-cache lookup | Concept. Load is lazy in modern OSes (ch. 4 p. 4); the staged-buffer cache is lazy loading of the zip (spec 172 §3). |
| trap / return-from-trap (6) | verb call / `Result` | Adopt trap as a design word only. |
| yield (6) | `await` points in asyncio | Not a vfs verb. |
| interrupt (6) | budget trips | Concept, as budgets. |
| check arguments (6) | `_gate_params` | Concept. |
| translate (13, 18) | `_resolve_terminal`, rebase | Concept. |
| malloc / free (17) | `write` / `delete` then `sweep` | Not as names. `delete` is not `free`; it only hides (ADR 074). |
| split / coalesce (17) | `subtract` / `normalise` on range sets | Concept. |
| flush (19) | none; entries stop matching instead | Not. Revalidation by stamps is the vfs design. |
| evict (19) | LRU in `RightsCache`, the run ring and the wasm cache | Adopt name. |

---

## 4. What does not transfer

**There is no hardware mode bit in Python.** Chapter 6's protection rests on the CPU refusing user-mode I/O (READ, ch. 6 p. 3). Python has no such refusal. An in-process caller can reach the storage object and can construct the system authority (EXECUTED, `s08/library.py`). So vfs's gate is a wall only where a real boundary sits under it: a wire, or wasm (INFERRED). vfs chose this on purpose (READ, ADR 068). The lesson that does transfer is to say so plainly.

**vfs never allocates space.** Chapter 17 is about handing out bytes in a region. vfs never sees a byte address. The SQL engine owns heap pages, B-tree page splits, TOAST and reclamation (`VACUUM` on Postgres) (INFERRED). Best fit, first fit and the rest have nothing to act on. External fragmentation in vfs's world is engine bloat from dead row versions and tombstones. vfs's one lever on it is `sweep` (READ, ADR 027).

**Allocators reuse addresses; vfs must never reuse an id.** Reuse is the whole point of a free list (READ, ch. 17 pp. 3–4). In vfs, reuse is a bug class. ULIDs are minted fresh (READ, ADR 019). SQLite tables use `AUTOINCREMENT` so a deleted top row id is never reused (READ, rows.py). Retired posting-encoding tags and retired error kinds are never reused either (READ, rows.py; results/kinds.py). The reason is ETL: ids cross engines and dumps, where a reused id silently joins the wrong lineage (READ, ADR 019 context).

**Translation is not an extra trip.** Paging's cost is an extra memory reference per access (READ, ch. 18 p. 9). In vfs, the `path` index is both the page table and the data access: one `SELECT` does both (EXECUTED). So vfs needs no path-translation cache, and adding a dentry-style cache would buy little and add a coherence problem (INFERRED).

**There is no single OS to send a shootdown.** One kernel owns a machine's TLBs and can flush them (READ, ch. 19 p. 9). vfs runs as many processes sharing one database. No process can tell another that a grant changed. So caches revalidate on every call instead, which costs statements (EXECUTED: 2 per warm call) (INFERRED for the cause).

**vfs does not schedule the CPU.** The scheduler questions that chapters 4 and 6 lead into belong to the engine (query scheduling) and to asyncio (cooperative). vfs's only scheduling fact is one wasm guest per process (READ, spec 169 §b8).

**Mounts are not processes.** The address-space analogy maps the *caller* (an authority) to the process, and maps a mount to a region of physical memory or a device. Two mounts do not need isolating from each other the way two processes do. Two callers do (INFERRED). Isolation between callers is done by hiding rows, not by giving each a private copy (READ, ADR 065).

**No swapping, no accessed bit.** Every row is always in the database, so the present bit has no meaning. An accessed bit would turn every read into a write; vfs writes nothing on a read (READ, ADR 072 rule 6).

**No saved registers.** A context switch saves machine state (READ, ch. 6 p. 9). A vfs call is stateless: the authority travels on every call and is re-derived each time (READ, authority.py). The little state there is rides in context variables (READ, spec 169 §b8).

---

## 5. The one design lesson

Chapter 6 says a kernel earns the name only when the program cannot reach the hardware except through its trap, and vfs's gate is that trap for the wire and the wasm guest but only a convention for in-process Python. The gate itself already has the textbook shape: a fixed table of ops (`_call_storage`), arguments checked first (`_gate_params`), a privileged control plane (no verb rewires the mount table), budgets as the timer, and protection checked on every access, cache hit included. What the book adds is the cost view: a translation cache must be cheap on a hit, and vfs's rights cache still pays two statements to revalidate every warm call, so that is the place to spend the next effort.

One line: vfs already has a real trap table; make the walls explicit and make the rights cache hit nearly free.
