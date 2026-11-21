# tier: language
# world: none
a=(hello world)
echo "${a[0]:1:3} ${a[1]: -3} ${a[1]:2}"
