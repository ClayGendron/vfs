"""Record what bash itself does for every case of the shell corpus.

Each case under ``tests/shell/cases/<area>/<name>.sh`` is run by bash 5.3 and
GNU coreutils in a container image pinned by digest, in a fresh copy of the
seed tree, with a fixed environment, and its standard output, standard error
and exit status are written beside the script as ``<name>.json``. Each case
runs twice; a case whose two runs differ is not recorded, because a record
must be a function of the script. Tests never run bash: they read the records.

    uv run python scripts/shell_record.py            # record cases with no record
    uv run python scripts/shell_record.py --all      # record every case again
    uv run python scripts/shell_record.py quoting/   # record the cases under one prefix

Docker must be running. The image is pulled by digest, never by tag.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tests" / "shell" / "cases"
WORLD = ROOT / "tests" / "shell" / "world"
IMAGE = "debian@sha256:07a3205e8583fdff12d2b05bd030f50437e9fd340ee616df0c05dc77af75767b"
CASE_TIMEOUT_SECONDS = 10
BATCH_TIMEOUT_SECONDS = 1800

# The environment a case runs in; the reference host gives the shell the same.
ENVIRONMENT = (
    "HOME=/home/agent",
    "PATH=/usr/local/bin:/usr/bin:/bin",
    "LC_ALL=C.UTF-8",
    "TZ=UTC",
    "USER=agent",
    "LOGNAME=agent",
    "TERM=dumb",
)

# Runs inside the container as root, and runs each case as an unprivileged user.
_DRIVER = r"""
set -u
mkdir -p /home/agent
chown 1000:1000 /home/agent
while IFS= read -r rel; do
  for run in 1 2; do
    out="/out/$rel.$run"
    mkdir -p "$(dirname "$out")"
    rm -rf /work && mkdir /work
    if grep -q '^# world: seed' "/cases/$rel.sh"; then cp -a /seed/. /work/; fi
    chown -R 1000:1000 /work
    src="$(cat "/cases/$rel.sh")"
    cd /work
    timeout -s KILL {timeout} setpriv --reuid=1000 --regid=1000 --clear-groups \
      env -i {env} bash --norc --noprofile -c "$src" bash \
      </dev/null >"$out.stdout" 2>"$out.stderr"
    echo $? >"$out.status"
    cd /
  done
done </cases.list
"""


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prefixes", nargs="*", help="record only cases under these prefixes")
    parser.add_argument("--all", action="store_true", help="record cases that already have a record")
    args = parser.parse_args(argv)
    cases = _select(args.prefixes, every=args.all)
    if not cases:
        sys.stdout.write("nothing to record\n")
        return 0
    version = _bash_version()
    unstable: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        out = Path(scratch) / "out"
        out.mkdir()
        _run_batch(cases, out)
        for rel in cases:
            first, second = (_read_run(out / f"{rel}.{n}") for n in (1, 2))
            if first != second:
                unstable.append(rel)
                continue
            record = {"image": IMAGE, "bash": version, **first}
            (CASES / f"{rel}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.write(f"recorded {len(cases) - len(unstable)} of {len(cases)} cases\n")
    for rel in unstable:
        sys.stdout.write(f"not recorded, two runs differ: {rel}\n")
    return 1 if unstable else 0


def _select(prefixes: list[str], *, every: bool) -> list[str]:
    chosen = []
    for script in sorted(CASES.rglob("*.sh")):
        rel = script.relative_to(CASES).with_suffix("").as_posix()
        if prefixes and not any(rel.startswith(prefix) for prefix in prefixes):
            continue
        if every or not script.with_suffix(".json").exists():
            chosen.append(rel)
    return chosen


def _bash_version() -> str:
    done = subprocess.run(
        ["docker", "run", "--rm", IMAGE, "bash", "-c", "echo $BASH_VERSION"],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return done.stdout.strip()


def _run_batch(cases: list[str], out: Path) -> None:
    listing = out.parent / "cases.list"
    listing.write_text("".join(f"{rel}\n" for rel in cases))
    driver = _DRIVER.replace("{timeout}", str(CASE_TIMEOUT_SECONDS)).replace("{env}", " ".join(ENVIRONMENT))
    with tempfile.TemporaryDirectory() as seed:
        shutil.copytree(WORLD, seed, dirs_exist_ok=True)
        subprocess.run(
            [
                "docker", "run", "--rm", "--network=none",
                "-v", f"{CASES}:/cases:ro",
                "-v", f"{listing}:/cases.list:ro",
                "-v", f"{seed}:/seed:ro",
                "-v", f"{out}:/out",
                IMAGE, "bash", "-c", driver,
            ],
            check=True,
            timeout=BATCH_TIMEOUT_SECONDS,
        )  # fmt: skip


def _read_run(stem: Path) -> dict[str, object]:
    record: dict[str, object] = {"status": int(Path(f"{stem}.status").read_text().strip())}
    for stream in ("stdout", "stderr"):
        raw = Path(f"{stem}.{stream}").read_bytes()
        try:
            record[stream] = raw.decode("utf-8")
        except UnicodeDecodeError:
            record[f"{stream}_base64"] = base64.b64encode(raw).decode("ascii")
    return record


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
