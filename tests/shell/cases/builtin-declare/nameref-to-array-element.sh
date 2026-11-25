# tier: language
# world: none
arr=(a b c)
declare -n r='arr[1]'
r=Z
echo "arr: ${arr[*]}"
