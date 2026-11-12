"""Call fsspec's local du with and without total and maxdepth over the vfs src/ tree, and print the records."""
import json
import sys

import fsspec

root = sys.argv[1]
fs = fsspec.filesystem("file")
print("fsspec", fsspec.__version__)
total = fs.du(root)
print("du(total=True) ->", type(total).__name__, total)
per_file = fs.du(root, total=False)
print("du(total=False) -> dict with", len(per_file), "entries; first 3:", json.dumps(dict(list(per_file.items())[:3]), indent=None))
d1 = fs.du(root, total=False, maxdepth=1)
print("du(total=False, maxdepth=1) ->", len(d1), "entries:", json.dumps(d1, indent=None))
d1w = fs.du(root, total=False, maxdepth=1, withdirs=True)
print("du(total=False, maxdepth=1, withdirs=True) ->", len(d1w), "entries:", json.dumps(d1w, indent=None))
print("du(total=True, maxdepth=1) ->", fs.du(root, total=True, maxdepth=1))
print("du(total=True, withdirs=True) ->", fs.du(root, total=True, withdirs=True))
sizes = fs.sizes([f"{root}/vfs/base.py", f"{root}/vfs/native.py"])
print("sizes([...]) ->", sizes)
info = fs.info(root)
print("info(root) keys ->", sorted(info))
print("info(root) size ->", info["size"], "type", info["type"])
found = fs.find(root, maxdepth=1, withdirs=True, detail=True)
print("find(maxdepth=1, withdirs=True, detail=True) -> keys of first dir record:", sorted(next(v for v in found.values() if v["type"] == "directory")))
ls = fs.ls(root, detail=True)
print("ls(detail=True) record types ->", sorted({e["type"] for e in ls}), "dir size field ->", [e["size"] for e in ls if e["type"] == "directory"])
