# tier: language
# world: none
a=(a b c d)
a=("${a[@]:1}")
echo "${a[*]} indices=${!a[*]}"
