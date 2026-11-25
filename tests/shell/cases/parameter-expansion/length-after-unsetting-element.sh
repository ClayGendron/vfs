# tier: language
# world: none
arr=(a b c d)
unset 'arr[1]'
echo "count=${#arr[@]} keys=${!arr[*]}"
