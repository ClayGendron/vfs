# tier: language
# world: none
a=(a b c d e)
expr="1+2"
echo "${a[expr]} ${a[$expr]}"
