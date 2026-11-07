"""Refuse a release whose tag does not name the project version.

The publish workflow runs this in every job on a release event, right after
checkout and setup-uv and before any wheel is built, so a release cut on a tree whose
``pyproject.toml`` still says the previous number fails here instead of at
PyPI's door seven builds later::

    python scripts/check_release_tag.py v0.1.0a1    # exit 0 when pyproject says 0.1.0a1

Standard library only: it runs before the project environment exists.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"


def project_version(pyproject: Path) -> str:
    """The ``[project]`` table's version string."""
    with pyproject.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def main(argv: list[str] | None = None) -> int:
    """0 when the tag is ``v`` plus the project version, 1 otherwise."""
    parser = argparse.ArgumentParser(description="Check a release tag against pyproject.toml")
    parser.add_argument("tag", help="the release tag, e.g. v0.1.0a1")
    parser.add_argument("--pyproject", type=Path, default=PYPROJECT)
    args = parser.parse_args(argv)
    version = project_version(args.pyproject)
    print(f"tag {args.tag}, project version {version}")
    if args.tag == f"v{version}":
        return 0
    print(
        f"error: the tag {args.tag} does not name the project version {version}; expected v{version}", file=sys.stderr
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
