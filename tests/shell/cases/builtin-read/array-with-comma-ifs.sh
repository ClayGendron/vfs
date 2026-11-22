# tier: language
# world: none
IFS=, read -r -a parts <<< "a,b,,d"
echo "count=${#parts[@]}"
printf '[%s]\n' "${parts[@]}"
