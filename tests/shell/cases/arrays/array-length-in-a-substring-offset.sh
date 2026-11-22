# tier: language
# world: none
a=(a b c d e)
n=2
echo "${a[@]:n:n}"
echo "${a[@]:${#a[@]}-2}"
