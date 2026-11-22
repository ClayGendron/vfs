# tier: language
# world: none
f() { echo still-here; }
readonly -f f
unset -f f 2>/dev/null
echo "status=$?"
f
