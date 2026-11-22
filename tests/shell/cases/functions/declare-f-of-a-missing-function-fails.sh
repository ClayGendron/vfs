# tier: language
# world: none
declare -f no_such_function
echo "status=$?"
declare -F no_such_function
echo "status=$?"
