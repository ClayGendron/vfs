# tier: language
# world: none
a=(x y)
a[1]+=z
a[5]+=new
echo "${a[@]} count=${#a[@]}"
