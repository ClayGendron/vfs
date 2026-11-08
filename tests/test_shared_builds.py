"""The session-wide build claim: one build, a published skip, and a dead builder failing its waiters at once."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from tests.support import shared_builds
from tests.support.shared_builds import build_once

if TYPE_CHECKING:
    import pathlib


class _Builder:
    """A build that counts its calls and answers, or skips, as told."""

    def __init__(self, *, skip: str | None = None) -> None:
        self.calls = 0
        self._skip = skip

    def __call__(self, workdir: pathlib.Path) -> Any:
        self.calls += 1
        if self._skip is not None:
            pytest.skip(self._skip)
        return {"built": str(workdir.name)}


def test_a_published_build_is_read_not_rebuilt(tmp_path: pathlib.Path) -> None:
    builder = _Builder()
    assert build_once(tmp_path, "k", builder) == {"built": "k"}
    assert build_once(tmp_path, "k", builder) == {"built": "k"}
    assert builder.calls == 1


def test_a_builder_skip_skips_every_waiter(tmp_path: pathlib.Path) -> None:
    """Guards: a builder's skip published as an error, failing every waiter."""
    builder = _Builder(skip="no engine here")
    for _caller in range(2):
        with pytest.raises(pytest.skip.Exception, match="no engine here"):
            build_once(tmp_path, "k", builder)
    assert builder.calls == 1


def test_a_claim_whose_builder_died_fails_its_waiter_at_once(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards: a waiter blocking out the whole bound on a claim no live process holds."""
    exited = subprocess.Popen([sys.executable, "-c", "pass"])
    exited.wait()
    claim = tmp_path / "k.claim"
    claim.mkdir()
    (claim / "pid").write_text(str(exited.pid))
    # A bound already spent: were the dead builder not seen, the wait would end in TimeoutError instead.
    monkeypatch.setattr(shared_builds, "BUILD_WAIT_SECONDS", -1.0)
    builder = _Builder()
    with pytest.raises(RuntimeError, match="exited without publishing"):
        build_once(tmp_path, "k", builder)
    assert builder.calls == 0
