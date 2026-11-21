# tier: language
# world: none
arr=(zero one two)
mapfile -t -O 5 arr <<< $'five\nsix'
echo "count=${#arr[@]}"
for i in "${!arr[@]}"; do echo "$i=${arr[i]}"; done
