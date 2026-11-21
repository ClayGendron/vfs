# tier: language
# world: none
a=(zero one two)
declare -n ref='a[1]'
echo "ref=$ref"
ref=ONE
echo "a=${a[*]}"
