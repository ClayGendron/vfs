"""The shell on its vfs host: the corpus runs through ``cli`` as it runs on the reference host, every
request the machine asks reaches a public verb with the caller's authority, and nothing runs as the
system actor."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from vfs import AsyncVirtualFileSystem, VirtualFileSystem
from vfs.authority import Authority, Principal
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


@pytest.mark.parametrize(
    ("reason", "kind"),
    [
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
