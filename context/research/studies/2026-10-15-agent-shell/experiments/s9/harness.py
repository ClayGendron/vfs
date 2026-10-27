"""Run the S9 30-command corpus on just-bash-py and bashkit (Python package).

Usage (from the vfs repo root):
  uv run --with just-bash --with bashkit python -I <this file> <out_dir>

Writes <out_dir>/results.json and <out_dir>/results.md. Each engine gets one
long-lived instance (filesystem shared across calls, as an agent session would
see it). Nothing here imports vfs.
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from pathlib import Path

FILES = {
    "/data/notes.txt": "alpha\nTODO fix login\nbeta\nTODO write docs\nalpha\n",
    "/data/config.json": '{"name":"demo","items":[{"id":1},{"id":2}]}\n',
    "/data/people.csv": "name,city,age\nann,paris,30\nbob,rome,41\n",
}


def load_corpus(path: Path) -> list[str]:
    cmds = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cmds.append(line.replace("\\n", "\n"))
    return cmds


def norm(result: object) -> dict:
    out = {}
    for attr in ("stdout", "stderr", "exit_code", "exitCode", "error", "stdout_truncated", "stderr_truncated"):
        if hasattr(result, attr):
            v = getattr(result, attr)
            if isinstance(v, bytes):
                v = v.decode("utf-8", "replace")
            out[attr] = v
    if "exit_code" not in out and "exitCode" in out:
        out["exit_code"] = out.pop("exitCode")
    return out


async def run_just_bash_py(cmds: list[str]) -> list[dict]:
    import just_bash  # noqa: PLC0415

    bash = just_bash.Bash(files=FILES)
    rows = []
    for cmd in cmds:
        try:
            r = await bash.exec(cmd)
            rows.append({"cmd": cmd, **norm(r)})
        except Exception as e:  # noqa: BLE001
            rows.append({"cmd": cmd, "exception": f"{type(e).__name__}: {e}"})
    return rows


def run_bashkit(cmds: list[str]) -> list[dict]:
    import bashkit  # noqa: PLC0415

    bash = bashkit.Bash(files=FILES)
    rows = []
    for cmd in cmds:
        try:
            r = bash.execute_sync(cmd)
            rows.append({"cmd": cmd, **norm(r)})
        except Exception as e:  # noqa: BLE001
            rows.append({"cmd": cmd, "exception": f"{type(e).__name__}: {e}"})
    return rows


def main() -> None:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    cmds = load_corpus(Path(__file__).with_name("corpus.sh"))
    results: dict[str, object] = {"n_commands": len(cmds)}
    versions: dict[str, str] = {}

    try:
        import importlib.metadata as md  # noqa: PLC0415

        for dist in ("just-bash", "bashkit"):
            try:
                versions[dist] = md.version(dist)
            except md.PackageNotFoundError:
                versions[dist] = "not installed"
    except Exception:  # noqa: BLE001
        pass
    results["versions"] = versions

    for name, runner in (("just-bash-py", lambda: asyncio.run(run_just_bash_py(cmds))), ("bashkit", lambda: run_bashkit(cmds))):
        try:
            results[name] = runner()
        except Exception:  # noqa: BLE001
            results[name] = {"fatal": traceback.format_exc()}

    (out_dir / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))

    lines = ["# S9 corpus results", "", f"versions: {versions}", ""]
    for name in ("just-bash-py", "bashkit"):
        rows = results[name]
        lines.append(f"## {name}")
        lines.append("")
        if isinstance(rows, dict):
            lines.append("FATAL:\n```\n" + rows["fatal"] + "\n```")
            continue
        ok = sum(1 for r in rows if r.get("exit_code") == 0)
        lines.append(f"exit 0: {ok}/{len(rows)}")
        lines.append("")
        lines.append("| # | command | exit | stdout (repr, first 160) | stderr (repr, first 160) |")
        lines.append("|---|---|---|---|---|")
        for i, r in enumerate(rows, 1):
            cmd = r["cmd"].replace("\n", "\\n").replace("|", "\\|")
            if "exception" in r:
                lines.append(f"| {i} | `{cmd}` | EXC | {r['exception'][:160]} | |")
                continue
            so = repr(r.get("stdout", ""))[:160].replace("|", "\\|")
            se = repr(r.get("stderr", ""))[:160].replace("|", "\\|")
            extra = ""
            if r.get("error"):
                extra = f" error={r['error']!r}"
            lines.append(f"| {i} | `{cmd}` | {r.get('exit_code')}{extra} | {so} | {se} |")
        lines.append("")
    (out_dir / "results.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
