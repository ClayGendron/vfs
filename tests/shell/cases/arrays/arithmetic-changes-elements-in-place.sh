# tier: language
# world: none
a=(1 2 3)
(( a[0]++ ))
(( a[1] *= 10 ))
(( a[5] = 7 ))
echo "${a[*]} indices=${!a[*]}"
let 'a[2] += 4'
echo "${a[2]}"
