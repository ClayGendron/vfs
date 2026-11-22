# tier: language
# world: none
a=(x y)
declare -A a
echo "status=$? value=${a[0]}"
