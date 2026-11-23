"""How many host (tool) calls one code-mode program may make, in Monty and in smolagents' local executor.

The question for a vfs code mode: an ETL batch of 10,000 files is a supported contract, so a program that
loops over 10,000 paths and calls a verb on each must either fit the sandbox's per-program budget or be
expressed as one batched verb call. This script measures where each sandbox stops such a loop with its
default limits. It counts calls; it times nothing.
"""

from __future__ import annotations

import sys

from pydantic_monty import Monty
from smolagents.local_python_executor import LocalPythonExecutor
from smolagents.tools import tool

SIZES = (10, 500, 999, 1000, 1001, 2000, 10000)


def monty_loop(n: int) -> str:
    calls = {"n": 0}

    def stat(path: str) -> dict:
        calls["n"] += 1
        return {"path": path, "size": len(path)}

    code = f"total = 0\nfor i in range({n}):\n    total += stat('/data/f' + str(i))['size']\ntotal"
    with Monty() as pool:
        with pool.checkout() as session:
            try:
                out = session.feed_run(code, external_lookup={"stat": stat})
                return f"ok result={out} host_calls={calls['n']}"
            except Exception as exc:  # the sandbox's own refusal is the finding
                return f"refused after host_calls={calls['n']}: {type(exc).__name__}: {str(exc)[:160]}"


def monty_no_ambient_fs() -> str:
    with Monty() as pool:
        with pool.checkout() as session:
            try:
                session.feed_run("import os\nos.listdir('/')")
                return "listed / (ambient filesystem present)"
            except Exception as exc:
                return f"{type(exc).__name__}: {str(exc)[:160]}"


calls_smol = {"n": 0}


@tool
def stat(path: str) -> dict:
    """Return metadata for a path.

    Args:
        path: the path to stat.
    """
    calls_smol["n"] += 1
    return {"path": path, "size": len(path)}


def smol_loop(n: int) -> str:
    calls_smol["n"] = 0
    executor = LocalPythonExecutor(additional_authorized_imports=[])
    executor.send_tools({"stat": stat})
    code = f"total = 0\nfor i in range({n}):\n    total += stat('/data/f' + str(i))['size']\nprint(total)"
    try:
        out = executor(code)
        return f"ok logs={out.logs.strip()} host_calls={calls_smol['n']}"
    except Exception as exc:
        return f"refused after host_calls={calls_smol['n']}: {type(exc).__name__}: {str(exc)[:160]}"


def main() -> None:
    print(f"python {sys.version.split()[0]}")
    print("monty, no ambient filesystem:", monty_no_ambient_fs())
    for n in SIZES:
        print(f"monty loop n={n}: {monty_loop(n)}")
    for n in (10, 10000, 200000):
        print(f"smolagents local loop n={n}: {smol_loop(n)}")


if __name__ == "__main__":
    main()
