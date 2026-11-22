# tier: language
# world: none
a=(x y z)
echo "indices: ${!a[@]}"
for i in "${!a[@]}"; do echo "$i=${a[i]}"; done
