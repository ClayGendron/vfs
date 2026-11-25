# tier: language
# world: none
f() { return abc; echo "not reached"; }
f
echo "status=$?"
