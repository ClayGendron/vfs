# tier: language
# world: none
arr=(a b c d e)
printf '[%s]\n' "${arr[@]:1:2}"
echo "${arr[@]: -2}"
