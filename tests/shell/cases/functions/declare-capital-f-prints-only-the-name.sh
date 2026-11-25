# tier: language
# world: none
f() { echo hi; }
declare -F f
echo "status=$?"
