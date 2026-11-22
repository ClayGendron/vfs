# tier: language
# world: none
IFS=' ,' read -r -a parts <<< "a , b,,c"
echo "count=${#parts[@]}"
printf '[%s]\n' "${parts[@]}"
