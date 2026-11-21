# tier: language
# world: none
set -e
f() { [ -n "" ] && echo "not printed"; }
f
echo "not reached"
