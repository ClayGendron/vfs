# tier: language
# world: none
f() { false || return 3; echo "not printed"; }
f
echo "status=$?"
