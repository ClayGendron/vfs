# tier: language
# world: none
f() { echo working; false; }
f; echo "status=$?"
g() { false; echo recovered; }
g; echo "status=$?"
