# tier: language
# world: none
set -e
f() { false; echo "in f"; }
! f
echo "continued status=$?"
