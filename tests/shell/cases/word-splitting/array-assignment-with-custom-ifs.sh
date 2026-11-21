# tier: language
# world: none
IFS=,
v='a,b,,c'
arr=($v)
echo "count=${#arr[@]}"
printf '[%s]\n' "${arr[@]}"
