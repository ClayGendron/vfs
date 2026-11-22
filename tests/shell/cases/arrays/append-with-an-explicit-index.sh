# tier: language
# world: none
a=(a b)
a+=([5]=f g)
for i in "${!a[@]}"; do echo "$i=${a[i]}"; done
