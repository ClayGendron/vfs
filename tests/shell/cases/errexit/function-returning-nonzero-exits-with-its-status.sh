# tier: language
# world: none
set -e
f() { return 2; }
echo "before"
f
echo "not reached"
