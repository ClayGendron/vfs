# tier: language
# world: none
arr=(a b c)
printf -v arr '%s' NEW
printf '[%s]\n' "${arr[@]}"
