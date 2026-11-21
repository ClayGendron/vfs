# tier: language
# world: none
a=("a b" "c d")
printf '[%s]\n' "${a[@]/ /_}"
