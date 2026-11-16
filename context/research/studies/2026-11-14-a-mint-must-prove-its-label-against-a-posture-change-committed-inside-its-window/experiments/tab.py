"""Tabulate the experiment's JSON-lines output: tab.py <tag>."""
import collections
import json
import pathlib
import sys

tag = sys.argv[1]
out = pathlib.Path(__file__).parent / "out"
rows = []
for path in sorted(out.glob(f"{tag}-*.jsonl")):
    rows += [json.loads(line) for line in path.read_text().splitlines()]
for kind in ("tighten", "loosen", "transfer", "restore"):
    found = [row for row in rows if row["kind"] == kind]
    if not found:
        continue
    print(f"== {kind}")
    by = collections.defaultdict(dict)
    for row in found:
        engine, _, rest = row["leg"].partition("/")
        by[rest or "-"][engine] = row["outcome"]
    engines = sorted({row["leg"].partition("/")[0] for row in found})
    print("  " + " | ".join(["leg".ljust(52), *engines]))
    for leg in sorted(by):
        print("  " + " | ".join([leg.ljust(52), *(by[leg].get(e, "?").ljust(len(e)) for e in engines)]))
for kind in ("attempts", "statements", "contention", "contention-labels", "loosen-read", "locks"):
    found = [row for row in rows if row["kind"] == kind]
    if kind == "attempts":
        tally = collections.Counter((row["leg"].split("/")[0], row["attempts"]) for row in found)
        print("== attempts per call (engine, attempts): count", dict(tally))
    elif kind == "loosen-read":
        print("== loosen: carol reads", collections.Counter((r["leg"].split("/")[0], r["carol_reads"]) for r in found))
    else:
        for row in found:
            print(f"== {kind}", {k: v for k, v in row.items() if k != "kind"})
