# tier: language
# world: none
read -r -a parts <<< "red green  blue"
echo "count=${#parts[@]}"
printf '[%s]\n' "${parts[@]}"
