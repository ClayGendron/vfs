# tier: language
# world: none
if false; then f() { echo defined; }; fi
f
echo "status=$?"
if true; then g() { echo "g defined"; }; fi
g
