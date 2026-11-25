# tier: language
# world: none
declare -a a=(x y z)
echo "count=${#a[@]} second=${a[1]}"
declare -p a
