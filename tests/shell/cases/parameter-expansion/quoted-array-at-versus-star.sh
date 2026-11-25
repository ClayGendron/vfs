# tier: language
# world: none
arr=(a 'b c' d)
printf '[%s]\n' "${arr[@]}"
printf '[%s]\n' "${arr[*]}"
