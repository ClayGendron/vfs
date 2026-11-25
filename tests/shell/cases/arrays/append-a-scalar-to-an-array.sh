# tier: language
# world: none
a=(foo bar)
a+=baz
echo "${a[*]} count=${#a[@]}"
