# tier: language
# world: none
IFS=, read -a parts <<< "a,b,"
echo "count=${#parts[@]}"
IFS=, read -a parts <<< ",a"
echo "count=${#parts[@]} first=[${parts[0]}]"
