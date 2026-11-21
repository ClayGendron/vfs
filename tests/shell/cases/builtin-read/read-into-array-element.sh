# tier: language
# world: none
arr=(a b c)
read 'arr[1]' <<< "B"
echo "${arr[*]}"
