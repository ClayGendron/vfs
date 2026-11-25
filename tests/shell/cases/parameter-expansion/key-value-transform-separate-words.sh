# tier: language
# world: none
arr=(a 'b c')
printf '[%s]\n' "${arr[@]@k}"
printf '[%s]\n' "${arr[@]@K}"
