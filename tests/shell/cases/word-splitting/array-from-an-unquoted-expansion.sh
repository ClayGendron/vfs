# tier: language
# world: none
v='a b  c'
arr=($v)
echo "count=${#arr[@]}"
printf '[%s]\n' "${arr[@]}"
