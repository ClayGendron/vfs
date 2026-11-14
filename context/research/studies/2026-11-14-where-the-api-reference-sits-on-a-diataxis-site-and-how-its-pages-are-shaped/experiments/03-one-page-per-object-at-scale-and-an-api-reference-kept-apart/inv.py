"""Decode a Sphinx objects.inv and count the distinct pages it points at, by path prefix.

Usage: python3 -I inv.py <objects.inv> <depth>, where depth is how many path
segments make a prefix (1 groups by top folder, 2 by the folder beneath it).
"""

import re
import sys
import zlib
from collections import Counter


def main(path: str, depth: int) -> None:
    with open(path, "rb") as handle:
        header = [handle.readline().decode().strip() for _ in range(4)]
        body = zlib.decompress(handle.read()).decode()
    print(header[1], "|", header[2])
    pages: set[str] = set()
    terms = 0
    roles: Counter[str] = Counter()
    for line in body.splitlines():
        match = re.match(r"(.+?)\s+(\S+:\S+)\s+(-?\d+)\s+(\S+)\s+(.*)", line)
        if match is None:
            continue
        name, role, _priority, uri = match.groups()[:4]
        if uri.endswith("$"):
            uri = uri[:-1] + name
        pages.add(uri.split("#")[0])
        roles[role] += 1
        if role == "std:term":
            terms += 1
    print("objects:", sum(roles.values()), "distinct pages:", len(pages), "std:term:", terms)
    prefixes: Counter[str] = Counter()
    for page in pages:
        prefixes["/".join(page.split("/")[:depth])] += 1
    for prefix, count in prefixes.most_common(25):
        print(f"{count:6d}  {prefix}")
    print("roles:", dict(roles.most_common(12)))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
