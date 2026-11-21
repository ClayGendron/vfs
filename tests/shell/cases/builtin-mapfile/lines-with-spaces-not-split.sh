# tier: language
# world: none
mapfile -t arr <<< $'  lead\ttab  \n*'
printf '[%s]\n' "${arr[@]}"
echo "count=${#arr[@]}"
