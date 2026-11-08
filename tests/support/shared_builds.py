"""Heavy fixtures built once per test session, shared by every xdist worker.

A fixture that writes tens of thousands of rows costs the same on every
worker that asks for it, and with work stealing that can be every
worker. A build here is claimed by the first worker to create its claim
directory (an atomic ``mkdir`` on every platform); that worker builds
into the session's shared temporary directory and publishes a ready
marker, and every other worker waits for the marker and reads what was
built. A build that raises publishes its error, so a waiter fails with
the builder's reason instead of waiting out its bound; a build that
skips publishes its reason, so every waiter skips for it too. The
claim holds the builder's pid, so a waiter whose builder died without
publishing (killed outright, and restarted by xdist) fails at once.

    shared = shared_directory(tmp_path_factory)
    result = build_once(shared, "sqlite-plans", lambda directory: measure(directory))
"""

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING, Any, Final

import pytest

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

# How long a waiting worker gives a rival's build before failing, in seconds.
BUILD_WAIT_SECONDS: Final = 900.0

# How often a waiting worker looks for the rival's ready marker, in seconds.
_POLL_SECONDS: Final = 0.2

# The file inside a claim that names the builder's process.
_PID_FILE: Final = "pid"


def shared_directory(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """The session's temporary directory every worker sees: the workers' common parent under xdist."""
    base = tmp_path_factory.getbasetemp()
    return base.parent if os.environ.get("PYTEST_XDIST_WORKER") else base


def build_once(shared: pathlib.Path, key: str, build: Callable[[pathlib.Path], Any]) -> Any:
    """*build*'s JSON-serializable result for *key*, built by exactly one worker of the session.

    The builder gets a directory of its own under *shared* to leave
    files in, and its result is written beside it; every caller,
    builder or waiter, answers the same decoded result.
    """
    claim = shared / f"{key}.claim"
    ready = shared / f"{key}.json"
    try:
        claim.mkdir()
    except FileExistsError:
        return _awaited(claim, ready, key)
    (claim / _PID_FILE).write_text(str(os.getpid()))
    workdir = shared / key
    workdir.mkdir(exist_ok=True)
    try:
        result = build(workdir)
    except pytest.skip.Exception as exc:
        _publish(ready, {"skip": str(exc.msg)})
        raise
    except BaseException as exc:
        _publish(ready, {"error": f"{type(exc).__name__}: {exc}"})
        raise
    _publish(ready, {"result": result})
    return result


def _awaited(claim: pathlib.Path, ready: pathlib.Path, key: str) -> Any:
    """The rival builder's published result, its skip or its error, waited for while the builder lives."""
    deadline = time.monotonic() + BUILD_WAIT_SECONDS
    while not ready.exists():
        if _builder_gone(claim) and not ready.exists():
            msg = f"the shared build {key!r} was claimed by a process that exited without publishing"
            raise RuntimeError(msg)
        if time.monotonic() > deadline:
            msg = f"the shared build {key!r} did not finish within {BUILD_WAIT_SECONDS} s"
            raise TimeoutError(msg)
        time.sleep(_POLL_SECONDS)
    published = json.loads(ready.read_text())
    if "skip" in published:
        pytest.skip(published["skip"])
    if "error" in published:
        msg = f"the shared build {key!r} failed in another worker: {published['error']}"
        raise RuntimeError(msg)
    return published["result"]


def _builder_gone(claim: pathlib.Path) -> bool:
    """Whether the claim's builder process has exited; a claim whose pid is not yet written is still live."""
    try:
        pid = int((claim / _PID_FILE).read_text())
    except (FileNotFoundError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _publish(ready: pathlib.Path, payload: dict[str, Any]) -> None:
    """Write *payload* beside the marker's name, then rename it into place, so no reader sees half of it."""
    staged = ready.with_suffix(".staged")
    staged.write_text(json.dumps(payload))
    staged.replace(ready)
