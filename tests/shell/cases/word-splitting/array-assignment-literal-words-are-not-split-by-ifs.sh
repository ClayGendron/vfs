# tier: language
# world: none
IFS=,
arr=(a,b c)
echo "count=${#arr[@]}"
printf '[%s]\n' "${arr[@]}"
