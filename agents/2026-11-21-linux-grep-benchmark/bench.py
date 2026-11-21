"""Replay a Claude Code session's grep and glob commands through system tools, ripgrep and vfs.

The session's Bash calls are read from its transcript. Each call that ran in the Linux checkout is split into
stages: ``grep -n PAT FILES`` (with an optional ``| head``), ``sed -n A,Bp FILE`` (with an optional
``| grep -n``), and ``ls DIR`` (with an optional ``| grep -E``). Each stage then runs three ways:

- ``generic``: the macOS system tools (``/usr/bin/grep``, ``/usr/bin/sed``, ``/bin/ls``, ``/usr/bin/head``).
- ``rg``: the same pipeline with ``rg`` in place of every ``grep``. ``sed``, ``ls`` and ``head`` stay.
- ``vfs``: the calls an agent makes on an ``AsyncVirtualFileSystem`` over the indexed SQLite database:
  ``glob`` for a shell glob, ``grep`` with the files as ``paths``, ``read`` for ``sed`` with the line range cut
  out in Python, and ``ls``. One long-lived process; no process spawn per call.

Each stage's output is reduced to a canonical set of lines, so the three tools are checked to agree.

A second suite asks each grep pattern of the session over the whole tree (``grep -rnI``, ``rg -n``, ``vfs grep``
with no paths) and two repo-wide name globs (``find``, ``rg --files -g``, ``vfs glob``).

    uv run python agents/2026-11-21-linux-grep-benchmark/bench.py --session S.jsonl --root ~/Git/Repos/linux \
        --db linux.db --out results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shlex
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from glob import glob
from pathlib import Path as FsPath
from typing import Any

from vfs import AsyncVirtualFileSystem, DatabaseStorage

GENERIC = {"grep": "/usr/bin/grep", "sed": "/usr/bin/sed", "ls": "/bin/ls", "head": "/usr/bin/head"}
NAME_ALTERNATIVES = ("path-lookup", "vfs", "locking", "porting", "mount_api")


# ---------------------------------------------------------------------------
# The workload: stages parsed from the transcript
# ---------------------------------------------------------------------------


@dataclass
class Stage:
    """One pipeline of a session command, in the shape the three runners share."""

    command: int
    source: str
    kind: str  # "grep" | "sed" | "ls"
    files: list[str] = field(default_factory=list)
    shell_globs: list[str] = field(default_factory=list)
    pattern: str | None = None  # BRE for grep, BRE for sed's pipe, ERE for ls's pipe
    line_range: tuple[int, int] | None = None
    head: int | None = None


def session_commands(transcript: FsPath, root: FsPath) -> list[str]:
    """The Bash commands that ran in ``root``, once each, in transcript order, with the ``cd`` stripped."""
    prefix = f"cd {root} && "
    seen: list[str] = []
    for line in transcript.read_text().splitlines():
        message = json.loads(line).get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        for block in message["content"]:
            if block.get("type") == "tool_use" and block.get("name") == "Bash":
                command = block["input"]["command"]
                if command.startswith(prefix) and command[len(prefix) :] not in seen:
                    seen.append(command[len(prefix) :])
    return seen


def parse_stages(index: int, command: str, root: FsPath) -> list[Stage]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";|>")
    lexer.whitespace_split = True
    tokens = list(lexer)
    stages: list[Stage] = []
    for sequence in split(tokens, ";"):
        sequence = drop_redirects(sequence)
        pipeline = split(sequence, "|")
        stage = parse_pipeline(index, pipeline, root)
        if stage is not None:
            stages.append(stage)
    return stages


def split(tokens: list[str], separator: str) -> list[list[str]]:
    groups: list[list[str]] = [[]]
    for token in tokens:
        if token == separator:
            groups.append([])
        else:
            groups[-1].append(token)
    return [group for group in groups if group]


def drop_redirects(tokens: list[str]) -> list[str]:
    kept: list[str] = []
    skip = 0
    for position, token in enumerate(tokens):
        if skip:
            skip -= 1
            continue
        if token == "2" and position + 1 < len(tokens) and tokens[position + 1] == ">":
            skip = 2
            continue
        kept.append(token)
    return kept


def parse_pipeline(index: int, pipeline: list[list[str]], root: FsPath) -> Stage | None:
    first, *rest = pipeline
    source = " | ".join(shlex.join(part) for part in pipeline)
    program = first[0]
    if program == "echo":
        return None
    if program == "grep":
        assert first[1] == "-n", first
        pattern, *arguments = first[2:]
        files: list[str] = []
        shell_globs: list[str] = []
        for argument in arguments:
            if "*" in argument:
                shell_globs.append(argument)
                files.extend(sorted(FsPath(match).relative_to(root).as_posix() for match in glob(str(root / argument))))
            else:
                files.append(argument)
        stage = Stage(index, source, "grep", files=files, shell_globs=shell_globs, pattern=pattern)
        for part in rest:
            assert part[0] == "head", part
            stage.head = int(part[1].lstrip("-")) if len(part) > 1 else 10
        return stage
    if program == "sed":
        assert first[1] == "-n", first
        start, end = first[2].removesuffix("p").split(",")
        stage = Stage(index, source, "sed", files=[first[3]], line_range=(int(start), int(end)))
        for part in rest:
            assert part[:2] == ["grep", "-n"], part
            stage.pattern = part[2]
        return stage
    if program == "ls":
        stage = Stage(index, source, "ls", files=[first[1].rstrip("/")])
        for part in rest:
            assert part[:2] == ["grep", "-E"], part
            stage.pattern = part[2]
        return stage
    raise ValueError(f"unhandled stage: {source}")


def bre_to_ere(pattern: str) -> str:
    """A basic regular expression as grep reads it, rewritten for ripgrep's and vfs's syntax."""
    out: list[str] = []
    position = 0
    while position < len(pattern):
        char = pattern[position]
        if char == "\\" and position + 1 < len(pattern):
            following = pattern[position + 1]
            out.append("|" if following == "|" else "\\" + following)
            position += 2
            continue
        out.append("\\" + char if char in "{}()+?|" else char)
        position += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def run_pipeline(argvs: list[list[str]], cwd: FsPath) -> tuple[float, str]:
    """Run a pipeline of processes, as a shell would, and return the wall time and the last stage's output."""
    started = time.perf_counter()
    processes: list[subprocess.Popen[bytes]] = []
    upstream = None
    for argv in argvs:
        process = subprocess.Popen(argv, cwd=cwd, stdin=upstream, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if upstream is not None:
            upstream.close()
        upstream = process.stdout
        processes.append(process)
    output, _ = processes[-1].communicate()
    for process in processes[:-1]:
        process.wait()
    return time.perf_counter() - started, output.decode("utf-8", "replace")


def shell_argvs(stage: Stage, flavour: str) -> list[list[str]]:
    rg = flavour == "rg"

    def grep_argv(flags: list[str], pattern: str, files: list[str]) -> list[str]:
        if rg:
            return ["rg", "--color=never", "--no-heading", *flags, "-e", bre_to_ere(pattern), *files]
        return [GENERIC["grep"], *flags, "-e", pattern, *files]

    if stage.kind == "grep":
        assert stage.pattern is not None
        argvs = [grep_argv(["-n"], stage.pattern, stage.files)]
        if stage.head is not None:
            argvs.append([GENERIC["head"], f"-{stage.head}"])
        return argvs
    if stage.kind == "sed":
        assert stage.line_range is not None
        start, end = stage.line_range
        argvs = [[GENERIC["sed"], "-n", f"{start},{end}p", stage.files[0]]]
        if stage.pattern is not None:
            argvs.append(grep_argv(["-n"], stage.pattern, []))
        return argvs
    argvs = [[GENERIC["ls"], stage.files[0]]]
    if stage.pattern is not None:
        # The pattern is already extended syntax, which both greps read under -E.
        argvs.append(["rg", "--color=never", "-e", stage.pattern] if rg else [GENERIC["grep"], "-E", stage.pattern])
    return argvs


async def run_vfs(kernel: AsyncVirtualFileSystem, stage: Stage) -> tuple[float, list[str], list[str]]:
    """One stage through the vfs verbs; returns the wall time, the canonical lines, and any errors or warnings."""
    notes: list[str] = []
    started = time.perf_counter()
    if stage.kind == "grep":
        assert stage.pattern is not None
        files = [name for name in stage.files if not any(glob_matches(name, g) for g in stage.shell_globs)]
        for shell_glob in stage.shell_globs:
            globbed = await kernel.glob("/" + shell_glob, kind="file")
            notes.extend(describe(error) for error in globbed.errors)
            files.extend(str(row.path).lstrip("/") for row in globbed.observations)
        result = await kernel.grep(bre_to_ere(stage.pattern), paths=tuple("/" + name for name in files))
        notes.extend(describe(error) for error in result.errors)
        order = {name: position for position, name in enumerate(stage.files)}
        hits: list[tuple[int, int, str]] = []
        for row in result.observations:
            name = str(row.path).lstrip("/")
            for match in row.matches or []:
                assert match.match is not None
                text = (match.content or "").rstrip("\n")
                line = f"{name}:{match.match}:{text}" if len(stage.files) > 1 else f"{match.match}:{text}"
                hits.append((order.get(name, len(order)), match.match, line))
        lines = [line for _, _, line in sorted(hits)]
        if stage.head is not None:
            lines = lines[: stage.head]
    elif stage.kind == "sed":
        assert stage.line_range is not None
        result = await kernel.read("/" + stage.files[0])
        notes.extend(describe(error) for error in result.errors)
        start, end = stage.line_range
        body = (result.observations[0].content or "").split("\n")[start - 1 : end]
        if stage.pattern is not None:
            matcher = re.compile(bre_to_ere(stage.pattern))
            lines = [f"{number}:{text}" for number, text in enumerate(body, 1) if matcher.search(text)]
        else:
            lines = body
    else:
        result = await kernel.ls("/" + stage.files[0])
        notes.extend(describe(error) for error in result.errors)
        names = sorted(str(row.path).rsplit("/", 1)[-1] for row in result.observations)
        if stage.pattern is not None:
            matcher = re.compile(stage.pattern)
            names = [name for name in names if matcher.search(name)]
        lines = names
    return time.perf_counter() - started, lines, notes


def glob_matches(name: str, shell_glob: str) -> bool:
    return FsPath(name).match(shell_glob)


def describe(error: Any) -> str:
    return f"{getattr(error, 'severity', '?')}:{getattr(error, 'kind', '?')}:{getattr(error, 'message', error)}"[:300]


# ---------------------------------------------------------------------------
# Repo-wide suite
# ---------------------------------------------------------------------------


def repo_grep_argv(flavour: str, pattern: str) -> list[str]:
    if flavour == "rg":
        return ["rg", "--color=never", "--no-heading", "-n", "-e", bre_to_ere(pattern)]
    return [GENERIC["grep"], "-rnI", "--exclude-dir=.git", "-e", pattern, "."]


def hit_keys(output: str) -> set[str]:
    keys: set[str] = set()
    for line in output.splitlines():
        found = re.match(r"^(?:\./)?(.*?):(\d+):", line)
        if found:
            keys.add(f"{found.group(1)}:{found.group(2)}")
    return keys


async def vfs_repo_grep(kernel: AsyncVirtualFileSystem, pattern: str) -> tuple[float, set[str], list[str]]:
    started = time.perf_counter()
    result = await kernel.grep(bre_to_ere(pattern))
    elapsed = time.perf_counter() - started
    keys = {f"{str(row.path).lstrip('/')}:{match.match}" for row in result.observations for match in row.matches or []}
    return elapsed, keys, [describe(error) for error in result.errors]


GLOB_CASES = {
    "names matching *{path-lookup,vfs,locking,porting,mount_api}*": {
        "generic": [
            "/usr/bin/find", ".", "-path", "./.git", "-prune", "-o", "-type", "f", "(",
            *[arg for alt in NAME_ALTERNATIVES for arg in ("-name", f"*{alt}*", "-o")][:-1],
            ")", "-print",
        ],
        "rg": ["rg", "--files", "-g", "*{" + ",".join(NAME_ALTERNATIVES) + "}*"],
        "vfs": "*{" + ",".join(NAME_ALTERNATIVES) + "}*",
    },
    "every header, **/*.h": {
        "generic": ["/usr/bin/find", ".", "-path", "./.git", "-prune", "-o", "-type", "f", "-name", "*.h", "-print"],
        "rg": ["rg", "--files", "-g", "*.h"],
        "vfs": "**/*.h",
    },
}  # fmt: skip


def path_keys(output: str) -> set[str]:
    return {line.removeprefix("./") for line in output.splitlines() if line}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def summary(times: list[float]) -> dict[str, float]:
    return {"median_ms": statistics.median(times) * 1000, "min_ms": min(times) * 1000, "runs": len(times)}


async def bench(args: argparse.Namespace) -> dict[str, Any]:
    root: FsPath = args.root.expanduser()
    commands = session_commands(args.session, root)
    stages = [stage for index, command in enumerate(commands) for stage in parse_stages(index, command, root)]
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{args.db}")
    kernel = AsyncVirtualFileSystem(storage=storage)
    report: dict[str, Any] = {"commands": commands, "stages": [], "repo_grep": [], "repo_glob": []}
    try:
        first = time.perf_counter()
        warm = await kernel.stat("/fs")
        report["vfs_first_call_ms"] = (time.perf_counter() - first) * 1000
        assert warm.success, warm.errors

        for stage in stages:
            row: dict[str, Any] = {"command": stage.command, "source": stage.source, "kind": stage.kind}
            outputs: dict[str, list[str]] = {}
            for flavour in ("generic", "rg"):
                argvs = shell_argvs(stage, flavour)
                times = []
                for repetition in range(args.reps + 1):
                    elapsed, output = run_pipeline(argvs, root)
                    if repetition:
                        times.append(elapsed)
                outputs[flavour] = output.splitlines()
                row[flavour] = summary(times) | {"argv": [shlex.join(argv) for argv in argvs]}
            times = []
            notes: list[str] = []
            for repetition in range(args.reps + 1):
                elapsed, lines, notes = await run_vfs(kernel, stage)
                if repetition:
                    times.append(elapsed)
                else:
                    row["vfs_first_ms"] = elapsed * 1000
            outputs["vfs"] = lines
            row["vfs"] = summary(times) | {"notes": notes}
            row["lines"] = {flavour: len(found) for flavour, found in outputs.items()}
            row["agree"] = {
                "rg": sorted(outputs["rg"]) == sorted(outputs["generic"]),
                "vfs": sorted(outputs["vfs"]) == sorted(outputs["generic"]),
            }
            if not row["agree"]["vfs"] or not row["agree"]["rg"]:
                row["diff"] = {
                    "generic_only": sorted(set(outputs["generic"]) - set(outputs["vfs"]))[:10],
                    "vfs_only": sorted(set(outputs["vfs"]) - set(outputs["generic"]))[:10],
                    "rg_vs_generic": sorted(set(outputs["rg"]) ^ set(outputs["generic"]))[:10],
                }
            report["stages"].append(row)
            print(f"[stage] {stage.source[:90]} agree={row['agree']}", flush=True)

        if args.repo_wide:
            patterns = list(dict.fromkeys(stage.pattern for stage in stages if stage.kind == "grep" and stage.pattern))
            for pattern in patterns:
                row = {"pattern": pattern, "ere": bre_to_ere(pattern)}
                keys: dict[str, set[str]] = {}
                for flavour, reps in (("generic", args.generic_repo_reps), ("rg", args.reps_repo)):
                    times = []
                    for _ in range(reps):
                        elapsed, output = run_pipeline([repo_grep_argv(flavour, pattern)], root)
                        times.append(elapsed)
                    keys[flavour] = hit_keys(output)
                    row[flavour] = summary(times)
                times = []
                notes = []
                for repetition in range(args.reps_repo + 1):
                    elapsed, found, notes = await vfs_repo_grep(kernel, pattern)
                    if repetition:
                        times.append(elapsed)
                    else:
                        row["vfs_first_ms"] = elapsed * 1000
                keys["vfs"] = found
                row["vfs"] = summary(times) | {"notes": notes}
                row["hits"] = {flavour: len(found) for flavour, found in keys.items()}
                row["files"] = {name: len({key.rsplit(":", 1)[0] for key in found}) for name, found in keys.items()}
                row["disagree"] = {
                    "generic_minus_rg": sorted(keys["generic"] - keys["rg"])[:5],
                    "rg_minus_generic": sorted(keys["rg"] - keys["generic"])[:5],
                    "rg_minus_vfs": sorted(keys["rg"] - keys["vfs"])[:5],
                    "vfs_minus_rg": sorted(keys["vfs"] - keys["rg"])[:5],
                }
                report["repo_grep"].append(row)
                print(f"[repo grep] {pattern[:60]} {row['hits']} {row['generic']['median_ms']:.0f}/"
                      f"{row['rg']['median_ms']:.0f}/{row['vfs']['median_ms']:.0f} ms", flush=True)  # fmt: skip
            for label, case in GLOB_CASES.items():
                row = {"case": label}
                found_sets: dict[str, set[str]] = {}
                for flavour in ("generic", "rg"):
                    times = []
                    for repetition in range(args.reps_repo + 1):
                        elapsed, output = run_pipeline([case[flavour]], root)
                        if repetition:
                            times.append(elapsed)
                    found_sets[flavour] = path_keys(output)
                    row[flavour] = summary(times) | {"argv": shlex.join(case[flavour])}
                times = []
                for repetition in range(args.reps_repo + 1):
                    started = time.perf_counter()
                    result = await kernel.glob(case["vfs"], kind="file")
                    if repetition:
                        times.append(time.perf_counter() - started)
                found_sets["vfs"] = {str(r.path).lstrip("/") for r in result.observations}
                row["vfs"] = summary(times) | {"call": f"glob({case['vfs']!r}, kind='file')",
                                               "notes": [describe(e) for e in result.errors]}  # fmt: skip
                row["count"] = {flavour: len(found) for flavour, found in found_sets.items()}
                row["vfs_minus_rg"] = sorted(found_sets["vfs"] - found_sets["rg"])[:5]
                row["rg_minus_vfs"] = sorted(found_sets["rg"] - found_sets["vfs"])[:5]
                report["repo_glob"].append(row)
                print(f"[repo glob] {label} {row['count']}", flush=True)
    finally:
        await kernel.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=FsPath, required=True)
    parser.add_argument("--root", type=FsPath, required=True)
    parser.add_argument("--db", type=FsPath, required=True)
    parser.add_argument("--out", type=FsPath, required=True)
    parser.add_argument("--reps", type=int, default=5, help="timed runs per session stage, after one warm-up")
    parser.add_argument("--reps-repo", type=int, default=3, help="timed runs per repo-wide rg and vfs query")
    parser.add_argument("--generic-repo-reps", type=int, default=1, help="timed runs per repo-wide system grep")
    parser.add_argument("--repo-wide", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(bench(args))
    args.out.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
