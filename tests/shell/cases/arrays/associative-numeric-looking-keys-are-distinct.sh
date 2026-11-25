# tier: language
# world: none
declare -A m
m[1]=one
m[01]=zero-one
echo "1=${m[1]} 01=${m[01]} count=${#m[@]}"
