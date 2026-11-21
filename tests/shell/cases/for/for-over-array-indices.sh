# tier: language
# world: none
arr=(x y z)
arr[7]=w
for i in "${!arr[@]}"; do echo "$i=${arr[i]}"; done
