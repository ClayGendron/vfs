# tier: language
# world: none
declare -a a=(1)
declare -A a 2>/dev/null
echo "status=$?"
declare -p a
