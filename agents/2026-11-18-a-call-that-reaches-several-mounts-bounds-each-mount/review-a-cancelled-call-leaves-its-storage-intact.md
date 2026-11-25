# Review: a cancelled call leaves its storage intact

The branch `a-cancelled-call-leaves-its-storage-intact` was read four times on 2026-11-20 and 2026-11-21. Each reading was given the diff against `dev` and the spec beside this file, and no summary of the work. Each one ran its findings as scripts. The spec's own readings, before anything was built, are in `review.md` in this directory.

| What was read | Verdict | Findings |
|---|---|---|
| The fix as first built: an in-memory storage and a storage in a file that VFS opened from a URL | Does not land yet | The caller's cancellation was replaced by a new one, and three paths were not covered |
| The fix after the first round, with the mark read before every statement on all four SQLite hosts | Does not land yet | 1 High, on a handed session factory |
| The whole branch after `session_factory=` was removed | Lands | 0 High, 2 Medium, 7 Low |
| The fixes that answered the third reading, and nothing else | Does not land yet | 0 High, 3 Medium, 5 Low, each answered below |

## What the first reading changed

- **Found: the caller was raised a new and empty `CancelledError`.** anyio knows its own cancellation by the message on the exception, so `anyio.move_on_after` and `anyio.fail_after` let the error escape their blocks. Starlette, FastAPI, httpx and the MCP SDK are built on anyio. Decided: the caller is raised the first cancellation it caught, the same object.
- **Found: `install_extensions` ran in its caller's task.** A cancelled install cost an in-memory storage its database, as a cancelled call had. Decided: it runs out of reach as an attempt does.
- **Found: a storage that was handed a session factory was not tested at all,** and the fast tier's one test could not fail. Decided: the handed hosts join the sweeps, and the fast test counts connections.
- **Found: one test waited on a timer.** Decided: it holds a driver round trip, as the others do.
- **Decided after the reading, as a change of behaviour that was asked for:** every SQLite storage runs each attempt out of reach, and the mark is read before each statement, so a cancelled call sends no statement after the one in flight. Before, a cancelled read ran all its statements and only a commit was refused.

Twenty-three mutants were replayed against the tests of this round, and each was killed. They are rows of `context/standards/mutant-ledger.md`.

## What the second reading changed

The second reading made about 6,500 cuts.

- **Found, High: a handed session factory that returns the same session twice recursed without end.** The wrapper around a session wrapped a wrapper, and the 954th call raised `RecursionError`.
- **Found: a handed session factory over an in-memory database took no turns,** so a cancelled rebuild could commit one phase alone and leave every later rebuild refused.
- **Found: a caller cancelled while its attempt waits for a connection waits for the pool.** Before the branch it was back at once. Decided: left as it is and said in the docstrings, because a checkout that has begun cannot be cancelled without the defect of this spec. A test counts what is sent. It is a task.
- **Found: two mutants survived,** the session's exit without `finally` and a `suppress` that named `CancelledError` for nothing. Each has a test now.
- **Found: the dialect was tested by name at three sites.** Decided: `DialectProfile.attempts_out_of_reach` declares it.
- **Found: `grant` and `revoke` were not swept.** They are.
- **Found: under an anyio cancel scope the event loop keeps turning until the attempt ends,** 135,379 cancellations for one statement held a second. Left as a task.

The two findings about a handed session factory were not fixed. They led to a question and a study, `agents/2026-11-21-a-storage-always-owns-its-sessions/research.md`, which found that no comparable library takes a session factory, that a handed storage shared only the pool with its application, and that VFS already changed settings on a handed engine. Decided: `session_factory=` is removed. A storage builds and owns its engine, takes `engine_arguments=`, and exposes the engine as a read-only property. The refusals then became three listeners that are put in place once, and the wrapper around each session and the listener on each connection were deleted. Thirty-five mutants were replayed against the new build, and each was killed.

## What the third reading changed

The third reading held a write at each of its 81 round trips on both hosts under an anyio scope, cut first touch at about 1,230 round trips and `install_extensions` at 78, cut a rebuild 125 times, ran 720 concurrent callers of which 437 were cancelled, cut a write of 10,000 files at three depths, and ran 44 sets of engine arguments. No write was torn, no cancellation escaped a scope that had cancelled first, and no connection was thrown away.

- **Found, Medium: a time limit of asyncio that cancels first, and a cancel scope of anyio that cancels second, let `CancelledError` escape the scope.** The caller was raised the first cancellation, which carries no message, and the scope knows its own by its message. Decided: the first is still raised, and each later cancellation with another message is the `__context__` of the one before it, where anyio looks next. Run in both orders on both hosts.
- **Found, Medium: a connection that an application opens on `storage.engine` beside a call costs an in-memory storage its database.** The checkout stamps its settings on the one connection inside the call's transaction. Decided: the property's docstring and `README.md` say the engine is for listeners alone, on `storage.engine.sync_engine`, and that no connection or session is opened on it. Nothing prevents it, and that is a task.
- **Found: an in-memory URL took a pool class or a `pool_recycle` that cost it its database,** the second in silence. Decided: both are refused at construction with a `ValueError` that names the key, as the two required arguments are. A storage in a file takes any pool.
- **Suspected by reading: `isolation_level="AUTOCOMMIT"` would let each statement of a write commit alone** on SQL Server, Oracle and an unknown dialect, which pin no isolation level. Decided: it is refused on every dialect, on the engine and in its execution options. Not run on a server.
- **Found: five mutants survived.** A second cancellation that takes the mark off, the first-touch re-arm put on every pool, the required argument written into the application's own mapping, a new error raised with the first one's arguments, and the mark set in the caller's context. Each has a test now.
- **Found: `SerializedSession.__getattr__` had no caller left,** and one test kept it alive. Both are removed.
- **Found: a creator on SQLite gives up `ClosingConnection`,** though the docstring said the requirement always holds. The docstring is corrected, and nothing is refused. It is a task.
- **Found: stale prose** in the spec and in four lines of the roadmap, which planned for a handed session factory. Corrected.

Forty-eight mutants were replayed against that build, and each was killed.

## What the fourth reading changed

The fourth reading was given only the fixes that answered the third. It ran 15 arrangements of two and three cancellers beside a plain `await`, and 70 sets of engine arguments.

- **Found, Medium: the chain of cancellations is lost when the call is awaited inside an `except` block or a `finally` during an error.** Python replaces the `__context__` of an error that leaves a block which is handling another. With a time limit first and a cancel scope second, the scope's cancellation then escaped the scope, in 4 of 12 cases. The same before the third reading's fix. Decided: the cancellation raised is the first that carries a message, or the first of all when none does, because only a canceller that reads the message needs it on the error itself, and a time limit and a task group of asyncio do not read it. The others are chained behind it. The 12 cases pass on both hosts. One limit remains and is a task: of two cancellers that both read a message, around a call awaited inside an `except` block, the second is lost.
- **Found, Medium: a `pool=` instance on an in-memory URL was refused by SQLAlchemy with an error that named two arguments the application had not given.** The fix of the third reading put them in. Decided: `pool` is refused there by a `ValueError` of VFS that names it.
- **Found, Medium: two docstrings said that every in-memory URL is guarded.** SQLAlchemy classes the two spellings with `file::memory:` as a database in a file, so nothing is required of them. Decided: the words say how far the guard reaches, a test pins it, and the spelling is a task.
- **Found: with the time limit outside the scope, a limit that ran out first raises no `TimeoutError`,** because the scope takes the cancellation, as a plain `await` does when the scope's cancellation lands first. It is stated in the spec and pinned.
- **Found: four mutants survived,** two in the chain of three cancellers and two in the reading of `execution_options`. Each has a test now, and `execution_options` that is not a mapping passes to SQLAlchemy untouched.

Fifty-four mutants were replayed against the last build. Fifty-two were killed in the full scope. The two that take the out-of-reach rule away are killed with the scope tests left out, and hang a run with them in: a call on a database in a file that a cancel scope cancels then leaves a driver task that never ends. The scope tests carry a timeout of 60 seconds for that reason. Under parallel workers the timeout was not seen to end the run, and that is a task.

The fourth reading then read its own findings against the answers and found each closed or answered in words. It found one thing more, and it is left as it is.

- **Found, Medium: of two cancellers that land while one call waits, the outside one can be lost.** A cancel scope of anyio takes any error that carries its message, whatever else is pending on the task. A `task.cancel()` or a time limit of asyncio from outside the scope, with the scope cancelled in the same wait, is therefore lost: the task runs on. A plain `await` ends the task when the outside cancellation lands first. The order before it lost the scope's cancellation and let the error escape the scope. Both need two cancellations inside one statement's wait. Decided: the build stays, the docstring and the spec say it, and a test pins what happens. Raising the first cancellation and delivering each later one again at the next `await` would lose neither. It changes behaviour, and it is a task.

By reading, and with no server engine to run, the third reading found no statement, lock, listener or task added on Postgres, SQL Server, Oracle, MariaDB or an unknown dialect.

## Security

`engine_arguments` and the `engine` property do not touch the permission gate. Raw SQL through the engine is open only to code that already holds the storage and its URL. For URLs that carry a password, and for six constructions that were refused, no password appeared in a repr, a `ValueError`, an error of SQLAlchemy or a classified result. Each storage builds its own engine and pool, so one mount's caller does not reach another's connection.

## The documentation check

The check asks whether the change needs a docstring, a page for users, a Maintainers page or a glossary term.

- **Docstrings: yes.** `DatabaseStorage`, `InMemoryStorage`, `with_retry`, `install_extensions`, `merge_engine_arguments`, the `engine` property and the module `attempts.py` say what a cancelled call has done and what the constructor takes.
- **A page for users: not in this landing.** `README.md` shows the new constructor. What a caller may count on after a cancelled call belongs in a How-to page beside the time limit, which is the next landing, and is a task. A draft that mixed a how-to, a reference and an explanation was written and dropped.
- **A Maintainers page: yes.** `documentation/maintainers/cancellation.md` is new. `how-we-work.md` gains this check as a step of the autonomous pass, and `how-we-document.md` gains the rule that a page is prose.
- **A glossary term: no.** "Attempt" is used on one Maintainers page and in the docstrings of one module. Whether it becomes a term is a task.

## What was run

All on the last commit of source, on Python 3.13, with nothing else running.

- `scripts/ci.sh`: lint, format and types at zero; 5,827 tests passed and 18 were skipped at 100% coverage; the docs examples and the wheel size pass.
- `scripts/docs.sh check`: the export, the build, the type check with no error, and 23 build tests pass. Its 20 browser tests were run against the Chromium build on the machine, which is older than the one the docs app pins, and pass.

## Not run

- **A server engine.** No container runtime was available. The workflow `test-dialects.yml` runs the engine legs on the pull request.
- **Python 3.11, 3.12 and 3.14.** They are legs of the pull request's Tests job.
- **The synchronous `VirtualFileSystem` and uvloop under cancellation.**
