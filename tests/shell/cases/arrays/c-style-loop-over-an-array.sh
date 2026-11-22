# tier: language
# world: none
a=(red green blue)
for (( i = 0; i < ${#a[@]}; i++ )); do echo "$i: ${a[i]}"; done
