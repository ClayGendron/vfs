# tier: language
# world: none
declare -a a=([5]=x [2]=y)
echo "indices=${!a[*]}"
echo "count=${#a[@]}"
a+=(z)
declare -p a
