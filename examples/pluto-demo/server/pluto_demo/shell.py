"""The shell: bare unix names over the vfs verbs, one parser for people and agents.

A command line comes in as text; it goes out as rendered text and the
``Result`` behind it. The grammar is the one an agent already knows from
its training: ``ls``, ``tree``, ``cat``, ``find``, ``grep`` with ripgrep's
flags, plus the three verbs a file system never had: ``glean`` (what it
means), ``graph`` (how it connects) and ``grant`` (who may see it).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from vfs.results.render import render_result

if TYPE_CHECKING:
    from vfs.results import Result
    from vfs.session import Session

Verb = Literal[
    "ls",
    "tree",
    "cat",
    "find",
    "grep",
    "glean",
    "graph",
    "write",
    "edit",
    "mkdir",
    "rm",
    "link",
    "grant",
    "revoke",
    "grants",
    "whoami",
    "su",
    "help",
]

HELP = """Halyard workspace shell. Every verb runs through the same kernel, as the principal you are signed in as.

  ls [path]                       list a directory
  tree [path] [-L depth]          draw the tree
  cat <path>                      read a file
  find <pattern> [path]           match names and structure, e.g. find '**/*.md' /meetings
  grep [-i] [-F] [-w] [-C n] [-c] <pattern> [path...]
                                  match content, ripgrep style
  glean [-n k] <query> [path]     ranked search by meaning: lexical, vector and graph legs fused
  graph <in|out|around> <path> [-d depth]
                                  walk the typed edges between files
  write <path> <text>             create or replace a file
  edit <path> <old> <new>         replace text in a file
  mkdir [-p] <path>               make a directory
  rm <path>                       move a file to the trash
  link <source> <target> <type>   add a typed edge
  grant <path> <principal> <level> give list, read, add, contribute or read_write at a path
  revoke <path> <principal>       take a grant back
  grants <path>                   show who holds what at a path
  whoami                          the signed-in principal
  su <principal>                  sign in as someone else: clay, sam
"""

GRAPH_METHODS = {"in": "inbound", "out": "outbound", "around": "neighborhood", "meet": "meet"}


@dataclass
class ShellOutput:
    verb: str
    ok: bool
    output: str
    paths: list[str] = field(default_factory=list)
    switched_to: str | None = None
    result: Result | None = None


class ParseError(Exception):
    """A command line the grammar does not accept; the message is the shell's answer."""


# ---------------------------------------------------------------------------
# Running a line
# ---------------------------------------------------------------------------


async def run_line(session: Session, line: str, *, principal: str) -> ShellOutput:
    """Parse *line* and run it as *session*; never raises for a bad line."""
    try:
        words = shlex.split(line)
    except ValueError as exc:
        return ShellOutput("help", False, f"ERROR could not parse the line: {exc}")
    if not words:
        return ShellOutput("help", True, "")
    verb, args = words[0], words[1:]
    try:
        return await _dispatch(session, verb, args, principal=principal)
    except ParseError as exc:
        return ShellOutput(verb if verb in VERBS else "help", False, f"ERROR {exc}")


VERBS: frozenset[str] = frozenset(
    (
        "ls",
        "tree",
        "cat",
        "find",
        "grep",
        "glean",
        "graph",
        "write",
        "edit",
        "mkdir",
        "rm",
        "link",
        "grant",
        "revoke",
        "grants",
        "whoami",
        "su",
        "help",
    )
)


async def _dispatch(session: Session, verb: str, args: list[str], *, principal: str) -> ShellOutput:
    if verb == "help":
        return ShellOutput("help", True, HELP)
    if verb == "whoami":
        return ShellOutput("whoami", True, principal)
    if verb == "su":
        if len(args) != 1:
            raise ParseError("usage: su <principal>")
        return ShellOutput("su", True, f"signed in as {args[0]}", switched_to=args[0])
    if verb == "ls":
        return _finish("ls", await session.ls(_one_path(args, default="/")))
    if verb == "tree":
        flags, rest = _take_flags(args, {"-L": 1})
        depth = int(flags["-L"][0]) if "-L" in flags else None
        return _finish("tree", await session.tree(_one_path(rest, default="/"), depth))
    if verb == "cat":
        return _finish("cat", await session.read(_one_path(args)))
    if verb == "find":
        if not args:
            raise ParseError("usage: find <pattern> [path]")
        pattern, *paths = args
        return _finish("find", await session.glob(pattern, paths=tuple(paths)))
    if verb == "grep":
        return await _grep(session, args)
    if verb == "glean":
        flags, rest = _take_flags(args, {"-n": 1})
        if not rest:
            raise ParseError("usage: glean [-n k] <query> [path]")
        query, *paths = rest
        limit = int(flags["-n"][0]) if "-n" in flags else 8
        return _finish("glean", await session.glean(query, limit=limit, paths=tuple(paths)))
    if verb == "graph":
        flags, rest = _take_flags(args, {"-d": 1})
        if len(rest) < 2 or rest[0] not in GRAPH_METHODS:
            raise ParseError("usage: graph <in|out|around> <path> [-d depth]")
        depth = int(flags["-d"][0]) if "-d" in flags else 2
        return _finish("graph", await session.graph(GRAPH_METHODS[rest[0]], rest[1], depth=depth))
    if verb == "write":
        if len(args) != 2:
            raise ParseError("usage: write <path> <text>")
        return _finish("write", await session.write(path=args[0], content=args[1], parents=True))
    if verb == "edit":
        if len(args) != 3:
            raise ParseError("usage: edit <path> <old> <new>")
        return _finish("edit", await session.edit(args[0], args[1], args[2]))
    if verb == "mkdir":
        flags, rest = _take_flags(args, {"-p": 0})
        return _finish("mkdir", await session.mkdir(_one_path(rest), parents="-p" in flags, exist_ok="-p" in flags))
    if verb == "rm":
        return _finish("rm", await session.delete(_one_path(args)))
    if verb == "link":
        if len(args) != 3:
            raise ParseError("usage: link <source> <target> <type>")
        return _finish(
            "link", await session.mkedge(source=args[0], target=args[1], edge_type=args[2], provenance="user")
        )
    if verb == "grant":
        if len(args) != 3:
            raise ParseError("usage: grant <path> <principal> <level>")
        return _finish("grant", await session.grant(args[0], args[1], args[2]))  # ty: ignore[invalid-argument-type]
    if verb == "revoke":
        if len(args) != 2:
            raise ParseError("usage: revoke <path> <principal>")
        return _finish("revoke", await session.revoke(args[0], args[1]))
    if verb == "grants":
        return _finish("grants", await session.grants(_one_path(args, default="/")))
    raise ParseError(f"{verb}: not a verb here. Type help.")


async def _grep(session: Session, args: list[str]) -> ShellOutput:
    flags, rest = _take_flags(args, {"-i": 0, "-F": 0, "-w": 0, "-C": 1, "-c": 0, "-l": 0, "-m": 1})
    if not rest:
        raise ParseError("usage: grep [-i] [-F] [-w] [-C n] <pattern> [path...]")
    pattern, *paths = rest
    context = int(flags["-C"][0]) if "-C" in flags else 0
    mode: Literal["lines", "files", "count"] = "count" if "-c" in flags else "files" if "-l" in flags else "lines"
    result = await session.grep(
        pattern,
        paths=tuple(paths),
        case_mode="insensitive" if "-i" in flags else "sensitive",
        fixed_strings="-F" in flags,
        word_regexp="-w" in flags,
        before_context=context,
        after_context=context,
        output_mode=mode,
        max_count=int(flags["-m"][0]) if "-m" in flags else None,
    )
    return _finish("grep", result)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _finish(verb: str, result: Result) -> ShellOutput:
    text = render_result(result).rstrip()
    if result.success and not text:
        text = "(no matches)" if verb in {"find", "grep", "glean"} else "(empty)"
    return ShellOutput(verb, result.success, text, paths=[str(p) for p in result.paths], result=result)


def _one_path(args: list[str], *, default: str | None = None) -> str:
    if len(args) > 1:
        raise ParseError("expected one path")
    if args:
        return args[0]
    if default is None:
        raise ParseError("expected a path")
    return default


def _take_flags(args: list[str], spec: dict[str, int]) -> tuple[dict[str, list[str]], list[str]]:
    """Split *args* into the flags *spec* names (flag → arity) and the rest, in order."""
    flags: dict[str, list[str]] = {}
    rest: list[str] = []
    i = 0
    while i < len(args):
        word = args[i]
        if word in spec:
            arity = spec[word]
            values = args[i + 1 : i + 1 + arity]
            if len(values) < arity:
                raise ParseError(f"{word} needs a value")
            flags[word] = values
            i += 1 + arity
        elif word.startswith("-") and len(word) > 1 and word[1:].isalpha() and all("-" + c in spec for c in word[1:]):
            for c in word[1:]:
                flags["-" + c] = []
            i += 1
        else:
            rest.append(word)
            i += 1
    return flags, rest
