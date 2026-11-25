# tier: language
# world: none
declare -r x=1
declare +r x 2>/dev/null
echo "status=$?"
declare -p x
