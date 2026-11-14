"""Count, for one Sphinx inventory, the pages under a prefix by the kind of the first Python object each holds.

Usage: python3 -I kinds.py <objects.inv> <path prefix>, for example reference/generated.
"""

import re
import sys
import zlib
from collections import Counter, defaultdict


def main(path: str, prefix: str) -> None:
    with open(path, "rb") as handle:
        for _ in range(4):
            handle.readline()
        body = zlib.decompress(handle.read()).decode()
    by_page: dict[str, list[str]] = defaultdict(list)
    for line in body.splitlines():
        match = re.match(r"(.+?)\s+(\S+:\S+)\s+(-?\d+)\s+(\S+)\s+(.*)", line)
        if match is None:
            continue
        name, role, _priority, uri = match.groups()[:4]
        if uri.endswith("$"):
            uri = uri[:-1] + name
        page = uri.split("#")[0]
        if page.startswith(prefix) and role.startswith("py:"):
            by_page[page].append(role)
    kinds: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    for roles in by_page.values():
        kinds[roles[0]] += 1
        sizes["1 object" if len(roles) == 1 else "2+ objects"] += 1
    print("pages holding a Python object under", prefix, ":", len(by_page))
    print(dict(kinds.most_common()))
    print(dict(sizes))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
