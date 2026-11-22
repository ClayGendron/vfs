# tier: language
# world: none
set -e
inner() { false; echo "inner continues"; }
outer() { inner; echo "outer continues"; }
if outer; then echo "condition true"; fi
