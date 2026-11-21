# tier: language
# world: none
readonly -a arr=(1 2)
arr[0]=9 2>/dev/null
echo "status=$?"
printf '[%s]\n' "${arr[@]}"
