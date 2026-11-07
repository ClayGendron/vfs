"""The tag check refuses a tag that is not v plus the project version; the workflows run on what they say."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
_SCRIPT = REPO / "scripts" / "check_release_tag.py"
_SPEC = importlib.util.spec_from_file_location("check_release_tag", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
check_release_tag = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_release_tag)


@pytest.fixture
def scratch_pyproject(tmp_path: Path) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "vfs-py"\nversion = "0.1.0a1"\n')
    return path


def test_a_matching_tag_passes(scratch_pyproject: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Changing the comparison to a prefix match or dropping the `v` lets a wrong tag through."""
    assert check_release_tag.main(["v0.1.0a1", "--pyproject", str(scratch_pyproject)]) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("tag", ["v0.1.0a2", "0.1.0a1"])
def test_a_mismatched_tag_fails(tag: str, scratch_pyproject: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A tag one number off, or missing its `v`, exits 1 and names both the tag and the version once."""
    assert check_release_tag.main([tag, "--pyproject", str(scratch_pyproject)]) == 1
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert tag in err
    assert "0.1.0a1" in err


def _workflow(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text())
    return loaded


def test_the_publish_workflow_runs_the_check_first_in_every_job() -> None:
    """Removing the step from one job, or ordering it after a build step, or restoring macos-13, fails here."""
    workflow = _workflow("publish.yml")
    # PyYAML reads the bare key `on` as the boolean True.
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    assert {"release", "workflow_dispatch"} <= set(triggers)
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    runners: list[str] = []
    for name, job in jobs.items():
        steps = job["steps"]
        checks = [i for i, step in enumerate(steps) if "scripts/check_release_tag.py" in str(step.get("run", ""))]
        assert len(checks) == 1, f"job {name!r} runs the tag check {len(checks)} times"
        assert "release" in str(steps[checks[0]].get("if", "")), f"job {name!r}: the check is not gated on a release"
        builds = [
            i
            for i, step in enumerate(steps)
            if "maturin-action" in str(step.get("uses", "")) or "download-artifact" in str(step.get("uses", ""))
        ]
        assert builds and min(builds) > checks[0], f"job {name!r}: a build step precedes the tag check"
        # No job syncs a project, so the action's cache post-step would fail a job that cached nothing.
        setups = [step for step in steps if "setup-uv" in str(step.get("uses", ""))]
        assert setups, f"job {name!r} has no setup-uv step"
        assert all(step.get("with", {}).get("enable-cache") is False for step in setups), (
            f"job {name!r}: a setup-uv step does not set enable-cache: false"
        )
        runners.append(str(job["runs-on"]))
    assert "release" in str(jobs["publish"]["if"])
    text = (WORKFLOWS / "publish.yml").read_text()
    assert "macos-13" not in text
    assert "macos-15-intel" in text


def test_the_publish_matrix_builds_the_five_wheels_a_host_can_install() -> None:
    """A musl row back in the matrix, or a Linux row off manylinux 2_28, fails here; sqlite-vec ships no musl wheel."""
    platforms = _workflow("publish.yml")["jobs"]["wheels"]["strategy"]["matrix"]["platform"]
    assert len(platforms) == 5, [platform["name"] for platform in platforms]
    assert not any("musllinux" in str(platform) for platform in platforms)
    linux = [platform for platform in platforms if platform["name"].startswith("linux-")]
    assert [platform["manylinux"] for platform in linux] == ["2_28", "2_28"]


def test_the_dialect_workflow_pins_its_runner_and_its_keyring() -> None:
    """The ODBC step names the 24.04 feed, so the runner is that release and the keys go where its signed-by looks."""
    workflow = _workflow("test-dialects.yml")
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    assert [job["runs-on"] for job in jobs.values()] == ["ubuntu-24.04"]
    (job,) = jobs.values()
    (odbc,) = [step for step in job["steps"] if step.get("name") == "Install ODBC driver"]
    run = odbc["run"]
    assert "/usr/share/keyrings/microsoft-prod.gpg" in run
    assert "keys/microsoft.asc" in run
    assert "keys/microsoft-2025.asc" in run
    assert "trusted.gpg.d" not in run
