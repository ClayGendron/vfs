# tier: language
# world: none
declare -A m
read 'm[k]' <<< "val"
echo "m[k]=${m[k]}"
