# tier: language
# world: none
read -r -a arr <<< '  a b  c '
echo "count=${#arr[@]}"
printf '[%s]\n' "${arr[@]}"
IFS=: read -r -a arr <<< 'a::b'
echo "count=${#arr[@]}"
