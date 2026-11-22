# tier: language
# world: none
declare -A m
printf -v 'm[key]' '%s' value
echo "m[key]=${m[key]}"
