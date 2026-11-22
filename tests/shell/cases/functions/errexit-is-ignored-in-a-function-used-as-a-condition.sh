# tier: language
# world: none
set -e
f() { false; echo "after false inside f"; }
f || echo "never printed"
if f; then echo "f returned true"; fi
echo "still running"
