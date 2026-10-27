"""S9 probe 2: result shapes, output overflow, limit errors, binary bytes, state.

Usage (from the vfs repo root):
  uv run --with just-bash --with bashkit python -I <this file> <out_dir>
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def shape(r: object) -> dict:
    d = {}
    for k in dir(r):
        if k.startswith("_"):
            continue
        try:
            v = getattr(r, k)
        except Exception as e:  # noqa: BLE001
            v = f"<err {e}>"
        if callable(v):
            continue
        if isinstance(v, bytes):
            v = f"<bytes len={len(v)} head={v[:12]!r}>"
        elif isinstance(v, str) and len(v) > 200:
            v = f"<str len={len(v)} head={v[:60]!r} tail={v[-60:]!r}>"
        d[k] = v
    return d


async def just_bash_py() -> dict:
    import just_bash  # noqa: PLC0415

    out: dict = {}
    bash = just_bash.Bash()
    out["attrs"] = sorted(k for k in dir(await bash.exec("true")) if not k.startswith("_"))
    out["overflow_seq_400000"] = shape(await bash.exec("seq 1 400000"))
    try:
        out["infinite_loop"] = shape(await bash.exec("while true; do :; done"))
    except Exception as e:  # noqa: BLE001
        out["infinite_loop"] = {"exception": f"{type(e).__name__}: {e}"}
    try:
        await bash.fs.write_file("/tmp/img.png", PNG)
        out["cat_png_via_fs_api"] = shape(await bash.exec("cat /tmp/img.png"))
    except Exception as e:  # noqa: BLE001
        out["cat_png_via_fs_api"] = {"exception": f"{type(e).__name__}: {e}"}
    out["state_env"] = shape(await bash.exec("export X=1; echo $X"))
    out["state_env_next_call"] = shape(await bash.exec("echo X=$X"))
    out["state_cwd"] = shape(await bash.exec("cd /tmp; pwd"))
    out["state_cwd_next_call"] = shape(await bash.exec("pwd"))
    return out


def bashkit_probe() -> dict:
    import bashkit  # noqa: PLC0415

    out: dict = {}
    bash = bashkit.Bash()
    out["attrs"] = sorted(k for k in dir(bash.execute_sync("true")) if not k.startswith("_"))
    out["overflow_seq_400000"] = shape(bash.execute_sync("seq 1 400000"))
    out["infinite_loop"] = shape(bash.execute_sync("while true; do :; done"))
    bash.fs().write_file("/tmp/img.png", PNG)
    out["cat_png_via_fs_api"] = shape(bash.execute_sync("cat /tmp/img.png"))
    out["read_file_api"] = repr(bash.fs().read_file("/tmp/img.png"))
    out["state_env"] = shape(bash.execute_sync("export X=1; echo $X"))
    out["state_env_next_call"] = shape(bash.execute_sync("echo X=$X"))
    out["state_cwd"] = shape(bash.execute_sync("cd /tmp; pwd"))
    out["state_cwd_next_call"] = shape(bash.execute_sync("pwd"))
    out["unavailable_hint_docker"] = shape(bash.execute_sync("docker ps"))
    out["did_you_mean"] = shape(bash.execute_sync("grpe foo"))
    tool = bashkit.BashTool()
    out["tool_description"] = tool.description()
    out["tool_system_prompt"] = tool.system_prompt()
    out["tool_input_schema"] = tool.input_schema()
    out["tool_help_head"] = tool.help()[:1500]
    tool.execute_sync("echo persisted > /tmp/t.txt")
    out["tool_state_next_call"] = shape(tool.execute_sync("cat /tmp/t.txt"))
    out["tool_result_attrs"] = out["tool_state_next_call"].keys().__class__.__name__
    return out


def main() -> None:
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    res = {}
    try:
        res["just-bash-py"] = asyncio.run(just_bash_py())
    except Exception as e:  # noqa: BLE001
        res["just-bash-py"] = {"fatal": f"{type(e).__name__}: {e}"}
    try:
        res["bashkit"] = bashkit_probe()
    except Exception as e:  # noqa: BLE001
        res["bashkit"] = {"fatal": f"{type(e).__name__}: {e}"}
    text = json.dumps(res, indent=2, ensure_ascii=False, default=str)
    (out_dir / "probe2.json").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
