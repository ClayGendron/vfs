"""S3 experiment — a Python reference of the one program ABI, and a two-stage pipe.

Run from the vfs repo root:

    uv run python context/research/studies/2026-10-15-agent-shell/experiments/s3/abi_demo.py

What it builds, in order:

1. The pipe payload: a stream of chunks, each chunk either ``Rows`` (a
   ``Result`` slice: rows + classified errors, op-tagged) or ``Bytes`` (a
   byte buffer with a mime). Never both in one chunk.
2. The ABI: a ``Program`` declares the shape it consumes and produces
   (``rows`` or ``bytes``) and has one entry point ``main(call) -> int``.
   ``call`` carries args, env, cwd, stdin (a chunk stream), stdout (a
   chunk sink), stderr (a text sink) and ``fs`` — the verb capability bound
   to an ``Authority``. Nothing else is reachable.
3. Three programs: ``ls`` and ``cat`` and ``grep`` (verb builtins, rows in /
   rows out), ``wc`` (a text kernel, bytes in / bytes out), and ``id.wasm``
   (a stub for a wasi binary: bytes in / bytes out, whole-stdin staging,
   argv-chosen exit code).
4. The two laws at the seams: rows become bytes only when the consumer is
   byte-shaped (through the one render chokepoint, except a single bytes-
   bodied ``read`` row, which crosses raw with its mime); bytes become rows
   only when the consumer is row-shaped (one row, sniffed into content XOR
   data with a mime).
5. The pipe runner: every stage a task, bounded queues between stages
   (backpressure), PIPESTATUS, ``$?`` = last stage, pipefail = rightmost
   failure, stderr merged in order with a stage prefix.

Everything printed is labelled EXECUTED in the report.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

from vfs import Authority, Principal, VirtualFileSystem
from vfs.models import Entry, Observation
from vfs.models.media import SNIFF_LENGTH, sniff_mime
from vfs.paths import Path
from vfs.results import ErrorKind, Result
from vfs.results.kinds import kind_family
from vfs.storage.backends.memory import InMemoryStorage

# ---------------------------------------------------------------------------
# 1. The pipe payload
# ---------------------------------------------------------------------------

Shape = Literal["rows", "bytes"]


@dataclass(frozen=True)
class Rows:
    """One slice of a result stream: rows plus the errors found while producing them."""

    result: Result


@dataclass(frozen=True)
class Bytes:
    """One buffer of a byte stream. ``mime_type`` is what the producer knows, else None."""

    data: bytes
    mime_type: str | None = None


Chunk = Rows | Bytes

ROWS_PER_CHUNK = 1000
"""A producer never hands the pipe more than this many rows at once."""


class Sink(Protocol):
    async def emit(self, chunk: Chunk) -> None: ...


class TextSink(Protocol):
    def write(self, text: str) -> None: ...


# ---------------------------------------------------------------------------
# 2. The ABI
# ---------------------------------------------------------------------------


class Fs(Protocol):
    """The filesystem capability: the vfs verbs, already bound to one Authority.

    A program never sees the Authority and never passes one. It cannot
    widen what it holds because there is no parameter to widen.
    """

    async def ls(self, path: str) -> Result: ...
    async def read(self, path: str) -> Result: ...
    async def glob(self, pattern: str) -> Result: ...
    async def grep(self, pattern: str, *, observations: list[Observation] | None) -> Result: ...
    async def write(self, path: str, *, content: str | None = None, data: bytes | None = None) -> Result: ...


@dataclass
class Call:
    """Everything a program gets. There is no other door."""

    args: tuple[str, ...]
    env: Mapping[str, str]
    cwd: Path
    stdin: AsyncIterator[Chunk]
    stdout: Sink
    stderr: TextSink
    fs: Fs


class Program(Protocol):
    name: str
    consumes: Shape
    produces: Shape

    async def main(self, call: Call) -> int: ...


class BoundFs:
    """``Fs`` over the live router: every verb re-enters the public method with the bound authority."""

    def __init__(self, vfs: VirtualFileSystem, authority: Authority) -> None:
        self._vfs = vfs
        self._authority = authority

    async def ls(self, path: str) -> Result:
        return await self._vfs.ls(path, authority=self._authority)

    async def read(self, path: str) -> Result:
        # A byte program must get the file, so the bytes body is projected
        # explicitly: ``read`` elides ``data`` unless the column is asked for.
        columns = frozenset({"content", "data", "mime_type", "size_bytes", "kind"})
        return await self._vfs.read(path, columns=columns, authority=self._authority)

    async def glob(self, pattern: str) -> Result:
        return await self._vfs.glob(pattern, authority=self._authority)

    async def grep(self, pattern: str, *, observations: list[Observation] | None) -> Result:
        return await self._vfs.grep(pattern, observations=observations, authority=self._authority)

    async def write(self, path: str, *, content: str | None = None, data: bytes | None = None) -> Result:
        return await self._vfs.write(path=path, content=content, data=data, parents=True, authority=self._authority)


# ---------------------------------------------------------------------------
# Exit codes from a Result — the one mapping every verb builtin uses
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_TIMEOUT = 124
EXIT_NOT_EXECUTABLE = 126
EXIT_NOT_FOUND = 127
EXIT_CANCELLED = 130

_KIND_EXIT: dict[str, int] = {
    ErrorKind.timeout: EXIT_TIMEOUT,
    ErrorKind.cancelled: EXIT_CANCELLED,
    ErrorKind.permission_denied: EXIT_NOT_EXECUTABLE,
    ErrorKind.unauthenticated: EXIT_NOT_EXECUTABLE,
    ErrorKind.unsupported: EXIT_NOT_EXECUTABLE,
    ErrorKind.unrecognized: EXIT_NOT_FOUND,
}


def exit_code_for(result: Result) -> int:
    """``0`` when the envelope succeeds; else the code of its first fatal fact's family, else ``1``."""
    if result.success:
        return EXIT_OK
    for error in result.failures:
        family = kind_family(error.kind)
        if family is not None and family in _KIND_EXIT:
            return _KIND_EXIT[family]
    return EXIT_FAILURE


def errors_to_stderr(result: Result) -> str:
    """The error lines of a result, rendered by the one chokepoint (an empty-row failure renders errors alone)."""
    if not result.errors:
        return ""
    return Result(ops=result.ops, errors=result.errors).to_str() + "\n"


async def emit_rows(stdout: Sink, result: Result) -> int:
    """Hand *result* to the pipe in slices of ``ROWS_PER_CHUNK`` rows; errors ride on the first slice."""
    rows = result.observations
    if not rows:
        await stdout.emit(Rows(Result(ops=result.ops, errors=result.errors)))
        return 1
    chunks = 0
    for start in range(0, len(rows), ROWS_PER_CHUNK):
        errors = result.errors if start == 0 else []
        await stdout.emit(Rows(Result(ops=result.ops, observations=rows[start : start + ROWS_PER_CHUNK], errors=errors)))
        chunks += 1
    return chunks


# ---------------------------------------------------------------------------
# 3. Three kinds of program
# ---------------------------------------------------------------------------


class Ls:
    """Verb builtin: rows out. Stdin is ignored (``ls`` never reads it)."""

    name = "ls"
    consumes: Shape = "rows"
    produces: Shape = "rows"

    async def main(self, call: Call) -> int:
        target = call.args[0] if call.args else str(call.cwd)
        result = await call.fs.ls(target)
        call.stderr.write(errors_to_stderr(result))
        await emit_rows(call.stdout, result)
        return exit_code_for(result)


class Cat:
    """Verb builtin: ``read`` each argument; rows out — a bytes body stays bytes on its row."""

    name = "cat"
    consumes: Shape = "rows"
    produces: Shape = "rows"

    async def main(self, call: Call) -> int:
        code = EXIT_OK
        for arg in call.args:
            result = await call.fs.read(arg)
            call.stderr.write(errors_to_stderr(result))
            await emit_rows(call.stdout, result)
            code = max(code, exit_code_for(result))
        return code


class Glob:
    name = "glob"
    consumes: Shape = "rows"
    produces: Shape = "rows"

    async def main(self, call: Call) -> int:
        result = await call.fs.glob(call.args[0])
        call.stderr.write(errors_to_stderr(result))
        await emit_rows(call.stdout, result)
        return exit_code_for(result)


class Grep:
    """Verb builtin that *consumes* rows: upstream rows scope the search, no text is re-parsed."""

    name = "grep"
    consumes: Shape = "rows"
    produces: Shape = "rows"

    async def main(self, call: Call) -> int:
        scope: list[Observation] = []
        async for chunk in call.stdin:
            assert isinstance(chunk, Rows)
            scope.extend(chunk.result.observations)
        result = await call.fs.grep(call.args[0], observations=scope or None)
        call.stderr.write(errors_to_stderr(result))
        await emit_rows(call.stdout, result)
        return exit_code_for(result)


class Wc:
    """Text kernel: bytes in, bytes out. Counts like POSIX wc; ``-l`` prints lines only.

    It is written against bytes on purpose: the same code would be a Rust
    kernel or a wasi binary. It also records how many chunks it saw.
    """

    name = "wc"
    consumes: Shape = "bytes"
    produces: Shape = "bytes"

    def __init__(self) -> None:
        self.chunks_seen = 0

    async def main(self, call: Call) -> int:
        lines = words = nbytes = 0
        tail = b""
        async for chunk in call.stdin:
            assert isinstance(chunk, Bytes)
            self.chunks_seen += 1
            data = tail + chunk.data
            nbytes += len(chunk.data)
            lines += data.count(b"\n")
            parts = data.split()
            # A word split across chunks is counted once: keep the unfinished tail.
            if data and not data[-1:].isspace():
                tail = parts.pop() if parts else data
            else:
                tail = b""
            words += len(parts)
        if tail:
            words += 1
        out = f"{lines}\n" if "-l" in call.args else f"{lines} {words} {nbytes}\n"
        await call.stdout.emit(Bytes(out.encode(), "text/plain"))
        return EXIT_OK


class IdWasm:
    """Stub for a wasi binary: stages ALL of stdin (whole-file model), writes it back, exits as told.

    ``--exit N`` sets the exit status; ``--stderr TEXT`` writes to stderr.
    The real thing is a wasmtime instance; the ABI it sees is identical.
    """

    name = "id.wasm"
    consumes: Shape = "bytes"
    produces: Shape = "bytes"

    async def main(self, call: Call) -> int:
        staged = bytearray()
        mime: str | None = None
        async for chunk in call.stdin:
            assert isinstance(chunk, Bytes)
            staged += chunk.data
            mime = mime or chunk.mime_type
        args = list(call.args)
        code = int(args[args.index("--exit") + 1]) if "--exit" in args else EXIT_OK
        if "--stderr" in args:
            call.stderr.write(args[args.index("--stderr") + 1] + "\n")
        await call.stdout.emit(Bytes(bytes(staged), mime))
        return code


# ---------------------------------------------------------------------------
# 4. The two laws at the seams
# ---------------------------------------------------------------------------


def rows_to_bytes(chunk: Rows) -> Bytes:
    """Rows → bytes, only ever for a byte-shaped consumer.

    One bytes-bodied ``read`` row crosses raw with its mime (a byte
    program asked for the file, give it the file). Everything else is the
    canonical text rendering of the slice — the producing op's default
    projection — so ``ls`` is one path per line and ``read`` is the body.
    """
    result = chunk.result
    if result.op == "read" and len(result.observations) == 1:
        row = result.one()
        if row.data is not None:
            return Bytes(row.data, row.mime_type)
    # Errors never cross a byte seam: they went to the stage's stderr. Only rows render.
    text = Result(ops=result.ops, observations=result.observations).to_str()
    return Bytes(text.encode() + (b"\n" if text else b""), "text/plain")


def bytes_to_rows(data: bytes, mime_type: str | None, *, stage: int) -> Rows:
    """Bytes → rows, only ever for a row-shaped consumer: exactly one row.

    Valid UTF-8 without NUL is ``content``; anything else is ``data`` with
    a sniffed mime. The row needs a path — ``Observation.path`` is
    required — so it gets a synthetic one under ``/.vfs/run``.
    """
    path = Path(f"/.vfs/run/{stage}/stdout")
    try:
        text = data.decode("utf-8")
        is_text = "\x00" not in text
    except UnicodeDecodeError:
        is_text = False
    if is_text:
        row = Observation(path=path, kind="file", content=text, mime_type=mime_type or "text/plain", size_bytes=len(data))
    else:
        row = Observation(
            path=path,
            kind="file",
            data=data,
            mime_type=sniff_mime(data[:SNIFF_LENGTH], declared=mime_type),
            size_bytes=len(data),
        )
    return Rows(Result(ops=("run",), observations=[row]))


# ---------------------------------------------------------------------------
# 5. The pipe runner
# ---------------------------------------------------------------------------

_END = object()
QUEUE_DEPTH = 2
"""Chunks a producer may run ahead of its consumer — the backpressure bound."""


class QueueSink:
    def __init__(self, queue: asyncio.Queue) -> None:
        self.queue = queue
        self.emitted = 0
        self.max_depth = 0

    async def emit(self, chunk: Chunk) -> None:
        await self.queue.put(chunk)
        self.emitted += 1
        self.max_depth = max(self.max_depth, self.queue.qsize())


class StageStderr:
    def __init__(self, prefix: str, log: list[str]) -> None:
        self.prefix, self.log = prefix, log

    def write(self, text: str) -> None:
        for line in text.splitlines():
            self.log.append(f"{self.prefix}: {line}")


async def drain(queue: asyncio.Queue) -> AsyncIterator[Chunk]:
    while (item := await queue.get()) is not _END:
        yield item


async def adapt(upstream: AsyncIterator[Chunk], consumer: Shape, *, stage: int) -> AsyncIterator[Chunk]:
    """Apply the seam laws between two stages. Same shape: pass through untouched."""
    pending = bytearray()
    pending_mime: str | None = None
    async for chunk in upstream:
        if isinstance(chunk, Rows) and consumer == "bytes":
            yield rows_to_bytes(chunk)
        elif isinstance(chunk, Bytes) and consumer == "rows":
            # One program output is one row: gather, mint once at end of stream.
            pending += chunk.data
            pending_mime = pending_mime or chunk.mime_type
        else:
            yield chunk
    if consumer == "rows" and (pending or pending_mime is not None):
        yield bytes_to_rows(bytes(pending), pending_mime, stage=stage)


async def empty_stdin() -> AsyncIterator[Chunk]:
    return
    yield  # pragma: no cover


@dataclass
class PipeOutcome:
    rows: Result
    stderr: list[str]
    pipestatus: list[int]
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def status(self) -> int:
        return self.pipestatus[-1]

    @property
    def pipefail_status(self) -> int:
        failing = [code for code in self.pipestatus if code != 0]
        return failing[-1] if failing else 0


async def run_pipeline(
    stages: list[tuple[Program, tuple[str, ...]]],
    *,
    fs: Fs,
    env: Mapping[str, str],
    cwd: Path,
) -> PipeOutcome:
    """Run ``stages`` as one pipeline. The terminal boundary is row-shaped: the pipe's end is a Result."""
    stderr_log: list[str] = []
    queues = [asyncio.Queue(maxsize=QUEUE_DEPTH) for _ in stages]
    sinks = [QueueSink(q) for q in queues]
    tasks: list[Awaitable[int]] = []
    upstream: AsyncIterator[Chunk] = empty_stdin()
    for index, (program, args) in enumerate(stages):
        stdin = adapt(upstream, program.consumes, stage=index)
        call = Call(args=args, env=env, cwd=cwd, stdin=stdin, stdout=sinks[index], stderr=StageStderr(program.name, stderr_log), fs=fs)
        tasks.append(_run_stage(program, call, queues[index]))
        upstream = drain(queues[index])
    terminal = adapt(upstream, "rows", stage=len(stages))
    collected: list[Result] = []

    async def collect() -> None:
        async for chunk in terminal:
            assert isinstance(chunk, Rows)
            collected.append(chunk.result)

    codes, _ = await asyncio.gather(asyncio.gather(*tasks), collect())
    merged = Result.merge(collected)
    stats = {f"{p.name}@{i}.chunks_emitted": s.emitted for i, ((p, _), s) in enumerate(zip(stages, sinks, strict=True))}
    stats |= {f"{p.name}@{i}.max_queue_depth": s.max_depth for i, ((p, _), s) in enumerate(zip(stages, sinks, strict=True))}
    return PipeOutcome(rows=merged, stderr=stderr_log, pipestatus=list(codes), stats=stats)


async def _run_stage(program: Program, call: Call, queue: asyncio.Queue) -> int:
    try:
        return await program.main(call)
    finally:
        await queue.put(_END)


# ---------------------------------------------------------------------------
# The demonstration
# ---------------------------------------------------------------------------

PNG_HEAD = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24

Scenario = Callable[[], Awaitable[None]]


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def show(outcome: PipeOutcome, *, projection: tuple[str, ...] | None = None) -> None:
    print("stdout (rows rendered at the terminal boundary):")
    text = outcome.rows.to_str(projection=projection)
    print("  " + text.replace("\n", "\n  ") if text else "  <empty>")
    print(f"stderr: {outcome.stderr if outcome.stderr else '<none>'}")
    print(f"PIPESTATUS={outcome.pipestatus}  $?={outcome.status}  pipefail={outcome.pipefail_status}")
    print(f"ops={outcome.rows.ops} rows={len(outcome.rows)} success={outcome.rows.success}")
    print(f"stats={outcome.stats}")


async def main() -> None:
    vfs = VirtualFileSystem(storage=InMemoryStorage())
    alice = Authority.of(Principal("alice"))
    fs = BoundFs(vfs, alice)
    env = {"HOME": "/home/alice", "PATH": "/.agents/bin"}
    cwd = Path("/src")

    seed = [
        Entry(path="/src/auth.py", content="def login():\n    return 'auth ok'\n"),
        Entry(path="/src/db.py", content="def connect():\n    pass\n"),
        Entry(path="/src/README.md", content="# src\n\nauth lives in auth.py\n"),
        Entry(path="/img/logo.png", data=PNG_HEAD),
    ]
    wrote = await vfs.write(seed, parents=True, authority=alice)
    assert wrote.success, wrote.to_str()

    banner("A. ls /src | wc -l  (rows -> bytes at the ls|wc seam; bytes -> rows at the terminal)")
    wc = Wc()
    out = await run_pipeline([(Ls(), ("/src",)), (wc, ("-l",))], fs=fs, env=env, cwd=cwd)
    show(out)
    print("same rows, projection=('content',):")
    print("  " + out.rows.to_str(projection=("content",)).replace("\n", "\n  "))
    print(f"the row itself: path={out.rows.one().path} mime={out.rows.one().mime_type} content={out.rows.one().content!r}")

    banner("B. cat /src/auth.py | wc  (a text read row crosses as its body, not as a table)")
    out = await run_pipeline([(Cat(), ("/src/auth.py",)), (Wc(), ())], fs=fs, env=env, cwd=cwd)
    show(out, projection=("content",))

    banner("C. cat /img/logo.png | id.wasm  (one bytes-bodied read row crosses RAW; stdout sniffs back to a media row)")
    out = await run_pipeline([(Cat(), ("/img/logo.png",)), (IdWasm(), ())], fs=fs, env=env, cwd=cwd)
    show(out)
    row = out.rows.one()
    print(f"the row itself: path={row.path} mime={row.mime_type} data_len={len(row.data or b'')} content={row.content!r} populated={sorted(row.populated)}")

    banner("D. glob '**/*.py' | grep auth  (rows -> rows: grep scopes to upstream rows, no text re-parse)")
    out = await run_pipeline([(Glob(), ("**/*.py",)), (Grep(), ("auth",))], fs=fs, env=env, cwd=cwd)
    show(out)

    banner("E. ls /nope | wc -l  (a failed verb: classified error -> stderr line + exit code; wc still runs)")
    out = await run_pipeline([(Ls(), ("/nope",)), (Wc(), ("-l",))], fs=fs, env=env, cwd=cwd)
    show(out, projection=("content",))

    banner("F. cat /src/db.py | id.wasm --exit 3 --stderr 'boom'  (a program's own exit code and stderr)")
    out = await run_pipeline([(Cat(), ("/src/db.py",)), (IdWasm(), ("--exit", "3", "--stderr", "boom"))], fs=fs, env=env, cwd=cwd)
    show(out, projection=("content",))

    banner("G. 10,000 files: ls /big | wc -l  (chunked rows, bounded queue, wc counts chunks not time)")
    big = [Entry(path=f"/big/f{i:05d}.txt", content=f"{i}\n") for i in range(10_000)]
    wrote = await vfs.write(big, parents=True, authority=alice)
    assert wrote.success, wrote.to_str()
    wc = Wc()
    out = await run_pipeline([(Ls(), ("/big",)), (wc, ("-l",))], fs=fs, env=env, cwd=cwd)
    show(out, projection=("content",))
    print(f"wc saw {wc.chunks_seen} byte chunks (one per {ROWS_PER_CHUNK}-row slice); queue depth never exceeded {QUEUE_DEPTH}")

    banner("H. what a byte program would see for `ls /src` (the rendered bytes, verbatim)")
    listing = await fs.ls("/src")
    print(repr(rows_to_bytes(Rows(listing)).data.decode()))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
