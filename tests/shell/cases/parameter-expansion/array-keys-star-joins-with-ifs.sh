# tier: language
# world: none
arr=(a b c)
IFS=,
echo "${!arr[*]}"
