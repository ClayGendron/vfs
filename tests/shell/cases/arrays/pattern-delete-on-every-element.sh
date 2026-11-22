# tier: language
# world: none
a=(a1b2 c3d4)
echo "${a[@]//[0-9]/}"
echo "${a[@]//[a-z]}"
