# tier: language
# world: none
f() { echo here; }
f
unset -f f
f
echo "status=$?"
