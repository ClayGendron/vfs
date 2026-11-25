# tier: language
# world: none
IFS=,
a=(x,y z)
v="p,q"
b=($v)
unset IFS
echo "a count=${#a[@]} b count=${#b[@]}"
printf '[%s]' "${a[@]}" "${b[@]}"; echo
