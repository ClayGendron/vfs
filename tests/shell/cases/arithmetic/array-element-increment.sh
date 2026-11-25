# tier: language
# world: none
a=(5 9)
(( a[1]++ ))
(( a[0] += 10 ))
echo "${a[@]}"
