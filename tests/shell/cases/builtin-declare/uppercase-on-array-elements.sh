# tier: language
# world: none
declare -au a=(one two)
a+=(three)
printf '[%s]\n' "${a[@]}"
