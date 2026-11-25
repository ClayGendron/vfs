# tier: language
# world: none
g() { echo "g sees $x"; }
f() { local x=from-f; g; }
x=top
f
g
