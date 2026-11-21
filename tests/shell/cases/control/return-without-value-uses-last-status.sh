# tier: language
# world: none
f() { false; return; }
f
echo "status=$?"
g() { (exit 6); return; }
g
echo "status=$?"
