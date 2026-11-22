"""The vfs host of the shell's machine.

:func:`run_line` starts the machine on a line and drives it to its end. Every
request the machine asks becomes one call of a public verb of the router,
with the authority the caller was admitted as. A verb's refusal becomes the
error a Unix tool would see, so ``cat`` prints "No such file or directory"
where the router says ``not_found``, and the refusal itself is kept on the
result as a warning: a program's failure is evidence, not the call's failure.
The call fails only when the line could not run to its end as written.

A line is parsed whole before anything runs, so a syntax error, a refused
construct or a spent parse budget fails the call and touches nothing.

Each open of a file is one ``read`` of its whole body, judged as the caller
at that moment, so a second ``cat`` of a file sees an edit or a revoke made in
between. The body is held only while its open reads it, and every chunk of
one open comes from the version that open saw.

A program name the host resolves (:data:`vfs.shell.programs.PROGRAMS`) is
asked of the host at each start: ``grep -r`` and ``find`` are served from the
indexed verbs where their answer is GNU's, and handed back to the shell's
library otherwise; the verbs with no Unix name run as programs of their own.
"""

from __future__ import annotations

import asyncio
import random
import time
from functools import partial
from typing import TYPE_CHECKING, Any, Final, NamedTuple

from pydantic import Field

from vfs.deadline import Deadline
from vfs.native import extension
from vfs.offload import call_offloaded, offload_pool
from vfs.paths import Path
from vfs.results import ErrorKind, Result, ResultError, Severity, classified
from vfs.shell.programs import PROGRAMS

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from vfs.authority import Authority
    from vfs.shell.programs import Router

SHELL_NAME: Final = "bash"
"""``$0`` of every line, so its errors read as bash's do."""

ENVIRONMENT: Final[tuple[tuple[str, str], ...]] = (
    ("HOME", "/"),
    ("PATH", "/usr/bin:/bin"),
    ("LC_ALL", "C.UTF-8"),
    ("TZ", "UTC"),
)
"""The environment a line starts with."""

LIMITS: Final = frozenset(
    {
        "memory_bytes",
        "loop_iterations",
        "function_depth",
        "nesting",
        "output_bytes",
        "slice",
        "fuel_slice",
        "module_memory_bytes",
        "source_bytes",
        "tokens",
        "depth",
        "pipeline_stages",
    }
)
"""The budgets ``run_line`` takes by name in ``limits``."""

DEADLINE_SECONDS: Final = 30.0
"""The wall a line runs under, from its start to its end, the time its verbs take included."""

PID: Final = 1000
"""``$$`` of every line: the machine is no process, and a fixed value keeps a line a function of its input."""

_KIND_OF: Final[dict[str, str]] = {"directory": "directory"}

READING_BYTES: Final = 128 << 20
"""Bytes of the bodies open files hold at once. Each open of a file is one ``read`` of its whole body,
held until the open reads its end; past this, the body read least recently gives way, since a reader
may stop early, and its open reads it again only at the version it first saw."""

_BODY: Final = frozenset({"content", "data"})
"""The columns a read asks for: a bytes body comes back only when ``data`` is named."""

_HOST_ERROR: Final[dict[str, str]] = {
    ErrorKind.not_found: "not_found",
    ErrorKind.exists: "exists",
    ErrorKind.not_empty: "not_empty",
    ErrorKind.permission_denied: "permission_denied",
    ErrorKind.unauthenticated: "permission_denied",
    ErrorKind.read_only: "permission_denied",
    ErrorKind.unsupported: "unsupported",
}
"""The host error a router refusal reads as; ``wrong_kind`` reads by the kind it names."""

NETWORK_REFUSAL: Final = (
    "network access is not available inside vfs; read a file with cat, or find one with grep or search"
)
"""What a line prints for a network program: vfs knows it and does not run it, so it exits 126."""

REFUSED_PROGRAMS: Final[dict[str, str]] = {"curl": NETWORK_REFUSAL, "wget": NETWORK_REFUSAL}
"""Programs vfs knows and will not run, each with what the line prints; the command exits 126."""

UNKNOWN_PROGRAMS: Final[dict[str, str]] = {
    "git": "command not found; vfs keeps versions itself: stat shows a version, /.vfs/trash holds deleted files",
    "sudo": "command not found; a line runs with its caller's rights and no others",
    "python3": "command not found; vfs runs no interpreter inside a line",
    "python": "command not found; vfs runs no interpreter inside a line",
    "perl": "command not found; sed -i edits a file in place",
}
"""Names vfs never runs, each with a hint at what does the work here; the command exits 127."""

LINE_FACTS: Final = 100
"""Distinct refusals a line's result keeps; a refusal seen before is kept once, and past this count
the rest are counted in one rollup, so a loop of refusals leaves a bounded result."""

_FAILURE_KIND: Final[dict[str, ErrorKind]] = {
    "syntax": ErrorKind.invalid,
    "refused": ErrorKind.unsupported,
    "budget": ErrorKind.budget_exhausted,
}

# ---------------------------------------------------------------------------
# Running a line
# ---------------------------------------------------------------------------


class LineResult(Result):
    """What ``cli`` returns: a :class:`Result` with what the line printed and how its commands fared.

    ``success`` says whether the line ran to its end as written, and ``exit_code`` and ``statuses``
    say how its commands fared, as ``subprocess.run`` keeps a program's exit apart from its own
    failure. A command that exits non-zero, or a verb vfs refused inside the line, leaves
    ``success`` true: ``cat f 2>/dev/null || touch f`` is a line working as written. The call fails
    when the line did not parse, holds a refused construct, or a budget, the deadline or a cancel
    ended it. ``stdout`` and ``stderr`` are the bytes bash would print, decoded as UTF-8 with
    invalid bytes replaced. The errors are the classified facts: why a line did not run to its
    end, and, as warnings, each distinct thing vfs refused inside it.
    """

    ops: tuple[str, ...] = ("cli",)
    """Always ``("cli",)``: the call that made the result, which is no routed op."""
    stdout: str = ""
    """What the line wrote to standard output."""
    stderr: str = ""
    """What the line wrote to standard error."""
    exit_code: int = 0
    """``$?`` of the line: the last command's status, or 2 when the line could not run as written,
    124 when its deadline passed, 130 when it was cancelled and 137 when a budget ended it."""
    statuses: list[list[int]] = Field(default_factory=list)
    """``PIPESTATUS`` after each pipeline of the line's top level that set it, in order: ``[[1, 0]]`` for
    ``cat /nope | wc -l``. A pipeline inside a loop, a function or a compound command adds no entry
    of its own, so the list is bounded by the line's text. A pipeline that did not run, a function
    definition and a compound command that ran no pipeline set none and add no entry."""
    fuel_used: int = 0
    """The instructions the line executed inside the machine's module, a function of the line and its replies."""

    def to_str(self, *, projection: tuple[str, ...] | list[str] | None = None) -> str:
        """The line's standard output, then its standard error, then its facts after a blank line."""
        facts = Result(ops=self.ops, errors=self.errors).to_str(projection=projection)
        printed = self.stdout + self.stderr
        return f"{printed}\n{facts}" if facts else printed


def library_programs() -> list[str]:
    """The library's programs the machine runs itself: every one the host does not resolve."""
    return [name for name in extension().SHELL_PROGRAMS if name not in PROGRAMS]


def refused_line(fact: ResultError) -> LineResult:
    """The result of a line that never started, for the one fact that stopped it."""
    return LineResult(errors=[fact], exit_code=2)


async def run_line(
    fs: Router,
    line: str,
    authority: Authority,
    *,
    cwd: str = "/",
    stdin: bytes = b"",
    env: Sequence[tuple[str, str]] = ENVIRONMENT,
    limits: Mapping[str, int] | None = None,
    fuel: int | None = None,
    deadline: Deadline | None = None,
) -> LineResult:
    """Run ``line`` as ``authority`` and return its output, its exit status and its evidence.

    The result carries ``stdout`` and ``stderr`` as text and ``exit_code`` as an int. It fails
    only when the line could not run as written: it does not parse, it holds a refused construct,
    or a budget, the deadline or a cancel ended it. A program that exits non-zero is not a
    failure of the call. ``env`` is the environment the line starts with, and ``limits`` lowers
    or raises the machine's budgets by name, each one of :data:`LIMITS`; an unknown name or a
    value that is no count from 0 to 2**64 fails the call as ``invalid``. ``fuel`` is the
    instructions the line may execute, and ``deadline`` the instant it must end by,
    ``DEADLINE_SECONDS`` from the call when not given.

    The machine runs inside its WebAssembly module, one slice at a time on the process pool, so
    the event loop never waits on it. A cancelled call cancels the line: the slice running then
    ends within one tick of the runtime's clock.
    """
    deadline = deadline if deadline is not None else Deadline.after(DEADLINE_SECONDS)
    refused = sorted(name for name, value in (limits or {}).items() if name not in LIMITS or not _a_budget(value))
    if refused:
        detail = f"no such budget, or no count: {', '.join(refused)}; the budgets are {', '.join(sorted(LIMITS))}"
        return refused_line(classified(ErrorKind.invalid, detail=detail))
    if authority.actor.is_system:
        detail = "a line never runs as the system actor; name the caller's authority"
        return refused_line(classified(ErrorKind.invalid, detail=detail))
    start = partial(
        extension().ShellMachine,
        line,
        env=[*env, ("PWD", cwd)],
        cwd=cwd,
        name=SHELL_NAME,
        args=[],
        stdin=stdin,
        programs=library_programs(),
        host_programs=list(PROGRAMS),
        pid=PID,
        limits=dict(limits) if limits is not None else None,
        fuel=fuel,
        deadline=deadline.remaining(),
    )
    try:
        machine = await call_offloaded(offload_pool(), start)
    except ValueError as error:
        kind, message, line_number, column = error.args
        fact = classified(
            _FAILURE_KIND.get(kind, ErrorKind.internal),
            detail=message,
            data={"line": line_number, "column": column},
        )
        return LineResult(
            errors=[fact], stdout="", stderr=f"{SHELL_NAME}: line {line_number}: {message}\n", exit_code=2
        )
    host = _Host(fs, authority)
    stdout = bytearray()
    stderr = bytearray()
    statuses: list[list[int]] = []
    replies: list[tuple[str, str, object]] = []
    try:
        while True:
            output, requests, (state, status, reason), ended = await call_offloaded(
                offload_pool(), partial(machine.step, replies)
            )
            statuses.extend(ended)
            for stream, chunk in output:
                (stdout if stream == 1 else stderr).extend(chunk)
            replies = [(key, *await host.answer(op, {**args, "key": key})) for key, op, args in requests]
            if state != "running":
                break
    except asyncio.CancelledError:
        machine.cancel()
        raise
    errors = list(host.evidence)
    if state == "ended":
        errors.append(_ended(reason or ""))
    return LineResult(
        errors=errors,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
        exit_code=status,
        statuses=statuses,
        fuel_used=machine.fuel_used,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _a_budget(value: object) -> bool:
    """Whether ``value`` is a count the machine can hold: an integer, not a bool, from 0 to 2**64."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 1 << 64


def _ended(reason: str) -> ResultError:
    """The fact for a line a budget, a cancel or a fault ended."""
    if reason.startswith("Budget"):
        return classified(ErrorKind.budget_exhausted, detail=reason)
    if reason.startswith("Cancelled"):
        return classified(ErrorKind.cancelled)
    if reason.startswith("Deadline"):
        return classified(ErrorKind.timeout, detail="the line's deadline passed")
    return classified(ErrorKind.internal, detail=reason)


class _Seen(NamedTuple):
    """The version of a file an open saw at its first read."""

    path: str
    version: int | None


class _Host:
    """One line's answers: each request a public verb called as the line's authority."""

    def __init__(self, fs: Router, authority: Authority) -> None:
        self._fs = fs
        self._authority = authority
        self._bodies: dict[_Seen, bytes] = {}
        self._held = 0
        self._opens: dict[str, _Seen] = {}
        self._sharers: dict[_Seen, int] = {}
        self._running: dict[str, list[tuple[bytes, bytes, int | None]]] = {}
        self._facts: dict[tuple[str, str | None, str], ResultError] = {}
        self._unkept = 0

    @property
    def fs(self) -> Router:
        """The router every request and program of the line calls."""
        return self._fs

    @property
    def authority(self) -> Authority:
        """The authority the line was admitted as."""
        return self._authority

    @property
    def evidence(self) -> list[ResultError]:
        """Each distinct refusal of the line once, as a warning, and a rollup of those past the count."""
        facts = list(self._facts.values())
        if self._unkept:
            message = f"{self._unkept} more refusals inside the line are not kept"
            rollup = {"vfs.rollup": {"count": self._unkept, "sources": []}}
            facts.append(classified(ErrorKind.truncated, detail=message, data=rollup, severity=Severity.warning))
        return facts

    def keep(self, fact: ResultError) -> None:
        """Keep ``fact`` as a warning of the line, once, while fewer than ``LINE_FACTS`` are kept."""
        key = (str(fact.kind), fact.path, fact.message)
        if key in self._facts:
            return
        if len(self._facts) >= LINE_FACTS:
            self._unkept += 1
            return
        self._facts[key] = fact.model_copy(update={"severity": Severity.warning})

    async def answer(self, op: str, args: dict[str, Any]) -> tuple[str, object]:
        """The reply to one request, as the machine reads it."""
        if op == "read":
            return await self._read(args["path"], args["open"], args["offset"], args["length"])
        if op == "stat":
            return await self._stat(args["path"])
        if op == "list":
            return await self._list(args["path"])
        if op == "value":
            return _value(args["name"])
        if op == "start":
            return await self._start(args)
        if op == "feed":
            return await self._feed(args)
        return await self._mutate(op, args)

    async def _read(self, path: str, opened: str, offset: int, length: int) -> tuple[str, object]:
        """A slice of the body the open named ``opened`` saw. Its first read is a ``read`` of the
        whole body, judged as the caller; a later one reads it again only if it gave way, and
        refuses it if the file has moved to another version since. Opens that saw one version of
        one file share its body."""
        seen = self._opens.get(opened)
        body = None if seen is None else self._bodies.pop(seen, None)
        if body is None:
            result = await self._fs.read(path, columns=_BODY, authority=self._authority)
            refusal = self._refusal(result)
            if refusal is not None:
                self._close(opened)
                return refusal
            row = result.observations[0]
            if seen is not None and seen.version != row.version:
                self._close(opened)
                self.keep(classified(ErrorKind.conflict, Path(path), detail="the file changed while it was open"))
                return "error", "invalid"
            if seen is None:
                seen = _Seen(path, row.version)
                self._opens[opened] = seen
                self._sharers[seen] = self._sharers.get(seen, 0) + 1
            self._held -= len(self._bodies.pop(seen, b""))
            body = row.data if row.data is not None else (row.content or "").encode()
        else:
            self._held -= len(body)
        end = offset + length
        if end >= len(body):
            self._close(opened)
        if seen in self._sharers:
            self._hold(seen, body)
        return "data", (body[offset:end], end >= len(body))

    def _close(self, opened: str) -> None:
        """Forget the open named ``opened``, and the body it saw once no other open shares it."""
        seen = self._opens.pop(opened, None)
        if seen is None:
            return
        self._sharers[seen] -= 1
        if not self._sharers[seen]:
            del self._sharers[seen]
            self._held -= len(self._bodies.pop(seen, b""))

    def _hold(self, seen: _Seen, body: bytes) -> None:
        """Keep ``body`` for the opens that saw it, last in line. Past ``READING_BYTES`` the bodies
        read least recently give way, never this one; their opens keep the version they saw."""
        self._bodies[seen] = body
        self._held += len(body)
        while self._held > READING_BYTES and len(self._bodies) > 1:
            self._held -= len(self._bodies.pop(next(iter(self._bodies))))

    async def _stat(self, path: str) -> tuple[str, object]:
        result = await self._fs.stat(path, authority=self._authority)
        refusal = self._refusal(result, keep=False)
        if refusal is not None:
            return refusal
        row = result.observations[0]
        kind = _KIND_OF.get(row.kind or "", "file")
        return "stat", (kind, row.size_bytes or 0)

    async def _list(self, path: str) -> tuple[str, object]:
        result = await self._fs.ls(path, authority=self._authority)
        refusal = self._refusal(result)
        if refusal is not None:
            return refusal
        entries = [
            (str(row.path).rsplit("/", 1)[-1], _KIND_OF.get(row.kind or "", "file")) for row in result.observations
        ]
        return "entries", entries

    async def _start(self, args: dict[str, Any]) -> tuple[str, object]:
        """Resolve a program name: vfs's own program, run now, the library's, a refusal, or not found."""
        name = args["name"]
        if name in REFUSED_PROGRAMS:
            self.keep(classified(ErrorKind.unsupported, detail=f"{name}: {REFUSED_PROGRAMS[name]}"))
            return "refused", (126, REFUSED_PROGRAMS[name])
        if name in UNKNOWN_PROGRAMS:
            return "refused", (127, UNKNOWN_PROGRAMS[name])
        program = PROGRAMS.get(name)
        if program is None:
            return "error", "not_found"
        ran = await program(self, list(args["args"]), args["cwd"])
        if ran is None:
            return "library", None
        replies: list[tuple[bytes, bytes, int | None]] = [
            (chunk, b"", None) if stream == 1 else (b"", chunk, None) for stream, chunk in ran.writes
        ]
        if replies:
            replies[-1] = (*replies[-1][:2], ran.status)
        else:
            replies.append((b"", b"", ran.status))
        self._running[args["key"]] = replies
        return "started", None

    async def _feed(self, args: dict[str, Any]) -> tuple[str, object]:
        """The next of a program's writes, in the order it made them, its status on the last."""
        replies = self._running[args["program"]]
        reply = replies.pop(0)
        if not replies:
            del self._running[args["program"]]
        return "output", reply

    async def _mutate(self, op: str, args: dict[str, Any]) -> tuple[str, object]:
        fs, who = self._fs, self._authority
        if op == "write":
            body = _body(args["data"])
            mode = args["mode"]
            result = await fs.write(
                path=args["path"], **body, append=mode == "append", if_absent=mode == "create_new", authority=who
            )
        elif op == "touch":
            result = await fs.write(path=args["path"], content="", if_absent=True, authority=who)
            if result.failures and result.failures[0].kind == ErrorKind.exists:
                return "done", None
        elif op == "mkdir":
            result = await fs.mkdir(args["path"], parents=args["parents"], exist_ok=args["parents"], authority=who)
        elif op == "remove":
            result = await fs.delete(args["path"], cascade=args["recursive"], authority=who)
        elif op == "copy":
            result = await fs.copy(args["source"], args["target"], authority=who)
        elif op == "move":
            result = await fs.move(args["source"], args["target"], authority=who)
        else:
            return "error", "unsupported"
        return self._refusal(result) or ("done", None)

    def _refusal(self, result: Result, *, keep: bool = True) -> tuple[str, object] | None:
        """The host error for a refused verb, kept as evidence; ``None`` when the verb succeeded."""
        if result.success:
            return None
        fact = result.failures[0]
        if keep:
            self.keep(fact)
        if fact.kind == ErrorKind.wrong_kind:
            named = (fact.data or {}).get("kind")
            return "error", "is_a_directory" if named == "directory" else "not_a_directory"
        return "error", _HOST_ERROR.get(fact.kind, "invalid")


def _body(data: bytes) -> dict[str, Any]:
    """A written body as the router takes it: text when it is UTF-8, bytes when not."""
    try:
        return {"content": data.decode()}
    except UnicodeDecodeError:
        return {"data": data}


def _value(name: str) -> tuple[str, object]:
    """A value that is not a function of the line."""
    if name == "time":
        return "text", str(int(time.time()))
    if name == "random":
        return "text", str(random.randrange(32768))
    return "error", "unsupported"
