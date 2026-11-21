# tier: language
# world: none
declare -A m=([a]=hello)
echo "${m[a]^^} ${m[@]/l/L} ${m[a]:1:3}"
