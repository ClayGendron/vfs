# tier: language
# world: none
set -e
f() { false || return 4; echo "not reached"; }
echo "before"
f
echo "not reached"
