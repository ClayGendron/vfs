# tier: language
# world: none
a=(x y)
declare -n r=a
r+=(z)
echo "count=${#r[@]} a=${a[*]}"
