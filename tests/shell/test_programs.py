"""The programs vfs runs itself: ``grep -r`` and ``find`` print what the shell's library prints for the
same line at one indexed verb call, a form the verbs cannot serve exactly is the library's, and each
verb with no Unix name is a program that is one call of its verb as the caller."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from vfs import AsyncVirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.results import ErrorKind, Result, classified
from vfs.results.kinds import Severity
from vfs.shell import host as host_module
from vfs.shell import programs as programs_module
from vfs.shell import run_line
from vfs.shell.host import ENVIRONMENT

from .test_host import AGENT, _cases, _known_failures, _seeded, _stream, ok

if TYPE_CHECKING:
    from collections.abc import Callable

SYSTEM = Authority.system()
ADA = Authority.of(Principal("ada"))


async def _hand_back(caller: Any, words: list[str], cwd: str) -> None:
    return None


async def _world() -> AsyncVirtualFileSystem:
    fs = await _seeded(seed=True)
    for path in (
        "/work/tree/a/x.txt",
        "/work/tree/a.md",
        "/work/tree/a-b.txt",
        "/work/tree/B.txt",
        "/work/tree/_u",
        "/work/tree/\u0130.md",
    ):
        ok(await fs.write(path=path, content="x marks\nno\n", parents=True, authority=SYSTEM))
    ok(await fs.mkdir("/work/tree/z/empty", parents=True, authority=SYSTEM))
    return fs


def _spy(monkeypatch: pytest.MonkeyPatch, fs: AsyncVirtualFileSystem, verbs: tuple[str, ...]) -> list[str]:
    calls: list[str] = []
    for verb in verbs:
        original: Callable[..., Any] = getattr(fs, verb)

        def spy(*args: Any, _verb: str = verb, _original: Callable[..., Any] = original, **kwargs: Any) -> Any:
            calls.append(_verb)
            assert kwargs.get("authority") == AGENT
            return _original(*args, **kwargs)

        monkeypatch.setattr(fs, verb, spy)
    return calls


async def _library(monkeypatch: pytest.MonkeyPatch, line: str, name: str) -> tuple[str, str, int]:
    fs = await _world()
    with monkeypatch.context() as patched:
        patched.setitem(programs_module.PROGRAMS, name, _hand_back)
        result = await run_line(fs, line, AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    return result.stdout, result.stderr, result.exit_code


# ---------------------------------------------------------------------------
# grep -r from the grep verb
# ---------------------------------------------------------------------------


SERVED_GREP = (
    "grep -r TODO .",
    "grep -rn 'def ' src",
    "grep -rl alpha .",
    "grep -rc alpha docs",
    "grep -rc alpha docs/a.md docs",
    "grep -r return src/lib",
    "grep -rh alpha docs",
    "grep -rH alpha docs/a.md",
    "grep -rn -y BETA docs",
    "grep -rc -i TODO .",
    "grep -rF 'a, b' src",
    "grep -rE 'al(pha|so)' docs",
    "grep -r -e alpha -e beta docs",
    "grep -rq alpha docs; echo $?",
    "grep -rq zzz docs; echo $?",
    "grep -rs alpha nope docs; echo $?",
    "grep -r alpha nope docs; echo $?",
    "grep -r alpha nope docs 2>&1",
    "grep -r zzz docs; echo $?",
    "grep -rn alpha /work/docs/",
    "grep -r alpha docs docs/a.md",
    "grep -rl alpha docs src",
    "grep -R alpha docs",
    "grep --recursive --line-number --ignore-case BETA docs",
    "grep -rn '^$' .",
    "grep -r '' data",
    "cd docs && grep -r alpha",
    "grep -r alpha ./docs",
    "grep -rn x tree",
    "grep -rc x tree",
    "grep -r 'a\\.' src",
    "grep -rG 'in\\(it\\|t\\)' src",
    "grep -r '[0-9][0-9]*' data/numbers.txt",
    "grep -rl alpha docs | head -1",
    "grep -r --color=never alpha docs",
    "grep -r --regexp=alpha docs",
)


@pytest.mark.parametrize("line", SERVED_GREP)
async def test_a_served_grep_prints_what_the_library_prints_at_one_grep_call(
    monkeypatch: pytest.MonkeyPatch, line: str
) -> None:
    want = await _library(monkeypatch, line, "grep")
    fs = await _world()
    calls = _spy(monkeypatch, fs, ("grep", "glob", "read", "ls"))
    result = await run_line(fs, line, AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert (result.stdout, result.stderr, result.exit_code) == want
    assert "read" not in calls
    assert "ls" not in calls
    assert calls.count("grep") == 1
    assert calls.count("glob") == (1 if " -rc " in line else 0)


LIBRARY_GREP = (
    "grep alpha docs/a.md",
    "grep -rv alpha docs",
    "grep -rx alpha docs",
    "grep -ro alpha docs",
    "grep -rm1 alpha docs",
    "grep -rC1 alpha docs",
    "grep -rL alpha docs",
    "grep -r '\\<alpha' docs",
    "grep -r '[[:digit:]]' data",
    "grep -rw add src",
    "grep -rw 'a.b' src",
    "grep -ri 'été' docs",
    "grep -ri INTRO docs",
    "grep -ri KEY src",
    "grep -ri '[a-c]lpha' docs",
    "grep -r alpha - < docs/a.md",
    "grep -rf docs/a.md docs",
    "echo alpha | grep alpha",
    "grep -r --include='*.md' alpha docs/a.md",
    "grep -r --regexp alpha docs",
    "grep -r --null alpha docs",
    "grep -r alpha docs -e",
    "grep -r",
    "grep -r --include='*.{md}' alpha docs",
    "grep -rc --include='*.md' alpha docs",
)


@pytest.mark.parametrize("line", LIBRARY_GREP)
async def test_a_grep_form_the_verb_cannot_serve_is_the_librarys(monkeypatch: pytest.MonkeyPatch, line: str) -> None:
    want = await _library(monkeypatch, line, "grep")
    fs = await _world()
    calls = _spy(monkeypatch, fs, ("grep", "glob"))
    result = await run_line(fs, line, AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert (result.stdout, result.stderr, result.exit_code) == want
    assert calls == []


@pytest.mark.parametrize(
    ("line", "stdout"),
    [
        (
            "grep -r --include='*.md' alpha . | sort",
            "./docs/a.md:# alpha\n./docs/a.md:first line of alpha\n./docs/b.md:beta mentions alpha once\n",
        ),
        (
            "grep -rn --include='*.md' --include='*.txt' --exclude='b*' alpha . | sort",
            "./docs/a.md:1:# alpha\n./docs/a.md:2:first line of alpha\n",
        ),
        ("grep -rl --exclude='*.md' alpha . | sort", ""),
        (
            "grep -rE 'al{,1}pha' docs",
            "docs/a.md:# alpha\ndocs/a.md:first line of alpha\ndocs/b.md:beta mentions alpha once\n",
        ),
    ],
)
async def test_a_served_grep_prints_what_gnu_grep_prints_where_the_library_departs(line: str, stdout: str) -> None:
    """Each answer is GNU grep 3.11's over a copy of the seed world, in ``C.UTF-8``."""
    fs = await _world()
    result = await run_line(fs, line, AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert (result.stdout, result.stderr) == (stdout, "")


async def test_an_include_after_an_exclude_is_the_librarys() -> None:
    fs = await _world()
    result = await run_line(
        fs, "grep -r --exclude='a*' --include='*.md' alpha docs", AGENT, cwd="/work", env=ENVIRONMENT
    )
    await fs.close()
    assert "unrecognized option" in result.stderr


async def test_a_recursive_grep_over_two_hundred_files_is_one_grep_call(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    for n in range(200):
        body = "needle here\n" if n % 7 == 0 else "hay\n"
        ok(await fs.write(path=f"/docs/d{n % 10}/f{n:03}.md", content=body, parents=True, authority=SYSTEM))
    ok(await fs.grant("/", "agent", "read_write", authority=SYSTEM))
    calls = _spy(monkeypatch, fs, ("grep", "read", "ls", "stat", "glob"))
    result = await run_line(fs, "grep -rn needle /docs", AGENT, cwd="/", env=ENVIRONMENT)
    assert calls == ["stat", "grep"]
    with monkeypatch.context() as patched:
        patched.setitem(programs_module.PROGRAMS, "grep", _hand_back)
        library = await run_line(fs, "grep -rn needle /docs", AGENT, cwd="/", env=ENVIRONMENT)
    await fs.close()
    assert calls.count("read") == 200
    assert result.stdout == library.stdout
    assert result.stdout.count("\n") == 29


async def test_grep_and_find_are_programs_to_type_on_the_vfs_host() -> None:
    fs = await _world()
    result = await run_line(fs, "type grep find search; command -v glob", AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert result.stdout == ("grep is /usr/bin/grep\nfind is /usr/bin/find\nsearch is /usr/bin/search\n/usr/bin/glob\n")


def _grep_and_find_cases() -> list[tuple[str, str, dict[str, Any], bool, bool]]:
    known = _known_failures()
    return [
        case for case in _cases() if case[0].startswith(("programs/grep/", "programs/find/")) and case[0] not in known
    ]


@pytest.mark.parametrize(
    ("name", "source", "record", "seed", "stderr_exact"),
    _grep_and_find_cases(),
    ids=[case[0] for case in _grep_and_find_cases()],
)
async def test_a_grep_or_find_case_runs_on_the_vfs_host_as_bash_recorded_it(
    name: str, source: str, record: dict[str, Any], seed: bool, stderr_exact: bool
) -> None:
    fs = await _seeded(seed)
    result = await run_line(fs, source, AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert result.stdout.encode() == _stream(record, "stdout")
    assert result.exit_code == record["status"]
    want_err = _stream(record, "stderr")
    if stderr_exact:
        assert result.stderr.encode() == want_err
    else:
        assert bool(result.stderr) == bool(want_err)


# ---------------------------------------------------------------------------
# find from the glob verb
# ---------------------------------------------------------------------------


SERVED_FIND = (
    "find .",
    "find docs -name '*.md'",
    "find . -type f",
    "find . -type d",
    "find . -name '[ab].md'",
    "find . -name '????.txt'",
    "find . -iname 'A*'",
    "find tree -iname '?.md'",
    "find tree -ipath 'TREE/?.MD'",
    "find src -path '*lib*'",
    "find . -wholename './src/*.py'",
    "find . -ipath './DOCS/*'",
    "find . -maxdepth 1",
    "find . -maxdepth 0",
    "find . -mindepth 2 -type f",
    "find . -maxdepth 2 -mindepth 2",
    "find docs/a.md",
    "find docs/a.md -type d; echo $?",
    "find nope docs; echo $?",
    "find docs nope 2>&1; echo $?",
    "find /work -name helpers.py",
    "find docs/ -name 'a*'",
    "find . -name '*.md' -print",
    "find . -name '*.md' -a -type f",
    "find . -name '*.txt' -and -name 'n*'",
    "find tree",
    "find tree -type d -name '*'",
    "find . -name '{a,b}.md'",
    "find . -name 'a**'",
    "find . -name '.*'",
    "cd docs && find",
    "find / -name 'a.md'",
    "find . -true",
    "find . -name '*.md' | head -1",
)


@pytest.mark.parametrize("line", SERVED_FIND)
async def test_a_served_find_prints_what_the_library_prints_at_one_glob_call(
    monkeypatch: pytest.MonkeyPatch, line: str
) -> None:
    want = await _library(monkeypatch, line, "find")
    fs = await _world()
    calls = _spy(monkeypatch, fs, ("glob", "ls", "stat"))
    result = await run_line(fs, line, AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert (result.stdout, result.stderr, result.exit_code) == want
    assert "ls" not in calls
    assert calls.count("glob") >= 1 or "-maxdepth 0" in line or "docs/a.md" in line
    starts = _find_starts(line)
    assert calls.count("stat") == starts + line.count("cd ")
    assert calls.count("glob") <= starts


def _find_starts(line: str) -> int:
    """How many starting points the ``find`` of ``line`` names, at least the one it defaults to."""
    words = line.split("find", 1)[1].split("|")[0].split(";")[0].split("2>")[0].split()
    named = 0
    for word in words:
        if word.startswith("-") or word in ("!", "("):
            break
        named += 1
    return max(1, named)


LIBRARY_FIND = (
    "find . -name '*.md' -o -name '*.py'",
    "find . -not -name '*.md'",
    "find . ! -type d",
    "find . -empty",
    "find . -name docs -prune",
    "find . -name '[^a]*'",
    "find . -name '[[:digit:]]*'",
    "find . -name 'a\\*'",
    "find . -type l",
    "find . -print -name '*.md'",
    "find . -name '*.md' -maxdepth 1",
    "find . -print0",
    "find . -bogus",
    "find . -maxdepth x",
    "find . -a -name '*.md'",
    "find . -name '*.md' -a",
    "find . -name",
)


@pytest.mark.parametrize("line", LIBRARY_FIND)
async def test_a_find_form_the_verb_cannot_serve_is_the_librarys(monkeypatch: pytest.MonkeyPatch, line: str) -> None:
    want = await _library(monkeypatch, line, "find")
    fs = await _world()
    calls = _spy(monkeypatch, fs, ("glob",))
    result = await run_line(fs, line, AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert (result.stdout, result.stderr, result.exit_code) == want
    assert calls == []


async def test_find_over_two_hundred_files_is_one_glob_call(monkeypatch: pytest.MonkeyPatch) -> None:
    fs = AsyncVirtualFileSystem()
    for n in range(200):
        ok(
            await fs.write(
                path=f"/docs/d{n % 10}/f{n:03}.{'md' if n % 2 else 'txt'}", content="x", parents=True, authority=SYSTEM
            )
        )
    ok(await fs.grant("/", "agent", "read_write", authority=SYSTEM))
    calls = _spy(monkeypatch, fs, ("glob", "read", "ls", "stat"))
    result = await run_line(fs, "find /docs -name '*.md'", AGENT, cwd="/", env=ENVIRONMENT)
    await fs.close()
    assert calls == ["stat", "glob"]
    assert result.stdout.count("\n") == 100
    assert result.stdout.splitlines()[:2] == ["/docs/d1/f001.md", "/docs/d1/f011.md"]


# ---------------------------------------------------------------------------
# The verbs with no Unix name
# ---------------------------------------------------------------------------


async def _graph() -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem()
    for path in ("/g/a.md", "/g/b.md", "/g/c.md", "/g/sub/d.md"):
        ok(await fs.write(path=path, content="alpha beta gamma\n", parents=True, authority=SYSTEM))
    ok(await fs.mkedge(source="/g/a.md", target="/g/b.md", edge_type="links", authority=SYSTEM))
    ok(await fs.mkedge(source="/g/b.md", target="/g/c.md", edge_type="cites", authority=SYSTEM))
    ok(await fs.grant("/", "ada", "read_write", authority=SYSTEM))
    return fs


@pytest.mark.parametrize(
    ("line", "verb", "stdout", "status"),
    [
        ("glob '*.md' /g", "glob", "/g/a.md\n/g/b.md\n/g/c.md\n/g/sub/d.md\n", 0),
        ("cd /g && glob -t d '*' .", "glob", "/g\n/g/sub\n", 0),
        ("glob -n 1 'a.*' /g", "glob", "/g/a.md\n", 0),
        ("glob --type=f -- '*' /g/sub", "glob", "/g/sub/d.md\n", 0),
        ("glob --type f '*' /g/sub", "glob", "/g/sub/d.md\n", 0),
        ("traverse -d all outbound /g/a.md", "traverse", "/g/a.md\n/g/b.md\n/g/c.md\n", 0),
        ("traverse meet /g/a.md /g/c.md", "traverse", "/g/a.md\n/g/c.md\n/g/b.md\n", 0),
        ("glob '*.py' /g", "glob", "", 1),
        ("traverse outbound /g/a.md", "traverse", "/g/a.md\n/g/b.md\n", 0),
        ("traverse -d 2 outbound /g/a.md", "traverse", "/g/a.md\n/g/b.md\n/g/c.md\n", 0),
        ("traverse -d 2 -t links outbound /g/a.md", "traverse", "/g/a.md\n/g/b.md\n", 0),
        ("traverse -e -d 2 outbound /g/a.md", "traverse", "/g/a.md\tlinks\t/g/b.md\n/g/b.md\tcites\t/g/c.md\n", 0),
        ("traverse inbound /g/c.md", "traverse", "/g/c.md\n/g/b.md\n", 0),
        ("traverse outbound /g/none.md", "traverse", "", 1),
        ("cd /g && grant sub bob read", "grant", "", 0),
        ("revoke /g bob", "revoke", "", 0),
        ("cd /g && grants a.md", "grants", "/\t*\tread_write\n/\tada\tread_write\n", 0),
        ("edit /g/a.md beta BETA && cat /g/a.md", "edit", "alpha BETA gamma\n", 0),
        ("edit -a /g/a.md a A && cat /g/a.md", "edit", "AlphA betA gAmmA\n", 0),
        ("mkedge -t links /g/c.md /g/a.md && traverse outbound /g/c.md", "mkedge", "/g/c.md\n/g/a.md\n", 0),
        ("rmedge -t links /g/a.md /g/b.md && traverse outbound /g/a.md", "rmedge", "/g/a.md\n", 0),
    ],
)
async def test_a_verb_with_no_unix_name_is_one_call_of_its_verb_as_the_caller(
    monkeypatch: pytest.MonkeyPatch, line: str, verb: str, stdout: str, status: int
) -> None:
    fs = await _graph()
    calls: list[tuple[str, Authority | None]] = []
    original: Callable[..., Any] = getattr(fs, verb)

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append((verb, kwargs.get("authority")))
        return original(*args, **kwargs)

    monkeypatch.setattr(fs, verb, spy)
    result = await fs.cli(line + "; echo status=$?", authority=ADA)
    await fs.close()
    assert result.stdout == stdout + f"status={status}\n", result.stderr
    assert calls == [(verb, ADA)]


TROUBLE = frozenset({"glob '*.md' /nope /g", "glob 'a**' /g"})
"""Lines a program could not finish, which print their reason alone, as against a misuse."""


@pytest.mark.parametrize(
    ("line", "stderr", "status"),
    [
        ("glob", "glob: missing pattern\n", 2),
        ("glob -t x '*'", "glob: invalid type: \u2018x\u2019\n", 2),
        ("glob -n 0 '*'", "glob: invalid count: \u20180\u2019\n", 2),
        ("glob '*' -t", "glob: option requires an argument -- 't'\n", 2),
        ("glob '*' --type", "glob: option '--type' requires an argument\n", 2),
        ("glob --bogus '*'", "glob: unrecognized option '--bogus'\n", 2),
        ("edit --all=x /g/a.md a b", "edit: option '--all' doesn't allow an argument\n", 2),
        ("edit /g a b", "edit: /g: Is a directory\n", 1),
        ("traverse outbound", "traverse: missing start\n", 2),
        ("traverse -n x outbound /g/a.md", "traverse: invalid limit: \u2018x\u2019\n", 2),
        ("revoke /g bob extra", "revoke: extra operand \u2018extra\u2019\n", 2),
        ("glob -q '*'", "glob: invalid option -- 'q'\n", 2),
        ("glob '*.md' /nope /g", "glob: /nope: No such file or directory\n", 2),
        (
            "glob 'a**' /g",
            "glob: glob pattern 'a**': '**' inside a component ('a**') — use '**' as a whole path segment\n",
            2,
        ),
        ("search -n x alpha", "search: invalid limit: \u2018x\u2019\n", 2),
        ("search", "search: missing query\n", 2),
        ("traverse", "traverse: missing method\n", 2),
        ("traverse sideways /g/a.md", "traverse: invalid method: \u2018sideways\u2019\n", 2),
        ("traverse -d x outbound /g/a.md", "traverse: invalid depth: \u2018x\u2019\n", 2),
        ("grant /g bob", "grant: missing level\n", 2),
        ("grant /g bob reed", "grant: invalid level: \u2018reed\u2019\n", 2),
        ("revoke /g", "revoke: missing principal\n", 2),
        ("grants", "grants: missing path\n", 2),
        ("edit /g/a.md zzz y", "edit: /g/a.md: old_string not found in file content.\n", 1),
        ("edit /g/nope.md a b", "edit: /g/nope.md: No such file or directory\n", 1),
        ("edit /g/a.md x", "edit: missing replacement\n", 2),
        ("mkedge /g/a.md /g/b.md", "mkedge: missing edge type; name it with -t\n", 2),
        ("mkedge -t links /g/a.md /g/zz.md", "mkedge: /g/zz.md: No such file or directory\n", 1),
        ("rmedge -t links /g/a.md", "rmedge: missing target\n", 2),
    ],
)
async def test_a_program_misused_says_why_as_gnu_tools_do(line: str, stderr: str, status: int) -> None:
    fs = await _graph()
    result = await fs.cli(line, authority=ADA)
    await fs.close()
    name = line.split()[0]
    misuse = status == 2 and line not in TROUBLE
    help_hint = f"{programs_module.USAGE[name]}Try '{name} --help' for more information.\n" if misuse else ""
    assert result.stderr == stderr + help_hint
    assert result.exit_code == status


@pytest.mark.parametrize(
    "name", ["glob", "search", "traverse", "grant", "revoke", "grants", "edit", "mkedge", "rmedge"]
)
async def test_each_program_prints_its_help_and_exits_zero(name: str) -> None:
    result = await AsyncVirtualFileSystem().cli(f"{name} --help", authority=ADA)
    assert result.exit_code == 0
    assert result.stdout.startswith(programs_module.USAGE[name])
    assert result.stderr == ""


async def test_a_program_that_changes_rights_or_bodies_forgets_the_bodies_the_line_holds() -> None:
    fs = await _graph()
    line = "cat /g/a.md; edit /g/a.md alpha omega; cat /g/a.md; grant /g/b.md ada read; cat /g/a.md"
    result = await fs.cli(line, authority=ADA)
    await fs.close()
    assert result.stdout == "alpha beta gamma\nomega beta gamma\nomega beta gamma\n"


async def test_a_refusal_inside_a_program_is_kept_as_a_warning() -> None:
    fs = await _graph()
    result = await fs.cli("edit /g/nope.md a b; echo $?", authority=ADA)
    await fs.close()
    assert result.stdout == "1\n"
    assert [str(error.kind) for error in result.errors] == ["vfs.not_found"]


async def test_each_program_resolved_by_the_host_is_listed_for_the_machine() -> None:
    assert set(programs_module.PROGRAMS) == {
        "grep",
        "find",
        "glob",
        "search",
        "traverse",
        "grant",
        "revoke",
        "grants",
        "edit",
        "mkedge",
        "rmedge",
    }
    assert not set(programs_module.PROGRAMS) & set(host_module.library_programs())


async def test_the_line_result_of_a_served_program_is_a_result() -> None:
    fs = await _world()
    result: Result = await run_line(fs, "grep -rl alpha docs", AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert result.success is True


async def test_a_served_grep_leaves_out_a_body_stored_as_bytes() -> None:
    """A departure from GNU: the grep verb matches text and renderings, never raw bytes, so GNU's
    ``Binary file ... matches`` and a match in UTF-8 written as bytes are not printed."""
    fs = await _world()
    ok(await fs.write(path="/work/bin/raw.dat", data=b"alpha\x00\xff\n", parents=True, authority=SYSTEM))
    ok(await fs.write(path="/work/bin/text.md", data=b"alpha as bytes\n", authority=SYSTEM))
    served = await run_line(fs, "grep -r alpha bin; echo $?", AGENT, cwd="/work", env=ENVIRONMENT)
    library = await run_line(fs, "grep alpha bin/raw.dat bin/text.md", AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert served.stdout == "1\n"
    assert library.stdout == "Binary file bin/raw.dat matches\nbin/text.md:alpha as bytes\n"


async def test_a_served_grep_leaves_out_a_file_the_caller_may_list_but_not_read() -> None:
    """A departure from GNU: no verb tells an unreadable file from one that does not match without
    reading every file, so a served grep is silent where GNU prints ``Permission denied`` and exits 2."""
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/s/open.txt", content="alpha open\n", parents=True, authority=SYSTEM))
    ok(await fs.write(path="/s/secret.txt", content="alpha secret\n", authority=SYSTEM))
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    ok(await fs.grant("/s", "agent", "list", authority=SYSTEM))
    ok(await fs.grant("/s/open.txt", "agent", "read", authority=SYSTEM))
    served = await run_line(fs, "grep -r alpha /s", AGENT, cwd="/", env=ENVIRONMENT)
    library = await run_line(fs, "grep alpha /s/open.txt /s/secret.txt", AGENT, cwd="/", env=ENVIRONMENT)
    await fs.close()
    assert (served.stdout, served.stderr, served.exit_code) == ("/s/open.txt:alpha open\n", "", 0)
    assert (library.stderr, library.exit_code) == ("grep: /s/secret.txt: Permission denied\n", 2)


def _truncating(fs: AsyncVirtualFileSystem, verb: str, monkeypatch: pytest.MonkeyPatch) -> None:
    original: Callable[..., Any] = getattr(fs, verb)

    async def truncated(*args: Any, **kwargs: Any) -> Result:
        answer = await original(*args, **kwargs)
        cut = classified(ErrorKind.truncated, detail="the stage's time budget", severity=Severity.warning)
        return answer.model_copy(update={"observations": answer.observations[:1], "errors": [*answer.errors, cut]})

    monkeypatch.setattr(fs, verb, truncated)


@pytest.mark.parametrize(
    ("line", "verb"),
    [("grep -rn alpha docs", "grep"), ("grep -rc alpha docs", "glob"), ("find docs -name '*.md'", "glob")],
)
async def test_a_verb_answer_cut_short_hands_the_line_to_the_library(
    monkeypatch: pytest.MonkeyPatch, line: str, verb: str
) -> None:
    want = await _library(monkeypatch, line, line.split()[0])
    fs = await _world()
    _truncating(fs, verb, monkeypatch)
    result = await run_line(fs, line, AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert (result.stdout, result.stderr, result.exit_code) == want


async def test_grants_of_a_path_the_caller_cannot_see_reads_as_its_unix_error() -> None:
    fs = await _graph()
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    result = await fs.cli("grants /g/a.md; echo $?", authority=Authority.of(Principal("grace")))
    await fs.close()
    assert (result.stdout, result.stderr) == ("1\n", "grants: /g/a.md: No such file or directory\n")


@pytest.mark.parametrize(
    ("pattern", "names"),
    [
        ("s.md", ["S.md", "s.md"]),
        ("i.md", ["I.md", "i.md", "\u0130.md"]),
        ("k.md", ["k.md"]),
        ("S.MD", ["S.md", "s.md"]),
        ("?.md", ["I.md", "S.md", "i.md", "k.md", "s.md", "\u0130.md", "\u0131.md", "\u017f.md"]),
        ("[a-z].md", ["I.md", "S.md", "i.md", "k.md", "s.md", "\u0130.md"]),
    ],
)
async def test_a_served_find_iname_folds_each_character_as_gnu_find_does(pattern: str, names: list[str]) -> None:
    """Each answer is GNU findutils' in ``C.UTF-8``: the dotted capital I lowers to ``i``, and the long s
    and the dotless i lower to themselves. The Kelvin sign is left out, as a path's NFC fold makes it ``K``."""
    fs = await _world()
    for name in ("\u017f", "\u0131", "\u0130", "s", "i", "k", "S", "I"):
        ok(await fs.write(path=f"/work/fold/{name}.md", content="x", parents=True, authority=SYSTEM))
    result = await run_line(fs, f"find fold -iname '{pattern}'", AGENT, cwd="/work", env=ENVIRONMENT)
    await fs.close()
    assert sorted(result.stdout.splitlines()) == sorted(f"fold/{name}" for name in names)
