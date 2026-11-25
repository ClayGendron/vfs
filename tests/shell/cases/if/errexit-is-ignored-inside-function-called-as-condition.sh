# tier: language
# world: none
set -e
f() { false; echo "f kept running"; }
if f; then echo "f returned success"; fi
