# tier: language
# world: none
f() { return 3; }
f
echo "status=$?"
g() { return 0; }
g
echo "status=$?"
