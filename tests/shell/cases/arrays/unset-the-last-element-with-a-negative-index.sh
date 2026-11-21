# tier: language
# world: none
a=(a b c)
unset 'a[-1]'
echo "${a[*]} count=${#a[@]}"
