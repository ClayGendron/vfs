"""The suite's own guards: a failed shared assertion shows both sides, a leak fails, and a hang ends.

A pin or a contract that asserts in a helper module prints a bare
``AssertionError`` unless pytest rewrote that module, and a pin that
failed once in CI printed neither list. A connection or a thread a test
leaves behind is reported by the collector in whatever test runs next,
or only in the summary, unless the suite makes it an error. A test that
hangs under parallel workers is ended alone, and every thread's stack
is left in a file, because pytest-xdist drops a worker's stderr.
"""

from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

from tests.conftest import HANG_DIR_VAR, HELPER_PACKAGES

TESTS: Final = Path(__file__).parent
REPO: Final = TESTS.parent
LEAKS_ARE_ERRORS: Final = (
    "error::ResourceWarning",
    "error::pytest.PytestUnraisableExceptionWarning",
    "error::pytest.PytestUnhandledThreadExceptionWarning",
)
HANGING: Final = """
import asyncio
import threading

import pytest


@pytest.fixture
def teardown_that_waits_forever():
    yield
    threading.Event().wait()


def test_a_loop_that_waits_forever():
    asyncio.run(asyncio.Event().wait())


def test_a_thread_that_waits_forever():
    threading.Event().wait()


def test_a_failure_whose_teardown_waits_forever(teardown_that_waits_forever):
    assert False


def test_the_worker_runs_on():
    pass
"""
IMPLICIT_LOOP: Final = """
import asyncio
import gc


async def test_an_async_test_first():
    pass


def test_then_no_loop_is_left_open_but_the_one_in_use():
    in_use = asyncio.get_event_loop()
    stray = [o for o in gc.get_objects() if isinstance(o, asyncio.BaseEventLoop) and not o.is_closed()]
    assert stray == [in_use]
"""
CHILD_INI: Final = """[pytest]
asyncio_mode = auto
timeout = 2
timeout_method = signal
filterwarnings =
    error::ResourceWarning
    error::pytest.PytestUnraisableExceptionWarning
"""
RUN_BACKSTOP_SECONDS: Final = 300
"""Ends the child run should the guard under test fail to: a liveness bound, never a measure."""


def test_every_helper_module_that_asserts_is_rewritten() -> None:
    asserting = [name for name in _helper_modules() if _asserts(name)]
    assert asserting, "the walk found no helper module, so it proves nothing"
    unrewritten = [name for name in asserting if "@pytest_ar" not in vars(importlib.import_module(name))]
    assert unrewritten == []


def test_a_leak_is_an_error(pytestconfig: pytest.Config) -> None:
    filters = pytestconfig.getini("filterwarnings")
    assert [rule for rule in LEAKS_ARE_ERRORS if rule not in filters] == []


@pytest.mark.slow
def test_a_hung_test_fails_alone_and_leaves_every_stack_in_a_file(tmp_path: Path) -> None:
    hangs = _run_child(tmp_path, HANGING, "-n", "1")
    assert hangs.returncode == 1, hangs.stdout
    assert "3 failed, 1 passed, 1 error" in hangs.stdout, hangs.stdout
    [log] = sorted((tmp_path / "hangs").iterdir())
    dumped = log.read_text(encoding="utf-8")
    for test, frame in (
        ("test_a_loop_that_waits_forever", "test_a_loop_that_waits_forever"),
        ("test_a_thread_that_waits_forever", "test_a_thread_that_waits_forever"),
        ("test_a_failure_whose_teardown_waits_forever", "teardown_that_waits_forever"),
    ):
        assert f"test_hanging.py::{test}" in dumped, dumped
        assert f" in {frame}" in dumped, dumped
    assert "test_the_worker_runs_on" not in dumped, dumped


@pytest.mark.slow
def test_a_run_with_no_hang_leaves_no_file(tmp_path: Path) -> None:
    ran = _run_child(tmp_path, HANGING, "-n", "1", "-k", "runs_on")
    assert ran.returncode == 0, ran.stdout
    assert not (tmp_path / "hangs").exists() or list((tmp_path / "hangs").iterdir()) == []


@pytest.mark.slow
def test_no_test_leaves_a_loop_that_pytest_asyncio_made_unasked(tmp_path: Path) -> None:
    ran = _run_child(tmp_path, IMPLICIT_LOOP, "-n", "0")
    assert ran.returncode == 0, ran.stdout


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _helper_modules() -> list[str]:
    """Every module of the helper packages that pytest would not rewrite on its own, as a dotted name."""
    names: list[str] = []
    for package in HELPER_PACKAGES:
        for file in sorted((REPO / package.replace(".", "/")).rglob("*.py")):
            if file.name.startswith("test_") or file.name in ("__init__.py", "conftest.py"):
                continue
            names.append(".".join(file.relative_to(REPO).with_suffix("").parts))
    return names


def _asserts(name: str) -> bool:
    tree = ast.parse((REPO / f"{name.replace('.', '/')}.py").read_text(encoding="utf-8"))
    return any(isinstance(node, ast.Assert) for node in ast.walk(tree))


def _run_child(tmp_path: Path, source: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run *source* as a test file in a child pytest under this suite's hooks, with a two-second deadline."""
    (tmp_path / "test_hanging.py").write_text(source, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text(CHILD_INI, encoding="utf-8")
    command = [sys.executable, "-m", "pytest", "-c", str(tmp_path / "pytest.ini"), "--rootdir", str(tmp_path)]
    command += ["-p", "tests.conftest", "-p", "no:cacheprovider", "-q", *arguments, str(tmp_path / "test_hanging.py")]
    environment = dict(os.environ)
    environment.update({"PYTHONPATH": str(REPO), HANG_DIR_VAR: str(tmp_path / "hangs")})
    environment.pop("PYTEST_XDIST_WORKER", None)
    return subprocess.run(
        command, capture_output=True, text=True, env=environment, timeout=RUN_BACKSTOP_SECONDS, check=False
    )
