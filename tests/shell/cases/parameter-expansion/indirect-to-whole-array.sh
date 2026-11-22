# tier: language
# world: none
arr=(a 'b c' d)
ref='arr[@]'
printf '[%s]\n' "${!ref}"
