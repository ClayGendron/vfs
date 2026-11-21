# tier: language
# world: none
f() { echo "in f"; (exit 4); }
f
echo "status=$?"
