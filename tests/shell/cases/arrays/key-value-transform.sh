# tier: language
# world: none
declare -A m=([k]="v 1")
a=(x "y z")
echo "${m[@]@K}"
echo "${a[@]@K}"
