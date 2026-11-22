# tier: language
# world: none
a=(1 2)
b=("three four" 5)
c=("${a[@]}" "${b[@]}")
echo "count=${#c[@]}"
printf '[%s]' "${c[@]}"; echo
