# tier: language
# world: none
f() { echo original; }
readonly -f f
f() { echo replaced; } 2>/dev/null
echo "status=$?"
f
