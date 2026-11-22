"""The shell on its vfs host: the corpus runs through ``cli`` as it runs on the reference host, every
request the machine asks reaches a public verb with the caller's authority, and nothing runs as the
system actor."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import signal
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
                ok(await fs.write(path=target, **_as_written(path.read_bytes()), parents=True, authority=SYSTEM))
    ok(await fs.grant("/", "agent", "read_write", authority=SYSTEM))
    return fs


def _as_written(body: bytes) -> dict[str, Any]:
    """A body as the shell writes it: text when it is UTF-8, bytes when not."""
    try:
        return {"content": body.decode()}
    except UnicodeDecodeError:
        return {"data": body}


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
    assert result.exit_code == record["status"], result.stderr
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
        answered += op not in ("start", "feed")
        return await real_answer(self, op, args)

    monkeypatch.setattr(host_module._Host, "answer", counting)
    line = (
        "cat docs/a.md | wc -l; ls src; mkdir -p out/x; echo hi > out/x/f.txt; cp out/x/f.txt out/g.txt; "
        "mv out/g.txt out/h.txt; rm -r out; [ -d docs ] && echo dir; grep -c alpha docs/*.md"
    )
    result = await run_line(fs, line, AGENT, cwd="/work", env=ENVIRONMENT)
    assert result.exit_code == 0, result.stderr
    assert answered > 10
    assert len(calls) == answered, "one public verb for each request that is no program's start or feed"
    assert {who for _, who in calls} == {AGENT}
    assert {verb for verb, _ in calls} >= {"read", "stat", "ls", "write", "mkdir", "delete", "copy", "move"}


async def test_a_command_that_only_prints_writes_its_file_once(monkeypatch: pytest.MonkeyPatch) -> None:
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
        ("/g", "", True),
        ("/g", "a\nb\n", True),
    ], "a group can act before it ends, so its file is opened with a write first"


async def _read_only_ro() -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/w/keep.txt", content="kept", parents=True, authority=SYSTEM))
    ok(await fs.mkdir("/ro", authority=SYSTEM))
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    ok(await fs.grant("/w", "ada", "read_write", authority=SYSTEM))
    ok(await fs.grant("/ro", "ada", "read", authority=SYSTEM))
    return fs


@pytest.mark.parametrize(
    ("line", "stdout"),
    [
        ('printf -v x hi > /ro/out.txt; echo "[$x] $?"', "[] 1\n"),
        ("{ cat > /ro/out.txt; cat; } <<< hi", "hi\n"),
        ("echo x > /ro/out.txt; echo $?", "1\n"),
        ("cat > /ro/out.txt <<< hi; echo $?", "1\n"),
        ("{ cat < /dev/stdin > /ro/out.txt; cat; } <<< hi", "hi\n"),
    ],
    ids=[
        "printf-v-sets-nothing",
        "cat-leaves-its-input",
        "echo-refused-at-the-end",
        "cat-of-its-own-input",
        "cat-of-dev-stdin-leaves-its-input",
    ],
)
async def test_a_refused_redirection_leaves_its_command_undone(line: str, stdout: str) -> None:
    fs = await _read_only_ro()
    result = await fs.cli(line, authority=ADA)
    assert result.stdout == stdout
    assert "/ro/out.txt" in result.stderr
    assert (await fs.stat("/ro/out.txt", authority=SYSTEM)).success is False


async def test_a_command_never_runs_before_its_refused_redirection() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/w/keep.txt", content="kept", parents=True, authority=SYSTEM))
    ok(await fs.mkdir("/ro", authority=SYSTEM))
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    ok(await fs.grant("/w", "ada", "read_write", authority=SYSTEM))
    ok(await fs.grant("/ro", "ada", "read", authority=SYSTEM))
    result = await fs.cli("{ rm /w/keep.txt; echo done; } > /ro/out.txt; echo status=$?", authority=ADA)
    assert result.stdout == "status=1\n"
    assert "/ro/out.txt" in result.stderr
    assert (await fs.stat("/w/keep.txt", authority=SYSTEM)).success is True


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
    assert seen_by_ada.exit_code == 1
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
    assert "Usage: search" in result.stderr
    assert result.exit_code == 2


async def test_a_limit_that_is_no_ascii_number_is_a_misuse() -> None:
    result = await AsyncVirtualFileSystem().cli("search -n \u00b2 alpha; echo $?", authority=ADA)
    assert result.stdout == "2\n"
    assert result.stderr.startswith("search: invalid limit: \u2018\u00b2\u2019\n")


def _counted_reads(monkeypatch: pytest.MonkeyPatch, fs: AsyncVirtualFileSystem, after: Any = None) -> list[str]:
    """Count the router reads ``fs`` serves, calling ``after(n)`` once the ``n``-th returns."""
    reads: list[str] = []
    real_read = fs.read

    async def counted(*args: Any, **kwargs: Any) -> Result:
        result = await real_read(*args, **kwargs)
        reads.append(args[0] if args else kwargs.get("path", ""))
        if after is not None:
            await after(len(reads))
        return result

    monkeypatch.setattr(fs, "read", counted)
    return reads


async def test_each_open_of_a_file_is_a_fresh_read_that_sees_an_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.mkdir("/w", authority=SYSTEM))
    ok(await fs.write(path="/w/f", content="v1\n", authority=SYSTEM))
    ok(await fs.grant("/", "ada", "read_write", authority=SYSTEM))

    async def edit(n: int) -> None:
        if n == 1:
            ok(await fs.write(path="/w/f", content="v2\n", authority=SYSTEM))

    reads = _counted_reads(monkeypatch, fs, edit)
    result = await fs.cli("cat /w/f; cat /w/f", authority=ADA)
    assert result.stdout == "v1\nv2\n"
    assert reads == ["/w/f", "/w/f"]


async def test_an_open_after_a_revoke_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.mkdir("/w", authority=SYSTEM))
    ok(await fs.write(path="/w/f", content="secret\n", authority=SYSTEM))
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    ok(await fs.grant("/w", "ada", "read", authority=SYSTEM))

    async def revoke(n: int) -> None:
        if n == 1:
            ok(await fs.revoke("/w", "ada", authority=SYSTEM))

    _counted_reads(monkeypatch, fs, revoke)
    result = await fs.cli("cat /w/f; echo st=$?; cat /w/f; echo st=$?", authority=ADA)
    assert result.stdout == "secret\nst=0\nst=1\n"


async def test_one_open_reads_one_version_across_its_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.mkdir("/w", authority=SYSTEM))
    lines = 30_000
    ok(await fs.write(path="/w/a", content="".join(f"A{n:07}\n" for n in range(lines)), authority=SYSTEM))
    ok(await fs.grant("/", "ada", "read_write", authority=SYSTEM))

    async def rewrite(n: int) -> None:
        if n == 1:
            ok(await fs.write(path="/w/a", content="".join(f"B{n:07}\n" for n in range(lines)), authority=SYSTEM))

    reads = _counted_reads(monkeypatch, fs, rewrite)
    result = await fs.cli("{ read -r x; echo $x; touch /w/z; grep -c ^A; } < /w/a", authority=ADA)
    assert result.stdout == f"A0000000\n{lines - 1}\n"
    assert reads == ["/w/a"], "a body of five chunks is one read, and a write elsewhere in the line forgets nothing"


async def test_two_opens_of_one_file_are_two_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/big.txt", content="x" * 100, authority=SYSTEM))
    ok(await fs.write(path="/a.txt", content="a" * 300_000, authority=SYSTEM))
    ok(await fs.write(path="/b.txt", content="b" * 300_000, authority=SYSTEM))
    reads = _counted_reads(monkeypatch, fs)
    result = await fs.cli("cat /big.txt /big.txt | wc -c; cat /a.txt | cat /b.txt - | wc -c", authority=ADA)
    assert result.stdout == "200\n600000\n"
    assert reads[:2] == ["/big.txt", "/big.txt"]
    assert sorted(reads[2:]) == ["/a.txt", "/b.txt"]


async def test_a_body_given_way_is_read_again_only_at_the_version_its_open_saw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host_module, "READING_BYTES", 150_000)
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/a.txt", content="a" * 100_000, authority=SYSTEM))
    ok(await fs.write(path="/b.txt", content="b" * 100_000, authority=SYSTEM))
    line = "{ read -r -n 1 x <&3; read -r -n 1 y <&4; cat <&3 | wc -c; } 3</a.txt 4</b.txt"

    reads = _counted_reads(monkeypatch, fs)
    result = await fs.cli(line, authority=ADA)
    assert result.stdout == "99999\n"
    assert reads == ["/a.txt", "/b.txt", "/a.txt"], "b's body made a's give way, and a is read again"
    assert result.errors == []

    async def rewrite(n: int) -> None:
        if n == 2:
            ok(await fs.write(path="/a.txt", content="c" * 100_000, authority=SYSTEM))

    _counted_reads(monkeypatch, fs, rewrite)
    result = await fs.cli(line, authority=ADA)
    assert "c" not in result.stdout
    assert [str(error.kind) for error in result.errors] == ["vfs.conflict"]


async def test_two_opens_of_one_file_each_keep_the_version_they_saw(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.mkdir("/w", authority=SYSTEM))
    lines = 30_000
    ok(await fs.write(path="/w/a", content="".join(f"A{n:07}\n" for n in range(lines)), authority=SYSTEM))
    ok(await fs.grant("/", "ada", "read_write", authority=SYSTEM))

    async def rewrite(n: int) -> None:
        if n == 1:
            ok(await fs.write(path="/w/a", content="".join(f"B{n:07}\n" for n in range(lines)), authority=SYSTEM))

    reads = _counted_reads(monkeypatch, fs, rewrite)
    line = "{ read -r x <&3; read -r y <&4; echo $y; grep -c ^A <&3; } 3</w/a 4</w/a"
    result = await fs.cli(line, authority=ADA)
    assert result.stdout == f"B0000000\n{lines - 1}\n"
    assert reads == ["/w/a", "/w/a"]


async def test_two_opens_of_one_version_share_one_body_past_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host_module, "READING_BYTES", 150_000)
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/a.txt", content="a\n" * 100_000, authority=SYSTEM))
    reads = _counted_reads(monkeypatch, fs)
    line = "while read -r x <&3 && read -r y <&4; do :; done 3</a.txt 4</a.txt; echo done"
    result = await fs.cli(line, authority=ADA)
    assert result.stdout == "done\n"
    assert reads == ["/a.txt", "/a.txt"], "readers in step of one file read it once each, never again"


async def test_a_body_larger_than_the_budget_is_read_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host_module, "READING_BYTES", 1000)
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/big.bin", content="y" * 300_000, authority=SYSTEM))
    reads = _counted_reads(monkeypatch, fs)
    result = await fs.cli("wc -c < /big.bin", authority=ADA)
    assert result.stdout == "300000\n"
    assert reads == ["/big.bin"], "the body being read never gives way to itself"


async def test_a_body_read_to_its_end_is_let_go(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/big.bin", content="y" * 300_000, authority=SYSTEM))
    held: list[int] = []
    real_read = host_module._Host._read

    async def counted(self: Any, *args: Any) -> tuple[str, object]:
        reply = await real_read(self, *args)
        held.append(self._held)
        return reply

    monkeypatch.setattr(host_module._Host, "_read", counted)
    result = await fs.cli("cat /big.bin | wc -c", authority=ADA)
    assert result.stdout == "300000\n"
    assert held[0] == 300_000
    assert held[-1] == 0


async def test_rm_ri_keeps_a_directory_a_child_arrived_in(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/w/d/x.txt", content="x\n", parents=True, authority=SYSTEM))
    ok(await fs.grant("/", "ada", "read_write", authority=SYSTEM))
    real_ls = fs.ls

    async def arriving(*args: Any, **kwargs: Any) -> Result:
        result = await real_ls(*args, **kwargs)
        if (args[0] if args else kwargs.get("path")) == "/w/d":
            ok(await fs.write(path="/w/d/new.txt", content="new\n", authority=SYSTEM))
        return result

    monkeypatch.setattr(fs, "ls", arriving)
    result = await fs.cli("rm -ri /w/d; echo st=$?", stdin=b"y\ny\ny\n", authority=ADA)
    assert result.stdout == "st=1\n"
    assert result.stderr.endswith("rm: cannot remove '/w/d': Directory not empty\n")
    assert (await fs.read("/w/d/new.txt", authority=SYSTEM)).success
    assert not (await fs.read("/w/d/x.txt", authority=SYSTEM)).success


async def test_bodies_whose_readers_stopped_early_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host_module, "READING_BYTES", 250_000)
    fs = AsyncVirtualFileSystem()
    for n in range(20):
        ok(await fs.write(path=f"/t/{n:02}.txt", content="first\n" + "z" * 100_000, parents=True, authority=SYSTEM))
    held: list[int] = []
    real_read = host_module._Host._read

    async def counted(self: Any, *args: Any) -> tuple[str, object]:
        reply = await real_read(self, *args)
        held.append(self._held)
        return reply

    monkeypatch.setattr(host_module._Host, "_read", counted)
    result = await fs.cli("for f in /t/*; do read -r x < $f; echo $x; done | uniq -c", authority=ADA)
    assert result.stdout == "     20 first\n"
    assert len(held) == 20
    assert max(held) <= 250_000 + 100_006, "a reader that stopped early leaves a body that gives way in time"


async def test_a_refused_search_reads_as_its_message_and_is_kept_as_a_warning() -> None:
    fs = AsyncVirtualFileSystem()
    result = await fs.cli("search alpha /no/such/root; echo $?", authority=ADA)
    assert result.stdout.endswith("2\n")
    assert result.stderr.startswith("search: /no")
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
    assert result.exit_code == 2
    assert (await fs.stat("/made.txt", authority=SYSTEM)).success is False


async def test_a_budget_that_ends_a_line_is_its_failure() -> None:
    fs = AsyncVirtualFileSystem()
    result = await run_line(fs, "while :; do :; done", ADA, limits={"loop_iterations": 50})
    assert result.success is False
    assert result.errors[-1].kind == ErrorKind.budget_exhausted
    assert result.exit_code == 137


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
    assert result.exit_code == status
    if named == "output":
        assert len(result.stdout) == 1000
    assert (await fs.cli("echo after", authority=ADA)).stdout == "after\n"


async def test_a_chain_past_the_depth_budget_is_an_error_not_a_crash() -> None:
    fs = AsyncVirtualFileSystem()
    result = await fs.cli("e=$(printf '1+%.0s' {1..70000})1; echo $((e))", authority=ADA)
    assert result.exit_code == 1, "an expansion error ends the line, as it ends bash"
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
    assert result.exit_code == 137
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


def test_a_deep_line_ends_on_its_budget_on_a_thread_with_a_small_stack() -> None:
    ended: list[tuple[str, int, str | None]] = []

    def run() -> None:
        machine = _machine("f(){ if :; then { ( f ); }; fi; }; f")
        while (status := machine.step([])[2])[0] == "running":
            pass
        ended.append(status)

    previous = threading.stack_size(1 << 20)
    try:
        worker = threading.Thread(target=run)
        worker.start()
        worker.join()
    finally:
        threading.stack_size(previous)
    assert ended == [("ended", 137, 'Budget("nesting", 1000)')]


@pytest.mark.parametrize("fuel", [0, 1000])
def test_a_start_that_spends_its_fuel_is_a_budget_and_a_far_deadline_is_none(fuel: int) -> None:
    # The fuel may run out while the instance is made or while the line parses; either is the budget.
    with pytest.raises(ValueError, match="fuel") as raised:
        _machine("echo hi", fuel=fuel)
    assert raised.value.args[0] == "budget"
    machine = _machine("echo hi", deadline=1e300)
    assert machine.step([])[2] == ("done", 0, None)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="the process forks")
@pytest.mark.filterwarnings("ignore:This process .* is multi-threaded")
def test_a_forked_child_ends_a_line_at_its_deadline() -> None:
    _machine("echo warm").step([])
    child = os.fork()
    if child == 0:  # pragma: no cover - runs in the forked child, which reports by its exit code
        # Whatever happens here, the child ends here: it must never go on as a second test run.
        code = 2
        try:
            signal.alarm(30)
            endless = _machine(
                "while :; do :; done", limits={**UNBOUNDED_LOOP, "fuel_slice": 10**15}, fuel=10**15, deadline=0.2
            )
            code = 0 if endless.step([])[2][1] == 124 else 1
        finally:
            os._exit(code)
    _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0, "the child has an epoch thread of its own"


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
    assert result.exit_code == 1
    assert "Permission denied" in result.stderr or "No such file" in result.stderr


async def test_a_refused_listing_reads_as_its_unix_error() -> None:
    fs = AsyncVirtualFileSystem()
    host = host_module._Host(fs, ADA)
    assert await host.answer("list", {"path": "/missing"}) == ("error", "not_found")
    assert [e.severity for e in host.evidence] == [Severity.warning]


async def test_an_unknown_request_is_unsupported() -> None:
    host = host_module._Host(AsyncVirtualFileSystem(), ADA)
    assert await host.answer("chmod", {"path": "/x"}) == ("error", "unsupported")


@pytest.mark.parametrize(
    "limits", [{"memory_byte": 10}, {"memory_bytes": -1}, {"memory_bytes": 2**70}, {"memory_bytes": "10"}]
)
async def test_an_unknown_or_negative_budget_fails_the_call(limits: dict[str, int]) -> None:
    result = await run_line(AsyncVirtualFileSystem(), "echo hi", ADA, limits=limits)
    assert result.errors[0].kind == ErrorKind.invalid
    assert result.exit_code == 2


def test_the_module_memory_limit_ends_the_line_and_not_the_process() -> None:
    machine = _machine(
        "x=a; while :; do x=$x$x; done", limits={"memory_bytes": 1 << 30, "module_memory_bytes": 32 << 20}
    )
    while (status := machine.step([])[2])[0] == "running":
        pass
    assert status == ("ended", 137, 'Budget("module_memory", 33554432)')


def test_values_that_are_not_functions_of_the_line() -> None:
    assert host_module._value("time")[0] == "text"
    assert 0 <= int(str(host_module._value("random")[1])) < 32768
    assert host_module._value("other") == ("error", "unsupported")


# ---------------------------------------------------------------------------
# The result of a line
# ---------------------------------------------------------------------------

FUEL = 400_000_000
"""Instructions enough to start a line and run a few thousand steps of it, and no more."""


async def test_a_verb_refused_inside_a_line_is_a_warning_and_the_line_runs() -> None:
    result = await AsyncVirtualFileSystem().cli("cat /nope | wc -l", authority=ADA)
    assert result.success is True
    assert result.stdout == "0\n"
    assert result.exit_code == 0
    assert result.statuses == [[1, 0]]
    assert [(e.kind, e.severity) for e in result.errors] == [(ErrorKind.not_found, Severity.warning)]


async def test_each_top_level_pipeline_that_ran_is_one_entry_of_statuses() -> None:
    fs = AsyncVirtualFileSystem()
    assert (await fs.cli("false; true | false; false && true", authority=ADA)).statuses == [[1], [0, 1], [1]]
    looped = await fs.cli("for i in {1..1000}; do false | true; done", authority=ADA)
    assert looped.statuses == [[1, 0]]


async def test_a_line_a_wall_stopped_keeps_the_statuses_before_it() -> None:
    line = "true | false; while :; do :; done"
    stopped = await run_line(AsyncVirtualFileSystem(), line, ADA, limits={"loop_iterations": 1 << 40}, fuel=FUEL)
    assert stopped.success is False
    assert stopped.errors[-1].data == {"limit": "fuel"} or "fuel" in (stopped.errors[-1].message or "")
    assert stopped.statuses == [[0, 1]]


async def test_a_program_vfs_refuses_is_a_warning_and_its_own_exit_is_none() -> None:
    result = await AsyncVirtualFileSystem().cli("curl http://x; echo y | grep -q x; false", authority=ADA)
    assert result.success is True
    assert result.statuses == [[126], [0, 1], [1]]
    assert [(e.kind, e.severity) for e in result.errors] == [(ErrorKind.unsupported, Severity.warning)]


async def test_a_refusal_repeated_in_a_loop_is_kept_once() -> None:
    result = await AsyncVirtualFileSystem().cli("for i in {1..2000}; do cat /nope; done 2>/dev/null", authority=ADA)
    assert [e.kind for e in result.errors] == [ErrorKind.not_found]


async def test_the_facts_a_line_keeps_are_bounded_and_the_rest_counted() -> None:
    line = "for i in {1..2000}; do cat /nope$i; done 2>/dev/null"
    result = await AsyncVirtualFileSystem().cli(line, authority=ADA)
    assert len(result.errors) == host_module.LINE_FACTS + 1
    rollup = result.errors[-1]
    assert (rollup.kind, rollup.severity) == (ErrorKind.truncated, Severity.warning)
    assert rollup.data == {"vfs.rollup": {"count": 2000 - host_module.LINE_FACTS, "sources": []}}
    assert result.success is True


async def test_every_line_result_names_its_call() -> None:
    fs = AsyncVirtualFileSystem()
    session = fs.open_session(ADA)
    await session.close()
    results = [
        await fs.cli("echo hi", authority=ADA),
        await fs.cli("if", authority=ADA),
        await fs.cli("echo hi", authority=SYSTEM),
        await run_line(fs, "echo hi", ADA, limits={"nope": 1}),
        await session.cli("echo hi"),
    ]
    assert [r.ops for r in results] == [("cli",)] * 5
    assert [r.success for r in results] == [True, False, False, False, False]
    assert all(r.exit_code == 2 for r in results[1:])


async def test_a_line_result_crosses_the_wire_whole() -> None:
    result = await AsyncVirtualFileSystem().cli("echo out; echo err >&2; cat /nope; false | true", authority=ADA)
    back = host_module.LineResult.from_payload(result.to_payload(), strict=True)
    assert isinstance(back, host_module.LineResult)
    assert back == result
    assert back.statuses == [[0], [0], [1], [1, 0]]


async def test_a_line_result_rolled_up_at_the_wire_keeps_what_the_line_printed() -> None:
    result = await AsyncVirtualFileSystem().cli("echo out; cat /a /b /c; false | true", authority=ADA)
    payload = result.to_payload(max_errors=1)
    assert (payload["stdout"], payload["exit_code"], payload["statuses"]) == ("out\n", 0, [[0], [1], [1, 0]])
    assert len(payload["errors"]) == 2


async def test_a_line_result_prints_its_output_then_its_facts() -> None:
    result = await AsyncVirtualFileSystem().cli("echo out; echo err >&2; cat /nope", authority=ADA)
    text = str(result)
    assert text.startswith("out\nerr\ncat: /nope: No such file or directory\n")
    assert "WARNING" in text.split("\n\n")[-1]
    assert str(await AsyncVirtualFileSystem().cli("echo hi", authority=ADA)) == "hi\n"


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


def test_a_closed_facade_answers_a_line_with_a_classified_refusal() -> None:
    fs = VirtualFileSystem()
    session = fs.open_session(ADA)
    session.close()
    closed_session = session.cli("echo hi")
    fs.close()
    closed_facade = fs.cli("echo hi", authority=ADA)
    assert [r.ops for r in (closed_session, closed_facade)] == [("cli",), ("cli",)]
    assert closed_session.errors[0].kind == ErrorKind.invalid
    assert closed_facade.errors[0].kind == ErrorKind.backend_unavailable
    assert closed_facade.success is False
    assert closed_facade.exit_code == 2


async def test_an_empty_or_dot_operand_removes_nothing_through_the_router() -> None:
    fs = await _seeded(seed=False)
    ok(await fs.write(path="/work/sub/a.txt", content="a\n", parents=True, authority=SYSTEM))
    line = 'X=; rm -rf "$X"; rm -rf .; rm -rf ..; rm -rf ../sub/.; echo st=$?'
    result = await fs.cli(line, cwd="/work/sub", authority=ADA)
    assert result.stdout == "st=1\n"
    assert (await fs.read("/work/sub/a.txt", authority=SYSTEM)).success


async def test_a_sandboxed_sed_writes_no_file_through_the_router() -> None:
    fs = await _seeded(seed=False)
    ok(await fs.write(path="/work/f.txt", content="a\n", authority=SYSTEM))
    result = await fs.cli("sed --sandbox 'w /work/out' /work/f.txt; echo st=$?", authority=ADA)
    assert result.stdout == "st=1\n"
    assert not (await fs.stat("/work/out", authority=SYSTEM)).observations
