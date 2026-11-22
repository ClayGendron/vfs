# tier: language
# world: none
a=($(printf '%s\n' "one two" three))
echo "count=${#a[@]}"
printf '[%s]\n' "${a[@]}"
