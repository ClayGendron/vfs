# tier: language
# world: none
declare -A m=([0]=zero [a]=b)
echo "[\$m=$m]"
declare -A n=([a]=b)
echo "[\$n=$n]"
