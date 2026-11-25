# tier: language
# world: none
declare -A m=(k1 v1 "key two" "value two")
echo "k1=${m[k1]} key two=${m[key two]} count=${#m[@]}"
