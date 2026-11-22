# tier: language
# world: none
a=(x)
a+=(y z)
echo "${a[@]} count=${#a[@]}"
a+=w
echo "${a[@]}"
