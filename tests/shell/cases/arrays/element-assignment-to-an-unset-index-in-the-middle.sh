# tier: language
# world: none
a=(a b c)
a[1]=B
a[10]=K
echo "${a[*]} count=${#a[@]} last-index=${!a[*]}"
