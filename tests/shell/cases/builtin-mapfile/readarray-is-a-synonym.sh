# tier: language
# world: none
readarray -t arr <<< $'x\ny'
echo "count=${#arr[@]} [${arr[0]}] [${arr[1]}]"
