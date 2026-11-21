"""The vfs host of the shell's machine.

:func:`run_line` starts the machine on a line and drives it to its end. Every
request the machine asks becomes one call of a public verb of the router,
with the authority the caller was admitted as. A verb's refusal becomes the
error a Unix tool would see, so ``cat`` prints "No such file or directory"
where the router says ``not_found``, and the refusal itself is kept on the
result as a warning: a program's failure is evidence, not the call's failure.

A line is parsed whole before anything runs, so a syntax error, a refused
construct or a spent parse budget fails the call and touches nothing.

The bodies the line reads are held for the rest of the line, so a file read
in chunks is one ``read``; any write, move, copy or delete forgets them.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING, Any, Final

from vfs.native import extension
from vfs.results import ErrorKind, Result, ResultError, Severity, classified

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from vfs.authority import Authority
    from vfs.base import AsyncVirtualFileSystem

SHELL_NAME: Final = "bash"
"""``$0`` of every line, so its errors read as bash's do."""

ENVIRONMENT: Final[tuple[tuple[str, str], ...]] = (
    ("HOME", "/"),
    ("PATH", "/usr/bin:/bin"),
    ("LC_ALL", "C.UTF-8"),
    ("TZ", "UTC"),
)
"""The environment a line starts with."""

PID: Final = 1000
"""``$$`` of every line: the machine is no process, and a fixed value keeps a line a function of its input."""

_KIND_OF: Final[dict[str, str]] = {"directory": "directory"}

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

_FAILURE_KIND: Final[dict[str, ErrorKind]] = {
    "syntax": ErrorKind.invalid,
    "refused": ErrorKind.unsupported,
    "budget": ErrorKind.budget_exhausted,
}

# ---------------------------------------------------------------------------
# Running a line
# ---------------------------------------------------------------------------


class LineResult(Result):
    """What ``cli`` returns: a :class:`Result` with what the line printed and the status it exited with.

    ``stdout`` and ``stderr`` are the bytes bash would print, decoded as UTF-8 with invalid bytes
    replaced. ``exit_status`` is the status bash would exit with. The errors are the classified facts:
    a line that could not run, a budget that ended it, and each verb a program was refused.
    """

    stdout: str = ""
    """What the line wrote to standard output."""
    stderr: str = ""
    """What the line wrote to standard error."""
    exit_status: int = 0
    """The last command's status, or 2, 130 or 137 when the line could not run, was cancelled or hit a budget."""


async def run_line(
    fs: AsyncVirtualFileSystem,
    line: str,
    authority: Authority,
    *,
    cwd: str = "/",
    stdin: bytes = b"",
    env: Sequence[tuple[str, str]] = ENVIRONMENT,
    limits: Mapping[str, int] | None = None,
) -> LineResult:
    """Run ``line`` as ``authority`` and return its output, its exit status and its evidence.

    The result carries ``stdout`` and ``stderr`` as text and ``exit_status`` as an int. It fails
    only when the line could not run as written: it does not parse, it holds a refused construct,
    or a budget ended it. A program that exits non-zero is not a failure of the call. ``env`` is
    the environment the line starts with, and ``limits`` lowers or raises the machine's budgets
    by name (``memory_bytes``, ``loop_iterations``, ``function_depth``, ``slice`` and the parse
    budgets).
    """
    if authority.actor.is_system:
        detail = "a line never runs as the system actor; name the caller's authority"
        return LineResult(errors=[classified(ErrorKind.invalid, detail=detail)], exit_status=2)
    try:
        machine = extension().ShellMachine(
            line,
            env=[*env, ("PWD", cwd)],
            cwd=cwd,
            name=SHELL_NAME,
            args=[],
            stdin=stdin,
            programs=list(extension().SHELL_PROGRAMS),
            pid=PID,
            limits=dict(limits) if limits is not None else None,
        )
    except ValueError as error:
        kind, message, line_number, column = error.args
        fact = classified(
            _FAILURE_KIND.get(kind, ErrorKind.internal),
            detail=message,
            data={"line": line_number, "column": column},
        )
        return LineResult(
            errors=[fact], stdout="", stderr=f"{SHELL_NAME}: line {line_number}: {message}\n", exit_status=2
        )
    host = _Host(fs, authority)
    stdout = bytearray()
    stderr = bytearray()
    replies: list[tuple[str, str, object]] = []
    while True:
        output, requests, (state, status, reason) = machine.step(replies)
        for stream, chunk in output:
            (stdout if stream == 1 else stderr).extend(chunk)
        replies = [(key, *await host.answer(op, args)) for key, op, args in requests]
        if state != "running":
            break
    errors = list(host.evidence)
    if state == "ended":
        errors.append(_ended(reason or ""))
    return LineResult(
        errors=errors,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
        exit_status=status,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ended(reason: str) -> ResultError:
    """The fact for a line a budget, a cancel or a fault ended."""
    if reason.startswith("Budget"):
        return classified(ErrorKind.budget_exhausted, detail=reason)
    if reason.startswith("Cancelled"):
        return classified(ErrorKind.cancelled)
    return classified(ErrorKind.internal, detail=reason)


class _Host:
    """One line's answers: each request a public verb called as the line's authority."""

    def __init__(self, fs: AsyncVirtualFileSystem, authority: Authority) -> None:
        self._fs = fs
        self._authority = authority
        self._bodies: dict[str, bytes] = {}
        self.evidence: list[ResultError] = []

    async def answer(self, op: str, args: dict[str, Any]) -> tuple[str, object]:
        """The reply to one request, as the machine reads it."""
        if op == "read":
            return await self._read(args["path"], args["offset"], args["length"])
        if op == "stat":
            return await self._stat(args["path"])
        if op == "list":
            return await self._list(args["path"])
        if op == "value":
            return _value(args["name"])
        self._bodies.clear()
        return await self._mutate(op, args)

    async def _read(self, path: str, offset: int, length: int) -> tuple[str, object]:
        body = self._bodies.get(path)
        if body is None:
            result = await self._fs.read(path, columns=_BODY, authority=self._authority)
            refusal = self._refusal(result)
            if refusal is not None:
                return refusal
            row = result.observations[0]
            body = row.data if row.data is not None else (row.content or "").encode()
            self._bodies[path] = body
        end = offset + length
        return "data", (body[offset:end], end >= len(body))

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
        else:
            result = await fs.move(args["source"], args["target"], authority=who)
        return self._refusal(result) or ("done", None)

    def _refusal(self, result: Result, *, keep: bool = True) -> tuple[str, object] | None:
        """The host error for a refused verb, kept as evidence; ``None`` when the verb succeeded."""
        if result.success:
            return None
        fact = result.failures[0]
        if keep:
            self.evidence.append(fact.model_copy(update={"severity": Severity.warning}))
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
