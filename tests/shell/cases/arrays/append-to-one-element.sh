# tier: language
# world: none
a=(foo bar)
a[0]+=-suffix
a[1]+=2
echo "${a[*]}"
