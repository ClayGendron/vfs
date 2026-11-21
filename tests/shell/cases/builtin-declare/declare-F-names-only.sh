# tier: language
# world: none
f() { :; }
declare -F f
echo "status=$?"
declare -F nosuch
echo "missing status=$?"
