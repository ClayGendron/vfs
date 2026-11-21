# tier: language
# world: none
set -e
f() { return 1; }
f && echo "not printed"
echo "continued"
