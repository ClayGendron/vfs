# tier: language
# world: none
a=(a b c d)
echo "count=${#a[@]} star=${#a[*]}"
e=()
echo "empty count=${#e[@]}"
unset u
echo "unset count=${#u[@]}"
