# tier: language
# world: none
a=([3]=x)
a+=(y)
a[${#a[@]}]=z
echo "indices=${!a[*]}"
for i in "${!a[@]}"; do echo "$i=${a[i]}"; done
