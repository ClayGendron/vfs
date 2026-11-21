# tier: language
# world: none
# stderr: exact
declare -A m
mapfile m <<< "x"
echo "status=$?"
