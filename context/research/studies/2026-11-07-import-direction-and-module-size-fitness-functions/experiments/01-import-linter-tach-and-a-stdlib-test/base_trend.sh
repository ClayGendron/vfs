#!/bin/sh
# Line count of src/vfs/base.py at each commit that touched it in the last ten days, oldest first.
cd "$(dirname "$0")/../../../../../.." || exit 1
echo "date       sha      lines  (src/vfs/base.py at that commit)"
git log --since=10.days --reverse --format='%cs %h' -- src/vfs/base.py | while read -r d h; do
  n=$(git show "$h:src/vfs/base.py" | wc -l | tr -d ' ')
  echo "$d $h $n"
done
echo "working tree now: $(wc -l < src/vfs/base.py | tr -d ' ')"
