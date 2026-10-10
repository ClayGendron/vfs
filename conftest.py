"""The documentation's code examples are tests.

Every ``python`` fence in ``README.md`` and under the four Diátaxis
directories runs against the live package through Sybil, one namespace
per page, in document order. A page gets a fresh SQLite-backed
``storage`` and ``fs`` before its first example and has them closed
after its last, and runs inside a scratch directory so a relative
database path in an example lands there, not in the repo. Top-level
``await`` is allowed in a fence.

    uv run pytest docs README.md

A fence that is not runnable (a signature, a sketch) is preceded by
``<!-- skip: next -->`` in the Markdown.
"""

from __future__ import annotations

import ast
import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sybil import Sybil
from sybil.evaluators.python import pad
from sybil.parsers.markdown import CodeBlockParser, SkipParser

from vfs import VirtualFileSystem
from vfs.storage.backends.database import DatabaseStorage

if TYPE_CHECKING:
    from sybil import Example

DOC_PATTERNS = (
    "README.md",
    "docs/tutorials/*.md",
    "docs/how-to/*.md",
    "docs/reference/*.md",
    "docs/explanation/*.md",
)

_LOOP = "__loop__"
_TMP = "__tmp__"
_CWD = "__cwd__"


class AsyncPythonEvaluator:
    """Run a fence in the page namespace, awaiting it when it awaits."""

    def __call__(self, example: Example) -> None:
        __tracebackhide__ = True
        source = pad(example.parsed, example.line + example.parsed.line_offset)
        code = compile(source, example.path, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, dont_inherit=True)
        outcome = eval(code, example.namespace)
        if asyncio.iscoroutine(outcome):
            example.namespace[_LOOP].run_until_complete(outcome)
        example.namespace.pop("__builtins__", None)


def _setup(namespace: dict[str, Any]) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="vfs-docs-"))
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/vfs.sqlite")
    namespace[_TMP] = tmp
    namespace[_CWD] = Path.cwd()
    namespace[_LOOP] = asyncio.new_event_loop()
    namespace["storage"] = storage
    namespace["fs"] = VirtualFileSystem(storage=storage)
    os.chdir(tmp)


def _teardown(namespace: dict[str, Any]) -> None:
    loop: asyncio.AbstractEventLoop = namespace[_LOOP]
    filesystems = {id(v): v for v in namespace.values() if isinstance(v, VirtualFileSystem)}
    for fs in filesystems.values():
        loop.run_until_complete(fs.close())
    loop.close()
    os.chdir(namespace[_CWD])
    shutil.rmtree(namespace[_TMP], ignore_errors=True)


pytest_collect_file = Sybil(
    parsers=[CodeBlockParser(language="python", evaluator=AsyncPythonEvaluator()), SkipParser()],
    patterns=DOC_PATTERNS,
    setup=_setup,
    teardown=_teardown,
).pytest()
