"""The shell on its vfs host: the corpus runs through ``cli`` as it runs on the reference host, every
request the machine asks reaches a public verb with the caller's authority, and nothing runs as the
system actor."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from vfs import AsyncVirtualFileSystem, VirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.deadline import Deadline
from vfs.native import extension
from vfs.results import ErrorKind, Result
from vfs.results.kinds import Severity
from vfs.shell import host as host_module
from vfs.shell import run_line

if TYPE_CHECKING:
    from collections.abc import Callable

SYSTEM = Authority.system()
ADA = Authority.of(Principal("ada"))
GRACE = Authority.of(Principal("grace"))
SHELL = Path(__file__).parent
ENVIRONMENT = (
    ("HOME", "/home/agent"),
    ("PATH", "/usr/local/bin:/usr/bin:/bin"),
    ("LC_ALL", "C.UTF-8"),
    ("TZ", "UTC"),
    ("USER", "agent"),
    ("LOGNAME", "agent"),
    ("TERM", "dumb"),
)


def ok(result: Result) -> Result:
    assert result.success is True, result.error_message
    return result


# ---------------------------------------------------------------------------
# The corpus on the vfs host
# ---------------------------------------------------------------------------


def _cases() -> list[tuple[str, str, dict[str, Any], bool, bool]]:
    lines = (SHELL / "deltas.txt").read_text().splitlines()
    deltas = {line.split()[0] for line in lines if line and not line.startswith("#")}
    cases = []
    for script in sorted((SHELL / "cases").rglob("*.sh")):
        name = script.relative_to(SHELL / "cases").with_suffix("").as_posix()
        if name in deltas:
            continue
        source = script.read_text().rstrip("\n")
        header = [line.strip() for line in source.splitlines() if line.startswith("#")]
        record = json.loads(script.with_suffix(".json").read_text())
        cases.append((name, source, record, "# world: seed" in header, "# stderr: exact" in header))
    return cases


def _known_failures() -> set[str]:
    text = (SHELL / "known_failures.txt").read_text()
    return {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}


def _stream(record: dict[str, Any], name: str) -> bytes:
    if name in record:
        return record[name].encode()
    return base64.b64decode(record.get(f"{name}_base64", ""))


async def _seeded(seed: bool) -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem()
    ok(await fs.mkdir("/work", authority=SYSTEM))
    ok(await fs.mkdir("/home/agent", parents=True, authority=SYSTEM))
    ok(await fs.mkdir("/tmp", authority=SYSTEM))
    if seed:
        world = SHELL / "world"
        for path in sorted(world.rglob("*")):
            target = "/work/" + path.relative_to(world).as_posix()
            if path.is_dir():
                ok(await fs.mkdir(target, parents=True, authority=SYSTEM))
            else:
                ok(await fs.write(path=target, data=path.read_bytes(), parents=True, authority=SYSTEM))
    ok(await fs.grant("/", "agent", "read_write", authority=SYSTEM))
    return fs


AGENT = Authority.of(Principal("agent"))

SAMPLE: int = 10
"""One language-tier case in this many runs on the vfs host; all of them run on the reference host."""


def _sampled() -> list[tuple[str, str, dict[str, Any], bool, bool]]:
    known = _known_failures()
    chosen = [case for case in _cases() if case[0] not in known and "# tier: program" not in case[1]]
    return chosen[::SAMPLE]


@pytest.mark.slow
@pytest.mark.parametrize(
    ("name", "source", "record", "seed", "stderr_exact"), _sampled(), ids=[case[0] for case in _sampled()]
)
async def test_a_language_case_runs_on_the_vfs_host_as_on_the_reference_host(
    name: str, source: str, record: dict[str, Any], seed: bool, stderr_exact: bool
) -> None:
    fs = await _seeded(seed)
    result = await run_line(fs, source, AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    want_err = _stream(record, "stderr")
    assert result.stdout.encode() == _stream(record, "stdout"), name
    assert result.exit_status == record["status"], result.stderr
    if stderr_exact:
        assert result.stderr.encode() == want_err
    else:
        assert bool(result.stderr) == bool(want_err), result.stderr


# ---------------------------------------------------------------------------
# Every request is a public verb with the caller's authority
# ---------------------------------------------------------------------------


async def test_every_request_reaches_a_public_verb_with_the_admitted_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = await _seeded(seed=True)
    calls: list[tuple[str, Authority | None]] = []
    for verb in ("read", "stat", "ls", "write", "mkdir", "delete", "copy", "move"):
        original: Callable[..., Any] = getattr(fs, verb)

        def spy(*args: Any, _verb: str = verb, _original: Callable[..., Any] = original, **kwargs: Any) -> Any:
            calls.append((_verb, kwargs.get("authority")))
            return _original(*args, **kwargs)

        monkeypatch.setattr(fs, verb, spy)
    answered = 0
    real_answer = host_module._Host.answer

    async def counting(self: Any, op: str, args: dict[str, Any]) -> tuple[str, object]:
        nonlocal answered
        answered += 1
        return await real_answer(self, op, args)

    monkeypatch.setattr(host_module._Host, "answer", counting)
    line = (
        "cat docs/a.md | wc -l; ls src; mkdir -p out/x; echo hi > out/x/f.txt; cp out/x/f.txt out/g.txt; "
        "mv out/g.txt out/h.txt; rm -r out; [ -d docs ] && echo dir; grep -c alpha docs/*.md"
    )
    result = await run_line(fs, line, AGENT, cwd="/work", env=ENVIRONMENT)
    assert result.exit_status == 0, result.stderr
    assert answered > 10
    assert len(calls) == answered, "one public verb for each request"
    assert {who for _, who in calls} == {AGENT}
    assert {verb for verb, _ in calls} >= {"read", "stat", "ls", "write", "mkdir", "delete", "copy", "move"}


async def test_each_redirection_is_one_write_verb(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    writes: list[dict[str, Any]] = []
    real_write = fs.write

    async def spy(**kwargs: Any) -> Result:
        writes.append(kwargs)
        return await real_write(**kwargs)

    monkeypatch.setattr(fs, "write", spy)
    result = await fs.cli("echo x > /f; echo y >> /f; { echo a; echo b; } >> /g; cat /f /g", authority=ADA)
    assert result.stdout == "x\ny\na\nb\n"
    assert [(w["path"], w["content"], w["append"]) for w in writes] == [
        ("/f", "x\n", False),
        ("/f", "y\n", True),
        ("/g", "a\nb\n", True),
    ]


async def test_two_authorities_see_different_listings() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    ok(await fs.write(path="/ada/notes.md", content="mine", parents=True, authority=SYSTEM))
    ok(await fs.write(path="/grace/plan.md", content="hers", parents=True, authority=SYSTEM))
    ok(await fs.grant("/ada", "ada", "read_write", authority=SYSTEM))
    ok(await fs.grant("/grace", "grace", "read_write", authority=SYSTEM))
    seen_by_ada = await fs.cli("ls /; cat /grace/plan.md", authority=ADA)
    seen_by_grace = await fs.cli("ls /; cat /grace/plan.md", authority=GRACE)
    assert seen_by_ada.stdout != seen_by_grace.stdout
    assert "hers" in seen_by_grace.stdout
    assert "hers" not in seen_by_ada.stdout
    assert seen_by_ada.exit_status == 1
    assert [e.severity for e in seen_by_ada.errors] == [Severity.warning]


async def test_the_system_actor_is_refused_named_or_by_default() -> None:
    named = await AsyncVirtualFileSystem().cli("echo hi", authority=SYSTEM)
    assert named.success is False
    assert named.errors[0].kind == ErrorKind.invalid
    by_default = await AsyncVirtualFileSystem(default_authority=SYSTEM).cli("echo hi")
    assert by_default.success is False


# ---------------------------------------------------------------------------
# Program names vfs resolves
# ---------------------------------------------------------------------------


async def test_a_name_vfs_resolves_runs_refuses_or_is_not_found() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/docs/a.md", content="alpha beta", parents=True, authority=SYSTEM))
    ok(await fs.write(path="/docs/b.md", content="gamma delta", parents=True, authority=SYSTEM))
    ok(await fs.grant("/", "ada", "read_write", authority=SYSTEM))
    line = "search alpha /docs; echo $?; cd /docs; search -n 1 gamma .; curl http://x; echo $?; git log; echo $?"
    line += "; nosuch; echo $?"
    result = await fs.cli(line, authority=ADA)
    assert result.stdout == "/docs/a.md\n0\n/docs/b.md\n126\n127\n127\n"
    assert "curl: network access is not available inside vfs" in result.stderr
    assert "git: command not found; vfs keeps versions itself" in result.stderr
    assert "nosuch: command not found" in result.stderr
    assert result.success is True


async def test_search_is_the_search_verb_called_as_the_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    calls: list[tuple[str, Authority | None]] = []
    real_search = fs.search

    async def spy(query: str, **kwargs: Any) -> Result:
        calls.append((query, kwargs.get("authority")))
        return await real_search(query, **kwargs)

    monkeypatch.setattr(fs, "search", spy)
    result = await fs.cli("search nothing-here; echo $?; search", authority=ADA)
    assert calls == [("nothing-here", ADA)]
    assert result.stdout == "1\n"
    assert "usage: search" in result.stderr


async def test_a_refused_search_reads_as_its_message_and_is_kept_as_a_warning() -> None:
    fs = AsyncVirtualFileSystem()
    result = await fs.cli("search alpha /no/such/root; echo $?", authority=ADA)
    assert result.stdout.endswith("1\n")
    assert result.stderr.startswith("search: ")
    assert [e.severity for e in result.errors] == [Severity.warning]


# ---------------------------------------------------------------------------
# Lines that cannot run, and lines a budget ends
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        ("if then", ErrorKind.invalid),
        ("eval echo hi", ErrorKind.unsupported),
        ("echo " + "x " * 200_000, ErrorKind.budget_exhausted),
    ],
)
async def test_a_line_that_cannot_run_fails_and_changes_nothing(line: str, kind: ErrorKind) -> None:
    fs = AsyncVirtualFileSystem()
    result = await fs.cli(f"echo made > /made.txt; {line}", authority=ADA)
    assert result.success is False
    assert result.errors[0].kind == kind
    assert result.exit_status == 2
    assert (await fs.stat("/made.txt", authority=SYSTEM)).success is False


async def test_a_budget_that_ends_a_line_is_its_failure() -> None:
    fs = AsyncVirtualFileSystem()
    result = await run_line(fs, "while :; do :; done", ADA, limits={"loop_iterations": 50})
    assert result.success is False
    assert result.errors[-1].kind == ErrorKind.budget_exhausted
    assert result.exit_status == 137


# ---------------------------------------------------------------------------
# The runtime is the wall: fuel, the deadline, output, nesting and cancel
# ---------------------------------------------------------------------------

UNBOUNDED_LOOP = {"loop_iterations": 10**12}


@pytest.mark.parametrize(
    ("line", "limits", "fuel", "seconds", "kind", "status", "named"),
    [
        ("while :; do :; done", UNBOUNDED_LOOP, 10**8, None, ErrorKind.budget_exhausted, 137, "fuel"),
        ("while :; do :; done", UNBOUNDED_LOOP, 10**15, 0.05, ErrorKind.timeout, 124, "deadline"),
        (
            "while :; do echo 123456789; done",
            {**UNBOUNDED_LOOP, "output_bytes": 1000},
            None,
            30.0,
            ErrorKind.budget_exhausted,
            137,
            "output",
        ),
        ("f(){ if :; then { ( f ); }; fi; }; f", None, None, 30.0, ErrorKind.budget_exhausted, 137, "nesting"),
        ("f(){ echo $( f ); }; f", None, None, 30.0, ErrorKind.budget_exhausted, 137, "function_depth"),
    ],
    ids=["fuel", "deadline", "output", "nesting", "function-depth"],
)
async def test_each_wall_ends_a_line_and_the_process_goes_on(
    line: str,
    limits: dict[str, int] | None,
    fuel: int | None,
    seconds: float | None,
    kind: ErrorKind,
    status: int,
    named: str,
) -> None:
    fs = AsyncVirtualFileSystem()
    deadline = Deadline.after(seconds) if seconds is not None else None
    result = await run_line(fs, line, ADA, limits=limits, fuel=fuel, deadline=deadline)
    assert result.success is False
    assert result.errors[-1].kind == kind
    assert named in result.errors[-1].message
    assert result.exit_status == status
    if named == "output":
        assert len(result.stdout) == 1000
    assert (await fs.cli("echo after", authority=ADA)).stdout == "after\n"


async def test_a_chain_past_the_depth_budget_is_an_error_not_a_crash() -> None:
    fs = AsyncVirtualFileSystem()
    result = await fs.cli("e=$(printf '1+%.0s' {1..70000})1; echo $((e))", authority=ADA)
    assert result.exit_status == 1, "an expansion error ends the line, as it ends bash"
    assert "recursion level exceeded" in result.stderr
    assert (await fs.cli("echo after", authority=ADA)).stdout == "after\n"


async def test_the_event_loop_runs_while_a_line_computes() -> None:
    beats = 0

    async def heart() -> None:
        nonlocal beats
        while True:
            await asyncio.sleep(0)
            beats += 1

    task = asyncio.create_task(heart())
    result = await run_line(AsyncVirtualFileSystem(), "while :; do :; done", ADA, limits=UNBOUNDED_LOOP, fuel=10**8)
    task.cancel()
    assert result.exit_status == 137
    assert beats > 5, "each slice runs on the pool, so the loop runs between them"


async def test_a_cancelled_call_cancels_its_line(monkeypatch: pytest.MonkeyPatch) -> None:
    hops = 0
    real_hop = host_module.call_offloaded

    async def counted(executor: Any, work: Callable[[], Any]) -> Any:
        nonlocal hops
        hops += 1
        return await real_hop(executor, work)

    monkeypatch.setattr(host_module, "call_offloaded", counted)
    fs = AsyncVirtualFileSystem()
    line = run_line(fs, "while :; do :; done", ADA, limits=UNBOUNDED_LOOP, fuel=10**15)
    task = asyncio.create_task(line)
    for _ in range(100_000):
        if hops >= 3:
            break
        await asyncio.sleep(0.001)
    assert hops >= 3, "the line is running its slices"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await fs.cli("echo after", authority=ADA)).stdout == "after\n"


def _machine(line: str, **options: Any) -> Any:
    return extension().ShellMachine(
        line, env=[], cwd="/", name="bash", args=[], stdin=b"", programs=[], pid=1000, **options
    )


def test_cancel_ends_a_running_slice_from_another_thread() -> None:
    machine = _machine("while :; do :; done", limits={**UNBOUNDED_LOOP, "fuel_slice": 10**15}, fuel=10**15)
    ended: list[tuple[str, int, str | None]] = []
    worker = threading.Thread(target=lambda: ended.append(machine.step([])[2]))
    worker.start()
    machine.cancel()
    worker.join()
    assert ended == [("ended", 130, "Cancelled")]
    assert machine.step([])[2][0] == "ended"


def test_one_line_spends_the_same_fuel_twice() -> None:
    def spend() -> int:
        machine = _machine("x=0; for i in {1..2000}; do x=$((x + i)); done; echo $x")
        while machine.step([])[2][0] == "running":
            pass
        return machine.fuel_used

    first = spend()
    assert first > 0
    assert spend() == first


def test_a_step_already_running_refuses_a_second() -> None:
    machine = _machine("while :; do :; done", limits={**UNBOUNDED_LOOP, "fuel_slice": 10**15}, fuel=10**15)
    together = threading.Barrier(2)
    refused: list[str] = []
    ended: list[str] = []

    def step() -> None:
        together.wait()
        try:
            ended.append(machine.step([])[2][0])
        except RuntimeError as error:
            refused.append(str(error))

    workers = [threading.Thread(target=step) for _ in range(2)]
    for worker in workers:
        worker.start()
    for _ in range(100_000):
        if refused:
            break
        threading.Event().wait(0.001)
    machine.cancel()
    for worker in workers:
        worker.join()
    assert refused == ["a step of this line is already running"]
    assert ended == ["ended"]


@pytest.mark.parametrize(
    ("reason", "kind"),
    [
        ("Deadline", ErrorKind.timeout),
        ("Cancelled", ErrorKind.cancelled),
        ('Internal("x")', ErrorKind.internal),
        ('Budget("memory", 1)', ErrorKind.budget_exhausted),
    ],
)
def test_an_ended_line_names_why(reason: str, kind: ErrorKind) -> None:
    assert host_module._ended(reason).kind == kind


# ---------------------------------------------------------------------------
# A refused verb reads as the error a Unix tool sees
# ---------------------------------------------------------------------------


async def test_refusals_read_as_unix_errors() -> None:
    fs = await _seeded(seed=True)
    line = (
        "cat docs; cat docs/a.md/x; touch docs/a.md && echo touched; set -C; echo x > docs/a.md; "
        "mkdir docs; rm nope; cp nope x; mv nope x; ls nope; printf '\\377\\376' > bin.dat; wc -c < bin.dat"
    )
    result = await run_line(fs, line, AGENT, cwd="/work", env=ENVIRONMENT)
    assert "cat: docs: Is a directory" in result.stderr
    assert "cat: docs/a.md/x: Not a directory" in result.stderr
    assert "touched" in result.stdout
    assert "cannot overwrite existing file" in result.stderr
    assert "mkdir: cannot create directory \u2018docs\u2019: File exists" in result.stderr
    assert result.stdout.endswith("2\n")
    body = frozenset({"content", "data"})
    data = (await fs.read("/work/bin.dat", columns=body, authority=SYSTEM)).observations[0].data
    assert data == b"\xff\xfe"


async def test_a_closed_storage_reads_as_permission_denied() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    ok(await fs.write(path="/f.txt", content="x", authority=SYSTEM))
    result = await fs.cli("echo y > /g.txt", authority=ADA)
    assert result.exit_status == 1
    assert "Permission denied" in result.stderr or "No such file" in result.stderr


def test_values_that_are_not_functions_of_the_line() -> None:
    assert host_module._value("time")[0] == "text"
    assert 0 <= int(str(host_module._value("random")[1])) < 32768
    assert host_module._value("other") == ("error", "unsupported")


# ---------------------------------------------------------------------------
# The session and the sync facade
# ---------------------------------------------------------------------------


async def test_a_session_runs_a_line_as_its_authority_until_closed() -> None:
    fs = AsyncVirtualFileSystem()
    session = fs.open_session(ADA)
    assert (await session.cli("echo $((6 * 7))")).stdout == "42\n"
    await session.close()
    assert (await session.cli("echo hi")).success is False


def test_the_sync_facade_runs_a_line() -> None:
    with VirtualFileSystem() as fs:
        assert fs.cli("printf '%s\\n' a b | wc -l", authority=ADA).stdout == "2\n"
        with fs.open_session(ADA) as session:
            assert session.cli("echo hi", stdin=b"").stdout == "hi\n"
