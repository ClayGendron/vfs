# An interrupted line is saved as its inputs and its replies, and replays them when it is resumed

A draft, written on 2026-11-22. It is not reviewed, and nothing is built. It is spec 8 of the nine that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps, and it rests on that page, on the two guides under `documentation/how-to/`, and on the tree at `6dae6a1d` on the branch `a-job-is-interrupted-and-resumed`. Every fact marked "Run" below was run that day. The extension installed in the checkout was older than the source (it did not take `host_programs`), so the probes ran against a build of the working tree made in the session's scratch directory, with wasmtime 51.0.0. The first draft was written without sight of the other eight specs. A second pass, the same day, read all eight and took every name another spec owns from that spec. Each is cited by its number and its heading, because the other eight were being revised during that pass. What no other spec provides yet is listed under "Needs no other spec meets yet".

## The outcome wanted

A shell line that reaches a step needing a person stops before that step and returns. Its job is stored as the line's inputs and the replies it had been given. When the job is resumed with the answer, the line carries on from that step, in any process, and returns the result its call would have returned. Nothing the line did before the stop is done again. A line that is never stopped stores nothing.

## Builds on

Each of the other eight specs is drafted and not built.

- **The shell as built** (`src/vfs/shell/`, `crates/vfs-shell`, `crates/vfs-shell-wasm`, `crates/vfs-core/src/shell_binding.rs`). Landed.
- **`agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md`.** Landed. Its version mint keeps every replaced body whole, which decision 7 rests on.
- **Spec 0, the kernel keeps records of its own.** Used as it stands:
  - decision 9, "The store is used through `query` and `commit`, and a failure is one exception";
  - decision 12, "A batch of rows is written in chunked statements through four helpers": `insert_rows`;
  - decision 17, "Expired records are removed by a counted sweep in bounded chunks, and a record past its expiry reads as absent before it is swept": `register_sweeper`;
  - decision 6, "A root in memory keeps its records in a second database in memory";
  - decision 22, "The interface is private, and this is all of it", and its eight rules, which decision 9 here follows one by one.
- **Spec 1, a row carries an etag.** Decision 4, "Each verb fills the etag on the rows it already returns": a `read` row carries `etag` beside `version` and `content_hash`. Decision 2, "An etag is twenty hexadecimal characters: a keyed digest of the mount, the entry and the version": an etag is compared and never taken apart, so decision 7 keeps the version beside it.
- **Spec 2, a session is stored.** Decision 13, "`vfs_sessions` holds one row per session, under a key that is never used twice": a line's job names its session by `session_key`, on spec 7's row. This spec's own table names no session.
- **Spec 3, the session remembers what it read.**
  - decision 16, "A bare line is a strict session of its own, and it is never stored": the line session and its table in memory;
  - decision 17, "The shell's host sends what a line is shown and what it changes through the guarded router, and its probes through the kernel";
  - decision 18, "A writer that spans chunks carries the etag its last chunk left": the host's writer mapping, which decision 28 rebuilds;
  - decision 19, "Both faces and both stores share one implementation": the table's interface of look up, show and change, which decision 28 replays through.
- **Spec 4, a session works in turns.** Decision 10, "The shell state is stored on the turn row when a line ends having changed it, and a line starts from the nearest state at or before its turn": nothing is stored when a line is interrupted and saved as a job, and a resumed line stores its state when it ends, in the turn it started in. Its `run_line_from` and `ShellState` are the start state the line record keeps. Decision 12, "`rewind(before=turn)` removes that turn and every later one, with their stamps, and cancels their waiting jobs, in one transaction": the pages of a cancelled job go with it by decision 9 here.
- **Spec 5, a rewind puts a session's files back.** Decision 5, "A rollback reads the files through two storage methods, `find_entries` and `read_versions`, and no public verb is added", and its first landing, which is the seam alone. By ruling 8 of the reconciliation there is one seam that reads an old body, and spec 5 owns it: `SupportsVersions`, `read_versions`, `VersionTarget` and the trait `versions`. Decision 8 here uses them and adds no seam.
- **Spec 6, a policy judges each step.**
  - decision 6, "`via` is the line that made the step, and the line itself is not a step": `Line(text, cwd)` and `decisions.in_line`;
  - decision 9, "A file system keeps its policies in the order they were added, and a change is seen by the next step": `decisions.guarded`, the test with no I/O that decision 4 asks once;
  - decision 14, "A denial refuses the whole step under one new kind, `vfs.permission_denied.policy`": inside a line a policy's denial prints `Permission denied`;
  - decision 21, "A step turns into JSON and back into an equal step, and has one canonical form".
- **Spec 7, a job is interrupted and resumed.** It owns the record, the states and the claim, and this spec uses them by their names:
  - decision 4, "`vfs_jobs` holds one row per stored job, and `vfs_job_pages` holds what does not fit in the row": the `kind` `line`, the saved part, `JOB_INLINE_BYTES`;
  - decision 5, "A job is in one of four states, and every change of state is one conditional update on its revision": `interrupted`, `running`, `finished`, `cancelled`;
  - decision 6, "The job is committed before the interrupted result is returned";
  - decision 9, "An interrupt's id is derived from the job, the place, the raiser and a count, and an answer is used only for the question it answered": the place;
  - decision 12, "The interrupted result is a `Result` with one fatal entry of the kind `vfs.interrupted`, and it carries the job", and decision 15, "An interrupted result turned into text reads "Not approved", and the first one in a process logs one `WARNING`";
  - decision 16, "`resume(job_id, answer, *, authority)` is the only public call that answers, and it returns the result the caller's call would have returned", and decision 17, "A job may be resumed by the system authority, and by an authority that holds `read_write` on every path the step names";
  - decision 20, "A resume runs the policies again with the answers the job has, and the run ends in one of seven ways";
  - decision 21, "Exactly one resume carries a job on, and the loser is refused with the job's state", decision 22, "The saved step is carried out as its caller, with rights judged again, and with the etags the preview saw as `if_match`", and decision 23, "A claim is a lease of five minutes, and a job left running past it is carried on again under the same guard";
  - decision 24, "A finished or cancelled job answers `resume` with its result again until it lapses, and the stored result is bounded": `JOB_RESULT_BYTES`;
  - decision 26, "The same step made again by the same caller while its job waits joins that job";
  - decision 27, "A denial and a cancel are the kinds `vfs.interrupt.denied` and `vfs.interrupt.cancelled`, and their words name the principal that answered by its name", and decision 29, "`Cancel(reason=None)` answers any interrupt and ends the job, and nothing the job did is undone";
  - decision 34, "A resumed job stays in its turn, and what it writes is remembered by its session", and decision 36, "A waiting job lapses `job_lifetime` after it stopped, 24 hours by default, and the sweep removes it";
  - decision 37, "A line's job uses the same record, states and claim, and spec 8 supplies what is saved and how it is carried on": `store_job`, `load_job`, `stop_again`, `claim`, `finish`, `cancel`, and a kind as one object. Decision 27 here is that object.
- **`agents/2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md`.** Drafted. It changes the wire and pins the toolchain. The journal holds the replies as the Python host gives them, so the wire's change does not change it.
- **`agents/2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md`.** Drafted. Its verb budget is counted inside the machine, so decision 23 covers it with no change.
- **`agents/2026-11-21-the-shell-runs-the-standing-program-table/spec.md`.** Drafted. Its decision 2 serves `date` and its kin through `value`, which decision 11 journals.
- **`agents/2026-11-22-a-served-grep-hands-its-matches-to-the-line-a-page-at-a-time/spec.md`.** Drafted, with its decisions open. If a feed comes to make a verb call of its own, that feed's reply is journaled with its bytes, by decision 6's rule for a reply nothing else can rebuild.
- **`agents/2026-11-21-an-append-keeps-only-what-it-added/spec.md`.** Drafted. It changes what a version row holds. Spec 5's `read_versions` answers `not_found` for a version that is not stored whole, which decision 15 here turns into a refused resume.
- **Roadmap stories H4 and F3, decisions D40, D41, D43, D46, D54 and D60.** "Earlier decisions this reverses" says what becomes of each.

Three files are rewritten by more than one of the nine. `src/vfs/shell/host.py` is changed by specs 3, 4 and 6 and by this spec. `HostError` in `crates/vfs-shell/src/machine/mod.rs` gains two members from spec 3 and one from this spec. `src/vfs/base.py` is changed by all nine.

## Terms

- **Line.** One call of `cli`: a string of bash, run as one caller.
- **Machine.** The shell's interpreter, a WebAssembly module. It does no I/O. A host drives it with `step(replies)`.
- **Host.** `src/vfs/shell/host.py`. It answers each request of the machine with a public verb, as the line's caller.
- **Request.** One thing the machine asks of its host. It has a **key**, its place in the walk of the line: the path of the task that asked and an ordinal in that task, written `0.1#3`.
- **Reply.** The host's answer to one request.
- **Step.** One public verb about to run, with its checked arguments. It is spec 6's word. A request that reaches a public verb is one step.
- **Step loop.** `while True:` in `run_line`. Each pass calls `machine.step` once, and answers the requests it returns in order. A pass is not a step: one pass can return several requests.
- **Journal.** The replies a line has been given, in the order they were given, each with the key and a digest of the request it answered.
- **Position.** An entry's place in the journal, an integer counted from 1.
- **Place.** Where a step stands inside its job, as spec 7 uses the word. For a step of a line it is the position of its request, a dot, and the count of verb calls the host had made for that request: `12.0`.
- **Stop.** The point where a step of a line must be interrupted. The line's job is saved there and the call returns.
- **Replay.** Running a fresh machine from the line's start and answering from the journal.
- **Line record.** The JSON document a line's job holds in its saved part: the line's inputs and where it stopped.
- **Build fingerprint.** A digest of the build of the machine and of the tables a walk depends on. It is not the `fingerprint` column of `vfs_jobs`, which is spec 7's digest of what was called.
- **Host program.** A name in `PROGRAMS` that the host runs itself at a `start` request, such as `grep -r` or `edit`.
- **Slice.** The work the machine does between two returns of `step` when it asks nothing.
- **Fuel.** The instructions the module has executed, counted by the runtime.
- **Interrupt.** What a stopped job waits for: a message, a schema for the answer, and a preview. It is spec 7's.
- **Claim.** The conditional update by which one resume, and no other, moves a job to `running`. It is spec 7's.
- **Etag.** Twenty hexadecimal characters that name one entry at one version. It is spec 1's, and it cannot be taken apart.
- **Stamp.** A session's memory that it was shown a path at an etag. It is spec 3's.
- **Guarded router.** The kernel's verbs wrapped with spec 3's rules. A stored session holds one and a line holds one.
- **Line session.** The strict session a bare `fs.cli` line runs in, whose stamps are a table in memory. It is spec 3's.

## What the code does today

Read at `6dae6a1d`, and run on 2026-11-22 on a file system in memory.

| Fact | How it is known |
|---|---|
| `run_line` starts one machine and loops: `step(replies)`, then one `host.answer` for each request, in the order the step returned them. | Read, `host.py:252-261`. |
| The machine is started with the line, `env` and `PWD`, `cwd`, `$0`, no arguments, `stdin`, the two program lists, `pid`, `limits`, `fuel` and the seconds left of the deadline. | Read, `host.py:219-233`. |
| A line never runs as the system actor. | Read, `host.py:216-218`. |
| The machine asks twelve kinds of request: `read`, `write`, `touch`, `stat`, `list`, `mkdir`, `remove`, `copy`, `move`, `value`, `start` and `feed`. | Read, `crates/vfs-shell/src/machine/mod.rs:165-224` and `shell_binding.rs:673-762`. |
| The host serves each with one public verb, except `value`, `feed`, and a `start` that runs a host program. | Read, `host.py:353-367`, `:369-505`. |
| A host program calls up to three verbs. `grep` calls `stat`, `grep` and `glob`. `find` calls `stat` and `glob`. `grant`, `revoke`, `edit`, `mkedge` and `rmedge` call one verb each, and it is the only change they make. | Read, `programs.py:268-355`, `:483-527`, `:695-757`, `:913-930`. |
| The host keeps state between requests: the body each open saw, the opens that share it, the writes of each running host program not yet fed, and up to 100 refusals. | Read, `host.py:309-321`, `:122`. |
| `value` answers `time` from `time.time()` and `random` from `random.randrange`. | Read, `host.py:516-522`. |
| The machine asks `value` in one place, for `printf '%(…)T'`, and never asks `random`. `$RANDOM`, `$SECONDS`, `$EPOCHSECONDS`, `$EPOCHREALTIME` and `$SRANDOM` expand to nothing. `date`, `sleep` and `mktemp` are `start` requests the host answers `not_found`. | Read, `builtins.rs:489-503`. Run. |
| `$$` is the `pid` the host passes, 1000. A subshell's `$BASHPID` is computed from its place: `(echo $BASHPID)` prints 1101. | Read, `host.py:80`, `shell.rs:355-358`. Run. |
| The machine has no clock, no random source and no hashed map. It is one future polled in a fixed order, and "a future here never wakes anything". | Read, `io.rs:1-4`, `:434-473`. A search of `crates/vfs-shell/src` and `crates/vfs-shell-wasm/src` for `HashMap`, `HashSet`, `Instant` and `SystemTime` finds nothing. |
| A slice ends on a count of fuel, never on a clock. The clock ends a line at its deadline and does nothing else. | Read, `shell_binding.rs:441-459`. |
| Two laws are held today: two runs of one line ask equal key lists, and the same line spends the same fuel. | Read, `crates/vfs-shell/tests/laws.rs:48`, `crates/vfs-shell-wasm/tests/module_laws.rs:276`. |
| 18 lines were each run once through the real host with every request and reply recorded, then twice more on fresh machines fed the recorded replies by position. All 36 replays asked the same requests in the same order and gave the same output, statuses, exit status and fuel. The lines hold pipelines of five stages, three jobs run with `&` and `wait`, loops, substitutions, process substitution, host programs and an early-closing `head`. | Run, `spec8_probe_replay.py`. |
| Five lines were stopped before every change and resumed by replay, 4, 30, 4, 9 and 5 times. Each gave the output, the files, the list of changes and the fuel of a run never stopped, and made 0 router calls while the journal lasted. One stops in the middle of an open that spans chunks, and one between a host program's start and its feed. | Run, `spec8_probe_stops.py`. |
| The order of requests across tasks depends on where a slice ends. With `fuel_slice` at 100,000,000 in place of 10,000,000, two of five concurrent lines asked in another order, and one asked a ninth request. With 200,000, one of five differed. Output and exit status were the same every time. | Run, `spec8_probe_values.py`, `spec8_probe_slice.py`. |
| `cat a > b` sends two writes to `b`: one of 0 bytes that truncates when the file opens, and one that appends the body. `echo x > b`, `tee b`, `sed -i` and `cp a b` each send one request that changes `b`. | Read, `files.rs:1-7`. Run, `spec8_probe_guide.py`. |
| A refused change fails its command and the line goes on. The status is 1 for a redirection, `cp`, `mv`, `rm`, `mkdir`, `touch`, `tee` and `cat`, 2 for `ls`, and 4 for `sed -i`. | Run, `spec8_probe_guide.py`. |
| The machine prints a refusal from a closed set of eight texts. | Read, `mod.rs:232-258`. |
| A replaced body is kept whole in `vfs_versions` under the version it had, with its hash. Nothing reads one back. | Read, `storage/backends/database/versions.py:1-16`, `models/rows.py:487-507`. |
| `cli` takes a line, `cwd`, `stdin` and an authority, on four faces. | Read, `base.py:1668-1677`, `session.py:414-417`, `sync.py:598-599`. |

The four probe scripts are in the session's scratch directory under `specs/`. They are not kept, and the tests under "Tests" stand in their place. The probes drove the host as it is built today. They did not run spec 3's guarded router or spec 7's record, which do not exist.

## The problem

A line is many steps. When one of them needs a person, VFS must stop and return, and it holds nothing open. The line's place is inside the machine, and the machine is a future over shared cells that cannot be moved to another process.

An earlier draft saved the machine's linear memory at the stop and wrote it into a fresh instance at the resume. That was ruled out: nothing saved is a memory snapshot. Its other cost was its own decision 22. A saved memory describes one instant, so a line could be saved only at a stop, and a line that died anywhere else could never be recovered.

The other road is to walk the line again. It is safe only if the walk is the same walk, and only if nothing the line did is done again. The first is a property of the machine, which the probes above show. The second needs every reply the line was given.

## Decisions

### 1. A line's job is the line's inputs, its journal and the place it stopped

Nothing of the machine is saved. A line's job is a row of `vfs_jobs` whose `kind` is `line` (spec 7, decision 4). Its saved part holds the line record of decision 3. The journal is in `vfs_job_replies`. A resume builds the machine again from the inputs and feeds it the journal.

Reason: ruling 2 of the overview. A line is a function of its inputs and its replies, which the two laws and the 36 replays show, so the inputs and the replies are the whole of its state.

### 2. A journal and a line record are records the kernel keeps, and add no primitive

Neither has a path. Both are reached only through `resume` and `jobs`, which are management methods. No view of them is served in the namespace.

Reason: Article 1 of the constitution allows five first-class things and gives each a path. A journal is a record about a call, as a grant is a record about a path.

### 3. The line record holds everything the machine is started with

The saved part of a line's job is the document spec 7's decision 4 defines for a step, for the step the line is stopped before: its format number, the caller's authority in full, that step as spec 6 writes it, and the etags its preview saw. It gains one key, `line`, whose value is the line record:

| Field | Holds |
|---|---|
| `format` | `JOURNAL_FORMAT`, 1 |
| `build` | decision 13's build fingerprint, of the build that ran the line |
| `line` | the line's text, at most the parse budget of 1 MiB |
| `cwd` | the working directory the line started in |
| `env` | the pairs `run_line` was given, before it adds `PWD` |
| `name`, `args`, `pid` | `$0`, the arguments, and `$$` |
| `limits`, `fuel` | the budgets as the call gave them, or null |
| `stdin_bytes` | the length of the line's standard input |
| `stopped` | the position, key, name and digest of the request the line stopped at, and the place of the step |
| `stops` | how many times the line has stopped |
| `entries`, `bytes`, `pages` | the journal's counters: its next position, its size, and its next page |
| `evidence`, `unkept` | the refusals the host had kept, at most 100, and the count past 100 |

- The session and the turn are `session_key` and `turn_number` on the job row (spec 7, decision 4). `cwd` and `env` are the `ShellState` the line started from, which for a line of a stored session is the one spec 4's decision 10 read.
- Standard input is not in the record. It is the journal's first entry, at position 0, when it is not empty.
- The two program lists are not in the record. The build fingerprint covers them.
- The deadline is not in the record. Decision 23 says why.
- `evidence` is the host's own bounded state, not the machine's. It is saved because the facts come from verb results that the journal does not keep.
- The record is JSON. Nothing in it is revived as a Python object other than through a pydantic model.
- A saved part of at most `JOB_INLINE_BYTES` is in the row, and a larger one is in `vfs_job_pages`, by spec 7's rule. The stopped step carries its own arguments, so a line stopped before a write of 8 MiB has a saved part of about 11 MiB, as a direct write of that body has.

Reason: a replay that takes any input from the running process can walk another line. Reading every input from the record makes a changed environment, a changed default budget or a changed `PID` constant unable to change the walk. The stopped step is saved as spec 7 saves any step, so that who may resume, the listing and the judging of spec 7 need no second road for a line.

### 4. Replies are kept in memory while a line runs, and are written only when it stops

- A line records its replies only when it can be interrupted. It asks `decisions.guarded` once, when it starts (spec 6, decision 9). With no policy on the kernel and none in the call context, a line records nothing, hashes nothing, and runs as it does today.
- A recording line keeps one entry in memory for each reply. It writes nothing to any store until a step must be interrupted.
- At a stop, the entries added since the last stop are written, with the job row, in one `commit` of the kernel store. Then the machine is dropped and the call returns.
- A line that ends without stopping drops its entries. No statement was issued for them.
- A process that dies in the middle of a line that has never stopped leaves what the line had done, and no job. This is a failed call, as it is today. Decision 29 says what becomes of a resumed line whose process died.
- A policy added while a line runs judges the line's later steps (spec 6, decision 9), and so can interrupt a line that is not recording. That line cannot be stopped, and decision 10 says what it gets.
- When tools are built, a tool that can ask makes a call interruptible too, and the same test covers it.

Reason: a line that is never stopped must cost nothing, and most lines are never stopped. Writing each reply as it is given would put a synchronous statement on every read a line makes, which the overview forbids. The format still allows it later: the journal is positional and append-only, so writing entries as they are made changes when they are written and nothing else.

### 5. The journal is positional, and each entry carries the key and a digest of its request

An entry is `[position, key, op, digest, kind, payload]`, with a seventh item, `stamps`, when decision 28 gives it one.

- `position` counts the replies from 1, in the order the host gave them.
- `key` is the machine's key for the request.
- `op` is the request's name.
- `digest` is the first 16 bytes of a SHA-256, in hex. It covers the bytes `vfs.line.request.1`, the key, the name, and every argument in name order. Each part is preceded by its length as 8 bytes. Text is UTF-8, an integer is decimal, a flag is `1` or `0`, bytes are themselves, and a list is its count and then its items.
- `kind` and `payload` are the reply, in decision 6's form.

The journal is matched by position, never by key alone and never by content.

Reason: Restate and Temporal both match by position and compare what should be stable, and both report the index on a mismatch. The key in the digest ties each entry to its place in the walk, so an answer can never reach a request it was not for. Matching by content is what the bug tables of Restate's agents layer and of LangGraph record.

### 6. Each kind of request has one journaled form

| Request | Journaled | Form of the payload |
|---|---|---|
| `read` | yes | `ref`: the etag, the version and the content hash of the body the open saw, by decision 7. Or `data`: the bytes of the slice and whether it ended the file, when the row has no etag or its mount cannot serve an old body. Or `error`: the code. |
| `stat` | yes | `stat`: the kind and the size. Or `error`. |
| `list` | yes | `entries`: each name and kind, in the order given. Or `error`. |
| `value` | yes | `text`: the text given. Or `error`. |
| `start` | yes | `library`. Or `refused`: the status and the message. Or `error`. Or `started`: every write the program made, in order, with its status, which is the whole of what its feeds will hand out. |
| `feed` | yes, with no payload | The reply is taken from the `started` entry's writes, as the host takes it today. |
| `write` | yes | `done`, with the etag of the row the write left. Or `error`: the code. Or `denied`: the words, by decision 18. |
| `move` | yes | `done`, with the source and the target. Or `error`. Or `denied`. |
| `touch`, `mkdir`, `remove`, `copy` | yes | `done`. Or `error`. Or `denied`. |

- Bytes inside a payload are base64. A journal's size is its encoded size.
- The request's own arguments are not kept, but for a move's two paths, which decision 7 follows. A write's data is in no entry. Only the digest is.
- The etag of a write is kept because spec 3's decision 18 holds each later chunk of that writer to it.
- A reply that nothing else can rebuild is journaled with its bytes. A reply that a kept entry or a stored version can rebuild is journaled as the pointer to it.

Reason: the machine reads each reply to decide its next step, so each must be given again exactly. Keeping a request's arguments would double the memory of every write a recording line makes, and the digest is enough to tell that the machine asked the same thing.

### 7. A read is journaled as a reference to the body it saw, and the body is read again on replay

- The host asks `read` for `etag` and `version` beside the columns it asks for today. The body an open saw is named by its path, its etag, its version and its content hash. An etag cannot be taken apart (spec 1, decision 2), so the version is kept beside it.
- Each `read` entry of that open holds the etag, the version and the hash. The path, the offset and the length are in the request.
- On replay the host fetches the body by decision 8, once for each open, and cuts each slice from it. The body is held under `READING_BYTES` as a live body is.
- The path asked at the resume is where the line itself left the file: the host follows the line's own journaled moves, of the file or of a directory above it, from the path the read named. A file the line deleted is still at its path, as a tombstone.
- The fetch is the kernel's own, made as the system authority. It asks no policy and leaves no stamp.
- A body that cannot be found refuses the resume, by decision 15.

| Way to keep a read | Verdict |
|---|---|
| The bytes, in the journal | Rejected. A line may read tens of megabytes. Each stop would write them to the kernel's store and each resume would read them back. File content would sit outside its mount, outside the mount's access rules, for a day after a delete. |
| The identity of the row, read again from the live file and refused if it changed | Rejected. A line that reads a file and then changes it, such as `sed -i`, could never be resumed. |
| A reference to the version seen, read from the mount | Chosen. An entry is about 180 bytes whatever the file's size. The body stays where its access rules are. The hash proves the bytes are the ones the line saw. |

What makes an old version readable: the write path keeps every replaced body whole in `vfs_versions`, a delete keeps the row and its body until the trash is swept, and nothing but that sweep removes a version. So the body cannot be found only when, between the stop and the resume, its file was deleted and swept, its mount was removed, or another caller moved it.

A resumed line's output can hold bytes its caller read before a right was taken away. It is the output the call would have returned had it not been stopped.

Reason: Temporal's history taught that values stored for replay are kept and shown for the life of the record, and that a reference resolved at the point of use is what keeps content out of it. The cost is a resume that can find a body gone.

### 8. The body is read through spec 5's `read_versions`, and this spec adds no seam

The first draft gave the storage a method of its own, `read_version`. It is withdrawn. One seam reads an old body, and it is spec 5's (its decision 5, "A rollback reads the files through two storage methods, `find_entries` and `read_versions`, and no public verb is added").

- For each open the host calls `read_versions` once, on the mount that holds the path, as the system authority, with one `VersionTarget`: the path of decision 7, the `version` and the `etag` the read reported, and no `holding`.
- The storage finds the row at the path, live or deleted, proves it is the entry by minting its etag at that version, and answers the version row with the smallest number at or above it, or the body the row holds now when there is none. That is spec 5's rule, and no etag is taken apart.
- The `content_hash` returned is compared on this side with the journaled one. A difference, or a `not_found`, counts as a body that cannot be found.
- A text body is used as its UTF-8 bytes, as the host encodes a read today (`host.py:392`).
- The host journals a read by reference only when the row carries an etag and its mount's storage declares spec 5's trait `versions` with the value `kept`. Any other read is journaled with its bytes.
- One fetch is three statements on the mount, or two when the row still holds the body, by spec 5's count.

Reason: ruling 8 of the reconciliation. Two methods that both read an old body would be two places for the rule of what a version row holds, and that rule is about to change for appends.

### 9. `vfs_job_replies` holds a journal as pages of at most 1 MiB, appended at each stop

| Column | Type | Holds |
|---|---|---|
| `job_id` | `String(32)`, as `vfs_jobs` keys a job | the job |
| `page` | integer | the page's number in the journal, from 0 |
| `body` | `LargeBinary`, at most `JOURNAL_PAGE_BYTES`, 1 MiB | a run of the journal's encoded bytes |

- The primary key is `(job_id, page)`. There is no other index and no foreign key. The table names no session.
- The journal's encoding is one entry to a line: a JSON array, UTF-8, ended by a newline. The pages of a job below `pages` in its line record, joined in order, are the journal.
- Each stop encodes the entries added since the last stop, cuts them into pages, and inserts them. A stop's first page is a new page, so no stored row is ever updated.
- `page` and `position` are counters. The next of each is kept in the line record, which only the holder of the job's claim writes, so no `next_number` is needed, as spec 0's decision 11 notes.

By the eight rules of spec 0's decision 22:

1. The table is added to `build_kernel_tables`. Its name begins with `vfs_job`, one of `KERNEL_TABLE_PREFIXES`. The landing adds one to `KERNEL_FORMAT_VERSION`.
2. Its statements are in a new module, `vfs.kernel_store.replies`.
3. No read verb writes to it, so nothing is written behind.
4. It stores no time. Its rows go when their job's `expires_at`, read against `store.now()`, has passed.
5. Pages are written with `insert_rows`, inside the `commit` that writes the job row.
6. A page is not a record beside a change to a file, so neither of spec 0's two forms applies. It is written in the `commit` that stores the job (spec 7, decision 6), before the call returns.
7. It has no kind written behind.
8. It has a sweeper, registered before spec 7's so that a job's pages go before its row. Each call issues one statement of fixed binds: `DELETE FROM vfs_job_replies WHERE (job_id, page) IN (SELECT r.job_id, r.page FROM vfs_job_replies AS r LEFT JOIN vfs_jobs AS j ON j.job_id = r.job_id WHERE j.job_id IS NULL OR j.expires_at <= :now LIMIT :limit)`. It removes the pages of a lapsed job and of a job whose row is gone.

- A resume reads a job's pages with one statement, in a `query`: `WHERE job_id = :id AND page < :pages ORDER BY page`.
- When a line finishes, its pages are removed by one statement, `DELETE FROM vfs_job_replies WHERE job_id = :id`, in a `commit` after spec 7's `finish`. A process that dies between the two leaves pages the sweeper removes.
- A cancelled job keeps its pages until the sweeper takes them.

Reason: a journal is only ever written at its end and read whole, in order. Rows per entry would cost a line of 10,000 requests 10,000 rows at its stop. Pages cost it one or two.

### 10. A journal is bounded at `JOURNAL_BYTES`, and a line past its bound cannot be stopped

- `JOURNAL_BYTES` is 16 MiB. It counts the journal's encoded bytes, standard input among them.
- It is a budget of the line. `journal_bytes` joins `LIMITS`, and a host sets it as it sets the others. Zero means the line records nothing.
- A line that passes it drops its entries, records nothing more, and runs on.
- If a step of that line then needs a person, the step is not done, the interrupt is not stored, and the line ends there. Its exit status is 137. Its error is `vfs.budget_exhausted`, with the detail `Budget("journal", 16777216): the line was given more replies than it may keep, so it could not be stopped for a step that needs a person; that step was not done`. Its result holds what the line had printed, as the result of any budget does.
- A line that was not recording when a policy interrupted it ends the same way, with "the line was not keeping its replies" in the detail.
- A stop the store cannot commit fails the step with `vfs.unavailable`, and the step has not run (spec 7, decision 6). Inside a line that is a refused verb: its command fails and the line goes on. The same holds when the stop meets a job of the same fingerprint that is `running` (spec 7, decision 26).

Reason: every reply a recording line is given is held in memory until it ends, so the hold needs a bound. Reads are references, so the bound is reached only by what has no stored version: standard input, listings, the output of host programs, and the stamps of decision 28. 16 MiB is the line's own output budget. Ending the line is what every other budget does, and it fails closed: a step a policy wanted judged is never run unjudged, and no later command runs on the belief that it was.

### 11. Every value the machine asks for is journaled as given, and the process id is an input

- A `value` reply is journaled as its text, whatever its name. A replay gives the same text and calls no clock and no random source.
- `pid` is in the line record. Every other process id is computed inside the machine from it and from the place of the subshell.
- A program that reads the host, such as `date`, asks through `value` when it is built, and is covered with no change here.

Reason: a value is the only thing a line is given that no store can give again. Roadmap decision D54 chose to record and replay these words, and this keeps it.

### 12. The order of requests inside a line is a function of its inputs, its replies and its build

- Stages of a pipeline, jobs run with `&`, and substitutions are tasks of one future. They are polled in a fixed order and never woken by anything outside it.
- Where a slice ends decides which task asks first, and it can decide how many requests are asked. A slice ends on a count of fuel. So the order is fixed by the line, the replies, the budgets and the build that counts the fuel.
- `fuel_slice` and every other budget are in the line record, and the build is in the build fingerprint.
- The journal is therefore keyed by position alone. No entry is matched across an order that moved.

Reason: the probes found the order equal in 36 replays and 52 resumes under one build and one set of budgets, and found it move when `fuel_slice` alone changed. Keying by the machine's key would let a replay run under another order, and the ninth request of the probe shows that another order can ask another set of requests.

### 13. A job carries the fingerprint of the build that ran it, and a resume under another build is refused before anything is claimed

- The binding exports `SHELL_FINGERPRINT`: a SHA-256, in hex, of the module's bytes, the version of wasmtime it was built with, and the binding's default `FUEL`, `FUEL_SLICE` and `MODULE_MEMORY_BYTES`. The build script takes the wasmtime version from the lock file.
- `line_fingerprint()` is the SHA-256 of `JOURNAL_FORMAT`, `SHELL_FINGERPRINT`, the sorted names of the library's programs and the sorted names of `PROGRAMS`. It is the `build` field of the line record.
- The line's kind compares the record's `build` and `format` with its own when it decodes the saved part, which `resume` does before it judges or claims (spec 7, decision 16, step 6). When either differs, the resume returns one `vfs.conflict`, not retryable, with the detail "the shell is not the build that stopped this line, so the line cannot be carried on from where it stopped; resume it from a process that runs that build, or cancel the job". The job is left `interrupted` and nothing is recorded.
- That a kind's decode may refuse is asked of spec 7 under "Needs no other spec meets yet". Until it is met the same check runs first when the kind carries the job on, and the job is finished with the conflict.
- The package's version is not in the build fingerprint.
- `JOURNAL_FORMAT` is raised by hand when the journal's encoding or the host's replay of an entry changes.

Reason: a new module, a new runtime or a new program table can walk another line, and DBOS shows that the honest answer is a classified refusal, not a stranded row or a silent second path. Leaving the package's version out keeps a job resumable across an upgrade that did not touch the shell. Checking before the claim lets a process of the old build still resume the job during a rolling deploy.

### 14. A resume starts a fresh machine and a fresh host, and answers from the journal until it runs out

The step loop is the one `run_line` has, entered inside `decisions.in_line(Line(line, cwd))` with the record's text and directory, so every step of the resumed line carries the `via` its first run carried (spec 6, decision 6). While the journal has an entry for the next position, the host answers from it:

| Entry | What the host does |
|---|---|
| `read`, `ref` | Registers the open as seeing that body. Takes the body from the bodies it holds, or fetches it by decision 8. Cuts the slice, and closes the open at the end of the file, as a live read does. |
| `read`, `data` | Gives the bytes. |
| `read`, `error` | Closes the open and gives the error, as a live refusal does. |
| `start`, `started` | Puts the program's writes where its feeds will take them, and answers `started`. |
| `feed` | Takes the next write, as a live feed does. |
| `write` | Gives the reply, and moves the writer mapping of spec 3's decision 18 as the first run's reply moved it, with the journaled etag. |
| `move`, `remove` | Gives the reply, and drops from that mapping what an accepted one drops. |
| anything else | Gives the reply as it is kept. |

- No verb is called through the line's routers. No policy is asked. No stamp is stored. No clock is read. The only calls on a mount are decision 8's fetches.
- An entry's `stamps` are shown to the line session's table, by decision 28.
- The output, the statuses and the fuel are produced again by the machine, and are the ones the line produced before.
- When the journal ends, the host's evidence is set from the record, and the next request is the one the line stopped at.
- The host and the machine are then in the state they were in at the stop, and the same loop goes on live.

Reason: this is Temporal's replay, with the journal as the history. Running the host's own code for an open and a feed rebuilds its state by the road that made it, so a stop in the middle of an open or between a start and its feed needs no state of its own saved. The probe stopped in both places.

### 15. Every replayed request is checked against its entry, and a mismatch refuses the resume with a conflict that names the step

- For each request, the host computes the digest and compares the key, the name and the digest with the entry at that position.
- The request asked when the journal ends is compared with `stopped` in the same way.
- A line that ends, or asks nothing, with entries left is a mismatch at the first entry not reached.
- A mismatch returns one `vfs.conflict`, not retryable. Its detail is "the line did not ask what it asked before: at step N it asked `write` at `0.1#3`, and its journal holds `read` at `0#2`; nothing more was run". Its `data` is `{"vfs.line": {"reason": "diverged", "position": N, "asked": {…}, "journal": {…}}}`.
- A body that decision 8 cannot find, or whose hash is another, returns one `vfs.conflict` at the file's path, with "the line read this file at a version that can no longer be read, so the line cannot be carried on from where it stopped", and the reason `version`.
- No kind is added. `vfs.conflict` is the kind that exists today.

What can cause a mismatch: a new module, runtime or program table, which decision 13 refuses first; a changed input, which decision 3 rules out by reading every input from the record; and a fault in the machine that makes a walk depend on something outside its replies. The check is for the third.

Reason: Restate's rule. A replay that does not match must stop before it runs anything live, because from that point the journal describes another line.

### 16. A resume that cannot replay ends the job with its refusal, and nothing of the line is run

The first draft left such a job as it was, by replaying before the claim. Spec 7 claims first: the claim is committed before a job is carried on (its decision 21). So this decision now reads:

- A refusal of decision 15 is found after the claim. The kind finishes the job with it, by spec 7's `finish`. Nothing was run and no file was changed.
- The result is a `LineResult` with `success` false, exit status 2, the one conflict, no output, and the job. A later `resume` returns it again (spec 7, decision 24).
- The deadline passing during the replay ends the line as a deadline ends any line: status 124, `vfs.timeout`, and what the replay had printed. The job is finished with that result.
- A build that differs is the one case found before the claim, by decision 13. That job is left `interrupted`.

Reason: both refusals of decision 15 are permanent. A journal that diverges will diverge again, and a version that was swept does not come back. A job that could never be carried on is better ended, with its reason stored, than left waiting for an approval that can do nothing.

### 17. The step the line stopped at is judged by spec 7's `resume`, and its outcome is delivered at its place in the walk

The first draft made the stopped step again as a public verb, after the replay. Spec 7's `resume` judges the saved step first, with the answer, before any job is carried on (its decision 20). So the order is: judge, claim, walk. The seven outcomes of that decision, for a line:

| The run reports | What happens to a line |
|---|---|
| The answer does not fit its schema | As for a step: the job is unchanged, and the result is `vfs.invalid`. |
| A stop, after or before the answer was used | As for a step: `stop_again`, with the new interrupt. The line is not walked and no page is written. This is a step that two policies each ask a person about. |
| Allow, after the answer was used | The job is claimed. The line is walked, and at the stopped place the step is carried out by spec 7's dispatch (its decision 22), through the line's guarded router. Its reply is journaled and the line goes on. |
| A denial by an answer | The job is claimed. The line is walked, and at the stopped place the step's result is the `vfs.interrupt.denied` refusal. The command fails, by decision 18, and the line goes on. |
| A denial by a policy | The job is claimed. The line is walked, and the step's result is spec 6's `vfs.permission_denied.policy` refusal. The command prints `Permission denied` and the line goes on. |
| Allow, and the answer was never used | The job is claimed. The line is walked, and the step's result is spec 7's `vfs.conflict` for an answer nobody asked for. The step is not run. The command fails, by decision 18, and the line goes on. |

- In the last three rows spec 7's decision 20 finishes a job of one step. Its decision 29 leaves a denial inside a line to this spec, and the claim in those rows is asked of spec 7 under "Needs no other spec meets yet".
- **How the outcome is delivered.** The resumed host knows the stopped place. For each verb call it is about to make it computes the place. The call at the stopped place, when its step has the canonical form of the saved step (spec 6, decision 21), is answered with the outcome and makes no second call. Every other call is made live.
- **A step that is carried out and refused all the same**, by a right taken away or by a file changed since the preview, fails its command as any refused verb does, and the line goes on.
- **`cmd || fallback`** runs the fallback after a denial, and `set -e` ends the line as it does for any failed command.
- **A cancel** is spec 7's decision 29: one update, and no walk. The result is a `LineResult` with status 130, the `vfs.interrupt.cancelled` entry, and no output. What the line did before it stopped stands.

Reason: one judging of a stopped step, in one place, is spec 7's, and a line must not judge it a second time. A denial is a refused step and a cancel is the end of the job, as the guide says, and inside a line a refused step is a failed command.

### 18. A denial reaches the machine as a refusal with its own words, and its command exits as it does for `Permission denied`

- The wire gains one reply kind, `denied`, whose value is the words. The Python host gives `("denied", words)`.
- In the machine, `HostError` gains `Denied` with the words, and stops being `Copy`. Every place that matches a refusal treats `Denied` as it treats `PermissionDenied`, and prints the words where it prints `Permission denied`. Spec 3's decision 17 adds two members of its own, for its two refusals.
- The words are the entry's message, an em dash, and its hint as the renderer composes it (spec 7, decision 27): `Denied by <name> — This step needed approval, and <name> denied it. Reason: <reason>`. They hold no path and no retry class.
- So `rm` prints `rm: cannot remove '/contracts/acme.md': Denied by <name> — …` and exits 1. A redirection prints `bash: line 1: /contracts/acme.md: Denied by <name> — …` and its command exits 1. `sed -i` exits 4 and `ls` exits 2, as each does for `Permission denied` today.
- A host program prints the same words through the road it has, `name: path: reason`, and exits 1.
- The refusals the host words are named in one table in `host.py`, `WORDED_REFUSALS`. This spec puts two in it, the two a resume itself makes: `vfs.interrupt.denied`, and spec 7's `vfs.conflict` for an answer nobody asked for, whose `data` names its job. Every other kind keeps the code it maps to, which for `vfs.permission_denied.policy` is `permission_denied`, by spec 6's decision 14. Spec 6 may add its kind to the table, and its command then prints the policy's reason with nothing else here changed.
- The fact is kept among the line's warnings, as every refusal inside a line is.

Reason: the guide says a denied command prints that the principal denied it, and that a denial is not a missing right. The machine's eight texts cannot say so. One new reply is the smallest change that can.

### 19. A host program that is stopped is started again from its first verb

- A step inside a host program has the place of its `start` request and the count of verb calls the program had made: `12.2` is the third verb of the program started at position 12.
- When that step is interrupted, the `start` request has no reply and no entry. The resume reaches it live and runs the program again from its start. When the program makes the call at the stopped place, decision 17 delivers the outcome there.
- A law holds for every name in `PROGRAMS`: a host program makes at most one change, and no verb call follows it. So a program that is started again repeats reads and never a change.
- If the program takes another road the second time, and makes another step at that place or none, the outcome is not delivered. Whatever step it does make is judged live, as any step is.

Reason: a program's verbs before its change are reads, and a read done twice changes nothing. Journaling a program's verbs one by one would add a second journal inside the first for a case the law rules out. A tool is not a host program, and its rules are spec 7's decision 38.

### 20. A line stops once for each interrupt, at the first request that needs a person

- The requests one pass of the step loop returns are answered in order. The first whose verb comes back interrupted ends the loop. The requests after it in that pass are not answered and have no entry.
- The replies given before it in that pass are in the journal.
- On the resume the machine asks the same requests in the same order. The earlier ones are answered from the journal, the stopped one with its outcome, and the later ones live.
- Two stages of a pipeline that each need a person stop the line twice, one after the other.

Reason: ruling 4 of the overview. A job has at most one interrupt waiting.

### 21. A line that stops again appends to its journal, and each resume walks the line from its start

- Each stop writes only the entries added since the last one. A resumed line that stops again moves from `running` back to `interrupted`, by spec 7's `stop_again`.
- Each resume replays the whole journal. Its cost is the machine's work up to the stop and one fetch for each open before it.
- A line with `n` stops is walked `n` more times. When the stops are spread evenly through it, that is about `n / 2` runs of the line beside its own.
- No machine is kept in memory between a stop and its resume.

Reason: the journal is the truth and a kept machine would be a cache of it. A cache helps only a resume in the same process within moments, and a person answers in minutes, from any process. Temporal keeps such a cache and still replays on every miss.

### 22. The result that ends a line holds the line's whole output, and an interrupted result holds none

Every result of a line is a `LineResult`, whose `ops` is `("cli",)`, from `cli` and from `resume` alike (spec 7, decision 16).

| Result | `success` | `interrupted` | `exit_code` | `stdout`, `stderr`, `statuses` | `errors` |
|---|---|---|---|---|---|
| The line stopped | false | true | 126 | empty | spec 7's one entry of kind `vfs.interrupted` |
| The resumed line stopped again | false | true | 126 | empty | the same, for the new step |
| The resumed line ended | as for any line | false | the line's | everything from the line's first command | the line's warnings, from before and after every stop |
| The line was cancelled | false | false | 130 | empty | spec 7's one entry of kind `vfs.interrupt.cancelled` |
| The resume could not replay | false | false | 2 | empty | the one conflict |
| The answer did not fit, or the caller may not resume | false | false | 2 | empty | spec 7's refusal |

- `fuel_used` is the fuel the machine had spent when the call returned. For a line that ended, it is the fuel of a run never stopped.
- `job` is the line's `Job` on every row, with `kind` `line`, and `verb` and `path` those of the step the line is stopped before.
- The text of an interrupted result prints no output and the one entry, in spec 7's words. It names no job and no resume.
- A resumed result is not a tail. A host hands it to its agent as the answer to the line.
- **The stored copy.** A finished line stores its result for a second `resume`, as spec 7's decision 24 has it, under `JOB_RESULT_BYTES`. A result over that bound is stored without `stdout` and `stderr`: its exit status, its statuses, its errors, and one warning of kind `vfs.budget_exhausted.truncated` that says the output of this line is not kept and how many bytes it was. The first `resume` returns the whole result, from memory.

Reason: the guide says the result of a resume is the one the call would have returned, and that an agent only ever sees that one. Output given once, by the result that ends the line, cannot be shown twice. 126 is the shell's status for a command that was found and could not be run, which is what "not approved" means to whoever reads it. A cancel walks nothing, so it has no output to give.

### 23. The machine's budgets are counted once, and the deadline is each call's own

- Fuel, memory, loop iterations, function depth, nesting, output bytes and the parse budgets are counted inside the machine. A replay counts the same work again in a fresh instance and reaches the stop with the same counts. So a line that is stopped may do exactly what a line never stopped may do.
- A verb budget counted by the machine is covered the same way.
- The host's CPU is spent again on every resume, for the work up to the stop.
- The deadline is not saved. The first call and each resume get `DEADLINE_SECONDS` of their own, and a resume's deadline covers its replay. A line's deadline is 30 seconds and spec 7's lease is 300, so a resume that is alive never outlives its claim.
- A resume whose caller is cancelled after the claim leaves the job `running`, as spec 7's decision 23 has it. Decision 29 says what the next resume finds.
- A resume takes a turn among the lines a router runs at once, as a new line does.

Reason: a budget that is a count is a function of the line, so it needs no saving. A clock is not, and the overview keeps clocks out of what is stored. The time a person takes to answer is no part of a line's work.

### 24. A resumed line runs as its caller, in the session and turn it started in, and its stamps cross the stop

- Every verb after the replay is called with the authority the saved part holds, judged as it stands at the resume.
- A line run through a stored session has `session_key` and `turn_number` on its job. The resumed host is given that session's guarded router, for that turn, in whichever process resumes it (spec 7, decision 34). Its stamps were stored as it read, and are there.
- A line run with no session has a line session (spec 3, decision 16). Spec 3 never stores it. Decision 28 journals what it was shown and rebuilds it at the resume.
- A replayed read is no call of a verb, so it stores no stamp.
- A stopped line changes none of its session's shell state. The resumed line stores its state when it ends, in the turn it started in (spec 4, decision 10).
- A line never runs as the system authority, so a line's job is never a system job.

Reason: the guide says a resumed line runs as whoever started it, with that caller's access as it stands. A bare line that read a file, stopped, and then wrote it back must still be guarded, and must not be refused as unread.

### 25. A line made again runs again, and joins its waiting job at its first stop

The first draft stored a second job. Spec 7's record joins a call made again to its waiting job (its decision 26), and its decision 37 puts a line's fingerprint over the line's own inputs. So this decision now reads:

- The `fingerprint` of a line's job is `sha256("vfs.job.1" NUL owner_key NUL session_key or "" NUL "cli" NUL d)`, where `d` is the SHA-256 of the line's text, `cwd`, `env`, `name`, `args`, `pid`, `limits`, `fuel` and the SHA-256 of its standard input, each preceded by its length. It is computed only at a stop.
- `cli` called again with the same inputs, by the same caller in the same session, runs the line from its start. Nothing is looked up when it starts.
- When that second run reaches a stop, the insert finds the first job on the unique index and joins it. The call returns the first job's interrupted result. The second run's journal is dropped.
- The commands the second run made before its stop ran a second time. Only the job is one.
- A host whose code may run again, such as a LangGraph node, asks its session for a waiting job before it runs a line, and resumes that job.

Reason: finding a waiting job when a line starts would cost a statement at the start of every line, which decision 4 forbids. Joining at the stop costs nothing more than the insert, and it keeps a second job from waiting for an answer that, once given, would run the rest of the line twice.

### 26. Three landings, in this order

1. The machine and the binding: the `denied` reply, `SHELL_FINGERPRINT`, and the replay law in the crates' tests.
2. The journal: `journal.py`, recording and replay in the host, driven in tests by a stand-in for a policy, and the use of `read_versions`. After spec 1's etag, spec 3's first landing and spec 5's first landing.
3. The kernel: `vfs_job_replies`, the line's kind, `cli` and `resume` joined to spec 7, the faces, and the guides. After spec 7's third landing.

Reason: each leaves the tree green. The first needs nothing from the other eight specs, and the second needs no job, so both can be built while spec 7 is.

### 27. A line is one kind of spec 7's job, and its kind is one object

`LineKind`, in `vfs.kernel_store.replies`, is the object spec 7's decision 37 asks for.

| What spec 7 asks | What the line's kind does |
|---|---|
| It encodes what it saves | Returns the `line` key of the saved part, by decision 3, and the rows of the new pages for `vfs_job_replies`. |
| It decodes it | Checks the record against its pydantic model, and its `build` and `format` by decision 13. |
| It carries a claimed job on | Decision 29's check, then the walk of decisions 14 to 17, then `stop_again` or `finish`. |

- **How a stop reaches it.** `run_line` sets one context variable, `journal.running`, to the line that is running, for the length of the line: its journal, its inputs and the place of the verb call the host is making. It is set beside `decisions.in_line`. A verb whose judging reports a stop reads it. When a line is running, the job that is stored is of the kind `line`, its place is the place read there, and its `fingerprint` is decision 25's.
- **The first stop** is spec 7's `store_job`, with the pages in the same `commit`. **A later stop** of a resumed line is its `stop_again`, with the new pages in the same `commit`.
- The verb returns spec 7's interrupted result to the host. The host ends the step loop and `run_line` returns the `LineResult` of decision 22.
- That `store_job` and `stop_again` take a kind's rows and a running line's place is asked of spec 7 under "Needs no other spec meets yet".

Reason: spec 7's decision 37 gives the record, the states and the claim to every kind, so `resume`, `jobs`, a session's calls and the sweep need no second road for a line. A context variable is how spec 6 already tells a verb that a line made it.

### 28. What a bare line was shown is journaled with each entry, and the replay shows it again

- A line session's table is in memory and is never stored (spec 3, decision 16). At a stop it would be lost, and the resumed line's first write to a file it had read would be refused as unread.
- While a bare line records, the host wraps the line session's table in one that notes each `show` and each `change` the guarded router makes on it, through the interface of spec 3's decision 19. The notes made while a request is answered are that entry's `stamps`: for each, which of the two it was, and the stamp's fields as spec 3's decision 4 has them.
- On replay, each entry's `stamps` are made again on a fresh table, in order. When the journal ends the table holds what it held at the stop.
- A line run through a stored session journals no `stamps`. Its stamps are rows of `vfs_session_stamps` already.
- A listing stamps at most 1,024 rows (spec 3, decision 3), so an entry's `stamps` are bounded by that, and they count toward `JOURNAL_BYTES`.
- The writer mapping of spec 3's decision 18 is rebuilt for both kinds of line, by decision 14, from the etag each `write` entry keeps.

Reason: the stamps of a bare line are a function of the results its verbs returned, and those results are not kept. Journaling what the table was shown, and nothing else, rebuilds the table by the one interface spec 3 gives it, with no stamp rule written twice.

### 29. A line claimed a second time is not walked again

- Spec 7's lease lets a job left `running` be claimed again after 300 seconds, and a job of one step is then carried out again under its etag guard (its decision 23). A line has no such guard: an append made after the stop would be made twice.
- When the line's kind is handed a job whose `attempts` is more than one, it walks nothing. It finishes the job with a `LineResult` of status 1 and one `vfs.conflict`, with `data` holding the job id and `in_doubt: true`, and the detail: an earlier resume of this line stopped before it recorded its result, so the line may have run past the step it was stopped at; nothing was run again; read the files before running the line again.
- This is what a resumed line gets when its process died, or its caller was cancelled, after the claim.

Reason: after the claim a line's replies are in memory again, as before its first stop. A second walk would know what the line did up to its last stop and nothing after it. Refusing is the one answer in which nothing runs twice.

## Cost

Costed against the reference deployment in the working agreement.

**Per verb call, about 150,000 a day.** A line no policy applies to pays nothing: no entry, no hash, no statement. A line a policy applies to pays, for each request, one SHA-256 over the request's arguments and one entry in memory of 110 to 180 bytes, and for a bare line the stamps of decision 28, about 100 bytes for each row it was shown. It issues no statement for them. A direct verb pays nothing.

**Per file write, per index visit, per batch.** Nothing is added.

**A stop.** Spec 7's insert of the job row, its pages of the saved part when the stopped step is over 64 KiB, and one `insert_rows` of journal pages, in one `commit`. At the bound of 16 MiB the journal's insert is two statements. The bytes are the record, about 1 KB beside the line's text, and the entries. A line that read 50 MB in 800 chunks stores about 150 KB.

**A resume.** Spec 7's statements for the read, the judging and the claim. Then one `SELECT` of the pages, one call of `read_versions` for each open the line made before the stop, which is two or three statements on its mount, and the machine's work up to the stop, which the fuel budget bounds at about five seconds. Then the stop's cost again, or spec 7's `finish` and one `DELETE` of the pages.

**A line with `n` stops.** `n` inserts, `n` selects, and about `n / 2` walks of the line.

**Memory.** At most `JOURNAL_BYTES` for each running line a policy applies to, and the bodies a replay holds under `READING_BYTES`, as a live line holds them.

**The day.** How many lines are stopped is an assumption: no measurement exists. At one line in a hundred of the agent calls, 1,500 stops a day write about 6 MB, and each is removed when its line ends. The table holds the pages of the jobs that wait or were cancelled, for at most the job lifetime of 24 hours.

**The sweep.** One statement of two binds for each call of the sweeper. Its subquery reads `vfs_job_replies`, which holds at most about 22 rows for a job.

**Per lock.** A stop inserts rows under one job's id and holds them for the length of a commit. No reader waits on them, and no other job touches them. On SQLite the kernel's store is its own file, and a stop is one small transaction on its one writer. `read_versions` is a plain read.

## Left as it is

- **Recovery after a process dies in the middle of a line.** Before a first stop it is a failed call. After a resume it is decision 29's refusal. Writing entries as they are made would allow a recovery, and decision 4 says why it is not done.
- **A machine kept between a stop and its resume.** Decision 21.
- **A redirection of a program's output is two steps.** The machine sends the truncating write when the file opens. Under a policy on that path the line stops twice. A change that made a redirection one step is the shell's, and no spec for it is written.
- **One writer can send its opening write twice.** The probe's ninth request is a second truncating write of one file, sent by another task while the first was still waiting for its reply. A task that ends flushes every writer the line holds (`exec.rs:1919-1925`), and a writer counts as unwritten until its first reply arrives (`files.rs:190-192`, `:220`). It does not break a replay. It is one more step for a policy to judge. It is a defect of the shell, outside the nine specs, and it needs a spec of its own.
- **Tools.** A tool in a line, and a tool that asks, are left out of the nine.
- **A view of a journal in the namespace,** and any way to read one entry by SQL.
- **The words of an interrupted result,** the states of a job, the claim, the lease and who may resume. They are spec 7's. The words a line's interrupted result carries when earlier commands of the line ran are spec 7's to own, by the reconciliation.

## Tests

Each is written and seen failing before the code. Counts are of statements recorded by a `before_cursor_execute` listener on the kernel's store and on the mount, of calls to a spied function, of rows, and of exit statuses. Never of time.

In the crates:

- `crates/vfs-shell/tests/laws.rs::a_line_fed_its_recorded_replies_by_position_asks_the_same_requests`: over a table of lines with pipelines, `&` and `wait`, substitutions and loops, a second machine fed the first one's replies asks an equal list of keys and requests and prints equal output. Zero mismatches.
- `crates/vfs-shell-wasm/tests/module_laws.rs::a_replayed_line_asks_in_the_same_order_and_spends_the_same_fuel`: the same on the module, with slices ended by fuel. The two fuel counts are equal.
- `crates/vfs-shell/tests/laws.rs::a_denied_reply_prints_its_words_and_exits_as_permission_denied`: for a redirection, `cp`, `mv`, `rm`, `mkdir`, `touch`, `tee`, `cat`, `ls` and `sed -i`, the status under `Denied` equals the status under `PermissionDenied`, and the words are on standard error once.
- `crates/vfs-shell-wasm/tests/wire_roundtrip.rs::a_denied_reply_crosses_the_wire`: one `denied` reply encodes and decodes to itself.
- `tests/test_native.py::test_the_shell_fingerprint_is_exported`: 64 hex characters, equal on two reads.

`tests/shell/test_journal.py`:

- `test_a_request_digest_is_pinned`: one golden digest for each of the twelve requests.
- `test_entries_encode_and_decode_to_themselves`: every kind of payload, with bytes that are not UTF-8, with `stamps` and without.
- `test_a_journal_past_its_bound_drops_its_entries`: with `journal_bytes` at 200, the journal holds 0 entries after the request that passes it.
- `test_a_stored_journal_of_this_format_still_decodes`: a fixture file decodes to a pinned list.
- `test_a_lines_job_fingerprint_is_pinned`: one golden value of decision 25's digest, and another for a line that differs in one input.

`tests/shell/test_host.py`:

- `test_a_line_no_policy_applies_to_records_nothing`: `request_digest` is called 0 times.
- `test_a_replay_calls_no_verb`: a host given a journal answers every entry with 0 calls to any method of either router.
- `test_a_replay_rebuilds_an_open_and_a_feed`: a journal that ends inside an open and after a `started` entry; the next live `read` and `feed` return the bytes a line never stopped gets.
- `test_a_replay_rebuilds_a_bare_lines_stamps`: a bare line reads two files and lists a directory, then its journal is replayed on a fresh host; the fresh table answers `look up` for each of the paths as the first table did. Counted: the paths, and 0 calls of a verb.
- `test_a_replay_rebuilds_the_writer_mapping`: a journal with an accepted truncating write; the next live append of that writer is sent with the journaled etag as `if_match`.
- `test_a_replay_follows_the_lines_own_move`: a journal with a read of `/a` and an accepted move of `/a` to `/b`; the fetch names `/b`. One call of `read_versions`.
- `test_a_replayed_request_that_differs_names_its_step`: an entry with another digest; one `vfs.conflict` whose `data` holds that position.
- `test_a_line_that_ends_with_entries_left_is_a_mismatch`: a journal with one entry more than the line asks; one `vfs.conflict` whose position is that entry's.

`tests/shell/test_programs.py`:

- `test_a_host_program_makes_at_most_one_change_and_makes_it_last`: for each name in `PROGRAMS` over a table of arguments, a spy counts at most 1 changing verb and 0 verbs after it.

`tests/shell/test_line_jobs.py`, through the kernel, on SQLite. The first, the fourth and the last are also to be run on the Postgres leg:

- `test_a_line_that_is_not_stopped_stores_nothing`: with a policy that allows every step, 0 statements on the kernel's store and 0 rows in `vfs_jobs`, `vfs_job_pages` and `vfs_job_replies`.
- `test_a_stop_writes_the_job_and_its_pages_in_one_commit`: one `INSERT` into `vfs_job_replies`, one row, one commit, and a row of `vfs_jobs` whose `kind` is `line`.
- `test_a_line_with_cp_stops_once_and_its_note_is_written_once`: the guide's line with `cp`; `/notes.md` holds one line and is at version 1 after the resume.
- `test_a_resumed_line_equals_one_never_stopped`: the probe's lines, stopped before every change; equal `stdout`, `stderr`, `statuses`, `exit_code` and `fuel_used`, and an equal list of changing calls.
- `test_no_public_verb_that_changes_anything_is_called_during_replay`: between the claim and the end of the journal, 0 calls of a verb through the line's routers, 0 `INSERT`, `UPDATE` or `DELETE` on the mount, and `read_versions` called once for each open.
- `test_a_redirection_of_a_programs_output_stops_twice`: `cat a > b` under a policy on `b` returns two interrupted results.
- `test_a_line_stopped_three_times_appends_three_runs_of_pages`: 3 inserts and 0 updates on `vfs_job_replies`, and the job's `state` goes `interrupted`, `running`, `interrupted` twice over.
- `test_a_read_is_journaled_as_a_reference`: a line reads 5 MiB and stops; its pages hold under 4,096 bytes.
- `test_a_read_replays_from_the_version_it_saw`: a line prints a file, overwrites it and stops; the resumed output holds the first body.
- `test_a_version_that_is_gone_ends_the_job`: the file is deleted and swept; one `vfs.conflict` at its path; the job is `finished`; 0 changes; a second `resume` returns the same result with 0 writes.
- `test_a_resume_under_another_build_is_refused_before_the_claim`: with `line_fingerprint` patched, one `vfs.conflict`, 0 writes on the kernel's store, the job still `interrupted`.
- `test_a_denial_fails_one_command_and_the_line_goes_on`: the statuses of decision 18; the words on standard error; `cmd || fallback` runs the fallback; one warning of kind `vfs.interrupt.denied`; `success` true; the job `finished`.
- `test_a_policy_that_now_denies_fails_the_command_and_the_line_goes_on`: `Permission denied` on standard error, one warning of kind `vfs.permission_denied.policy`.
- `test_an_answer_nobody_asks_for_fails_the_command_and_the_step_is_not_run`: the policy is removed before the resume; the step's file is at its old version; the line's later command ran.
- `test_a_cancel_ends_the_job_and_walks_nothing`: status 130, kind `vfs.interrupt.cancelled`, empty output, 0 machines started, the next command's file absent.
- `test_a_value_replays_as_given`: with `_value` spied, a line that prints the time, stops, and prints it again calls it twice in all, and the resumed output holds the first value.
- `test_two_stages_that_each_need_a_person_stop_one_at_a_time`: two interrupted results, one interrupt each.
- `test_a_step_two_policies_ask_about_stops_twice_and_writes_no_second_page`: 2 interrupted results, 1 `INSERT` into `vfs_job_replies` in all, and 0 machines started by the first resume.
- `test_a_line_past_its_journal_budget_ends_at_the_step_that_needs_a_person`: exit 137, `vfs.budget_exhausted`, the step's file at its old version, 0 rows stored.
- `test_an_interrupted_result_holds_no_output_and_names_no_job`: empty `stdout`, `stderr` and `statuses`; `exit_code` 126; `ops` is `("cli",)`; the text holds neither "resume" nor "job".
- `test_a_budget_is_counted_once`: with `loop_iterations` at N, a line of N iterations with a stop in the middle ends with status 0, and one of N + 1 ends with 137, as each does when never stopped.
- `test_each_call_gets_a_deadline_of_its_own`: `Deadline.after` is called once for the call and once for the resume, each with `DEADLINE_SECONDS`.
- `test_a_resumed_line_runs_as_its_caller`: every router call after the replay carries the saved authority and `via` equal to `Line(text, cwd)`; a right revoked before the resume fails the step with status 1.
- `test_a_bare_lines_stamps_cross_the_stop`: `cat f`, a stop, then `sed -i` on `f` ends with status 0; with a rival's edit of `f` during the wait, the `sed` is refused as changed and `f` keeps the rival's body.
- `test_a_stopped_host_program_changes_once`: `edit` under a policy; after the approval the file is one version on.
- `test_a_line_made_again_joins_its_job_at_the_stop`: 1 row in `vfs_jobs`, the same job id on both results, and 0 statements on the kernel's store before the second run's stop.
- `test_a_line_claimed_a_second_time_is_not_walked`: a job left `running` with its lease ended; the resume starts 0 machines, calls 0 verbs, and returns one `vfs.conflict` with `in_doubt` true.
- `test_a_large_result_is_stored_without_its_output`: a line that prints 2 MiB; the first `resume` returns it whole; the second returns status and errors and one `vfs.budget_exhausted.truncated` warning.
- `test_the_sweeper_takes_a_lapsed_jobs_pages_before_its_row`: after the clock passes `expires_at`, one pass leaves 0 rows in both tables; and pages whose job row was removed by hand are taken too.
- `test_a_line_of_10_000_requests_stops_in_one_insert`: a loop of 10,000 `stat` requests and then a stop issues 1 `INSERT` into `vfs_job_replies`, of 2 rows at most. Marked `slow`.
- `test_another_process_resumes_the_line`: two kernels over one SQLite file, and the synchronous face; equal output.

The docs gate runs every block of Step 7 of the interrupt guide, as changed below.

## Scope

In:

- `crates/vfs-shell/src/machine/` (`Reply`, `HostError`, every place that matches a refusal, `files.rs`), `crates/vfs-shell-wasm/src/wire.rs`, `crates/vfs-core/src/shell_binding.rs`, `python.rs`, `build.rs`, and `src/vfs/_native.pyi`.
- `src/vfs/shell/journal.py`, new: `Journal`, `LineRecord`, the running line and its context variable, `request_digest`, the encoding, the recording table of decision 28, `line_fingerprint`, `JOURNAL_FORMAT`, `JOURNAL_BYTES`, `JOURNAL_PAGE_BYTES`. It imports nothing from `vfs.storage` and nothing from `vfs.kernel_store`.
- `src/vfs/shell/host.py`: recording, the replay road of `answer`, the delivery of an outcome at its place, `journal_bytes` in `LIMITS`, and `etag` and `version` in the columns a read asks for.
- `src/vfs/kernel_store/replies.py`, new: the table, its statements, its sweeper, and `LineKind`.
- `src/vfs/base.py`: `cli` returning a stop's result, and the routing of `read_versions` for a replay. `sync.py`, `session.py` and `sync_session.py` for the same.
- The tests above and the docs below.

No storage method is added. No public name is added: `LineResult` exists, and `journal_bytes` is one more name in `LIMITS`.

Out: everything under "Left as it is", and every table and name another spec owns.

The landings are decision 26's three. Each is green alone.

## What the docs must say

- A line that stops keeps what it did, and a resumed line returns the whole of what the line printed, from its first command.
- VFS keeps the line's text, its standard input, its environment and its replies while the job waits. A file's content is not copied: the line's reads are kept as pointers to the versions it read. A host that puts a secret in a line's text or environment has it stored for the job's lifetime.
- A resume is refused with a conflict, and nothing is run, when the shell is another build. The job still waits: resume it from a process of the first build, or cancel it.
- A resume ends the job with a conflict, and nothing is run, when the line no longer asks what it asked, or when a file the line read was deleted and swept or was moved by another caller.
- A denied command prints who denied it and exits as it does for `Permission denied`.
- A cancelled line returns status 130 and no output. What it did before it stopped stands.
- A resumed line whose process died is not carried on again. Its job ends with a conflict that says the line may have run past its stop.
- A line that was given more than 16 MiB of replies that have no stored version cannot be stopped. A step of it that needs a person ends the line.
- A redirection of a program's output, `cmd > file`, is two changes to `file`, and can stop twice.
- `cli` made again runs the line again. If the first call's job still waits, the second call joins it when it reaches a stop, and the commands before the stop have then run twice. Code that may run again asks its session for a waiting job first.
- Each resume walks the line from its start, so a line with many stops costs more than one with few.

Pages: Step 7 of `documentation/how-to/interrupt-a-job-and-ask-a-person.md`; the docstrings of `cli` and `LineResult`; the `LIMITS` docstring for `journal_bytes`; the LangGraph section of the interrupt guide for a line; a Maintainers page for the journal's format and the build fingerprint.

## Earlier decisions this reverses

- **Roadmap D60** leaned to saving the machine's memory. Ruling 2 ended that, and this spec builds the other answer.
- **Decisions 18 to 23 of the earlier interrupt draft.** Memory pages, the module hash on the row, `in_doubt` as an ask of the host, and status 75 for a stopped line are all replaced. The status is 126.
- **Roadmap D41** recorded effects, the reads a walk depends on, and the identity of every other read, and read the rest again from the live file under a hash check. Every reply is now journaled, and a read is fetched at the version it saw, never from the live file as it now is.
- **Roadmap D40** drained a pipeline before stopping, so that questions raised together were shown together. A line now stops at the first.
- **Roadmap D43** gave a run a ledger of 64 MiB and evicted the oldest run. A journal is 16 MiB for one line, and nothing is evicted.
- **Roadmap D46** left a step in doubt after a crash and asked the host to say done or redo. A line whose resume died is ended by decision 29, and the host is told and not asked.
- **Roadmap D54** stands: the shell's words that are not functions of the line are recorded and replayed.
- **Roadmap F3 criterion 10 and H4.** The determinism law stands, with decision 5's digest in place of an earlier fingerprint. H4's step rows in an action log, its `/.vfs/jobs` view and its `answer` verb are not built by this spec.
- **This spec's own first draft.** Decision 8 no longer adds a storage method. Decision 16 no longer leaves a job that cannot replay as it was. Decision 17 no longer replays on a cancel, and no longer judges the stopped step itself. Decision 25 no longer stores a second job.

## Choices for the owner

Each is decided above, and is listed here because it is the owner's to change.

1. **A read is kept as a reference, not as bytes** (decision 7). It costs a resume that fails when a version was swept or a file was moved by another caller.
2. **The journal's bound is 16 MiB, and a line past it ends at a step that needs a person** (decision 10). The other answer refuses that one step and lets the line go on.
3. **An interrupted line's exit status is 126** (decision 22). The earlier draft used 75.
4. **An interrupted result holds no output** (decision 22). The other answer holds what the line had printed, and a host must then cut it from the resumed result.
5. **A cancelled line returns no output** (decisions 17 and 22). The other answer walks the line to its stop to rebuild what it printed, and needs the job's result composed by a walk where spec 7 composes it from the row.
6. **The guide's line uses `cp`** (below). The other answer is a change to the shell so that a redirection is one step.
7. **Each call gets a deadline of its own** (decision 23).
8. **The build fingerprint leaves the package's version out** (decision 13), so a job outlives an upgrade that did not touch the shell.
9. **A line made again runs again and joins at its stop** (decision 25). The other answer looks for a waiting job when a line starts, at one statement a line.
10. **A resumed line whose process died is ended, not walked again** (decision 29).
11. **Inside a line, an answer nobody asks for fails its command and the line goes on** (decision 17). The other answer ends the line there, as it ends a job of one step.

## Where this spec disagrees with the overview or the guides

1. **Step 7 of the interrupt guide stops twice, not once.** Its line holds `cat /drafts/acme.md > /contracts/acme.md`. Run: the machine sends a write of 0 bytes that truncates `/contracts/acme.md`, then a `stat` and a `read` of the draft, then a write of 27 bytes that appends. Both writes are changes under `/contracts`, so the policy interrupts both, and the first is a change that empties the contract. The change proposed: the guide's line uses `cp /drafts/acme.md /contracts/acme.md`, which is one `copy` request (run), and the guide says in one sentence that `cmd > file` is two changes.
2. **The guide's Step 7 names one cause of a refused resume, a shell that changed.** There are two more: a file the line read was deleted and swept, or was moved by another caller. The change proposed is the fourth sentence under "What the docs must say".
3. **The guide says that had the principal cancelled the job, "the line would have stopped there".** It says nothing of the result. The change proposed: one sentence that a cancelled line returns no output.
4. **The guide's LangGraph section says a call made again returns the waiting job "rather than starting a second one".** For a line the second call runs the line's earlier commands again before it joins. The change proposed is the tenth sentence under "What the docs must say".
5. **The overview says `vfs_job_replies` holds the journal of a line's replies, in order.** It holds that journal as pages, and the line's standard input as the journal's first entry, so that no row of `vfs_jobs` grows with it.

The first draft's point about the words "so nothing was changed" is settled by the reconciliation: spec 7 owns the words for a line whose earlier commands ran.

## Needs no other spec meets yet

Each names the spec that should meet it and the text its decision would need.

1. **Spec 7, decision 37, "A line's job uses the same record, states and claim, and spec 8 supplies what is saved and how it is carried on".** "When a line is running (`journal.running` is set), a stop is stored as a job of the kind `line`. `store_job` and `stop_again` take the place of the step from the running line, take the fingerprint from its kind, and write the rows the kind hands them for `vfs_job_replies` in the same `commit` as the job row."
2. **Spec 7, decision 20, "A resume runs the policies again with the answers the job has, and the run ends in one of seven ways".** "For a job of the kind `line`, a denial by an answer, a denial by a policy, and an allow whose answer was never used do not finish the job. The job is claimed as an allow claims it, with the answer recorded by the same rule, and the refusal is handed to the kind as the result of the stopped step."
3. **Spec 7, decision 16, step 6.** "A kind's decode may refuse. `resume` then returns that refusal, claims nothing and records nothing." Without it, decision 13's check runs after the claim and ends the job.
4. **Spec 7, decision 22, "The saved step is carried out as its caller, with rights judged again, and with the etags the preview saw as `if_match`".** "The dispatch takes the router it calls. For a line the kind passes the line's guarded router, so that the step's result refreshes the line's stamps and its writer mapping."
5. **Spec 7, decisions 16, 24 and 29.** "A kind makes the result `resume` and the first call return from the entry this spec built, and encodes the result that is stored. For a line it is a `LineResult`, by spec 8's decision 22."
6. **Spec 3, decision 16, "A bare line is a strict session of its own, and it is never stored", and decision 19.** "The table's `show` and `change` take values that turn into JSON and back, so that spec 8 can journal what a line session was shown and show it again to a fresh table when the line is resumed." And, for a line of a stored session: "A guarded router is made from a session key and a turn number alone, with no handle in memory", which spec 7's decision 34 also needs.

What the other specs ask of this one is met. Spec 5 asks that each `read` entry hold the row's version beside its etag and its hash, and that the body be fetched by its `read_versions` as the system authority: decisions 7 and 8. Spec 6 asks that a step a replayed line makes carry the same `via` as the first run: decision 14. Spec 6 also asks that the reply `denied` be able to carry a policy's reason: decision 18 keeps the kinds it words in one table that spec 6 may add its kind to. Spec 7's decision 37 asks for the fingerprint over the line's inputs, the place of a step, and the registration of `vfs_job_replies` with the sweep: decisions 25, 19 and 9. Spec 4's decision 12 leaves the pages of a cancelled job to this spec's rule: decision 9. Spec 5 asks that this spec build on its landing: decision 8.

## Not checked

- **The other eight specs were read once, while each was being revised.** Every name taken from them is as it stood then. Spec 7 had not yet taken in the reconciliation when it was read.
- **Any engine but SQLite in memory.** No statement here was run on Postgres, and the kernel's store does not exist yet. To run: `tests/shell/test_line_jobs.py` on the Postgres leg, above all the sweeper's statement with its row-value `IN` and its `LIMIT` in a subquery.
- **Spec 5's `read_versions`.** No line of it exists. Spec 5 was revised during the second pass to serve this use, and its text was read once after that. A row whose body is kept outside `vfs_content` was not read.
- **Spec 3's guarded router and spec 7's record.** Neither exists, so no probe ran through them. The probes drove today's host, with a stand-in for a stop.
- **Fuel across builds.** Fuel was equal across runs of one build on one machine. Whether two CPU architectures, or two builds of one wasmtime version, count the same fuel was not run. If they do not, a resume across them is refused by decision 15, not by decision 13.
- **The sizes of entries and of stamps.** They are computed from the encoding, not measured.
- **The time of a replay** of a line at its full fuel.
- **How many lines are stopped in a day.**
- **A replay under the binary wire** of the boundary spec, which is not built.
- **A policy added or removed between a stop and its resume,** beyond the one case of decision 17's last row.

## One line

A stopped line is kept as what it was given, and is carried on by giving it the same again.
