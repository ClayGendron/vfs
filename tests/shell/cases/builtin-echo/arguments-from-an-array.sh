# tier: language
# world: none
arr=(-n "a b" c)
echo "${arr[@]}"
echo "|"
echo "${arr[*]}"
arr=()
echo "${arr[@]}" "[empty]"
