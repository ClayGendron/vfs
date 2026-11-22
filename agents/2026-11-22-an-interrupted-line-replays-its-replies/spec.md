# An interrupted line is saved as its inputs and its replies, and replays them when it is resumed

A draft, written on 2026-11-22. It is not reviewed, and nothing is built. It is spec 8 of the nine that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps, and it rests on that page, on the two guides under `documentation/how-to/`, and on the tree at `6dae6a1d` on the branch `a-job-is-interrupted-and-resumed`. Every fact marked "Run" below was run that day. The extension installed in the checkout was older than the source (it did not take `host_programs`), so the probes ran against a build of the working tree made in the session's scratch directory, with wasmtime 51.0.0. The other eight specs were being written at the same time and were not seen. What this spec needs from each is stated under "Builds on" as a need.

## The outcome wanted

A shell line that reaches a step needing a person stops before that step and returns. Its job is stored as the line's inputs and the replies it had been given. When the job is resumed with the answer, the line carries on from that step, in any process, and returns the result its call would have returned. Nothing the line did before the stop is done again. A line that is never stopped stores nothing.

## Builds on

- **The shell as built** (`src/vfs/shell/`, `crates/vfs-shell`, `crates/vfs-shell-wasm`, `crates/vfs-core/src/shell_binding.rs`). Landed.
- **`agents/2026-11-20-write-takes-preconditions-and-an-append/spec.md`.** Landed. Its version mint keeps every replaced body whole, which decision 8 reads.
- **Spec 0, the kernel keeps records of its own.** Not written when this was drafted. Needs: a table made as the kernel's tables are made; one synchronous transaction that holds a row of `vfs_jobs` and rows of `vfs_job_replies` together; the same on a root storage in memory; a sweep that calls decision 9's orphan statement.
- **Spec 1, a row carries an etag.** Not written. Needs: `etag` as a column a `read` can name; a function a storage uses to take an etag apart into the entry's identity and its version.
- **Spec 3, the session remembers what it read.** Not written. Needs: the session a bare line gets can be saved when the line's job is saved, asked for again when the job is resumed with the stamps it had, and dropped when the job ends. This spec does not design how.
- **Spec 4, a session works in turns.** Not written. Needs: whatever is done to a session's shell state at the end of a line is done when the line ends, never when it stops.
- **Spec 6, a policy judges each step.** Not written. Needs: a `Step` for each public verb the host calls; `step.via` able to name a line; a test, with no I/O, of whether any policy applies to a call (the kernel's policies and the session's are both empty or not).
- **Spec 7, a job is interrupted and resumed.** Not written. Needs, each used by a numbered decision:
  1. `vfs_jobs` keeps, for a line, one document this spec defines, the line record of decision 3, of at most about 1.5 MiB. It keeps the caller's authority so that it can be built again, and the session and turn.
  2. A verb called by a line's host is judged with a place: the journal position of the request and the count of verb calls already made for that request. A step that must be interrupted comes back to the host as an interrupted result that holds the interrupt and has stored nothing. A step of a line is never matched to another job's waiting step.
  3. A function that stores or updates the job row for a line inside a transaction this spec adds its pages to.
  4. `resume` of a line job checks who may resume and the answer's schema, then calls decision 13's check before it claims anything, then claims, then calls decision 14's replay. It records the answer only when the replay reports that it reached the stop. A replay that refuses releases the claim and leaves the job as it was.
  5. After the replay, the stopped step is made through spec 7's road for a saved step: the policies run again with the answer, the step is checked to be the one saved, and the preview's precondition holds.
  6. `Cancel` reaches this spec as the fact spec 7 makes for it. A denial reaches it as a failed `Result` of kind `vfs.interrupt.denied`.
  7. A finished line's `LineResult` is stored as the job's result. It holds up to 16 MiB of output.
  8. Every removal of a job row runs decision 9's delete in the same transaction.
  9. A claimed job whose resume did not come back is never offered again. A claimed job whose call was cancelled can be ended with no result.
- **`agents/2026-11-21-the-shell-crosses-its-boundary-in-binary/spec.md`.** Drafted. It changes the wire and pins the toolchain. The journal holds the replies as the Python host gives them, so the wire's change does not change it.
- **`agents/2026-11-21-a-line-has-a-verb-budget-and-cli-tightens-it/spec.md`.** Drafted. Its verb budget is counted inside the machine, so decision 23 covers it with no change.
- **`agents/2026-11-21-the-shell-runs-the-standing-program-table/spec.md`.** Drafted. Its decision 2 serves `date` and its kin through `value`, which decision 11 journals.
- **`agents/2026-11-22-a-served-grep-hands-its-matches-to-the-line-a-page-at-a-time/spec.md`.** Drafted, with its decisions open. If a feed comes to make a verb call of its own, that feed's reply is journaled with its bytes, by decision 6's rule for a reply nothing else can rebuild.
- **`agents/2026-11-21-an-append-keeps-only-what-it-added/spec.md`.** Drafted. It changes what a version row holds. Whichever spec changes the version rows keeps `read_version` of decision 8 returning the whole body.
- **Roadmap stories H4 and F3, decisions D40, D41, D43, D46, D54 and D60.** "Earlier decisions this reverses" says what becomes of each.

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
- **Stop.** The point where a step of a line must be interrupted. The line's job is saved there and the call returns.
- **Replay.** Running a fresh machine from the line's start and answering from the journal.
- **Line record.** The JSON document the job row holds for a line: its inputs and where it stopped.
- **Fingerprint.** A digest of the build of the machine and of the tables a walk depends on.
- **Host program.** A name in `PROGRAMS` that the host runs itself at a `start` request, such as `grep -r` or `edit`.
- **Slice.** The work the machine does between two returns of `step` when it asks nothing.
- **Fuel.** The instructions the module has executed, counted by the runtime.
- **Interrupt.** What a stopped job waits for: a message, a schema for the answer, and a preview. It is spec 7's.
- **Claim.** The mark by which one resume, and no other, holds a job. It is spec 7's.
- **Etag.** A value that names one entry at one version. It is spec 1's.
- **Stamp.** A session's memory that it was shown a path at an etag. It is spec 3's.

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

The four probe scripts are in the session's scratch directory under `specs/`. They are not kept, and the tests under "Tests" stand in their place.

## The problem

A line is many steps. When one of them needs a person, VFS must stop and return, and it holds nothing open. The line's place is inside the machine, and the machine is a future over shared cells that cannot be moved to another process.

An earlier draft saved the machine's linear memory at the stop and wrote it into a fresh instance at the resume. That was ruled out: nothing saved is a memory snapshot. Its other cost was its own decision 22. A saved memory describes one instant, so a line could be saved only at a stop, and a line that died anywhere else could never be recovered.

The other road is to walk the line again. It is safe only if the walk is the same walk, and only if nothing the line did is done again. The first is a property of the machine, which the probes above show. The second needs every reply the line was given.

## Decisions

### 1. A line's job is the line's inputs, its journal and the place it stopped

Nothing of the machine is saved. The job row holds the line record of decision 3. The journal is in `vfs_job_replies`. A resume builds the machine again from the inputs and feeds it the journal.

Reason: ruling 2 of the overview. A line is a function of its inputs and its replies, which the two laws and the 36 replays show, so the inputs and the replies are the whole of its state.

### 2. A journal and a line record are records the kernel keeps, and add no primitive

Neither has a path. Both are reached only through `resume` and `jobs`, which are management methods. No view of them is served in the namespace.

Reason: Article 1 of the constitution allows five first-class things and gives each a path. A journal is a record about a call, as a grant is a record about a path.

### 3. The line record holds everything the machine is started with

| Field | Holds |
|---|---|
| `format` | `JOURNAL_FORMAT`, 1 |
| `fingerprint` | decision 13's digest, of the build that ran the line |
| `line` | the line's text, at most the parse budget of 1 MiB |
| `cwd` | the working directory the line started in |
| `env` | the pairs `run_line` was given, before it adds `PWD` |
| `name`, `args`, `pid` | `$0`, the arguments, and `$$` |
| `limits`, `fuel` | the budgets as the call gave them, or null |
| `stdin_bytes` | the length of the line's standard input |
| `stopped` | the position, key, name and digest of the request the line stopped at, and the count of verb calls made for it before the one that stopped |
| `stops` | how many times the line has stopped |
| `entries`, `bytes`, `pages` | the journal's counters: its next position, its size, and its next page |
| `evidence`, `unkept` | the refusals the host had kept, at most 100, and the count past 100 |

- The caller's authority, the session and the turn are on the job row, which is spec 7's.
- Standard input is not in the record. It is the journal's first entry, at position 0, when it is not empty.
- The two program lists are not in the record. The fingerprint covers them.
- The deadline is not in the record. Decision 23 says why.
- `evidence` is the host's own bounded state, not the machine's. It is saved because the facts come from verb results that the journal does not keep.
- The record is JSON. Nothing in it is revived as a Python object other than through a pydantic model.

Reason: a replay that takes any input from the running process can walk another line. Reading every input from the record makes a changed environment, a changed default budget or a changed `PID` constant unable to change the walk.

### 4. Replies are kept in memory while a line runs, and are written only when it stops

- A line records its replies only when it can be interrupted, which is when spec 6's test says a policy applies to the call. With no policy on the kernel and none on the session, a line records nothing, hashes nothing, and runs as it does today.
- A recording line keeps one entry in memory for each reply. It writes nothing to any store until a step must be interrupted.
- At a stop, the entries added since the last stop are written, with the job row, in one transaction. Then the machine is dropped and the call returns.
- A line that ends without stopping drops its entries. No statement was issued for them.
- A process that dies in the middle of a line leaves what the line had done, and no job. This is a failed call, as it is today. It is so before a first stop and after a resume alike. A job claimed by a resume that died is never resumed again, by need 9.
- A policy added while a line runs can interrupt a line that is not recording. That line cannot be stopped, and decision 10 says what it gets.
- When tools are built, a tool that can ask makes a call interruptible too, and the same test covers it.

Reason: a line that is never stopped must cost nothing, and most lines are never stopped. Writing each reply as it is given would put a synchronous statement on every read a line makes, which the overview forbids. The format still allows it later: the journal is positional and append-only, so writing entries as they are made changes when they are written and nothing else.

### 5. The journal is positional, and each entry carries the key and a digest of its request

An entry is `[position, key, op, digest, kind, payload]`.

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
| `read` | yes | `ref`: the etag and the content hash of the body the open saw, by decision 7. Or `data`: the bytes of the slice and whether it ended the file, when the row has no etag or its mount keeps no versions. Or `error`: the code. |
| `stat` | yes | `stat`: the kind and the size. Or `error`. |
| `list` | yes | `entries`: each name and kind, in the order given. Or `error`. |
| `value` | yes | `text`: the text given. Or `error`. |
| `start` | yes | `library`. Or `refused`: the status and the message. Or `error`. Or `started`: every write the program made, in order, with its status, which is the whole of what its feeds will hand out. |
| `feed` | yes, with no payload | The reply is taken from the `started` entry's writes, as the host takes it today. |
| `write`, `touch`, `mkdir`, `remove`, `copy`, `move` | yes | `done`. Or `error`: the code. Or `denied`: the words, by decision 18. |

- Bytes inside a payload are base64. A journal's size is its encoded size.
- The request's own arguments are not kept. A write's data is in no entry. Only the digest is.
- A reply that nothing else can rebuild is journaled with its bytes. A reply that a kept entry or a stored version can rebuild is journaled as the pointer to it.

Reason: the machine reads each reply to decide its next step, so each must be given again exactly. Keeping a request's arguments would double the memory of every write a recording line makes, and the digest is enough to tell that the machine asked the same thing.

### 7. A read is journaled as a reference to the body it saw, and the body is read again on replay

- The host asks `read` for `etag` beside the columns it asks for today. The body an open saw is named by its path, its etag and its content hash.
- Each `read` entry of that open holds the etag and the hash. The offset and the length are in the request.
- On replay the host fetches the body by decision 8's seam, once for each open, and cuts each slice from it. The body is held under `READING_BYTES` as a live body is.
- The fetch is the kernel's own. It passes no gate and asks no policy.
- A body that is gone refuses the resume, by decision 15.

| Way to keep a read | Verdict |
|---|---|
| The bytes, in the journal | Rejected. A line may read tens of megabytes. Each stop would write them to the kernel's store and each resume would read them back. File content would sit outside its mount, outside the mount's access rules, for a day after a delete. |
| The identity of the row, read again from the live file and refused if it changed | Rejected. A line that reads a file and then changes it, such as `sed -i`, could never be resumed. |
| A reference to the version seen, read from the mount | Chosen. An entry is about 170 bytes whatever the file's size. The body stays where its access rules are. The hash proves the bytes are the ones the line saw. |

What makes an old version readable: the write path keeps every replaced body whole in `vfs_versions`, a delete keeps the row and its body until the trash is swept, and nothing but that sweep removes a version. So the body is gone only when its file was deleted and swept, or its mount was removed, between the stop and the resume.

A resumed line's output can hold bytes its caller read before a right was taken away. It is the output the call would have returned had it not been stopped.

Reason: Temporal's history taught that values stored for replay are kept and shown for the life of the record, and that a reference resolved at the point of use is what keeps content out of it. The cost is one more seam and a resume that can find a body gone.

### 8. A storage gains one seam, `read_version`, that returns the body an etag and a hash name

```python
class SupportsVersions(Protocol):
    async def read_version(self, *, path: Path, etag: str, content_hash: str) -> bytes | None: ...
```

- The kernel routes by `path` to the mount that holds it, as it routes a read, and calls the seam with the mount's own path. It takes no authority.
- A storage declares it with the trait `versions: kept`. The host journals a read by reference only when the row's mount declares it and the row has an etag and a hash. Any other read is journaled with its bytes.
- The database storage answers in at most two statements. The first reads the row the etag names, live or deleted, with its body. If its hash is `content_hash`, that body is the answer. The second reads the row of `vfs_versions` for that entry with the lowest version at or above the etag's and that hash. If neither holds the hash, the answer is `None`.
- A text body is returned as its UTF-8 bytes, as the host encodes a read today (`host.py:392`).
- The answer is checked: the SHA-256 of the returned bytes is the hash, or the storage answers `None`.

Reason: the hash is what the line saw, so any stored body with that hash under that entry is the right bytes. This asks nothing of version numbers beyond a place to start the search, so a version that ticked for a move or a change of metadata does not confuse it.

### 9. `vfs_job_replies` holds a journal as pages of at most 1 MiB, appended at each stop

| Column | Type | Holds |
|---|---|---|
| `job_id` | as `vfs_jobs` keys a job | the job |
| `page` | integer | the page's number in the journal, from 0 |
| `body` | bytes, at most `JOURNAL_PAGE_BYTES`, 1 MiB | a run of the journal's encoded bytes |

- The primary key is `(job_id, page)`. There is no other index and no foreign key.
- The journal's encoding is one entry to a line: a JSON array, UTF-8, ended by a newline. The pages of a job, joined in order, are the journal.
- Each stop encodes the entries added since the last stop, cuts them into pages, and inserts them. A stop's first page is a new page, so no stored row is ever updated.
- Pages are inserted in statements of at most `BLOB_PAGE_BYTES`, 8 MiB, of body, by the shared `byte_chunked` helper, as version bodies are.
- A resume reads them with one statement, `WHERE job_id = :id ORDER BY page`.
- One statement removes them, `DELETE FROM vfs_job_replies WHERE job_id = :id`. It runs in the transaction that stores a finished line's result, and in every transaction that removes a job row. A removal of many jobs chunks the ids by `membership_budget`.
- The sweep also removes pages whose job is gone: `DELETE … WHERE job_id NOT IN (SELECT … FROM vfs_jobs)`. The table holds only the pages of waiting line jobs, so the statement is bounded by them.
- `page` and `position` are counters. The next of each is kept in the line record, which the store holds, so the process that holds the claim is the only one that hands them out.

Reason: a journal is only ever written at its end and read whole, in order. Rows per entry would cost a line of 10,000 requests 10,000 rows at its stop. Pages cost it one or two.

### 10. A journal is bounded at `JOURNAL_BYTES`, and a line past its bound cannot be stopped

- `JOURNAL_BYTES` is 16 MiB. It counts the journal's encoded bytes, standard input among them.
- It is a budget of the line. `journal_bytes` joins `LIMITS`, and a host sets it as it sets the others. Zero means the line records nothing.
- A line that passes it drops its entries, records nothing more, and runs on.
- If a step of that line then needs a person, the step is not done, the interrupt is not stored, and the line ends there. Its exit status is 137. Its error is `vfs.budget_exhausted`, with the detail `Budget("journal", 16777216): the line was given more replies than it may keep, so it could not be stopped for a step that needs a person; that step was not done`. Its result holds what the line had printed, as the result of any budget does.
- A line that was not recording when a policy interrupted it ends the same way, with "the line was not keeping its replies" in the detail.
- A stop whose transaction the store refuses ends the line with status 1 and the store's own refusal. The step is not done.

Reason: every reply a recording line is given is held in memory until it ends, so the hold needs a bound. Reads are references, so the bound is reached only by what has no stored version: standard input, listings, and the output of host programs. 16 MiB is the line's own output budget. Ending the line is what every other budget does, and it fails closed: a step a policy wanted judged is never run unjudged, and no later command runs on the belief that it was.

### 11. Every value the machine asks for is journaled as given, and the process id is an input

- A `value` reply is journaled as its text, whatever its name. A replay gives the same text and calls no clock and no random source.
- `pid` is in the line record. Every other process id is computed inside the machine from it and from the place of the subshell.
- A program that reads the host, such as `date`, asks through `value` when it is built, and is covered with no change here.

Reason: a value is the only thing a line is given that no store can give again. Roadmap decision D54 chose to record and replay these words, and this keeps it.

### 12. The order of requests inside a line is a function of its inputs, its replies and its build

- Stages of a pipeline, jobs run with `&`, and substitutions are tasks of one future. They are polled in a fixed order and never woken by anything outside it.
- Where a slice ends decides which task asks first, and it can decide how many requests are asked. A slice ends on a count of fuel. So the order is fixed by the line, the replies, the budgets and the build that counts the fuel.
- `fuel_slice` and every other budget are in the line record, and the build is in the fingerprint.
- The journal is therefore keyed by position alone. No entry is matched across an order that moved.

Reason: the probes found the order equal in 36 replays and 52 resumes under one build and one set of budgets, and found it move when `fuel_slice` alone changed. Keying by the machine's key would let a replay run under another order, and the ninth request of the probe shows that another order can ask another set of requests.

### 13. A job carries the fingerprint of the build that ran it, and a resume under another build is refused before anything is claimed

- The binding exports `SHELL_FINGERPRINT`: a SHA-256, in hex, of the module's bytes, the version of wasmtime it was built with, and the binding's default `FUEL`, `FUEL_SLICE` and `MODULE_MEMORY_BYTES`. The build script takes the wasmtime version from the lock file.
- `line_fingerprint()` is the SHA-256 of `JOURNAL_FORMAT`, `SHELL_FINGERPRINT`, the sorted names of the library's programs and the sorted names of `PROGRAMS`.
- A resume compares the record's `fingerprint` and `format` with its own before the job is claimed and before the answer is recorded. When either differs, the resume returns one `vfs.conflict`, not retryable, with the detail "the shell is not the build that stopped this line, so the line cannot be carried on from where it stopped; resume it from a process that runs that build, or cancel the job".
- The package's version is not in the fingerprint.
- `JOURNAL_FORMAT` is raised by hand when the journal's encoding or the host's replay of an entry changes.

Reason: a new module, a new runtime or a new program table can walk another line, and DBOS shows that the honest answer is a classified refusal, not a stranded row or a silent second path. Leaving the package's version out keeps a job resumable across an upgrade that did not touch the shell. Checking before the claim lets a process of the old build still resume the job during a rolling deploy.

### 14. A resume starts a fresh machine and a fresh host, and answers from the journal until it runs out

The step loop is the one `run_line` has. While the journal has an entry for the next position, the host answers from it:

| Entry | What the host does |
|---|---|
| `read`, `ref` | Registers the open as seeing that body. Takes the body from the bodies it holds, or fetches it by `read_version`. Cuts the slice, and closes the open at the end of the file, as a live read does. |
| `read`, `data` | Gives the bytes. |
| `read`, `error` | Closes the open and gives the error, as a live refusal does. |
| `start`, `started` | Puts the program's writes where its feeds will take them, and answers `started`. |
| `feed` | Takes the next write, as a live feed does. |
| anything else | Gives the reply as it is kept. |

- No public verb is called. No policy is asked. No stamp is left. No clock is read.
- The output, the statuses and the fuel are produced again by the machine, and are the ones the line produced before.
- When the journal ends, the host's evidence is set from the record, and the next request is the one the line stopped at.
- The host and the machine are then in the state they were in at the stop, and the same loop goes on live.

Reason: this is Temporal's replay, with the journal as the history. Running the host's own code for an open and a feed rebuilds its state by the road that made it, so a stop in the middle of an open or between a start and its feed needs no state of its own saved. The probe stopped in both places.

### 15. Every replayed request is checked against its entry, and a mismatch refuses the resume with a conflict that names the step

- For each request, the host computes the digest and compares the key, the name and the digest with the entry at that position.
- The request asked when the journal ends is compared with `stopped` in the same way.
- A line that ends, or asks nothing, with entries left is a mismatch at the first entry not reached.
- A mismatch returns one `vfs.conflict`, not retryable. Its detail is "the line did not ask what it asked before: at step N it asked `write` at `0.1#3`, and its journal holds `read` at `0#2`; nothing more was run; cancel the job". Its `data` is `{"vfs.line": {"reason": "diverged", "position": N, "asked": {…}, "journal": {…}}}`.
- A `read_version` that answers `None` returns one `vfs.conflict` at the file's path, with "the line read this file at a version that is no longer stored, so the line cannot be carried on from where it stopped; cancel the job", and the reason `version`.
- The deadline passing during the replay returns `vfs.timeout`.

What can cause a mismatch: a new module, runtime or program table, which decision 13 refuses first; a changed input, which decision 3 rules out by reading every input from the record; and a fault in the machine that makes a walk depend on something outside its replies. The check is for the third.

Reason: Restate's rule. A replay that does not match must stop before it runs anything live, because from that point the journal describes another line.

### 16. A resume that cannot replay changes nothing

- A refusal of decision 13 or 15 leaves the job interrupted, with its interrupt waiting. The answer is not recorded and the claim is released. Nothing was run and nothing was written.
- The result is a `LineResult` with `success` false, exit status 2, the one refusal, no output, and the job.
- The job can still be resumed by a process that can replay it. It can be cancelled, by decision 17. It lapses with its lifetime.

Reason: a replay calls no verb, so refusing it costs nothing that must be undone. Ending the job at the first failed attempt would let one process of a new build end every job an older process could still resume.

### 17. The step the line stopped at is made again as the public verb it was, with the answer

After the replay, the host handles the stopped request as it handles any request, and names its place to spec 7.

- **An approval.** The step is carried out by spec 7's rules for a saved step. Its reply is journaled at its position, and the line goes on. If the verb is refused all the same, by a right taken away or by a file changed since the preview, the command fails as it fails for any refused verb, and the line goes on.
- **A denial.** The verb returns a failure of kind `vfs.interrupt.denied`. The host gives the machine a `denied` reply with the words, by decision 18. That one command fails, the reply is journaled, the fact is kept among the line's warnings, and the line goes on. `cmd || fallback` runs the fallback, and `set -e` ends the line as it does for any failed command.
- **A cancel.** The replay runs to the stop and the line ends there. The step is not made. The exit status is 130. The result holds what the line printed up to the stop, its statuses, the fact of kind `vfs.interrupt.cancelled` as its error, and the line's warnings. `success` is false.
- **A cancel that cannot replay.** The job is cancelled all the same. The result holds no output, the cancel's fact, and the conflict of decision 13 or 15 as a warning.
- **A step with two policies that each need a person.** The line stops again at the same position. The stop writes no page, and the record's `stops` goes up by one.

Reason: a step of a line is a public verb like any other, so it is judged, previewed and answered by the one road spec 7 builds. A cancel must always land, because it is how a host gives up on a job that cannot be replayed.

### 18. A denial reaches the machine as a refusal with its own words, and its command exits as it does for `Permission denied`

- The wire gains one reply kind, `denied`, whose value is the words. The Python host gives `("denied", words)`.
- In the machine, `HostError` gains `Denied` with the words, and stops being `Copy`. Every place that matches a refusal treats `Denied` as it treats `PermissionDenied`, and prints the words where it prints `Permission denied`.
- The words are the message of the fact, with no path and no retry class: `Denied by <name> — This step needed approval, and <name> denied it. Reason: <reason>`.
- So `rm` prints `rm: cannot remove '/contracts/acme.md': Denied by <name> — …` and exits 1. A redirection prints `bash: line 1: /contracts/acme.md: Denied by <name> — …` and its command exits 1. `sed -i` exits 4 and `ls` exits 2, as each does for `Permission denied` today.
- A host program prints the same words through the road it has, `name: path: reason`, and exits 1.
- The host gives `denied` for a refusal whose kind is `vfs.interrupt.denied`. Every other kind keeps the code it maps to today.

Reason: the guide says a denied command prints that the principal denied it, and that a denial is not a missing right. The machine's eight texts cannot say so. One new reply is the smallest change that can.

### 19. A host program that is stopped is started again from its first verb

- A step inside a host program is judged with its request's position and the count of verb calls the program had made.
- When that step is interrupted, the `start` request has no reply and no entry. The resume reaches it live and runs the program again from its start.
- A law holds for every name in `PROGRAMS`: a host program makes at most one change, and no verb call follows it. So a program that is started again repeats reads and never a change.
- If the program takes another road the second time and asks about another step, the answer is not used, by spec 7's rule that an answer is for one step at one place.

Reason: a program's verbs before its change are reads, and a read done twice changes nothing. Journaling a program's verbs one by one would add a second journal inside the first for a case the law rules out. A tool is not a host program, and its rules are spec 7's.

### 20. A line stops once for each interrupt, at the first request that needs a person

- The requests one pass of the step loop returns are answered in order. The first whose verb must be interrupted ends the loop. The requests after it in that pass are not answered and have no entry.
- The replies given before it in that pass are in the journal.
- On the resume the machine asks the same requests in the same order. The earlier ones are answered from the journal, the stopped one with the answer, and the later ones live.
- Two stages of a pipeline that each need a person stop the line twice, one after the other.

Reason: ruling 4 of the overview. A job has at most one interrupt waiting.

### 21. A line that stops again appends to its journal, and each resume walks the line from its start

- Each stop writes only the entries added since the last one.
- Each resume replays the whole journal. Its cost is the machine's work up to the stop and one fetch for each open before it.
- A line with `n` stops is walked `n` more times. When the stops are spread evenly through it, that is about `n / 2` runs of the line beside its own.
- No machine is kept in memory between a stop and its resume.

Reason: the journal is the truth and a kept machine would be a cache of it. A cache helps only a resume in the same process within moments, and a person answers in minutes, from any process. Temporal keeps such a cache and still replays on every miss.

### 22. The result that ends a line holds the line's whole output, and an interrupted result holds none

| Result | `success` | `interrupted` | `exit_code` | `stdout`, `stderr`, `statuses` | `errors` |
|---|---|---|---|---|---|
| The line stopped | false | true | 126 | empty | the fact spec 7 makes for the interrupted step |
| The resumed line stopped again | false | true | 126 | empty | the same, for the new step |
| The resumed line ended | as for any line | false | the line's | everything from the line's first command | the line's warnings, from before and after every stop |
| The line was cancelled | false | false | 130 | everything up to the stop | the cancel's fact, then the warnings |
| The resume could not replay | false | false | 2 | empty | the one conflict, or the one timeout |

- `fuel_used` is the fuel the machine had spent when the call returned. For a line that ended, it is the fuel of a run never stopped.
- `job` is the line's job on every row.
- The text of an interrupted result prints no output and the one fact. It names no job and no resume.
- A resumed result is not a tail. A host hands it to its agent as the answer to the line.

Reason: the guide says the result of a resume is the one the call would have returned, and that an agent only ever sees that one. Output given once, by the result that ends the line, cannot be shown twice. 126 is the shell's status for a command that was found and could not be run, which is what "not approved" means to whoever reads it.

### 23. The machine's budgets are counted once, and the deadline is each call's own

- Fuel, memory, loop iterations, function depth, nesting, output bytes and the parse budgets are counted inside the machine. A replay counts the same work again in a fresh instance and reaches the stop with the same counts. So a line that is stopped may do exactly what a line never stopped may do.
- A verb budget counted by the machine is covered the same way.
- The host's CPU is spent again on every resume, for the work up to the stop.
- The deadline is not saved. The first call and each resume get `DEADLINE_SECONDS` of their own, and a resume's deadline covers its replay.
- A resume cancelled or timed out during the replay is decision 16. One cancelled after the stopped step was made ends the line as a cancelled call does today, and the job ends with no result.
- A resume takes a turn among the lines a router runs at once, as a new line does.

Reason: a budget that is a count is a function of the line, so it needs no saving. A clock is not, and the overview keeps clocks out of what is stored. The time a person takes to answer is no part of a line's work.

### 24. A resumed line runs as its caller, in the session and turn it started in, and its stamps cross the stop

- Every verb after the replay is called with the authority on the job row, judged as it stands at the resume.
- A line run through a stored session resumes in that session and turn. Its stamps were stored as it read, and are there.
- A line run with no session has a session of its own for the length of the line. The stop is inside that length. That session is saved with the job and given back at the resume, by the need on spec 3.
- A replayed read leaves no stamp, since it calls no verb.
- A stopped line changes none of its session's shell state. The end of the resumed line is the line's end.
- A line never runs as the system authority, so a line's job is never a system job.

Reason: the guide says a resumed line runs as whoever started it, with that caller's access as it stands. A bare line that read a file, stopped, and then wrote it back must still be guarded, and must not be refused as unread.

### 25. A line made again is a new line

- `cli` called again with the same text while its job waits runs the line from its start and, if it stops, stores a second job.
- A host whose code may run again, such as a LangGraph node, asks its session for a waiting job before it runs a line, and resumes that job.

Reason: finding a waiting job by a line's content would cost a statement at the start of every line, which decision 4 forbids, and would hand a second line that was meant to be a second line the first one's job.

### 26. Three landings, in this order

1. The machine and the binding: the `denied` reply, `SHELL_FINGERPRINT`, and the replay law in the crates' tests.
2. The journal and the seam: `journal.py`, recording and replay in the host, driven in tests by a stand-in for a policy, and `read_version` on the storage.
3. The kernel: `vfs_job_replies`, `cli` and `resume` joined to spec 7, the faces, and the guides.

Reason: each leaves the tree green. The first needs nothing from the other eight specs and the second needs only spec 1's etag, so both can be built while spec 7 is.

## Cost

Costed against the reference deployment in the working agreement.

**Per verb call, about 150,000 a day.** A line no policy applies to pays nothing: no entry, no hash, no statement. A line a policy applies to pays, for each request, one SHA-256 over the request's arguments and one entry in memory of 110 to 170 bytes. It issues no statement for them. A direct verb pays nothing.

**Per file write, per index visit, per batch.** Nothing is added.

**A stop.** The statements spec 7 issues for the job row, and one `INSERT` of pages, in one transaction. At the bound of 16 MiB it is two. The bytes are the record, about 1 KB beside the line's text, and the entries. A line that read 50 MB in 800 chunks stores about 140 KB.

**A resume.** The statements spec 7 issues, one `SELECT` of the pages, at most two statements on a mount for each open the line made before the stop, and the machine's work up to the stop, which the fuel budget bounds at about five seconds. Then the stop's cost again, or one `DELETE` of the pages beside the result.

**A line with `n` stops.** `n` inserts, `n` selects, and about `n / 2` walks of the line.

**Memory.** At most `JOURNAL_BYTES` for each running line a policy applies to, and the bodies a replay holds under `READING_BYTES`, as a live line holds them.

**The day.** How many lines are stopped is an assumption: no measurement exists. At one line in a hundred of the agent calls, 1,500 stops a day write about 6 MB, and each is removed when its line ends. The table holds the pages of the jobs that wait, for at most the job lifetime of 24 hours.

**Per corpus.** The sweep's orphan statement reads `vfs_job_replies`, which is bounded by the waiting line jobs.

**Per lock.** A stop inserts rows under one job's id and holds them for the length of a commit. No reader waits on them, and no other job touches them. On SQLite the kernel's store is its own file, and a stop is one small transaction on its one writer. `read_version` is a plain read.

## Left as it is

- **Recovery after a process dies in the middle of a line.** It is a failed call. Writing entries as they are made would allow it, and decision 4 says why it is not done.
- **A machine kept between a stop and its resume.** Decision 21.
- **A redirection of a program's output is two steps.** The machine sends the truncating write when the file opens. Under a policy on that path the line stops twice. A change that made a redirection one step is the shell's, and no spec for it is written.
- **One writer can send its opening write twice.** The probe's ninth request is a second truncating write of one file, sent by another task while the first was still waiting for its reply. A task that ends flushes every writer the line holds (`exec.rs:1919-1925`), and a writer counts as unwritten until its first reply arrives (`files.rs:190-192`, `:220`). It does not break a replay. It is one more step for a policy to judge. It needs a spec of its own.
- **Tools.** A tool in a line, and a tool that asks, are left out of the nine.
- **A view of a journal in the namespace,** and any way to read one entry by SQL.
- **The words of an interrupted result,** the claim, the states of a job and who may resume. They are spec 7's.

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
- `test_entries_encode_and_decode_to_themselves`: every kind of payload, with bytes that are not UTF-8.
- `test_a_journal_past_its_bound_drops_its_entries`: with `journal_bytes` at 200, the journal holds 0 entries after the request that passes it.
- `test_a_stored_journal_of_this_format_still_decodes`: a fixture file decodes to a pinned list.

`tests/shell/test_host.py`:

- `test_a_line_no_policy_applies_to_records_nothing`: `request_digest` is called 0 times.
- `test_a_replay_calls_no_verb`: a host given a journal answers every entry with 0 calls to any method of the router.
- `test_a_replay_rebuilds_an_open_and_a_feed`: a journal that ends inside an open and after a `started` entry; the next live `read` and `feed` return the bytes a line never stopped gets.
- `test_a_replayed_request_that_differs_names_its_step`: an entry with another digest; one `vfs.conflict` whose `data` holds that position.
- `test_a_line_that_ends_with_entries_left_is_a_mismatch`: a journal with one entry more than the line asks; one `vfs.conflict` whose position is that entry's.

`tests/shell/test_programs.py`:

- `test_a_host_program_makes_at_most_one_change_and_makes_it_last`: for each name in `PROGRAMS` over a table of arguments, a spy counts at most 1 changing verb and 0 verbs after it.

`tests/shell/test_line_jobs.py`, through the kernel, on SQLite, with a contract row on the Postgres leg for the first, the fourth and the last:

- `test_a_line_that_is_not_stopped_stores_nothing`: with a policy that allows every step, 0 statements on the kernel's store and 0 rows in `vfs_jobs` and `vfs_job_replies`.
- `test_a_stop_writes_the_job_and_its_pages_in_one_transaction`: one `INSERT` into `vfs_job_replies`, one row, one commit.
- `test_a_line_with_cp_stops_once_and_its_note_is_written_once`: the guide's line with `cp`; `/notes.md` holds one line and is at version 1 after the resume.
- `test_a_resumed_line_equals_one_never_stopped`: the probe's lines, stopped before every change; equal `stdout`, `stderr`, `statuses`, `exit_code` and `fuel_used`, and an equal list of changing calls.
- `test_no_public_verb_that_changes_anything_is_called_during_replay`: between the start of a resume and the end of the journal, 0 calls to any public verb, 0 `INSERT`, `UPDATE` or `DELETE` on the mount, and `read_version` called once for each open.
- `test_a_redirection_of_a_programs_output_stops_twice`: `cat a > b` under a policy on `b` returns two interrupted results.
- `test_a_line_stopped_three_times_appends_three_runs_of_pages`: 3 inserts and 0 updates on `vfs_job_replies`.
- `test_a_read_is_journaled_as_a_reference`: a line reads 5 MiB and stops; its pages hold under 4,096 bytes.
- `test_a_read_replays_from_the_version_it_saw`: a line prints a file, overwrites it and stops; the resumed output holds the first body; the second statement of `read_version` runs once.
- `test_a_version_that_is_gone_refuses_the_resume`: the file is deleted and swept; one `vfs.conflict` at its path; the job is still interrupted; 0 changes.
- `test_a_resume_under_another_build_is_refused_before_the_claim`: with `line_fingerprint` patched, one `vfs.conflict`, 0 writes on the kernel's store, the job still interrupted.
- `test_a_denial_fails_one_command_and_the_line_goes_on`: the statuses of decision 18's table; the words on standard error; `cmd || fallback` runs the fallback; one warning of kind `vfs.interrupt.denied`; `success` true.
- `test_a_cancel_ends_the_line_with_130_and_what_it_printed`: the output before the stop; the next command's file is absent; kind `vfs.interrupt.cancelled`.
- `test_a_cancel_lands_when_the_line_cannot_be_replayed`: the job is cancelled; no output; two errors.
- `test_a_value_replays_as_given`: with `_value` spied, a line that prints the time, stops, and prints it again calls it twice in all, and the resumed output holds the first value.
- `test_two_stages_that_each_need_a_person_stop_one_at_a_time`: two interrupted results, one interrupt each.
- `test_a_step_two_policies_ask_about_stops_twice_and_writes_no_second_page`: 2 interrupted results, 1 `INSERT` into `vfs_job_replies` in all, and `stops` is 2.
- `test_a_line_past_its_journal_budget_ends_at_the_step_that_needs_a_person`: exit 137, `vfs.budget_exhausted`, the step's file at its old version, 0 rows stored.
- `test_an_interrupted_result_holds_no_output_and_names_no_job`: empty `stdout`, `stderr` and `statuses`; `exit_code` 126; the text holds neither "resume" nor "job".
- `test_a_budget_is_counted_once`: with `loop_iterations` at N, a line of N iterations with a stop in the middle ends with status 0, and one of N + 1 ends with 137, as each does when never stopped.
- `test_each_call_gets_a_deadline_of_its_own`: `Deadline.after` is called once for the call and once for the resume, each with `DEADLINE_SECONDS`.
- `test_a_resumed_line_runs_as_its_caller`: every router call after the replay carries the saved authority; a right revoked before the resume fails the step with status 1.
- `test_a_bare_lines_stamps_cross_the_stop`: `cat f`, a stop, then `sed -i` on `f` ends with status 0; with a rival's edit of `f` during the wait, the `sed` is refused and `f` keeps the rival's body.
- `test_a_stopped_host_program_changes_once`: `edit` under a policy; after the approval the file is one version on.
- `test_a_line_made_again_is_a_second_job`: 2 rows in `vfs_jobs`.
- `test_a_line_of_10_000_requests_stops_in_one_insert`: a loop of 10,000 `stat` requests and then a stop issues 1 `INSERT` into `vfs_job_replies`, of 2 rows at most. Marked `slow`.
- `test_another_process_resumes_the_line`: two kernels over one SQLite file, and the synchronous face; equal output.

`tests/storage/test_conformance.py`, on every engine leg, rows for `read_version`: the live body by its hash in 1 statement; a replaced body from `vfs_versions` in 2; a bytes body; a deleted file not yet swept; a swept file answers `None`; a hash nothing holds answers `None`.

The docs gate runs every block of Step 7 of the interrupt guide, as changed below.

## Scope

In:

- `crates/vfs-shell/src/machine/` (`Reply`, `HostError`, every place that matches a refusal, `files.rs`), `crates/vfs-shell-wasm/src/wire.rs`, `crates/vfs-core/src/shell_binding.rs`, `python.rs`, `build.rs`, and `src/vfs/_native.pyi`.
- `src/vfs/shell/journal.py`, new: `Journal`, `LineRecord`, `LineStop`, `request_digest`, the encoding, `line_fingerprint`, `JOURNAL_FORMAT`, `JOURNAL_BYTES`, `JOURNAL_PAGE_BYTES`. It imports nothing from `vfs.storage`.
- `src/vfs/shell/host.py`: recording, the replay road of `answer`, `resume_line` beside `run_line`, `journal_bytes` in `LIMITS`, and `etag` in the columns a read asks for.
- `src/vfs/storage/protocol.py` (`SupportsVersions`), the database storage's `read_version` and its trait.
- `src/vfs/base.py`: `cli` saving a stop, the routing of `read_version`, and the line's half of `resume`. `sync.py`, `session.py` and `sync_session.py` for the same.
- `vfs_job_replies`, where spec 0 puts the kernel's tables.
- The tests above and the docs below.

Out: everything under "Left as it is", and every table and name another spec owns.

The landings are decision 26's three. Each is green alone.

## What the docs must say

- A line that stops keeps what it did, and a resumed line returns the whole of what the line printed, from its first command.
- VFS keeps the line's text, its standard input, its environment and its replies while the job waits. A file's content is not copied: the line's reads are kept as pointers to the versions it read. A host that puts a secret in a line's text or environment has it stored for the job's lifetime.
- A resume is refused with a conflict, and nothing is run, when the shell is another build, when the line no longer asks what it asked, or when a file the line read has been deleted and swept. The job still waits. Cancel it, or resume it from a process that can.
- A denied command prints who denied it and exits as it does for `Permission denied`.
- A cancelled line returns what it printed before it stopped, with status 130.
- A line that was given more than 16 MiB of replies that have no stored version cannot be stopped. A step of it that needs a person ends the line.
- A redirection of a program's output, `cmd > file`, is two changes to `file`, and can stop twice.
- `cli` is not safe to make twice. Code that may run again asks its session for a waiting job first.
- Each resume walks the line from its start, so a line with many stops costs more than one with few.

Pages: Step 7 of `documentation/how-to/interrupt-a-job-and-ask-a-person.md`; the docstrings of `cli` and `LineResult`; the `LIMITS` docstring for `journal_bytes`; the LangGraph section of the interrupt guide for a line; a Maintainers page for the journal's format, the fingerprint and `read_version`.

## Earlier decisions this reverses

- **Roadmap D60** leaned to saving the machine's memory. Ruling 2 ended that, and this spec builds the other answer.
- **Decisions 18 to 23 of the earlier interrupt draft.** Memory pages, the module hash on the row, `in_doubt`, and status 75 for a stopped line are all replaced. The status is 126.
- **Roadmap D41** recorded effects, the reads a walk depends on, and the identity of every other read, and read the rest again from the live file under a hash check. Every reply is now journaled, and a read is fetched at the version it saw, never from the live file.
- **Roadmap D40** drained a pipeline before stopping, so that questions raised together were shown together. A line now stops at the first.
- **Roadmap D43** gave a run a ledger of 64 MiB and evicted the oldest run. A journal is 16 MiB for one line, and nothing is evicted.
- **Roadmap D46** left a step in doubt after a crash and asked the host. Nothing is in doubt: a line that died is a failed call.
- **Roadmap D54** stands: the shell's words that are not functions of the line are recorded and replayed.
- **Roadmap F3 criterion 10 and H4.** The determinism law stands, with decision 5's digest in place of an earlier fingerprint. H4's step rows in an action log, its `/.vfs/jobs` view and its `answer` verb are not built by this spec.

## Choices for the owner

Each is decided above, and is listed here because it is the owner's to change.

1. **A read is kept as a reference, not as bytes** (decision 7). It costs the seam of decision 8 and a resume that fails when a version was swept.
2. **The journal's bound is 16 MiB, and a line past it ends at a step that needs a person** (decision 10). The other answer refuses that one step and lets the line go on.
3. **An interrupted line's exit status is 126** (decision 22). The earlier draft used 75.
4. **An interrupted result holds no output** (decision 22). The other answer holds what the line had printed, and a host must then cut it from the resumed result.
5. **A cancelled line's result holds what it printed, rebuilt by a replay** (decision 17). The other answer returns no output and replays nothing.
6. **The guide's line uses `cp`** (below). The other answer is a change to the shell so that a redirection is one step.
7. **Each call gets a deadline of its own** (decision 23).
8. **The fingerprint leaves the package's version out** (decision 13), so a job outlives an upgrade that did not touch the shell.
9. **A line made again is a new line** (decision 25).
10. **A line that dies between stops is not recovered** (decision 4).

## Where this spec disagrees with the overview or the guides

1. **Step 7 of the interrupt guide stops twice, not once.** Its line holds `cat /drafts/acme.md > /contracts/acme.md`. Run: the machine sends a write of 0 bytes that truncates `/contracts/acme.md`, then a `stat` and a `read` of the draft, then a write of 27 bytes that appends. Both writes are changes under `/contracts`, so the policy interrupts both, and the first is a change that empties the contract. The change proposed: the guide's line uses `cp /drafts/acme.md /contracts/acme.md`, which is one `copy` request (run), and the guide says in one sentence that `cmd > file` is two changes.
2. **The guide's text for an interrupted result says "so nothing was changed".** For a line whose earlier commands ran, that is false. The change proposed, to spec 7's words when the step came from a line: "so this command was not run. The commands before it ran."
3. **The guide's Step 7 names one cause of a refused resume, a shell that changed.** There is a second: a file the line read was deleted and swept. The change proposed is the third sentence under "What the docs must say".
4. **The overview says `vfs_job_replies` holds the journal of a line's replies, in order.** It holds that journal as pages, and the line's standard input as the journal's first entry, so that no row of `vfs_jobs` grows with it.

## Not checked

- **The eight other specs.** None was seen. Every need under "Builds on" may meet a spec that decided otherwise, above all spec 7's order of claim, replay and answer, and spec 3's session for a bare line.
- **Any engine but SQLite in memory.** No statement here was run on Postgres, and the kernel's store does not exist yet.
- **`read_version`.** It is read from the schema and the mint, and no line of it was run. A row whose body is kept outside `vfs_content` was not read.
- **Fuel across builds.** Fuel was equal across runs of one build on one machine. Whether two CPU architectures, or two builds of one wasmtime version, count the same fuel was not run. If they do not, a resume across them is refused by decision 15, not by decision 13.
- **The sizes of entries.** They are computed from the encoding, not measured.
- **The time of a replay** of a line at its full fuel.
- **How many lines are stopped in a day.**
- **Whether spec 7 can store a result of 16 MiB.**
- **A replay under the binary wire** of the boundary spec, which is not built.
- **A policy added or removed between a stop and its resume.** It is asked about the stopped step as it stands at the resume, by spec 7's rule, and no test here pins it.

## One line

A stopped line is kept as what it was given, and is carried on by giving it the same again.
