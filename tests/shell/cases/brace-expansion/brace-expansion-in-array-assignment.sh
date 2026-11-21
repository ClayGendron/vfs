# tier: language
# world: none
arr=({1..3} x{a,b})
echo "${#arr[@]}: ${arr[*]}"
