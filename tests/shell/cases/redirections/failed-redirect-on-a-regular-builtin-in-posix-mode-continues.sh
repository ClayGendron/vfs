# tier: language
# world: none
set -o posix
echo before
echo hi > nodir/out
echo "reached status=$?"
