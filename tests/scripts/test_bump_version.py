"""The bump script moves the version along the lane, refuses the moves the lane forbids, and keeps the lock in step."""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

import pytest
from packaging.version import Version

REPO = Path(__file__).resolve().parents[2]
_SCRIPT = REPO / "scripts" / "bump_version.py"
_SPEC = importlib.util.spec_from_file_location("bump_version", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
bump_version = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bump_version)

SCRATCH_PYPROJECT = """\
[build-system]
requires = ["maturin>=1.8.4,<2.0"]

[tool.maturin]
version = "9.9.9"

[project]
name = "vfs-py"
version = "0.0.22"

[tool.other]
version = "8.8.8"
"""

TRANSITIONS = [
    ("0.0.22", {"part": "patch"}, "0.0.23"),
    ("0.0.22", {"part": "minor"}, "0.1.0"),
    ("0.1.0", {"part": "major"}, "1.0.0"),
    ("0.0.22", {"part": "minor", "pre": "a"}, "0.1.0a1"),
    ("0.0.22", {"part": "major", "pre": "b"}, "1.0.0b1"),
    ("0.1.0a1", {"pre": "a"}, "0.1.0a2"),
    ("0.1.0a4", {"pre": "b"}, "0.1.0b1"),
    ("0.1.0b2", {"pre": "rc"}, "0.1.0rc1"),
    ("0.1.0b3", {"final": True}, "0.1.0"),
    ("0.1.0b3", {"explicit": "0.2.0.dev1"}, "0.2.0.dev1"),
]

REFUSALS = [
    ("0.1.0b1", {"pre": "a"}, "backwards"),
    ("0.1.0rc1", {"pre": "b"}, "backwards"),
    ("0.1.0", {"final": True}, "already a final"),
    ("0.1.0", {"pre": "a"}, "part flag"),
    ("0.1.0a1", {"part": "patch"}, "pre-release"),
    ("0.1.0a1", {"part": "minor", "pre": "a"}, "pre-release"),
    ("0.1.0", {"explicit": "not-a-version"}, "PEP 440"),
]


@pytest.mark.parametrize(("current", "move", "expected"), TRANSITIONS, ids=[row[2] for row in TRANSITIONS])
def test_each_transition_in_the_lane(current: str, move: dict[str, object], expected: str) -> None:
    """Mutating any row of the transition table in the script changes one of these answers."""
    assert bump_version.next_version(Version(current), **move) == Version(expected)


@pytest.mark.parametrize(("current", "move", "reason"), REFUSALS, ids=[row[2] for row in REFUSALS])
def test_each_refusal_in_the_lane(current: str, move: dict[str, object], reason: str) -> None:
    """Dropping a refusal from next_version lets a forbidden move through."""
    with pytest.raises(bump_version.BumpRefused, match=reason):
        bump_version.next_version(Version(current), **move)


def test_a_refusal_writes_nothing_and_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refusal reaching main leaves the file as it was, runs no lock, and says why once on stderr."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(SCRATCH_PYPROJECT)
    calls: list[list[str]] = []
    monkeypatch.setattr(bump_version, "run", lambda args, **_: calls.append(args))

    status = bump_version.main(["--final", "--pyproject", str(pyproject)])

    captured = capsys.readouterr()
    assert status == 2
    assert pyproject.read_text() == SCRATCH_PYPROJECT
    assert calls == []
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert "already a final" in captured.err


def test_main_rewrites_pyproject_and_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only the [project] version line changes; one `uv lock` runs beside the file; old → new is printed."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(SCRATCH_PYPROJECT)
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(bump_version, "run", lambda args, **kwargs: calls.append((args, kwargs)))

    status = bump_version.main(["--minor", "--pre", "a", "--pyproject", str(pyproject)])

    assert status == 0
    before = SCRATCH_PYPROJECT.splitlines()
    after = pyproject.read_text().splitlines()
    changed = [(old, new) for old, new in zip(before, after, strict=True) if old != new]
    assert changed == [('version = "0.0.22"', 'version = "0.1.0a1"')]
    assert tomllib.loads(pyproject.read_text())["tool"]["maturin"]["version"] == "9.9.9"
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ["uv", "lock"]
    assert kwargs["cwd"] == tmp_path
    assert capsys.readouterr().out == "0.0.22 → 0.1.0a1\n"


def test_the_lock_carries_the_project_version() -> None:
    """A bump that forgets `uv lock` leaves the lock a version behind; this reads both files."""
    project = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
    lock = tomllib.loads((REPO / "uv.lock").read_text())
    locked = [package["version"] for package in lock["package"] if package["name"] == project["name"]]
    assert locked == [project["version"]]


def test_the_manifests_say_what_the_lane_needs() -> None:
    """The maturin floor that bootstraps Rust, packaging declared, and a crate comment that names the module."""
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert pyproject["build-system"]["requires"] == ["maturin>=1.8.4,<2.0"]
    dev = pyproject["dependency-groups"]["dev"]
    assert any(requirement.startswith("packaging") for requirement in dev)
    assert "_accel" not in (REPO / "crates" / "vfs-core" / "Cargo.toml").read_text()
