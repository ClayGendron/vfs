# tier: language
# world: none
arr=(a b c)
declare -n r=arr
echo "via ref: ${r[*]} count=${#r[@]}"
r+=(d)
echo "arr: ${arr[*]}"
