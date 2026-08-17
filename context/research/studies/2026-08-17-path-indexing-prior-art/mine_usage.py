#!/usr/bin/env python3
"""Mine Claude Code session JSONL files for file-search tool usage statistics.

Scans ~/.claude/projects/**/*.jsonl (recursively — sessions nest subagent
logs in subdirectories) and extracts every tool_use block. Primary targets
are the dedicated "Grep" and "Glob" tools; on this machine the harness has
no such tools (zero calls), so the script also parses Bash tool_use
commands for rg/grep/egrep/fgrep/find/fd invocations and reports the same
aggregates over those: scoping (glob/path/type), glob-shape taxonomy,
directory-scope depth, literal-vs-regex patterns, case-insensitivity, and
co-occurrence. Read-only; reports only aggregates and search-pattern
strings, with home-directory prefixes stripped from scope listings.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from collections import Counter
from pathlib import Path

HOME = str(Path.home())
PROJECTS = Path(HOME) / ".claude" / "projects"

REGEX_META = set(r".*+?[](){}|^$\\")

SEARCH_TOOLS = {"rg", "grep", "egrep", "fgrep", "ggrep", "ugrep", "zgrep", "fd", "find"}
PUNCT_CHARS = ";|&<>()"
KEYWORD_BREAKS = {"then", "do", "else", "elif", "fi", "done", "esac", "{", "}"}

# rg flags that consume a following value (subset that matters for parsing).
RG_VALUE_FLAGS = {
    "-g", "--glob", "--iglob", "-t", "--type", "-T", "--type-not", "-A", "-B", "-C",
    "-m", "--max-count", "--max-depth", "--max-filesize", "-e", "--regexp",
    "-f", "--file", "--sort", "--sortr", "-E", "--encoding", "--color",
    "--colors", "-j", "--threads", "--pre", "--pre-glob", "-r", "--replace",
    "--context-separator", "--field-match-separator", "--path-separator",
}
GREP_VALUE_FLAGS = {
    "-e", "--regexp", "-f", "--file", "-m", "--max-count", "-A", "-B", "-C",
    "--include", "--exclude", "--exclude-dir", "--include-dir", "--color",
    "-d", "--directories", "-D", "--devices", "--label",
}
FIND_GLOB_PRIMARIES = {"-name", "-iname"}
FIND_PATH_PRIMARIES = {"-path", "-ipath", "-wholename", "-iwholename"}
FIND_VALUE_PRIMARIES = FIND_GLOB_PRIMARIES | FIND_PATH_PRIMARIES | {
    "-type", "-maxdepth", "-mindepth", "-newer", "-mtime", "-mmin", "-size",
    "-perm", "-user", "-group", "-exec", "-execdir", "-printf", "-fprintf",
}
FD_VALUE_FLAGS = {
    "-e", "--extension", "-t", "--type", "-g", "--glob", "-E", "--exclude",
    "-d", "--max-depth", "--min-depth", "--maxdepth", "-x", "--exec",
    "-X", "--exec-batch", "--search-path", "--base-directory",
}


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def is_dirlike(path_str: str) -> str:
    """Classify a scope path as 'dir', 'file', or 'unknown'."""
    p = path_str.rstrip()
    if not p:
        return "unknown"
    try:
        if os.path.isdir(os.path.expanduser(p)):
            return "dir"
        if os.path.isfile(os.path.expanduser(p)):
            return "file"
    except OSError:
        pass
    if p.endswith("/") or p in (".", "..", "~"):
        return "dir"
    base = os.path.basename(p)
    if "." in base and not base.startswith(".") and 1 <= len(base.rsplit(".", 1)[1]) <= 10:
        return "file"
    return "dir"


def classify_glob(g: str) -> str:
    """Bucket a glob-ish pattern into a shape taxonomy (first match wins)."""
    g = g.strip().lstrip("!")  # negated globs classify by their body
    if not g:
        return "other"
    if re.fullmatch(r"\*\*?(/\*{1,2})*/?", g):  # *, **, **/*, **/**
        return "recursive-any"
    if "/" in g:
        return "directory-scoped path glob"
    if re.search(r"\[[^\]]+\]", g):
        return "character class"
    if re.fullmatch(r"\*\.(\{[^}]+\}|[A-Za-z0-9_+\-]+)", g):
        return "bare extension glob (brace)" if "{" in g else "bare extension glob"
    if "{" in g and "}" in g:
        return "brace group (non-extension)"
    if "*" in g or "?" in g:
        return "stem wildcard"
    return "basename literal"


def strip_home(p: str) -> str:
    """Reduce an absolute personal path to a project-relative-ish form."""
    p = p.replace(HOME, "~") if p.startswith(HOME) else p
    if p.startswith("~"):
        parts = [s for s in p.split("/") if s]
        # Drop ~ and generic code-dir prefixes down to the project segment.
        while parts and parts[0].lower() in ("~", "git", "repos", "repositories", "projects", "src", "code"):
            parts.pop(0)
        return "/".join(parts) or "~"
    return p


def depth_of(p: str) -> int:
    return len([s for s in p.strip("/").split("/") if s not in ("", ".")])


# ---------------------------------------------------------------------------
# Bash command parsing
# ---------------------------------------------------------------------------

def tokenize_lines(command: str):
    """Yield token lists, one per logical shell line, punctuation-aware."""
    command = command.replace("\\\n", " ")
    for line in command.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            lex = shlex.shlex(line, posix=True, punctuation_chars=PUNCT_CHARS)
            lex.whitespace_split = True
            yield list(lex)
        except ValueError:
            continue  # unbalanced quotes (heredoc bodies etc.)


def split_segments(tokens: list[str]) -> list[tuple[str, list[str]]]:
    """Split tokens into (preceding-operator, segment) pipeline pieces."""
    segs: list[tuple[str, list[str]]] = [("", [])]
    skip_next = False
    for t in tokens:
        if skip_next:
            skip_next = False
            continue
        if t and all(c in PUNCT_CHARS for c in t):
            if ">" in t or "<" in t:
                # Redirection: drop its target and any glued fd number.
                skip_next = True
                if segs[-1][1] and re.fullmatch(r"\d+", segs[-1][1][-1]):
                    segs[-1][1].pop()
                segs.append((">", []))
            else:
                segs.append(("|" if t in ("|", "|&") else t, []))
        elif t in KEYWORD_BREAKS:
            segs.append((";", []))
        else:
            segs[-1][1].append(t)
    return [(op, s) for op, s in segs if s]


def parse_search_segment(tokens: list[str]) -> dict | None:
    """Parse one pipeline segment; return a call record if it is a search tool."""
    # Skip env-var prefixes, `command`, `xargs [flags]`, `sudo`, `timeout N`.
    i = 0
    via_xargs = False
    while i < len(tokens):
        t = tokens[i]
        if "=" in t and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*=.*", t):
            i += 1
        elif t in ("command", "sudo", "noglob", "nice", "builtin"):
            i += 1
        elif t == "timeout" and i + 1 < len(tokens):
            i += 2
        elif t == "xargs":
            via_xargs = True
            i += 1
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 2 if tokens[i] in ("-I", "-n", "-P", "-d", "-s") else 1
        else:
            break
    if i >= len(tokens):
        return None
    tool = os.path.basename(tokens[i])
    if tool == "git" and i + 1 < len(tokens) and tokens[i + 1] == "grep":
        tool = "grep"
        i += 1
    if tool not in SEARCH_TOOLS:
        return None
    args = tokens[i + 1:]
    if tool == "find":
        rec = parse_find(args)
    elif tool == "fd":
        rec = parse_fd(args)
    else:
        rec = parse_grep_like(tool, args)
    rec["via_xargs"] = via_xargs
    return rec


def parse_grep_like(tool: str, args: list[str]) -> dict:
    rec = {"tool": "rg" if tool == "rg" else "grep", "globs": [], "types": [],
           "paths": [], "pattern": None, "ci": False, "fixed": False,
           "files_mode": False, "output": "content", "recursive": tool == "rg"}
    value_flags = RG_VALUE_FLAGS if tool == "rg" else GREP_VALUE_FLAGS
    positionals: list[str] = []
    j = 0
    while j < len(args):
        a = args[j]
        if a == "--":
            positionals.extend(args[j + 1:])
            break
        if a.startswith("--") and "=" in a:
            flag, val = a.split("=", 1)
            if flag in ("--glob", "--iglob", "--include"):
                rec["globs"].append(val)
            elif flag in ("--type",):
                rec["types"].append(val)
            elif flag in ("--regexp",):
                rec["pattern"] = rec["pattern"] or val
            elif flag == "--ignore-case":
                rec["ci"] = True
            elif flag == "--fixed-strings":
                rec["fixed"] = True
        elif a in ("-g", "--glob", "--iglob", "--include"):
            if j + 1 < len(args):
                rec["globs"].append(args[j + 1]); j += 1
        elif a in ("-t", "--type"):
            if j + 1 < len(args):
                rec["types"].append(args[j + 1]); j += 1
        elif a in ("-e", "--regexp"):
            if j + 1 < len(args):
                if rec["pattern"] is None:
                    rec["pattern"] = args[j + 1]
                j += 1
        elif a in ("-i", "--ignore-case"):
            rec["ci"] = True
        elif a in ("-F", "--fixed-strings"):
            rec["fixed"] = True
        elif a in ("-r", "-R", "--recursive"):
            rec["recursive"] = True
        elif a in ("-q", "--quiet", "--silent"):
            rec["output"] = "quiet"
        elif a in ("-l", "--files-with-matches", "-L", "--files-without-match", "--files", "-c", "--count"):
            rec["files_mode"] = True
            rec["output"] = "count" if a in ("-c", "--count") else "files"
        elif a.startswith("-g") and len(a) > 2 and tool == "rg":
            rec["globs"].append(a[2:])  # glued form -g'*.py'
        elif a.startswith("-t") and len(a) > 2 and tool == "rg":
            rec["types"].append(a[2:])
        elif a in value_flags:
            j += 1  # skip the value
        elif re.fullmatch(r"-[A-Za-z]+\d*", a):
            # Combined short flags like -rin, -lF, -A5.
            flags = a[1:]
            rec["ci"] = rec["ci"] or "i" in flags
            rec["fixed"] = rec["fixed"] or "F" in flags
            rec["recursive"] = rec["recursive"] or "r" in flags or "R" in flags
            if "q" in flags:
                rec["output"] = "quiet"
            if "l" in flags or "c" in flags:
                rec["files_mode"] = True
                rec["output"] = "files" if "l" in flags else "count"
        elif a.startswith("-") and len(a) > 1:
            pass  # unknown long/odd flag
        else:
            positionals.append(a)
        j += 1
    if positionals:
        if rec["pattern"] is None:
            rec["pattern"] = positionals[0]
            rec["paths"] = positionals[1:]
        else:
            rec["paths"] = positionals
    return rec


def parse_find(args: list[str]) -> dict:
    rec = {"tool": "find", "globs": [], "types": [], "paths": [],
           "pattern": None, "ci": False, "fixed": False,
           "files_mode": True, "output": "files"}
    j = 0
    while j < len(args) and not args[j].startswith("-"):
        rec["paths"].append(args[j]); j += 1
    while j < len(args):
        a = args[j]
        if a in FIND_GLOB_PRIMARIES and j + 1 < len(args):
            rec["globs"].append(args[j + 1])
            rec["ci"] = rec["ci"] or a == "-iname"
            j += 1
        elif a in FIND_PATH_PRIMARIES and j + 1 < len(args):
            rec["globs"].append(args[j + 1]); j += 1
        elif a == "-type" and j + 1 < len(args):
            rec["types"].append(args[j + 1]); j += 1
        elif a in FIND_VALUE_PRIMARIES and j + 1 < len(args):
            j += 1
        j += 1
    return rec


def parse_fd(args: list[str]) -> dict:
    rec = {"tool": "fd", "globs": [], "types": [], "paths": [],
           "pattern": None, "ci": False, "fixed": False,
           "files_mode": True, "output": "files"}
    positionals: list[str] = []
    glob_mode = False
    j = 0
    while j < len(args):
        a = args[j]
        if a.startswith("--") and "=" in a:
            flag, val = a.split("=", 1)
            if flag in ("--extension",):
                rec["globs"].append(f"*.{val.lstrip('.')}")
            elif flag in ("--glob",):
                glob_mode = True
        elif a in ("-e", "--extension") and j + 1 < len(args):
            rec["globs"].append(f"*.{args[j + 1].lstrip('.')}"); j += 1
        elif a in ("-g", "--glob"):
            glob_mode = True
        elif a in ("-i", "--ignore-case"):
            rec["ci"] = True
        elif a in ("-F", "--fixed-strings", "--literal"):
            rec["fixed"] = True
        elif a in FD_VALUE_FLAGS:
            j += 1
        elif a.startswith("-") and a != "-":
            pass
        else:
            positionals.append(a)
        j += 1
    if positionals:
        if glob_mode:
            rec["globs"].append(positionals[0])
        else:
            rec["pattern"] = positionals[0]
        rec["paths"] = positionals[1:]
    return rec


FILE_FEEDERS = {"cat", "head", "tail", "bat"}


def extract_bash_searches(command: str) -> list[dict]:
    out = []
    for tokens in tokenize_lines(command):
        prev_seg: list[str] | None = None
        for op, seg in split_segments(tokens):
            rec = parse_search_segment(seg)
            if rec is not None:
                rec["stream_filter"] = False
                if op == "|" and not rec["paths"] and not rec["via_xargs"]:
                    head = os.path.basename(prev_seg[0]) if prev_seg else ""
                    feeder_files = ([a for a in prev_seg[1:] if not a.startswith("-")]
                                    if head in FILE_FEEDERS and prev_seg else [])
                    if feeder_files:
                        # `cat file | grep pat` is a file search on that file.
                        rec["paths"] = feeder_files
                    else:
                        rec["stream_filter"] = True
                out.append(rec)
            prev_seg = seg
    return out


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def scan() -> dict:
    files = sorted(PROJECTS.rglob("*.jsonl"))
    stats = {"n_files": len(files), "bad_files": 0, "bad_lines": 0, "dup_ids": 0,
             "grep_calls": [], "glob_calls": [], "bash_total": 0,
             "bash_searches": [], "bash_unparsed": 0}
    seen: set[str] = set()
    for f in files:
        try:
            fh = f.open("r", encoding="utf-8", errors="replace")
        except OSError:
            stats["bad_files"] += 1
            continue
        with fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    stats["bad_lines"] += 1
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict) or not isinstance(msg.get("content"), list):
                    continue
                for b in msg["content"]:
                    if not isinstance(b, dict) or b.get("type") != "tool_use":
                        continue
                    name, tid = b.get("name"), b.get("id")
                    if name not in ("Grep", "Glob", "Bash"):
                        continue
                    if tid:
                        if tid in seen:
                            stats["dup_ids"] += 1
                            continue
                        seen.add(tid)
                    inp = b.get("input") or {}
                    if not isinstance(inp, dict):
                        continue
                    if name == "Grep":
                        stats["grep_calls"].append(inp)
                    elif name == "Glob":
                        stats["glob_calls"].append(inp)
                    else:
                        stats["bash_total"] += 1
                        cmd = inp.get("command")
                        if isinstance(cmd, str):
                            recs = extract_bash_searches(cmd)
                            stats["bash_searches"].extend(recs)
                        else:
                            stats["bash_unparsed"] += 1
    return stats


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def report(st: dict) -> None:
    ng, nb = len(st["grep_calls"]), len(st["glob_calls"])
    print("=" * 72)
    print("1. COUNTS")
    print(f"session files scanned      : {st['n_files']}")
    print(f"unreadable files           : {st['bad_files']}")
    print(f"unparseable lines          : {st['bad_lines']}")
    print(f"duplicate tool_use ids     : {st['dup_ids']}")
    print(f"Grep tool calls            : {ng}")
    print(f"Glob tool calls            : {nb}")
    print(f"Bash tool calls            : {st['bash_total']}")
    searches = st["bash_searches"]
    print(f"Bash-invoked search commands (rg/grep/find/fd): {len(searches)}")
    tool_counts = Counter(r["tool"] for r in searches)
    for t, n in tool_counts.most_common():
        print(f"    {t:6s}: {n:6d}  ({pct(n, len(searches))})")
    filters = [r for r in searches if r["stream_filter"]]
    print(f"stream filters (grep over piped command output, "
          f"not file search — excluded below): {len(filters)}")

    searches = [r for r in searches if not r["stream_filter"]]
    grep_like = [r for r in searches if r["tool"] in ("rg", "grep")]
    find_like = [r for r in searches if r["tool"] in ("find", "fd")]
    n_gl = len(grep_like)
    print(f"file-search grep-like calls (rg+grep) analyzed below: {n_gl}")

    # ---- 2. scoping of grep-like calls ----
    def globby(p: str) -> bool:
        return any(c in p for c in "*?[")

    with_glob = [r for r in grep_like if r["globs"]]
    with_type = [r for r in grep_like if r["types"]]
    with_path = [r for r in grep_like if r["paths"]]
    unscoped = [r for r in grep_like if not (r["globs"] or r["types"] or r["paths"])]
    path_kind = Counter()
    for r in with_path:
        if all(globby(p) for p in r["paths"]):
            path_kind["shell-glob"] += 1
            continue
        kinds = {is_dirlike(p) for p in r["paths"] if not globby(p)}
        path_kind["dir" if "dir" in kinds else ("file" if "file" in kinds else "unknown")] += 1
    print()
    print("=" * 72)
    print(f"2. SCOPING of grep-like calls (rg+grep, n={n_gl})")
    print(f"with glob scope (-g/--include) : {len(with_glob):6d}  ({pct(len(with_glob), n_gl)})")
    print(f"with path arg(s)               : {len(with_path):6d}  ({pct(len(with_path), n_gl)})")
    for k in ("dir", "file", "shell-glob", "unknown"):
        if path_kind.get(k):
            print(f"    path is {k:10s}         : {path_kind[k]:6d}  ({pct(path_kind[k], len(with_path))} of pathed)")
    print(f"with type scope (-t)           : {len(with_type):6d}  ({pct(len(with_type), n_gl)})")
    print(f"unscoped (cwd-wide, no filter) : {len(unscoped):6d}  ({pct(len(unscoped), n_gl)})")

    # ---- 3. glob-shape taxonomy ----
    grep_globs = [g for r in grep_like for g in r["globs"]]
    findfd_globs = [g for r in find_like for g in r["globs"]]
    shellglob_paths = [p for r in searches for p in r["paths"] if globby(p)]
    all_globs = grep_globs + findfd_globs + shellglob_paths
    print()
    print("=" * 72)
    print(f"3. GLOB-SHAPE TAXONOMY  ({len(all_globs)} glob patterns: "
          f"{len(grep_globs)} rg/grep scopes + {len(findfd_globs)} find/fd + "
          f"{len(shellglob_paths)} shell-glob path args)")
    shape_counts = Counter(classify_glob(g) for g in all_globs)
    for shape, n in shape_counts.most_common():
        print(f"{shape:32s}: {n:6d}  ({pct(n, len(all_globs))})")
    sub = Counter()
    for g in all_globs:
        if classify_glob(g) == "directory-scoped path glob":
            key = []
            if g.startswith("**/"):
                key.append("**/-prefixed")
            elif "**" in g:
                key.append("embedded **")
            if "{" in g:
                key.append("with braces")
            sub["+".join(key) if key else "plain dir/name glob"] += 1
    if sub:
        print("  [directory-scoped sub-shapes]")
        for k, n in sub.most_common():
            print(f"    {k:30s}: {n:6d}")
    print()
    print("Top 20 literal glob strings (home-stripped):")
    for g, n in Counter(strip_home(g) for g in all_globs).most_common(20):
        print(f"  {n:6d}  {g}")

    # ---- 4. directory scopes ----
    all_paths = [p for r in searches for p in r["paths"] if not globby(p)]
    dir_paths = [p for p in all_paths if is_dirlike(p) == "dir"]
    rel_depths = Counter()
    for p in dir_paths:
        if p.startswith("/") or p.startswith("~"):
            rel_depths[f"abs:{depth_of(strip_home(p))}"] += 1
        else:
            rel_depths[f"rel:{depth_of(p)}"] += 1
    print()
    print("=" * 72)
    print(f"4. DIRECTORY SCOPES  ({len(dir_paths)} dir-like path args across all search calls)")
    print("depth distribution (rel: relative to cwd; abs: project-relative after home-strip):")
    for k in sorted(rel_depths, key=lambda s: (s.split(":")[0], int(s.split(":")[1]))):
        n = rel_depths[k]
        print(f"  {k:8s}: {n:6d}  ({pct(n, len(dir_paths))})")
    print("Top 15 directory scopes (home-stripped):")
    for p, n in Counter(strip_home(p) for p in dir_paths).most_common(15):
        print(f"  {n:6d}  {p}")

    # ---- 5. pattern side ----
    pats = [r["pattern"] for r in grep_like if r["pattern"]]
    literal = [p for p in pats if r"\b" not in p and not (set(p) & REGEX_META)]
    fixed = [r for r in grep_like if r["fixed"]]
    ci = [r for r in grep_like if r["ci"]]
    alt = [p for p in pats if "|" in p]
    print()
    print("=" * 72)
    print(f"5. PATTERN SIDE (grep-like, n={n_gl}; {len(pats)} with a parsed pattern)")
    print(f"plain literal (no regex metachars): {len(literal):6d}  ({pct(len(literal), len(pats))})")
    print(f"contains regex metachars          : {len(pats) - len(literal):6d}  ({pct(len(pats) - len(literal), len(pats))})")
    print(f"  of which use alternation '|'    : {len(alt):6d}  ({pct(len(alt), len(pats))})")
    print(f"explicit -F fixed-strings         : {len(fixed):6d}  ({pct(len(fixed), n_gl)})")
    print(f"case-insensitive (-i / -iname)    : {len(ci):6d}  ({pct(len(ci), n_gl)})")
    plain_grep = [r for r in grep_like if r["tool"] == "grep"]
    rec_grep = [r for r in plain_grep if r["recursive"]]
    print(f"recursive -r (of plain grep calls): {len(rec_grep):6d}  ({pct(len(rec_grep), len(plain_grep))})")
    out_modes = Counter(r["output"] for r in grep_like)
    print("output mode (content vs file-list vs count):")
    for m, n in out_modes.most_common():
        print(f"  {m:10s}: {n:6d}  ({pct(n, n_gl)})")

    # ---- 6. co-occurrence ----
    def combo(r: dict) -> str:
        parts = [k for k, v in (("glob", r["globs"]), ("path", r["paths"]), ("type", r["types"])) if v]
        return "+".join(parts) if parts else "(unscoped)"

    print()
    print("=" * 72)
    print(f"6. SCOPE CO-OCCURRENCE (grep-like, n={n_gl})")
    for k, n in Counter(combo(r) for r in grep_like).most_common():
        print(f"  {k:20s}: {n:6d}  ({pct(n, n_gl)})")
    multi_glob = [r for r in grep_like if len(r["globs"]) > 1]
    multi_path = [r for r in searches if len(r["paths"]) > 1]
    print(f"\ncalls with >1 glob scope : {len(multi_glob)}  ({pct(len(multi_glob), n_gl)})")
    print(f"calls with >1 path arg   : {len(multi_path)}  ({pct(len(multi_path), len(searches))})")
    types = Counter(t for r in grep_like for t in r["types"])
    print("`-t type` values:", dict(types.most_common(15)))
    fd_ext = Counter(g for r in find_like if r["tool"] == "fd" for g in r["globs"])
    print("fd extension/glob scopes (top 10):", dict(fd_ext.most_common(10)))


if __name__ == "__main__":
    report(scan())
