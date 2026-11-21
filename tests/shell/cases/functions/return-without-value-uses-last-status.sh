# tier: language
# world: none
f() { false; return; }
f; echo "after false: $?"
g() { true; return; }
g; echo "after true: $?"
