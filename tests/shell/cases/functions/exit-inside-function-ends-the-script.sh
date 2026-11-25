# tier: language
# world: none
f() { echo before; exit 4; echo "after exit"; }
f
echo "not reached"
