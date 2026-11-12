"""Call pyfilesystem2's glob count over the vfs src/ tree and print the Counts record."""
import sys

import fs
from fs.osfs import OSFS

root = sys.argv[1]
print("fs", fs.__version__)
osfs = OSFS(root)
counts = osfs.glob("**/*.py").count()
print("glob('**/*.py').count() ->", repr(counts))
print("fields ->", counts._fields)
counts_all = osfs.glob("**").count()
print("glob('**').count() ->", repr(counts_all))
counts_dirs = osfs.glob("**/").count()
print("glob('**/').count() ->", repr(counts_dirs))
info = osfs.getinfo("vfs", namespaces=["details"])
print("getinfo('vfs', details) size ->", info.size, "is_dir ->", info.is_dir)
print("getsize('vfs/base.py') ->", osfs.getsize("vfs/base.py"))
steps = list(osfs.walk(max_depth=1))
print("walk(max_depth=1) first Step ->", steps[0].path, "dirs", len(steps[0].dirs), "files", len(steps[0].files))
