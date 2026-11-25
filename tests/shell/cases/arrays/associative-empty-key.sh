# tier: language
# world: none
declare -A m
m[""]=x
echo "status=$? count=${#m[@]}"
