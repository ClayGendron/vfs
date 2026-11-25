# tier: language
# world: none
arr=(one two three)
printf '[%s]\n' "${arr[@]//e/E}"
