# tier: language
# world: none
arr=(keep0 keep1 keep2)
mapfile -t -O 1 arr <<< $'new1\nnew2'
for i in "${!arr[@]}"; do echo "$i=${arr[i]}"; done
