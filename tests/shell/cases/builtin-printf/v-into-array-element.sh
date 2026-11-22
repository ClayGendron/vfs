# tier: language
# world: none
arr=(zero one two)
printf -v 'arr[1]' '%s' ONE
printf -v 'arr[5]' '%d' 5
printf '[%s]\n' "${arr[@]}"
echo "count=${#arr[@]}"
