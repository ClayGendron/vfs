# tier: language
# world: none
arr=(inc lib src)
printf '[%s]\n' "${arr[@]/#/-I}"
