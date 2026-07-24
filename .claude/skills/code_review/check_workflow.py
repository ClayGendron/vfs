"""Validate an authored code-review workflow script before it is launched.

The workflow's correctness has two halves: the orchestration code, which
must be byte-identical to workflow_template.js outside the authored
scope-constants block, and the scope itself, which this checker re-derives
from git and compares against what the author wrote. Run it on every
authored script; launch only on PASS (exit 0).

    uv run python .claude/skills/code_review/check_workflow.py <script.js>
"""

from __future__ import annotations

# ruff: noqa: T201 — this is a CLI; print is its output channel
import re
import socket
import subprocess
import sys
from pathlib import Path

TEMPLATE_PATH = Path(__file__).with_name("workflow_template.js")
PLACEHOLDER = "// __SCOPE_CONSTANTS__"
START_MARKER = "// --- scope constants"
END_MARKER = "// --- end scope constants"

# Host ports from docker/compose.test.yml; the template's ENGINES block
# promises agents these are live, so the checker verifies before launch.
ENGINE_PORTS = {"postgres": 54320, "mysql": 33061, "mssql": 14330, "oracle": 15210}


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check(script_path: Path) -> tuple[list[str], list[str]]:
    """Run every check; return (failures, warnings)."""
    fails: list[str] = []
    warns: list[str] = []
    text = script_path.read_text(encoding="utf-8")

    if "= args" in text and re.search(r"const\s*\{[^}]*\bscope\b[^}]*\}\s*=\s*args", text):
        fails.append(
            "script destructures scope from `args` — args can silently fail to "
            "bind; inline repo/scope/scratch as literal consts instead"
        )

    block, remainder = _split_scope_block(text)
    if block is None:
        fails.append(
            f"scope-constants markers not found: the authored block must sit "
            f"between lines starting with '{START_MARKER}' and '{END_MARKER}'"
        )
        return fails, warns

    _check_template_conformance(remainder, fails)

    consts = _parse_consts(block, fails)
    if consts is None:
        return fails, warns
    repo, scratch, scope = consts

    if re.search(r"(?<!\\)\$\{", _raw_scope_literal(block) or ""):
        fails.append("scope template literal contains unescaped ${ interpolation")

    if not Path(repo).is_dir() or _git(repo, "rev-parse", "--git-dir").returncode != 0:
        fails.append(f"repo is not a git checkout: {repo}")
        return fails, warns
    if not Path(scratch).is_dir():
        warns.append(f"scratch dir does not exist yet: {scratch}")

    if "undefined" in scope:
        fails.append("scope contains the string 'undefined' — a value did not render")
    warns.extend(f"scope contains a placeholder-looking token: {ph}" for ph in re.findall(r"<[a-z][a-z-]*>", scope))

    _check_range(repo, scope, fails, warns)
    _check_drift(repo, scope, fails)
    _check_engines(fails)
    return fails, warns


def _check_template_conformance(remainder: str, fails: list[str]) -> None:
    """The script outside the authored block must match the template exactly."""
    if not TEMPLATE_PATH.is_file():
        fails.append(f"canonical template missing: {TEMPLATE_PATH}")
        return
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    t_lines = [ln.rstrip() for ln in template.splitlines()]
    r_lines = [ln.rstrip() for ln in remainder.splitlines()]
    if t_lines == r_lines:
        return
    for i, (t, r) in enumerate(zip(t_lines, r_lines, strict=False), start=1):
        if t != r:
            fails.append(
                f"script drifts from workflow_template.js at template line {i}:\n  template: {t}\n  script:   {r}"
            )
            return
    fails.append(
        f"script drifts from workflow_template.js: line counts differ (template {len(t_lines)}, script {len(r_lines)})"
    )


def _check_range(repo: str, scope: str, fails: list[str], warns: list[str]) -> None:
    """Re-derive the commit set from git and compare against the scope text."""
    m = _find_range(scope)
    if not m:
        fails.append("scope declares no commit range (expected <base>..<tip>)")
        return
    base, tip = m.group(1), m.group(2)
    base_full = _resolve_commit(repo, base)
    tip_full = _resolve_commit(repo, tip)
    if not base_full or not tip_full:
        fails.append(f"range endpoints do not resolve to commits: {base}..{tip}")
        return

    log = _git(repo, "log", "--format=%H%x00%s%x00%b%x01", f"{base}..{tip}")
    if log.returncode != 0:
        fails.append(f"git log {base}..{tip} failed: {log.stderr.strip()}")
        return
    in_range: dict[str, tuple[str, str]] = {}
    for record in log.stdout.split("\x01"):
        if record.strip():
            sha, subject, body = record.strip("\n").split("\x00")
            in_range[sha] = (subject, body)
    if not in_range:
        fails.append(f"range {base}..{tip} contains no commits")
        return

    # Outside the range expression itself, every commit SHA the scope
    # mentions must be inside the range: a mentioned commit that is the base
    # or outside it is the silent off-by-one-base defect.
    scope_wo_range = scope.replace(m.group(0), " ")
    mentioned = set(re.findall(r"\b[0-9a-f]{7,40}\b", scope_wo_range))
    for tok in sorted(mentioned):
        full = _resolve_commit(repo, tok)
        if full == base_full:
            fails.append(
                f"scope names the base commit {tok} as if it were reviewed, but "
                f"{base}..{tip} EXCLUDES it — off-by-one base? (base must be the "
                f"parent of the oldest reviewed commit)"
            )
        elif full and full not in in_range:
            fails.append(
                f"scope mentions commit {tok} but it is OUTSIDE {base}..{tip} — "
                f"off-by-one base? (base must be the parent of the oldest commit)"
            )
    mentioned_full = {f for f in (_resolve_commit(repo, t) for t in mentioned) if f}
    for sha, (subject, _) in in_range.items():
        if sha not in mentioned_full and sha[:7] not in scope:
            fails.append(f"commit {sha[:7]} ({subject}) is in the range but never named in the scope")

    # Subjects are binding; bodies are checked loosely (whitespace-normalized).
    scope_norm = _norm(scope)
    for sha, (subject, body) in in_range.items():
        if _norm(subject) not in scope_norm:
            fails.append(f"commit {sha[:7]} subject missing from scope: {subject}")
        body_head = _norm(body)[:60]
        if body_head and body_head not in scope_norm:
            warns.append(f"commit {sha[:7]} body not found in scope (checked first 60 chars)")

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != tip_full:
        warns.append(
            f"tip {tip} is not the current HEAD ({head[:7]}) — reviewers must read "
            f"scoped files via `git show {tip}:<path>`, and the scope should say so"
        )


def _check_engines(fails: list[str]) -> None:
    """The workflow's prompts promise live engines; verify each port answers."""
    down = sorted(name for name, port in ENGINE_PORTS.items() if not _port_open(port))
    if down:
        fails.append(
            f"database engines unreachable: {', '.join(down)} — the workflow "
            f"promises every agent live engines; bring them up first (db_test "
            f"skill build-up) or fix the ports before launching"
        )


def _check_drift(repo: str, scope: str, fails: list[str]) -> None:
    """Dirty working-tree files inside the scoped diff must be declared."""
    m = _find_range(scope)
    if not m:
        return
    scoped = set(_git(repo, "diff", "--name-only", f"{m.group(1)}..{m.group(2)}").stdout.split())
    dirty = set()
    for line in _git(repo, "status", "--porcelain").stdout.splitlines():
        if line.strip():
            dirty.add(line[3:].split(" -> ")[-1].strip('"'))
    fails.extend(
        f"working tree is dirty over scoped file {path}, but the scope "
        f"declares no drift caveat naming it (reviewers must judge the "
        f"committed state via git show <tip>:{path})"
        for path in sorted(scoped & dirty)
        if path not in scope or "drift" not in scope.lower()
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    script_path = Path(sys.argv[1])
    if not script_path.is_file():
        print(f"no such file: {script_path}")
        return 2
    fails, warns = check(script_path)
    for w in warns:
        print(f"WARN: {w}")
    for f in fails:
        print(f"FAIL: {f}")
    if fails:
        print(f"\nFAIL — {len(fails)} problem(s); do not launch this script.")
        return 1
    suffix = f" ({len(warns)} warning(s))" if warns else ""
    print(f"\nPASS — scope verified against git{suffix}; ready to launch.")
    return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _git(repo: str, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", repo, *argv], capture_output=True, text=True)


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=2):
            return True
    except OSError:
        return False


def _find_range(scope: str) -> re.Match[str] | None:
    """The scope's <base>..<tip> expression; ^/~ suffixes on the base allowed."""
    return re.search(r"\b([0-9a-f]{7,40}(?:\^+|~\d*)?)\.\.\.?([0-9a-f]{7,40})\b", scope)


def _resolve_commit(repo: str, token: str) -> str | None:
    result = _git(repo, "rev-parse", "--verify", "--quiet", f"{token}^{{commit}}")
    return result.stdout.strip() or None


def _norm(text: str) -> str:
    return " ".join(text.split())


def _split_scope_block(text: str) -> tuple[str | None, str]:
    """Cut the authored block out; put the placeholder back in its place."""
    lines = text.splitlines(keepends=True)
    start = end = None
    for i, line in enumerate(lines):
        if line.strip().startswith(START_MARKER) and start is None:
            start = i
        elif line.strip().startswith(END_MARKER):
            end = i
    if start is None or end is None or end <= start:
        return None, text
    block = "".join(lines[start : end + 1])
    remainder = "".join(lines[:start]) + PLACEHOLDER + "\n" + "".join(lines[end + 1 :])
    return block, remainder


def _parse_consts(block: str, fails: list[str]) -> tuple[str, str, str] | None:
    """Extract repo, scratch, and the unescaped scope text from the block."""
    values: dict[str, str] = {}
    for name in ("repo", "scratch"):
        m = re.search(rf"const {name} = ['\"](.+?)['\"]", block)
        if not m:
            fails.append(f"authored block does not declare `const {name} = '...'`")
        else:
            values[name] = m.group(1)
    raw = _raw_scope_literal(block)
    if raw is None:
        fails.append("authored block does not declare `const scope = `...`` (template literal)")
    if len(values) < 2 or raw is None:
        return None
    scope = re.sub(r"\\(.)", r"\1", raw)
    return values["repo"], values["scratch"], scope


def _raw_scope_literal(block: str) -> str | None:
    """The scope template literal's raw text, escapes intact; None if absent."""
    m = re.search(r"const scope = `", block)
    if not m:
        return None
    chars: list[str] = []
    i = m.end()
    while i < len(block):
        ch = block[i]
        if ch == "\\" and i + 1 < len(block):
            chars.append(block[i : i + 2])
            i += 2
            continue
        if ch == "`":
            return "".join(chars)
        chars.append(ch)
        i += 1
    return None


if __name__ == "__main__":
    sys.exit(main())
