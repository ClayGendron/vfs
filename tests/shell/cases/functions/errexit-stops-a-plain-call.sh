# tier: language
# world: none
set -e
f() { echo start; false; echo "not reached"; }
f
echo "not reached either"
