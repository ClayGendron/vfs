# tier: language
# world: none
read -a arr <<< 'one\ two three'
echo "count=${#arr[@]}"
printf '[%s]\n' "${arr[@]}"
