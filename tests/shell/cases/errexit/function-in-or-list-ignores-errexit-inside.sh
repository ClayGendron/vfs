# tier: language
# world: none
set -e
f() { false; echo "still in f"; }
f || echo "handler"
echo "continued"
