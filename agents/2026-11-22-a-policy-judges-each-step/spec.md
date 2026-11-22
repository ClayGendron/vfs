# A policy judges each step before it runs

This spec is a draft, written on 2026-11-22. It is not reviewed, and nothing in it is built. It is spec 6 of the nine that `agents/2026-11-22-the-specs-for-jobs-and-sessions/overview.md` maps. It rests on that overview, on the guide `documentation/how-to/interrupt-a-job-and-ask-a-person.md` (its steps 1 and 2 and its sections "Combine Policies" and "The System Authority Is Never Interrupted"), on the code of the branch `a-job-is-interrupted-and-resumed` at `6dae6a1d`, and on four studies under `agents/2026-11-22-a-job-is-interrupted-and-resumed/research/`: `cedar.md`, `approval-modes.md`, `langgraph.md` and `temporal.md`. Every probe named below was run on 2026-11-22 on a SQLite file or the in-memory storage, under Python 3.13.11. The probe scripts were scratch files and are not kept, so each result is stated where it is used. The other eight specs were drafted on the same day, without sight of this one.

**Round two, 2026-11-22.** The other eight drafts were then read: each one's Builds on, every decision that names this spec or something it owns, and every decision this spec leans on. A name another spec owns is written here as that spec has it, and is cited by its number and its heading, because the others were being revised at the same time. Decision 23 is new. Decisions 2, 3, 8, 10, 13, 16 and 17 changed in what they decide, and each says where. Most of the others gained a citation and nothing else. No decision was renumbered or removed. This spec keeps no record, so the first three rulings of round two, on the kernel store, the session key and the etag, ask nothing of it but what decisions 21 and 23 say. What no other spec provides yet is under "Needs no other spec meets yet".

**Round three, 2026-11-22.** The names of the other eight are frozen at `7c383f32`, and every citation here was read again against the owner's text. Five of the six needs of round two are met by their owners and are gone from the list. Decision 24 is new: the rights proof can be asked alone, which spec 5's rewind needs. Decision 14 now has a denied command print the policy's reason, through the table spec 8 keeps. Decisions 2, 13 and 17 changed in small ways and say where. The public surface is written out beside the specs, in `surface-6.md`.

## The outcome wanted

A host hands VFS functions of its own, and VFS shows each one every verb it is typed for, before that verb changes anything. A function allows the verb or denies it with a reason. A denial stops the verb whole, and the caller reads why. A function that breaks stops the verb too. A file system with no such function, or with none typed for a verb, pays nothing for that verb.

## Builds on

| What | State | What this spec takes from it or needs of it |
|---|---|---|
| The parameter table, `src/vfs/params.py` | landed | The table's rows become the fields of the step classes. Decision 2. |
| The cancellation rule, `documentation/maintainers/cancellation.md` | landed | A cancelled call leaves its storage whole. A call cancelled while a policy is asked has reached no storage. |
| Spec 0, the kernel keeps records of its own | drafted | Nothing. This spec keeps no record, so it uses none of the forms of spec 0, decision 22 ("The interface is private, and this is all of it"). Spec 0, decision 21 ("The store judges no rights, and no session, policy or tool can reach it") holds here: a policy is handed a step, and a step holds nothing that reaches the store. |
| Spec 1, a row carries an etag | drafted | It is built before this spec and changes the table the step classes are written from. Spec 1, decision 6 ("`write`, `edit`, `delete` and `move` take `if_match`, and their batch forms take `if_matches`"), decision 7 ("`if_version` and `if_versions` leave") and decision 14 ("The four public faces, the parameter table and the seam carry the same names") say how. Its decision 8 ("The rules at the gate") adds two kinds of parameter, `etag` and `etags`, which a field of a step class can have. Its decision 17 ("`restore` takes `if_match` and `if_matches`, and they name the tombstone") gives `restore` the pair too, and its decision 18 ("The mark `ABSENT`, in place of an etag, requires that the path holds no live row") lets either hold the string `"absent"`. Decisions 2 and 21 here take them. Met. |
| Spec 2, a session is stored, named and forked | drafted | Spec 2, decision 2 ("`fs.session(authority=None, id=None, *, strict=True, policies=())` returns a handle and does no I/O") and decision 3 ("The handle holds seven values, and only its current turn ever changes") give the handle and its slot `_policies`, public as `policies`, a tuple. Its decision 4 ("`strict` and `policies` belong to the handle and are never stored") has the handle build a `PolicySet` once, through this spec's constructor, keep it, and run each verb inside `decisions.with_policies`. Until this spec lands it refuses a non-empty `policies` with `ValueError`. Decision 17 here removes that refusal and its test, and gives the constructor. Met. |
| Spec 3, the session remembers what it read | drafted | Spec 3, decision 8 ("A read writes its stamps behind, and a change writes them with the change") orders a change through a session: strict refuses at its step 3, and the kernel is called at its step 5, where the policies are. So `vfs.conflict.unread` (spec 3, decision 12, "The two refusals are `vfs.conflict.changed` and `vfs.conflict.unread`, and neither carries a version") is given before any policy is asked. `vfs.conflict.changed` is found by the storage's precondition, after the policies, as every refusal of a verb's body is. Met. |
| Spec 4, a session works in turns | drafted | Nothing is needed. A fork's handle carries the source handle's policies (spec 4, decision 16, "`fork(id, before=turn)` makes a new session of the same owner under an id that owner has not used"). |
| Spec 5, a rewind puts a session's files back | drafted | It asks this spec for two things. Spec 5, decision 13 ("A rewind with files is one step to the policies and one job to an interrupt") needs a step class that is no verb's, `RewindStep`, and a way to have it judged. Spec 5, decision 9 ("Steps run in batches through the router's verbs, as the session's authority, below the session and below the policies") needs a way to dispatch a verb inside a step already judged. Decision 23 here gives both. Its decision 13 also proves each batch of its plan by `admits` before anyone is asked, and decision 24 here gives the kernel's call for that, `fs._proof`. |
| Spec 7, a job is interrupted and resumed | drafted | It owns `interrupt`, `require_approval`, the job and `resume`. This spec owns the place a policy is asked and the judging coroutine. What each asks of the other is in the two lists below this table. |
| Spec 8, an interrupted line replays its replies | drafted | Spec 8, decision 4 ("Replies are kept in memory while a line runs, and are written only when it stops") asks for a test, with no I/O, of whether any policy can apply to a call. Decision 9 here gives `decisions.guarded`. It asks for a step for each verb a line's host calls and a `via` that can name a line: decisions 2 and 6. This spec asked two things of it, and both are met. A resumed line carries its `via`: spec 8, decision 14 ("A resume starts a fresh machine and a fresh host, and answers from the journal until it runs out") enters `decisions.in_line(Line(line, cwd))` with the record's text and directory. A denied command can print a policy's reason: spec 8, decision 18 ("A denial reaches the machine as a refusal with its own words, and its command exits as it does for `Permission denied`") keeps the table `WORDED_REFUSALS`, which decision 14 here adds this spec's kind to. |
| Tools (`@tool`, `/.vfs/bin`) | not written | `RunStep` and its call site exist. The tools spec states how a run's rights are proven before its policies, and adds its own value to the type of `via`. |

**What this spec asks of spec 7, and where it is met.**

1. Awaited inside a policy, `interrupt` and `require_approval` either return at once, because the job holds an answer for that place, or stop the policy with a signal that is a `BaseException` and no `Exception`. Raising it writes nothing. Met by spec 7, decision 8 ("`interrupt(message, schema, *, details=None)` stops its policy by raising a `BaseException`, and returns the answer once the job has it"): the signals are `Interrupted` and `AnswerRefused`.
2. An asking context around each policy, so that an interrupt is filed under the policy's name. Met by the same decision. `Run` is one frozen value of `src/vfs/jobs/asking.py`, and it is what `judge` takes as `run`. `asking(run, step, policy_name)` returns the context manager the coroutine enters around each policy, whose value says afterwards whether a stop was raised inside it. A call site with no run passes `None`, and `asking` then makes the run of a first call. `asking.py` imports `vfs.decisions` and never `vfs.judging`.
3. Given the step, a policy's name and its `Interrupted`, the job is stored and the interrupted result returned. Met by spec 7, decision 6 ("The job is committed before the interrupted result is returned"), decision 12 ("The interrupted result is a `Result` with one fatal entry of the kind `vfs.interrupted`, and it carries the job") and `store_job` of decision 37 ("A line's job uses the same record, states and claim, and spec 8 supplies what is saved and how it is carried on").
4. An answer nobody asks for again never runs the step. Met by spec 7, decision 20 ("A resume runs the policies again with the answers the job has, and the run ends in one of seven ways"), its last row. A stop that a policy caught is recorded by the asking context: spec 7, decision 8, "A policy that swallows the stop".
5. `require_approval` marks the decision it returns for a person's "no" with the interrupt's id. Met by spec 7, decision 11 ("`require_approval(message, *, details=None)` is `interrupt(message, Approval)` turned into a decision that remembers which answer it came from"). The refusal for it is spec 7, decision 27 ("A denial and a cancel are the kinds `vfs.interrupt.denied` and `vfs.interrupt.cancelled`, and their words name the principal that answered by its name").
6. A resumed step is judged again by the judging coroutine and passes the gate again. Met by spec 7, decision 20, and by decision 22 ("The saved step is carried out as its caller, with rights judged again, and with the etags the preview saw as `if_match`"), which dispatches through the kernel's own path for the verb. This spec first asked that the rights proof be asked again too. Spec 7 leaves the caller's rights to the storage when the verb runs, and decision 10 here now says so. The two sentences this spec asked of those decisions are in them: spec 7, decision 20, takes the policies from `fs._chosen(type(step))`, and decision 22 calls the step's public verb with `step.parameters()` inside `decisions.within(fs)`. The reads of a preview are made inside `decisions.within(fs)` too (spec 7, decision 13, "The preview is computed once, as the caller, for seven verbs, and every part of it is bounded").
7. `interrupt` reached in a job of the system authority fails the step. Met by spec 7, decision 30 ("A job of the system authority is never interrupted, and a step that would interrupt it fails with the rule's words").
8. A job that a session's policy judged is resumed with that session's policies. Met by spec 7, decision 33 ("A job its session's policies judged is resumed through a handle that carries policies of the same names"), from the names the verdict of decision 13 here reports.

**What spec 7 asks of this spec, and where it is met.** Its Builds on asks for ten things.

| It asks for | Here |
|---|---|
| A `Step` with `verb`, `paths`, `authority` and `via` that turns into JSON and back into an equal value, bytes as base64 | Decision 21 |
| A canonical form in which each body stands as its sha256 | Decision 21 |
| One judging coroutine, called for the first run and for every resume, that reports allow, a denial by a policy, a denial by an answer with its interrupt's id, a stop with the first raiser in policy order, or a refused answer | Decision 13 |
| Policy names that are unique among those asked about one step | Decisions 9 and 17 |
| The names of the session's policies that were shown the step | Decision 13, `Verdict.of_session` |
| A module for `Step` that imports nothing from `vfs.results` | Decision 2 |
| A `Decision` that can carry an interrupt's id, set only by `require_approval` | Decision 12 |
| Failing closed for a policy that returns after its `interrupt` raised the stop | Decision 15 |
| No policy run for the system authority | Decision 18 |
| The caller's access judged before any policy is asked | Decision 10, for a first call of a change. Not for a read, a restore's verdict on a row, or a resume. "Needs no other spec meets yet" says why. |

## Terms

- **Verb.** One of the 25 operations in `Op` (`src/vfs/ops.py:38`), such as `edit`.
- **Step.** One verb about to run, with the arguments the kernel has checked, as a typed value that cannot be changed. One step is no verb: a rewind that puts files back (decision 23).
- **Step class.** The Python class of the steps of one verb, such as `EditStep`.
- **Group.** A base class that several step classes share. `Mutation` is the one group.
- **Policy.** An `async` function the host writes and marks with `@policy`. It takes a step and returns a decision.
- **Decision.** What a policy returns: allow, or deny with a reason.
- **Registry.** The ordered collection of policies a file system holds.
- **Call site.** The one place in a verb's path through the kernel where its policies are asked.
- **Gate.** The checks the kernel makes with no storage: the arguments, the path, the mount's capabilities, the reserved paths and the permission maps (`_gate_params` and `_gate_entry` in `src/vfs/base.py`).
- **Rights gate.** The first thing a storage does inside a mutating verb: it resolves the caller's rights and judges every path the verb names (`_gate` and `WriteGate.targets` in `backend.py`).
- **Rights proof.** One call on the storage, `admits`, that runs a verb's rights gate and nothing after it.
- **Fail closed.** A guard that breaks refuses. Fail open is the opposite: a guard that breaks lets the work through.
- **The system authority.** `Authority.system()`, the caller that stands for the host's own code.
- **Line.** One call of `cli`: a line of bash whose every file access is a call of a public verb.
- **Signal.** What `interrupt` raises to stop a policy. Spec 7 has two, `Interrupted` and `AnswerRefused` (spec 7, decision 8).
- **Judging coroutine.** The one coroutine that asks every policy typed for a step and reports what they decided (decision 13).
- **Pass.** One asking of every policy typed for a step. A step that is interrupted and resumed has more than one pass.
- **Statement.** A SQL statement other than `BEGIN`, `COMMIT`, `PRAGMA`, `SAVEPOINT`, `RELEASE` and `ROLLBACK`.

## What the code does today

| Fact | How it is known |
|---|---|
| No step class, no `@policy`, no `Decision` and no `policies=` argument exist in `src/`. | Run: a search of `src/vfs` for each name finds none. |
| Every public verb calls `_gate_params` first. A wrong argument is refused `invalid` before anything else is looked at. | Read, `src/vfs/base.py:2690-2703`, and each verb, such as `:820` and `:990`. |
| The table `PARAMS` holds 25 verbs and 142 rows. `RULES` holds 22 shape rules and `VALUE_RULES` holds 8. | Run. |
| The table has two readers in the tree: the gate, and the test that every verb's signature names the table's parameters. A third, a schema projection, is named in the module's docstring and does not exist in `src/`. | Read, `src/vfs/params.py:3-9`, `tests/test_params.py:28`. Run: a search for the projection finds only the docstring. |
| The kernel's gate does not know who is calling. It judges the mount's capabilities and the permission maps. | Read, `src/vfs/base.py:32-34` and `:2705-2755`. |
| A caller's rights are judged by the storage, inside the verb's own transaction, as that transaction's first reads. | Read, `src/vfs/storage/backends/database/backend.py:714-719` (write), `:761-766` (edit), `:791-797` (delete), `:922-927` (mkdir), `:1418-1428` (move and copy). |
| On SQLite a mutating verb holds the database's one writer lock from its first read to its commit. | Read, `backend.py:1380-1388`. |
| A one-file `write` issues 8 statements as the system authority and 15 as a named caller whose rights are cached. Of the 7 more, 5 are the rights gate's reads, 1 is the fence's read before the commit, and 1 is the insert of the version's subjects. A 10,000-entry rewrite issues 20 as the system authority and 25 as that caller. | Run, on a SQLite file. |
| The storage already answers one rights question outside any verb: `holds`, which the kernel asks before a mount change. It judges a level at a path. It reads no row, so it knows neither a row's owner nor its label. It issues 3 statements. | Read, `src/vfs/storage/protocol.py:469-489`, `src/vfs/mounts.py:355-373`, `rights_reads.py:45-55`. Run. |
| A storage that keeps grants and cannot answer `holds` refuses the mount change `unsupported`. A storage that declares no grant verb is not asked. | Read, `src/vfs/mounts.py:372-375`. |
| A read's rights are a filter over rows. The storage resolves the caller, refuses an unnamed caller where the posture wants a name, and then answers under a view. A row the caller may not see is `not_found` from the body. | Read, `backend.py:1197-1251`. |
| A `restore` gives its verdict on a row when it reads that row, inside its body. | Read, `backend.py:824-862`. |
| `cli` is not an op. Each request of a line is answered by one public verb, called with the line's authority. Nothing tells that verb it was made by a line. | Read, `src/vfs/ops.py:15-19`, `src/vfs/shell/host.py:353-367`, `:377`, `:421`, `:430`, `:471-493`. |
| A line never runs as the system authority. | Read, `src/vfs/shell/host.py:216-218`. |
| The line `cat /a; echo x > /b; rm /c` makes seven calls of public verbs: `stat`, `read`, `stat`, `stat`, `write`, `stat`, `delete`. The line `echo hi` makes none. A `cat` that is refused prints its error, the line goes on to `|| echo fallback`, exits 0, and keeps the refusal as one warning. | Run, in round two, once the extension was rebuilt. |
| A chained `glob` or `grep`, one given rows in hand, calls the kernel's own public `stat` or `read` for a fact a row lacks. | Read, `src/vfs/chain.py:99` and `:150`. |
| `run` routes, and no storage that ships answers it. | Read, `src/vfs/storage/protocol.py:390`. `backend.py` has no `run` method. |
| The synchronous face owns one loop on one thread. A verb called from that thread is refused `invalid` and never waited on. A call's task runs in a copy of the caller's context. | Read, `src/vfs/sync.py:94-96` and `:691-698`. |
| An error kind degrades to its parent by its dotted prefix, for the renderer's hint and for the exception a caller raises. The shell maps a refusal to a host error by the exact kind. | Read, `src/vfs/results/kinds.py:311-329`, `src/vfs/exceptions.py:88-99`, `src/vfs/shell/host.py:94-102` and `:505`. |
| The fields of an `Entry` and of an `Edge` can be assigned after construction. An `Observation` and an `EditOperation` refuse it. Freezing `Entry` by configuration alone breaks its construction, because its validators assign `ext` and other fields. | Run. |
| The storage is handed values the kernel made before it dispatches: a copy of each entry (`without_mount` returns a new object even at `/`), and a new `Edge` for each edge. | Read, `src/vfs/base.py:2486` and `:2572`. Run. |
| Under `asyncio.timeout`, a coroutine that waits past the limit raises `TimeoutError`, and its own `except Exception` cannot catch it. A coroutine that holds the loop past the limit and then returns raises nothing, and the scope's `expired()` is false. A coroutine that catches the cancellation and returns raises nothing, and `expired()` is true. A cancel from the caller leaves the scope as `CancelledError`. | Run. |
| In the interpreter, one read of a context variable with one dictionary lookup takes 66 ns. A frozen value of five fields takes 0.3 µs to build. One `await` of a function that returns at once, under `asyncio.timeout`, takes 1.5 µs. A tuple of the paths of 10,000 entries takes 0.3 ms to build and 80 KB. One prefix test over those 10,000 paths takes 0.45 ms when nothing matches. | Run. Figures for the cost section, never for a test. |
| `src/vfs/base.py` is 3,090 lines, which is its entry in the size list. | Read, `tests/lint/allowlist.py:27`. |

## The problem

A host has no way to put a rule of its own in front of a verb. Access rules say who may do what. They cannot say "a change under `/contracts` stops for a person", or "no delete this week".

Three things stand in the way of adding one.

- **A verb's arguments would be described twice.** The gate reads them from a table of rows. A policy needs them as typed attributes. Two descriptions drift.
- **There is no place after the rights check and before the work.** The kernel's gate does not know the caller. The storage judges the caller inside the transaction that then does the work. A host function cannot run there: on SQLite it would hold the one writer lock while it ran.
- **A guard written by a host can break.** The Cedar study ran a guard that raised an error: the engine skipped it and the request was allowed (`cedar.md`, section B). Cedar can afford that because it proves a validated policy cannot raise. A Python function has no such proof.

## Decisions

### 1. A step, a policy and a decision are values about one call, and add no primitive

Article 1 of the constitution allows five first-class things, and requires each to have a path. A step has no path. It is a value the kernel builds about a call and drops when the call ends, as an `Authority` is. A policy is code the host holds, and it is not stored. A decision is a return value. This spec stores nothing: it adds no table, no column and no record, on any engine.

A step composes two things the constitution already has: the paths of the namespace, and the arguments of an operation on it.

The other articles, as touched. Article 2: a policy's refusal is a `Result`, and its kind is in the family the taxonomy calls `PermissionDenied` (decision 14). The refusal tells a caller not to retry, so no caller is left to guess. Article 4: the one new call on a storage, `admits`, is a declared protocol, and a storage that keeps grants and lacks it is refused out loud (decision 11). Article 5: nothing here writes, so no write path gains a conflict mode, and a call that is cancelled while a policy is asked is cancelled whole.

Reason: the overview rules that a session, a turn and a job are records and not primitives, and the things in this spec are not even records.

### 2. Each verb has one step class, and that class is the one description of the verb's arguments

A new leaf module, `src/vfs/steps.py`, holds one frozen dataclass for each of the 25 verbs. The name of a class is the verb's name in capitalised words with `Step` after it. Each class has one field for each parameter of its verb except `authority`, and the field carries what the table's row carries today.

```python
@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EditStep(Mutation):
    """An ``edit`` that is about to run."""

    verb: ClassVar[Op] = "edit"
    path: Path | None = param("path", doc="the file to edit")
    old: str | None = param("str", doc="sugar form: text to find")
    new: str | None = param("str", doc="sugar form: replacement text")
    edits: tuple[EditOperation, ...] | None = param("edits", doc="native form: sequential, atomic EditOperation list")
    observations: tuple[Observation, ...] | None = param("observations", doc="row-addressed targets")
    replace_all: bool = param("bool", nullable=False, default=False, doc="replace every match of old")
```

- `param(kind, *, name=None, required=False, nullable=True, minimum=None, maximum=None, choices=None, default=None, doc="")` returns a dataclass field whose default is `default` and whose metadata holds the `ParamSpec` of today.
- `ParamKind`, `ParamSpec` and `param` move to `steps.py`. `steps.py` imports the standard library, `vfs.ops`, `vfs.authority`, `vfs.paths` and `vfs.storage.grants`, and names model types only under `TYPE_CHECKING`. It imports nothing from `vfs.results`, so the result envelope may import a step.
- `params.py` imports the classes and builds `PARAMS` from them when it is imported: for each verb, the rows of its class's fields in the order they are written, then the `authority` row. `RULES`, `VALUE_RULES`, `param_violation` and every name `params.py` exports today stay where they are. No `ParamSpec(` call is left in `params.py`.
- `STEPS: Final[dict[Op, type[Step]]]` in `steps.py` maps each verb to its class.
- The derived table equals the table it replaces, row for row: each row's name, kind, bounds, choices, default and words unchanged. That table holds 25 verbs and 142 rows at `6dae6a1d`. It holds 150 once spec 1's decisions 6, 7 and 17 have landed: two rows leave `write`, and ten join five verbs, `restore` among them. Round two had 148 here, written before spec 1 gave `restore` its pair. The gate, its messages and the signature test are untouched.

Three verbs take a scope parameter named `paths`: `glob`, `grep` and `search`. Every step has a core attribute of that name (decision 4), and the two do not mean the same thing when the verb is given rows in hand. On those three classes the field is `roots`, and its row keeps the name `paths` through `param(..., name="paths")`.

| Class | Verb | Group | Its own attributes |
|---|---|---|---|
| `ReadStep` | `read` | | `path`, `observations`, `columns` |
| `StatStep` | `stat` | | `path`, `observations`, `columns` |
| `LsStep` | `ls` | | `path`, `observations`, `after`, `limit`, `columns` |
| `TreeStep` | `tree` | | `path`, `max_depth`, `after`, `limit`, `columns` |
| `GlobStep` | `glob` | | `pattern`, `roots`, `observations`, `ext`, `ext_not`, `globs_not`, `kind`, `max_count`, `after`, `limit`, `columns` |
| `GrepStep` | `grep` | | `pattern`, `roots`, `observations`, `ext`, `ext_not`, `globs`, `globs_not`, `case_mode`, `fixed_strings`, `word_regexp`, `invert_match`, `before_context`, `after_context`, `output_mode`, `max_count`, `allow_scan`, `columns` |
| `SearchStep` | `search` | | `query`, `limit`, `roots`, `observations`, `ext`, `ext_not`, `globs`, `globs_not`, `columns` |
| `TraverseStep` | `traverse` | | `method`, `path`, `observations`, `depth`, `edge_types`, `edge_types_not`, `minimal`, `limit`, `columns` |
| `GrantsStep` | `grants` | | `path` |
| `RunStep` | `run` | | `path`, `arguments`, and the property `tool`, the last segment of `path` |
| `WriteStep` | `write` | `Mutation` | `entries`, `path`, `content`, `data`, `if_version`, `if_versions`, `if_absent`, `append`, `parents` |
| `EditStep` | `edit` | `Mutation` | `path`, `old`, `new`, `edits`, `observations`, `replace_all` |
| `DeleteStep` | `delete` | `Mutation` | `path`, `observations`, `cascade` |
| `RestoreStep` | `restore` | `Mutation` | `path`, `observations` |
| `SweepStep` | `sweep` | `Mutation` | `path` |
| `MkdirStep` | `mkdir` | `Mutation` | `path`, `parents`, `exist_ok` |
| `MkedgeStep` | `mkedge` | `Mutation` | `edges`, `source`, `target`, `edge_type`, `provenance` |
| `RmedgeStep` | `rmedge` | `Mutation` | `edges`, `source`, `target`, `edge_type` |
| `MoveStep` | `move` | `Mutation` | `src`, `dest`, `moves` |
| `CopyStep` | `copy` | `Mutation` | `src`, `dest`, `copies` |
| `GrantStep` | `grant` | `Mutation` | `path`, `principal`, `level` |
| `RevokeStep` | `revoke` | `Mutation` | `path`, `principal` |
| `SetPostureStep` | `set_posture` | `Mutation` | `path`, `posture` |
| `AddMemberStep` | `add_member` | `Mutation` | `group`, `member`, `path` |
| `RemoveMemberStep` | `remove_member` | `Mutation` | `group`, `member`, `path` |

The table above lists the attributes as the tree has them at `6dae6a1d`. The classes are written from the table as it stands when this spec is built, and spec 1 is built first. By spec 1, decision 6 and decision 7, `WriteStep` then has `if_match` and `if_matches` in place of `if_version` and `if_versions`, and `EditStep`, `DeleteStep` and `MoveStep` have `if_match` and `if_matches` too. By spec 1, decision 17, so has `RestoreStep`. Their fields are of spec 1's kinds `etag` and `etags`, and either may hold spec 1's mark `ABSENT`, the string `"absent"` (spec 1, decision 18).

One class is no verb's: `RewindStep`, which decision 23 adds. It is in none of the table's rows and has no row in `PARAMS`.

All 28 classes are exported from `vfs` by name, as the guide imports them.

`verb` is a `str` on `Step`. On the 25 classes above it is an `Op`. On `RewindStep` it is `"rewind"`.

| Way to hold the description | Verdict |
|---|---|
| The table stays, and the classes are written beside it, with a test that the two agree | Rejected. That is two descriptions, which is what the test would exist to police. |
| The classes are made from the table when the module is imported | Rejected. A type checker and an editor cannot see an attribute made that way, so `step.old` would be untyped. |
| The classes are written by hand, each field carries its row, and the table is built from them | Chosen. |

Reason: a policy's author reads `step.old` in an editor and a type checker checks it, which needs a class written in the source. The gate needs rows. Building the rows from the fields leaves one place where a parameter is named, typed, bounded and worded.

### 3. `Step` is every step, and `Mutation` is the one group

`Step` is the base class of every step class. `Mutation` is the base class of the 15 whose verb is in `WRITE_GATED_OPS` (`src/vfs/ops.py:98`): the ten that change the file tree, and the five that change who may see it. Neither base class has a `verb`, and neither is ever built.

Round two adds a sixteenth class under `Mutation`: `RewindStep`, the rewind that puts files back (decision 23). `Mutation` is therefore the fifteen verbs and `RewindStep`, as the ruling for this spec has it.

The guide lists seven changes under `Mutation`: a write, an edit, a delete, a move, a copy, a new directory and a restore. The other eight are an edge made or removed, a sweep, a grant, a revoke, a posture, and a member added or removed.

`RunStep` is in no group. A run of a tool is not a change to the file tree and not a read (`EXEC_OPS`, `src/vfs/ops.py:89`).

No group is made for the reads. A policy for several reads names them in a union.

Reason for the fifteen: `WRITE_GATED_OPS` is the set a read-only mount refuses, so it is the project's one answer to "what changes something". A policy that guards `/contracts` and is typed `Mutation` must see a grant on `/contracts`, because a grant there changes who may read the contracts. Reason for no read group: its natural name, `Read`, sits one word from `ReadStep`, and no policy is known that needs every read and nothing else. A group can be added later without changing any policy that exists.

### 4. Every step carries `verb`, `paths`, `subtree`, `authority`, `via` and `touches`

| Attribute | Type | What it holds |
|---|---|---|
| `verb` | `str` | The verb's name, one of `Op`, or `"rewind"` for the one step that is no verb (decision 23). It is set on the class. |
| `paths` | `tuple[Path, ...]` | Every path the step names, as the kernel sees it, with the mount's path in front. In the order named, with nothing removed. |
| `subtree` | `bool` | Whether the step acts on everything beneath its paths. |
| `authority` | `Authority` | The caller. Never `None`: a call that names none carries the kernel's default authority, or the anonymous one. |
| `via` | `Line \| None` | The line that made the step, or `None` for a direct call. Decision 6. |
| `touches(path)` | `bool` | Whether the step reaches `path`. |

What `paths` holds, by verb:

| Verbs | `paths` |
|---|---|
| `read`, `stat`, `ls`, `edit`, `delete`, `restore`, `traverse` | `path`, or the path of each row in `observations` |
| `tree`, `sweep`, `mkdir`, `run`, `grant`, `revoke`, `grants`, `set_posture`, `add_member`, `remove_member` | `path` |
| `write` | The path of each entry. In the single form, `path`. |
| `move`, `copy` | For each pair, its source and then its destination |
| `mkedge`, `rmedge` | For each edge, its source and then its target |
| `glob`, `grep`, `search` | Each of `roots`, or the path of each row in `observations`. With neither, `/` alone, because the call reaches every mount. |

What `subtree` holds, by verb:

| `subtree` is true | `subtree` is false |
|---|---|
| `delete` with `cascade`; `restore`; `move`; `copy`; `sweep` of a path that is not a trash view; `grant`, `revoke`, `set_posture`; `ls`, `tree`; `glob`, `grep`, `search` over roots or over nothing | `read`, `stat`, `write`, `edit`, `mkdir`, `mkedge`, `rmedge`, `traverse`, `run`, `grants`, `add_member`, `remove_member`; `delete` without `cascade`; `sweep` of a trash view; `glob`, `grep`, `search` over rows in hand |

`touches(path)` is true in two cases.

1. A path the step names is `path`, or lies beneath it.
2. `subtree` is true, and `path` lies beneath a path the step names.

`path` is checked as every path is, by `resolve_path`. A string that is not an absolute path raises `ValueError`, which fails the policy closed (decision 15). `/contracts2` is not beneath `/contracts`: the test is on whole segments. `touches("/")` is true for every step that names a path.

The guide defines `touches` by the first case alone. Under that rule a `delete("/legal")` that cascades does not touch `/legal/contracts`, a `move("/legal", "/old")` does not, and neither does a `grep` of the whole tree. A policy that guards a folder would miss the calls that reach every file in it. A probe confirmed that the root itself is not such a case: the path check refuses a change of `/` before any policy could be asked.

A graph walk follows edges to wherever they lead inside its mount, and `touches` cannot know where. `TraverseStep` names its starting paths only. A policy that guards reads by path treats a `TraverseStep` by its type.

Reason for `subtree` as a public attribute: the kernel already holds this fact for the permission maps (`_reaches_beneath`, `src/vfs/base.py:3079`), `touches` needs it, and "a recursive delete needs a person" is a rule a host will write. Where the kernel's fact and this one differ, this one is the wider: a `restore` brings back everything beneath a directory, and a listing names what is beneath its path. A guard that asks once too often is the safe error.

### 5. A step is built after every check the kernel makes by itself, only when a policy will see it, and it cannot be rebound

- **When.** A step is built at the call site of decision 10, after the gate has passed. A call the gate refuses builds none. A call no policy is typed for builds none. A call of the system authority builds none.
- **From what.** The values the gate admitted. A path the verb names directly, which is `path`, `src`, `dest`, `source`, `target` and each of `roots`, is the `Path` it resolved to. A sequence is a tuple. A mapping is a read-only view (`types.MappingProxyType`): a run's `arguments`, and `if_versions` today or `if_matches` once spec 1, decision 6, has landed. A parameter the caller left out holds its default. A value inside a model or a pair is as the caller gave it, and `paths` holds the resolved form of every path.
- **As the caller gave the call.** An `edit` given `old` and `new` has those two and `edits` is `None`. A `write` given `path` and `content` has those and `entries` is `None`. `step.parameters()` returns the verb's arguments as a mapping from parameter name to value, without the ones that hold their default, so that `getattr(fs, step.verb)(**step.parameters(), authority=step.authority)` is the same call.
- **Frozen.** Every class is `frozen=True`, so assigning an attribute raises `FrozenInstanceError`. An `Observation` and an `EditOperation` in a step refuse assignment too.
- **Two models in a step can be changed in place.** An `Entry` and an `Edge` accept assignment today. A policy that assigns to one changes the caller's own object. It does not change what this call hands its storage, because the kernel made the storage's copies before the step was built (`src/vfs/base.py:2486`, `:2572`). Freezing the two models is a change to `src/vfs/models/` of its own: a probe that froze `Entry` by configuration could not construct one.
- **No body is copied.** A `WriteStep` holds the caller's `Entry` objects by reference.
- **Its `repr` holds no body.** `repr(step)` is the class name, the first path, the number of paths and the caller's actor kind. A policy that logs a step logs no content.

A step for a 10,000-entry write is one tuple of 10,000 references for `entries` and one for `paths`: about 0.3 ms and 160 KB, with no statement and no copy of an entry. `touches` reads `paths` in order and stops at the first that matches. A call that matches nothing reads all 10,000, about 0.45 ms for each path a policy asks about.

Reason: a policy that reads an attribute must be able to trust it, so the step is built from what the gate admitted and not from what the caller sent. Building it only when a policy will see it is what makes a file system with no policy pay nothing.

### 6. `via` is the line that made the step, and the line itself is not a step

```python
@dataclass(frozen=True, slots=True)
class Line:
    text: str    # the line as cli was given it
    cwd: str     # the directory the line started in
```

- **Each verb a line makes is a step.** A `cat` is a `ReadStep`. A redirect is a `WriteStep`. An `rm` is a `DeleteStep`. A `grep -r` that the indexed verb serves is a `GrepStep`. Each has `via` set to the `Line`. A step of a direct call has `via` of `None`. The shell also probes: a probe found that `cat /a; echo x > /b; rm /c` makes four `stat` calls beside its `read`, its `write` and its `delete`, and each is a `StatStep` of the line.
- **Reads inside a line are steps like any other.** A file system with only `Mutation` policies asks nothing about them.
- **The line itself is shown to no policy.** There is no step class for `cli`, and no policy is asked before a line starts. A line that makes no verb, such as `echo hi`, reaches no policy.
- **A verb's own inner calls are part of its step.** A chained `glob` or `grep` calls the kernel's `stat` or `read` for a fact a row lacks (`src/vfs/chain.py:99`, `:150`). Those calls are shown to no policy. The outer step names the same rows in `paths`.

How the kernel knows. A new module, `src/vfs/decisions.py`, holds one context variable and the value it carries.

```python
@dataclass(frozen=True, slots=True)
class CallContext:
    via: Line | None = None                    # set by run_line for the length of the line
    policies: PolicySet | None = None          # a session's own, decision 17
    asking: Asking | None = None               # the kernel that is asking, and the policy's name
    inner: object | None = None                # the kernel whose call sites ask nothing here
    proving: object | None = None              # the kernel whose call sites prove and stop, decision 24
```

`Asking` is a frozen value of two fields, `kernel` and `policy`. `run_line` enters `decisions.in_line(Line(line, cwd))` around the whole line. The call site of a chained `glob` or `grep` enters `decisions.within(self)` around its filter. `within` has two more users, which decision 23 names: a step that is carried out by calls of public verbs after it was judged whole. The context is read once at each call site. A task the kernel starts inherits it, and the synchronous face runs each call in a copy of its caller's context (`src/vfs/sync.py:94-96`), so both faces carry it.

A line that goes through a session reaches the kernel through spec 3's guarded router (spec 3, decision 17, "The shell's host sends what a line is shown and what it changes through the guarded router, and its probes through the kernel"). The router calls the same public verbs inside the same context, so its steps carry the line's `via`.

`interrupt` takes no argument that names its job, so spec 7 keeps a context of its own for the policy that is being asked: the asking context of spec 7, decision 8. The judging coroutine sets both around each policy: this spec's mark, which decision 19 reads, and spec 7's. The two are not merged, because this one exists from landing 2 and spec 7's holds a job's answers.

The type of `via` is `Line | None` in this spec. The tools spec adds a value for a step that a tool's function makes.

| Is the line a step? | Verdict |
|---|---|
| Yes, a class for `cli` that policies typed `Step` see before the line starts | Rejected. A policy on a line can only read its text. Three products in the approval study say of their own rules over shell text that they are not a boundary (`approval-modes.md`, section 3). |
| No, each verb is the step | Chosen. |

Reason: in the overview's model a line is a job of many steps, not a step. The decision record "the gate order is the execution policy" (pin 1) rules that no verdict is passed on the command text, because the gates fire on every verb a command resolves to. That holds, and policies join those gates.

### 7. `@policy` checks the function when it is decorated and returns a `Policy`

`policy` is in `src/vfs/decisions.py`. It is used bare, or with keywords.

```python
@policy
async def contracts_need_a_person(step: Mutation) -> Decision: ...

@policy(name="frozen", timeout=30.0)
async def contracts_are_frozen(step: DeleteStep | MoveStep) -> Decision: ...
```

It raises `TypeError`, with words that name the function and the rule, when:

- the function was not defined with `async def`;
- it does not take exactly one argument;
- the argument has no annotation, or the annotation cannot be resolved by `typing.get_type_hints`;
- the annotation is neither `Step`, nor a subclass of it, nor a union whose every member is one.

It raises `ValueError` when `name` is empty or `timeout` is not a number greater than zero. All of this happens where the function is defined, before any file system exists.

It returns a `Policy`, a frozen value.

| Attribute | What it holds |
|---|---|
| `name` | The function's `__name__`, or the `name` keyword. It is what a refusal and an interrupt name. |
| `covers` | The step classes the policy sees: every one of the 26 in `STEP_CLASSES` (decision 23) that is a subclass of a member of the annotation. |
| `timeout` | The seconds one asking may take. `POLICY_TIMEOUT_SECONDS`, which is 10.0, unless the keyword set it. |

`await a_policy(step)` calls the function, so a policy is tested alone. Two `Policy` values are equal when they wrap the same function. A ready-made policy is equal to another made with the same arguments (decision 20).

The return annotation is not checked. What a policy returns is checked each time it is asked (decision 15).

Reason: the Temporal study found a validator of the wrong shape that was accepted for years and never ran, so every update passed it (`temporal.md`, section A, commit `419ee16`). A guard that silently does nothing is the worst failure a guard has, so the shape is checked at the first moment it can be.

### 8. The type of a policy's argument is the only thing that chooses the steps it sees

A policy is asked about a step when the step's class is in its `covers`. With `RewindStep` counted, as round two has it, `Step` covers all 26, `Mutation` covers 16, `DeleteStep | MoveStep` covers 2, and `Mutation | RunStep` covers 17.

A registry keeps a table from each step class to the tuple of policies that cover it, in the order they were added. The table is built when the registry changes. A call looks its verb's class up once. When the tuple is empty, the call builds no step, asks no storage for a rights proof, and awaits nothing.

A policy that is not typed for a step is never called for it, not even to be told no.

No path is part of a policy's scope. A policy that cares about a folder tests `step.touches(...)` in its body.

Reason: the type is already in the source, a type checker reads it, and the choice costs one dictionary lookup. The Cedar study notes that its open-source engine evaluates every policy on every request, and that a registered policy for one operation should cost nothing on another (`cedar.md`, section E).

### 9. A file system keeps its policies in the order they were added, and a change is seen by the next step

```python
AsyncVirtualFileSystem(..., policies: Iterable[Policy] = ())      # and VirtualFileSystem
fs.add_policy(policy: Policy) -> None
fs.remove_policy(policy: Policy) -> None
fs.policies() -> tuple[Policy, ...]
```

- The constructor takes `policies` after `default_authority`, and keeps them in the order given.
- `add_policy` puts a policy last. Adding a policy that is already there changes nothing.
- `remove_policy` takes one out. Removing a policy that is not there raises `ValueError` with its name, as `list.remove` does.
- `policies()` returns them in order.
- An item that is not a `Policy` raises `TypeError`: "a policy is a function marked with @policy".
- Two different policies with one `name` raise `ValueError`. A name is what an interrupt is filed under, so one registry never holds it twice.
- None of the three is a coroutine, and none does I/O. They are plain methods on both faces, as `mounts()` and `capabilities()` are, and the twin test names them.
- `VirtualFileSystem.wrap(fs)` keeps the registry of the kernel it wraps.
- `decisions.guarded(registry)` says whether the registry or the call context holds any policy. It is two truth tests and no I/O. It is the test spec 8, decision 4 ("Replies are kept in memory while a line runs, and are written only when it stops") asks for: a line asks it once, when it starts, to learn whether it can be interrupted at all.
- The three methods manage a collection the kernel keeps, so they return plain values and raise, as ruling 5 of round two has it and as `add_mount` does today.
- The names follow `documentation/maintainers/how-we-name.md`: `add` and `remove` for a thing that joins or leaves a collection the file system keeps, and a plural noun for the collection.

The registry is a frozen value, `PolicySet`: the tuple, and the table of decision 8. A change builds a new one under a `threading.Lock` and replaces the kernel's reference in one assignment. A call reads the reference once, at its call site.

So a change made while calls run is seen by every step that reaches its call site after it. A step that is already being asked finishes with the policies it started with. A line asks each of its steps afresh, so a policy added in the middle of a line judges the line's later steps. Two threads that add at once both land.

Each process holds its own registry. Nothing about a policy is stored.

Reason: the guide's surface is the constructor argument and two methods. A copy on each change keeps the path every call takes free of a lock.

### 10. A policy is asked after the kernel's gate, after the caller's rights are proven for a change, and before any storage is asked to act

There is one call site for each shape of dispatch, and each calls one kernel method, `_admit`. It sits after the last check that can refuse the call with no storage, and before the first call that acts on a storage.

| Shape | Verbs | Where, in today's `src/vfs/base.py` |
|---|---|---|
| One path | `read`, `stat`, `ls`, `tree`, `edit`, `delete`, `restore`, `sweep`, `mkdir`, `traverse`, `run` | `_route_single`, after `_gate_entry` and the cursor's check (`:1864-1870`), before `_dispatch_read` |
| Rows in `observations` | The same verbs, and `search` over rows in hand | `_dispatch_grouped_observations`, after every group has passed the gate (`:1920-1924`), before the mounts are asked |
| A grant verb | `grant`, `revoke`, `grants`, `set_posture`, `add_member`, `remove_member` | `_route_grant`, after `_gate_entry` (`:1963-1965`) |
| A search of mounts | `glob`, `grep`, `search` with roots or with none | `_route_fanout`, after the hop is taken and the plan is made (`:2024-2031`), before a call or a probe is built |
| Pairs | `move`, `copy` | `_route_two_path`, after the loop over pairs (`:2349-2378`), before the mounts are asked (`:2380`) |
| Entries | `write` | `_route_entry_batch`, after the entries and the keys of `if_versions` are checked (`:2472-2501`), before the mounts are asked (`:2503`) |
| Edges | `mkedge`, `rmedge` | `_route_edge_batch`, after the loop over edges (`:2552-2595`), before the mounts are asked (`:2598`) |
| A chained filter | `glob`, `grep` over rows in hand | In `glob` and `grep`, after the rows are checked (`:1380-1382`, `:1489-1491`), before the filter runs |

A call that names no row, such as a `write` of no entries, returns before its call site and is no step.

What `_admit` does, in order. The first step that returns ends it.

1. Read the registry and the call context. Find the policies typed for this verb's class: the file system's, then the session's that are not already among them (decision 17).
2. If the context says a policy of this kernel is being asked and the caller is not the system authority, refuse `invalid` (decision 19).
3. If the context says this kernel's call sites ask nothing here (`decisions.within`, decisions 6 and 23), or no policy is typed for the class, or the caller is the system authority: return, and the verb runs.
4. Build the step.
5. For a `Mutation` that is a verb's, ask each mount the step reaches for its rights proof, at the same time, with the arguments the verb will be sent (decision 11). If any refuses, return the refusals, merged as the verb would merge them. No policy is asked.
6. Ask the policies, through the judging coroutine (decision 13). Return the refusal its verdict gives. From landing 3, when the verdict holds a stop, hand it to spec 7 and return the interrupted result spec 7 makes (spec 7, decision 6, "The job is committed before the interrupted result is returned"). Otherwise return and let the verb run.

Step 1 is also a kernel-private call of its own, `fs._chosen(cls)`, which returns the policies and the names of those that came from the call context. Spec 7's `resume` calls it for the step it rebuilt (decision 23).

So for a change, the order of refusals is: a wrong argument, a wrong path, a busy mount point, an unsupported verb, a reserved path, a read-only map, the caller's rights, and only then a policy. A change the caller may not make is refused in the storage's own words, and no policy is called for it.

**No transaction, connection or lock is held while a policy is asked.** The rights proof is a read that has ended. The verb's own transaction has not begun.

**The verb judges the caller's rights again**, inside its transaction, as it does today. Rights can change between the proof and the work, and the proof is never trusted in place of the gate.

What is and is not proven before a policy is asked:

| Step | Proven first |
|---|---|
| `write`, `edit`, `mkdir`, `delete`, `sweep`, `move`, `copy`, `mkedge`, `rmedge`, `grant`, `revoke`, `set_posture`, `add_member`, `remove_member` | Everything the verb's rights gate judges: the caller's rights on every path the step names. |
| `restore` | That the caller is named where the posture wants a name (`backend.py:824-830`). The verdict on each deleted row is given when the body reads the row (`backend.py:832-862`), which is after its policies. |
| Every read, and `grants` | Nothing. A read's rights are a filter over rows, applied as the storage answers (`backend.py:1197-1251`). A policy may be asked about a read whose answer is then `not_found`. |
| `run` | Nothing in this spec. No storage that ships answers `run`. The tools spec states the proof. |
| A chained `glob` or `grep` | Nothing. It reads no storage for a row that carries what it needs, and the inner read it may make is judged as any read is. |
| A `RewindStep` | Nothing by `_ask`: the step has no rights gate of its own. Spec 5 proves each batch of its plan first, through `fs._proof` (decision 24), and takes out of the plan an entry the proof refuses (spec 5, decision 13). Each change is judged again by the storage when it is dispatched, as the session's authority (spec 5, decision 9, "Steps run in batches through the router's verbs, as the session's authority, below the session and below the policies"). |
| A step carried on by a resume | Nothing before its policies. Spec 7, decision 20 ("A resume runs the policies again with the answers the job has, and the run ends in one of seven ways") runs the judging coroutine on the saved step, and spec 7, decision 22 ("The saved step is carried out as its caller, with rights judged again, and with the etags the preview saw as `if_match`") then dispatches it, where the storage judges the caller's rights. So a caller who lost a right while its job waited is refused by the verb, after the policies were asked again. |

A refusal the body of a verb finds after its gate is found after the policies were asked: a row a rival changed inside the window, and a mapped path of a move that an earlier pair of the same call closed (`authorized.py:363-391`).

The proof is a promise about a first call. Round two narrowed it by the last row: the proof needs the mounts a route resolved, and a resume has a saved step and no route. The person who answers a job is judged by spec 7's own rule, before any policy runs (spec 7, decision 17, "A job may be resumed by the system authority, and by an authority that holds `read_write` on every path the step names").

The cases, walked:

| Case | What happens |
|---|---|
| Two calls at once | Each reads the registry once and builds its own step. One policy may be asked by both, interleaved on the loop, so a policy must be safe to run twice at once. No lock of VFS is held by either. |
| Two processes | Each holds its own registry and asks its own policies. Nothing is shared and nothing is stored. A job stopped in one and resumed in the other is decision 16. |
| A crash between the proof and the asking, or between the asking and the verb | Nothing has been written by the call or by this spec. The call is gone with its process, and there is no record to repair. |
| A cancelled call | Decision 15. Nothing has been dispatched. |
| SQLite, Postgres and the in-memory storage | Decision 11. The same gate code runs on all three. |
| A 10,000-entry batch | One step, one proof, one asking of each policy. Decisions 5 and 11. |
| The synchronous face | Decision 19. The policy runs on the facade's loop. |
| The system authority, and the anonymous caller | Decision 18. The first is shown to no policy, and the second to every one typed for its step. |

Two more things are left where they are. A listing spends its hop of the call's budget inside `_dispatch_read`, after its call site, as it does after the gate today. A default-authority call logs one more `DEBUG` record on `vfs.authority` for each mount its proof asks, because the proof goes through `_call_storage` (`src/vfs/base.py:2881`).

| Where the policy runs | Verdict |
|---|---|
| Inside the storage, between its rights gate and its work | Rejected. A host function would run inside the verb's transaction. On SQLite that holds the one writer lock for as long as the function takes, and a function may take ten seconds. The working agreement holds a lock other callers need for a commit and no longer. |
| Before the storage, with no proof of rights | Rejected. A caller with no right to a file could make a person be asked about it, and could fill the approval queue with questions about changes that would be refused anyway. |
| Before the storage, and the rights are proven only when a policy denies or interrupts | Not chosen. It issues no extra statement for a step every policy allows. It calls the policy function for a step the caller may not make, which the guide says does not happen. It is listed under "Choices for the owner". |
| Before the storage, after one read that runs the verb's own rights gate | Chosen. |

Reason: the guide promises that a call the caller has no right to make is refused before any policy sees it, and the approval study gives the reason that matters most: people who are asked often approve 93 to 97 percent of what they are shown (`approval-modes.md`, section 6), so a question about a change that could never land costs attention and buys nothing. A read that has ended is the only form of that check which holds no lock while a host's function runs.

### 11. The storage answers one new question, `admits`, with its rights gate and nothing else

```python
@runtime_checkable
class SupportsAdmits(Protocol):
    async def admits(self, op: Op, *, authority: Authority | None = None, **arguments: Any) -> Result: ...
```

- `arguments` are the ones the verb's own method takes, as the kernel will send them.
- A successful result with no row means the verb's rights gate would let the call through now. A failed result carries the refusals that gate would give, in the same words, on the same paths.
- It writes nothing, reads no body, and takes no lock. It runs as `holds` runs, in one read session at the isolation a read verb runs at (`backend.py:1346-1378`). On Postgres and on a SQLite file it waits on no writer.
- It is not a routed verb, as `holds` is not. It is in no capability set and no mount can mask it.

In `DatabaseStorage` each mutating verb's gate becomes one function that the verb and `admits` both call. Nothing about what a gate judges changes.

| Verb | The gate `admits` runs |
|---|---|
| `write` | `_gate` at the write's rungs, the additive ones under `if_absent` or `append`, then `targets(paths, "upsert", parents=...)` (`backend.py:712-719`) |
| `edit` | `targets(..., "modify")` (`:761-766`) |
| `mkdir` | `targets([path], "create", parents=...)` (`:922-927`) |
| `mkedge`, `rmedge` | The sources as `"modify"`, and for `mkedge` the targets as `"read"` (`:967-974`, `:996-1001`) |
| `delete` | `targets(..., "modify")`, then `subtrees` under `cascade` (`:791-797`) |
| `sweep` | Its gate (`:885-896`) |
| `restore` | `_gate`, then `anonymous` (`:824-830`) |
| `move`, `copy` | The transfer's gate, with `admit_destinations` (`:1418-1428`) |
| `grant`, `revoke`, `set_posture` | `grant_refusal`, which each body calls first (`rights.py:1021`, `:1050`, `:1137`), under the cached gate. The revision bump the write takes as its first statement is not taken. |
| `add_member`, `remove_member` | The refusal of any caller but the system authority (`rights.py:1452-1453`) |

The kernel sends it through `_call_storage`, which gains one branch for it, so its paths come back with the mount's path in front as a verb's do.

A storage that does not have `admits`:

- If its declared capabilities hold no grant verb, it keeps no rights. The kernel asks it nothing and goes on to the policies.
- If they hold a grant verb, the step is refused `unsupported`, at the mount's path, with the detail "the storage here keeps grants and cannot judge a step before a policy is asked". No policy is asked. This is the rule `rights_refusal` already has for `holds` (`src/vfs/mounts.py:372-375`).

Three storages ship, and all three are `DatabaseStorage`. The in-memory storage serves `admits` on its one connection, behind the host lock, as it serves any read.

The size of a proof is bounded as the gate is. Its reads over the step's paths are chunked by `membership_budget`. For a named caller with cached rights a one-file `write` adds four statements: three reads for the caller's rights (`vfs_principal_revisions`, `vfs_relabels`, `vfs_grants`) and one for the target rows. The verb's own gate reads a fifth, the mount revision its fence compares, and a proof commits nothing, so it has no fence and skips that read (`authorized.py:142`). A 10,000-entry `write` adds the same four at the engines' 32,668-key chunk.

| Way to prove rights | Verdict |
|---|---|
| `holds(path, level)` at the verb's rung, once for each path | Rejected. It knows no row. A caller who holds `add` and owns the file may edit it, by the owner floor, and `holds` at `contribute` would refuse them. It is also one call for each path. |
| The verb's own gate, as a question | Chosen. It is the same code, so it cannot disagree with the verb except by a change made in between. |

**`admits` beside spec 7's `holds_all`.** Spec 7, decision 18 ("A storage answers the rights question for many paths in one call") adds `holds_all(paths, level, authority)` to `SupportsHolds`. The two answer different questions, and both stay.

| | `admits` | `holds_all` |
|---|---|---|
| Asked about | The caller of a step | The person who answers a job |
| The question | Would this verb's rights gate let this call through | Does this authority hold one named rung at every path |
| Reads rows | Yes: a row's owner, its label, whether it is there | No: grants and postures only |
| The rung | The verb's own, which differs for a new name, an occupied one and a deleted one | `read_write`, whatever the verb |

`holds_all` cannot serve the proof, for the reason `holds` cannot: it knows no row, so it would refuse an owner editing its own file. `admits` cannot serve spec 7's rule: the person who answers is not making the call, and an `edit` is admitted at `contribute`, a rung below the `read_write` that spec 7, decision 17, requires of whoever resumes.

Reason: the only judgement that never refuses a call the verb would allow is the verb's own.

### 12. A `Decision` allows or denies, and nothing else

```python
@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reason: str | None = None

    @classmethod
    def allow(cls) -> Decision: ...
    @classmethod
    def deny(cls, reason: str) -> Decision: ...
```

- `Decision.allow()` takes nothing.
- `Decision.deny(reason)` takes a reason, which is a string that is not blank. A reason of another type raises `TypeError`, and a blank one raises `ValueError`. Raised inside a policy, either fails it closed.
- The reason is carried whole. The renderer folds its newlines, as it folds every message's (`src/vfs/results/render.py:103-105`).
- There is no third value. A policy that needs a person does not return something: it awaits `interrupt()` or `require_approval()`, which spec 7 owns, and returns a decision once it has the answer.
- Landing 3 adds one field, `answered: str | None`, which is `None` for a decision a policy made by itself. `require_approval` sets it, to the id of the interrupt that was answered, on the decision it returns for a person's "no" (spec 7, decision 11, "`require_approval(message, *, details=None)` is `interrupt(message, Approval)` turned into a decision that remembers which answer it came from"). Nothing else sets it. The id is spec 7's (its decision 9, "An interrupt's id is derived from the job, the place, the raiser and a count, and an answer is used only for the question it answered").

`Decision` is exported from `vfs`.

Reason: Cedar's stable decision has two values, and its third outcome lives in a separate interface that has been rewritten once (`cedar.md`, sections B and F). The guide takes the same line for a different reason: a stop is not something a function can return and then continue from. It is an `await` that either gives the answer or ends the function.

### 13. Every policy typed for the step is asked, one after another in the order added, and the strictest answer wins

The order is the file system's policies in the order they were added, then the session's in the order they were given (decision 17). They are asked one after another. One policy has returned, or has been stopped, before the next is called.

The asking is one coroutine, the judging coroutine. Round two gave it a module of its own, `src/vfs/judging.py`.

```python
async def judge(
    step: Step,
    policies: Sequence[Policy],
    *,
    of_session: Collection[str] = (),
    run: object | None = None,
) -> Verdict: ...
```

It is called for a first call, by the kernel's call site, and for every resume, by spec 7's `resume` (spec 7, decision 20). `run` is spec 7's `Run`, one frozen value of `src/vfs/jobs/asking.py`: the job's id when there is one, the step's place, the answers on record, the answer just given, and whether the job may be interrupted (spec 7, decision 8). The kernel's call site has no run and passes `None`, and spec 7's `asking` then makes the run of a first call. A resume passes the run it built. This spec passes it through unread. The coroutine returns a `Verdict` of plain values and builds no `Result`: `steps.py`, `decisions.py` and `judging.py` import nothing from `vfs.results`. The kernel turns a verdict into the verb's result.

Why a module of its own. Spec 7 puts `require_approval` in `src/vfs/jobs/asking.py`, and it returns a `Decision`, so that module imports `decisions.py`. From landing 3 the judging coroutine sets spec 7's asking context and catches its two signals, so it imports `jobs/asking.py`. With the coroutine inside `decisions.py`, the two modules would import each other. The order is `steps`, `decisions`, `jobs/asking`, `judging`, `base`.

```python
@dataclass(frozen=True, slots=True)
class Refusal:
    policy: str                    # the name of the policy that denied or failed
    reason: str | None = None      # its reason, for a denial
    failed: str | None = None      # how it failed, decision 15
    answered: str | None = None    # the interrupt whose answer denied, landing 3

@dataclass(frozen=True, slots=True)
class Verdict:
    refusals: tuple[Refusal, ...] = ()   # in the order asked; empty when nothing denied
    asked: tuple[str, ...] = ()          # the name of every policy asked, in order
    of_session: tuple[str, ...] = ()     # those that came from the call context
    stopped: tuple[str, BaseException] | None = None   # landing 3: the first policy stopped, and its `Interrupted`
    unfit: BaseException | None = None                 # landing 3: an `AnswerRefused`
```

`Refusal` and `Verdict` are in `judging.py`. The five things spec 7 asks the coroutine to report are these fields: allow is a verdict with nothing in it, a denial by a policy is a `Refusal`, a denial by an answer is a `Refusal` whose `answered` is the interrupt's id, a stop is `stopped`, and a refused answer is `unfit`. `of_session` is what spec 7, decision 33 ("A job its session's policies judged is resumed through a handle that carries policies of the same names") stores on the job.

From landing 3, around each policy the coroutine enters `asking(run, step, policy.name)`, spec 7's context manager, which sets the asking context and resets it when the policy returns or raises (spec 7, decision 8). Its value says afterwards whether a stop was raised inside it, which is how a swallowed stop is found (decision 15). It catches `Interrupted` and `AnswerRefused` there. An `AnswerRefused` ends the asking at once: the answer does not fit its schema, no later policy is asked, and spec 7 answers `vfs.invalid` and leaves the job as it was (spec 7, decision 19, "An answer is checked by the policy's own `interrupt`, during the run that `resume` makes, and a wrong answer writes nothing").

Each asking has one of four outcomes.

| Outcome | How it comes about |
|---|---|
| Allow | The policy returned `Decision.allow()`. |
| Deny | The policy returned a denial. |
| Failed | Decision 15. It counts as a denial. |
| Interrupt | The policy was stopped by spec 7's `Interrupted`. Landing 3. |

After the last policy:

1. **If any denied or failed, the step is refused.** The result carries one error for each policy that denied or failed, in the order they were asked. No person is asked. No job is stored. Every signal of this pass is dropped.
2. **Otherwise, on a resume, if nobody asked for the answer the resume carried, the step is not run** (decision 16). Spec 7 sees this and ends the job (spec 7, decision 20, last row).
3. **Otherwise, if any was stopped by a signal, the job is interrupted for the first of them in order.** The verdict's `stopped` holds that policy's name and its `Interrupted`. The kernel hands spec 7 the step and the verdict, spec 7 stores the job with `store_job` (spec 7, decision 37), and the kernel returns the interrupted result of kind `vfs.interrupted` (spec 7, decision 12). The signals of later policies are dropped. Each is raised again, by its own policy, in a later pass. Spec 7 has the same rule from its side (spec 7, decision 25, "A job waits on one interrupt at a time, in the order the policies were added").
4. **Otherwise every policy allowed, and the verb runs.**

Every policy is asked in every pass, whatever an earlier one decided. A policy that awaits an interrupt does nothing to the ones after it: they are still asked, in order. That is how a later denial is found before a person is troubled.

A walk through three policies, `a`, `b` and `c`, where `a` and `c` each need a person:

| Pass | `a` | `b` | `c` | What happens |
|---|---|---|---|---|
| The call | stopped | allows | stopped | Interrupted for `a`. `c`'s signal is dropped. |
| The resume with a yes for `a` | allows | allows | stopped | Interrupted for `c`, on the same job. |
| The resume with a yes for `c` | allows | allows | allows | The verb runs. |

Had `b` denied in the first pass, the step would be refused then, and nobody asked.

The longest a pass can take is the sum of its policies' timeouts.

| How they are asked | Verdict |
|---|---|
| All at once, with `asyncio.gather` | Rejected. The answer would be the same, since deny beats interrupt beats allow in any order. The order of what the policies log, and of what they read, would differ from run to run. |
| One after another, stopping at the first denial | Rejected. The guide says each step is shown to every policy typed for it, and a caller is better told every reason at once than one at a time. |
| One after another, every one | Chosen. |

Reason: the approval study found that every confusion it recorded came from an order, a priority or a pattern over shell text, and that "the strictest wins" was the one rule no source reported as confusing (`approval-modes.md`, section 3). The Temporal study found a change to the order in which waiting code was run that was turned on and then off again within ten days, because resumed work behaved differently (`temporal.md`, section F). So the order is fixed here, in words, before any job is stored that depends on it.

### 14. A denial refuses the whole step under one new kind, `vfs.permission_denied.policy`

`ErrorKind` gains one member, `policy_denied`, with the value `vfs.permission_denied.policy`. Its row in `KIND_CONTRACTS`:

| Field | Value |
|---|---|
| Phrase | `Refused by a policy` |
| Retry class | `never` |
| Hint | `A rule of this file system refused this step, so nothing was changed. Do not retry it or make the change another way.` |
| What `path` means | `the one path the refused step names; None when it names several, because the policy judged the step whole` |

One error is made for each policy that denied.

- **Kind.** `vfs.permission_denied.policy`, severity `error`, not retryable.
- **Path.** The step's path when it names exactly one. `None` when it names several.
- **Message.** The phrase, then `: `, then the policy's reason, then ` (policy <name>)`.
- **Data.** `{"policy": <name>}`, and `"paths": <how many>` when the step names several.

The result has `ops` of the verb, no row, and `success` false. Nothing was dispatched to any mount, so a step over three mounts is refused on all three.

From landing 3, a denial whose decision carries `answered` is a person's answer and not the policy's own. Its error is the one spec 7 builds, of kind `vfs.interrupt.denied`, and it takes the same place in the order (spec 7, decision 27, "A denial and a cancel are the kinds `vfs.interrupt.denied` and `vfs.interrupt.cancelled`, and their words name the principal that answered by its name").

Ruling 6 of round two confirms the kind: `vfs.permission_denied.policy` is this spec's, and the other eight cite it. Spec 5 raises it from a rewind a policy denies (spec 5, decision 13).

An example, for a policy named `contracts_are_frozen` that returned `Decision.deny("Contracts are frozen until Friday.")` for an edit:

```text
ERROR /contracts/acme.md: Refused by a policy: Contracts are frozen until Friday. (policy contracts_are_frozen) — A rule of this file system refused this step, so nothing was changed. Do not retry it or make the change another way. (retry: never)
```

Inside a line, the verb's refusal becomes a host error as any refusal does. `_HOST_ERROR` in `src/vfs/shell/host.py` gains the new kind, mapped to `permission_denied`, so the command prints "Permission denied" and exits non-zero, and the line goes on to its next command. The refusal is kept on the line's result as a warning, with the reason. A probe in round two ran the shape of this with a rights refusal: the command printed its error, `|| echo fallback` ran, the line exited 0, and the result kept one warning.

Spec 8 gives a line a way to print a refusal's own words: the reply `denied` (spec 8, decision 18, "A denial reaches the machine as a refusal with its own words, and its command exits as it does for `Permission denied`"). The refusals the host words are named in one table in `host.py`, `WORDED_REFUSALS`, and spec 8 leaves this spec free to add its kind.

Round three decides that it does. `vfs.permission_denied.policy` is a row of `WORDED_REFUSALS`. The words are what spec 8 gives every worded refusal: the entry's message, an em dash, and its hint, with no path and no retry class. The host reads the first failure of the verb's result, so where several policies denied, the command prints the first one's reason, and the line's warnings keep them all. So `rm /contracts/acme.md` under the example above prints:

```text
rm: cannot remove '/contracts/acme.md': Refused by a policy: Contracts are frozen until Friday. (policy contracts_are_frozen) — A rule of this file system refused this step, so nothing was changed. Do not retry it or make the change another way.
```

It exits 1, as it does for `Permission denied`, and the line goes on. The row is one line of `host.py`. It is added by whichever of spec 8's landing and this spec's second landing is built later. Until the table exists, the command prints "Permission denied", by the row of `_HOST_ERROR` above, which stays as the code the kind maps to.

Reason for the row: an agent reads a command's error where the command failed. "Permission denied" tells it to look for access, which is the wrong thing to look for, and the reason is the one thing it can act on.

A caller that raises on failure gets what `permission_denied` raises, by the family rule (`src/vfs/exceptions.py:88-99`).

| Kind | Verdict |
|---|---|
| `vfs.permission_denied` itself | Rejected. Its hint tells the caller to ask for access. Access is not what is missing, and a grant would not help. |
| A new top-level kind | Rejected. Article 2 of the constitution closes the taxonomy to seven families, and this refusal is of the family "the caller is known and may not". |
| A child of `vfs.interrupt` | Rejected. The guide keeps that prefix for what a person decided in answer to an interrupt. |
| `vfs.permission_denied.policy` | Chosen. A reader that does not know it falls back to `permission_denied`, which is true. |

Reason: a caller must be able to tell three things apart without reading prose: no right, a rule of the host, and a person's "no". Each has a kind of its own, and the first two share a parent because both mean the caller may not.

### 15. A policy that raises, returns no decision or passes its timeout denies

Each asking is wrapped. What the wrapper does with what happens:

| What the policy did | Outcome | `data["failed"]` | What is logged on `vfs.decisions` |
|---|---|---|---|
| Returned a `Decision` in time | That decision | | Nothing |
| Raised an `Exception` | Failed | `"raised"` | One `ERROR` with the traceback |
| Returned anything that is not a `Decision`: `None`, `True`, a string | Failed | `"returned"` | One `WARNING` with the type's name |
| Was still waiting when its timeout passed | Failed | `"timeout"` | One `WARNING` |
| Returned after its timeout, having held the loop without waiting | Failed | `"timeout"` | One `WARNING`, and once for each policy name a second that says it held the event loop |
| Caught the timeout's cancellation and returned | Failed | `"timeout"` | One `WARNING` |
| Was stopped by spec 7's `Interrupted` | Interrupt | | Nothing |
| Caught spec 7's `Interrupted` and returned anything. Landing 3. The asking context records that a stop was raised (spec 7, decision 8, "A policy that swallows the stop") | Failed | `"swallowed"` | One `WARNING` |
| Raised spec 7's `AnswerRefused`. Landing 3 | The asking ends, and the verdict carries it (decision 13) | | Nothing |
| Was cancelled because its caller was | `CancelledError` goes on to the caller | | Nothing |
| Raised `KeyboardInterrupt` or `SystemExit` | It goes on to the caller | | Nothing |

- **The timeout.** `POLICY_TIMEOUT_SECONDS: Final = 10.0`, in `src/vfs/decisions.py`. A policy sets its own with `@policy(timeout=...)`. It is ten seconds because that is the wall every matching stage already runs under (`WALL_TIME_BUDGET`, `src/vfs/deadline.py:36`), and it sits inside the thirty seconds a line has.
- **How it is kept.** The asking runs under `asyncio.timeout(policy.timeout)`, with a `Deadline` taken before it. A probe showed two cases the timeout scope does not raise for: a policy that never waits and returns late, and a policy that catches the cancellation. So after the policy returns, the decision is thrown away when the scope's `expired()` is true or the `Deadline` has passed.
- **A cancel is told from a timeout** by where it came from. The caller's cancel leaves the scope as `CancelledError` and is raised on. Nothing has been dispatched, so the storage is whole.
- **A policy that holds the event loop** cannot be stopped. VFS runs on one loop, and a function that does not wait gives nothing else a turn: every call on that kernel waits while it runs. VFS refuses its answer when it comes, and says so once in the log. The guide tells a host to run such work with `asyncio.to_thread`.

The refusal is of the kind in decision 14. Its message never holds the exception's text, which could hold a body or a secret. The detail after the phrase is one of:

| `failed` | Detail |
|---|---|
| `"raised"` | `the policy <name> failed, so the step was refused` |
| `"returned"` | `the policy <name> returned no decision, so the step was refused` |
| `"timeout"` | `the policy <name> did not decide within <seconds> seconds, so the step was refused` |
| `"swallowed"` | `the policy <name> went on after it asked a person, so the step was refused` |

A log record names the policy and the verb, and never the step's arguments.

Reason: the Cedar probe ran a guard that raised, and the request was allowed. A guard that can be defeated by making it fail is not a guard. Each of the ways a Python function can fail to answer is therefore given the strictest answer, in the one place every asking passes through.

### 16. A policy is asked again when its job is resumed, and an answer nobody asks for again never runs the step

A resumed step is a new pass. Every policy typed for the step is asked, as for a first call, by the same judging coroutine (spec 7, decision 20, "A resume runs the policies again with the answers the job has, and the run ends in one of seven ways"). `interrupt` now returns the answer on record, so the policy that asked goes on to its decision. The rights proof is not asked again at a resume: decision 10 says why, and the storage judges the caller when the saved step is dispatched.

What a policy may rest on:

- **What it asks, and whether it asks, must be a function of the step and of the answers it has been given.** The same step, with the same answers so far, reaches the same next question.
- **It should not read the clock, a random number, or state that changes, to decide whether to ask.**
- **Its decision may rest on anything.** A policy that allowed yesterday and denies today, because a freeze began, denies. The decision at the resume is the one that counts, because that is when the work is done.

VFS cannot prove a function pure. It finds the one departure that would be dangerous, and treats every other as a new judgement.

| At the resume | What the kernel does |
|---|---|
| The policy that asked asks the same thing | `interrupt()` returns the answer. The policy decides. |
| The policy that asked now denies before it asks | Denied. A denial is the strictest answer. |
| Another policy now denies | Denied. |
| A policy that allowed before now needs a person | The job is interrupted again, for that policy. |
| The policy that asked allows without asking again | **The step is not run.** Every policy allowed, and nobody asked for the answer the resume carried. |
| The policy that asked is not among those asked: it was removed, or the process that resumes never added it | **The step is not run**, for the same reason. |
| The policy that asked asks something else at that place | The recorded answer is dropped and the job is interrupted with the question now asked (spec 7, decision 9, "An interrupt's id is derived from the job, the place, the raiser and a count, and an answer is used only for the question it answered"). |

The two rows in bold are one rule: **an answer that is no longer asked for never lets the step through.** This spec states the rule, because it follows from asking again. Spec 7 keeps the answers, so it is spec 7 that sees an answer go unused, ends the job, and words the refusal. That is the last row of spec 7, decision 20: the job is `finished`, the answer is not recorded, and `resume` returns `vfs.conflict`, "the question this job was waiting on is no longer asked, and nothing was carried out". The caller makes the call again, and it is judged by the policies as they now are. The judging coroutine's part is small: it reports that every policy allowed, and names the policies it asked.

Why the rule is needed. A person answered "no". If the policy that asked is gone, or has changed its mind about asking, nothing reads that "no", every other policy allows, and the step would run against the person's answer.

So a job is resumed in a process that has the policies of the process that stopped it. A resume by a process with no policies does not run the step unguarded. The job ends, and the step is not run.

Reason: the approval study found this defect in a shipped library: a predicate that ran again at the resume and returned false, after which "the reviewer's answer is skipped and the tool runs, even if they rejected it" (`approval-modes.md`, section 3). The LangGraph study found that nearly every interrupt bug of two years had one shape, an answer that reached a question it was not for, or no question at all (`langgraph.md`, section F). Asking again is right because rights and rules can change while a job waits. Refusing an unread answer is what makes asking again safe.

### 17. A session's policies are asked after the file system's and can only add

- A handle is given its policies by `fs.session(..., policies=[...])` (spec 2, decision 2, "`fs.session(authority=None, id=None, *, strict=True, policies=())` returns a handle and does no I/O"). They are code, so they are not stored with the session, and each handle carries the ones it was given, in its slot `_policies`, public as `policies`, a tuple (spec 2, decision 3 and decision 4).
- Spec 2, decision 4, refuses a non-empty `policies` with `ValueError`, "policies are not served yet", until this spec lands. This spec removes that line and the test `test_a_non_empty_policies_is_refused_until_policies_exist`.
- The constructor spec 2, decision 4, names is `decisions.policy_set(policies, beside=registry)`. It builds a `PolicySet`, with the `TypeError` of decision 9 for an item that is no `Policy` and the `ValueError` below for a name used twice. It does no I/O, so spec 2's rule for `fs.session` holds. The handle calls it once and keeps the set in its slot `_policies`, and `session.policies` returns the set's policies as a tuple, in order (spec 2, decision 4). The function keeps its last results by the tuple it was given, so a handle asked for at the top of every request with the same policies builds the set once.
- Each verb the handle forwards, and its `cli`, runs inside `decisions.with_policies(that_set)`. A handle given none enters nothing. Spec 3's guarded router sits between the handle and the kernel and runs inside the same context.
- At the call site the policies asked are the file system's, in order, and then the session's that are not equal to one already there. A policy in both is asked once, in the file system's place.
- Two different policies with one `name` cannot both be asked, because an interrupt is filed by name. `fs.session` raises `ValueError` when a policy it is given shares a name with a different one in its own list or in the file system's registry at that moment. When the clash appears later, because a policy was added to the file system afterwards, the step is refused before any policy is asked, with `data["failed"]` of `"duplicate"` and the detail `two policies are named <name>, so the step was refused`.
- A handle has no `add_policy` and no `remove_policy`, and nothing it carries can take a file system's policy out of the asking.

A session can therefore ask for more review and never for less: the strictest answer wins over the union, and the union only grows.

A job that a session's policies judged is resumed through a handle that carries policies of the same names. That rule and its refusals are spec 7's (spec 7, decision 33, "A job its session's policies judged is resumed through a handle that carries policies of the same names"): `fs.resume` of such a job is refused `vfs.invalid`, and so is `session.resume` on a handle whose policies have other names. What this spec gives it is `Verdict.of_session`, the names of the session's policies that were asked about the step, and `handle.policies`, whose names the resume compares.

Until spec 2's handle is in the tree, the rule is built and tested through `decisions.with_policies` itself. The edits to `fs.session` and to the handle's verbs land with whichever of the two specs is built second.

Reason: the decision record "the session law" rules that a session never widens itself (rule 1). The same holds for review: the approval study's nearest precedent says a narrower scope "can add a gate but never remove one" (`approval-modes.md`, section 3).

### 18. No policy is asked about a step of the system authority

When `step.authority.is_system` would be true, `_admit` returns before it builds a step. No policy is called, no rights proof is asked, and nothing is awaited.

- A call that names no authority runs as the kernel's `default_authority`. When that is the system authority, the call is shown to no policy. The warning the kernel logs for such a default (`src/vfs/authority.py:247-258`) gains six words: "...passes every rights check and is shown to no policy".
- A line never runs as the system authority (`src/vfs/shell/host.py:216-218`), so every step of every line is shown to its policies.
- The anonymous caller is not exempt. Its steps are shown as any caller's are.
- A policy cannot interrupt a system job, because it is never asked about one. A tool can try. Spec 7 makes that fail the step with `vfs.invalid` (spec 7, decision 30, "A job of the system authority is never interrupted, and a step that would interrupt it fails with the rule's words").
- A rewind that puts files back as the system authority is shown to no policy either (spec 5, decision 13).

Reason: the system authority stands for the host's own code, which wrote the policies and can remove them. A nightly load of a million files as the system authority must not stop for a person, and must not pay for a rule it is exempt from. The decision record "the session law" names the system actor as the one marked exception (rule 6), and this is the same exception.

### 19. A policy is `async`, runs on the kernel's loop, and calls its file system only as the system authority

- **Both faces.** A policy is an `async` function whether the host uses `AsyncVirtualFileSystem` or `VirtualFileSystem`. `@policy` refuses any other. On the synchronous face it runs on the facade's loop thread, where the kernel runs.
- **Why not a plain function.** It would run on the loop and hold up every call for as long as it took. A plain function that called back into the synchronous face would wait on the thread it is running on. The facade already refuses that call `invalid` so that it does not hang (`src/vfs/sync.py:691-698`), and a policy that needs a file could never read one.
- **What it may call.** The asynchronous kernel, as the system authority: `await fs.read(path, authority=Authority.system())`. That call is shown to no policy, by decision 18, so a policy cannot ask itself.
- **What is refused.** While a policy of a kernel is being asked, a verb called on that kernel as any other authority is refused `invalid`, with the detail `a policy calls its file system as the system authority; this call named another`. A `cli` called there is refused the same way. The policy receives a failed result, as any caller would.
- **Another kernel is its own business.** A policy of one file system may write to a second as any caller. The second asks its own policies.
- **A host that holds only the synchronous face** builds the kernel first and wraps it, `VirtualFileSystem.wrap(kernel)`, and gives its policies the kernel.
- **A policy should not change a file.** It is asked again at each resume, so a change it makes is made again.

| What a policy may call | Verdict |
|---|---|
| Nothing | Rejected. A rule such as "deny while `/freeze` exists" needs one read. |
| Anything, with its inner steps shown to no policy | Rejected. That is a second exemption beside the system authority's, and a way round every other policy. |
| Anything, judged like any call | Rejected. A policy typed `Step` that reads a file as a named caller asks itself about that read, without end, until its timeout. |
| Its own file system, as the system authority only | Chosen. |

Reason: one exemption is easier to reason about than two, and the system authority is the one that already exists.

### 20. One ready-made policy ships, `policies.review(paths=...)`

`src/vfs/policies.py` is a public module, imported as `from vfs import policies`.

```python
def review(*, paths: Sequence[str]) -> Policy: ...
```

- It is typed `Mutation | RunStep`, so it is never asked about a read.
- For a `Mutation`, it finds the first of its paths that `step.touches(...)`. If there is one, it returns `await require_approval(f"A change under {path} needs a person.")`. If there is none, it allows.
- For a `RunStep`, it returns `await require_approval(f"A run of {step.tool} needs a person.")`, whatever its paths are.
- `paths` is required. Each is checked by `resolve_path`, and the list is kept sorted with repeats removed. An empty list, or a string that is not an absolute path, raises `ValueError`. `["/"]` is every path.
- Its `name` is `review(` then its paths joined by `, ` then `)`: `review(/contracts, /finance)`.
- Two calls with the same paths return equal policies, so adding both is adding one.

Nothing else ships. There is no `policies.strictest`, because the registry is the combiner. There is no string such as `policies="review"`. There is no policy that lets every change through that VFS can undo, because no public verb reverts a file to an earlier version yet.

It needs `require_approval` (spec 7, decision 11), so it is built in landing 3.

A `RewindStep` is a `Mutation`, so `review` is asked about a rewind that puts files back, and asks for a person when any file it would put back is under one of its paths.

Reason: the approval study ranks a review scoped by path first, as the one mode every product has and the one the guide teaches, and warns against a default over the whole tree: at the reference deployment that is about 37 questions a person a day, and people who are asked that often approve 93 to 97 percent of what they are shown (`approval-modes.md`, sections 6 and 7). So `paths` has no default.

### 21. A step turns into JSON and back into an equal step, and has one canonical form

```python
step.to_payload() -> dict[str, Any]
Step.from_payload(payload: Mapping[str, Any], *, authority: Authority) -> Step
step.canonical() -> bytes
```

`to_payload` returns JSON-native data: `{"verb": ..., "parameters": {...}, "paths": [...], "subtree": ..., "via": {"text": ..., "cwd": ...} or null}`. The authority is not in it. Spec 7 saves the caller's authority beside it and hands it back to `from_payload`.

`parameters` holds what `step.parameters()` holds, each value written by the kind of its field:

| Kind of field | In the payload |
|---|---|
| A path, a string, an integer, a boolean | The value |
| Bytes, a write's `data` | A string of base64 |
| A sequence of strings | A list. `columns`, a set, is a sorted list. |
| An etag, spec 1's kind `etag` | The value, a string of twenty characters, or spec 1's mark `ABSENT`, the string `"absent"`. An etag is compared and never taken apart (spec 1, decision 2, "An etag is twenty hexadecimal characters: a keyed digest of the mount, the entry and the version"). |
| A mapping: a run's `arguments`, and `if_versions` today or `if_matches`, spec 1's kind `etags`, once it has landed | An object. A run's `arguments` that hold a value JSON cannot carry make `to_payload` raise `ValueError` naming the key. |
| `observations` | Each row as `model_dump(mode="json")` gives it. The model already writes bytes as base64 (`src/vfs/models/entry.py:447`). |
| `entries` | Each entry as `model_dump(mode="json")` gives it, with `data` written as base64 by this method. A probe found that the dump raises `UnicodeDecodeError` for a bytes body that is not UTF-8, and that with `data` as base64 a text entry, a bytes entry and a directory each come back equal. |
| `edits` | Each as `{"old": ..., "new": ..., "replace_all": ...}` |
| `moves`, `copies` | Each pair as a list of two strings |
| `edges` | Each edge as `model_dump(mode="json")` gives it |

`from_payload` finds the class by `verb` in `STEP_CLASSES` (decision 23), reads each field back by its kind, and builds the step. A verb that is not there, or a field of the wrong shape, raises `ValueError`. It does not run the gate. The step is checked when its call is made again.

A `RewindStep` has four fields, a string and three integers, and each is written as it is. Its canonical form is its `verb` and those four.

The fingerprint spec 7 takes over the canonical form is spec 7, decision 26 ("The same step made again by the same caller while its job waits joins that job").

For every class and every form a verb takes, `Step.from_payload(step.to_payload(), authority=step.authority) == step`.

`canonical()` is what a fingerprint is taken over. It returns the UTF-8 bytes of a JSON object with sorted keys and no spare whitespace, holding `verb` and `parameters` alone, with three changes to `parameters`:

- A write's `content` or `data` stands as `{"sha256": <hex>}`, the hash of its bytes.
- An entry stands as its `path`, `kind`, `source`, `mime_type` and `content_hash`. Those are the four columns the write preconditions spec calls an entry's material, and its path. An entry's timestamps are left out: a validator sets them when the entry is made, so the same call made twice would differ by them.
- A row of `observations` stands as its `path`.

`via`, `paths` and `subtree` are not in it. Two calls with the same verb and the same arguments have the same canonical form whether a line made them or not.

A payload holds every body of the step, so making one costs in proportion to the bytes the step carries. A canonical form reads each entry's `content_hash`, which was measured when the entry was made, and hashes only a body given as bare `content` or `data`. Neither is made for a step that is allowed or denied. Spec 7 makes them, for a step it is about to save.

All three are built in landing 1, since they are pure.

Reason: spec 7 saves a stopped step and tells two stopped steps apart by a fingerprint, and the step classes are the one place that knows each verb's arguments. A second description of them in the job's code is what decision 2 exists to prevent.

### 22. Three landings, in this order

1. **The step classes.** `steps.py`, the table built from it, the payload and the canonical form of decision 21, `RewindStep` and `STEP_CLASSES` of decision 23, the exports, the reference page and the glossary term Step. No verb behaves differently. It is built after spec 1's landings, so the table it replaces is spec 1's.
2. **Policies that allow and deny.** `decisions.py`, `judging.py`, the registry on both faces, the kind, `admits`, the eight call sites, `_chosen`, `_ask` and `within` of decision 23, failing closed, the system authority's exemption, `via`, the rule for a session's policies, the reference page and the glossary term Policy. Decisions 7 to 15 without the interrupt outcome, and 17 to 19. Where spec 2's handle is already in the tree, this landing also makes the edits of decision 17 to it.
3. **Policies that interrupt.** The fourth outcome of decision 13, the swallowed stop of decision 15, `Decision.answered`, `policies.review`, and the tests of decision 16's rule, which spec 7's code keeps. It is built in the same pull request as spec 7's third landing (spec 7, decision 39, "Four landings, in this order": "Interrupting and resuming a step"), because its code reads spec 7's signals and sets spec 7's context.

Decision 23 was added in round two. It names no landing of its own: its class is in landing 1 and its three calls are in landing 2. Decision 24, added in round three, is in landing 2 with them. The row of `WORDED_REFUSALS` in decision 14 is added by whichever of spec 8's landing and landing 2 is built later.

Reason: each leaves the tree green and is of use alone. The first is a refactor that the second and every later spec can rest on. The second gives a host a deny rule with no job table. The third cannot exist before the thing it reads.

### 23. A step class need not be a verb's: `RewindStep` is one, and a step that is carried out by many calls is judged once

Added in round two, by ruling 7: a step need not be a verb. Spec 5's rewind that puts files back is one step and one job (spec 5, decision 13, "A rewind with files is one step to the policies and one job to an interrupt").

```python
@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class RewindStep(Mutation):
    """A rewind that is about to put a session's files back."""

    verb: ClassVar[str] = "rewind"
    before: str          # the turn id the rewind goes back to before
    session_key: int     # the session, by its key
    turn_number: int     # the number of the turn named by `before`
    through: int         # the newest change row the plan covers
```

- **Its fields.** `session_key` is the key of spec 2, decision 13 ("`vfs_sessions` holds one row per session, under a key that is never used twice"). `turn_number` is the number of spec 4, decision 2 ("`vfs_session_turns` holds one row per turn"). `through` is the id spec 5 reads when it selects the session's change rows (spec 5, decision 6, "A rewind with files walks the session's change rows newest first and undoes each one"). These three are what spec 5, decision 13, saves for the job, and `before` is the turn id spec 5 asks the step to carry.
- **Its core attributes.** `paths` is every path the plan would change: the path an entry is at and the path it goes back to. `subtree` is false, because the plan names each path. `authority` is the session's. `via` is `None`.
- **Its group.** It is a `Mutation`. A policy typed `Mutation` or `Step` is asked about it. A policy typed for one verb, such as `DeleteStep`, is not.
- **It has no row in the parameter table.** `rewind` is no verb and has no gate of its own. Its fields are plain dataclass fields, and `parameters()` returns the four.
- **`STEP_CLASSES`.** `STEPS` stays the 25 classes of the verbs, keyed by `Op`, because the parameter table is built from it. `STEP_CLASSES: Final[dict[str, type[Step]]]` holds all 26, keyed by `verb`. `covers` (decision 7) and `from_payload` (decision 21) read `STEP_CLASSES`. A later step that is no verb joins it.

A step that no verb's call site builds needs a way to be judged, and a step that is carried out by many verb calls needs those calls not to be judged again. Three kernel-private members give both. None is public, and none is on a session.

| Member | What it does | Who calls it |
|---|---|---|
| `fs._chosen(cls)` | Returns the policies typed for a step class, the file system's and then the call context's, and the names of those that came from the context. It is step 1 of `_admit` (decision 10). | `_admit`, `_ask`, and spec 7's `resume` for the step it rebuilt |
| `await fs._ask(step)` | Judges a step that was built outside a call site. It is steps 1, 2, 3 and 6 of `_admit`: it asks no rights proof, because the step has no verb whose gate could be run. It returns `None` when the step may go on, and otherwise the result to give back: the refusal of decision 14, or spec 7's interrupted result. | Spec 5, for a `RewindStep` |
| `decisions.within(fs)` | A context in which this kernel's call sites ask nothing: it sets the mark `inner` of decision 6. | The chained `glob` and `grep` (decision 6); spec 5's batches (spec 5, decision 9); spec 7's dispatch of a saved step it has just judged, and the reads of its preview |

Inside `within`, only the policies are skipped. The gate runs. The storage judges the caller's rights on every call, as it always does. So a rewind that a policy allowed can still be refused, entry by entry, by the session's rights as they stand.

What each outcome of `_ask` means for a rewind is spec 5's to say, and spec 5, decision 13, says it: allowed, the steps run; denied, nothing is put back and `rewind` raises with `vfs.permission_denied.policy`; interrupted, nothing is put back and the job is saved.

`within` is a way round the policies, so it is private. It is not exported from `vfs`, no public method enters it, and a policy cannot use it to widen itself: decision 19 refuses a call a policy makes as any caller but the system authority before step 3 of `_admit` is reached.

| How a rewind meets the policies | Verdict |
|---|---|
| Each file put back is shown to the policies as its own write, delete or move | Rejected by spec 5, decision 13: a rollback of 300 files would be 300 interrupts, with the files half put back between them. |
| No policy sees a rewind | Rejected. It changes files, and a policy typed `Mutation` guards changes. |
| One step, of a class of its own | Chosen. |

Reason: the step classes are the one place that says what a policy can be shown, so a thing a policy must see has a class there, whether or not a verb makes it. One private mark for "already judged" serves the chained filter, the rewind and the resumed step, where three specs would otherwise each invent a way round the call site.

### 24. The rights proof can be asked alone, through `fs._proof`

Added in round three. Spec 5, decision 13 ("A rewind with files is one step to the policies and one job to an interrupt") proves each batch of a rollback's plan "by `admits`, with the arguments the batch will send", before `_ask` is called, so that no person is asked about a file the session's authority may not change. `admits` is a storage's method and takes paths as one mount sees them (decision 11). A batch is a call of a public verb, with the kernel's paths, and may reach several mounts. The kernel gives the call that joins the two.

```python
async def _proof(self, verb: Op, /, *, authority: Authority, **arguments: Any) -> Result: ...
```

- It is kernel-private. It is not public, not on a session, and not on the synchronous face.
- `arguments` are the ones the public verb takes.
- It calls the public verb inside `decisions.proving(self)`, a fourth mark in the call context of decision 6: `proving: object | None`, the kernel whose call sites prove and stop.
- With the mark set for this kernel, `_admit` does three things and returns. It asks no policy. For a `Mutation` that is a verb's, it asks each mount the call reaches for `admits`, as step 5 of decision 10 does, whether or not any policy is typed for the verb. It returns the refusals, merged as the verb would merge them, or a result with the verb in `ops`, no row and no error.
- Nothing is dispatched. The verb's own storage method is never called under the mark.
- A call the gate refuses is refused by the gate, as always, before the mark is read.
- For the system authority, and for a verb that is no `Mutation`, it returns the empty result at once. There is nothing to prove.
- A storage that keeps grants and has no `admits` refuses it `unsupported`, by decision 11.

Its refusals name the paths the verb would refuse, in the storage's own words, so spec 5 takes those entries out of its plan and reports each with its refusal.

Its cost is the proof's: four read statements for a batch by a named caller with cached rights, chunked by `membership_budget`, for each mount the batch reaches. Spec 5 has the same figure for each batch of a rollback.

| How a rollback's batch is proven | Verdict |
|---|---|
| Spec 5 resolves each path to its mount and calls the storage's `admits` itself | Rejected. Resolving a path to its mount, and rewriting a batch into each mount's own paths, is what a verb's route does. A second copy would drift from it. |
| The batch's public verb is called, and stops at its call site | Chosen. The gate, the route and the proof are the ones the real call will meet a moment later. |

Reason: the proof is only as good as its agreement with the call it stands for, and the surest agreement is to run that call's own path and stop before the work.

## Cost

Costed against the reference deployment in the working agreement. Statement counts were run on SQLite. Interpreter times are from one probe on one machine and are orders of size.

**What one verb call pays.**

| Case | Awaits added | Statements added | Objects built | Time in the interpreter |
|---|---|---|---|---|
| No policy on the file system, and none in the call context | 0 | 0 | 0 | One context read and one dictionary lookup, about 66 ns |
| Policies exist, and none is typed for this verb | 0 | 0 | 0 | The same |
| A policy is typed for the verb, and the caller is the system authority | 0 | 0 | 0 | The same, and one test |
| A policy is typed for a read, another caller | One for each policy | 0 | One step | About 0.3 µs for the step and 1.5 µs for each policy, and whatever the policy does |
| A policy is typed for a change, another caller | One for the proof, one for each policy | The rights gate's reads: 4 for a one-file write by a named caller | One step | The same, and one read session |

**Per verb call, about 150,000 a day.** About three calls in four are reads. With policies typed `Mutation`, a read adds no statement, no await and no object. That is a counted test.

**Per change made by a caller who is not the system authority.** About one agent call in four changes something: about 37,500 a day, 1.3 a second over the working day and about 5 a second at the peak hour. With one `Mutation` policy installed, each adds 4 read statements: about 150,000 a day, 5 a second on average and 20 a second at peak. A one-file write by a named caller goes from 15 statements to 19. On Postgres that is four more round trips for each change. No row is written, and no lock is taken.

**Per file write, about 1,050,000 a day.** A million of those are the nightly batch. Run as the system authority it is shown to no policy and adds nothing. Run as a named service, each 10,000-file batch is one step: one proof of 4 statements, and one asking of each policy. A policy that calls `touches` for two folders reads 20,000 paths, about a millisecond. A hundred batches a night add 400 statements.

**Per index visit, about 11,000,000 a day.** Nothing. An index pass and a rebuild are the storage's own work and are not verbs, so they make no step.

**Per batch.** One step, whatever its size. The proof's reads are chunked by `membership_budget`, as the gate's are, so no statement grows with the batch.

**Per corpus.** Nothing.

**Per lock.** None is taken and none is held. The proof is a plain read, which waits on no writer on Postgres and on a SQLite file. The in-memory storage serves it on its one connection, in turn, as it serves any read. No transaction is open while a policy is asked.

**What is not bounded by VFS.** A policy's own work. A policy that waits is ended at its timeout. A policy that holds the loop for a second stalls about 20 calls at the peak hour, and nothing in the process can stop it. A step with `n` policies can take the sum of their timeouts.

**Memory.** A registry is one tuple and one table of 26 keys. A step for 10,000 entries is two tuples of 10,000 references, about 160 KB, for the length of the call.

**A rewind that puts files back.** One `RewindStep`, one asking of each policy typed `Mutation` or `Step`, and no rights proof. Its `paths` hold two paths for each entry the plan would change, so a plan of 10,000 entries is a tuple of 20,000 references. The batches it then dispatches run inside `decisions.within`, where each call site returns after the one context read, so 10,000 files put back add no asking beyond the first.

**A resume.** One more pass of the judging coroutine, and no rights proof. Its statements are spec 7's.

## Left as it is

- **A rights proof before a read's policies.** A policy typed for reads is asked before the storage has filtered the read. Proving a read first would run the read twice.
- **The verdict of a `restore` on each row.** It is given in the body, after the policies.
- **A path as part of a policy's scope.** A scope of paths on `@policy` would let the kernel skip the rights proof for a change outside them. With one policy typed `Mutation`, every change by a caller who is not the system authority pays the 4 statements, wherever it is.
- **A group for the reads.**
- **A step for the line.**
- **`Entry` and `Edge` stay changeable in place.** A step is frozen, and two of the models it can hold are not. What spec 7 saves of a step is spec 7's to state, and it is told here that a policy can have changed an entry in place before it interrupted.
- **`run`.** Its step class and call site exist. No storage that ships answers it.
- **`via` for a step a tool's function makes.**
- **A model that answers in a person's place.** A host writes a policy that calls its own model, and returns a denial or awaits an approval when the model fails.
- **Remembered answers.** "Approve for the rest of the session" is the host's, as the approval study recommends.
- **`review_irreversible`.** It waits for a public verb that reverts a file to an earlier version.
- **A policy on a mount.** A policy belongs to a file system or a session. A mount has its permission map.
- **The hop budget of a listing** is spent after its policies are asked.

## Tests

Each is written and seen failing before the code. Counts are of calls to a spied function, of dispatches recorded by `RecorderStorage` (`tests/support/base_doubles.py:32`), or of statements recorded by the `before_cursor_execute` listener on a SQLite file. Never of time. A row of the storage contract runs on every engine leg.

Landing 1, `tests/test_steps.py` and `tests/test_params.py`:

- `test_every_op_has_one_step_class`: `set(STEPS)` equals `ALL_OPS`, 25 classes, each `verb` is its key, and each name is the verb in capitalised words with `Step`. `STEP_CLASSES` holds those 25 and `RewindStep`, 26, each under its `verb`.
- `test_mutation_is_the_write_gated_ops_and_the_rewind`: the verbs of the subclasses of `Mutation` in `STEPS` equal `WRITE_GATED_OPS`, 15, and the subclasses of `Mutation` in `STEP_CLASSES` are those and `RewindStep`, 16.
- `test_the_table_is_built_from_the_step_classes`: `PARAMS` holds 25 verbs and the number of rows the table held before the landing, taken from the tree the landing starts from: 142 at `6dae6a1d`, and 150 after spec 1. The source of `params.py` holds no `ParamSpec(` call, counted as zero. `"rewind"` is no key of `PARAMS`.
- `test_a_rewind_step_names_every_path_of_its_plan`: a `RewindStep` built over a plan of 20 entries has 40 paths, `subtree` false and `via` of `None`; `touches("/contracts")` is true when one of them is under `/contracts`; its payload comes back as an equal step.
- `test_the_scope_of_a_search_keeps_its_parameter_name`: the rows of `glob`, `grep` and `search` each hold one named `paths`, and the three classes each have a field `roots`.
- Every test in `tests/test_params.py` that exists today passes unchanged, the signature test and the refusal messages among them.
- `test_a_step_is_frozen`: assigning each of the six core attributes raises `FrozenInstanceError`, and assigning an item of a `RunStep`'s `arguments` raises `TypeError`.
- `test_paths_and_subtree_of_each_verb`: one case for each of the 25 classes, and for each form a verb takes, asserting `paths` and `subtree` against the two tables of decision 4.
- `test_touches`: a path at, inside, beside (`/contracts2`) and above the one asked; a cascade delete of `/legal` touches `/legal/contracts`; a delete of `/legal` without cascade does not; an unscoped `grep` touches every path; a string that is no path raises `ValueError`.
- `test_parameters_issue_the_same_call`: for one step of each class, `step.parameters()` passed to the verb on a `RecorderStorage` records the dispatch the first call recorded.
- `test_a_ten_thousand_entry_step_copies_no_entry`: `step.entries[i] is entries[i]` for all 10,000, `len(step.paths)` is 10,000, and a spy on `Entry.model_copy` counts zero.
- `test_a_payload_comes_back_as_an_equal_step`: one case for each of the 25 classes and each form a verb takes, a bytes entry that is not UTF-8 and a directory entry among them: the payload passes `json.dumps`, and `from_payload` of it equals the step.
- `test_the_canonical_form_ignores_what_is_not_the_call`: two `write` steps built a moment apart from the same path and body have equal canonical forms; a different body, path or flag gives a different one; the same call with `via` a line and with `via` of `None` gives the same one; the bytes hold the body's sha256 and not the body.
- `test_a_canonical_form_hashes_no_entry_again`: for 10,000 entries a spy on `hashlib.sha256` counts zero.
- `test_a_steps_repr_holds_no_body`: the `repr` of a `WriteStep` whose content is a marker string does not hold the marker.
- `tests/test_package.py`: the 28 classes are exported from `vfs`.

Landing 2, `tests/test_decisions.py`:

- `test_policy_refuses_a_wrong_function`: six cases, each raising `TypeError` with no file system made: not `async`; no argument; two arguments; no annotation; an annotation that is no step; an annotation that cannot be resolved.
- `test_policy_refuses_a_wrong_keyword`: an empty `name`, a `timeout` of zero, a `timeout` that is no number, each `ValueError`.
- `test_the_annotation_sets_what_a_policy_covers`: `Step` covers 26, `Mutation` 16, `DeleteStep | MoveStep` 2, `Mutation | RunStep` 17, and `RewindStep` 1.
- `test_a_decision_has_two_values`: `allow()` and `deny("r")`; `deny("")` raises `ValueError`; `deny(None)` raises `TypeError`.
- `test_the_registry_keeps_its_order`, `test_adding_a_policy_twice_is_one_policy`, `test_two_policies_with_one_name_are_refused`, `test_removing_a_policy_that_is_absent_raises`, `test_an_unmarked_function_is_refused`.
- `test_two_threads_that_add_both_land`: 2 threads, 100 policies each, 200 in the registry.

Landing 2, `tests/base/test_policies.py`, on `RecorderStorage` unless a count of statements is named:

- `test_a_read_adds_nothing_under_mutation_policies`: for each of the 8 read verbs and `grants`, with one `Mutation` policy: the policy is called 0 times, `admits` is called 0 times, no step is built (counted by putting a counting class in place of each class in `STEPS`), and on a SQLite file the read issues the number of statements it issues with no policy.
- `test_a_policy_that_is_not_typed_for_the_step_is_not_called`: policies typed `DeleteStep`, `MoveStep` and `Mutation`, one `edit`: calls are 0, 0 and 1.
- `test_a_step_the_gate_refuses_reaches_no_policy`: eight refusals, one case each: a wrong argument, a path that does not resolve, a reserved path, a read-only map, a masked verb, a busy mount point, a pair that crosses mounts, a closed kernel. In each the policy is called 0 times and `admits` 0 times.
- `test_a_change_the_caller_may_not_make_reaches_no_policy`: on the in-memory storage with a posture of `none`, for 14 verbs, `write`, `edit`, `mkdir`, `delete`, `sweep`, `move`, `copy`, `mkedge`, `rmedge`, `grant`, `revoke`, `set_posture`, `add_member` and `remove_member`: the refusal is the storage's own kind, the policy is called 0 times, and no mutation statement runs.
- `test_a_restore_is_proven_at_its_gate_alone`: an unnamed caller under a posture of `none` is `unauthenticated` and the policy is called 0 times. A named caller with no right on the deleted row has the policy called once, and the verb then refuses.
- `test_a_read_is_shown_to_its_policy_before_it_is_filtered`: a policy typed `ReadStep` is called once for a read of a path the caller's rights hide, `admits` is called 0 times, and the result is `not_found`.
- `test_a_matched_change_adds_the_gates_reads_and_no_more`: on a SQLite file, a one-file `write` by a named caller with one allowing `Mutation` policy issues the statements of the same write with no policy, plus the statements `admits` issues alone, and `admits` alone issues no `INSERT`, `UPDATE` or `DELETE`.
- `test_a_ten_thousand_entry_write_is_one_step`: the policy is called once, `admits` once for each mount, and `admits` issues the number of statements it issues for a 10-entry write. Marked `slow`.
- `test_a_storage_that_keeps_grants_and_cannot_judge_refuses`: a double that declares `grant` and has no `admits`: the step is `unsupported`, the policy is called 0 times. A double that declares no grant verb: the policy is called once.
- `test_a_denial_refuses_the_whole_step`: a `write` over two mounts, denied: 0 dispatches on either, one error of kind `vfs.permission_denied.policy`, `path` is `None`, `data` is `{"policy": "frozen", "paths": 2}`, and the message is the phrase, the reason and the name.
- `test_every_policy_is_asked_in_the_order_added`: four policies, the second and third deny: the recorded order is 1, 2, 3, 4, and the result holds two errors in that order.
- `test_a_policy_that_raises_refuses`: `data["failed"]` is `"raised"`, the message does not hold the exception's text, one `ERROR` record on `vfs.decisions`, 0 dispatches.
- `test_a_policy_that_returns_no_decision_refuses`: four cases, `None`, `True`, a string and a dictionary.
- `test_a_policy_past_its_timeout_refuses`: `@policy(timeout=0.01)` that awaits an event nobody sets. The outcome is asserted and no time is.
- `test_a_policy_that_holds_the_loop_past_its_timeout_refuses`: the clock of `vfs.deadline` is patched to jump while the policy runs. One refusal, two `WARNING` records, and a second such call logs one.
- `test_a_policy_that_swallows_its_timeout_refuses`: a policy that catches `BaseException` and returns `Decision.allow()`.
- `test_a_cancelled_call_cancels_its_policy`: the call's task is cancelled while the policy waits: `CancelledError`, 0 dispatches.
- `test_the_system_authority_is_shown_to_no_policy`: all 25 verbs as the system authority, with a policy typed `Step` that denies: 0 calls, 25 dispatches. The same with `default_authority` the system authority and no `authority` argument, and the constructor's warning holds the new words.
- `test_the_anonymous_caller_is_shown_to_policies`: 1 call.
- `test_a_registry_change_is_seen_by_the_next_step`: a policy added between two calls is called 0 and then 1 times. A policy added while another call waits inside a policy is not asked about that call.
- `test_a_policy_reads_its_file_system_as_the_system_authority`: inside a policy, a `read` as the system authority succeeds and asks 0 policies, a `read` as a named caller is `invalid` with the words of decision 19, and a `cli` is refused the same way. A `write` to a second kernel as a named caller lands.
- `test_a_chained_grep_is_one_step`: a `grep` over rows in hand that must read a body, with a policy typed `Step`: 1 call, of a `GrepStep`.
- `test_a_contexts_policies_are_asked_after_the_file_systems`: recorded order is the file system's two and then the context's one. A policy in both is called once. Two different policies with one name refuse the step with `failed` of `"duplicate"`. The verdict's `of_session` holds the one name that came from the context.
- `test_ask_judges_a_step_that_is_no_verb`: `fs._ask(RewindStep(...))` with a policy typed `Mutation`: 1 call of the policy, 0 calls of `admits`. A policy typed `DeleteStep` is called 0 times. As the system authority the policy is called 0 times. A denial comes back as a result of kind `vfs.permission_denied.policy` whose `ops` is `("rewind",)`.
- `test_a_call_inside_within_asks_no_policy`: inside `decisions.within(fs)`, a `write`, a `delete`, a `restore` and a `move` of 10 entries each, with a policy typed `Step`: 0 calls of the policy, 0 calls of `admits`, 4 dispatches. The same calls on a second kernel inside the first kernel's `within` call that kernel's policy 4 times. A call the caller's rights refuse is still refused inside `within`.
- `test_chosen_names_the_policies_of_a_class`: `fs._chosen(EditStep)` returns the file system's policies typed for it and then the context's, with the context's names apart.
- `test_a_proof_asks_admits_and_dispatches_nothing`: `fs._proof("write", entries=..., authority=scout)` over two mounts, with no policy on the file system: `admits` is called once on each mount, the verb's own method 0 times, and the result is a success with no row. With a policy typed `Step` that denies, the policy is called 0 times. On the in-memory storage with a right taken from one of 20 files, the result holds one refusal, at that file's path, of the storage's own kind, and no mutation statement runs. As the system authority, and for a `read`, `admits` is called 0 times. A wrong argument is `invalid`, from the gate.

Landing 2, elsewhere:

- `tests/storage/test_conformance.py`, one contract row for each of the 15 verbs in the table of decision 11: `admits` succeeds where the verb succeeds, fails with the verb's own kind and path where the verb is refused on rights, and leaves every row as it was. On every engine leg.
- `tests/storage/database/test_authorized.py::test_admits_for_a_write_issues_four_reads`: a named caller with cached rights, one file, counted on SQLite.
- `tests/shell/test_host.py::test_each_verb_of_a_line_is_a_step_with_via`: `cat /a; echo x > /b; rm /c` with a recording policy typed `Step`: seven steps, as a probe counted the line's calls today: four `StatStep`s, one `ReadStep`, one `WriteStep` and one `DeleteStep`, each with `via` equal to `Line(text, "/")`. A policy typed `Mutation` is called twice. A direct call has `via` of `None`.
- `tests/shell/test_host.py::test_a_line_is_shown_to_no_policy_itself`: `echo hi` calls the policy 0 times.
- `tests/shell/test_host.py::test_a_denied_step_fails_as_a_command`: `cat /contracts/a || echo fallback` with a denial of reads under `/contracts`: standard output is `fallback`, standard error holds `Permission denied`, the exit status is 0, and the result holds one warning of the new kind.
- `tests/shell/test_host.py::test_a_denied_command_prints_the_policys_reason`, once spec 8's `WORDED_REFUSALS` is in the tree: the same line prints the reason and the policy's name on standard error, and no longer the bare `Permission denied`; `rm` of a guarded file exits 1; with two denying policies the first one's reason is printed and the result keeps two warnings.
- `tests/test_sync.py`: `_assert_twins` for `add_policy`, `remove_policy`, `policies` and the constructor. `test_a_policy_runs_on_the_facades_loop`: the thread's name inside the policy is `LOOP_THREAD_NAME`. `test_a_policy_that_calls_the_synchronous_face_is_refused_not_hung`: the policy gets an `invalid` result.
- `tests/results/test_result_laws.py` round-trips the new kind. `tests/results/test_render.py` pins the line of decision 14 exactly.
- `tests/test_ops.py`: the surface test still holds, since the three new methods are no coroutines.
- Where spec 2's handle is in the tree: its test `test_a_non_empty_policies_is_refused_until_policies_exist` is deleted, as spec 2, decision 4, says. `test_a_handles_policies_are_checked_when_it_is_asked_for`: an item that is no `Policy` raises `TypeError`, two different policies of one name raise `ValueError`, and neither issues a statement. `test_a_handles_policies_are_asked_after_the_file_systems`: the order through a handle is the order of the context test above.

Landing 3, in `tests/base/test_policies.py` and `tests/test_policies.py`, with spec 7 in the tree:

- `test_a_later_denial_beats_an_earlier_interrupt`: policies `a` (asks) and `b` (denies): the step is refused, and 0 jobs are stored.
- `test_the_first_interrupt_in_order_is_raised`: the walk of decision 13: calls of `a`, `b`, `c` are 1, 1, 1 in each of three passes, the job is interrupted twice, and 1 mutation lands.
- `test_an_answer_that_is_not_asked_for_again_never_runs_the_step`: a policy that asks at the call and allows without asking at the resume, answered "no" and then, in a second case, "yes": 0 mutation statements in both, and the result is spec 7's `vfs.conflict` (spec 7, decision 20). Spec 7 has the same case from its side, `test_an_answer_no_longer_asked_for_ends_the_job`.
- `test_a_job_resumed_without_its_policy_never_runs_the_step`: the policy is removed before the resume, and again with a second kernel over the same SQLite file that has no policy: 0 mutation statements, and the verdict names no policy of that name among those asked.
- `test_an_answer_that_does_not_fit_ends_the_asking`: three policies, the first raises `AnswerRefused`: the second and third are called 0 times, and the verdict's `unfit` holds it.
- `test_a_policy_that_goes_on_after_it_asked_refuses`: a policy that catches `BaseException` around `require_approval` and returns `Decision.allow()`: `failed` is `"swallowed"`, 0 dispatches, 0 jobs stored.
- `test_a_policy_that_now_denies_still_denies`, `test_a_policy_that_now_asks_interrupts_again`.
- `test_review_asks_for_a_change_under_its_paths`: under `/contracts` it is interrupted; under `/notes` it is not, and the policy awaits nothing; a read calls it 0 times; with `paths` of `/legal/contracts`, a `delete("/legal")` with cascade is interrupted.
- `test_review_names_itself_by_its_paths`, `test_review_refuses_no_paths`, `test_two_reviews_of_the_same_paths_are_one_policy`.
- `test_a_sessions_policy_interrupts_and_is_resumed_through_its_handle`, once spec 2's handle is in the tree: resumed through the handle the step runs once, and resumed with `fs.resume` it is refused `vfs.invalid` and does not run (spec 7, decision 33).
- `test_review_asks_for_a_rewind_under_its_paths`, once spec 5's rewind is in the tree: a `RewindStep` with one path under `/contracts` is interrupted, and one with none is not.

## Scope

In, by landing:

1. `src/vfs/steps.py` (new, with `RewindStep` and `STEP_CLASSES`); `src/vfs/params.py` (the table built from the classes); `src/vfs/__init__.py` (28 names and `Line`); `tests/test_steps.py` (new), `tests/test_params.py`, `tests/test_package.py`; `documentation/reference/python-api/steps.md` (new), `index.md`, `glossary.md`.
2. `src/vfs/decisions.py` (new); `src/vfs/judging.py` (new: the judging coroutine, `Refusal` and `Verdict`); `src/vfs/base.py` (the constructor argument, three methods, `_admit`, `_chosen`, `_ask`, `_proof`, eight call sites, one branch of `_call_storage`, the refusal in `cli`); `src/vfs/session.py` and `src/vfs/sync_session.py`, where spec 2's handle is in the tree (the check in `fs.session`, the context around each verb, and spec 2's refusal of `policies` removed); `src/vfs/sync.py` (the argument and three twins); `src/vfs/shell/host.py` (`run_line` enters the line, and one row of `_HOST_ERROR`); `src/vfs/storage/protocol.py` (`SupportsAdmits`); `src/vfs/storage/backends/database/backend.py` (`admits`, and each gate as one function); `src/vfs/results/kinds.py` (the kind and its row); `src/vfs/authority.py` (six words); `src/vfs/__init__.py` (`Decision`, `Policy`, `policy`); `tests/support/base_doubles.py` (`admits` on the double); the tests named above; `tests/lint/allowlist.py` (the entries of `base.py` and `backend.py` raised: `base.py` grows by about 120 lines, since the asking lives in `judging.py` and the kernel only places the call sites and turns a verdict into a result); `documentation/reference/python-api/policies.md` (new), `index.md`, `storage.md`, `glossary.md`.
3. `src/vfs/policies.py` (new); `src/vfs/judging.py` (the fourth outcome, the swallowed stop, the answer that does not fit, and spec 7's context set around each policy); `src/vfs/decisions.py` (`Decision.answered`); `src/vfs/__init__.py` (`policies`); the tests named above; the guide.

Each landing runs `scripts/ci.sh` and `scripts/docs.sh check`. Landing 2 touches the database backend, so it runs the Postgres leg before its pull request.

Out: everything under "Left as it is"; the job, its record, `interrupt`, `require_approval`, `resume` and `holds_all`, which are spec 7's; the session handle and `fs.session`, which are spec 2's, but for the edits of decision 17; a line that replays and the reply `denied`, which are spec 8's; the rewind, its plan and what it does with the answer of `_ask`, which are spec 5's.

## What the docs must say

- A policy is a function the host writes. It is shown each step it is typed for, before the step runs, and allows it or denies it with a reason.
- The type of the argument chooses the steps. `Mutation` is every change, a change of rights and a rewind that puts files back included. A policy typed `Mutation` costs nothing on a read.
- A policy can only narrow. For a change, VFS proves the caller may make it first, and a change the caller may not make is refused before any policy is called.
- Every policy typed for a step is asked, in the order added. One denial refuses the step. The caller reads every reason.
- A policy that raises, returns no decision or passes its timeout denies. The timeout is ten seconds, and `@policy(timeout=...)` changes it.
- The system authority is shown to no policy.
- A policy is asked again at a resume, so it must ask the same thing for the same step, and a job is resumed where its policies are installed.
- A policy reads its file system as the system authority.

Pages:

- `documentation/reference/python-api/steps.md`, new: `Step`, `Mutation`, `Line` and the 26 classes, from their docstrings.
- `documentation/reference/python-api/policies.md`, new: `policy`, `Policy`, `Decision`, and the module `policies`.
- `documentation/reference/python-api/index.md`: two sections, "Steps" and "Policies".
- `documentation/reference/python-api/storage.md`: `SupportsAdmits`, if the page lists `SupportsHolds`; the docs export decides, since no public signature names it.
- The docstrings of `AsyncVirtualFileSystem` and `VirtualFileSystem`: the `policies` argument and the three methods. The docstring of `ErrorKind`: the new kind and its `data`.
- `documentation/reference/glossary.md`, two terms, between Mount and Storage:
  - **Policy.** A policy is a function the host writes that is shown each [step](#step) before it runs and decides whether it may. It is an `async` function marked with `@policy`, it takes the step, and it returns a `Decision` that allows the step or denies it with a reason. The type of its argument chooses the steps it is shown. A policy can only narrow what a caller may do. Every policy typed for a step is asked, in the order it was added, and one denial refuses the step. A policy that fails denies. No policy is asked about a step of the system authority. Types: `Policy`, `Decision`.
  - **Step.** A step is one verb about to run, with the arguments VFS has already checked. A direct call such as `edit` is one step, and a shell line makes one step for each verb it carries out. Every step has a `verb`, the `paths` it names, the `authority` that is calling, and `via`, which is the line that made it. Each kind of step adds the arguments of its own verb. One step is no verb: a rewind that puts a session's files back. A step cannot be changed. Types: `Step`, `Mutation`, one class for each verb, such as `EditStep`, and `RewindStep`.
- The guide, `documentation/how-to/interrupt-a-job-and-ask-a-person.md`: the changes listed under "Where this spec disagrees with the overview or the guides", and one that round two settled. Where the guide lists what `Mutation` covers, it reads: "a write, an edit, a delete, a move, a copy, a new directory, a restore, an edge made or removed, a sweep, a change to who may access a path, and a rewind that puts files back".
- Two smaller changes to the same guide, which follow from decisions 4, 9 and 23. The row for `step.verb` gains "or `"rewind"` for a rewind that puts files back". The sentence on `fs.add_policy` and `fs.remove_policy` is followed by "`fs.policies()` lists them in order."
- The overview's list of public names gains `fs.policies()`, `Policy` and `Line`, by ruling 10 of round two, and its list of error kinds has `vfs.permission_denied.policy`, by ruling 6.
- The sessions guide, `documentation/how-to/keep-a-session-for-each-conversation.md`, needs no change from this spec. It names neither a policy nor a step.

## Earlier decisions this reverses

The decision records were retired on 2026-10-30 and are read from git history at `3667fec2^`, under `context/decisions/`. Each is named by its title.

- **"The gate order is the execution policy" (the record numbered 084).** Pin 1, the gates fire on every verb a command resolves to and no verdict is passed on the command text, binds, and decision 6 rests on it. It gains one gate at the end of its order: capability, grammar, permission, the caller's rights, and then the host's policies. Pin 3, a line never runs as the system actor, binds, and decision 18 rests on it. Pin 4, "no `ask` inside vfs", is amended in its second sentence: VFS no longer only allows or classifies, because a host's policy may refuse a step. The half about stopping for a person is spec 7's. Pin 9, the classified refusals need no new kind, is amended: one kind is added.
- **"The session law" (063).** Rule 1, a session never widens itself, binds, and decision 17 applies it to review. Rule 2, rights are re-derived on every call, binds, and decision 16 does the same for policies: nothing a policy decided is kept between two passes. Rule 6, the system actor is the one marked exception, binds, and decision 18 is that exception. Rule 5, `ask` is a result bound to the request, is spec 7's.
- **Roadmap story H3, criterion 1.** Reversed in five points. `VirtualFileSystem(policy=hook)` with one callable, sync or async, becomes `policies=[...]`, a list of `async` functions marked `@policy`. `CallDescription` becomes the step classes. For `cli` the hook was to be given the static parse of the line: it is given nothing for the line, and each verb as a step. The hook's three returns, `allow`, `deny(kind, message)` and `pending(reason)`, become a `Decision` of two values, a denial names no kind of its own, and a stop is an `await`. The ask ledger was to be read ahead of the hook so that an answered call skipped it: policies are asked again at a resume. One sentence of the criterion is kept as written: the hook runs after the gate and before storage, and a call the gate would refuse never reaches it, counted.
- **Roadmap story H1, criterion 1.** Its line on pin 1, "the hook judges the static parse, never the command text, and may only deny or suspend, never widen", holds with "each verb the line makes" in place of "the static parse".
- **The draft "a call is interrupted and the host asks" of 2026-11-21**, at `agents/2026-11-21-a-call-is-interrupted-and-the-host-asks/spec.md` on its unmerged branch. Its decision 17, a run of a tool reaches the policy as `call.op == "run"`, becomes `RunStep`. Its scope named `strictest` beside `review`: `strictest` is not built. Its rule that an answered call skips the policy is reversed by the guide, and decision 16 carries what that costs.
- **The approval study's recommendation** of `policy="review"` as a string and of `policies.strictest(...)` is not taken. Its recommendation that a session may add and never loosen, and that the mode never belongs to the call or the mount, is.

## Choices for the owner

Each is decided above. Each is the owner's to change.

1. **Are a caller's rights proven before a policy is called, or only when a policy denies or interrupts?** Taken: before, by decision 10. It costs 4 read statements for each change a policy is typed for, about 150,000 a day at the reference deployment. The other answer costs nothing for a step every policy allows, and calls the policy function for a step the caller may not make. No person is asked either way.
2. **Is a read proven before its policies?** Taken: no. A policy typed for reads may be asked about a read that the caller's rights then hide. Proving it first runs every such read twice.
3. **Is the line itself shown to policies?** Taken: no, by decision 6.
4. **The timeout of a policy.** Taken: 10 seconds, changed for one policy by `@policy(timeout=...)`. A policy that calls a model may need more.
5. **One kind for a denial and for a policy that failed, or two?** Taken: one, `vfs.permission_denied.policy`, with `data["failed"]` telling them apart. Both tell a caller the same thing to do.
6. **May a policy call its file system as a caller other than the system authority?** Taken: no, by decision 19.
7. **Are `Entry` and `Edge` frozen?** Taken: not by this spec. It needs a spec of its own, which changes the validators of `Entry`.
8. **Does every policy see a step that an earlier one denied?** Taken: yes, and the caller reads every reason. Stopping at the first denial would save the later calls.
9. **Are a caller's rights proven again before the policies of a resume?** Taken: no, since round two. Spec 7 runs the policies on the saved step and lets the storage judge the caller when the step is dispatched. A caller who lost a right while its job waited can so have one more question put to a person before the verb refuses it. Proving first is one call of `fs._proof` in spec 7's `resume` and four read statements a resume, and it is the one need still listed under "Needs no other spec meets yet".
10. **Does a command a policy denied print the policy's reason, or "Permission denied"?** Taken, since round three: the reason, through spec 8's `WORDED_REFUSALS` (decision 14). Until spec 8 is built it prints "Permission denied", and the reason is kept as a warning on the line's result either way.

One choice of round one is settled. Round two rules that `Mutation` is the fifteen verbs a read-only mount refuses and `RewindStep`.

## Where this spec disagrees with the overview or the guides

Three points of round one are settled by round two and are no longer listed: what `Mutation` covers (the ruling for this spec), the kind `vfs.permission_denied.policy` (ruling 6), and the public names `fs.policies()`, `Policy` and `Line` (ruling 10). The words each needs in the guide and the overview are under "What the docs must say".

1. **The guide's rule for `touches`** is "any of the paths is that path or inside it". Proposed: add "or the step acts on everything beneath one of its paths, and that path is beneath it". Evidence: under the guide's rule a cascade delete of `/legal` does not touch `/legal/contracts`. The kernel holds the same fact for the permission maps, `src/vfs/base.py:3079`.
2. **The guide's table of core attributes** has five rows. Proposed: a sixth, `step.subtree`. And a sentence that the scope of a `glob`, a `grep` or a `search` is `step.roots`, because `step.paths` is every path the step names.
3. **The guide says of `step.via`** that it is "the shell line or tool that made it". Proposed: "`None` for a direct call, or a `Line` with the line's `text` and `cwd`". The tool's half arrives with tools.
4. **The guide says** "VFS checks the caller's access first, so a call the caller has no right to make is refused before any policy sees it". That is true of a change when it is first made. This spec cannot make it true of a read or of a restore's verdict on a row, and at a resume the caller's access is checked when the saved step is carried out, after its policies were asked again (spec 7, decision 22). Proposed: "For a change, VFS checks the caller's access first, so a change the caller has no right to make is refused before any policy sees it. A read is filtered by the caller's access when it is answered." Evidence: `backend.py:1197-1251` and `:832-862`.
5. **The guide says** a policy that "takes longer than its deadline" denies, and names no value. Proposed: "takes longer than its timeout, which is ten seconds unless `@policy(timeout=...)` sets another". The same sentence can name `@policy(name=...)`.
6. **The guide's "Combine Policies"** does not say what a caller reads when two policies deny, or where a session's job is resumed. Proposed, two sentences: "When several policies deny, the result carries each one's reason." "A job that a session's policies judged is resumed through that session, and any job is resumed by a program that has the policy which interrupted it; otherwise the resume is refused and the step is not run." The second sentence is spec 7's rule (spec 7, decisions 20 and 33) and is proposed here because the section is this spec's public face.
7. **The overview's model says a step is one verb about to run.** Round two rules that a step need not be a verb. Spec 5 carries the change proposed to the overview's sentence, and decision 23 here is the class.

## Needs no other spec meets yet

Round two listed six. Five are met at `7c383f32`, each read in its owner's text, and are no longer listed:

- The reads of a preview are made inside `decisions.within(fs)`: spec 7, decision 13 ("The preview is computed once, as the caller, for seven verbs, and every part of it is bounded").
- The policies of a resume come from `fs._chosen(type(step))`, and the saved step is dispatched as its public verb inside `decisions.within(fs)`: spec 7, decision 20 and decision 22.
- `Run`, and `asking(run, step, policy_name)`, in `src/vfs/jobs/asking.py`, which imports `vfs.decisions` and never `vfs.judging`: spec 7, decision 8.
- A resumed line runs inside `decisions.in_line(Line(line, cwd))`: spec 8, decision 14.
- A table of the refusals a line's host words, which this spec may add its kind to: spec 8, decision 18. Decision 14 here adds it.

One is still open.

1. **Spec 7, decision 20 ("A resume runs the policies again with the answers the job has, and the run ends in one of seven ways").** What is missing: the rights proof before the policies of a resume. Spec 7's Builds on lists "the rights proof before a change's policies, by `admits`" as taken from this spec, and its `resume` asks the policies of a saved step without it. This spec gives the proof for a first call of a change (decision 10), and since round three the call that asks it alone (decision 24). Text that would close it, in spec 7's decision 20: "Before the policies run again for a job of one step, `resume` awaits `fs._proof(step.verb, authority=step.authority, **step.parameters())` (spec 6, decision 24). A refusal ends the job as the step's result, and no policy is asked." It costs a resume four read statements. It is left open because it changes what a resume returns for a caller who lost a right, and it is choice 9 for the owner.

No other spec lists a need of this one under its own heading of this name. Two things were found in their text all the same, and are met here in round three: spec 5's proof of a batch "by `admits`" needed a call on the kernel, which is decision 24, and spec 1 corrected this spec's count of the parameter table to 150, which decision 2 now has.

One thing another spec asks of this one is met only in part. Spec 7's Builds on asks for the caller's access to be judged before any policy is asked. It is, for a first call of a change. It is not for a read or for a restore's verdict on a row, because those verdicts are given as the storage answers (decision 10).

## Not checked

- No test was written or run, and the suite was not run. Every count in "Tests" is what the test is to assert.
- Postgres. No server was available in either round. The statement counts are SQLite's. The four reads of a proof were counted as the gate's part of a write, not by running `admits`, which does not exist. What to run once `admits` is built: on the Postgres leg, with the `before_cursor_execute` listener, one `write` of one file by a named caller whose rights are cached, with and without one allowing `Mutation` policy; the difference is the proof's statements, expected to be 4. Then the same proof while a second session holds an open write transaction on the same row, to show the proof returns.
- That each gate in `backend.py` comes apart from its verb as cleanly as it reads. The gates of `delete`, `restore`, `sweep`, `move` and `copy` are already functions. Those of `write`, `edit`, `mkdir`, `mkedge` and `rmedge` are the first lines of a closure.
- Whether any test pins the words of the default-authority warning that decision 18 lengthens. A search of `tests/` found none.
- Whether the docs export needs a page for `SupportsAdmits`.
- The other eight specs were read in rounds two and three as far as they touch this spec: each Builds on, each list of unmet needs, and the decisions cited above. In round three every cited number, heading and borrowed name was read again in the owner's text at `7c383f32`. No decision of another spec was read that this spec neither cites nor depends on.
- That spec 7's `Interrupted` and `AnswerRefused` can be imported by `judging.py` without a cycle. Spec 7, decision 8, says `asking.py` imports `vfs.decisions` and never `vfs.judging`. No import was run, since neither module exists.
- That `fs.session` can call `decisions.policy_set` without I/O was read from spec 2, decision 2, and not run, since neither is built.
- That a public verb can stop at its call site under the mark of decision 24 for every shape of dispatch. It was read from the eight call sites of decision 10, each of which sits before the first call that acts on a storage, and was not run.
- The words a denied command prints under spec 8's `WORDED_REFUSALS` were composed from spec 8, decision 18, and this spec's row of `KIND_CONTRACTS`. The machine that prints them is spec 8's and is not built.
- The guide's code blocks were not run. The page says its interface is not built.
- The cost of a policy that reads a file as the system authority on every step. It is the host's choice, and one read of a small file is one statement as the system authority.
- A storage that wraps another kernel. None ships. The marks in the call context name the kernel they belong to so that such a storage would be judged by the inner kernel's own policies, and no test can show it.
- The interpreter times, on any machine but one.

## One line

A host's function is shown each verb as a typed, frozen step, after the caller's rights are proven for a change and before anything is changed, and a denial or a broken function refuses the step.
