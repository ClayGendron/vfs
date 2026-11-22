"""The shell: a line of bash, run inside vfs with every effect a public verb.

The interpreter is the ``vfs-shell`` crate, which parses a line whole, runs it
and does no IO of its own: it asks for every file it reads or writes as a
request. :func:`run_line` is its host here. Each request becomes one call of a
public verb of the router, with the caller's authority, so every effect of the
line passes the same gate as the caller's own call would.

    result = await fs.cli("grep -rn TODO /docs | head -3", authority=alice)
    print(result.stdout)
"""

from __future__ import annotations

from vfs.shell.host import LineResult, refused_line, run_line

__all__ = ["LineResult", "refused_line", "run_line"]
