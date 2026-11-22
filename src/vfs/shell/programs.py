"""The programs vfs runs itself inside a line, each a call or two of public verbs as the caller.

Two families share one table, :data:`PROGRAMS`. ``grep`` and ``find`` keep GNU's names and
GNU's output. The host serves a form from the indexed verbs when the verbs' answer is the one
GNU's program prints: ``grep -r`` is one call of ``grep``, where the shell's library reads every
file beneath its roots, and ``find`` is one call of ``glob`` for each directory it starts from,
where the library lists every directory and stats every file. Any other form, or a form whose
answer came back cut short, is handed back to the library, so a served form prints what the
library prints for it and only the cost differs. The library prints GNU's output for every option
it knows; it knows no ``--include`` or ``--exclude``, so a form of those it is handed back ends in
GNU's ``unrecognized option``.

A served program holds its whole answer before the line reads a byte of it, so its memory follows
what it matched, not the size of the tree, and ``| head`` does not bound it as it bounds the library.

Two things a served ``grep -r`` cannot print as GNU's would, since no verb tells them apart
without reading every file. A file the caller may list but not read is left out of its matches
without a word, and counted 0 by ``-c``, where GNU prints ``Permission denied`` and exits 2. A
body stored as bytes is never matched, where GNU matches its raw bytes and prints ``Binary file
... matches``.

The verbs with no Unix name are programs in the shape of a GNU tool: ``glob``, ``search``,
``traverse``, ``grant``, ``revoke``, ``grants``, ``edit``, ``mkedge`` and ``rmedge``. Each takes
its options as getopt takes them, prints ``--help``, answers a misuse with its reason, a usage
line and status 2, prints a refusal as ``name: path: reason`` with status 1, and is one call of
its verb. The query programs print absolute paths one a line and exit 0 when they found
something, 1 when they found nothing and 2 on trouble, as ``grep`` does.

    $ grep -rn TODO /docs | head -3        # one grep call
    $ find /docs -name '*.md'               # one stat, one glob
    $ traverse -d 2 outbound /docs/a.md     # one traverse call
"""

from __future__ import annotations

import posixpath
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Final, NamedTuple, Protocol

from vfs.models import Observation
from vfs.ops import RUNGS, TRAVERSE_DEPTH_DEFAULT, TRAVERSE_LIMIT_DEFAULT, TRAVERSE_METHODS
from vfs.results import ErrorKind
from vfs.results.kinds import KIND_CONTRACTS
from vfs.shell.patterns import case_folds_alike, fnmatch_safe, glob_safe, verb_regex

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from vfs.authority import Authority
    from vfs.ops import CaseMode, GrepOutputMode, Rung
    from vfs.paths import ObjectKind
    from vfs.results import Result, ResultError
    from vfs.shell.patterns import Dialect, Translated

USAGE: Final[dict[str, str]] = {
    "glob": "Usage: glob [-t f|d] [-n MAX] PATTERN [PATH]...\n",
    "search": "Usage: search [-n LIMIT] QUERY [PATH]...\n",
    "traverse": "Usage: traverse [-e] [-m] [-d DEPTH|all] [-t TYPE]... [-T TYPE]... [-n LIMIT] METHOD PATH...\n",
    "grant": "Usage: grant PATH PRINCIPAL LEVEL\n",
    "revoke": "Usage: revoke PATH PRINCIPAL\n",
    "grants": "Usage: grants PATH\n",
    "edit": "Usage: edit [-a] PATH OLD NEW\n",
    "mkedge": "Usage: mkedge -t TYPE SOURCE TARGET\n",
    "rmedge": "Usage: rmedge -t TYPE SOURCE TARGET\n",
}
"""Each verb program's usage line, the first line of its ``--help`` and of a misuse."""

_HELP: Final[dict[str, str]] = {
    "glob": "Print the paths whose names or paths match PATTERN beneath each PATH, or every mount.\n"
    "  -t, --type=f|d       only files, or only directories\n"
    "  -n, --max-count=MAX  print at most MAX paths\n",
    "search": "Print the paths that best match QUERY beneath each PATH, or every mount, best first.\n"
    "  -n, --limit=LIMIT    print at most LIMIT paths (10)\n",
    "traverse": "Walk the edges from each PATH by METHOD: inbound, outbound, neighborhood or meet.\n"
    "  -d, --depth=DEPTH    hops from the nearest start, or all (1)\n"
    "  -t, --type=TYPE      follow edges of TYPE\n"
    "  -T, --exclude-type=TYPE  leave edges of TYPE out\n"
    "  -n, --limit=LIMIT    at most LIMIT nodes from each storage (128)\n"
    "  -m, --minimal        a meet keeps only the nodes that hold the starts together\n"
    "  -e, --edges          print SOURCE TYPE TARGET for each edge, not the nodes\n",
    "grant": "Give PRINCIPAL the level LEVEL at PATH and beneath: list, read, add, contribute or read_write.\n",
    "revoke": "Remove the grant of PRINCIPAL at exactly PATH.\n",
    "grants": "Print PATH PRINCIPAL LEVEL for each grant that decides access at PATH.\n",
    "edit": "Replace the first OLD in PATH with NEW.\n  -a, --all            replace every OLD\n",
    "mkedge": "Make an edge of TYPE from SOURCE to TARGET, or refresh it.\n  -t, --type=TYPE      the edge's type\n",
    "rmedge": "Remove the edge of TYPE from SOURCE to TARGET.\n  -t, --type=TYPE      the edge's type\n",
}

GREP_USAGE: Final = "Usage: grep [OPTION]... PATTERNS [FILE]...\n"

_GREP_FLAGS: Final[dict[str, str]] = {
    "E": "extended",
    "F": "fixed",
    "G": "basic",
    "i": "ignore_case",
    "y": "ignore_case",
    "n": "number",
    "l": "files_with",
    "c": "count",
    "r": "recursive",
    "R": "recursive",
    "h": "no_name",
    "H": "with_name",
    "s": "silent",
    "q": "quiet",
}
"""The short options of ``grep`` a served form may carry, each by what it sets."""

_GREP_LONG: Final[dict[str, str]] = {
    "extended-regexp": "E",
    "fixed-strings": "F",
    "basic-regexp": "G",
    "ignore-case": "i",
    "line-number": "n",
    "files-with-matches": "l",
    "count": "c",
    "recursive": "r",
    "dereference-recursive": "R",
    "no-filename": "h",
    "with-filename": "H",
    "no-messages": "s",
    "quiet": "q",
    "silent": "q",
}

_GREP_IGNORED: Final = frozenset({"color", "colour", "line-buffered"})

_UNIX_ERRORS: Final[dict[str, str]] = {
    ErrorKind.not_found: "No such file or directory",
    ErrorKind.permission_denied: "Permission denied",
    ErrorKind.unauthenticated: "Permission denied",
    ErrorKind.read_only: "Permission denied",
    ErrorKind.exists: "File exists",
    ErrorKind.not_empty: "Directory not empty",
}
"""The ``strerror`` text a refusal reads as, by its kind."""

_LEVELS: Final = frozenset(rung for rung in RUNGS if rung != "none")


class Router(Protocol):
    """The verbs a line can reach, each called with the caller's authority.

    The router (:class:`~vfs.AsyncVirtualFileSystem`) is one; the shell names only the verbs, so it
    sits beneath the router and imports nothing above it.
    """

    async def read(self, path: str, /, *, columns: frozenset[str], authority: Authority | None) -> Result: ...

    async def stat(self, path: str, /, *, authority: Authority | None) -> Result: ...

    async def ls(self, path: str, /, *, authority: Authority | None) -> Result: ...

    async def glob(
        self,
        pattern: str,
        /,
        *,
        paths: tuple[str, ...],
        kind: ObjectKind | None,
        max_count: int | None,
        authority: Authority | None,
    ) -> Result: ...

    async def grep(
        self,
        pattern: str,
        /,
        *,
        paths: tuple[str, ...],
        globs: tuple[str, ...],
        globs_not: tuple[str, ...],
        case_mode: CaseMode,
        fixed_strings: bool,
        output_mode: GrepOutputMode,
        allow_scan: bool,
        authority: Authority | None,
    ) -> Result: ...

    async def search(
        self, query: str, /, *, limit: int, paths: tuple[str, ...], authority: Authority | None
    ) -> Result: ...

    async def traverse(
        self,
        method: str,
        path: str | None = ...,
        observations: list[Observation] | None = ...,
        *,
        depth: int | None,
        edge_types: tuple[str, ...],
        edge_types_not: tuple[str, ...],
        minimal: bool,
        limit: int | None,
        authority: Authority | None,
    ) -> Result: ...

    async def write(
        self,
        *,
        path: str,
        authority: Authority | None,
        content: str | None = ...,
        data: bytes | None = ...,
        if_absent: bool = ...,
        append: bool = ...,
    ) -> Result: ...

    async def edit(
        self, path: str, old: str, new: str, /, *, replace_all: bool, authority: Authority | None
    ) -> Result: ...

    async def mkdir(self, path: str, /, *, parents: bool, exist_ok: bool, authority: Authority | None) -> Result: ...

    async def delete(self, path: str, /, *, cascade: bool, authority: Authority | None) -> Result: ...

    async def copy(self, src: str, dest: str, /, *, authority: Authority | None) -> Result: ...

    async def move(self, src: str, dest: str, /, *, authority: Authority | None) -> Result: ...

    async def mkedge(self, *, source: str, target: str, edge_type: str, authority: Authority | None) -> Result: ...

    async def rmedge(self, *, source: str, target: str, edge_type: str, authority: Authority | None) -> Result: ...

    async def grant(self, path: str, principal: str, level: Rung, /, *, authority: Authority | None) -> Result: ...

    async def revoke(self, path: str, principal: str, /, *, authority: Authority | None) -> Result: ...

    async def grants(self, path: str, /, *, authority: Authority | None) -> Result: ...


class Ran(NamedTuple):
    """What a program wrote, a stream and its bytes in the order written, and its exit status."""

    writes: tuple[tuple[int, bytes], ...]
    status: int


class Caller(Protocol):
    """The line a program runs in: the router, the caller's authority, and where refusals are kept."""

    @property
    def fs(self) -> Router: ...

    @property
    def authority(self) -> Authority: ...

    def keep(self, fact: ResultError) -> None: ...


# ---------------------------------------------------------------------------
# grep -r from the grep verb
# ---------------------------------------------------------------------------


class _GrepForm(NamedTuple):
    """A served ``grep`` line, read: what it searches for, how, beneath what, and how it prints."""

    patterns: tuple[str, ...]
    dialect: Dialect
    options: frozenset[str]
    with_name: bool | None
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    operands: tuple[str, ...]


async def grep(caller: Caller, words: list[str], cwd: str) -> Ran | None:
    """``grep -r`` served by one call of the ``grep`` verb, or ``None`` for the library's form."""
    form = _grep_form(words)
    if form is None:
        return None
    translated = _grep_pattern(form)
    if translated is None:
        return None
    explicit = bool(form.operands)
    out = _Out("grep")
    roots: list[tuple[str, str, bool]] = []
    trouble = False
    for operand in form.operands or (".",):
        path = absolute(cwd, operand)
        stat = await caller.fs.stat(path, authority=caller.authority)
        if not stat.success:
            if "silent" not in form.options:
                out.err(f"grep: {operand}: No such file or directory\n")
            trouble = True
            continue
        directory = stat.observations[0].kind == "directory"
        shown = "" if directory and not explicit and operand == "." else operand
        roots.append((path, shown, directory))
    filtered = bool(form.includes or form.excludes)
    if filtered and not all(directory for _, _, directory in roots):
        return None
    mode: GrepOutputMode = "lines"
    if form.options & {"quiet", "files_with"}:
        mode = "files"
    elif "count" in form.options:
        mode = "count"
    found: dict[str, Observation] = {}
    every: list[Observation] = []
    if roots:
        paths = tuple(dict.fromkeys(path for path, _, _ in roots))
        one = len(form.patterns) == 1 and form.dialect == "fixed"
        result = await caller.fs.grep(
            form.patterns[0] if one else translated.regex,
            paths=paths,
            globs=form.includes,
            globs_not=form.excludes,
            case_mode="insensitive" if "ignore_case" in form.options else "sensitive",
            fixed_strings=one,
            output_mode=mode,
            allow_scan=True,
            authority=caller.authority,
        )
        if not result.success or result.errors:
            return None
        found = {str(row.path): row for row in result.observations}
        if mode == "count":
            dirs = tuple(dict.fromkeys(path for path, _, directory in roots if directory))
            if dirs:
                listing = await caller.fs.glob("*", paths=dirs, kind=None, max_count=None, authority=caller.authority)
                if not listing.success or listing.errors:
                    return None
                every = [row for row in listing.observations if row.kind != "directory"]
    show_name = form.with_name if form.with_name is not None else True
    selected = False
    for root, shown, directory in roots:
        if directory:
            beneath = every if mode == "count" else list(found.values())
            targets = sorted(
                ((_grep_order(root, str(row.path)), str(row.path)) for row in beneath if _under(root, str(row.path))),
            )
            files = [(path, _shown_beneath(shown, root, path)) for _, path in targets]
        else:
            files = [(root, shown)]
        for path, name in files:
            row = found.get(path)
            if row is not None:
                selected = True
            if mode == "files":
                if row is not None and "quiet" not in form.options:
                    out.out(f"{name}\n")
            elif mode == "count":
                count = int(row.score or 0) if row is not None else 0
                out.out(f"{name}:{count}\n" if show_name else f"{count}\n")
            elif row is not None:
                prefix = f"{name}:" if show_name else ""
                for match in row.matches or []:
                    number = f"{match.match}:" if "number" in form.options else ""
                    out.out(f"{prefix}{number}{match.content}\n")
    if "quiet" in form.options and selected:
        return out.done(0)
    if trouble:
        return out.done(2)
    return out.done(0 if selected else 1)


def _grep_form(words: list[str]) -> _GrepForm | None:
    """Read a ``grep`` line the way GNU's getopt does, or ``None`` when any part is not served."""
    options: set[str] = set()
    dialect: Dialect = "basic"
    with_name: bool | None = None
    patterns: list[str] = []
    includes: list[str] = []
    excludes: list[str] = []
    operands: list[str] = []
    index = 0
    done = False
    while index < len(words):
        word = words[index]
        index += 1
        if done or not word.startswith("-") or word == "-":
            operands.append(word)
            continue
        if word == "--":
            done = True
            continue
        if word.startswith("--"):
            name, equals, value = word[2:].partition("=")
            if name in _GREP_IGNORED:
                continue
            if name in ("regexp", "include", "exclude"):
                if not equals:
                    return None
                if name == "regexp":
                    patterns.extend(value.split("\n"))
                elif excludes or name == "exclude":
                    if name == "include":
                        return None
                    excludes.append(value)
                else:
                    includes.append(value)
                continue
            if equals or name not in _GREP_LONG:
                return None
            letters = _GREP_LONG[name]
        else:
            letters = word[1:]
        at = 0
        while at < len(letters):
            letter = letters[at]
            at += 1
            if letter == "e":
                value = letters[at:] if at < len(letters) else (words[index] if index < len(words) else None)
                if value is None:
                    return None
                if at >= len(letters):
                    index += 1
                patterns.extend(value.split("\n"))
                break
            setting = _GREP_FLAGS.get(letter)
            if setting is None:
                return None
            if setting in ("extended", "fixed", "basic"):
                dialect = "fixed" if setting == "fixed" else "extended" if setting == "extended" else "basic"
            elif setting == "no_name":
                with_name = False
            elif setting == "with_name":
                with_name = True
            else:
                options.add(setting)
    if "recursive" not in options:
        return None
    if not patterns:
        if not operands:
            return None
        patterns.extend(operands.pop(0).split("\n"))
    if any(not glob_safe(glob) for glob in (*includes, *excludes)):
        return None
    if (includes or excludes) and "count" in options:
        return None
    if "-" in operands:
        return None
    return _GrepForm(
        tuple(patterns), dialect, frozenset(options), with_name, tuple(includes), tuple(excludes), tuple(operands)
    )


def _grep_pattern(form: _GrepForm) -> Translated | None:
    """The form's patterns as one pattern of the verb's language, or ``None`` when one is not served."""
    parts: list[Translated] = []
    for pattern in form.patterns:
        translated = verb_regex(pattern, form.dialect)
        if translated is None:
            return None
        if "ignore_case" in form.options and not case_folds_alike(pattern):
            return None
        parts.append(translated)
    if len(parts) == 1:
        return parts[0]
    return parts[0]._replace(regex="|".join(f"(?:{part.regex})" for part in parts), literal=None)


def _grep_order(root: str, path: str) -> tuple[tuple[int, str], ...]:
    """The key the library's walk prints in: in each directory its files first, then its directories."""
    segments = _relative(root, path).split("/")
    return (*((1, segment) for segment in segments[:-1]), (0, segments[-1]))


def _shown_beneath(shown: str, root: str, path: str) -> str:
    """A file beneath a ``grep`` root as the library names it: the root as typed, then the rest."""
    rest = _relative(root, path)
    return f"{shown.rstrip('/')}/{rest}" if shown else rest


# ---------------------------------------------------------------------------
# find from the glob verb
# ---------------------------------------------------------------------------


class _FindTest(NamedTuple):
    """One test of a served ``find``: what it reads, the kind it compares, or the pattern it matches.

    A pattern is matched as GNU ``fnmatch`` reads it with no flags. With ``nocase``, both sides are
    first lowered one character at a time, as ``FNM_CASEFOLD`` lowers each with glibc's ``towlower``.
    """

    reads: str
    value: str
    nocase: bool = False


async def find(caller: Caller, words: list[str], cwd: str) -> Ran | None:
    """``find`` served by one call of the ``glob`` verb for each directory it starts from, or ``None``."""
    split = next(
        (at for at, word in enumerate(words) if (word.startswith("-") and len(word) > 1) or word in ("!", "(")),
        len(words),
    )
    starts = words[:split] or ["."]
    read = _find_expression(words[split:])
    if read is None:
        return None
    tests, mindepth, maxdepth = read
    names = [test.value for test in tests if test.reads == "name" and not test.nocase]
    pattern = next((name for name in names if glob_safe(name)), "*")
    kind: ObjectKind | None = "directory" if any(t.reads == "type" and t.value == "d" for t in tests) else None
    out = _Out("find")
    status = 0
    for start in starts:
        path = absolute(cwd, start)
        stat = await caller.fs.stat(path, authority=caller.authority)
        if not stat.success:
            out.err(f"find: \u2018{start}\u2019: No such file or directory\n")
            status = 1
            continue
        directory = stat.observations[0].kind == "directory"
        visits = [(start, directory, 0)]
        if directory and (maxdepth is None or maxdepth > 0):
            listing = await caller.fs.glob(
                pattern, paths=(path,), kind=kind, max_count=None, authority=caller.authority
            )
            if not listing.success or listing.errors:
                return None
            beneath = sorted(
                (tuple(_relative(path, str(row.path)).split("/")), row.kind == "directory")
                for row in listing.observations
                if _under(path, str(row.path))
            )
            visits.extend(
                (_join(start, "/".join(segments)), is_dir, len(segments))
                for segments, is_dir in beneath
                if maxdepth is None or len(segments) <= maxdepth
            )
        for shown, is_dir, depth in visits:
            if depth >= mindepth and all(_find_passes(test, shown, is_dir) for test in tests):
                out.out(f"{shown}\n")
    return out.done(status)


def _find_expression(tokens: list[str]) -> tuple[list[_FindTest], int, int | None] | None:
    """A ``find`` expression of tests joined by and, its global depth options first, or ``None``."""
    mindepth, maxdepth = 0, None
    index = 0
    while index < len(tokens) and tokens[index] in ("-maxdepth", "-mindepth"):
        if index + 1 >= len(tokens) or not (tokens[index + 1].isascii() and tokens[index + 1].isdigit()):
            return None
        if tokens[index] == "-maxdepth":
            maxdepth = int(tokens[index + 1])
        else:
            mindepth = int(tokens[index + 1])
        index += 2
    tests: list[_FindTest] = []
    joined = True
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token in ("-a", "-and"):
            if joined:
                return None
            joined = True
            continue
        if token == "-print" and index == len(tokens):
            break
        if token == "-true":
            joined = False
            continue
        value = tokens[index] if index < len(tokens) else None
        index += 1
        if value is None:
            return None
        if token in ("-name", "-iname", "-path", "-wholename", "-ipath") and fnmatch_safe(value):
            reads = "name" if token.endswith("name") and "whole" not in token else "path"
            tests.append(_FindTest(reads, value, nocase=token.startswith("-i")))
        elif token == "-type" and value in ("f", "d"):
            tests.append(_FindTest("type", value))
        else:
            return None
        joined = False
    if joined and tokens[index - 1 : index] in (["-a"], ["-and"]):
        return None
    return tests, mindepth, maxdepth


def _find_passes(test: _FindTest, shown: str, directory: bool) -> bool:
    """Whether one visit of ``find`` passes one test, read as GNU ``fnmatch`` reads it with no flags."""
    if test.reads == "type":
        return directory == (test.value == "d")
    subject = shown if test.reads == "path" else ("/" if shown == "/" else shown.rstrip("/").rsplit("/", 1)[-1])
    if test.nocase:
        return fnmatchcase(_lowered(subject), _lowered(test.value))
    return fnmatchcase(subject, test.value)


# ---------------------------------------------------------------------------
# The verbs with no Unix name
# ---------------------------------------------------------------------------


async def glob(caller: Caller, words: list[str], cwd: str) -> Ran:
    """``glob [-t f|d] [-n MAX] PATTERN [PATH]...``: one call of the ``glob`` verb."""
    parsed = _getopt("glob", words, values="tn", longs={"type": "t", "max-count": "n"})
    if isinstance(parsed, Ran):
        return parsed
    options, operands = parsed
    if not operands:
        return _misuse("glob", "missing pattern")
    kind: ObjectKind | None = None
    if "t" in options:
        if _last(options, "t") not in ("f", "d"):
            return _misuse("glob", f"invalid type: \u2018{_last(options, 't')}\u2019")
        kind = "directory" if _last(options, "t") == "d" else "file"
    count = _count(_last(options, "n"))
    if count is False:
        return _misuse("glob", f"invalid count: \u2018{_last(options, 'n')}\u2019")
    typed = {absolute(cwd, path): path for path in operands[1:]}
    result = await caller.fs.glob(
        operands[0], paths=tuple(typed), kind=kind, max_count=count, authority=caller.authority
    )
    out = _Out("glob")
    trouble = _report(caller, out, "glob", result, typed)
    rows = sorted(str(row.path) for row in result.observations)
    for row in rows:
        out.out(f"{row}\n")
    return out.done(2 if trouble else 0 if rows else 1)


async def search(caller: Caller, words: list[str], cwd: str) -> Ran:
    """``search [-n LIMIT] QUERY [PATH]...``: one call of the ``search`` verb, best first."""
    parsed = _getopt("search", words, values="n", longs={"limit": "n"})
    if isinstance(parsed, Ran):
        return parsed
    options, operands = parsed
    if not operands:
        return _misuse("search", "missing query")
    limit = _count(_last(options, "n"))
    if limit is False:
        return _misuse("search", f"invalid limit: \u2018{_last(options, 'n')}\u2019")
    typed = {absolute(cwd, path): path for path in operands[1:]}
    result = await caller.fs.search(
        operands[0], limit=10 if limit is None else limit, paths=tuple(typed), authority=caller.authority
    )
    out = _Out("search")
    trouble = _report(caller, out, "search", result, typed)
    for row in result.observations:
        out.out(f"{row.path}\n")
    return out.done(2 if trouble else 0 if result.observations else 1)


async def traverse(caller: Caller, words: list[str], cwd: str) -> Ran:
    """``traverse [OPTION]... METHOD PATH...``: one call of the ``traverse`` verb, nearest first."""
    parsed = _getopt(
        "traverse",
        words,
        flags="em",
        values="dtTn",
        longs={"depth": "d", "type": "t", "exclude-type": "T", "limit": "n", "minimal": "m", "edges": "e"},
    )
    if isinstance(parsed, Ran):
        return parsed
    options, operands = parsed
    if not operands:
        return _misuse("traverse", "missing method")
    method, starts = operands[0], operands[1:]
    if method not in TRAVERSE_METHODS:
        return _misuse("traverse", f"invalid method: \u2018{method}\u2019")
    if not starts:
        return _misuse("traverse", "missing start")
    depth: int | None = TRAVERSE_DEPTH_DEFAULT
    if "d" in options:
        hops = _count(_last(options, "d"), zero=True)
        if _last(options, "d") == "all":
            depth = None
        elif isinstance(hops, bool) or hops is None:
            return _misuse("traverse", f"invalid depth: \u2018{_last(options, 'd')}\u2019")
        else:
            depth = hops
    limit = _count(_last(options, "n"))
    if limit is False:
        return _misuse("traverse", f"invalid limit: \u2018{_last(options, 'n')}\u2019")
    paths = [absolute(cwd, start) for start in starts]
    result = await caller.fs.traverse(
        method,
        paths[0] if len(paths) == 1 else None,
        None if len(paths) == 1 else [Observation(path=path) for path in paths],
        depth=depth,
        edge_types=tuple(options.get("t", ())),
        edge_types_not=tuple(options.get("T", ())),
        minimal="m" in options,
        limit=TRAVERSE_LIMIT_DEFAULT if limit is None else limit,
        authority=caller.authority,
    )
    out = _Out("traverse")
    trouble = _report(caller, out, "traverse", result, dict(zip(paths, starts, strict=True)))
    printed = False
    for row in result.observations:
        if "e" in options and row.edge_type is not None:
            out.out(f"{row.path}\t{row.edge_type}\t{row.edge_target}\n")
            printed = True
        elif "e" not in options and row.edge_type is None:
            out.out(f"{row.path}\n")
            printed = True
    return out.done(2 if trouble else 0 if printed else 1)


async def grant(caller: Caller, words: list[str], cwd: str) -> Ran:
    """``grant PATH PRINCIPAL LEVEL``: one call of the ``grant`` verb, silent when it is given."""
    parsed = _operands("grant", words, ("path", "principal", "level"))
    if isinstance(parsed, Ran):
        return parsed
    path, principal, level = parsed
    if level not in _LEVELS:
        return _misuse("grant", f"invalid level: \u2018{level}\u2019")
    target = absolute(cwd, path)
    result = await caller.fs.grant(target, principal, _rung(level), authority=caller.authority)
    return _acted(caller, "grant", result, {target: path})


async def revoke(caller: Caller, words: list[str], cwd: str) -> Ran:
    """``revoke PATH PRINCIPAL``: one call of the ``revoke`` verb; a grant that is not there is no error."""
    parsed = _operands("revoke", words, ("path", "principal"))
    if isinstance(parsed, Ran):
        return parsed
    path, principal = parsed
    target = absolute(cwd, path)
    result = await caller.fs.revoke(target, principal, authority=caller.authority)
    return _acted(caller, "revoke", result, {target: path})


async def grants(caller: Caller, words: list[str], cwd: str) -> Ran:
    """``grants PATH``: one call of the ``grants`` verb, ``PATH PRINCIPAL LEVEL`` a line."""
    parsed = _operands("grants", words, ("path",))
    if isinstance(parsed, Ran):
        return parsed
    (path,) = parsed
    target = absolute(cwd, path)
    result = await caller.fs.grants(target, authority=caller.authority)
    out = _Out("grants")
    if _report(caller, out, "grants", result, {target: path}):
        return out.done(1)
    for row in (result.model_extra or {}).get("grants") or []:
        out.out(f"{row['path_prefix']}\t{row['principal_id']}\t{row['level']}\n")
    return out.done(0)


async def edit(caller: Caller, words: list[str], cwd: str) -> Ran:
    """``edit [-a] PATH OLD NEW``: one call of the ``edit`` verb, silent when it applies."""
    parsed = _getopt("edit", words, flags="a", longs={"all": "a"})
    if isinstance(parsed, Ran):
        return parsed
    options, operands = parsed
    named = _exactly("edit", operands, ("path", "text", "replacement"))
    if isinstance(named, Ran):
        return named
    path, old, new = named
    target = absolute(cwd, path)
    result = await caller.fs.edit(target, old, new, replace_all="a" in options, authority=caller.authority)
    return _acted(caller, "edit", result, {target: path})


async def mkedge(caller: Caller, words: list[str], cwd: str) -> Ran:
    """``mkedge -t TYPE SOURCE TARGET``: one call of the ``mkedge`` verb, silent when it is made."""
    return await _edge(caller, "mkedge", words, cwd)


async def rmedge(caller: Caller, words: list[str], cwd: str) -> Ran:
    """``rmedge -t TYPE SOURCE TARGET``: one call of the ``rmedge`` verb; an edge not there is no error."""
    return await _edge(caller, "rmedge", words, cwd)


PROGRAMS: Final[dict[str, Callable[[Caller, list[str], str], Awaitable[Ran | None]]]] = {
    "grep": grep,
    "find": find,
    "glob": glob,
    "search": search,
    "traverse": traverse,
    "grant": grant,
    "revoke": revoke,
    "grants": grants,
    "edit": edit,
    "mkedge": mkedge,
    "rmedge": rmedge,
}
"""The programs vfs runs itself, by name; a program that answers ``None`` hands its line to the library."""


def absolute(cwd: str, path: str) -> str:
    """``path`` as an absolute vfs path, read from ``cwd`` as the machine reads it."""
    return "/" + posixpath.normpath(posixpath.join(cwd, path)).lstrip("/")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _Out:
    """A program's writes in order, a run of one stream kept as one write."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._writes: list[tuple[int, bytearray]] = []

    def out(self, text: str) -> None:
        self._write(1, text)

    def err(self, text: str) -> None:
        self._write(2, text)

    def done(self, status: int) -> Ran:
        return Ran(tuple((stream, bytes(chunk)) for stream, chunk in self._writes), status)

    def _write(self, stream: int, text: str) -> None:
        if self._writes and self._writes[-1][0] == stream:
            self._writes[-1][1].extend(text.encode())
        else:
            self._writes.append((stream, bytearray(text.encode())))


def _getopt(
    name: str,
    words: list[str],
    *,
    flags: str = "",
    values: str = "",
    longs: Mapping[str, str] | None = None,
) -> tuple[dict[str, list[str]], list[str]] | Ran:
    """Options and operands as GNU getopt reads them, permuted; ``--help`` or a misuse as its ``Ran``.

    Each option maps to its values in order, an empty string for each use of a flag.
    """
    longs = longs or {}
    options: dict[str, list[str]] = {}
    operands: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        if word == "--":
            operands.extend(words[index:])
            break
        if word == "--help":
            return Ran(((1, (USAGE[name] + _HELP[name]).encode()),), 0)
        if not word.startswith("-") or word == "-":
            operands.append(word)
            continue
        pairs: list[tuple[str, str | None]] = []
        if word.startswith("--"):
            long, equals, value = word[2:].partition("=")
            letter = longs.get(long)
            if letter is None:
                return _misuse(name, f"unrecognized option '{word}'")
            if letter in values and not equals:
                if index >= len(words):
                    return _misuse(name, f"option '--{long}' requires an argument")
                value, index = words[index], index + 1
            elif letter not in values and equals:
                return _misuse(name, f"option '--{long}' doesn't allow an argument")
            pairs.append((letter, value if letter in values else None))
        else:
            at = 1
            while at < len(word):
                letter = word[at]
                at += 1
                if letter in values:
                    value = word[at:]
                    if not value:
                        if index >= len(words):
                            return _misuse(name, f"option requires an argument -- '{letter}'")
                        value, index = words[index], index + 1
                    pairs.append((letter, value))
                    break
                if letter not in flags:
                    return _misuse(name, f"invalid option -- '{letter}'")
                pairs.append((letter, None))
        for letter, value in pairs:
            options.setdefault(letter, []).append(value or "")
    return options, operands


def _operands(name: str, words: list[str], wanted: tuple[str, ...]) -> list[str] | Ran:
    """A program of operands only: exactly those ``wanted`` names, or its misuse."""
    parsed = _getopt(name, words)
    if isinstance(parsed, Ran):
        return parsed
    return _exactly(name, parsed[1], wanted)


def _exactly(name: str, operands: list[str], wanted: tuple[str, ...]) -> list[str] | Ran:
    """Exactly the operands ``wanted`` names, or the misuse that says which is missing or extra."""
    if len(operands) < len(wanted):
        return _misuse(name, f"missing {wanted[len(operands)]}")
    if len(operands) > len(wanted):
        return _misuse(name, f"extra operand \u2018{operands[len(wanted)]}\u2019")
    return operands


def _misuse(name: str, reason: str) -> Ran:
    """A misuse as GNU's tools print one: the reason, the usage, where to read more; status 2."""
    text = f"{name}: {reason}\n{USAGE[name]}Try '{name} --help' for more information.\n"
    return Ran(((2, text.encode()),), 2)


def _last(options: dict[str, list[str]], letter: str) -> str | None:
    """The value an option was given last, as getopt's callers read a repeated option."""
    values = options.get(letter)
    return values[-1] if values else None


def _count(value: str | None, *, zero: bool = False) -> int | None | bool:
    """A count option's value: ``None`` when not given, ``False`` when it is no count."""
    if value is None:
        return None
    if not (value.isascii() and value.isdigit()) or (int(value) == 0 and not zero):
        return False
    return int(value)


def _rung(level: str) -> Rung:
    """A level the program already checked, as the verb's type names it."""
    return next(rung for rung in RUNGS if rung == level)


async def _edge(caller: Caller, name: str, words: list[str], cwd: str) -> Ran:
    parsed = _getopt(name, words, values="t", longs={"type": "t"})
    if isinstance(parsed, Ran):
        return parsed
    options, operands = parsed
    if "t" not in options:
        return _misuse(name, "missing edge type; name it with -t")
    edge_type = _last(options, "t") or ""
    named = _exactly(name, operands, ("source", "target"))
    if isinstance(named, Ran):
        return named
    source, target = named
    typed = {absolute(cwd, source): source, absolute(cwd, target): target}
    verb = caller.fs.mkedge if name == "mkedge" else caller.fs.rmedge
    result = await verb(
        source=absolute(cwd, source), target=absolute(cwd, target), edge_type=edge_type, authority=caller.authority
    )
    return _acted(caller, name, result, typed)


def _acted(caller: Caller, name: str, result: Result, typed: dict[str, str]) -> Ran:
    """An action program's end: silent and 0 when the verb acted, its refusal and 1 when not."""
    out = _Out(name)
    return out.done(1 if _report(caller, out, name, result, typed) else 0)


def _report(caller: Caller, out: _Out, name: str, result: Result, typed: dict[str, str]) -> bool:
    """Print each error of ``result`` as ``name: path: reason`` and keep it; whether there was one."""
    failures = [error for error in result.errors if error.severity == "error"]
    for fact in failures:
        caller.keep(fact)
        where = typed.get(str(fact.path), str(fact.path)) if fact.path is not None else None
        out.err(f"{name}: {where}: {_reason(fact)}\n" if where is not None else f"{name}: {_reason(fact)}\n")
    return bool(failures)


def _reason(fact: ResultError) -> str:
    """A refusal as a Unix tool would word it: ``strerror``'s text where there is one, else the detail."""
    if fact.kind == ErrorKind.wrong_kind:
        return "Is a directory" if (fact.data or {}).get("kind") == "directory" else "Not a directory"
    if fact.path is not None and fact.kind in _UNIX_ERRORS:
        return _UNIX_ERRORS[fact.kind]
    contract = KIND_CONTRACTS.get(fact.kind)
    return fact.message.removeprefix(f"{contract.phrase}: " if contract is not None else "")


def _lowered(text: str) -> str:
    """Each character lowered alone, to one character, as ``towlower`` lowers it: the dotted capital I
    to ``i``, and the long s and the dotless i kept, since neither has a lowercase of its own."""
    return "".join(ch.lower()[:1] for ch in text)


def _under(root: str, path: str) -> bool:
    """Whether ``path`` lies strictly beneath ``root``."""
    return path != root and path.startswith(root.rstrip("/") + "/")


def _relative(root: str, path: str) -> str:
    return path[len(root.rstrip("/")) + 1 :]


def _join(base: str, rest: str) -> str:
    """A start of ``find`` and a path beneath it, as the library joins them."""
    return f"{base}{rest}" if base.endswith("/") else f"{base}/{rest}"
